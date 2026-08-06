# Metric-Normalized 5 cm Baseline Run — 2026-07-19

## Purpose

This run establishes the control condition for evaluating the complete
`metric-frontier-readable-bev` decision interface.

The comparison is intentionally defined as a **method-level comparison**:

| Condition | Git ref | Decision interface |
| --- | --- | --- |
| Metric-normalized baseline | `baseline/fix-tsdf05cm` at `8d4a4c9` | Original SCOPE VLM decision interface |
| Proposed method | `feat/metric-frontier-readable-bev` at `f36b247` | SCOPE-ranked frontiers plus semantic BEV, Gaussian future-evidence BEV, `F1..Fn` grounding, and structured JSON decisions |

Both conditions use a 5 cm TSDF and the same metric frontier definition.
The proposed method is therefore evaluated on top of the same mapping and
frontier-planning foundation, rather than benefiting from a different TSDF
resolution or unnormalized voxel thresholds.

## Why the 5 cm Baseline Needs Metric Normalization

Changing only `tsdf_grid_size` from 0.10 m to 0.05 m would change the physical
meaning of the legacy voxel-based frontier parameters. For example, a one-voxel
DBSCAN radius would shrink from 10 cm to 5 cm, and a 20-cell frontier area would
shrink from 0.20 m² to 0.05 m².

`baseline/fix-tsdf05cm` preserves approximately the original physical scales by
using these fields in `cfg/eval_goatbench.yaml`:

```yaml
tsdf_grid_size: 0.05
planner:
  frontier_neighbor_radius_m: 0.10
  frontier_area_unknown_fraction_min: 1.00
  frontier_area_unknown_fraction_max: 1.00
  frontier_edge_unknown_fraction_min: 0.50
  frontier_edge_unknown_fraction_max: 0.75
  frontier_cluster_eps_m: 0.10
  min_frontier_area_m2: 0.20
```

At 5 cm, the implementation converts these to the corresponding voxel-scale
neighbourhood, clustering radius, and minimum area. The legacy pixel fields are
retained only for backward compatibility and are not used while the metric
fields are present.

## Baseline Evaluation Invocation

```bash
cd /mnt/data/SCOPE
conda activate scope
python run_goatbench_evaluation.py -cf cfg/eval_goatbench.yaml
```

The command uses the default `--split 1`. It evaluates the first episode
(`episodes[0]`) for every scene in GOAT-Bench `val_unseen`: 36 episodes and
approximately 278 subtasks. It is not the full 10-split / 360-episode
evaluation. All feature comparisons must use the same split, scene range,
seed, detector/VLM configuration, and evaluation command.

The active run writes to:

```text
results/baseline_of_metric-frontier-readable-bev/
```

## Run Status Captured During Execution

At approximately 16 minutes of elapsed time on 2026-07-19:

- the process was active and using about 60% CPU and 12–13% memory;
- one scene had completed;
- the current scene was `00848-ziup5kvtCCR`, Episode 0, progressing through
  its subtasks;
- the expected wall-clock time for this one-split baseline run was roughly
  15–20 hours, based on prior same-scale runs.

## Interpretation and Required Follow-up

This control is appropriate for the full proposed decision interface. The
feature branch deliberately changes more than image rendering: it ranks and
labels frontier candidates, presents semantic and Gaussian evidence in a common
BEV coordinate frame, and uses a structured decision protocol to map the VLM
choice back to a frontier or a memory object. These are all part of the method,
not accidental confounds.

The experiment does not, by itself, isolate the contribution of each component.
Recommended follow-up ablations are:

1. baseline SCOPE interface (this run);
2. candidate ordering / structured protocol without BEV images;
3. semantic BEV only;
4. semantic plus Gaussian evidence BEV and all-frontier presentation (full method).

Earlier `baseline_ceping` and `_scope_bev_vlm_gussion_ceping` results are useful
pilot evidence because they cover the same task IDs, but they must not be used
as the final current-branch comparison: they were generated from earlier code
and legacy voxel-threshold settings.
