# Text to CAD: from a sentence to a printed part

How a request typed in chat ("make a clip that holds this hose to the wall") becomes a part on the
Core One's bed, and who decides what along the way. Written 2026-09-23 as the one-page overview for
people and agents new to this repo.

> **This page explains. It does not set rules.** The process is owned by [`workflow.md`](workflow.md),
> the hard rules by [`AGENTS.md`](../AGENTS.md) and [`platform/AGENTS.md`](../platform/AGENTS.md),
> and what a gate does *today* by the code: `platform/pipeline/gates.py list` and
> `platform/pipeline/next_action.py <part-or-plate>`. Where this page disagrees with any of them,
> they win. Fix this page.

## The premise

A language model cannot reliably turn a prompt into a part that fits. Everything measured here says
so. Frontier models get the shape roughly right and the numbers wrong. Five local models at q4 did not pass a single L-bracket, and all of them made the same
coordinate-frame mistake. So "text to CAD" here does not mean a model that emits a mesh. It means:

1. the model writes **parametric CadQuery code**, not geometry;
2. it **looks at renders of its own real export** and corrects itself;
3. a machine-checkable **spec** says what the numbers must be and where each one came from;
4. **deterministic gates** block on exact facts and only warn on heuristics;
5. a **human** approves every upload and every physical verdict.

One rule governs the whole AI layer: **a model may propose and critique. It may never attest.**
Nothing a model writes marks a dimension measured, passes a gate, or types an approval.

## The whole flow

```text
 "make me a ..."  + photo · measurements · the object itself
        │
 ⓪ INTAKE ......... look at the real thing · search what is already qualified ·
        │            compute the requirement · draw the options if there is a fork
 ① SPEC ........... spec.yaml: critical numbers + where each came from · fits · probes · joints
        │
 ② DIGITAL LOOP ... generator → build → render → verify → you point at "F16" → refine
        │            (seconds to minutes; loop until green)
 ③ WHAT TO PRINT .. unknown number → gauge · risky fit → coupon · simple and known → whole part
        │
 ④ PREPARE ........ slice → verify-slice → supports + islands → handoff → STOP
        │
 ⑤ APPROVE ........ you review the plate and type APPROVED=1; only then does it upload
        │
 ⑥ PRINT + MEASURE  you print, measure and record; the agent diagnoses   (hours)
        │
 ⑦ EXIT ........... change ONE thing → back to ② · release (CONFIRMED=1) · or stop and log why
```

Two loops, one cheap and one expensive. The discipline is to settle geometry in the cheap loop and
to spend the expensive one only on what a print alone can answer: does it fit, does it survive.

## Who does what

| Stage | You (the human) | The agent | Deterministic tools |
|---|---|---|---|
| Intake + spec | the request, the stakes, photos, measurements, the object | research, reference hunting, option sheets, the spec draft | provenance gate on the spec |
| Digital loop | pick a direction; point at labelled faces | write and run the generator, render, present | build, render, `verify` |
| Print | review the handoff, **type `APPROVED=1`**, print, measure | slice, check, assemble the handoff, then **stop** | `verify-slice`, `handoff.sh`, `send.sh` refusals |
| Result | observations, readings, attestation, **type `CONFIRMED=1`** | diagnose the delta, propose the next single change | `qualification_check.py` |

`APPROVED=1` and `CONFIRMED=1` are the two human-only switches. An agent never sets either one. That
holds even when you said "let's print it" earlier and even when the brief obviously ends in a print.

## ⓪ Intake: turning a sentence into a brief

The brief answers: what is it, where does it live or mate, what matters (fit, function, looks), and
**how bad is it if it is wrong**. The stakes decide how many gates the part stops at. A desk clip and
a load-bearing bracket run the same spine, but the clip breezes through while the bracket stops at
every gate ([workflow.md → Stakes-scaled rigor](workflow.md)).

The front end forks on origin:

- **Generative** (an idea): prose → spec → CadQuery.
- **Reverse-engineer** (an existing object): scan or photogrammetry → mesh → CAD. Calipers
  *verify* worn freeform geometry; they don't capture it (`platform/pipeline/scan-process/`, still a
  stub here; the car-parts venture carries this path).

Habits that have saved the most rework at this stage:

- **Look before you model a real object.** Prose gives provenance, never form. Fetch the photo and
  trace the whole outline from it. Reference images go in `photoref/` (kept untracked/local).
- **Search what is already qualified.** A printed joint (dovetail, key, ratchet, waves) probably
  exists as a numbered sample in `parts/_lib/joints.py` (mirror: [`joinery.md`](joinery.md)).
  Threaded or load-bearing joints start from [`fasteners.md`](fasteners.md).
- **Compute the requirement before choosing the mechanism.** "Grips tightly" is not a spec. One line
  of arithmetic settles which mechanisms can work.
- **Draw the options when there is a real fork.** If there is no geometry yet, present a drawn sheet
  with to-scale sections and let you answer by label. Once you pick, build it. A third options
  document reads as stalling.
- **Advisory AI intake.** `platform/ai/vision_intake.py` can draft a feature list from a photo, but
  every number it extracts stays `estimated`.

## ① Spec: the contract

Start a revision and a part folder:

```bash
platform/bench.sh start <slug>                 # rev/<slug>; if the tree is dirty with someone
                                               # else's work: git switch -c rev/<slug> in place
cp -r parts/_TEMPLATE parts/<category>/<name>  # then register it in parts/index.yaml
```

`spec.yaml` is what `verify` and the handoff check against. The parts that matter most:

| Field | What it carries |
|---|---|
| `part_id`, `handle`, `components` | the name ([`naming.md`](naming.md)): `category/[qualifier-]thing`, a short chat handle, named regions |
| `design.mode` | `restore` (from an identified source part) or `originate` (new intent) |
| `dimensions` | nominal, tolerance, and **provenance**: `measured`, `standard`, `estimated` or `placeholder`. A fit-critical number must be measured or standard, or the handoff refuses. |
| `reference` per dimension | `replicate` / `deviate` / `originate`, which decides how a region is checked |
| `probes` | exact assertions on the final STEP: this box must be solid, this one empty |
| `fits`, `joints`, `fasteners`, `bom` | mates, qualified joint samples by number, hardware |
| `slice` | print orientation, support policy, cylindrical keep-outs support may not enter |

The template's defaults **fail on purpose**, so a copied spec cannot reach a handoff until someone
answers for its numbers. If a dimension resists calipers, **print a gauge** (a sweep comb, a combined
apparatus, a registration gauge) to turn `estimated` into `measured`. Don't guess a part.

## ② The fast digital loop

This is where most of the work happens, and it is nearly free.

```bash
platform/pipeline/generate/build.sh parts/<cat>/<name>/src/<name>.py <outdir>   # → STL + STEP
platform/pipeline/preview/render.sh <part.stl> <outdir>                         # → 5 views + labelled drawings
platform/pipeline/verify/verify.sh parts/<cat>/<name>                           # → PASS / FAIL vs spec.yaml
```

- **The generator** is plain CadQuery in `src/`, run with `~/cadquery-env/bin/python`. Start from
  [`platform/codegen-templates/`](../platform/codegen-templates/README.md), which holds explicit datum
  planes, safe booleans, clean lofts, and pinned fonts. Retrieval (`platform/ai/retrieve.py`) suggests
  a proven pattern. Qualified joints are imported from the registry and never re-typed. Good
  generators assert their own invariants and refuse to export while `spec.yaml` disagrees.
- **Render** produces five stamped views (`iso · iso_back · top · front · back`) plus three
  **labelled drawings** whose face ids (`F16 round r3.20`) are read off the STEP. The views are stamped
  with the geometry's id, so a picture can't be passed off as a different version.
- **Present labelled, not bare.** You reply "F16 is too shallow", and an edge is "the edge between F07
  and F12". Never "the front left bit above the peg", because that sentence is a guess the next
  revision acts on.
  On organic figures, where face labels drown, components are lettered on a render instead.
- **Verify** splits by evidence class. Exact B-rep facts (valid STEP, closed solids, no bad faces),
  spec dimensions and declared probes **block**. Mesh heuristics and DFM (wall thickness, overhang)
  only **warn**. A part with no STEP is **unproven**, not passed.
- **Probe the solid for anything internal.** A clean render and a green verify once hid a "2 mm
  wall" that measured 0.50 mm at one end and 9.75 mm at the other. Cut a thin slab and read the spans.
- **Kernel dead ends.** When OCC refuses a fillet or boolean, look up the correct formulation
  (see [`platform/codegen-templates/README.md`](../platform/codegen-templates/README.md)). Never
  simplify the geometry to make the error go away.
  After repeated dead ends, an independent model reviews the spec, the mesh and the failure log. It
  checks a different invariant and does not invent dimensions.
- **Green:** `platform/bench.sh save "<note>"` checkpoints, and `bench.sh green "<note>"` pins the
  digital loop as green. Then comes the stakes-scaled feasibility check: should this be FDM at all,
  in what material, at what orientation?

## ③ Deciding what to print

| Situation | Print |
|---|---|
| a critical number is still unknown | a **measurement gauge**: it repairs the spec, it doesn't qualify a fit |
| fit-critical, long, or threaded/load-bearing | a **test coupon**: just the mating features, one question per coupon |
| small, low-risk, fully specified | the whole part |

Never spend a multi-hour print to learn that a fit is wrong. Every printed part carries its variant
key **debossed on the bed face**, so a pile of prints traces back to source.

## ④ Prepare and hand off

A part carries a `prepare.yaml` recipe: what kind of print this is, the one question it answers, the
stop condition, the plate path, and the slicer arguments. The coordinator runs every existing stage
and stops when the plate is ready:

```bash
platform/pipeline/prepare/prepare.sh --root "$PWD" parts/<cat>/<name>/prepare.yaml --preflight
platform/pipeline/prepare/prepare.sh --root "$PWD" parts/<cat>/<name>/prepare.yaml
```

Behind that: build (with producer evidence) → verify → render → **`slice.sh`** (headless PrusaSlicer,
HF0.4 profile triple by default, no brim unless there is evidence) → **`verify-slice.sh`** → support
plot → **`handoff.sh`**. `READY` means present the plate and **stop** ([`preparation.md`](preparation.md)).

What gets checked before you see it:

- **verify-slice** blocks on deterministic facts: bed fit, slicer exit, bad or stale G-code, missing
  or stale profile identity. It warns on mesh heuristics.
- **Supports:** `plot-supports.py` draws support against the model even when support is zero. A
  support-free claim needs `verify/island_check.py` on the G-code. Support style is settled by how it
  comes off in a real print, not by the slicer's numbers.
- **Multi-part plates:** the PrusaSlicer CLI silently slices only the last STL. `slice.sh` pre-merges
  with `arrange.py`, and the handoff prints part count next to weight so a collapse shows.
- **`handoff.sh`** derives every part from the plate itself. It refuses on stale geometry (10),
  spec-truth failures such as unsourced numbers (12), a model with no spec (13), a missing or stale
  B-rep verdict (14), incomplete
  qualification intent (15), an unbound manifest (16), or a failed slice gate (17).
  `gates.py exit <N>` explains any code.

**The handoff presents files, it doesn't summarize them.** Every path goes in front of you:
`plate.3mf` (open it in PrusaSlicer), `plate_1.gcode` with time and grams, the five previews,
`supports.png`, the labelled drawings, a geometry diff against the last physically proven version,
`slice_meta.json`, the explicitly *not-evaluated* `qualification_manifest.json`, and the source
`.stl` in case you want to re-slice by hand. Artifact table: [workflow.md → The handoff](workflow.md).

## ⑤ Approve and send

```bash
APPROVED=1 platform/pipeline/send/send.sh [--start] [--name <plate>.gcode] build/<...>/plate_1.gcode
```

Only you type this. **Send means upload**, not just start, because a staged plate is one tap from
running. `send.sh` refuses without the handoff (exit 8), without `APPROVED=1` (exit 9), and over the
file of an active job (exit 6). Give multi-plate uploads distinct `--name`s, since every plate is
`plate_1.gcode` locally. Default printer transport is PrusaLink (configured via `$PRUSALINK_ENV`,
see [`platform/pipeline/README.md`](../platform/pipeline/README.md)).

## ⑥ Print, measure, record

```bash
python3 platform/pipeline/verify/qualification_check.py init \
  --manifest build/<plate>/qualification_manifest.json --part parts/<cat>/<name> \
  --id YYYY-MM-DD-i1 --kind coupon --objective "the one question this print answers" \
  --output parts/<cat>/<name>/qa/iterations/YYYY-MM-DD-i1.yaml
```

The machine writes a `planned` record bound to the exact bytes that were printed, with every physical
field left empty. You fill in the real machine, spool, lot, environment, repeated readings, fit and
function observations, and your attestation. Then come the physical gates, which no digital check
replaces:

- **reality gate:** does it fit the *actual* mate?
- **functional gate** (when the stakes call for it): does it survive the real job?
- **fastener gate** (when there is hardware): real hardware, real access, real torque.

Caliper numbers compound. Freeform feedback ("base too tight") still works but can't be reused.
Reusable observations go to `research/results/measurements.csv`. When a symptom is physical and the
G-code is stock, check the machine: the artifacts describe what was *commanded*, never what the
hardware did (a loose nozzle screw once passed a full config investigation).

## ⑦ Exit

- **Revise:** the agent diagnoses the delta and changes **one** thing in spec or source, then back to ②.
- **Release:** `qualification.current` names the passing record for the current model bytes, and you
  pin it with `CONFIRMED=1 platform/bench.sh passed "<note>" <qa-record>`. Then
  `bench.sh land -m "<message>"` squashes the revision onto `main`, which only ever holds what was
  good on the bench.
- **Stop or escalate:** after N laps without convergence, or when code-CAD or FDM is the wrong tool,
  log the outcome honestly and hand it to a human decision. **A logged failure is a valid ending.**

`bench.sh back` lists every physically proven version and brings one back. Source is what merges;
geometry is always regenerated, never merged ([`versioning.md`](versioning.md)).

## Where AI is used, and where it is kept out

| Allowed: propose and critique | Not allowed: attest |
|---|---|
| draft a spec, a generator, a gauge, a measurement plan | set `provenance: measured` |
| retrieve a proven template (`platform/ai/retrieve.py`) | mark any gate passed |
| read renders and kernel numbers and flag suspects (one diagnosis-only pass) | promote an estimate to a fact |
| one bounded repair attempt, re-checked by the unchanged gates | type `APPROVED=1` or `CONFIRMED=1` |

Models are auditioned against incident-derived, executable benchmarks (`platform/ai/benchmark.py`)
and selected on reviewed accuracy, per role. A winner in one role gets no authority in another.
Datasets carry licence tiers, and non-commercial data never enters a production corpus because a
sibling venture sells parts. Details: [`ai-cad-skill-book.md`](ai-cad-skill-book.md),
[`llm-in-the-loop-plan.md`](llm-in-the-loop-plan.md), [`platform/ai/README.md`](../platform/ai/README.md).

## Asking the tree

Answer questions about state from the code and artifacts, not from prose (including this page):

```bash
platform/pipeline/next_action.py <part-or-plate>   # state, blockers, next legal action, with citations
platform/pipeline/gates.py list                    # every gate, what passes, what blocks
platform/pipeline/gates.py exit 14                 # what an exit code means
cat build/<plate>/gates.*.jsonl                    # the verdict of every gate a stage consulted
```

## Where things live

| Path | What |
|---|---|
| `parts/<category>/<name>/` | one part: `src/` generator, `step/` + `stl/` exports, `preview/`, `qa/`, `spec.yaml`, `prepare.yaml`, `README.md` |
| `parts/_TEMPLATE/` | the starting spec and recipe, with failing defaults |
| `parts/_lib/` | shared: joint registry + builders, probes, fit-core, debossed labels |
| `build/<category>/<part>/<plate>/` | one plate: G-code, `.3mf`, previews, reports, manifests |
| `platform/pipeline/` | the stages: `generate/ preview/ verify/ slice/ handoff/ send/ prepare/` |
| `platform/codegen-templates/` | proven CadQuery idioms and the traps they encode |
| `platform/ai/` | advisory retrieval, benchmarks, critique/repair, vision intake |
| `platform/bench.sh` | revision branches and the `green`/`passed` tags |
| `slicer-profiles/PrusaSlicer/` | project print/filament presets |
| `photoref/`, `vendor/` | reference images; third-party models and scans (foreign IP, kept apart) |
| `research/results/measurements.csv` | the append-only physical observation log |

**Toolchain** (declared in `platform/toolchain.lock`, checked by `platform/pipeline/toolchain.sh`):
CadQuery 2.8.0 on OCP 7.9.3.1 in `~/cadquery-env`, PrusaSlicer 2.9.6 (flatpak; it can't read
`/tmp`, so slices go under `build/`), OpenSCAD, FreeCAD (face labels), Blender (figure renders).
Printer: Prusa Core One with the HF0.4 nozzle, driven over PrusaLink.

**Rules that stop an agent** (full text in [`AGENTS.md`](../AGENTS.md)): all work happens in this
checkout, never in a sibling copy or worktree. Geometry changes go on a `rev/` branch, while prose goes
straight to `main`. Run `platform/pipeline/test.sh` before committing. Never auto-send.

## A worked example

`decor/beaver-pen-rest`, 2026-09-23. The request was one paragraph: a low-poly cartoon beaver holding
a fountain pen, a nod to the LSE mascot, with a decent universal pen fit.

- **Intake:** LSE's history set the pose and the motto on the plinth. Your reference photo later
  corrected the pose twice, because the model kept a sitting beaver that "looks more like a bear."
- **Spec and generator:** the pen fit was *proved, not guessed*. The generator checks against the
  final solid that 9–18 mm pens sit clear across both paws and lift out, prints those checks as spec
  probes, and refuses to export while the spec disagrees. The low-poly style is exact planar B-rep
  from convex hulls.
- **Loop:** each revision started from a sentence of yours ("the knees go into the middle of the
  feet"), with components lettered on the review page because face labels drown on a figure. The gates caught the agent's own mistakes, such as
  floating ears (three solids), a toe past the plinth edge, and a probe box straddling a designed gap.
- **Prepare:** every body, face and teeth plate ended READY, zero support, island-checked, and then
  **stopped** for approval. Colour came from push-in pieces rather than a filament change.

## Further reading

| Topic | Reference |
|---|---|
| The process, authoritative | [`workflow.md`](workflow.md) |
| Preparation and source identity | [`preparation.md`](preparation.md) |
| Physical evidence and release | [`versioning.md`](versioning.md) |
| Slicing, supports, PrusaLink | [`platform/pipeline/README.md`](../platform/pipeline/README.md) |
| Joints, fasteners, supports | [`joinery.md`](joinery.md), [`fasteners.md`](fasteners.md) |
| Platform vs consumer repos | [`consumer-contract.md`](consumer-contract.md) |
