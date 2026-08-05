# Batch frontier-potential scoring (5 cm baseline)

Branch: `feat/batch-frontier-potential-scoring`  
Base: `baseline/fix-tsdf05cm` (`tsdf_grid_size: 0.05`)

## What changes

The legacy baseline sends one potential-scoring VLM request for each newly
analysed frontier in a navigation step:

```text
task + F_0 image -> F_0 scores
task + F_1 image -> F_1 scores
task + F_2 image -> F_2 scores
```

With `batch_frontier_potential: true`, the branch sends one request per step:

```text
task + optional goal image + F_0 image + F_1 image + F_2 image
-> JSON scores for F_0, F_1, and F_2
```

The `F_i` labels are local to that one request and always run from `F_0` to
`F_{n-1}`, even if the planner's current frontier indices are sparse. The
implementation maps these local labels back to the original planner frontiers
after parsing, which prevents the VLM from returning a natural local label that
would otherwise be mistaken for an unrequested global ID.

The task contains the question, task type, target class, and goal image when
available. The model must return exactly one JSON object with one item for every
numbered frontier:

```json
{
  "frontiers": [
    {
      "id": 0,
      "semantic_richness": "High",
      "explorability": "Medium",
      "goal_relevance": "High",
      "potential_score": 4.2,
      "explanation": "..."
    }
  ]
}
```

The four scores are written back to the existing `PotentialGraph`; the normal
snapshot/frontier decision prompt and the 5 cm frontier-generation code are
unchanged. A malformed or missing item is not silently assigned a score: that
frontier remains eligible for a later batch. A failed batch never falls back to
serial requests, so the experiment measures the batch design cleanly.

Both `run_goatbench_evaluation.py` and `run_goatbench_full_evaluation.py` use
the shared batch implementation.

## Configuration and ablation

`cfg/eval_goatbench.yaml` selects the batch condition by default:

```yaml
exp_name: "baseline_batch_frontier_potential_5cm"
enable_potential_estimation: true
batch_frontier_potential: true
```

For a controlled legacy condition, keep every other setting identical and set:

```yaml
batch_frontier_potential: false
```

Use separate `exp_name` values so results do not overwrite each other. Run both
conditions with the same seed, split, `start_ratio`, `end_ratio`, endpoint, and
model:

```bash
python3 run_goatbench_evaluation.py -cf cfg/eval_goatbench.yaml \
  --start_ratio 0.0 --end_ratio 1.0 --split 1
```

## Latency outputs

`results/<exp_name>/vlm_timing.json` now contains two complementary measures:

- `summary.by_call_type.frontier_potential_batch`: individual batch API attempt
  time. As with existing measurements, this excludes retry sleep and local work.
- `stage_summary.frontier_potential_batch_step`: end-to-end wall time per step,
  including prompt/image assembly, all retries and waits, request time, and JSON
  parsing. It also reports the total number of frontiers sent.
- `stage_summary.frontier_potential_serial_step`: the corresponding end-to-end
  wall time when `batch_frontier_potential: false`.

For the latency result, report batch request count, mean API time, mean step
wall time, total frontiers scored, and total evaluation wall time. Compare these
alongside the normal GOAT-Bench output metrics from the two matched runs.
