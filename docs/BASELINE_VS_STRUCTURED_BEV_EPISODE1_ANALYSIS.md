# Baseline vs. structured-BEV VLM: single-episode analysis

## Scope and reproducibility

This comparison uses the same GOAT-Bench scene and episode in both result directories.

| Run | Branch | Result directory | Scene / episode | Subtasks |
| --- | --- | --- | --- | --- |
| Baseline | `fix/stale-snapshot-object-ids` | `results/episode1_baseline_time` | `00848-ziup5kvtCCR_ep_0` | 9 |
| Structured BEV | `feat/hsgm-structured-bev-vlm` | `results/episode1_scope_bev` | `00848-ziup5kvtCCR_ep_0` | 9 |

Both runs completed and used the local `gemma3:27b` VLM service. This is one episode only, so it is diagnostic evidence, not a statistically reliable benchmark conclusion.

## What changed relative to baseline

The structured-BEV branch **does not replace SCOPE's mapper or local navigation with HSGM**. It still uses SCOPE's TSDF map, SCOPE frontier scoring/planning, and SCOPE lower-level execution. “HSGM-style” describes the visualization and VLM input representation only.

| Area | Baseline | Structured-BEV branch |
| --- | --- | --- |
| Mapping / local navigation | SCOPE TSDF and SCOPE planner | Still SCOPE TSDF and SCOPE planner |
| Semantic map supplied to VLM | No top-down semantic BEV | Structured semantic BEV: agent pose/heading, explored/observed regions, trajectory, F1/F2/F3, and selected semantic labels |
| Unobserved-space evidence | No BEV evidence field | Gaussian evidence BEV centered at each candidate frontier; SCOPE future-evidence/relevance is its weight and uncertainty controls width |
| Frontier presentation | Frontier thumbnails and SCOPE scores | Same SCOPE score ordering, with F1/F2/F3 rendered consistently on maps and in the prompt |
| VLM decision contract | Text choice parsed by SCOPE | Explicit JSON: candidate/object choice, decision type, subtask status, reason, confidence |
| Traceability / timing | Standard run log | Full input bundles include both BEV paths; `vlm_timing.json` records every API attempt |

Important confound: the structured-BEV run used `tsdf_grid_size: 0.05`; baseline used `0.1`. This measures the combined effect of structured BEV/prompt changes and a finer TSDF grid, not a pure BEV-only ablation.

## Navigation outcomes

| Metric | Baseline | Structured BEV | Difference |
| --- | ---: | ---: | ---: |
| Snapshot success | 11.11% (1/9) | 11.11% (1/9) | 0.00 pp |
| Snapshot SPL | 9.17% | 9.63% | +0.46 pp |
| Distance success | 33.33% (3/9) | 44.44% (4/9) | +11.11 pp |
| Distance SPL | 31.39% | 39.86% | +8.47 pp |
| Wall-clock runtime | 19:29 | 33:25 | +13:56 |

For this episode, structured BEV reaches one additional target viewpoint and has higher distance SPL. Strict snapshot correctness is tied at one subtask each, and the successful subtask is not the same one. This supports a different, and on distance metrics better, trajectory for this episode; it does not establish a general semantic-object-selection improvement.

## Why the structured-BEV run takes longer

The two BEV images are included in the same final decision request; they do **not** create two extra VLM requests per decision. The main cause is more high-level replanning events.

`choose_every_step: true` is enabled in both runs. A high-level event is approximately identified by one `prefilter` request: after the robot moves to a local target and updates observations/map, it asks again whether to go to a snapshot or which frontier to explore.

| VLM call type | Baseline | Structured BEV | Interpretation |
| --- | ---: | ---: | --- |
| `prefilter` | 11 | 24 | About 24 vs. 11 high-level decision events |
| `decision` | 36 | 75 | Final-choice attempts, including retries |
| `self_refine` | 27 | 25 | Snapshot-validation calls; not the source of the increase |
| `frontier_potential` | 22 | 36 | More newly evaluated frontiers |
| **Total API requests** | **96** | **160** | **+64 requests** |

The final-choice-attempt ratio is similar: baseline `36 / 11 = 3.27`, structured BEV `75 / 24 = 3.13` attempts per high-level event. There is therefore no evidence that the JSON contract creates extra malformed-output retries. The larger count comes from more decision/replanning events, consistent with more snapshots (20.67 vs. 15.56) and frames (77.44 vs. 72.11) per subtask. The finer TSDF grid can also change frontier geometry and routes.

Grid size is map resolution, not physical movement stride. The planner's local target distance is controlled separately; however, a finer map can still create a different sequence of frontiers and re-plans.

## Why individual VLM responses are faster but the run is slower

| Call type | Structured BEV mean | Baseline mean | Delta |
| --- | ---: | ---: | ---: |
| All successful requests | 7.286 s (160) | 8.443 s (96) | -1.157 s |
| `decision` | 10.781 s (75) | 15.330 s (36) | -4.548 s |
| `frontier_potential` | 5.764 s (36) | 5.811 s (22) | -0.047 s |
| `prefilter` | 2.017 s (24) | 2.063 s (11) | -0.046 s |
| `self_refine` | 4.051 s (25) | 4.004 s (27) | +0.047 s |

The structured-BEV prompt requests compact JSON, while baseline frequently generates a longer natural-language choice/explanation. Shorter generated output is a plausible reason for lower mean `decision` latency on the local VLM service. It is not proof that BEV images make inference faster: service load/cache, different snapshot sets, and output length also affect latency.

Despite faster individual responses, structured BEV spends more aggregate VLM time because it makes more calls:

- Baseline VLM request time: about 810.5 s (13:31).
- Structured-BEV VLM request time: about 1165.8 s (19:26).

The remaining wall-clock increase comes from additional observation, detection, point-cloud/TSDF update, frontier evaluation, and visualization work associated with more replanning cycles.

## Recommended controlled next experiment

Run all 36 scenes' episode 1 with identical `tsdf_grid_size` (first use 0.1), planner/detector/extra-view/visualization/VLM settings, separate fresh output directories, and the same VLM service state as far as practical. Compare the generated `vlm_timing.json` files with `scripts/compare_vlm_timing.py`. Only then should aggregate success/SPL, total runtime, decision-event count, and per-call latency support a BEV design decision.
