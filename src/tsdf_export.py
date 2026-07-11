"""Persistence helpers for inspecting SCOPE's live TSDF planner state."""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
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


def _draw_object_instances(
    ax,
    planner,
    objects,
    scale,
    min_detections,
    relevant_classes=None,
    max_labeled_instances=10,
    show_irrelevant_outlines=False,
):
    """Draw task-relevant object footprints and optional context outlines.

    ``relevant_classes`` preserves the VLM prefilter ranking. Instances from
    those classes are shown first; remaining label slots are filled by the
    most stable other instances. If fewer than ``max_labeled_instances`` are
    available, every stable instance is shown.
    """
    if not objects:
        return 0

    cmap = plt.colormaps.get_cmap("tab20")
    ranked_classes = list(dict.fromkeys(relevant_classes or []))
    if relevant_classes is None:
        relevant_class_rank = None  # Preserve the legacy all-instance view.
    else:
        relevant_class_rank = {class_name: rank for rank, class_name in enumerate(ranked_classes)}

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
        # Relevant categories follow the VLM order. Non-relevant instances then
        # backfill unused slots by detection stability, so sparse early maps do
        # not look empty just because the VLM returned few categories.
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

    limit = max(0, int(max_labeled_instances))
    labeled_candidates = candidates if limit == 0 else candidates[:limit]
    labeled_ids = {obj_id for obj_id, *_ in labeled_candidates}

    count = 0
    for obj_id, obj, footprint, class_name, class_rank in candidates:
        is_labeled = obj_id in labeled_ids
        if not is_labeled and not show_irrelevant_outlines:
            continue

        # Matplotlib image axes are (x=voxel-y, y=voxel-x), matching SCOPE's
        # planner visualization convention.
        polygon_xy = np.column_stack((footprint[:, 1] * scale, footprint[:, 0] * scale))
        if not is_labeled:
            ax.add_patch(
                Polygon(
                    polygon_xy,
                    closed=True,
                    facecolor="none",
                    edgecolor="#6f6f6f",
                    linewidth=0.7,
                    alpha=0.60,
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
                edgecolor="black",
                linewidth=1.2,
                alpha=0.58,
                zorder=5,
            )
        )
        center = polygon_xy.mean(axis=0)
        rank_prefix = "" if class_rank is None else f"R#{class_rank + 1} "
        ax.text(
            center[0],
            center[1],
            f"{rank_prefix}{obj_id}: {class_name}",
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
    ax.text(xy[0, 0], xy[0, 1], " S", color="#1f77b4", fontsize=7, va="bottom", zorder=10)

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


def _build_planner_bev(planner, display_height):
    """Build the same 2D state map used by TSDFPlanner.agent_step()."""
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
    obstacle_slice = obstacle[:, :, height_index]
    kernel_size = max(1, int(0.3 / planner._voxel_size))
    obstacle_neighborhood = ndimage.convolve(
        obstacle_slice.astype(float),
        np.ones((kernel_size, kernel_size)),
        mode="constant",
        cval=0.0,
    )

    bev = np.full((*unoccupied.shape, 3), 255, dtype=np.uint8)
    bev[unoccupied] = (200, 200, 200)
    bev[explored & unoccupied] = (194, 246, 198)
    bev[
        (obstacle_neighborhood > 0)
        & (obstacle_neighborhood < kernel_size**2 / 2)
    ] = (100, 100, 100)
    bev[obstacle_neighborhood >= kernel_size**2 / 2] = (0, 0, 0)
    return bev, unoccupied


def _prediction_weight_and_sigma(scores, min_sigma_m, max_sigma_m):
    """Map VLM evidence scores to Gaussian strength and uncertainty width."""
    evidence = np.array(
        [
            scores.get("potential_score", 3.0),
            scores.get("semantic_richness", 3.0),
            scores.get("explorability", 3.0),
        ],
        dtype=float,
    )
    evidence = np.clip(evidence, 1.0, 5.0)
    relevance = float(np.clip(scores.get("goal_relevance", 3.0), 1.0, 5.0))
    evidence_strength = np.average(evidence, weights=[0.5, 0.3, 0.2]) / 5.0
    weight = evidence_strength * (relevance / 5.0)

    # The VLM provides categorical evidence rather than calibrated variance.
    # Treat low evidence and disagreement among diagnostics as higher uncertainty.
    disagreement = np.std(np.append(evidence, relevance)) / 2.0
    uncertainty = np.clip(0.5 * (1.0 - evidence_strength) + 0.5 * disagreement, 0.0, 1.0)
    sigma_m = min_sigma_m + uncertainty * (max_sigma_m - min_sigma_m)
    return float(weight), float(sigma_m)


def save_frontier_gaussian_bev(
    planner,
    output_dir,
    name,
    candidates,
    trajectory_voxels=None,
    display_height=1.8,
    min_sigma_m=0.5,
    max_sigma_m=2.0,
):
    """Save candidate frontier evidence as Gaussians over the planner BEV.

    ``candidates`` contains ``position`` in planner voxel coordinates and
    direct VLM ``scores``. Gaussian intensity is future-evidence strength
    multiplied by current-subtask relevance; width is an uncertainty proxy.
    """
    if not candidates:
        return None

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    bev, traversable = _build_planner_bev(planner, display_height)
    # Preserve SCOPE's state semantics beneath the score field: unexplored
    # free space is gray, explored free space is green, and obstacles are
    # black.  A blank white score canvas hides this navigation context.
    score_base = bev.copy()
    x_grid, y_grid = np.ogrid[: bev.shape[0], : bev.shape[1]]
    field = np.zeros(bev.shape[:2], dtype=np.float32)
    candidate_info = []

    for index, candidate in enumerate(candidates):
        position = np.asarray(candidate["position"], dtype=float)
        scores = candidate["scores"]
        weight, sigma_m = _prediction_weight_and_sigma(
            scores, min_sigma_m, max_sigma_m
        )
        sigma_vox = max(sigma_m / planner._voxel_size, 1e-6)
        squared_distance = (x_grid - position[0]) ** 2 + (y_grid - position[1]) ** 2
        field += weight * np.exp(-squared_distance / (2.0 * sigma_vox**2))
        candidate_info.append((position, weight, sigma_m, index))

    # A constant alpha would tint the entire explored region dark: even the
    # very small tails of a 0.5--2 m Gaussian receive the darkest magma
    # colour.  Reveal the neutral map below weak evidence and make opacity
    # increase with the normalized evidence instead.
    peak_field = float(field.max())
    normalized_field = field / peak_field if peak_field > 0 else field
    evidence_cutoff = 0.08
    visible_field = np.ma.masked_where(
        (normalized_field < evidence_cutoff) | ~traversable, field
    )
    heat_alpha = 0.82 * np.clip(
        (normalized_field - evidence_cutoff) / (1.0 - evidence_cutoff), 0.0, 1.0
    ) ** 0.65
    heat_alpha[~traversable] = 0.0
    fig, ax = plt.subplots(
        figsize=(max(8, bev.shape[1] / 120), max(8, bev.shape[0] / 120)),
        dpi=120,
    )
    ax.imshow(score_base, interpolation="nearest")
    # Darker red means stronger evidence. The gray/green base map remains the
    # sole encoding of exploration state, while weak evidence is transparent.
    reds = plt.colormaps.get_cmap("Reds")
    evidence_cmap = LinearSegmentedColormap.from_list(
        "evidence_reds", reds(np.linspace(0.35, 1.0, 256))
    )
    heat = ax.imshow(
        visible_field,
        cmap=evidence_cmap,
        alpha=heat_alpha,
        interpolation="bilinear",
        zorder=4,
    )
    _draw_trajectory(ax, trajectory_voxels, 1, 1)

    for position, weight, sigma_m, index in candidate_info:
        ax.scatter(
            position[1], position[0], s=64, c="white", edgecolors="black", linewidths=1.2, zorder=8
        )
        ax.text(
            position[1] + 2,
            position[0] - 2,
            f"F{index}: w={weight:.2f}, σ={sigma_m:.1f}m",
            fontsize=7,
            color="black",
            bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.85},
            zorder=9,
        )

    ax.set_title("Frontier future-evidence field", fontsize=10)
    ax.set_axis_off()
    colorbar = fig.colorbar(heat, ax=ax, fraction=0.046, pad=0.02)
    colorbar.set_label("weighted future evidence (<8% peak: transparent)", fontsize=8)
    output_path = output_dir / f"{name}_gaussian_bev.png"
    fig.savefig(output_path, dpi=120, bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return output_path


def save_bev_visualization(
    planner,
    output_dir,
    name,
    trajectory_voxels=None,
    objects=None,
    render_resolution=0.025,
    min_object_detections=2,
    trajectory_arrow_stride=1,
    relevant_classes=None,
    max_labeled_instances=10,
    show_irrelevant_outlines=False,
    display_height=1.8,
):
    """Save a semantic, high-resolution BEV image.

    ``render_resolution`` only controls output pixels and overlays; it does not
    change the planner's TSDF voxel size or invent additional geometry detail.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    bev, _ = _build_planner_bev(planner, display_height)

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
        ax,
        planner,
        objects,
        upsample,
        int(min_object_detections),
        relevant_classes=relevant_classes,
        max_labeled_instances=max_labeled_instances,
        show_irrelevant_outlines=show_irrelevant_outlines,
    )
    bev_path = output_dir / f"{name}_bev.png"
    fig.savefig(bev_path, dpi=120, bbox_inches="tight", pad_inches=0)
    plt.close(fig)

    return bev_path
