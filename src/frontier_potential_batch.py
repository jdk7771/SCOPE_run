"""Potential scoring for newly observed frontiers.

The batch mode keeps the baseline's frontier identity and PotentialGraph update
rules, but turns all newly observed frontiers in one navigation step into one
numbered multimodal VLM request.
"""

import logging
import time

import numpy as np

from src.potential_estimation_gpt_goal import (
    get_batch_potential_estimations,
    get_potential_estimation,
)
from src.vlm_timing import record_vlm_stage


def _log_frontier_potential_score(potential_graph, frontier_index, frontier):
    frontier_world_pos = potential_graph._voxel_to_world(frontier.position)
    final_score = potential_graph.get_potential_at_position(
        np.array([frontier_world_pos[0], frontier_world_pos[2]])
    )
    logging.info(
        "Frontier %d final potential score: %.2f", frontier_index, final_score
    )


def update_new_frontier_potentials(
    potential_graph, frontiers, subtask_metadata, cfg
):
    """Score unseen frontiers in batch mode or the legacy serial mode.

    A batch with a malformed/missing result leaves that frontier unanalyzed so
    it is eligible for the next step's batch. It never hides a batch failure by
    falling back to serial calls, which would invalidate the latency ablation.
    """
    if not getattr(cfg, "enable_potential_estimation", True):
        return

    if not hasattr(potential_graph, "_analyzed_frontiers"):
        potential_graph._analyzed_frontiers = set()

    new_frontiers = []
    for frontier_index, frontier in enumerate(frontiers):
        frontier_key = (tuple(frontier.position), frontier.image)
        if frontier_key in potential_graph._analyzed_frontiers:
            continue
        if frontier.feature is not None:
            new_frontiers.append((frontier_index, frontier, frontier_key))

    if not new_frontiers:
        return

    if getattr(cfg, "batch_frontier_potential", False):
        batch_start = time.perf_counter()
        results = get_batch_potential_estimations(
            subtask_metadata,
            [
                (frontier_index, frontier.feature)
                for frontier_index, frontier, _ in new_frontiers
            ],
        )
        stage_elapsed = time.perf_counter() - batch_start
        fully_parsed = results is not None and len(results) == len(new_frontiers)
        record_vlm_stage(
            "frontier_potential_batch_step",
            stage_elapsed,
            item_count=len(new_frontiers),
            success=fully_parsed,
        )
        logging.info(
            "Batch potential step: %d new frontiers, wall time %.3fs, parsed %d/%d",
            len(new_frontiers),
            stage_elapsed,
            0 if results is None else len(results),
            len(new_frontiers),
        )
        if results is None:
            logging.warning(
                "Batch potential request failed; keeping all %d frontiers eligible for retry",
                len(new_frontiers),
            )
            return

        for frontier_index, frontier, frontier_key in new_frontiers:
            potential_text = results.get(frontier_index)
            if potential_text is None:
                logging.warning(
                    "No valid batch potential result for frontier %d; keeping it eligible for retry",
                    frontier_index,
                )
                continue
            logging.info(
                "Frontier %d batch potential estimation: %s",
                frontier_index,
                potential_text,
            )
            potential_graph.update_from_frontier(
                frontier=frontier,
                subtask_metadata=subtask_metadata,
                occupied_map=None,
                potential_text=potential_text,
            )
            potential_graph._analyzed_frontiers.add(frontier_key)
            _log_frontier_potential_score(potential_graph, frontier_index, frontier)
        return

    # Legacy ablation: preserve the original one-frontier-per-request behavior.
    serial_start = time.perf_counter()
    for frontier_index, frontier, frontier_key in new_frontiers:
        try:
            potential_text = get_potential_estimation(subtask_metadata, frontier.feature)
            logging.info(
                "Frontier %d potential estimation: %s", frontier_index, potential_text
            )
            potential_graph.update_from_frontier(
                frontier=frontier,
                subtask_metadata=subtask_metadata,
                occupied_map=None,
                potential_text=potential_text,
            )
            potential_graph._analyzed_frontiers.add(frontier_key)
            _log_frontier_potential_score(potential_graph, frontier_index, frontier)
        except Exception as error:
            logging.warning(
                "Failed to get potential estimation for frontier %d: %s",
                frontier_index,
                error,
            )
            potential_graph.update_from_frontier(
                frontier=frontier,
                subtask_metadata=subtask_metadata,
                occupied_map=None,
                potential_text=None,
            )
    record_vlm_stage(
        "frontier_potential_serial_step",
        time.perf_counter() - serial_start,
        item_count=len(new_frontiers),
        success=all(
            frontier_key in potential_graph._analyzed_frontiers
            for _, _, frontier_key in new_frontiers
        ),
    )
