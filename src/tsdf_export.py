"""Persistence helpers for inspecting SCOPE's live TSDF planner state."""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Polygon
import numpy as np
from scipy import ndimage


def _object_footprint_voxels(planner, obj):
    """Return a stable XY footprint for a ConceptGraph oriented 3D box."""
    try:
        corners = np.asarray(obj["bbox"].get_box_points())
        if corners.ndim != 2 or corners.shape[1] != 3:
            return None
        points = np.asarray([planner.habitat2voxel(point)[:2] for point in corners])
    except Exception:
        return None

    points = np.unique(points, axis=0)
    if len(points) < 3:
        return None
    center = points.mean(axis=0)
    angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
    return points[np.argsort(angles)]


def _draw_object_instances(ax, planner, objects, scale, min_detections):
    """Draw detected 3D object footprints and labels on the high-resolution BEV."""
    if not objects:
        return 0

    cmap = plt.colormaps.get_cmap("tab20")
    count = 0
    for obj_id, obj in objects.items():
        if int(obj.get("num_detections", 0)) < min_detections:
            continue
        footprint = _object_footprint_voxels(planner, obj)
        if footprint is None:
            continue

        color = cmap(int(obj_id) % cmap.N)
        # Matplotlib image axes are (x=voxel-y, y=voxel-x), matching SCOPE's
        # planner visualization convention.
        polygon_xy = np.column_stack((footprint[:, 1] * scale, footprint[:, 0] * scale))
        ax.add_patch(
            Polygon(
                polygon_xy,
                closed=True,
                facecolor=color,
                edgecolor="black",
                linewidth=1.2,
                alpha=0.58,
                zorder=5,
            )
        )
        center = polygon_xy.mean(axis=0)
        class_name = str(obj.get("class_name", "object"))
        ax.text(
            center[0],
            center[1],
            f"{obj_id}: {class_name}",
            ha="center",
            va="center",
            fontsize=7,
            color="black",
            bbox={"boxstyle": "round,pad=0.18", "fc": "white", "ec": "none", "alpha": 0.82},
            zorder=6,
        )
        count += 1
    return count


def _draw_trajectory(ax, trajectory_voxels, scale, arrow_stride):
    """Draw the executed subtask trajectory as an orange path with direction arrows."""
    if trajectory_voxels is None or len(trajectory_voxels) < 2:
        return

    trajectory = np.asarray(trajectory_voxels, dtype=float)
    xy = np.column_stack((trajectory[:, 1] * scale, trajectory[:, 0] * scale))
    ax.plot(xy[:, 0], xy[:, 1], color="#ff8c00", linewidth=2.0, zorder=8)
    ax.scatter(xy[0, 0], xy[0, 1], color="#1f77b4", edgecolors="white", s=42, zorder=10)
    ax.text(xy[0, 0], xy[0, 1], " START", color="#1f77b4", fontsize=7, va="bottom", zorder=10)

    stride = max(1, int(arrow_stride))
    for start, end in zip(xy[:-1:stride], xy[1::stride]):
        if np.linalg.norm(end - start) < 1e-6:
            continue
        ax.add_patch(
            FancyArrowPatch(
                posA=tuple(start),
                posB=tuple(end),
                arrowstyle="-|>",
                mutation_scale=10,
                linewidth=1.5,
                color="#ff8c00",
                zorder=9,
            )
        )
    ax.scatter(xy[-1, 0], xy[-1, 1], color="#e31a1c", edgecolors="white", s=52, zorder=10)


def save_bev_visualization(
    planner,
    output_dir,
    name,
    trajectory_voxels=None,
    objects=None,
    render_resolution=0.025,
    min_object_detections=2,
    trajectory_arrow_stride=1,
    display_height=1.8,
):
    """Save a semantic, high-resolution BEV image.

    ``render_resolution`` only controls output pixels and overlays; it does not
    change the planner's TSDF voxel size or invent additional geometry detail.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    obstacle = planner._obstacle_vol_cpu
    if obstacle is None:
        obstacle = np.zeros_like(planner._tsdf_vol_cpu, dtype=bool)

    # Match TSDFPlanner.agent_step() exactly: its legacy top-down map uses a
    # head-height slice, not an all-height obstacle projection.
    height_index = int(display_height / planner._voxel_size) + planner.min_height_voxel
    height_index = int(np.clip(height_index, 0, planner._tsdf_vol_cpu.shape[2] - 1))
    unoccupied = np.logical_and(
        planner._tsdf_vol_cpu[:, :, height_index] > 0,
        planner._tsdf_vol_cpu[:, :, 0] < 0,
    )
    explored = np.any(planner._explore_vol_cpu > 0, axis=2)
    obstacle_slice = obstacle[:, :, height_index]
    kernel_size = max(1, int(0.3 / planner._voxel_size))
    obstacle_neighborhood = ndimage.convolve(
        obstacle_slice.astype(float),
        np.ones((kernel_size, kernel_size)),
        mode="constant",
        cval=0.0,
    )

    # Same state colors as the original SCOPE planner visualization:
    # white=unknown/non-traversable, gray=seen traversable, green=explored,
    # black=obstacle at the display height.
    bev = np.full((*unoccupied.shape, 3), 255, dtype=np.uint8)
    bev[unoccupied] = (200, 200, 200)
    bev[explored & unoccupied] = (194, 246, 198)
    bev[
        (obstacle_neighborhood > 0)
        & (obstacle_neighborhood < kernel_size**2 / 2)
    ] = (100, 100, 100)
    bev[obstacle_neighborhood >= kernel_size**2 / 2] = (0, 0, 0)

    if render_resolution <= 0:
        raise ValueError("render_resolution must be positive")
    scale = planner._voxel_size / float(render_resolution)
    if scale < 1:
        raise ValueError("render_resolution must not be coarser than the TSDF voxel size")
    upsample = max(1, int(round(scale)))
    if not np.isclose(scale, upsample):
        raise ValueError("render_resolution must divide the TSDF voxel size")
    # Keep the native [voxel-x, voxel-y] orientation. Matplotlib then uses
    # x=voxel-y and y=voxel-x, identical to TSDFPlanner.agent_step().
    rendered_bev = np.repeat(np.repeat(bev, upsample, axis=0), upsample, axis=1)

    height, width = rendered_bev.shape[:2]
    fig, ax = plt.subplots(
        figsize=(max(8, width / 120), max(8, height / 120)),
        dpi=120,
    )
    ax.imshow(rendered_bev, interpolation="nearest")
    ax.set_axis_off()
    _draw_trajectory(ax, trajectory_voxels, upsample, trajectory_arrow_stride)
    _draw_object_instances(
        ax, planner, objects, upsample, int(min_object_detections)
    )
    bev_path = output_dir / f"{name}_bev.png"
    fig.savefig(bev_path, dpi=120, bbox_inches="tight", pad_inches=0)
    plt.close(fig)

    return bev_path
