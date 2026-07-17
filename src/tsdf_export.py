"""Readable, metric-consistent BEV exports for SCOPE's live TSDF planner."""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, to_rgba
from matplotlib.patches import FancyArrowPatch, Polygon
import numpy as np


_CANDIDATE_COLORS = ("#9c27b0", "#0072b2", "#d55e00")


def _candidate_color(index):
    return _CANDIDATE_COLORS[(index - 1) % len(_CANDIDATE_COLORS)]


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


def _shift_voxels(points, crop_origin):
    """Shift planner [voxel-x, voxel-y] coordinates into a cropped BEV."""
    array = np.asarray(points, dtype=float).copy()
    if array.ndim == 1:
        array[:2] -= crop_origin
    else:
        array[:, :2] -= crop_origin
    return array


def _draw_object_instances(
    ax,
    planner,
    objects,
    scale,
    min_detections,
    crop_origin,
    relevant_classes=None,
    max_labeled_instances=10,
    fill_irrelevant_instances=False,
    show_irrelevant_outlines=False,
):
    """Draw concise object context without rank prefixes or opaque fills."""
    if not objects:
        return 0

    cmap = plt.colormaps.get_cmap("tab20")
    ranked_classes = list(dict.fromkeys(relevant_classes or []))
    relevant_class_rank = (
        None
        if relevant_classes is None
        else {class_name: rank for rank, class_name in enumerate(ranked_classes)}
    )
    candidates = []
    for obj_id, obj in objects.items():
        if int(obj.get("num_detections", 0)) < min_detections:
            continue
        footprint = _object_footprint_voxels(planner, obj)
        if footprint is None:
            continue
        class_name = str(obj.get("class_name", "object"))
        class_rank = None if relevant_class_rank is None else relevant_class_rank.get(class_name)
        candidates.append((obj_id, obj, footprint, class_name, class_rank))

    if relevant_class_rank is not None:
        candidates.sort(
            key=lambda item: (
                item[4] is None,
                item[4] if item[4] is not None else float("inf"),
                -int(item[1].get("num_detections", 0)),
                int(item[0]),
            )
        )
    else:
        candidates.sort(key=lambda item: (-int(item[1].get("num_detections", 0)), int(item[0])))

    label_pool = candidates if (relevant_class_rank is None or fill_irrelevant_instances) else [
        candidate for candidate in candidates if candidate[4] is not None
    ]
    limit = max(0, int(max_labeled_instances))
    labeled_ids = {obj_id for obj_id, *_ in (label_pool if limit == 0 else label_pool[:limit])}

    # Text uses only the class name: R#/C prefixes and tracker IDs have no
    # decision semantics and made the old BEV materially harder to read.
    label_step = max(2, int(round(0.24 / planner._voxel_size))) * scale
    label_offsets = [(1, -1), (1, 1), (-1, -1), (-1, 1), (2, 0), (-2, 0)]
    count = 0
    for obj_id, _, footprint, class_name, class_rank in candidates:
        is_labeled = obj_id in labeled_ids
        if not is_labeled and not show_irrelevant_outlines:
            continue
        footprint = _shift_voxels(footprint, crop_origin)
        polygon_xy = np.column_stack((footprint[:, 1] * scale, footprint[:, 0] * scale))
        if not is_labeled:
            ax.add_patch(
                Polygon(
                    polygon_xy,
                    closed=True,
                    facecolor="none",
                    edgecolor="#777777",
                    linewidth=0.55,
                    alpha=0.42,
                    zorder=4,
                )
            )
            continue

        color_index = int(obj_id) if class_rank is None else class_rank
        color = cmap(color_index % cmap.N)
        ax.add_patch(
            Polygon(
                polygon_xy,
                closed=True,
                facecolor=color,
                edgecolor="#333333",
                linewidth=0.9,
                alpha=0.28,
                zorder=5,
            )
        )
        center = polygon_xy.mean(axis=0)
        offset = label_offsets[count % len(label_offsets)]
        label_xy = center + np.asarray(offset) * label_step
        # Keep text inside the cropped canvas.  The previous clip-only policy
        # could silently hide every semantic name at a map boundary.
        x_min, x_max = sorted(ax.get_xlim())
        y_min, y_max = sorted(ax.get_ylim())
        label_xy[0] = np.clip(label_xy[0], x_min + 2, x_max - 2)
        label_xy[1] = np.clip(label_xy[1], y_min + 2, y_max - 2)
        ax.plot(
            [center[0], label_xy[0]], [center[1], label_xy[1]],
            color="#4a4a4a", linewidth=0.45, alpha=0.70, zorder=5,
        )
        ax.text(
            label_xy[0], label_xy[1], class_name,
            ha="center", va="center", fontsize=7.2, color="black",
            bbox={"boxstyle": "round,pad=0.12", "fc": "white", "ec": "none", "alpha": 0.84},
            zorder=6,
        )
        count += 1
    return count


def _draw_trajectory(ax, trajectory_voxels, scale, arrow_stride, crop_origin):
    """Draw the executed subtask trajectory with sparse directional arrows."""
    if trajectory_voxels is None or len(trajectory_voxels) < 2:
        return
    trajectory = _shift_voxels(trajectory_voxels, crop_origin)
    xy = np.column_stack((trajectory[:, 1] * scale, trajectory[:, 0] * scale))
    ax.plot(xy[:, 0], xy[:, 1], color="#ff8c00", linewidth=1.4, zorder=8)
    ax.scatter(xy[0, 0], xy[0, 1], color="#1f77b4", edgecolors="white", s=24, zorder=10)
    stride = max(1, int(arrow_stride))
    for start, end in zip(xy[:-1:stride], xy[1::stride]):
        if np.linalg.norm(end - start) < 1e-6:
            continue
        ax.add_patch(
            FancyArrowPatch(
                posA=tuple(start), posB=tuple(end), arrowstyle="-|>",
                mutation_scale=7, linewidth=1.0, color="#ff8c00", zorder=9,
            )
        )


def _draw_agent_pose(ax, agent_voxel, agent_yaw, planner, scale, crop_origin):
    """Draw a compact centre dot and heading arrow without blocking the map."""
    if agent_voxel is None:
        return
    point = _shift_voxels(agent_voxel, crop_origin)[:2]
    if point.size != 2 or not np.all(np.isfinite(point)):
        return
    try:
        direction = np.asarray(planner.rad2vector(agent_yaw), dtype=float)[:2]
    except Exception:
        direction = np.array([1.0, 0.0])
    norm = np.linalg.norm(direction)
    direction = np.array([1.0, 0.0]) if norm < 1e-6 else direction / norm
    center = np.array([point[1] * scale, point[0] * scale])
    forward = np.array([direction[1], direction[0]])
    arrow_length = 0.28 / planner._voxel_size * scale
    ax.scatter(
        center[0], center[1], s=34, c="#1565c0", edgecolors="white",
        linewidths=0.9, zorder=14,
    )
    ax.add_patch(
        FancyArrowPatch(
            posA=tuple(center), posB=tuple(center + forward * arrow_length),
            arrowstyle="-|>", mutation_scale=9, linewidth=1.8,
            color="#e31a1c", zorder=15,
        )
    )


def _draw_frontier_candidates(ax, frontiers, scale, crop_origin):
    """Draw F1..Fn with stable distinct colors in both BEV inputs."""
    for index, frontier in enumerate(frontiers or [], start=1):
        position = _shift_voxels(frontier.position, crop_origin)
        xy = (position[1] * scale, position[0] * scale)
        color = _candidate_color(index)
        ax.scatter(*xy, s=56, c="white", edgecolors=color, linewidths=1.7, zorder=11)
        ax.text(
            xy[0] + 1.5 * scale, xy[1] - 1.5 * scale, f"F{index}", fontsize=7,
            color="black", zorder=12, clip_on=True,
            bbox={"boxstyle": "round,pad=0.12", "fc": "white", "ec": color, "alpha": 0.92},
        )


def _build_planner_bev(planner, display_height):
    """Build a BEV that distinguishes unknown space from observed map state."""
    obstacle = planner._obstacle_vol_cpu
    if obstacle is None:
        obstacle = np.zeros_like(planner._tsdf_vol_cpu, dtype=bool)
    height_index = int(display_height / planner._voxel_size) + planner.min_height_voxel
    height_index = int(np.clip(height_index, 0, planner._tsdf_vol_cpu.shape[2] - 1))
    unoccupied = np.logical_and(
        planner._tsdf_vol_cpu[:, :, height_index] > 0,
        planner._tsdf_vol_cpu[:, :, 0] < 0,
    )
    explored = np.any(planner._explore_vol_cpu > 0, axis=2)
    observed = np.any(planner._weight_vol_cpu > 0, axis=2)
    obstacle_slice = obstacle[:, :, height_index]

    # Pale blue = genuinely unobserved/unknown.  It replaces the old white
    # canvas whose meaning was absent from both the image and VLM prompt.
    bev = np.full((*unoccupied.shape, 3), (224, 235, 250), dtype=np.uint8)
    bev[observed & ~unoccupied] = (230, 230, 230)
    bev[unoccupied] = (200, 200, 200)
    bev[explored & unoccupied] = (194, 246, 198)
    # This is a VLM display map, not the collision map.  Do not visually
    # inflate obstacles by 0.3 m: on a 5 cm grid it produced thick black walls
    # that swallowed corridor and object context.  Collision inflation remains
    # untouched inside the planner itself.
    bev[obstacle_slice] = (0, 0, 0)
    support = observed | explored | unoccupied | obstacle_slice
    return bev, unoccupied, support


def _compute_crop_bounds(shape, support, planner, trajectory_voxels=None, agent_voxel=None,
                         candidate_positions=None, padding_m=1.5, min_size_m=6.0):
    """Crop blank TSDF volume while retaining all decision-relevant positions."""
    points = [np.argwhere(support)]
    for item in (trajectory_voxels, [agent_voxel] if agent_voxel is not None else None, candidate_positions):
        if item is None:
            continue
        values = np.asarray(item, dtype=float)
        if values.size:
            points.append(values.reshape(-1, values.shape[-1])[:, :2])
    merged = np.vstack([item for item in points if len(item)])
    if len(merged) == 0:
        return 0, shape[0], 0, shape[1]
    lower = np.floor(np.nanmin(merged, axis=0)).astype(int)
    upper = np.ceil(np.nanmax(merged, axis=0)).astype(int) + 1
    pad = max(1, int(round(padding_m / planner._voxel_size)))
    lower -= pad
    upper += pad
    minimum = max(1, int(round(min_size_m / planner._voxel_size)))
    for axis in range(2):
        shortfall = minimum - (upper[axis] - lower[axis])
        if shortfall > 0:
            lower[axis] -= shortfall // 2
            upper[axis] += shortfall - shortfall // 2
    lower = np.maximum(lower, 0)
    upper = np.minimum(upper, np.asarray(shape[:2]))
    return int(lower[0]), int(upper[0]), int(lower[1]), int(upper[1])


def _crop_bev(bev, traversable, support, planner, trajectory_voxels=None, agent_voxel=None,
              candidate_positions=None, crop_padding_m=1.5, min_crop_size_m=6.0):
    x0, x1, y0, y1 = _compute_crop_bounds(
        bev.shape, support, planner, trajectory_voxels, agent_voxel, candidate_positions,
        crop_padding_m, min_crop_size_m,
    )
    return bev[x0:x1, y0:y1], traversable[x0:x1, y0:y1], np.asarray([x0, y0], dtype=float)


def _new_bev_figure(bev):
    """Create the exact same canvas geometry for semantic and Gaussian BEVs."""
    height, width = bev.shape[:2]
    figure_width = 8.0
    figure_height = min(10.0, max(5.5, figure_width * height / max(width, 1)))
    fig, ax = plt.subplots(figsize=(figure_width, figure_height), dpi=120)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    ax.imshow(bev, interpolation="nearest")
    ax.set_axis_off()
    return fig, ax


def _prediction_weight_and_sigma(scores, min_sigma_m, max_sigma_m):
    """Map direct frontier evidence scores to a visual, heuristic uncertainty."""
    evidence = np.array([
        scores.get("potential_score", 3.0),
        scores.get("semantic_richness", 3.0),
        scores.get("explorability", 3.0),
    ], dtype=float)
    evidence = np.clip(evidence, 1.0, 5.0)
    relevance = float(np.clip(scores.get("goal_relevance", 3.0), 1.0, 5.0))
    evidence_strength = np.average(evidence, weights=[0.5, 0.3, 0.2]) / 5.0
    weight = evidence_strength * (relevance / 5.0)
    disagreement = np.std(np.append(evidence, relevance)) / 2.0
    uncertainty = np.clip(0.5 * (1.0 - evidence_strength) + 0.5 * disagreement, 0.0, 1.0)
    sigma_m = min_sigma_m + uncertainty * (max_sigma_m - min_sigma_m)
    return float(weight), float(sigma_m)


def save_frontier_gaussian_bev(
    planner, output_dir, name, candidates, trajectory_voxels=None, agent_voxel=None,
    agent_yaw=None, display_height=1.8, min_sigma_m=0.5, max_sigma_m=2.0,
    trajectory_arrow_stride=4, crop_padding_m=1.5, min_crop_size_m=6.0,
):
    """Save a candidate-coloured evidence field on the same cropped BEV frame."""
    if not candidates:
        return None
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    bev, traversable, support = _build_planner_bev(planner, display_height)
    positions = [np.asarray(candidate["position"], dtype=float)[:2] for candidate in candidates]
    bev, traversable, crop_origin = _crop_bev(
        bev, traversable, support, planner, trajectory_voxels, agent_voxel, positions,
        crop_padding_m, min_crop_size_m,
    )
    x_grid, y_grid = np.ogrid[:bev.shape[0], :bev.shape[1]]
    candidate_info = []
    for index, candidate in enumerate(candidates, start=1):
        position = _shift_voxels(candidate["position"], crop_origin)[:2]
        weight, sigma_m = _prediction_weight_and_sigma(candidate["scores"], min_sigma_m, max_sigma_m)
        sigma_vox = max(sigma_m / planner._voxel_size, 1e-6)
        field = np.exp(-((x_grid - position[0]) ** 2 + (y_grid - position[1]) ** 2) / (2.0 * sigma_vox**2))
        candidate_info.append((position, weight, sigma_m, field, index))

    fig, ax = _new_bev_figure(bev)
    peak_weight = max((info[1] for info in candidate_info), default=1.0)
    for position, weight, sigma_m, field, index in candidate_info:
        visible = np.ma.masked_where((field < 0.08) | ~traversable, field)
        relative_weight = weight / max(peak_weight, 1e-6)
        alpha = 0.18 + 0.50 * relative_weight
        color = _candidate_color(index)
        cmap = LinearSegmentedColormap.from_list(
            f"candidate_{index}", [(1, 1, 1, 0), (*to_rgba(color)[:3], 1)]
        )
        ax.imshow(visible, cmap=cmap, alpha=alpha, interpolation="bilinear", zorder=4)
        ax.scatter(position[1], position[0], s=44, c="white", edgecolors=color, linewidths=1.5, zorder=10)
        ax.text(
            position[1] + 1.5, position[0] - 1.5, f"F{index}  {weight:.2f}, {sigma_m:.1f}m",
            fontsize=6.2, color="black", zorder=11, clip_on=True,
            bbox={"boxstyle": "round,pad=0.10", "fc": "white", "ec": color, "alpha": 0.88},
        )
    _draw_trajectory(ax, trajectory_voxels, 1, trajectory_arrow_stride, crop_origin)
    _draw_agent_pose(ax, agent_voxel, agent_yaw, planner, 1, crop_origin)
    ax.text(
        0.012, 0.012,
        "candidate color: F1/F2/F3 | radius: heuristic uncertainty | opacity: evidence × relevance",
        transform=ax.transAxes, fontsize=5.8, color="black",
        bbox={"boxstyle": "round,pad=0.16", "fc": "white", "ec": "none", "alpha": 0.80}, zorder=20,
    )
    output_path = output_dir / f"{name}_gaussian_bev.png"
    fig.savefig(output_path, dpi=120, pad_inches=0)
    plt.close(fig)
    return output_path


def save_bev_visualization(
    planner, output_dir, name, trajectory_voxels=None, objects=None, render_resolution=0.025,
    min_object_detections=2, trajectory_arrow_stride=4, relevant_classes=None,
    max_labeled_instances=10, fill_irrelevant_instances=False,
    show_irrelevant_outlines=False, display_height=1.8, frontier_candidates=None,
    agent_voxel=None, agent_yaw=None, crop_padding_m=1.5, min_crop_size_m=6.0,
):
    """Save a compact semantic BEV for VLM input.

    ``render_resolution`` remains accepted for config compatibility.  The
    output is rasterized at a fixed image resolution after crop, so it never
    upsamples or invents TSDF detail.
    """
    if render_resolution <= 0:
        raise ValueError("render_resolution must be positive")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    bev, traversable, support = _build_planner_bev(planner, display_height)
    positions = [np.asarray(frontier.position, dtype=float)[:2] for frontier in (frontier_candidates or [])]
    bev, _, crop_origin = _crop_bev(
        bev, traversable, support, planner, trajectory_voxels, agent_voxel, positions,
        crop_padding_m, min_crop_size_m,
    )
    fig, ax = _new_bev_figure(bev)
    _draw_trajectory(ax, trajectory_voxels, 1, trajectory_arrow_stride, crop_origin)
    _draw_object_instances(
        ax, planner, objects, 1, int(min_object_detections), crop_origin,
        relevant_classes=relevant_classes, max_labeled_instances=max_labeled_instances,
        fill_irrelevant_instances=fill_irrelevant_instances,
        show_irrelevant_outlines=show_irrelevant_outlines,
    )
    _draw_frontier_candidates(ax, frontier_candidates, 1, crop_origin)
    _draw_agent_pose(ax, agent_voxel, agent_yaw, planner, 1, crop_origin)
    ax.text(
        0.012, 0.012,
        "blue: unknown | gray: observed free | green: explored free | black: obstacle | colored: semantic context",
        transform=ax.transAxes, fontsize=5.8, color="black",
        bbox={"boxstyle": "round,pad=0.16", "fc": "white", "ec": "none", "alpha": 0.80}, zorder=20,
    )
    bev_path = output_dir / f"{name}_bev.png"
    fig.savefig(bev_path, dpi=120, pad_inches=0)
    plt.close(fig)
    return bev_path
