# HSGM-style structured BEV VLM branch

Branch: `feat/hsgm-structured-bev-vlm`

This branch keeps SCOPE's TSDF integration, frontier extraction, potential
estimation, memory snapshots, and low-level navigation unchanged.  It changes
only the high-level decision context and protocol.

Before each VLM query it writes and supplies two images in
`potential_graph/vlm_bev/`:

1. `*_semantic_bev.png` is the HSGM-style global semantic map. It marks the
   current agent pose and heading, explored and observed traversable space,
   obstacles, history trajectory, observed semantic instances, and the ranked
   candidate frontiers `F1` to `F3`.
2. `*_evidence_gaussian_bev.png` places a Gaussian on every displayed
   candidate. Its center is the SCOPE frontier endpoint; its weight combines
   predicted future evidence with current-subtask relevance; its width is the
   uncertainty proxy derived from the SCOPE frontier prediction.

Candidates are sorted by SCOPE's existing potential score, then by stable
frontier id. The same ordered subset is used in the map, the frontier image
list, and VLM output, so `F1` always refers to the same executable `Frontier`.
The decision map labels target/relevance-ranked instances first and then fills
unused label slots with stable context instances. This preserves useful
relations such as a refrigerator near a cabinet even before the target category
has been observed. `vlm_full_inputs/manifest.json` records the source paths of
both BEV images; their copies are `content_004.png` (semantic) and
`content_006.png` (evidence) in the current prompt ordering.

The VLM must return a JSON decision. Examples:

```json
{"selected_candidate":"F1","decision_type":"explore_frontier","subtask_status":"not_completed","reason":"F1 may reveal bedroom evidence","confidence":"medium"}
```

```json
{"selected_candidate":"object","decision_type":"go_to_memory_node","snapshot_index":0,"object_index":2,"subtask_status":"completed","reason":"The visible object satisfies the subtask","confidence":"high"}
```

`subtask_status` is logged as high-level evidence. Existing SCOPE arrival and
goal-object checks remain the authoritative completion gate, preventing a VLM
claim from completing a task without physical verification.
