#!/usr/bin/env python3
"""Build and persist a SCOPE TSDF map for one HM3D scene.

This utility deliberately bypasses VLM selection and scene-graph models.  It
uses SCOPE's Habitat camera configuration and TSDF integration path to create
an inspectable map from a deterministic navmesh tour.
"""

import argparse
import json
import logging
from pathlib import Path

import habitat_sim
import matplotlib.pyplot as plt
import numpy as np
import quaternion

from src.geom import get_cam_intr, get_scene_bnds
from src.habitat import get_quaternion, make_simple_cfg, pose_habitat_to_tsdf
from src.tsdf_planner import TSDFPlanner


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-id", default="00807-rsggHU7g7dh")
    parser.add_argument("--scene-root", default="/mnt/data/hm3d/val")
    parser.add_argument(
        "--scene-dataset-config",
        default="data/hm3d_annotated_basis.scene_dataset_config.json",
    )
    parser.add_argument("--output-dir", default="results/voxel_maps")
    parser.add_argument("--voxel-size", type=float, default=0.1)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--hfov", type=float, default=120.0)
    parser.add_argument("--camera-height", type=float, default=1.5)
    parser.add_argument("--camera-tilt-deg", type=float, default=-30.0)
    parser.add_argument("--targets", type=int, default=7)
    parser.add_argument("--sample-spacing", type=float, default=1.25)
    parser.add_argument("--seed", type=int, default=3407)
    return parser.parse_args()


def scene_paths(scene_root, scene_id):
    scene_name = scene_id.split("-", 1)[1]
    root = Path(scene_root) / scene_id
    return root / f"{scene_name}.basis.glb", root / f"{scene_name}.basis.navmesh"


def sensor_pose(agent):
    sensor_state = agent.get_state().sensor_states["depth_sensor"]
    pose = np.eye(4)
    pose[:3, :3] = quaternion.as_rotation_matrix(sensor_state.rotation)
    pose[:3, 3] = sensor_state.position
    return pose


def sample_tour(pathfinder, start, targets, seed):
    """Create a same-floor tour that covers separated parts of the navmesh."""
    rng = np.random.default_rng(seed)
    current = np.asarray(start, dtype=np.float32)
    visited = [current]
    route = [current]

    for _ in range(targets):
        candidates = []
        for _ in range(160):
            candidate = pathfinder.get_random_navigable_point()
            if abs(candidate[1] - current[1]) > 0.4:
                continue
            shortest_path = habitat_sim.ShortestPath()
            shortest_path.requested_start = current
            shortest_path.requested_end = candidate
            if not pathfinder.find_path(shortest_path):
                continue
            if not 8.0 <= shortest_path.geodesic_distance <= 35.0:
                continue
            coverage = min(np.linalg.norm(candidate - point) for point in visited)
            candidates.append((coverage, shortest_path.geodesic_distance, candidate, shortest_path.points))

        if not candidates:
            break
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        best_coverage = candidates[0][0]
        tied = [item for item in candidates if item[0] >= best_coverage * 0.95]
        _, _, current, path_points = tied[int(rng.integers(len(tied)))]
        route.extend(np.asarray(path_points[1:], dtype=np.float32))
        visited.append(current)

    return route


def subsample_route(route, spacing):
    sampled = [route[0]]
    last = route[0]
    for point in route[1:]:
        if np.linalg.norm(point - last) >= spacing:
            sampled.append(point)
            last = point
    if not np.allclose(sampled[-1], route[-1]):
        sampled.append(route[-1])
    return sampled


def save_bev(planner, route, output_path):
    height_index = int(planner.occupancy_height / planner._voxel_size) + planner.min_height_voxel
    free = np.logical_and(
        planner._tsdf_vol_cpu[:, :, height_index] > 0,
        planner._tsdf_vol_cpu[:, :, 0] < 0,
    )
    explored = np.any(planner._explore_vol_cpu > 0, axis=2)
    observed = np.any(planner._weight_vol_cpu > 0, axis=2)

    bev = np.full((*free.shape, 3), 245, dtype=np.uint8)
    bev[observed] = (104, 104, 104)
    bev[explored] = (193, 223, 230)
    bev[free] = (79, 171, 118)

    route_normal = np.asarray([planner.habitat2voxel(point)[:2] for point in route])
    route_normal = np.clip(route_normal, 0, np.asarray(free.shape) - 1)
    bev[route_normal[:, 0], route_normal[:, 1]] = (220, 56, 56)

    plt.imsave(output_path, np.transpose(bev, (1, 0, 2)), origin="lower")
    return int(free.sum()), int(explored.sum()), int(observed.sum())


def main():
    args = parse_args()
    np.random.seed(args.seed)
    scene_mesh, navmesh = scene_paths(args.scene_root, args.scene_id)
    if not scene_mesh.exists() or not navmesh.exists():
        raise FileNotFoundError(f"Missing scene assets: {scene_mesh} / {navmesh}")

    output_dir = Path(args.output_dir) / args.scene_id
    output_dir.mkdir(parents=True, exist_ok=True)

    settings = {
        "scene": str(scene_mesh),
        "default_agent": 0,
        "sensor_height": args.camera_height,
        "width": args.image_size,
        "height": args.image_size,
        "hfov": args.hfov,
        "scene_dataset_config_file": args.scene_dataset_config,
        "camera_tilt": np.deg2rad(args.camera_tilt_deg),
    }
    simulator = habitat_sim.Simulator(make_simple_cfg(settings))
    try:
        pathfinder = simulator.pathfinder
        pathfinder.seed(args.seed)
        if not pathfinder.load_nav_mesh(str(navmesh)):
            raise RuntimeError(f"Could not load navmesh: {navmesh}")

        start = pathfinder.get_random_navigable_point()
        floor_height = float(start[1])
        tsdf_bounds, scene_area = get_scene_bnds(pathfinder, floor_height)
        planner = TSDFPlanner(
            vol_bnds=tsdf_bounds,
            voxel_size=args.voxel_size,
            floor_height=floor_height,
            pts_init=start,
            init_clearance=0.6,
            occupancy_height=0.4,
            vision_height=1.2,
            save_visualization=True,
        )
        route = subsample_route(sample_tour(pathfinder, start, args.targets, args.seed), args.sample_spacing)
        agent = simulator.initialize_agent(0)
        intrinsics = get_cam_intr(args.hfov, args.image_size, args.image_size)
        view_angles = np.linspace(0, 2 * np.pi, num=4, endpoint=False)

        for position_index, position in enumerate(route):
            for angle in view_angles:
                state = habitat_sim.AgentState()
                state.position = position
                state.rotation = get_quaternion(float(angle), 0)
                agent.set_state(state)
                observations = simulator.get_sensor_observations()
                planner.integrate(
                    color_im=observations["color_sensor"],
                    depth_im=observations["depth_sensor"],
                    cam_intr=intrinsics,
                    cam_pose=pose_habitat_to_tsdf(sensor_pose(agent)),
                    obs_weight=1.0,
                    margin_h=0,
                    margin_w=0,
                    explored_depth=1.7,
                )
            if (position_index + 1) % 10 == 0 or position_index + 1 == len(route):
                logging.info("Integrated %d/%d route positions", position_index + 1, len(route))

        full_volume_path = output_dir / "scope_tsdf_volume.npz"
        np.savez_compressed(
            full_volume_path,
            tsdf=planner._tsdf_vol_cpu,
            weights=planner._weight_vol_cpu,
            explored=planner._explore_vol_cpu,
            obstacle=planner._obstacle_vol_cpu,
            volume_bounds=planner._vol_bnds,
            volume_origin=planner._vol_origin,
            voxel_size=np.asarray(args.voxel_size),
            floor_height=np.asarray(floor_height),
            route_habitat=np.asarray(route),
        )
        free_cells, explored_cells, observed_cells = save_bev(planner, route, output_dir / "scope_bev.png")
        metadata = {
            "scene_id": args.scene_id,
            "scene_area_m2": float(scene_area),
            "tsdf_bounds": planner._vol_bnds.tolist(),
            "volume_shape": list(planner._vol_dim),
            "voxel_size_m": args.voxel_size,
            "route_positions": len(route),
            "camera_views": len(route) * len(view_angles),
            "free_bev_cells": free_cells,
            "explored_bev_cells": explored_cells,
            "observed_bev_cells": observed_cells,
        }
        (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(json.dumps(metadata, indent=2))
        print(f"Saved full TSDF volume to {full_volume_path}")
        print(f"Saved BEV image to {output_dir / 'scope_bev.png'}")
    finally:
        simulator.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
