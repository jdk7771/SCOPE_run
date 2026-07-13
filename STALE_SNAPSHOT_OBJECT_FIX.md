# Stale snapshot object-ID fix

## Problem

Object denoising and merging can remove an object while a `SnapShot.cluster`
still holds its original ID.  The planner later indexed `objects[obj_id]` when
choosing or visualizing a snapshot, which could terminate evaluation with a
`KeyError` (for example, object ID `281`).

## Change

`src/tsdf_planner.py` now filters snapshot cluster IDs against the current
`objects` map before using them.

- Snapshot visualizations skip stale IDs and continue running.
- A snapshot whose entire cluster is stale is skipped during visualization.
- A newly selected target snapshot with no live objects is rejected safely,
  allowing the planner to choose another target.

This makes object-map cleanup non-fatal while preserving all live objects in
each snapshot cluster.
