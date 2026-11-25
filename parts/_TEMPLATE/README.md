# <Part Title>

**part_id:** `<category>/<name>`  ·  **status:** `draft`
> status: draft → printed → dim-verified → released

One-line description: what it is, what it mates with.

**Design path:** `restore` (identified source part, with replicate/deviate declarations) or
`originate` (new geometry constrained by interfaces/standards). Record the purpose and stable
reference evidence in `spec.yaml`; scans/photos establish shape, not fit authority.

## Fit-critical
The dimensions/fits that matter (the rest is cosmetic). Full targets in [`spec.yaml`](spec.yaml).
- e.g. outer 75.0 across flats (±0.2) slides onto the K1C boss; slip fit ~0.3 mm/side.

## This folder
- `src/` — parametric source (the single source of truth).
- `step/` — STEP master (archival, editable B-rep). **Committed.**
- `stl/` — one released, sliceable STL. **Committed.** (dev renders/scratch are git-ignored)
- `spec.yaml` — machine-checkable targets/tolerances/fits/acceptance.
- `provenance.json` — prompt/model identity, exact tool versions + lock hash, source commit, inputs,
  and artifact/export hashes. Template `null` values mean **unrecorded**, not “use the current
  version”; populate them from the actual build rather than copying a historical tool list.
- `qa/` — one byte-bound structured iteration record per coupon/full print, including failures,
  human physical observations, measured-vs-spec results, actual-mate result, and evidence refs.

## Build
```bash
# author src/ → export step/ + stl/ → verify against spec.yaml → slice → print → fill qa/
```

## Notes
Anything non-obvious: why a second geometry source exists (if any), print orientation,
supports, material choice, known issues.
