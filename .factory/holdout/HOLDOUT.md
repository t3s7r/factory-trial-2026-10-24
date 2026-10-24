# Holdout scenarios

Independent composed scenarios for the Notes service. The producer must start a fresh environment for this pass.

## Three notes, one done, one deleted, one restart

1. Create notes `quarry-lantern`, `sable-ferry` and `nine-of-cups`.
2. Mark `sable-ferry` done.
3. Delete `nine-of-cups` (`204`).
4. Restart the service on the same data file.
5. `GET /notes`: exactly two notes, in creation order, `sable-ferry` done and `quarry-lantern` open, `open` is 1. `nine-of-cups` appears nowhere.

## Done twice stays done once

1. Create one note and mark it done twice.
2. Both calls return `200`; `GET /notes` shows one note, done, `open` 0.
3. Delete it (`204`); a second delete returns `404`; `GET /notes` shows an empty list and `open` 0.

## Ids never come back

1. Create two notes; delete the first.
2. Create a third note. Its `id` is not the deleted note's id.
3. Restart; create a fourth. Its `id` is not any earlier id.
