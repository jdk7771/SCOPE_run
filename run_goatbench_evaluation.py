import os
import shutil

os.environ["TRANSFORMERS_VERBOSITY"] = "error"  # disable warning
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["HABITAT_SIM_LOG"] = (
    "quiet"  # https://aihabitat.org/docs/habitat-sim/logging.html
)
os.environ["MAGNUM_LOG"] = "quiet"

import argparse
from omegaconf import OmegaConf
import random
import numpy as np
import torch
import math
import time
import json
import logging
import matplotlib.pyplot as plt
import open_clip
from ultralytics import SAM, YOLOWorld

from src.habitat import pose_habitat_to_tsdf
from src.geom import get_cam_intr, get_scene_bnds
from src.tsdf_planner import TSDFPlanner, Frontier, SnapShot
from src.scene_goatbench import Scene
from src.utils import resize_image, calc_agent_subtask_distance, get_pts_angle_goatbench
from src.goatbench_utils import prepare_goatbench_navigation_goals
from src.query_vlm_goatbench import query_vlm_for_response
from src.logger_goatbench import Logger
from src.potential_graph import PotentialGraph
from src.potential_estimation_gpt_goal import get_potential_estimation
from src.tsdf_export import save_bev_visualization, save_frontier_gaussian_bev
from src.vlm_timing import configure_vlm_timing, log_vlm_timing_summary


def select_scope_frontier_candidates(tsdf_planner, potential_graph, max_candidates=3):
    """Keep the highest SCOPE-scored frontiers and preserve that F1..Fn order."""
    ranked = []
    for frontier in tsdf_planner.frontiers:
        prediction = potential_graph.get_frontier_prediction(frontier.position)
        if prediction is not None:
            scores = prediction["scores"]
            score = float(scores.get("potential_score", 0.0))
        else:
            scores = {"potential_score": 3.0, "semantic_richness": 3.0,
                      "explorability": 3.0, "goal_relevance": 3.0}
            try:
                world = potential_graph._voxel_to_world(frontier.position)
                score = float(potential_graph.get_potential_at_position(np.array([world[0], world[2]])))
            except Exception:
                score = 0.0
        ranked.append((score, int(frontier.frontier_id), frontier, scores))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked[:max(1, int(max_candidates))]


def main(cfg, start_ratio=0.0, end_ratio=1.0, split=1, scene_name_filter=None):
    configure_vlm_timing(
        cfg.output_dir,
        {
            "experiment": str(getattr(cfg, "exp_name", "")),
            "split": int(split),
            "start_ratio": float(start_ratio),
            "end_ratio": float(end_ratio),
            "scene_name": scene_name_filter or "",
        },
    )
    # load the default concept graph config
    cfg_cg = OmegaConf.load(cfg.concept_graph_config_path)
    OmegaConf.resolve(cfg_cg)

    img_height = cfg.img_height
    img_width = cfg.img_width
    cam_intr = get_cam_intr(cfg.hfov, img_height, img_width)

    random.seed(cfg.seed)
    np.random.seed(cfg.seed)

    # Load dataset
    scene_data_list = os.listdir(cfg.test_data_dir)
    if scene_name_filter:
        scene_name_filter = scene_name_filter.split("-", 1)[-1]
        scene_data_list = [
            filename
            for filename in scene_data_list
            if os.path.splitext(filename)[0] == scene_name_filter
        ]
        if not scene_data_list:
            raise ValueError(f"No GOAT-Bench data found for scene: {scene_name_filter}")
    num_scene = len(scene_data_list)
    random.shuffle(scene_data_list)
    # split the test data by scene
    scene_data_list = scene_data_list[
        int(start_ratio * num_scene) : int(end_ratio * num_scene)
    ]
    num_episode = 0
    for scene_data_file in scene_data_list:
        with open(os.path.join(cfg.test_data_dir, scene_data_file), "r") as f:
            num_episode += len(json.load(f)["episodes"])
    logging.info(
        f"Total number of episodes: {num_episode}; Selected episodes: {len(scene_data_list)}"
    )
    logging.info(f"Total number of scenes: {len(scene_data_list)}")

    all_scene_ids = os.listdir(cfg.scene_data_path + "/train") + os.listdir(
        cfg.scene_data_path + "/val"
    )

    # load detection and segmentation models
    detection_model = YOLOWorld(cfg.yolo_model_name)
    logging.info(f"Load YOLO model {cfg.yolo_model_name} successful!")

    sam_predictor = SAM(cfg.sam_model_name)
    logging.info(f"Load SAM model {cfg.sam_model_name} successful!")

    clip_model, _, clip_preprocess = open_clip.create_model_and_transforms(
        "ViT-B-32", "laion2b_s34b_b79k"
    )
    clip_tokenizer = open_clip.get_tokenizer("ViT-B-32")
    logging.info(f"Load CLIP model successful!")

    # Initialize the logger
    logger = Logger(
        cfg.output_dir, start_ratio, end_ratio, split, voxel_size=cfg.tsdf_grid_size
    )

    for scene_data_file in scene_data_list:
        # load goatbench data
        # print(scene_data_file)
        scene_name = scene_data_file.split(".")[0]
        # print(scene_name)
        # input("debug")
        scene_id = [scene_id for scene_id in all_scene_ids if scene_name in scene_id][0]
        scene_data = json.load(
            open(os.path.join(cfg.test_data_dir, scene_data_file), "r")
        )

        # selecat the episodes according to the split
        scene_data["episodes"] = scene_data["episodes"][split - 1 : split]
        total_episodes = len(scene_data["episodes"])

        all_navigation_goals = scene_data[
            "goals"
        ]

        for episode_idx, episode in enumerate(scene_data["episodes"]):
            logging.info(f"Episode {episode_idx + 1}/{total_episodes}")
            logging.info(f"Loading scene {scene_id}")
            episode_id = episode["episode_id"]

            all_subtask_goal_types, all_subtask_goals = (
                prepare_goatbench_navigation_goals(
                    scene_name=scene_name,
                    episode=episode,
                    all_navigation_goals=all_navigation_goals,
                )
            )
            # print(all_subtask_goals)
            # print(all_subtask_goal_types)
            # input("debug")

            finished_subtask_ids = list(logger.success_by_snapshot.keys())
            finished_episode_subtask = [
                subtask_id
                for subtask_id in finished_subtask_ids
                if subtask_id.startswith(f"{scene_id}_{episode_id}_")
            ]
            if len(finished_episode_subtask) >= len(all_subtask_goals):
                logging.info(f"Scene {scene_id} Episode {episode_id} already done!")
                continue

            pts, angle = get_pts_angle_goatbench(
                episode["start_position"], episode["start_rotation"]
            )


            try:
                del scene
            except:
                pass
            scene = Scene(
                scene_id,
                cfg,
                cfg_cg,
                detection_model,
                sam_predictor,
                clip_model,
                clip_preprocess,
                clip_tokenizer,
            )

            # initialize the TSDF
            floor_height = pts[1]
            # print(pts)
            # input("debug")
            tsdf_bnds, scene_size = get_scene_bnds(scene.pathfinder, floor_height)
            num_step = int(math.sqrt(scene_size) * cfg.max_step_room_size_ratio)
            num_step = max(num_step, 50)
            tsdf_planner = TSDFPlanner(
                vol_bnds=tsdf_bnds,
                voxel_size=cfg.tsdf_grid_size,
                floor_height=floor_height,
                floor_height_offset=0,
                pts_init=pts,
                init_clearance=cfg.init_clearance * 2,
                save_visualization=cfg.save_visualization,
            )

            # Initialize potential graph for this episode with correct bounds format
            logging.info(f"TSDF bounds shape: {tsdf_bnds.shape}, bounds: {tsdf_bnds}")
            potential_graph = PotentialGraph(
                vol_bounds=tsdf_bnds,
                voxel_size=cfg.tsdf_grid_size,
                grid_resolution=getattr(cfg, 'potential_grid_resolution', 1.0),
                decay_factor=getattr(cfg, 'potential_decay_factor', 0.95),
                influence_radius=getattr(cfg, 'potential_influence_radius', 3.0),
            )

            episode_dir, eps_frontier_dir, eps_snapshot_dir, eps_potential_dir = logger.init_episode(
                episode_id=f"{scene_id}_ep_{episode_id}"
            )

            # Create potential graph visualization directory
            eps_potential_dir = os.path.join(episode_dir, "potential_graph")
            os.makedirs(eps_potential_dir, exist_ok=True)
            eps_potential_vlm_input_dir = os.path.join(eps_potential_dir, "vlm_inputs")
            os.makedirs(eps_potential_vlm_input_dir, exist_ok=True)

            logging.info(f"\n\nScene {scene_id} initialization successful!")

            # run questions in the scene
            global_step = -1
            for subtask_idx, (goal_type, subtask_goal) in enumerate(
                zip(all_subtask_goal_types, all_subtask_goals)
            ):
                subtask_id = f"{scene_id}_{episode_id}_{subtask_idx}"
                logging.info(
                    f"\nScene {scene_id} Episode {episode_id} Subtask {subtask_idx + 1}/{len(all_subtask_goals)}"
                )

                subtask_metadata = logger.init_subtask(
                    subtask_id=subtask_id,
                    goal_type=goal_type,
                    subtask_goal=subtask_goal,
                    pts=pts,
                    scene=scene,
                    tsdf_planner=tsdf_planner,
                )

                # mapping from the obj id in habitat to the id assigned by concept graph
                # this mapping/alignment is done by heuristic matching between object masks
                goal_obj_ids_mapping = {
                    obj_id: [] for obj_id in subtask_metadata["goal_obj_ids"]
                }
                # print(goal_obj_ids_mapping)
                # input("debug")
                # run steps
                task_success = False
                cnt_step = -1
                n_filtered_snapshots = 0
                # Seed the semantic BEV with the known target category.  Later
                # VLM prefiltering replaces this with SCOPE's relevance ranking.
                relevant_object_classes = [subtask_metadata["class"]]

                # reset tsdf planner
                tsdf_planner.max_point = None
                tsdf_planner.target_point = None
                max_point_choice = None
                candidate_frontiers = []
                structured_decision = None

                if cfg.clear_up_memory_every_subtask and subtask_idx > 0:
                    scene.clear_up_detections()
                    tsdf_planner = TSDFPlanner(
                        vol_bnds=tsdf_bnds,
                        voxel_size=cfg.tsdf_grid_size,
                        floor_height=floor_height,
                        floor_height_offset=0,
                        pts_init=pts,
                        init_clearance=cfg.init_clearance * 2,
                        save_visualization=cfg.save_visualization,
                    )
                    # Also reset potential graph for new subtask if needed
                    potential_graph = PotentialGraph(
                        vol_bounds=tsdf_bnds,
                        voxel_size=cfg.tsdf_grid_size,
                        grid_resolution=getattr(cfg, 'potential_grid_resolution', 1.0),
                        decay_factor=getattr(cfg, 'potential_decay_factor', 0.95),
                        influence_radius=getattr(cfg, 'potential_influence_radius', 3.0),
                    )

                while cnt_step < num_step - 1:
                    cnt_step += 1
                    global_step += 1
                    logging.info(
                        f"\n== step: {cnt_step}, global step: {global_step} =="
                    )

                    # (1) Observe the surroundings, update the scene graph and occupancy map
                    # Determine the viewing angles for the current step
                    if cnt_step == 0:
                        angle_increment = cfg.extra_view_angle_deg_phase_2 * np.pi / 180
                        total_views = 1 + cfg.extra_view_phase_2
                    else:
                        angle_increment = cfg.extra_view_angle_deg_phase_1 * np.pi / 180
                        total_views = 1 + cfg.extra_view_phase_1
                    all_angles = [
                        angle + angle_increment * (i - total_views // 2)
                        for i in range(total_views)
                    ]
                    # Let the main viewing angle be the last one to avoid potential overwriting problems
                    main_angle = all_angles.pop(total_views // 2)
                    all_angles.append(main_angle)

                    rgb_egocentric_views = []
                    all_added_obj_ids = (
                        []
                    )
                    for view_idx, ang in enumerate(all_angles):

                        obs, cam_pose = scene.get_observation(pts, angle=ang)
                        rgb = obs["color_sensor"]
                        depth = obs["depth_sensor"]
                        semantic_obs = obs["semantic_sensor"]

                        # collect all view features
                        obs_file_name = f"{global_step}-view_{view_idx}.png"
                        with torch.no_grad():
                            # Concept graph pipeline update
                            annotated_rgb, added_obj_ids, target_obj_id_mapping = (
                                scene.update_scene_graph(
                                    image_rgb=rgb[..., :3],
                                    depth=depth,
                                    intrinsics=cam_intr,
                                    cam_pos=cam_pose,
                                    pts=pts,
                                    pts_voxel=tsdf_planner.habitat2voxel(pts),
                                    img_path=obs_file_name,
                                    frame_idx=cnt_step * total_views + view_idx,
                                    semantic_obs=semantic_obs,
                                    gt_target_obj_ids=subtask_metadata["goal_obj_ids"],
                                )
                            )
                            scene.all_observations[obs_file_name] = rgb
                            rgb_egocentric_views.append(
                                resize_image(rgb, cfg.prompt_h, cfg.prompt_w)
                            )
                            if cfg.save_visualization:
                                plt.imsave(
                                    os.path.join(eps_snapshot_dir, obs_file_name),
                                    annotated_rgb,
                                )
                            else:
                                plt.imsave(
                                    os.path.join(eps_snapshot_dir, obs_file_name), rgb
                                )
                            # update the mapping of hm3d object id to our detected object id
                            for (
                                gt_goal_id,
                                det_goal_id,
                            ) in target_obj_id_mapping.items():
                                goal_obj_ids_mapping[gt_goal_id].append(det_goal_id)
                            all_added_obj_ids += added_obj_ids

                        # Clean up or merge redundant objects periodically
                        scene.periodic_cleanup_objects(
                            frame_idx=cnt_step * total_views + view_idx,
                            pts=pts,
                            goal_obj_ids_mapping=goal_obj_ids_mapping,
                        )

                        # Update depth map, occupancy map
                        tsdf_planner.integrate(
                            color_im=rgb,
                            depth_im=depth,
                            cam_intr=cam_intr,
                            cam_pose=pose_habitat_to_tsdf(cam_pose),
                            obs_weight=1.0,
                            margin_h=int(cfg.margin_h_ratio * img_height),
                            margin_w=int(cfg.margin_w_ratio * img_width),
                            explored_depth=cfg.explored_depth,
                        )
                    logging.info(f"Goal object mapping: {goal_obj_ids_mapping}")

                    # (2) Update Memory Snapshots with hierarchical clustering
                    # Choose all the newly added objects as well as the objects nearby as the cluster targets
                    all_added_obj_ids = [
                        obj_id
                        for obj_id in all_added_obj_ids
                        if obj_id in scene.objects
                    ]
                    for obj_id, obj in scene.objects.items():
                        if (
                            np.linalg.norm(obj["bbox"].center[[0, 2]] - pts[[0, 2]])
                            < cfg.scene_graph.obj_include_dist + 0.5
                        ):
                            all_added_obj_ids.append(obj_id)
                    scene.update_snapshots(
                        obj_ids=set(all_added_obj_ids), min_detection=cfg.min_detection
                    )
                    logging.info(
                        f"Step {cnt_step}, update snapshots, {len(scene.objects)} objects, {len(scene.snapshots)} snapshots"
                    )
                    # (3) Update the Frontier Snapshots
                    update_success = tsdf_planner.update_frontier_map(
                        pts=pts,
                        cfg=cfg.planner,
                        scene=scene,
                        cnt_step=cnt_step,
                        save_frontier_image=cfg.save_visualization,
                        eps_frontier_dir=eps_frontier_dir,
                        prompt_img_size=(cfg.prompt_h, cfg.prompt_w),
                    )
                    if not update_success:
                        logging.info("Warning! Update frontier map failed!")

                    # Update potential graph with current frontiers
                    if len(tsdf_planner.frontiers) > 0:
                        if not hasattr(potential_graph, '_analyzed_frontiers'):
                            potential_graph._analyzed_frontiers = set()

                        for i, frontier in enumerate(tsdf_planner.frontiers):

                            frontier_key = (tuple(frontier.position), frontier.image)
                            if frontier_key in potential_graph._analyzed_frontiers: 
                                continue

                            if frontier.feature is not None and getattr(cfg, 'enable_potential_estimation', True):
                                try:
                                    potential_text = get_potential_estimation(subtask_metadata, frontier.feature)
                                    logging.info(f"Frontier {i} potential estimation: {potential_text}")
                                    potential_input_name = f"step_{global_step}_subtask_{subtask_idx}_frontier_{i}"
                                    plt.imsave(
                                        os.path.join(eps_potential_vlm_input_dir, f"{potential_input_name}_frontier.png"),
                                        frontier.feature,
                                    )
                                    with open(os.path.join(eps_potential_vlm_input_dir, f"{potential_input_name}_metadata.json"), "w") as f:
                                        json.dump(
                                            {
                                                "global_step": global_step,
                                                "cnt_step": cnt_step,
                                                "subtask_idx": subtask_idx,
                                                "frontier_index": i,
                                                "frontier_image": frontier.image,
                                                "frontier_position_voxel": frontier.position.tolist(),
                                                "question": subtask_metadata["question"],
                                                "task_type": subtask_metadata["task_type"],
                                                "target_class": subtask_metadata["class"],
                                                "goal_image": subtask_metadata.get("image"),
                                            },
                                            f,
                                            indent=2,
                                        )
                                    with open(os.path.join(eps_potential_vlm_input_dir, f"{potential_input_name}_response.txt"), "w") as f:
                                        f.write(potential_text or "")
                                    
                                    potential_graph.update_from_frontier(
                                        frontier=frontier,
                                        subtask_metadata=subtask_metadata,
                                        occupied_map=None,
                                        potential_text=potential_text
                                    )

                                    potential_graph._analyzed_frontiers.add(frontier_key)

                                    # Log the resulting potential score
                                    frontier_world_pos = potential_graph._voxel_to_world(frontier.position)
                                    final_score = potential_graph.get_potential_at_position(np.array([frontier_world_pos[0], frontier_world_pos[2]]))
                                    logging.info(f"Frontier {i} final potential score: {final_score:.2f}")
                                    if cfg.save_visualization:
                                        potential_graph.visualize(
                                            save_path=os.path.join(
                                                eps_potential_dir,
                                                f"potential_after_frontier_{global_step}_{subtask_id}_{i}.png",
                                            ),
                                            title=f"After Frontier {i} - Step {cnt_step}",
                                        )
                                    
                                except Exception as e:
                                    logging.warning(f"Failed to get potential estimation for frontier {i}: {e}")
                                    # Update with default scores if estimation fails
                                    potential_graph.update_from_frontier(
                                        frontier=frontier,
                                        subtask_metadata=subtask_metadata,
                                        occupied_map=None,
                                        potential_text=None
                                    )

                    # (4) Choose the next navigation point by querying the VLM
                    if cfg.choose_every_step:
                        # if we choose to query vlm every step, we clear the target point every step
                        if (
                            tsdf_planner.max_point is not None
                            and type(tsdf_planner.max_point) == Frontier
                        ):
                            # reset target point to allow the model to choose again
                            tsdf_planner.max_point = None
                            tsdf_planner.target_point = None

                    # use the most common id in the mapped ids as the detected target object id
                    target_obj_ids_estimate = []
                    for obj_id, det_ids in goal_obj_ids_mapping.items():
                        if len(det_ids) == 0:
                            continue
                        target_obj_ids_estimate.append(
                            max(set(det_ids), key=det_ids.count)
                        )

                    if (
                        tsdf_planner.max_point is None
                        and tsdf_planner.target_point is None
                    ):
                        # Check if we have valid choices before querying VLM
                        if len(scene.snapshots) == 0 and len(tsdf_planner.frontiers) == 0:
                            logging.warning(f"No snapshots or frontiers available for VLM query at step {cnt_step}")
                            continue
                        
                        candidate_ranked = select_scope_frontier_candidates(
                            tsdf_planner,
                            potential_graph,
                            max_candidates=getattr(cfg, "structured_bev_max_frontiers", 3),
                        )
                        candidate_frontiers = [item[2] for item in candidate_ranked]
                        semantic_bev_path = None
                        gaussian_bev_path = None
                        if getattr(cfg, "structured_bev_for_vlm", True):
                            try:
                                bev_input_dir = os.path.join(eps_potential_dir, "vlm_bev")
                                agent_voxel = tsdf_planner.habitat2voxel(pts)
                                bev_name = f"{global_step}_{subtask_id}"
                                semantic_bev_path = save_bev_visualization(
                                    tsdf_planner,
                                    bev_input_dir,
                                    f"{bev_name}_semantic",
                                    trajectory_voxels=logger.pts_voxels,
                                    objects=scene.objects,
                                    render_resolution=float(getattr(cfg, "tsdf_bev_render_resolution", 0.05)),
                                    min_object_detections=int(getattr(cfg, "tsdf_bev_min_object_detections", 2)),
                                    trajectory_arrow_stride=int(getattr(cfg, "tsdf_bev_trajectory_arrow_stride", 1)),
                                    relevant_classes=relevant_object_classes,
                                    max_labeled_instances=int(getattr(cfg, "tsdf_bev_max_labeled_instances", 10)),
                                    # Before the VLM has selected a memory node, it
                                    # needs nearby context (for example cabinet and
                                    # worktop when searching for a refrigerator).
                                    # Keep the target/relevance ranking first, then
                                    # fill unused label slots with stable instances.
                                    fill_irrelevant_instances=bool(
                                        getattr(cfg, "structured_bev_fill_context_instances", True)
                                    ),
                                    show_irrelevant_outlines=bool(getattr(cfg, "tsdf_bev_show_irrelevant_object_outlines", False)),
                                    frontier_candidates=candidate_frontiers,
                                    agent_voxel=agent_voxel,
                                    agent_yaw=angle,
                                    crop_padding_m=float(getattr(cfg, "tsdf_bev_crop_padding_m", 1.5)),
                                    min_crop_size_m=float(getattr(cfg, "tsdf_bev_min_crop_size_m", 6.0)),
                                    semantic_marker_radius_m=float(getattr(cfg, "tsdf_bev_semantic_marker_radius_m", 0.16)),
                                    semantic_max_footprint_area_m2=float(getattr(cfg, "tsdf_bev_semantic_max_footprint_area_m2", 6.0)),
                                    semantic_max_extent_m=float(getattr(cfg, "tsdf_bev_semantic_max_extent_m", 4.0)),
                                    semantic_support_radius_m=float(getattr(cfg, "tsdf_bev_semantic_support_radius_m", 0.4)),
                                )
                                gaussian_candidates = [
                                    {"position": frontier.position, "scores": scores}
                                    for _, _, frontier, scores in candidate_ranked
                                ]
                                if gaussian_candidates:
                                    gaussian_bev_path = save_frontier_gaussian_bev(
                                        tsdf_planner,
                                        bev_input_dir,
                                        f"{bev_name}_evidence",
                                        gaussian_candidates,
                                        trajectory_voxels=logger.pts_voxels,
                                        agent_voxel=agent_voxel,
                                        agent_yaw=angle,
                                        trajectory_arrow_stride=int(getattr(cfg, "tsdf_bev_trajectory_arrow_stride", 4)),
                                        crop_padding_m=float(getattr(cfg, "tsdf_bev_crop_padding_m", 1.5)),
                                        min_crop_size_m=float(getattr(cfg, "tsdf_bev_min_crop_size_m", 6.0)),
                                    )
                                    # Keep an inspection copy beside semantic BEVs.
                                    # This is the exact Gaussian image attached to the
                                    # VLM prompt, not a post-hoc reconstruction.
                                    if gaussian_bev_path:
                                        gaussian_vis_dir = os.path.join(
                                            logger.episode_dir,
                                            "visualization",
                                            "bev_gaussian",
                                        )
                                        os.makedirs(gaussian_vis_dir, exist_ok=True)
                                        shutil.copy2(
                                            gaussian_bev_path,
                                            os.path.join(
                                                gaussian_vis_dir,
                                                f"{bev_name}_gaussian_bev.png",
                                            ),
                                        )
                            except Exception as exc:
                                logging.warning("Failed to generate structured BEV VLM inputs: %s", exc)

                        logging.info(
                            "Querying VLM with %d snapshots and %d SCOPE-scored frontier candidates",
                            len(scene.snapshots), len(candidate_frontiers),
                        )
                        
                        # query the VLM for the next navigation point, and the reason for the choice
                        try:
                            vlm_response = query_vlm_for_response(
                                subtask_metadata=subtask_metadata,
                                scene=scene,
                                tsdf_planner=tsdf_planner,
                                rgb_egocentric_views=rgb_egocentric_views,
                                cfg=cfg,
                                verbose=True,
                                potential_graph=potential_graph,
                                frontier_candidates=candidate_frontiers,
                                semantic_bev_path=semantic_bev_path,
                                gaussian_bev_path=gaussian_bev_path,
                            )
                        except Exception as e:
                            logging.error(f"Exception during VLM query: {e}")
                            vlm_response = None
                        
                        if vlm_response is None:
                            logging.error(f"Subtask id {subtask_id} invalid: query_vlm_for_response failed!")
                            # Log diagnostic information
                            logging.info(f"Diagnostic info - Snapshots: {len(scene.snapshots)}, Frontiers: {len(tsdf_planner.frontiers)}")
                            logging.info(f"Scene objects: {len(scene.objects)}")
                            break

                        (
                            max_point_choice,
                            n_filtered_snapshots,
                            prefiltered_object_classes,
                            structured_decision,
                        ) = vlm_response

                        if prefiltered_object_classes:
                            relevant_object_classes = prefiltered_object_classes

                        if structured_decision is not None:
                            logging.info("Structured VLM decision: %s", json.dumps(structured_decision))

                        # set the vlm choice as the navigation target
                        update_success = tsdf_planner.set_next_navigation_point(
                            choice=max_point_choice,
                            pts=pts,
                            objects=scene.objects,
                            cfg=cfg.planner,
                            pathfinder=scene.pathfinder,
                        )
                        if not update_success:
                            logging.info(
                                f"Subtask id {subtask_id} invalid: set_next_navigation_point failed!"
                            )
                            break

                    # (5) Agent navigate to the target point for one step
                    return_values = tsdf_planner.agent_step(
                        pts=pts,
                        angle=angle,
                        objects=scene.objects,
                        snapshots=scene.snapshots,
                        pathfinder=scene.pathfinder,
                        cfg=cfg.planner,
                        path_points=None,
                        save_visualization=cfg.save_visualization,
                    )
                    if return_values[0] is None:
                        logging.info(
                            f"Subtask id {subtask_id} invalid: agent_step failed!"
                        )
                        break

                    # update agent's position and rotation
                    pts, angle, pts_voxel, fig, _, target_arrived = return_values
                    logger.log_step(pts_voxel=pts_voxel)
                    logging.info(
                        f"Current position: {pts}, {logger.subtask_explore_dist:.3f}"
                    )

                    # Mark current position as visited in potential graph
                    potential_graph.mark_visited(pts, radius=1.5)

                    # sanity check about objects, scene graph, snapshots, ...
                    scene.sanity_check(cfg=cfg)

                    if cfg.save_visualization:
                        # save the top-down visualization
                        logger.save_topdown_visualization(
                            global_step=global_step,
                            subtask_id=subtask_id,
                            subtask_metadata=subtask_metadata,
                            goal_obj_ids_mapping=goal_obj_ids_mapping,
                            fig=fig,
                        )
                        try:
                            bev_path = save_bev_visualization(
                                tsdf_planner,
                                os.path.join(
                                    logger.episode_dir,
                                    "visualization",
                                    "bev_semantic",
                                ),
                                f"{global_step}_{subtask_id}",
                                trajectory_voxels=logger.pts_voxels,
                                objects=scene.objects,
                                render_resolution=float(
                                    getattr(cfg, "tsdf_bev_render_resolution", 0.025)
                                ),
                                min_object_detections=int(
                                    getattr(cfg, "tsdf_bev_min_object_detections", 2)
                                ),
                                trajectory_arrow_stride=int(
                                    getattr(cfg, "tsdf_bev_trajectory_arrow_stride", 1)
                                ),
                                relevant_classes=relevant_object_classes,
                                max_labeled_instances=int(
                                    getattr(cfg, "tsdf_bev_max_labeled_instances", 10)
                                ),
                                # Match the decision BEV: when prefilter has no
                                # matching class, fill slots with stable context
                                # so object names never disappear from inspection.
                                fill_irrelevant_instances=bool(
                                    getattr(cfg, "structured_bev_fill_context_instances", True)
                                ),
                                show_irrelevant_outlines=bool(
                                    getattr(cfg, "tsdf_bev_show_irrelevant_object_outlines", False)
                                ),
                                frontier_candidates=candidate_frontiers,
                                agent_voxel=pts_voxel,
                                agent_yaw=angle,
                                crop_padding_m=float(getattr(cfg, "tsdf_bev_crop_padding_m", 1.5)),
                                min_crop_size_m=float(getattr(cfg, "tsdf_bev_min_crop_size_m", 6.0)),
                                semantic_marker_radius_m=float(getattr(cfg, "tsdf_bev_semantic_marker_radius_m", 0.16)),
                                semantic_max_footprint_area_m2=float(getattr(cfg, "tsdf_bev_semantic_max_footprint_area_m2", 6.0)),
                                semantic_max_extent_m=float(getattr(cfg, "tsdf_bev_semantic_max_extent_m", 4.0)),
                                semantic_support_radius_m=float(getattr(cfg, "tsdf_bev_semantic_support_radius_m", 0.4)),
                            )
                            logging.info(f"Saved semantic BEV: {bev_path}")
                        except Exception as exc:
                            logging.warning(f"Failed to save semantic BEV: {exc}")
                        # save the visualization of vlm's choice at each step
                        logger.save_frontier_visualization(
                            global_step=global_step,
                            subtask_id=subtask_id,
                            tsdf_planner=tsdf_planner,
                            max_point_choice=max_point_choice,
                            global_caption=f"{subtask_metadata['question']}\n{subtask_metadata['task_type']}\n{subtask_metadata['class']}",
                        )

                        # Save potential graph visualization
                        potential_viz_path = os.path.join(
                            eps_potential_dir, 
                            f"potential_{global_step}_{subtask_id}.png"
                        )
                        potential_graph.visualize(
                            save_path=potential_viz_path,
                            title=f"Step {cnt_step} - {subtask_metadata['question'][:50]}..."
                        )
                        
                        # Log potential graph statistics
                        stats = potential_graph.get_statistics()
                        logging.info(f"Potential graph stats: {stats}")

                    # (6) Check if the agent has arrived at the target to finish the question
                    if type(max_point_choice) == SnapShot and target_arrived:
                        # when the target is a snapshot, and the agent arrives at the target
                        # we consider the subtask is finished, take an observation and save the chosen target snapshot
                        obs, _ = scene.get_observation(pts, angle=angle)
                        rgb = obs["color_sensor"]
                        plt.imsave(
                            os.path.join(
                                logger.subtask_object_observe_dir, f"target.png"
                            ),
                            rgb,
                        )

                        snapshot_filename = max_point_choice.image.split(".")[0]
                        os.system(
                            f"cp {os.path.join(eps_snapshot_dir, max_point_choice.image)} {os.path.join(logger.subtask_object_observe_dir, f'snapshot_{snapshot_filename}.png')}"
                        )

                        task_success = True
                        break

                # Save final potential graph state for this subtask
                if cfg.save_visualization:
                    final_potential_path = os.path.join(
                        eps_potential_dir,
                        f"final_potential_{subtask_id}.png"
                    )
                    potential_graph.visualize(
                        save_path=final_potential_path,
                        title=f"Final - {subtask_metadata['question']}"
                    )
                    
                    # Save potential graph state
                    graph_state_path = os.path.join(
                        eps_potential_dir,
                        f"potential_state_{subtask_id}.pkl"
                    )
                    potential_graph.save_state(graph_state_path)

                # get some statistics
                if task_success and np.any(
                    [
                        obj_id in max_point_choice.cluster
                        for obj_id in target_obj_ids_estimate
                    ]
                ):
                    success_by_snapshot = True
                    logging.info(
                        f"Success: {target_obj_ids_estimate} in chosen snapshot {max_point_choice.image}!"
                    )
                else:
                    success_by_snapshot = False
                    logging.info(
                        f"Fail: {target_obj_ids_estimate} not in chosen snapshot!"
                    )
                # calculate the distance to the nearest view point
                agent_subtask_distance = calc_agent_subtask_distance(
                    pts, subtask_metadata["viewpoints"], scene.pathfinder
                )
                if agent_subtask_distance < cfg.success_distance:
                    success_by_distance = True
                    logging.info(
                        f"Success: agent reached the target viewpoint at distance {agent_subtask_distance}!"
                    )
                else:
                    success_by_distance = False
                    logging.info(
                        f"Fail: agent failed to reach the target viewpoint at distance {agent_subtask_distance}!"
                    )

                logger.log_subtask_result(
                    success_by_snapshot=success_by_snapshot,
                    success_by_distance=success_by_distance,
                    subtask_id=subtask_id,
                    gt_subtask_explore_dist=subtask_metadata["gt_subtask_explore_dist"],
                    goal_type=goal_type,
                    n_filtered_snapshots=n_filtered_snapshots,
                    n_total_snapshots=len(scene.snapshots),
                    n_total_frames=len(scene.frames),
                )

                logging.info(f"Scene graph of question {subtask_id}:")
                logging.info(f"Question: {subtask_metadata['question']}")
                logging.info(f"Task type: {subtask_metadata['task_type']}")
                logging.info(f"Answer: {subtask_metadata['class']}")
                scene.print_scene_graph()

                if not cfg.save_visualization:
                    # clear up the stored images to save memory
                    os.system(
                        f"rm -r {os.path.join(str(cfg.output_dir), f'{subtask_id}')}"
                    )

            # save the results at the end of each episode
            logger.save_results()

            logging.info(f"Episode {episode_id} finish")
            if not cfg.save_visualization:
                os.system(f"rm -r {episode_dir}")

    logger.save_results()
    # aggregate the results from different splits into a single file
    logger.aggregate_results()
    log_vlm_timing_summary()

    logging.info(f"All scenes finish")


if __name__ == "__main__":
    # Get config path
    parser = argparse.ArgumentParser()
    parser.add_argument("-cf", "--cfg_file", help="cfg file path", default="", type=str)
    parser.add_argument("--start_ratio", help="start ratio", default=0.0, type=float)
    parser.add_argument("--end_ratio", help="end ratio", default=1.0, type=float)
    parser.add_argument("--split", help="which episode", default=1, type=int)
    parser.add_argument("--scene_name", help="run exactly one HM3D scene", default="", type=str)
    args = parser.parse_args()
    cfg = OmegaConf.load(args.cfg_file)
    OmegaConf.resolve(cfg)
    # Set up logging
    cfg.output_dir = os.path.join(cfg.output_parent_dir, cfg.exp_name)
    if not os.path.exists(cfg.output_dir):
        os.makedirs(cfg.output_dir, exist_ok=True)
    logging_path = os.path.join(
        str(cfg.output_dir),
        f"log_{args.start_ratio:.2f}_{args.end_ratio:.2f}_{args.split}.log",
    )

    os.system(f"cp {args.cfg_file} {cfg.output_dir}")

    class ElapsedTimeFormatter(logging.Formatter):
        def __init__(self, fmt=None, datefmt=None):
            super().__init__(fmt, datefmt)
            self.start_time = time.time()

        def formatTime(self, record, datefmt=None):
            elapsed_seconds = record.created - self.start_time
            hours, remainder = divmod(elapsed_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

    # Set up the logging format
    formatter = ElapsedTimeFormatter(fmt="%(asctime)s - %(message)s")

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        handlers=[
            logging.FileHandler(logging_path, mode="a"),
            logging.StreamHandler(),
        ],
    )

    # Set the custom formatter
    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)

    # run
    logging.info(f"***** Running {cfg.exp_name} *****")
    main(
        cfg,
        start_ratio=args.start_ratio,
        end_ratio=args.end_ratio,
        split=args.split,
        scene_name_filter=args.scene_name or None,
    )
