"""Readable, metric-consistent BEV exports for SCOPE's live TSDF planner."""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, to_rgba
from matplotlib.patches import FancyArrowPatch
from matplotlib.path import Path as MplPath
from scipy import ndimage
import numpy as np


_RELIABILITY_SATURATION_DETECTIONS = 5.0
"""num_detections at which an object's identity is treated as fully
trusted (reliability saturates at 1.0). Shared between the semantic
foresight term (_frontier_semantic_novelty_3d) and the semantic-BEV object
rendering (_draw_object_instances) so both read the same signal off the
same scale -- not two independently-tuned thresholds."""


_CANDIDATE_PALETTE = [
    # Curated from tab20/tab20b, with every blue/pale-cyan entry dropped so no
    # candidate colour is confusable with the pale-blue "unknown space" BEV
    # background (224, 235, 250). Orange first since it reads best on both
    # the green "explored" and grey "observed" backgrounds.
    "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b",
    "#e377c2", "#bcbd22", "#7f7f7f", "#c49c00",
    "#f7b6d2", "#c5b0d5", "#98df8a", "#ff9896", "#8c6d31",
]


def _candidate_color(index):
    """Use distinct, background-safe colours for the first N VLM frontier labels."""
    return _CANDIDATE_PALETTE[(index - 1) % len(_CANDIDATE_PALETTE)]


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


def _object_anchor_voxel(planner, obj):
    """Return the object's tracked centre in planner XY voxel coordinates."""
    try:
        center = np.asarray(obj["bbox"].center, dtype=float)
        if center.shape != (3,) or not np.all(np.isfinite(center)):
            return None
        return np.asarray(planner.habitat2voxel(center)[:2], dtype=float)
    except Exception:
        return None


def _polygon_area_m2(footprint, voxel_size):
    """Area of a projected XY footprint in square metres."""
    footprint = np.asarray(footprint, dtype=float)
    if footprint.ndim != 2 or footprint.shape[0] < 3:
        return 0.0
    x, y = footprint[:, 0], footprint[:, 1]
    area_voxels = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
    return float(area_voxels * voxel_size * voxel_size)


def _point_has_support(mask, point, radius_voxels):
    """Whether a planner XY point has observed support in a local metric radius."""
    if mask is None or mask.size == 0:
        return False
    point = np.rint(np.asarray(point, dtype=float)[:2]).astype(int)
    radius = max(0, int(np.ceil(radius_voxels)))
    x0, x1 = max(0, point[0] - radius), min(mask.shape[0], point[0] + radius + 1)
    y0, y1 = max(0, point[1] - radius), min(mask.shape[1], point[1] + radius + 1)
    return bool(x0 < x1 and y0 < y1 and np.any(mask[x0:x1, y0:y1]))


def _semantic_shape_from_footprint(support, footprint, anchor, voxel_size, dilation_m=0.10):
    """Extract a compact observed TSDF shape inside a valid object footprint.

    The ConceptGraph OBB supplies only a candidate region.  The final shape is
    made from actual obstacle voxels inside it, lightly dilated for legibility,
    and restricted to the component nearest the tracked centre.
    """
    footprint = np.asarray(footprint, dtype=float)
    lower = np.floor(np.min(footprint, axis=0)).astype(int) - 1
    upper = np.ceil(np.max(footprint, axis=0)).astype(int) + 2
    lower = np.maximum(lower, 0)
    upper = np.minimum(upper, np.asarray(support.shape))
    if np.any(upper <= lower):
        return None
    shape = tuple((upper - lower).astype(int))
    local_footprint = footprint - lower
    grid_rows, grid_cols = np.mgrid[:shape[0], :shape[1]]
    local_points = np.column_stack((grid_rows.ravel(), grid_cols.ravel()))
    raw_mask = MplPath(local_footprint).contains_points(local_points, radius=1e-9).reshape(shape)
    observed_shape = raw_mask & support[lower[0]:upper[0], lower[1]:upper[1]]
    if np.count_nonzero(observed_shape) < 1:
        return None

    radius = max(1, int(round(float(dilation_m) / voxel_size)))
    observed_shape = ndimage.binary_dilation(observed_shape, iterations=radius) & raw_mask
    # Do not apply a closing/erosion pass here: early TSDF observations can be
    # only one or two valid surface voxels, and closing would erase them.
    labels, component_count = ndimage.label(observed_shape)
    if component_count == 0:
        return None

    local_anchor = np.asarray(anchor, dtype=float) - lower
    best_label, best_distance = None, float("inf")
    for label in range(1, component_count + 1):
        component_rows, component_cols = np.nonzero(labels == label)
        distances = (component_rows - local_anchor[0]) ** 2 + (component_cols - local_anchor[1]) ** 2
        distance = float(np.min(distances))
        if distance < best_distance:
            best_label, best_distance = label, distance
    semantic_shape = labels == best_label
    component_rows, component_cols = np.nonzero(semantic_shape)
    semantic_anchor = np.array(
        [component_rows.mean() + lower[0], component_cols.mean() + lower[1]], dtype=float
    )
    return semantic_shape, lower.astype(float), semantic_anchor


def _shape_contains_trajectory(shape_mask, shape_origin, trajectory):
    """Whether any recorded trajectory cell falls inside an observed semantic shape."""
    if trajectory is None or len(trajectory) == 0:
        return False
    local = np.rint(np.asarray(trajectory, dtype=float)[:, :2] - shape_origin).astype(int)
    valid = (
        (local[:, 0] >= 0) & (local[:, 0] < shape_mask.shape[0]) &
        (local[:, 1] >= 0) & (local[:, 1] < shape_mask.shape[1])
    )
    return bool(np.any(shape_mask[local[valid, 0], local[valid, 1]])) if np.any(valid) else False


def _semantic_shape_iou(first, second):
    """Compute IoU of two compact semantic masks in global voxel coordinates."""
    first_mask, first_origin = first["shape_mask"], np.rint(first["shape_origin"]).astype(int)
    second_mask, second_origin = second["shape_mask"], np.rint(second["shape_origin"]).astype(int)
    lower = np.maximum(first_origin, second_origin)
    upper = np.minimum(
        first_origin + np.asarray(first_mask.shape),
        second_origin + np.asarray(second_mask.shape),
    )
    if np.any(upper <= lower):
        return 0.0
    first_lower = lower - first_origin
    first_upper = upper - first_origin
    second_lower = lower - second_origin
    second_upper = upper - second_origin
    first_overlap = first_mask[first_lower[0]:first_upper[0], first_lower[1]:first_upper[1]]
    second_overlap = second_mask[second_lower[0]:second_upper[0], second_lower[1]:second_upper[1]]
    intersection = int(np.count_nonzero(first_overlap & second_overlap))
    union = int(np.count_nonzero(first_mask) + np.count_nonzero(second_mask) - intersection)
    return float(intersection / union) if union else 0.0


def _deduplicate_semantic_instances(candidates, voxel_size, merge_radius_m):
    """Keep one representative for overlapping duplicate same-class tracks.

    ConceptGraph association is intentionally permissive.  A cabinet observed
    from several angles can consequently survive as multiple nearby tracks.
    Rendering every track makes the decision BEV repeat one noun many times,
    even though the extra tracks add no spatial evidence for the VLM.
    """
    if not candidates:
        return []
    merge_radius_voxels = max(0.0, float(merge_radius_m) / voxel_size)
    kept = []
    for candidate in candidates:
        duplicate = False
        for representative in kept:
            if candidate["class_name"] != representative["class_name"]:
                continue
            distance = float(np.linalg.norm(candidate["anchor"] - representative["anchor"]))
            if distance > merge_radius_voxels:
                continue
            # A substantial footprint overlap is the normal duplicate-track
            # case.  The short-distance fallback handles sparse, disjoint
            # observed surface fragments belonging to the same physical item.
            if _semantic_shape_iou(candidate, representative) >= 0.20 or distance <= 0.25 / voxel_size:
                duplicate = True
                break
        if not duplicate:
            kept.append(candidate)
    return kept


def _prepare_semantic_instances(
    planner,
    objects,
    min_detections,
    relevant_classes=None,
    max_labeled_instances=10,
    fill_irrelevant_instances=False,
    trajectory_voxels=None,
    max_footprint_area_m2=6.0,
    max_extent_m=4.0,
    support_radius_m=0.4,
    shape_dilation_m=0.10,
    same_class_merge_radius_m=0.55,
):
    """Select only TSDF-consistent object anchors for a decision BEV.

    ConceptGraph boxes are useful as semantic *hypotheses*, but their raw OBB
    geometry is not a collision map.  In particular, a merged outlier box can
    span free TSDF cells and a previously executed path.  Such a box must not
    be presented to the VLM as a real semantic region.
    """
    if not objects:
        return []

    observed = np.any(planner._weight_vol_cpu > 0, axis=2)
    obstacle = planner._obstacle_vol_cpu
    if obstacle is not None:
        physical_support = np.any(obstacle, axis=2)
    else:
        # Keep visualisation usable when obstacle saving is disabled, while
        # retaining the stronger physical check during normal evaluation.
        physical_support = observed

    trajectory = None
    if trajectory_voxels is not None:
        trajectory = np.asarray(trajectory_voxels, dtype=float)
        if trajectory.ndim != 2 or trajectory.shape[1] < 2:
            trajectory = None
        elif len(trajectory):
            trajectory = trajectory[:, :2]

    ranked_classes = list(dict.fromkeys(relevant_classes or []))
    relevant_class_rank = (
        None
        if relevant_classes is None
        else {class_name: rank for rank, class_name in enumerate(ranked_classes)}
    )
    support_radius_voxels = float(support_radius_m) / planner._voxel_size
    candidates = []
    for obj_id, obj in objects.items():
        if int(obj.get("num_detections", 0)) < min_detections:
            continue
        anchor = _object_anchor_voxel(planner, obj)
        footprint = _object_footprint_voxels(planner, obj)
        if anchor is None or footprint is None:
            continue
        if not (0 <= anchor[0] < observed.shape[0] and 0 <= anchor[1] < observed.shape[1]):
            continue

        area_m2 = _polygon_area_m2(footprint, planner._voxel_size)
        extent_m = float(np.max(np.ptp(footprint, axis=0)) * planner._voxel_size)
        if not np.isfinite(area_m2) or not np.isfinite(extent_m):
            continue
        if area_m2 > max_footprint_area_m2 or extent_m > max_extent_m:
            continue

        # A displayed semantic anchor must be near an observed physical
        # surface.  This prevents a stale tracker box from labelling empty
        # navigable TSDF space as an object.
        if not _point_has_support(observed, anchor, support_radius_voxels):
            continue
        if not _point_has_support(physical_support, anchor, support_radius_voxels):
            continue

        semantic_shape = _semantic_shape_from_footprint(
            physical_support, footprint, anchor, planner._voxel_size,
            dilation_m=shape_dilation_m,
        )
        if semantic_shape is None:
            continue
        shape_mask, shape_origin, semantic_anchor = semantic_shape

        # A static semantic region may not cover a recorded navigable path.
        # The reported bathtub failure is rejected either here or by the raw
        # OBB size limits above; normal nearby furniture remains valid.
        if _shape_contains_trajectory(shape_mask, shape_origin, trajectory):
            continue

        class_name = str(obj.get("class_name", "object"))
        class_rank = None if relevant_class_rank is None else relevant_class_rank.get(class_name)
        candidates.append(
            {
                "obj_id": obj_id,
                "class_name": class_name,
                "class_rank": class_rank,
                "num_detections": int(obj.get("num_detections", 0)),
                "anchor": semantic_anchor,
                "shape_mask": shape_mask,
                "shape_origin": shape_origin,
            }
        )

    if relevant_class_rank is not None:
        candidates.sort(
            key=lambda item: (
                item["class_rank"] is None,
                item["class_rank"] if item["class_rank"] is not None else float("inf"),
                -item["num_detections"],
                int(item["obj_id"]),
            )
        )
    else:
        candidates.sort(key=lambda item: (-item["num_detections"], int(item["obj_id"])))

    candidates = _deduplicate_semantic_instances(
        candidates, planner._voxel_size, same_class_merge_radius_m,
    )

    label_pool = candidates if (relevant_class_rank is None or fill_irrelevant_instances) else [
        candidate for candidate in candidates if candidate["class_rank"] is not None
    ]
    limit = max(0, int(max_labeled_instances))
    return label_pool if limit == 0 else label_pool[:limit]


def _shift_voxels(points, crop_origin):
    """Shift planner [voxel-x, voxel-y] coordinates into a cropped BEV."""
    array = np.asarray(points, dtype=float).copy()
    if array.ndim == 1:
        array[:2] -= crop_origin
    else:
        array[:, :2] -= crop_origin
    return array


def _semantic_display_field(shape_mask, voxel_size, smoothing_m):
    """Return a display-only, sub-voxel-smoothed field for semantic contours.

    The original binary TSDF-supported mask remains the source of truth for
    validation, association and navigation.  This field is used only by
    Matplotlib to avoid visually distracting 5 cm stair-steps on object edges.
    """
    field = np.asarray(shape_mask, dtype=float)
    smoothing_voxels = max(0.0, float(smoothing_m) / voxel_size)
    if smoothing_voxels <= 0.0 or np.count_nonzero(field) < 4:
        return field, 0.5
    # Keep the blur below one cell.  It rounds a raster edge without shifting
    # the semantic footprint by more than roughly one 5 cm voxel.
    sigma = min(1.0, smoothing_voxels) * 0.65
    smoothed = ndimage.gaussian_filter(field, sigma=sigma, mode="nearest")
    if float(np.max(smoothed)) <= 0.5:
        return field, 0.5
    return smoothed, 0.5


def _draw_object_instances(
    ax, planner, instances, scale, crop_origin, display_smoothing_m=0.0,
    reliability_rendering_enabled=False,
):
    """Draw TSDF-supported semantic regions and their concise class labels.

    When ``reliability_rendering_enabled`` is False (default), every
    instance renders at the original fixed alpha/solid outline -- this
    reproduces prior behaviour exactly. When True, fill opacity and outline
    style are modulated by the same ``num_detections``-based reliability
    the semantic foresight term uses.
    """
    if not instances:
        return 0

    cmap = plt.colormaps.get_cmap("tab20")
    label_step = max(2, int(round(0.30 / planner._voxel_size))) * scale
    label_offsets = [(1, -1), (1, 1), (-1, -1), (-1, 1), (2, 0), (-2, 0)]
    count = 0
    for instance in instances:
        anchor = _shift_voxels(instance["anchor"], crop_origin)
        center = np.array([anchor[1] * scale, anchor[0] * scale])
        color_index = int(instance["obj_id"]) if instance["class_rank"] is None else instance["class_rank"]
        color = cmap(color_index % cmap.N)
        shape_origin = _shift_voxels(instance["shape_origin"], crop_origin)
        shape_mask = instance["shape_mask"]
        display_field, contour_level = _semantic_display_field(
            shape_mask, planner._voxel_size, display_smoothing_m,
        )
        rows = np.arange(shape_mask.shape[0]) + shape_origin[0]
        cols = np.arange(shape_mask.shape[1]) + shape_origin[1]
        upper_level = max(float(np.max(display_field)) + 1e-3, contour_level + 1e-3)
        if reliability_rendering_enabled:
            # Reliability reuses the same signal (and saturation scale) the
            # semantic foresight term reads off num_detections: a barely-
            # passed object (min_object_detections floor) renders
            # faint/dashed, a well-established one solid -- same number,
            # one more outlet, not a new mechanism.
            reliability = min(
                float(instance.get("num_detections", 0)) / _RELIABILITY_SATURATION_DETECTIONS, 1.0,
            )
            fill_alpha = 0.25 + 0.35 * reliability
            edge_style = "solid" if reliability >= 0.6 else "dashed"
        else:
            fill_alpha = 0.48
            edge_style = "solid"
        ax.contourf(
            cols * scale, rows * scale, display_field,
            levels=[contour_level, upper_level], colors=[color], alpha=fill_alpha, zorder=5,
        )
        ax.contour(
            cols * scale, rows * scale, display_field,
            levels=[contour_level], colors=["#333333"], linewidths=0.70,
            linestyles=[edge_style], zorder=6,
        )
        offset = label_offsets[count % len(label_offsets)]
        label_xy = center + np.asarray(offset) * label_step
        # Every anchor is part of the crop.  Clamp only the short callout, not
        # a remote object centre; this prevents the old edge-floating labels.
        x_min, x_max = sorted(ax.get_xlim())
        y_min, y_max = sorted(ax.get_ylim())
        label_xy[0] = np.clip(label_xy[0], x_min + 2, x_max - 2)
        label_xy[1] = np.clip(label_xy[1], y_min + 2, y_max - 2)
        ax.plot(
            [center[0], label_xy[0]], [center[1], label_xy[1]],
            color="#4a4a4a", linewidth=0.45, alpha=0.70, zorder=5,
        )
        ax.text(
            label_xy[0], label_xy[1], instance["class_name"],
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


def _build_planner_bev(planner, display_height, coverage_rendering_enabled=False, coverage_height_m=2.2):
    """Build a BEV that distinguishes unknown space from observed map state.

    When ``coverage_rendering_enabled`` is False (default), this reproduces
    the original column-collapsed boolean exactly (``np.any(..., axis=2)``):
    a column counts as "explored"/"observed" the moment any single height
    in it was seen once. When True, "explored"/"observed" become coverage
    *ratios* over the relevant-height band (the same band and cap used by
    the 3D geometric foresight signal, ``_frontier_unknown_volume_3d_ahead``)
    instead of that boolean -- a column whose floor is visible but whose
    cabinet-top above it was never actually in the camera's frame renders
    as partially, not fully, shaded, proportional to how much of it has
    actually been seen.
    """
    obstacle = planner._obstacle_vol_cpu
    if obstacle is None:
        obstacle = np.zeros_like(planner._tsdf_vol_cpu, dtype=bool)
    height_index = int(display_height / planner._voxel_size) + planner.min_height_voxel
    height_index = int(np.clip(height_index, 0, planner._tsdf_vol_cpu.shape[2] - 1))
    unoccupied = np.logical_and(
        planner._tsdf_vol_cpu[:, :, height_index] > 0,
        planner._tsdf_vol_cpu[:, :, 0] < 0,
    )
    obstacle_slice = obstacle[:, :, height_index]

    if coverage_rendering_enabled:
        n_z = planner._explore_vol_cpu.shape[2]
        height_voxels = max(1, int(round(coverage_height_m / planner._voxel_size)))
        z_cap = min(n_z, planner.min_height_voxel + height_voxels)
        explored_coverage = np.mean(planner._explore_vol_cpu[:, :, :z_cap] > 0, axis=2)
        observed_coverage = np.mean(planner._weight_vol_cpu[:, :, :z_cap] > 0, axis=2)
    else:
        explored_coverage = np.any(planner._explore_vol_cpu > 0, axis=2).astype(float)
        observed_coverage = np.any(planner._weight_vol_cpu > 0, axis=2).astype(float)

    # Pale blue = genuinely unobserved/unknown.  It replaces the old white
    # canvas whose meaning was absent from both the image and VLM prompt.
    unknown_rgb = np.array((224, 235, 250), dtype=float)
    observed_rgb = np.array((230, 230, 230), dtype=float)
    unoccupied_rgb = np.array((200, 200, 200), dtype=float)
    explored_rgb = np.array((194, 246, 198), dtype=float)

    bev = unknown_rgb + observed_coverage[..., None] * (observed_rgb - unknown_rgb)
    unoccupied_shade = unoccupied_rgb + explored_coverage[..., None] * (explored_rgb - unoccupied_rgb)
    bev[unoccupied] = unoccupied_shade[unoccupied]
    # This is a VLM display map, not the collision map.  Do not visually
    # inflate obstacles by 0.3 m: on a 5 cm grid it produced thick black walls
    # that swallowed corridor and object context.  Collision inflation remains
    # untouched inside the planner itself.
    bev[obstacle_slice] = (0, 0, 0)
    bev = np.clip(bev, 0, 255).astype(np.uint8)
    support = (observed_coverage > 0) | (explored_coverage > 0) | unoccupied | obstacle_slice
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


def _frontier_unknown_volume_ahead(
    planner, position_vox, direction_xy, max_range_m, cone_half_angle_deg=35.0,
):
    """Fraction of unexplored cells inside a sector ahead of a frontier.

    Zero extra VLM calls: this only reads the planner's existing occupancy
    bookkeeping (``planner.unexplored``), which is already maintained every
    step for frontier detection. This is the single-height-slice (2D)
    version, validated full-scale (see ``feat/foresight-anisotropic-gaussian``,
    38.85/61.87/29.12/41.88 on split1) -- kept byte-for-byte unchanged so the
    ``geometric_3d_weight=0`` fallback path reproduces that exact result.
    """
    unexplored = getattr(planner, "unexplored", None)
    if unexplored is None:
        return 0.0
    direction_xy = np.asarray(direction_xy, dtype=float)
    norm = np.linalg.norm(direction_xy)
    if norm < 1e-6:
        return 0.0
    direction_xy = direction_xy / norm

    max_range_vox = max(1.0, float(max_range_m) / planner._voxel_size)
    x0 = int(np.clip(position_vox[0] - max_range_vox, 0, unexplored.shape[0] - 1))
    x1 = int(np.clip(position_vox[0] + max_range_vox, 0, unexplored.shape[0] - 1)) + 1
    y0 = int(np.clip(position_vox[1] - max_range_vox, 0, unexplored.shape[1] - 1))
    y1 = int(np.clip(position_vox[1] + max_range_vox, 0, unexplored.shape[1] - 1)) + 1
    if x1 <= x0 or y1 <= y0:
        return 0.0

    xs, ys = np.mgrid[x0:x1, y0:y1]
    dx = xs - position_vox[0]
    dy = ys - position_vox[1]
    dist = np.sqrt(dx**2 + dy**2)
    within_range = (dist > 0) & (dist <= max_range_vox)
    cos_sim = (dx * direction_xy[0] + dy * direction_xy[1]) / np.maximum(dist, 1e-6)
    within_cone = cos_sim >= np.cos(np.deg2rad(cone_half_angle_deg))
    sector = within_range & within_cone
    sector_size = int(np.count_nonzero(sector))
    if sector_size == 0:
        return 0.0
    unknown_in_sector = int(np.count_nonzero(unexplored[x0:x1, y0:y1][sector]))
    return unknown_in_sector / sector_size


def _sector_xy_mask(planner, shape2d, position_vox, direction_xy, max_range_m, cone_half_angle_deg):
    """Shared 2D sector geometry (range + cone ahead of a frontier), ported
    unchanged from ``feat/3d-tsdf-foresight``. Returns ``(x0, x1, y0, y1,
    sector_mask)`` or ``None`` if the direction is degenerate."""
    direction_xy = np.asarray(direction_xy, dtype=float)
    norm = np.linalg.norm(direction_xy)
    if norm < 1e-6:
        return None
    direction_xy = direction_xy / norm

    max_range_vox = max(1.0, float(max_range_m) / planner._voxel_size)
    x0 = int(np.clip(position_vox[0] - max_range_vox, 0, shape2d[0] - 1))
    x1 = int(np.clip(position_vox[0] + max_range_vox, 0, shape2d[0] - 1)) + 1
    y0 = int(np.clip(position_vox[1] - max_range_vox, 0, shape2d[1] - 1))
    y1 = int(np.clip(position_vox[1] + max_range_vox, 0, shape2d[1] - 1)) + 1
    if x1 <= x0 or y1 <= y0:
        return None

    xs, ys = np.mgrid[x0:x1, y0:y1]
    dx = xs - position_vox[0]
    dy = ys - position_vox[1]
    dist = np.sqrt(dx**2 + dy**2)
    within_range = (dist > 0) & (dist <= max_range_vox)
    cos_sim = (dx * direction_xy[0] + dy * direction_xy[1]) / np.maximum(dist, 1e-6)
    within_cone = cos_sim >= np.cos(np.deg2rad(cone_half_angle_deg))
    sector = within_range & within_cone
    return x0, x1, y0, y1, sector


def _frontier_unknown_volume_3d_ahead(
    planner, position_vox, direction_xy, max_range_m, cone_half_angle_deg=35.0,
    relevant_height_m=2.2,
):
    """3D-volume counterpart of ``_frontier_unknown_volume_ahead``: fraction
    of unexplored *voxels* (not just one height slice) in the same sector,
    read from ``planner._weight_vol_cpu`` (already-maintained TSDF weight
    volume, zero extra sensing). Height-capped at ``relevant_height_m``
    above the real floor (not z=0 -- z=0 sits ``min_height_voxel`` cells
    below the floor pad) to avoid diluting the signal with near-constant
    unobserved ceiling space -- see ``feat/3d-tsdf-foresight``'s
    ``_frontier_sector_voxels`` docstring for the full derivation and the
    ~40% dilution measurement this cap fixes. Ported and simplified (ratio
    only, no voxel-set) since this fusion only needs a scalar, not the
    voxel-set greedy-coverage machinery from that branch.
    """
    weight_vol = getattr(planner, "_weight_vol_cpu", None)
    if weight_vol is None:
        return 0.0
    geom = _sector_xy_mask(
        planner, weight_vol.shape[:2], position_vox, direction_xy,
        max_range_m, cone_half_angle_deg,
    )
    if geom is None:
        return 0.0
    x0, x1, y0, y1, sector = geom
    n_z = weight_vol.shape[2]
    if relevant_height_m is not None:
        height_voxels = max(1, int(round(relevant_height_m / planner._voxel_size)))
        n_z = min(n_z, planner.min_height_voxel + height_voxels)
    sector_size = int(np.count_nonzero(sector)) * n_z
    if sector_size == 0:
        return 0.0
    column_unknown = weight_vol[x0:x1, y0:y1, :n_z] == 0
    unknown_mask = column_unknown & sector[:, :, None]
    return float(np.count_nonzero(unknown_mask)) / sector_size


def _frontier_semantic_novelty_3d(
    planner, objects, position_vox, direction_xy, max_range_m, cone_half_angle_deg=35.0,
    novelty_saturation_classes=4.0,
):
    """3D scene-graph counterpart of the geometric signal: how semantically
    "new" the space ahead of a frontier is, and how much that judgment
    should be trusted.

    Both quantities come from ``objects`` (the existing ConceptGraph scene
    graph -- no new detection, no new VLM call). An object counts as
    "already known" here if its tracked centre falls in the same sector
    used by the geometric signal. ``novelty_3d`` decreases with the number
    of *distinct* classes already known nearby (repeated instances of the
    same class count once, so this is "how much is already known", not raw
    object count). ``reliability`` is the mean, saturating fraction of
    ``num_detections`` among those objects -- 0.0 when no object claims
    this sector at all, which the caller uses to fall back to the 2D VLM
    ``explorability`` rating rather than trusting a claim built on
    weak/absent evidence. Occupancy state (the geometric signal) doesn't
    need this gating -- "this voxel was never observed" is a directly
    measured fact regardless of how much data exists elsewhere; "these are
    the objects here" is inferred from detections that can be sparse or
    wrong, which is why only this term is confidence-gated.

    Returns (novelty_3d, reliability), both in [0, 1].
    """
    if not objects:
        return 1.0, 0.0
    direction_xy = np.asarray(direction_xy, dtype=float)
    norm = np.linalg.norm(direction_xy)
    if norm < 1e-6:
        return 1.0, 0.0
    direction_xy = direction_xy / norm
    max_range_vox = max(1.0, float(max_range_m) / planner._voxel_size)
    cos_thresh = np.cos(np.deg2rad(cone_half_angle_deg))
    position_vox = np.asarray(position_vox, dtype=float)[:2]

    matched_classes = set()
    detection_fracs = []
    for obj in objects.values():
        anchor = _object_anchor_voxel(planner, obj)
        if anchor is None:
            continue
        delta = anchor - position_vox
        dist = float(np.linalg.norm(delta))
        if dist <= 0.0 or dist > max_range_vox:
            continue
        cos_sim = float(np.dot(delta, direction_xy) / dist)
        if cos_sim < cos_thresh:
            continue
        matched_classes.add(obj.get("class_name"))
        num_detections = float(obj.get("num_detections", 0))
        detection_fracs.append(
            min(num_detections / _RELIABILITY_SATURATION_DETECTIONS, 1.0)
        )

    if not detection_fracs:
        return 1.0, 0.0
    known_amount = len(matched_classes)
    novelty_3d = float(np.clip(1.0 - known_amount / novelty_saturation_classes, 0.0, 1.0))
    reliability = float(np.mean(detection_fracs))
    return novelty_3d, reliability


def _foresight_anisotropic_params(
    planner, frontier_position, orientation_xy, region_mask, scores, agent_voxel,
    min_sigma_par_m, max_sigma_par_m, min_sigma_perp_m, max_sigma_perp_m,
    max_foresight_range_m=3.0, semantic_foresight_weight=0.4, foresight_gain=0.6,
    geometric_3d_weight=0.0, foresight_3d_relevant_height_m=2.2, objects=None,
):
    """Frontier-conditioned anisotropic Gaussian: direction-aligned covariance
    whose long axis is modulated by an exploration "foresight" score.

    Foresight combines up to three zero/near-zero-extra-cost signals:
      - geometric (2D): fraction of unexplored space in a *single
        height-slice* sector ahead of the frontier -- the original,
        full-scale-validated signal (``feat/foresight-anisotropic-gaussian``).
      - geometric (3D, new): fraction of unexplored *voxels* (full height
        column, capped) in the same sector, from ``feat/3d-tsdf-foresight``.
        A full 2D->3D *replacement* (that branch) showed a genuine but
        lopsided trade-off on the full 278-task split1 -- worse on the two
        Snapshot metrics, better on the two Distance metrics -- suggesting
        the two geometric signals capture partially different, complementary
        information rather than one strictly subsuming the other. This
        fuses them (``geometric_3d_weight`` blends 2D and 3D) instead of
        picking one, so neither validated signal is thrown away.
        ``geometric_3d_weight=0.0`` (default) reproduces the original 2D-only
        formula exactly -- this fusion is strictly additive/optional.
      - semantic: reliability-gated blend of two sources -- 3D scene-graph
        novelty (``_frontier_semantic_novelty_3d``: fewer distinct known
        classes nearby -> higher novelty) and the existing ``explorability``
        VLM rating (no new VLM call, no prompt change). The blend weight is
        the 3D signal's own ``reliability`` (mean saturating fraction of
        ``num_detections`` among the objects it's based on) -- when the
        scene graph has no or weak evidence in this direction, this
        collapses to the original explorability-only formula; it only
        leans on the 3D estimate once there's enough evidence to trust it.

    Returns (weight, sigma_parallel_m, sigma_perp_m, e_parallel, e_perp).
    """
    base_weight, _ = _prediction_weight_and_sigma(scores, min_sigma_par_m, max_sigma_par_m)

    e_parallel = np.asarray(orientation_xy, dtype=float)
    norm = np.linalg.norm(e_parallel)
    e_parallel = e_parallel / norm if norm > 1e-6 else np.array([1.0, 0.0])
    e_perp = np.array([-e_parallel[1], e_parallel[0]])

    geom_foresight_2d = _frontier_unknown_volume_ahead(
        planner, frontier_position, e_parallel, max_foresight_range_m,
    )
    if geometric_3d_weight > 0.0:
        geom_foresight_3d = _frontier_unknown_volume_3d_ahead(
            planner, frontier_position, e_parallel, max_foresight_range_m,
            relevant_height_m=foresight_3d_relevant_height_m,
        )
        geom_foresight = (
            (1.0 - geometric_3d_weight) * geom_foresight_2d
            + geometric_3d_weight * geom_foresight_3d
        )
    else:
        geom_foresight = geom_foresight_2d
    explorability_2d = float(np.clip(scores.get("explorability", 3.0), 1.0, 5.0) - 1.0) / 4.0
    novelty_3d, reliability = _frontier_semantic_novelty_3d(
        planner, objects, frontier_position, e_parallel, max_foresight_range_m,
    )
    semantic_foresight = reliability * novelty_3d + (1.0 - reliability) * explorability_2d
    foresight = (
        (1.0 - semantic_foresight_weight) * geom_foresight
        + semantic_foresight_weight * semantic_foresight
    )

    weight = base_weight * (1.0 + foresight_gain * foresight)
    sigma_parallel_m = min_sigma_par_m + foresight * (max_sigma_par_m - min_sigma_par_m)

    if region_mask is not None and np.any(region_mask):
        region_points = np.argwhere(region_mask).astype(float)
        projected = (region_points - frontier_position) @ e_perp
        width_m = float(projected.max() - projected.min()) * planner._voxel_size
    else:
        width_m = min_sigma_perp_m * 2.0
    sigma_perp_m = float(np.clip(width_m / 2.0, min_sigma_perp_m, max_sigma_perp_m))

    return float(weight), float(sigma_parallel_m), sigma_perp_m, e_parallel, e_perp


def save_frontier_gaussian_bev(
    planner, output_dir, name, candidates, trajectory_voxels=None, agent_voxel=None,
    agent_yaw=None, display_height=1.8, min_sigma_m=0.5, max_sigma_m=2.0,
    trajectory_arrow_stride=4, crop_padding_m=1.5, min_crop_size_m=6.0,
    foresight_enabled=False, min_sigma_perp_m=0.25, max_sigma_perp_m=1.2,
    foresight_max_range_m=3.0, foresight_semantic_weight=0.4, foresight_gain=0.6,
    max_sigma_fraction_of_crop=0.35,
    foresight_geometric_3d_weight=0.0, foresight_3d_relevant_height_m=2.2, objects=None,
    coverage_rendering_enabled=False, coverage_height_m=2.2,
):
    """Save a candidate-coloured evidence field on the same cropped BEV frame.

    When ``foresight_enabled`` is False (default), this reproduces the
    original isotropic-circle field exactly. When True, each candidate's
    field becomes a frontier-direction-aligned anisotropic Gaussian whose
    long axis is stretched by an exploration "foresight" score (see
    ``_foresight_anisotropic_params``).

    Returns ``(output_path, candidate_weights)`` where ``candidate_weights``
    is a list aligned with ``candidates`` -- the same weight rendered as the
    ellipse's opacity/label text (``F{index} {weight:.2f}, {sigma_m:.1f}m``),
    exposed here so a caller can optionally also state it in text to the
    VLM instead of relying solely on the visual rendering.
    """
    if not candidates:
        return None, []
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    bev, traversable, support = _build_planner_bev(
        planner, display_height,
        coverage_rendering_enabled=coverage_rendering_enabled, coverage_height_m=coverage_height_m,
    )
    positions = [np.asarray(candidate["position"], dtype=float)[:2] for candidate in candidates]
    bev, traversable, crop_origin = _crop_bev(
        bev, traversable, support, planner, trajectory_voxels, agent_voxel, positions,
        crop_padding_m, min_crop_size_m,
    )
    x_grid, y_grid = np.ogrid[:bev.shape[0], :bev.shape[1]]
    candidate_info = []
    for index, candidate in enumerate(candidates, start=1):
        raw_position = np.asarray(candidate["position"], dtype=float)[:2]
        position = _shift_voxels(candidate["position"], crop_origin)[:2]
        if foresight_enabled:
            weight, sigma_par_m, sigma_perp_m, e_par, e_perp = _foresight_anisotropic_params(
                planner, raw_position, candidate.get("orientation", (1.0, 0.0)),
                candidate.get("region"), candidate["scores"], agent_voxel,
                min_sigma_m, max_sigma_m, min_sigma_perp_m, max_sigma_perp_m,
                max_foresight_range_m=foresight_max_range_m,
                semantic_foresight_weight=foresight_semantic_weight,
                foresight_gain=foresight_gain,
                geometric_3d_weight=foresight_geometric_3d_weight,
                foresight_3d_relevant_height_m=foresight_3d_relevant_height_m,
                objects=objects,
            )
            # A high-foresight ellipse must not dominate the crop regardless
            # of the absolute sigma range: cap its long axis to a fraction of
            # the shorter crop dimension so it stays a directional cue rather
            # than flooding the frame (observed in manual review: 1.9 m sigma
            # in a small room reached past the traversable area into the
            # unknown-space background).
            crop_extent_m = min(bev.shape[0], bev.shape[1]) * planner._voxel_size
            sigma_par_m = min(sigma_par_m, max_sigma_fraction_of_crop * crop_extent_m)
            sigma_par_vox = max(sigma_par_m / planner._voxel_size, 1e-6)
            sigma_perp_vox = max(sigma_perp_m / planner._voxel_size, 1e-6)
            dx = x_grid - position[0]
            dy = y_grid - position[1]
            d_par = dx * e_par[0] + dy * e_par[1]
            d_perp = dx * e_perp[0] + dy * e_perp[1]
            field = np.exp(-0.5 * ((d_par / sigma_par_vox) ** 2 + (d_perp / sigma_perp_vox) ** 2))
            sigma_m = sigma_par_m  # reported in the label; perp is visible in the ellipse shape
        else:
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
        0.012, 0.028,
        "candidate color: F1..Fn | radius: heuristic uncertainty | opacity: evidence × relevance",
        transform=ax.transAxes, fontsize=5.8, color="black",
        bbox={"boxstyle": "round,pad=0.16", "fc": "white", "ec": "none", "alpha": 0.80}, zorder=20,
    )
    output_path = output_dir / f"{name}_gaussian_bev.png"
    fig.savefig(output_path, dpi=120, pad_inches=0)
    plt.close(fig)
    candidate_weights = [info[1] for info in candidate_info]
    return output_path, candidate_weights


def save_bev_visualization(
    planner, output_dir, name, trajectory_voxels=None, objects=None, render_resolution=0.025,
    min_object_detections=2, trajectory_arrow_stride=4, relevant_classes=None,
    max_labeled_instances=10, fill_irrelevant_instances=False,
    show_irrelevant_outlines=False, display_height=1.8, frontier_candidates=None,
    agent_voxel=None, agent_yaw=None, crop_padding_m=1.5, min_crop_size_m=6.0,
    semantic_max_footprint_area_m2=6.0, semantic_max_extent_m=4.0,
    semantic_support_radius_m=0.4, semantic_shape_dilation_m=0.10,
    semantic_same_class_merge_radius_m=0.55,
    semantic_display_smoothing_m=0.05,
    coverage_rendering_enabled=False, coverage_height_m=2.2,
    reliability_rendering_enabled=False,
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
    bev, traversable, support = _build_planner_bev(
        planner, display_height,
        coverage_rendering_enabled=coverage_rendering_enabled, coverage_height_m=coverage_height_m,
    )
    semantic_instances = _prepare_semantic_instances(
        planner, objects, int(min_object_detections), relevant_classes=relevant_classes,
        max_labeled_instances=max_labeled_instances,
        fill_irrelevant_instances=fill_irrelevant_instances,
        trajectory_voxels=trajectory_voxels,
        max_footprint_area_m2=float(semantic_max_footprint_area_m2),
        max_extent_m=float(semantic_max_extent_m),
        support_radius_m=float(semantic_support_radius_m),
        shape_dilation_m=float(semantic_shape_dilation_m),
        same_class_merge_radius_m=float(semantic_same_class_merge_radius_m),
    )
    positions = [np.asarray(frontier.position, dtype=float)[:2] for frontier in (frontier_candidates or [])]
    positions.extend(instance["anchor"] for instance in semantic_instances)
    bev, _, crop_origin = _crop_bev(
        bev, traversable, support, planner, trajectory_voxels, agent_voxel, positions,
        crop_padding_m, min_crop_size_m,
    )
    fig, ax = _new_bev_figure(bev)
    _draw_trajectory(ax, trajectory_voxels, 1, trajectory_arrow_stride, crop_origin)
    _draw_object_instances(
        ax, planner, semantic_instances, 1, crop_origin,
        display_smoothing_m=float(semantic_display_smoothing_m),
        reliability_rendering_enabled=reliability_rendering_enabled,
    )
    _draw_frontier_candidates(ax, frontier_candidates, 1, crop_origin)
    _draw_agent_pose(ax, agent_voxel, agent_yaw, planner, 1, crop_origin)
    ax.text(
        0.012, 0.028,
        "blue: unknown | gray: observed free | green: explored free | black: obstacle | colored: semantic context",
        transform=ax.transAxes, fontsize=5.8, color="black",
        bbox={"boxstyle": "round,pad=0.16", "fc": "white", "ec": "none", "alpha": 0.80}, zorder=20,
    )
    bev_path = output_dir / f"{name}_bev.png"
    fig.savefig(bev_path, dpi=120, pad_inches=0)
    plt.close(fig)
    return bev_path
