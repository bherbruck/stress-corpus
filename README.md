# Stress corpus

10,000 everyday objects, each described in one plain sentence with real millimetre sizes. Build them in SolidCraft and/or Fusion, convert with Dutchman, compare the results, and file every failure where the bug lives. The goal is to find and fix bugs.

Example:

> S0001 · wall bracket · hole pattern · small · easy: A 2 mm stainless steel wall bracket, modelled from a 35 × 24 mm flat sheet. Drill 4 through holes of Ø3 mm in a 2 × 2 grid, 24.5 mm apart in X and 17 mm apart in Y, centred on the top face.

The list is in `items.jsonl` (one JSON line per item: `id, category, features, size, difficulty, brief`). `gen.py` makes it from a fixed seed (category × feature mix × size × difficulty), so anyone can regenerate the exact same file with `python3 gen.py`.

## Take part

1. Open the issues labelled `batch`. Each one is a batch of about 100 items: "Batch 07: S0601–S0700".
2. Claim one by assigning it to yourself. Only collaborators can be assigned, so if you are not one yet, comment "claiming" and a maintainer will assign you.
3. Work through the items and tick each box as you finish it.
4. Close the batch issue when every box is ticked.

## Two ways to build an item

- **SolidCraft:** build the part from the brief in SolidCraft. Note anything it refuses, gets wrong, or cannot do.
- **Fusion, then Dutchman:** build the same part in Fusion, export a STEP file from Fusion, convert the Fusion design with Dutchman, and compare the Dutchman result with Fusion's STEP export.

You can do either or both. Say which in the results.

## Record results

Add a pull request with `results/<batch>.jsonl` (for example `results/batch-07.jsonl`). One line per item and pipeline:

```json
{"id": "S0601", "pipeline": "solidcraft", "outcome": "built", "link": ""}
{"id": "S0602", "pipeline": "fusion-dutchman", "outcome": "failed", "link": "https://github.com/dutchman-cad/dutchman/issues/123"}
```

- `pipeline`: `solidcraft` or `fusion-dutchman`
- `outcome`: `built`, `failed`, or `skipped`
- `link`: the issue or PR for a failure, empty otherwise

## File failures

File every failure as its own issue in the repo where the bug lives, and put the item ID (for example `S0602`) in the title:

- SolidCraft could not build it or built it wrong: `tangency-labs/solidcraft`
- Dutchman converted it wrongly: `dutchman-cad/dutchman`
- The file reader or writer is at fault: `cadmpeg/cadmpeg`

Before you file, search that repo for an existing issue about the same problem (search the symptom and the feature name). If one exists, comment on it with the item ID instead of opening a new one.

## Fusion files stay private

Never upload Fusion designs, exports, or screenshots of them, here or anywhere public. SolidCraft's rule is that nothing is taken from commercial CAD. If a failure needs a repro for SolidCraft, rebuild it from scratch in SolidCraft as a small synthetic file and attach that.

## Licence

Apache-2.0, see `LICENSE`.
