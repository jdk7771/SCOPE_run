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
import time
import json
import logging
import matplotlib.pyplot as plt
import habitat_sim

import open_clip
from ultralytics import SAM, YOLOWorld

from src.habitat import pose_habitat_to_tsdf
from src.geom import get_cam_intr, get_scene_bnds
from src.tsdf_planner import TSDFPlanner, Frontier, SnapShot
from src.tsdf_export import save_bev_visualization
from src.scene_aeqa import Scene
from src.utils import resize_image, get_pts_angle_aeqa
from src.query_vlm_express import (
    query_vlm_for_response,
    answer_express_question,
    judge_express_answer,
)
from src.logger_aeqa import Logger
from src.const import *


def _append_express_record(output_dir, record):
    """Persist one completed benchmark item so an interrupted full run resumes."""
    with open(os.path.join(output_dir, "express_records.jsonl"), "a") as f:
        f.write(json.dumps(record) + "\n")


def _write_express_metrics(output_dir):
    """Compute EXPRESS-style aggregates using the recorded local VLM judge."""
    records = {}
    record_path = os.path.join(output_dir, "express_records.jsonl")
    if not os.path.exists(record_path):
        return
    with open(record_path) as f:
        for line in f:
            if line.strip():
                record = json.loads(line)
                records[record["question_id"]] = record
    values = list(records.values())
    scored = [r for r in values if r.get("judge_score") is not None]
    if not scored:
        return
    credit = np.asarray(
        [r["judge_score"] * r["judge_correct"] / 5.0 for r in scored], dtype=float
    )
    c_avg = 100.0 * float(np.mean(credit))
    c_star_avg = 100.0 * float(np.mean([r["judge_correct"] for r in scored]))
    path_credit = []
    for r in scored:
        path_len, shortest = r.get("path_length"), r.get("geodesic_distance")
        if path_len is not None and shortest is not None and path_len > 0:
            path_credit.append(
                (r["judge_score"] * r["judge_correct"] / 5.0)
                * shortest / max(path_len, shortest)
            )
    goal_distances = [r["goal_distance"] for r in values if r.get("goal_distance") is not None]
    metrics = {
        "n_completed": len(values),
        "n_judged": len(scored),
        "C_avg_local_gemma_judge": c_avg,
        "C_star_avg_local_gemma_judge": c_star_avg,
        "E_path_local_gemma_judge": 100.0 * float(np.mean(path_credit)) if path_credit else None,
        "d_T_avg": float(np.mean(goal_distances)) if goal_distances else None,
        "note": "C/C*/E_path use the local Gemma judge for a fair paired comparison; this is not the official GPT-4o-mini judge.",
    }
    with open(os.path.join(output_dir, "express_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    logging.info("EXPRESS metrics: %s", metrics)


def main(cfg, start_ratio=0.0, end_ratio=1.0):
    # load the default concept graph config
    cfg_cg = OmegaConf.load(cfg.concept_graph_config_path)
    OmegaConf.resolve(cfg_cg)

    img_height = cfg.img_height
    img_width = cfg.img_width
    cam_intr = get_cam_intr(cfg.hfov, img_height, img_width)

    random.seed(cfg.seed)
    np.random.seed(cfg.seed)

    # Load dataset
    questions_data = json.load(open(cfg.questions_list_path, "r"))
    total_questions = len(questions_data)
    questions_list = list(enumerate(questions_data))
    logging.info(f"Total number of questions: {total_questions}")
    # only process a subset of the questions
    questions_list = questions_list[
        int(start_ratio * total_questions) : int(end_ratio * total_questions)
    ]
    logging.info(f"number of questions after splitting: {len(questions_list)}")
    logging.info(f"question path: {cfg.questions_list_path}")

    # load detection and segmentation models
    detection_model = YOLOWorld(cfg.yolo_model_name)
    logging.info(f"Load YOLO model {cfg.yolo_model_name} successful!")

    sam_predictor = SAM(cfg.sam_model_name)  # UltraLytics SAM
    logging.info(f"Load SAM model {cfg.sam_model_name} successful!")

    clip_model, _, clip_preprocess = open_clip.create_model_and_transforms(
        "ViT-B-32", "laion2b_s34b_b79k"  # "ViT-H-14", "laion2b_s32b_b79k"
    )
    clip_tokenizer = open_clip.get_tokenizer("ViT-B-32")
    logging.info(f"Load CLIP model successful!")

    # Initialize the logger
    logger = Logger(
        cfg.output_dir,
        start_ratio,
        end_ratio,
        len(questions_list),
        voxel_size=cfg.tsdf_grid_size,
    )

    # Run all questions
    for question_idx, question_data in questions_list:
        question_id = f"express_{question_idx:04d}"
        scene_id = os.path.basename(question_data["scene_id"])
        if question_id in logger.success_list or question_id in logger.fail_list:
            logging.info(f"Question {question_id} already processed")
            continue
        if any([invalid_scene_id in scene_id for invalid_scene_id in INVALID_SCENE_ID]):
            logging.info(f"Skip invalid scene {scene_id}")
            continue
        logging.info(f"\n========\nIndex: {question_idx} Scene: {scene_id}")

        question = question_data["question"]
        answer = question_data["answer"]
        pts, angle = get_pts_angle_aeqa(
            question_data["start_position"], question_data["start_rotation"]
        )

        # load scene
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
        tsdf_planner = TSDFPlanner(
            vol_bnds=get_scene_bnds(scene.pathfinder, floor_height=pts[1])[0],
            voxel_size=cfg.tsdf_grid_size,
            floor_height=pts[1],
            floor_height_offset=0,
            pts_init=pts,
            init_clearance=cfg.init_clearance * 2,
            save_visualization=cfg.save_visualization,
        )

        episode_dir, eps_chosen_snapshot_dir, eps_frontier_dir, eps_snapshot_dir = (
            logger.init_episode(
                question_id=question_id,
                init_pts_voxel=tsdf_planner.habitat2voxel(pts)[:2],
            )
        )

        logging.info(f"\n\nQuestion id {question_id} initialization successful!")

        # run steps
        task_success = False
        cnt_step = -1

        gpt_answer = None
        n_filtered_snapshots = 0
        rgb_egocentric_views = []
        while cnt_step < cfg.num_step - 1:
            cnt_step += 1
            logging.info(f"\n== step: {cnt_step}")

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
            )  # Record all the objects that are newly added in this step
            for view_idx, ang in enumerate(all_angles):
                # For each view
                obs, cam_pose = scene.get_observation(pts, ang)
                rgb = obs["color_sensor"]
                depth = obs["depth_sensor"]

                obs_file_name = f"{cnt_step}-view_{view_idx}.png"
                with torch.no_grad():
                    # Concept graph pipeline update
                    annotated_rgb, added_obj_ids, _ = scene.update_scene_graph(
                        image_rgb=rgb[..., :3],
                        depth=depth,
                        intrinsics=cam_intr,
                        cam_pos=cam_pose,
                        pts=pts,
                        pts_voxel=tsdf_planner.habitat2voxel(pts),
                        img_path=obs_file_name,
                        frame_idx=cnt_step * total_views + view_idx,
                        target_obj_mask=None,
                    )
                    resized_rgb = resize_image(rgb, cfg.prompt_h, cfg.prompt_w)
                    scene.all_observations[obs_file_name] = resized_rgb
                    rgb_egocentric_views.append(resized_rgb)
                    if cfg.save_visualization:
                        plt.imsave(
                            os.path.join(eps_snapshot_dir, obs_file_name), annotated_rgb
                        )
                    else:
                        plt.imsave(os.path.join(eps_snapshot_dir, obs_file_name), rgb)
                    all_added_obj_ids += added_obj_ids

                # Clean up or merge redundant objects periodically
                scene.periodic_cleanup_objects(
                    frame_idx=cnt_step * total_views + view_idx, pts=pts
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

            # (2) Update Memory Snapshots with hierarchical clustering
            # Choose all the newly added objects as well as the objects nearby as the cluster targets
            all_added_obj_ids = [
                obj_id for obj_id in all_added_obj_ids if obj_id in scene.objects
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
                if cnt_step == 0:  # if the first step fails, we should stop
                    logging.info(
                        f"Question id {question_id} invalid: update_frontier_map failed!"
                    )
                    break

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

            if tsdf_planner.max_point is None and tsdf_planner.target_point is None:
                if len(scene.snapshots) == 0 and len(tsdf_planner.frontiers) == 0:
                    logging.info(
                        f"Question id {question_id} invalid: no snapshots or frontiers available!"
                    )
                    break
                # This branch's deduplicated, TSDF-supported and display-smoothed
                # semantic BEV is VLM context only; SCOPE's choices and navigation
                # remain identical to the baseline runner.
                semantic_bev_path = None
                if getattr(cfg, "semantic_bev_for_vlm", False):
                    try:
                        semantic_bev_path = save_bev_visualization(
                            tsdf_planner,
                            os.path.join(episode_dir, "vlm_bev"),
                            f"step_{cnt_step}_semantic",
                            trajectory_voxels=logger.pts_voxels,
                            objects=scene.objects,
                            render_resolution=float(getattr(cfg, "tsdf_bev_render_resolution", 0.05)),
                            min_object_detections=int(getattr(cfg, "tsdf_bev_min_object_detections", 2)),
                            trajectory_arrow_stride=int(getattr(cfg, "tsdf_bev_trajectory_arrow_stride", 1)),
                            max_labeled_instances=int(getattr(cfg, "tsdf_bev_max_labeled_instances", 10)),
                            fill_irrelevant_instances=bool(getattr(cfg, "tsdf_bev_fill_context_instances", True)),
                            show_irrelevant_outlines=bool(getattr(cfg, "tsdf_bev_show_irrelevant_object_outlines", False)),
                            frontier_candidates=list(tsdf_planner.frontiers),
                            agent_voxel=tsdf_planner.habitat2voxel(pts),
                            agent_yaw=angle,
                            crop_padding_m=float(getattr(cfg, "tsdf_bev_crop_padding_m", 1.5)),
                            min_crop_size_m=float(getattr(cfg, "tsdf_bev_min_crop_size_m", 6.0)),
                            semantic_max_footprint_area_m2=float(getattr(cfg, "tsdf_bev_semantic_max_footprint_area_m2", 6.0)),
                            semantic_max_extent_m=float(getattr(cfg, "tsdf_bev_semantic_max_extent_m", 4.0)),
                            semantic_support_radius_m=float(getattr(cfg, "tsdf_bev_semantic_support_radius_m", 0.4)),
                            semantic_shape_dilation_m=float(getattr(cfg, "tsdf_bev_semantic_shape_dilation_m", 0.10)),
                            semantic_same_class_merge_radius_m=float(getattr(cfg, "tsdf_bev_semantic_same_class_merge_radius_m", 0.55)),
                            semantic_display_smoothing_m=float(getattr(cfg, "tsdf_bev_semantic_display_smoothing_m", 0.05)),
                        )
                    except Exception as exc:
                        logging.warning("Failed to generate semantic BEV for EXPRESS: %s", exc)
                # query the VLM for the next navigation point, and the reason for the choice
                vlm_response = query_vlm_for_response(
                    question=question,
                    scene=scene,
                    tsdf_planner=tsdf_planner,
                    rgb_egocentric_views=rgb_egocentric_views,
                    cfg=cfg,
                    semantic_bev_path=semantic_bev_path,
                    verbose=True,
                )
                if vlm_response is None:
                    logging.info(
                        f"Question id {question_id} invalid: query_vlm_for_response failed!"
                    )
                    break

                max_point_choice, gpt_answer, n_filtered_snapshots = vlm_response

                # set the vlm choice as the navigation target
                update_success = tsdf_planner.set_next_navigation_point(
                    choice=max_point_choice,
                    pts=pts,
                    objects=scene.objects,
                    cfg=cfg.planner,
                    pathfinder=scene.pathfinder,
                    random_position=False,
                )
                if not update_success:
                    logging.info(
                        f"Question id {question_id} invalid: set_next_navigation_point failed!"
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
                logging.info(f"Question id {question_id} invalid: agent_step failed!")
                break

            # update agent's position and rotation
            pts, angle, pts_voxel, fig, _, target_arrived = return_values
            logger.log_step(pts_voxel=pts_voxel)
            logging.info(f"Current position: {pts}, {logger.explore_dist:.3f}")

            # sanity check about objects, scene graph, snapshots, ...
            scene.sanity_check(cfg=cfg)

            if cfg.save_visualization:
                # save the top-down visualization
                logger.save_topdown_visualization(
                    cnt_step=cnt_step,
                    fig=fig,
                )
                # save the visualization of vlm's choice at each step
                logger.save_frontier_visualization(
                    cnt_step=cnt_step,
                    tsdf_planner=tsdf_planner,
                    max_point_choice=max_point_choice,
                    global_caption=f"{question}\n{answer}",
                )

            # (6) Check if the agent has arrived at the target to finish the question
            if type(max_point_choice) == SnapShot and target_arrived:
                # when the target is a snapshot, and the agent arrives at the target
                # we consider the question is finished and save the chosen target snapshot
                snapshot_filename = max_point_choice.image.split(".")[0]
                shutil.copy2(
                    os.path.join(eps_snapshot_dir, max_point_choice.image),
                    os.path.join(
                        eps_chosen_snapshot_dir,
                        f"snapshot_{snapshot_filename}.png",
                    ),
                )

                task_success = True
                logging.info(
                    f"Question id {question_id} finished after arriving at target!"
                )
                break

        if not gpt_answer:
            # EXPRESS expects an answer for every item.  When SCOPE reaches its
            # step budget before selecting a snapshot, answer from the latest
            # SCOPE observation instead of using benchmark ground truth.
            last_view = rgb_egocentric_views[-1] if rgb_egocentric_views else None
            gpt_answer = answer_express_question(question, last_view)

        judge_score, judge_correct, judge_raw = judge_express_answer(
            question, answer, gpt_answer
        )
        goal_distance = None
        try:
            path = habitat_sim.ShortestPath()
            path.requested_start = np.asarray(pts)
            path.requested_end = np.asarray(question_data["goal_position"])
            if scene.pathfinder.find_path(path):
                goal_distance = float(path.geodesic_distance)
        except Exception as exc:
            logging.warning("Could not compute EXPRESS goal distance: %s", exc)

        logger.log_episode_result(
            success=task_success,
            question_id=question_id,
            explore_dist=logger.explore_dist,
            gpt_answer=gpt_answer,
            n_filtered_snapshots=n_filtered_snapshots,
            n_total_snapshots=len(scene.snapshots),
            n_total_frames=len(scene.frames),
        )

        logging.info(f"Scene graph of question {question_id}:")
        logging.info(f"Question: {question}")
        logging.info(f"Answer: {answer}")
        logging.info(f"Prediction: {gpt_answer}")
        scene.print_scene_graph()

        # update the saved results after each episode
        logger.save_results()

        _append_express_record(
            cfg.output_dir,
            {
                "question_id": question_id,
                "question_index": question_idx,
                "episode_id": question_data["episode_id"],
                "trajectory_id": question_data["trajectory_id"],
                "scene_id": scene_id,
                "type": question_data["type"],
                "question": question,
                "reference_answer": answer,
                "prediction": gpt_answer,
                "agent_answered": task_success,
                "judge_score": judge_score,
                "judge_correct": judge_correct,
                "judge_raw": judge_raw,
                "path_length": logger.path_length_list.get(question_id),
                "geodesic_distance": float(question_data["geodesic_distance"]),
                "goal_distance": goal_distance,
                "steps": cnt_step + 1,
            },
        )
        _write_express_metrics(cfg.output_dir)

        if not cfg.save_visualization:
            # clear up the stored images to save memory
            shutil.rmtree(episode_dir)

    logger.save_results()
    # aggregate the results from different splits into a single file
    logger.aggregate_results()
    _write_express_metrics(cfg.output_dir)

    logging.info(f"All scenes finish")


if __name__ == "__main__":
    # Get config path
    parser = argparse.ArgumentParser()
    parser.add_argument("-cf", "--cfg_file", help="cfg file path", default="", type=str)
    parser.add_argument("--start_ratio", help="start ratio", default=0.0, type=float)
    parser.add_argument("--end_ratio", help="end ratio", default=1.0, type=float)
    args = parser.parse_args()
    cfg = OmegaConf.load(args.cfg_file)
    OmegaConf.resolve(cfg)

    # Set up logging
    cfg.output_dir = os.path.join(cfg.output_parent_dir, cfg.exp_name)
    if not os.path.exists(cfg.output_dir):
        os.makedirs(cfg.output_dir, exist_ok=True)  # recursive
    logging_path = os.path.join(
        str(cfg.output_dir), f"log_{args.start_ratio:.2f}_{args.end_ratio:.2f}.log"
    )

    shutil.copy2(args.cfg_file, cfg.output_dir)

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
            logging.FileHandler(logging_path, mode="w"),
            logging.StreamHandler(),
        ],
    )

    # Set the custom formatter
    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)

    # run
    logging.info(f"***** Running {cfg.exp_name} *****")
    main(cfg, args.start_ratio, args.end_ratio)
