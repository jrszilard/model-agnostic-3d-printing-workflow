# AI-CAD skill book — cooperative, replication, and new-part authoring

This is the technique layer for improving AI-assisted CAD without weakening the approval gates.
It is not a model wish list. It turns the platform's proven source, probes, retrieval, benchmark,
and review artifacts into one repeatable authoring routine.

## The operating rule

An AI may propose and critique; it may **not** attest. A model is useful when it helps select a
testable pattern or spots a discrepancy. A dimension, material choice, fit confirmation, or
approval becomes authority only through measured evidence and human review.

Use AI where it shortens the fast digital loop:

1. classify the subject and evidence;
2. retrieve a proven pattern;
3. write parametric CadQuery with explicit datums and invariant probes;
4. compare against reference/previews/benchmarks;
5. run the normal verify, handoff, physical gates.

## Evidence and route

Before authoring, make the relationship explicit:

- `replicate` — must match a physical/reference target; overlay, scan underlay, and discrepancy are
  relevant only to that region.
- `deviate` — deliberately different for FDM/material/service reasons; assert intent, do not let a
  generic discrepancy check call it an error.
- `originate` — new geometry with no target; benchmark, probes, labeled views, and physical gates
  carry the proof.

For replicas, use feature-driven metrology first, Stage-A overlays where a physical reference
exists, and job-gated scan underlays only for freeform geometry. For new work, use the same
structure without pretending an original exists.

## Authoring habits that save the most revisions

1. **Start from the proven template, not a blank file.** `platform/codegen-templates/` carries the
   paid-for idioms: explicit datum planes, safe booleans, clean transition lofts, matching relief,
   fit-core, and pinned text.
2. **Retrieve before inventing.** Build/query `platform/ai/index_cadquery.py` and
   `platform/ai/retrieve.py`; default indexing excludes generated AI output, experiment controls,
   and AI tests. Explicit corpus rows need pinned permissive provenance plus local validation;
   research-only indexes are marked and refused by the normal retriever.
3. **Name datums and dimensions before code.** Weak coordinate frames are the recurring AI-CAD
   failure: features should be placed from explicit origins, planes, and measured values, not from
   whichever face happens to be topmost.
4. **Keep geometric complexity.** When OCC refuses a fillet, boolean, or loft, look up the correct
   formulation or escalate; do not simplify the requirement merely to suppress a traceback.
5. **Keep one geometry source and probe the final solid.** A generator that re-reads derived
   geometry, merges meshes, or silently drops a feature must fail on an exact invariant, not pass
   because it is manifold.
6. **Present labelled geometry for revision.** Labelled drawings plus exact probes turn prose
   feedback into an unambiguous parameter change.

## Review loop for replication and creation

- Overlay/scan comparison: inspect only `replicate` regions; render deliberate deviations as
  expected rather than error.
- Feature checks: prefer exact probes such as volume, bbox, circular radii, ordered point-inside
  samples, and final-solid ROI comparisons.
- The AI benchmark (`platform/ai/benchmark.py`) may score candidates on those exact checks. It is
  a model gate, never part acceptance.
- A critique model reads the unchanged task, source, and deterministic report and receives one
  diagnosis-only pass. It may recommend a repair but cannot edit, weaken checks, attest, or approve.
  `platform/ai/critique_benchmark.py` scores both required concepts and task-derived factual
  invariants; keyword recall alone once let a critic invent x=50 while sounding complete.
- A repair model receives at most one attempt under `platform/ai/repair_benchmark.py`; its returned
  code goes through the unchanged sandbox checks and remains unpromoted. A failure is evidence for
  the next prompt/template revision, not permission for an automatic loop.

## Using models without importing bad geometry

Models/datasets are advisory assets. Obey the licence tier before retrieval, evaluation, or
training. Open-source strong candidates remain candidates until their actual part passes the same
local task and verification.

Good assignments:

- vision intake: enumerate visible features, missing views, interfaces, and what must be measured;
  dimensions remain estimated;
- retrieval: suggest a template or query term;
- one-pass critique: flag why a rendered region or kernel scalar suspect;
- benchmark repair: use model-generated local code as a candidate to execute and compare.

Bad assignments:

- invent hidden dimensions;
- approve a CAD output as fit/print-ready;
- copy non-commercial generated geometry into production source;
- route around exact probes, fit-core identity, or handoff approval.

## Improvement loop

1. Preserve the failure as a task in `platform/ai/data/benchmarks.yaml`, with executable geometry
   expectations rather than prose only.
2. Pull the correct template into `platform/codegen-templates/`.
3. Rebuild the retrieval index; verify the intended template ranks for the incident query.
4. Keep platform tests green; review the adoption counters so new machinery is actually used.
5. Only then audition a model against the measured task. Remove models that cannot beat retrieval
   or one useful critique pass on the same evidence.
6. Compare role-specific results with `platform/ai/compare_results.py`. Review accuracy and false
   relationships directly; do not substitute correction timing or independent keyword counts for
   correctness. A winner in one role does not become authority in another.
7. Fine-tune only when a held-out failure remains after structured intent, validated retrieval, and
   one bounded deterministic repair. Passing the best retrieval condition is evidence *against*
   fine-tuning, even when weaker prompt conditions still fail.

## Current pain points this book addresses

- `faces(">Z")` drift — use explicit datum planes.
- Even/odd overlap voids — explicit solids and unions.
- Constant cutter on a taper — match relief to the same profile.
- Missing hook/feature after a final boolean — final-solid feature presence probes.
- Random local-model geometric drift — benchmark against incident-derived tasks before trusting.
- Retrieval echoing the benchmark itself — the indexer excludes those toy files deliberately.
- Vision intake pretending to measure — capture role and estimated provenance are explicit.
