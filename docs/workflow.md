# Workflow — idea → part (generic)

**Date:** 2026-07-07 · **Status:** approved, stress-tested by LLM council (`docs/council/`).
The end-to-end human+AI loop for producing **any** accurate, well-fitting 3D-printed part on this
platform — a bracket, a clip, a replacement knob, an enclosure, a fixture, a car part. It is
**domain-neutral**: consumer repositories (for example, a product line or personal parts bench)
*consume* this workflow and layer their own domain policies on top (see [`consumer-contract.md`](consumer-contract.md)).

## If a request has more than one plausible meaning

First try to answer from the actual artifacts. If “yesterday's second plate” describes two versions, don't choose by date or by which slice passed. Name the versions by their contents and ask, e.g. **“Add those three guides to the original plate, or print only the three ends?”** Before changing CAD or slicing, establish the base version, what stays, what changes (IDs and quantities), and the deliverable. Don't ask again for facts already in the brief or manifest. Record an explicit hold on any affected existing packet, not on unrelated work. The [provider-neutral start card](../platform/pipeline/AGENT-START.md) gives the commands and the rule for resuming after the answer.

## The mental model: two loops
- **Fast digital loop** (seconds–minutes, nearly free): design → preview → verify. Refine here freely.
- **Slow physical loop** (hours, expensive): print → measure → check → refine → reprint.

Two governing rules:
1. **Push the right decisions left** — resolve geometry and digital errors in CAD; resolve empirical
   fit with a small physical experiment. Do not spend an open-ended digital loop trying to predict
   what the coupon exists to measure. Minimize time/material to useful evidence, not print count.
2. **Fit-test before commitment** — for anything fit-critical or long, print a small **test coupon**
   (just the mating ends) before the full part. Never risk a multi-hour print to learn a fit is wrong.

## Forward-only improvement boundary

The goal is to make the **next print and the next design revision** more accurate—not to launch a
project that repairs every historical print, QA note, STL, or provenance file.

- Leave archived work as recorded; never invent missing measurements, uncertainty, tool versions,
  approvals, or `passed/*` tags.
- Apply the current contract whenever geometry is newly created, revised, or put on a future plate.
  Reprinting an old file is a future print, so it must pass the current gates at that point; untouched
  archive needs no proactive migration and gets no bypass.
- Feed each new physical result back into the next spec/source revision or a qualified
  printer/material/process sample. A failure preserved only in prose has not improved the workflow.
- Judge improvement prospectively: first-pass coupon/full-part success, number and cause of physical
  loops, time/material spent per accepted design, and recurrence of a known failure class—not the
  percentage of old files backfilled.
- Consumers use this same loop for both **Restore** (replicate/deviate from a measured reference) and
  **Improve/Originate** (new intent constrained by measured interfaces). Consumer-specific donor,
  vehicle, safety, legal, and acceptance evidence stays in the consumer; generic gates and qualified
  process/joint mechanisms flow back to this platform.

## The core discipline: conformance ≠ truth
`verify` proves a part matches **the spec we authored** — not that the spec matches **reality**. That
is a *conformance* check, and on its own it's circular. So the workflow has physical-truth **gates**
that a digital check can't replace:
- a **reality gate** — does it fit the *actual* mate / fill the *actual* space?
- a **functional gate** — does it *survive its job* (load, heat, UV, chemical, fatigue)?
- and it validates the **spec itself** against the real object, not just the model against the spec.

## Stakes-scaled rigor (replaces a rigid "autonomy dial")
How much gating, testing, and human involvement a part gets scales on two axes — set at the brief:

| | **Spec completeness** (how fully is it specified?) | **Stakes** (what happens if it's wrong?) |
|---|---|---|
| **Low** | fuzzy idea, needs feel → human in the loop each pass | cosmetic / loose fit → skip the functional gate |
| **High** | clear dims + refs → AI drives to green, light gates | load / heat / safety → functional gate is mandatory |

A cheap desk clip and an engine bracket run the **same spine** — the clip breezes through the gates,
the bracket stops at each one. Rigor is a property of the *part*, not the *workflow*. A part that
looks simple but hits a judgment call **escalates** (AI stops, pulls in the human) rather than guessing.

## Bench experiment first: a bounded path to evidence

A **detached measurement gauge / bench coupon**, a **fitting prototype**, and a **released part**
share the machine-safety and artifact-identity spine, but have different admission questions:

| Article | Before handoff | What must wait for physical evidence |
|---|---|---|
| Detached bench experiment | One stated question; labelled experimental values; representative local geometry/material/orientation/process; safe off-equipment procedure; current digital gates | The unknown being measured, pilot selection, retention and material qualification |
| Fitting / functional prototype | Applicable measured interfaces, coupon evidence, and domain permission for that use, in addition to digital gates | Service/load/environment acceptance |
| Released part | Applicable fit/function evidence and human release/tag requirements | Nothing may be inferred from a green slice |

This is **scheduling and scope**, not a new schema, gate exemption, or permission to call a fitting
part a coupon. Do not relabel known mating requirements as non-critical to get through verification.
Unknown experiment settings remain explicitly experimental; existing protected interfaces stay frozen.
Hazards of the bench experiment itself still need controls. User-supplied product/material choices
are recorded once, not re-requested each loop. A profile selection is not an actual-spool claim.

For an already bounded bench question, use this operating target (**not a measured SLA**):

1. **First five minutes:** state the question, variable sweep, controls and observation that will
   decide the next step. Check tool/profile availability, platform compatibility, artifact paths and
   the dependency-scoped checkpoint route before expanding CAD. Leave unrelated dirty work in
   place; never stash, reset, stage or opportunistically migrate it for this job.
2. **Aim for a reviewable handoff in 15 minutes.** Reuse an existing generator/library and the
   smallest representative feature. Do not carry the full assembly, new infrastructure, ornamental
   presentation or unrelated research into the critical path. A targeted exact assertion remains
   appropriate; an expanding general-purpose QA project does not.
3. Run the established **build → render → verify → slice → verify-slice → support plot → clean
   checkpoint → handoff** chain. Preserve all required views, reports, probes, process/geometry
   identity and human approval. The support plot is needed even when support extrusion is zero:
   `python3 platform/pipeline/preview/plot-supports.py <out>/plate_1.gcode <out>/supports.png`.
   Consumers use their stage wrappers and the shared plotting utility, not a copied stage.
4. **Stop iterating when the experiment is ready.** Address deterministic failures. Review and
   disclose mesh/DFM warnings once; fix a demonstrated defect affecting safety or the experiment,
   but do not demand a warning-free report or promote every heuristic to a release blocker.
   Re-run affected gates after changes; never reuse stale approval or skip required checks/tests.
5. **At 15 minutes without handoff, report the actual blocker and next action.** Do not silently
   extend the research/refactor loop. A blocked report is not success or permission to print; the
   human chooses whether to spend more time or park the test. Once handoff is ready, present it
   immediately and STOP for exact-plate approval, rather than holding it for a tooling improvement.

Keep the test result lightweight at intake: printed key, actual readings/observations and actual
hardware/material/process context. Accept raw human feedback immediately; structure it into the
existing forward-qualification record afterward without inventing missing fields or a pass.
Full retention/vehicle/release claims remain gated separately. No duplicate coupon ledger is needed.

Track **brief-to-first-handoff time, actual blockers, print time/material, and whether the result
answered the question**. Existing execution benchmarks and test counts do not measure agent lead
time. Automation improvements belong in the platform backlog and must not become prerequisites for
an otherwise ready coupon; consumers own only their domain test scope and evidence.

## Preparation entrypoint (platform 0.5)

For a declared Python/CadQuery part, use the [bounded preparation contract](preparation.md) and
`<part>/prepare.yaml`. Consumers invoke `scripts/platform/prepare.sh <part>/prepare.yaml`; the
platform bench supplies `--root "$PWD"` to `platform/pipeline/prepare/prepare.sh`. `--preflight`
resolves the canonical owner and aggregates missing dependencies, checkpoints, tools and presets
before CAD. A linked worktree is not a physical delivery root.

The coordinator owns every existing stage and required review artifact, including labelled views
and the zero-support plot. Exact producer/dependency/tool/config/output hashes govern reuse;
unrelated part dirt and unrelated HEAD changes do not. A changed generator with yesterday's mesh
is stale even if committed. Required source identity is **part + actual declared dependencies**,
not repository-wide cleanliness. Do not hand-author producer/cache records.

One initial pass plus one explicit changed-input repair; a further pass needs a concrete escalation
reason. Failures remain failures. `READY` presents a fresh handoff and **STOPs before approval or
send**. The machine records stage durations/reuse; the agent still records brief-to-handoff lead
time and whether the next human test answers the question. See the contract for conservative
invalidation and the supported producer/one-primary-model scope.

## The flow
```
 ⓪ BRIEF (you) ── what · where it lives/mates · what matters (fit? function? looks?) · STAKES ·
   │              inputs: dims / photos / SKETCH or BLUEPRINT / the physical object
   │   front-end branches on origin:
   ├── GENERATIVE ........ idea ─────────────► CAD
   └── REVERSE-ENGINEER .. scan/photogrammetry → mesh → CAD   (calipers VERIFY; they don't CAPTURE
   │                                                           worn freeform geometry — scan does)
   ▼
 ① SPEC (you + me) → spec.yaml. 3 required fields: critical dimension(s) · fit type ·
   │                pass criteria ("snaps in? y/n"). AI infers the rest. Ambiguity resolved HERE —
   │                a sketch/blueprint kills it fastest. If prose yields two spatial interpretations,
   │                render a LABELLED ORTHOGRAPHIC PLAN/SECTION (`preview/decision-drawing.sh`,
   │                which names every face off the STEP) and ask against those ids and the datum
   │                axes; perspective is not a coordinate system, and a described area is a guess
   │                the next revision acts on.
   │                Every critical nominal records provenance: measured · standard · estimated ·
   │                placeholder. Fit-critical values block unless measured/standard.
   │                Declare `design.mode: restore|originate`. Restore identifies a source and every
   │                dimension says replicate/deviate/originate; Originate may cite measured
   │                interfaces/standards but no source part. This becomes mandatory when the part
   │                next reaches a plate—archives are not bulk-migrated.
   │                **Dimension resists calipers? PRINT A GAUGE, not a guessed part:** sweep comb
   │                (one unknown), combined apparatus (known feature group), registration gauge
   │                (unknown tie between groups). The gauge converts estimated→measured.
   │                Confirm code-CAD can even express the shape; if organic, use scan-surfacing.
   │                Every part gets a `handle` + `components` list at spec time (see `docs/naming.md`);
   │                refer to parts/components by handle thereafter (chat, commits, files).
   │                **Threaded/load-bearing joint?** Add BOM + `fasteners:` now: method, actual
   │                hardware, assembly access, source assertion, coupon, and physical gate. Choose
   │                from `docs/fasteners.md`; do not let a generic “M3 screw” hide the receiver method.
   │                **Printed joint (dovetail / key / ratchet / waves)?** Cite the SAMPLE NUMBER and
   │                add `joints:` now — `parts/_lib/joints.py` is authoritative, `docs/joinery.md`
   │                is its generated mirror. Build with `parts/_lib/joint_builders.py`: `count` is
   │                the double-vs-triple axis and retention comes attached, so the ridges/waves
   │                cannot be forgotten or re-derived. NEVER re-type a qualified measure into a
   │                generator. A sample is (pattern × context): changing material, printer, or
   │                print orientation re-opens the coupon gate — the gate will say so.
   ▼
 ╔══ ② FAST DIGITAL LOOP (cheap) ═══════════════════════════════╗
 ║  design → preview → PRESENT LABELLED → you point → refine     ║   I drive; you steer
 ║  render.sh emits 5 views AND 3 labelled drawings; PRESENT THE ║
 ║  LABELLED ONES for any revision decision. You reply "F16 is   ║
 ║  too shallow" — never "the front left face above the peg".    ║
 ║  probe the final solid; freeze mating ROIs with fit-core.     ║
 ║  Fastener: assert stack-up/containment; preview real access.  ║
 ║  loop until GREEN                                             ║
 ╚═════════════════════════════╤═══════════════════════════════╝
   ▼
 ②ᵃ TOPOLOGY ESCALATION (only after repeated kernel/model dead ends) — give an independent model
   │   the spec, exported mesh, failure log and frozen mating ROIs. It reviews a DIFFERENT invariant;
   │   it does not invent missing dimensions. Sol→Terra on the wiper blend is the worked example:
   │   transition geometry solved the fillet dead end, then the second model caught grip intrusion.
   ▼
 ②ᵇ FEASIBILITY / MATERIAL GATE (stakes-scaled) — "should this even be FDM, in what material,
   │   at what orientation?" Trivial for cosmetic/fit-only; a real decision for load/heat/UV parts.
   ▼
 ③ PRINT DECISION ── critical nominal still unknown?                 ──► MEASUREMENT GAUGE first
   │                 fit-critical, long, or threaded/load-bearing?    ──► TEST COUPON first
   │                 small & low-risk, fully specified?               ──► print whole part
   │                 (gauge measures; coupon qualifies; neither is a production part)
   ▼
 ╔══ ④ SLOW PHYSICAL LOOP (expensive) ══════════════════════════╗
 ║  slice → verify-slice(gate) → HANDOFF: show files+paths      ║   deterministic (bed-fit/hard exit/bad gcode)
 ║  → exact not-evaluated qualification manifest → human        ║
 ║  approves → send   (handoff.sh + APPROVED=1 are HARD gates   ║   BLOCK; mesh heuristics only WARN
 ║  in send.sh — they block UPLOAD, not just start)              ║
 ║  → init planned qa/iterations record (still no verdict)       ║
 ║  → print (you) → record actual machine/spool/lot/dry state,   ║
 ║    nozzle/layer/plate/environment → measure raw repeats        ║   you print/measure; I diagnose
 ║  → upgrade dimension provenance and rebuild the spec          ║
 ║  → FASTENER GATE (when applicable): install actual hardware; ║
 ║    check access, anti-rotation, clamp, tip relief, splitting, ║
 ║    pull-out, and intended service cycles                       ║
 ║  → REALITY GATE: fit the ACTUAL mate                         ║
 ║  → FUNCTIONAL GATE (if stakes): survive the real application ║
 ║  → human completes the byte-bound iteration + attestation    ║
 ║  → record to results.csv when reusable (context-qualified)   ║
 ║  → I diagnose the delta + record failure class/next change   ║
 ║  → adjust ONE thing in spec/source → back to ②               ║
 ╚═════════════════════════════╤═══════════════════════════════╝
   ▼
 ⑤ EXIT — one of:
   ├─ RELEASE ....... meets fit AND function → `qualification.current` names the exact passing
   │                  record for current model bytes → commit evidence · human pins it with
   │                  `CONFIRMED=1 bench.sh passed ... <qa-record>` → status: released · finalize
   │                  provenance · qualified generic observations → research/results
   └─ STOP / ESCALATE  after N laps without convergence and the targeted second-model review, OR
                       a "can't be AI'd" judgment (code-CAD cannot express it, or FDM is inherently
                       wrong) → STOP. Log the outcome
                       (fit-but-broke / can't-AI) honestly and hand to a human decision: scan-surface,
                       change material, make it a casting/machining pattern, or abandon.
                       **A logged failure is a valid terminal state**, not a loop that runs forever.
```

## Presenting geometry for a revision decision (REQUIRED)

Whenever I show you geometry and ask what to change, I present the **labelled** drawings, not the
bare renders. `preview/render.sh` emits both, so there is nothing extra to run:

```
<part>/preview/<stem>_{top,front,side}_labelled.png   the drawings you look at
<part>/preview/<stem>.labelmap.json                   id -> kind, area, radius, centroid, normal
```

Every callout is a real face read off the STEP — `F16` is one surface, with a type (flat / round /
taper / curve), a size and a position. You reply **"F16 is too shallow"** and I go straight to that
surface. The alternative — "the front left face, slightly above the peg" — is a sentence I have to
guess at, and the next revision acts on my guess. Resolving that ambiguity is the single largest
measured gain in the 2026 text-to-CAD literature (Pro-CAD, arXiv:2602.03045: 1–2 clarifying
questions took mean Chamfer 7.80 → 0.63), and a label removes the need to ask at all.

Referring to an **edge**: name the two faces that meet at it — "the edge between F07 and F12". The
labelmap carries both centroids and normals, and the STEP holds the shared edge as a real entity,
so that resolves exactly.

Ids are sorted geometrically, not by export order, so they survive a rebuild of unchanged geometry.
Each face also carries a `fingerprint`, so if a revision moved things I can tell you "what you
called F07 is now F09" rather than silently answering about the wrong surface.

Parts with no STEP (OpenSCAD-only, or no parametric source) cannot be labelled this way — for those,
hand-authored callouts via `plan-drawing.py --annotations` are still the fallback.

### A coded parts map for a part under fit iterations (REQUIRED)

F-ids name single faces, and they renumber when a revision moves geometry. A part that goes round
the fit loop with you (print it, fit it, say what holds it up, print the next) also needs names for
**areas**: the inner wall, the notch over the rib, the corner block. For such a part I keep a
**parts map**: one picture rendered from the CAD in which every area has a short code (`T1` top
cover, `Q5` front wall, `W1` inner wall, `N4` the notch through it ...), coloured the same on every
view, with a one-line legend for each code, in the human's own words where given. The pattern came
from multi-iteration fit parts (e.g., an adjuster-bolt or coat-hook parts map script writing
`docs/<part>-parts-map.png`) where unlabelled areas made revision feedback ambiguous.

1. **The colours come from the CAD.** A `classify(points)` function sorts each point on the part into
   its area by the CAD module's own numbers (first matching rule wins); every view is rendered from
   the solid and coloured by it, so a colour edge is where the area ends. Nothing is drawn by hand.
   The mirror's map has five views (as you hold it, underneath, from one end, a cut through the
   feature that matters, a plan from below) and a small one as printed, on its props. Hold the part
   the way you hold it, and name the sides by what you can see (the tab-mark edge, the H side).
2. **Regenerate it with every iteration**, in the same commit as the CAD, and send it with every
   handoff next to the labelled previews. Its heading reads the version from the CAD (`STEM`), so a
   stale copy cannot pass for the new one.
3. **Ask and answer by code.** Questions name codes ("does N4 clear the ridge?"); so do your replies
   ("N4 needs 1.5 more"). A new feature with no code gets one in the same commit. A feature that goes
   away or merges into another keeps its code in the legend, marked ("G2 groove fill (removed)", "L1
   front L (now W1)"), so an older reply still reads.
4. **You will still point by shape, or at a spot on a preview.** Find it on the CAD first; to find
   "the L shape we see from the bottom", render the underside coloured by height. A point read off a
   plate preview is in **plate** coordinates: take off that copy's place on the plate before naming
   the area (on the mirror plate the second adapter sits at x 30, so x 40 is the part's x 10, the
   inner wall's outer face). A projection shows the lowest point along a whole wall, so answer with
   a **cut through the spot** you pointed at, your point marked, the version you saw beside the new
   one, and a **ruler in mm** wherever an extent is the question, so your reply can be a number.
5. **Each revision's change drawing** (the mirror's `docs/fa16-inner-wall-2026-10-17.png`) loads the
   previous version and its parts map from the commit they were sent from (`git show
   <commit>:<path>`), so it keeps showing what you saw after the source moves on; check that it still
   regenerates pixel for pixel.

## The mechanism sheet: compute it and say it before drawing it (REQUIRED)

For anything that clips, slides, hangs, flexes or carries a load. Of the twenty-six print round trips between
2026-10-09 and 2026-11-11, about nine came from physics nobody had computed first and about seven from an assumption
about how the part is used (counted by hand from the session notes). Both are caught at the spec, in minutes.

**Before CAD**, one line for each of these, with a number and the limit it is held to. They live in the generator as
`mech.require(...)` lines (`parts/_lib/mech.py`), so they print with every build and refuse when a change breaks one:

| Line | What it asks | The print that proved the need |
|---|---|---|
| The job | what it must do, with its number (holds a 60 g box upside down; slides 157 mm) | |
| Held by | a catch, a clamp or friction. A part that hangs needs a catch under a face that points down | TR8 i1: "none will hold upside down" |
| Load and margin | strain, stress or sag at the weak section against its limit, with the support condition | the lane cover's 4 mm sag; TR8 i3's tabs "permanetly bent" |
| Play times lever | the room of every sliding fit, times what reaches out from it | TR11 i2: 0.35 of room dropped an arm's end 5.0 |
| The way in and out | the path, the side the hand comes from once it is mounted, what must come out first | TM1's magnets jammed 1 mm short; TR9's bolt behind a wall |
| As printed | the pose; faces built by layers; anything under 0.34 wide; anything that starts in mid-air | lp-i6's lips sliced at 0.20 of 0.35 |
| Each fit number's source | a registry sample, a coupon or a measurement, in THIS material and socket direction | tr6-i1: PLA's numbers, all too tight in PETG |
| The one unknown | the single question this print answers | SC1 bundled a look test into a fit coupon |

**In the generator**, the matching checks come from the shared library, not from a new function per part:
`motion.sweep` (the way in), `motion.must_stop` (the fall), `motion.free_turn` (the rock), `probe_fast.cut` (a cut that
bites), sections through `checks.run`, and the part's negative controls in `qa/negatives.py`. The pattern is
`platform/codegen-templates/cadquery-mechanism-checks.py`; what has held and what to try is in the knowledge base,
`shared/stack-references/fdm-design-techniques.md`, by what the part must do.

**At every handoff**, three to five lines headed **How you'll use it**: how it goes on, how it is worked, how it comes
off and what stays loose, in the order a hand does them, each naming the side the hand comes from. They are there to be
contradicted before the print: "the magnets must lift out", "it will be against a wall" and "the lens is too small to
handle" each cost a print because the opposite assumption was never put in front of Justin.

**With the handoff of a build whose pieces move against each other**, a **working model**: one page where every
piece sits where the CAD puts it, each moving piece goes through its steps the way the CAD moves it, and the distance
between the pieces that must stay apart is the kernel's own at every step (`platform/pipeline/working-model/`; the
part describes its build in `docs/working_model.py`, and it takes about half a minute to make). Justin, 2026-11-11:
*"a working dynamic ... model for complex builds to illustrate how all the pieces work together and that will hopefully
make testing and refining the parts improved"*. Before the print it is where "that arm will meet that pad" gets said
about a model instead of a part; after a test, a reply can name a piece by its code and a point by its coordinates
("CA at x 104"). It is a picture and a ruler: it quotes the build's checks and approves nothing. A whole build gets
one too (first: the straight touge road, `parts/decor/touge-road/docs/working_model.py`): a control can ride on
another (the latch bolt on the road that lifts off its wall plate), a control stops where two pieces would meet (a
locked bolt stops the road lifting), and Play takes the build apart in its real order and puts it back.

## The handoff — present files + locations before "approve" (REQUIRED, ENFORCED)
`verify-slice` runs the *machine* checks; the *human* approves the **send**. Between them is an
explicit **handoff**, and it is a required step — never jump from "sliced" straight to "send?". For
every plate, before asking for approval, I present the review artifacts **with their paths** so you can
open and inspect them. Builds land in `build/<name>/`:

> **THE GATE COVERS UPLOAD, NOT JUST START — AND IT IS MECHANICAL.**
> Run `platform/pipeline/handoff/handoff.sh <outdir> [<part_dir>]`; it checks every review artifact
> exists, prints them with paths, and writes `handoff.txt`. `send.sh` **hard-refuses** without that
> file (exit 8) and again without an explicit `APPROVED=1` (exit 9). It also *reports* a plate whose
> profiles assume a different nozzle than the fitted one — see *The fitted nozzle is a bench fact*.
>
> **"I'll just stage it" is not a safe half-step.** A staged plate is one tap on the printer's screen
> from running, so uploading before the human has seen the geometry defeats the gate entirely. This
> was written as prose first and got rationalised away exactly that way on 2026-07-20 — a plate went
> to the printer before the preview was shown. `APPROVED=1` must be typed by a human; it is never
> inferred from "they said print it earlier" or from a brief that anticipates printing.

| Artifact | Path | What it's for |
|---|---|---|
| **PrusaSlicer project** | `build/<name>/plate.3mf` | the primary review file — `prusa-slicer <path>` to inspect the arranged plate, layers, supports |
| G-code | `build/<name>/plate_1.gcode` | what actually ships to the Core One (I also quote est. time + filament g) |
| Previews | `build/<name>/*_{iso,iso_back,top,front,back}.png` | quick visual without opening the GUI. FIVE views: iso/top/front cannot show a back face, and a mirrored deboss label shipped that way once (`7a9f08c`) |
| **Supports** | `build/<name>/supports.png` | FRONT/SIDE/TOP of **support vs model** + support-% of extrusion, via `preview/plot-supports.py` on the gcode — so the *supports* are visible for review, not just the model (the model preview can't show them) |
| **Decision drawing** | `<part>/preview/*_labelled.png` · `*.labelmap.json` · `.stamp` | labelled orthographic real-mesh drawing. REQUIRED when approval/placement depends on named edges, faces, handedness or a datum. **Generate with `preview/decision-drawing.sh <part_dir>`** — it reads the STEP, names every notable face (`F07 round r3.20`) and feeds `plan-drawing.py`. The labels exist so the REPLY is unambiguous: say "F12 is too shallow", not "the curved bit near the top on the left". `plan-drawing.py --annotations` still takes hand-written callouts for anything the face map cannot express. |
| **Parts map** (a part in fit iterations) | `<part>/docs/*parts-map.png` (from the part's `parts_map_drawing.py`) | every area coded from the CAD and regenerated with each iteration, so a question and its answer name codes ("N4 needs 1.5 more"), not shapes. REQUIRED for a part going round the fit loop with you: see "A coded parts map for a part under fit iterations" |
| **How you'll use it** (a mechanism) | in the handoff message | three to five lines: how it goes on, is worked and comes off, and from which side, so a wrong assumption is seen before the print. REQUIRED for anything that clips, slides, hangs, flexes or carries a load: see "The mechanism sheet" |
| **Working model** (pieces that move against each other) | the artifact page | every piece in place, each mover through its steps, the gap between the pieces that must stay apart at every step, the build's check lines |
| **Section** (internal mechanisms) | `build/<name>/*-section.png` | a thin-slab cut through the feature axis. REQUIRED whenever the part's mechanism is internal (a compliant pocket, a captured spring, a blind joint): iso/top/front structurally *cannot* show it, and a spring-panel coupon reached this gate three times on renders that hid a wall varying 0.50→9.75 mm. Cut a ~1 mm slab from the STEP, render it `--projection=ortho` |
| **Geometry diff** | `build/<name>/diff_<part>.txt` · `diff_<part>_was_{iso,front}.png` | what changed vs the newest `passed/*` tag — facets, volume, area, bbox, centroid. Informational, never a block. Catches `MOVED, not reshaped`: a translated solid is identical on every metric a render can show, which is how a 9.4 mm misalignment reaches a plate |
| **Version stamp** | `build/<name>/plate_geom.txt` · `gcode_manifest.json` · `<part>/preview/*.stamp` | geom ids bind preview↔plate; final gcode sha binds post-hooks↔verify↔handoff↔send. `handoff.sh` refuses stale geometry (exit 10), unresolved spec/primary/fit-core/probe identity (exit 12), a part on the plate with no `spec.yaml` (exit 13, escape `NO_SPEC_OK=1` which is recorded into `handoff.txt`), an absent/stale exact B-rep verdict (exit 14, no bypass), incomplete forward qualification intent/status (exit 15), or a non-PASS deterministic slice verdict (exit 17, no bypass). **The part dirs are DERIVED from `plate_geom.txt`, not passed in.** |
| **Print-process identity** | `build/<name>/slice_meta.json` | selected machine/process/filament names, rotations, overrides, post-hook hashes, slicer identity from G-code, and SHA-256 of the complete effective config embedded by PrusaSlicer. This identifies the process; it does not qualify it. `verify-slice` blocks missing/stale metadata. |
| **Physical-loop bridge** | `build/<name>/qualification_manifest.json` | machine-generated, explicitly **NOT EVALUATED** binding of a clean repository commit (including shared dependencies), spec, verify verdict, model geom/SHA, G-code SHA, profile/config identity, and plate estimates. `send.sh` requires the exact manifest from the human handoff. It contains no reading, verdict, approval, or operator claim. |
| Verdict + report | `build/<name>/verify_slice.txt` · `verify_report.txt` | machine PASS/FAIL + mesh/slicer/post-hook/gcode/support checks and CAD/spec-truth/fit-core report. |

Rule: **the handoff is presenting these files, not summarizing them.** Approval happens after you've had
the paths in hand; nothing is **uploaded or** started until then. Print orientation is set with `slice.sh --rotate-x/-y/-z`
(PrusaSlicer takes these natively — the old baked-in `…-print.stl` workaround was for OrcaSlicer, which
segfaulted on `--rotate-x`); note any non-flat orientation in the handoff so it isn't a surprise.

**Plate inventory:** capture the intended piece IDs and quantities before slicing. At handoff show `plate-inventory.json` **requested / in 3MF / in G-code** alongside time and grams. The [inventory gate](../platform/pipeline/README.md#requested-versus-sliced-inventory) refuses a missing, extra, substituted or unidentifiable piece; the number of input files and the total weight cannot establish what is on a merged plate. Usable pieces off the bed remain a separate human observation.

**Part marking (REQUIRED):** every printed part carries its variant key **debossed on the bed face**.
For a top-down print, mirror the bed-face label so it reads correctly when the printed part is
flipped over. Use explicit English glyphs; on transparent TPU, prefer a high-contrast geometric
stroke label over a shallow decorative font recess.
(via `parts/_lib/deboss.py`) — the same key as the generator's `VARIANTS` entry and the STL filename
segment. A pile of prints is identifiable at a glance, and any print traces back to its exact source.
Where space permits, the physically qualified baseline is 6mm bold text with a true 1mm recess
(`legible_deboss`); smaller labels require evidence. Inspect actual readability at the reality gate.

**Build tree:** `build/` mirrors the part hierarchy: single-part plates in
`build/<category>/<part-id>/<slug>/`, multi-part plates in `build/plates/<slug>/`. A support-only
slice experiment keeps the same parent plate and nests under `support-variants/<strategy>/` with a
README recording its settings/result/status; it is not a new part revision or an upload candidate.
Never a flat dump.

**TPU 95A process gate (added from SUNLU/Core One coupon evidence):** a named-spool product range
is not a qualified process. Disable mid-print retraction until feed stability is proven; then only
introduce 0.4–0.8 mm as an isolated change. Use a release layer on smooth/satin sheets (glue stick
or Kapton); textured powder-coated sheet is the no-separator alternative. Do not inherit rigid
process first-layer speeds: SUNLU TPU 95A's first-layer qualification starts at 15 mm/s, 215°C,
60°C bed, chamber target off, and first layers fan-off. For fit-critical flexible pockets, relieve
internal edges as well as corners while preserving the nominal flat grip faces.

### Brims are an exception, not a default

**Never add a brim unless it is genuinely necessary for this plate.** Justin's explicit feedback
(2026-09-16): FC8 printed well, but routinely added brims are difficult to remove and usually
unnecessary. This applies to **all parts**, not just broad/flat ones.

- **Default explicitly to `slice.sh --brim 0`** and include `--brim`, `'0'` in new preparation
  recipes. Check the effective sliced config has `brim_type=no_brim` and `brim_width=0`; omitting
  the option can inherit a preset or copied recipe. The generic template and examples use zero.
- **Necessity requires specific evidence**, such as observed lifting/warping on the relevant setup
  or documented contact-area/process constraints making an unbrimmed print unsuitable. “Tall”,
  “ASA”, “just in case”, a historical recipe, or a successful brimmed print alone is not evidence
  that a brim is necessary. Check normal sheet/first-layer setup and a suitable flat orientation
  first; do not use extra adhesion material to hide a correctable setup/design problem.
- **Record and disclose every exception before approval:** why it is necessary, why ordinary
  setup/orientation is insufficient, the smallest justified width, and how it will be removed
  without harming the part or mating edges. If necessity is uncertain, ask rather than silently
  enabling it. Separation tuning is for an already justified brim, not an alternative to omitting
  an unnecessary one. Do not substitute a raft or mouse ears by habit.
- **Handoff includes the adhesion decision:** “no brim (default)” or the evidence-backed exception
  and settings. Inspect support-specific brims/pads separately; model-brim settings do not prove
  that all support bases vanished. Do not disable structurally needed supports to claim no brim.
- **History stays true.** A reused recipe is a new process decision, not permission to retain its
  brim. Preserve sent G-code/3MF/manifest/receipt and the settings actually printed; a future
  no-brim reprint needs its own recipe/output, verification, handoff and fresh approval.

This is an authoring/review requirement, not a newly implemented automatic brim gate. The slicer
wrapper still accepts deliberate overrides; agents must apply this rule explicitly.

### The fitted nozzle is a bench fact, and it is HF0.4 — it always was

**The Core One has run the HF0.4 (high-flow) nozzle throughout.** Justin, 2026-09-21: *"the nozzle
has never been swapped. it has always been the high flow. I only bought the regular .4 and .6 as a
backup."* The repo said both things at once — `slicer-profiles/README.md` had "the nozzle currently
installed" = HF0.4 since 2026-09-17, while the gutter-backstop recipes written a day later say "the
STANDARD 0.4 nozzle". **The recipes were wrong when they were written**, and a later reading of them
turned that into an invented nozzle swap. Read the hardware fact from one place:
`PRUSALINK_NOZZLE` in `$PRUSALINK_ENV` (default `~/.config/3d-printing-workflow/prusalink.env`) — **PrusaLink reports nozzle *diameter*
but never high-flow**, so it cannot be discovered, only recorded.

- **`slice.sh` now defaults to the HF triple** (`Prusa CORE One HF0.4 nozzle` /
  `0.20mm SPEED @COREONE HF0.4` / `Prusament PLA @COREONE HF0.4`). Before 2026-09-21 it defaulted to
  the standard-0.4 triple, so **every plate this pipeline has ever built carried the wrong nozzle's
  recipe** — PETG at 240 °C with a 12 mm³/s cap where the HF preset says 250 °C and 21. That is
  conservative, not dangerous: those plates printed and their physical results stand *as printed*.
  What it cost was speed, not parts.
- **The printer does not enforce the flag.** `M862.1 ... F<0|1>` records which nozzle the plate was
  sliced for, and it is worth reading — but `ladder-i1`, `ladder-i2`, `f1-i1` and `f2-i1` all declare
  `F0`, all printed on this HF0.4 nozzle, and all produced usable results. `send.sh` therefore
  **reports** a mismatch and does not block it. (It was written as a hard refusal first; that would
  have refused those four plates.)
- **What a mismatch actually means:** the plate is carrying the other nozzle's speeds, flow cap and
  temperatures. Decide whether that is what you want before spending the print.
- **The three profile names must agree on high flow.** A `@COREONE 0.4` print or filament preset
  declares `! nozzle_high_flow[0]`; paired with the HF printer profile PrusaSlicer **exits 1 and
  writes no G-code**. Loud and safe. The silent case is `*STRUCTURAL*` presets and this project's TPU
  presets, which carry no high-flow clause at all and slice on either nozzle.
- **HF is hotter and faster, so moving a part onto the HF presets is a material change**, not a
  rename: PETG 240 → 250 °C and 12 → 21 mm³/s, ASA HF 265 not 260. A coupon qualified at the
  standard recipe is not automatically qualified at the HF one — but note the reverse is what has
  been happening, and it has been fine.
- **TPU on HF is proven, not blocked.** Prusa ships no FLEX/TPU preset for any HF nozzle, and
  `TPU_020_SLOW`'s parent is invalid on the HF *printer profile* — but the TPU plates were sliced
  against the standard-0.4 machine profile and **printed on the HF nozzle** (ladder-i2 gave P8). The
  2.5 mm³/s cap binds long before the nozzle does.

### The G-code cannot show you a loose screw

**2026-09-21, the case that produced everything below: the cause was mechanical, and I spent a
session looking for it in the slicer.** A PETG part strung badly and threw big *burnt* globs. I
pulled the plate off the printer, decoded its config, diffed it against the stock preset stack,
re-sliced it to match within 13 seconds, and proved every one of ~370 settings was stock. All true,
and all beside the point. Justin found it: **a thumb screw holding the nozzle was loose at the top,
so filament was not entering straight, was being skimmed as it fed, and the shavings cooked in the
hot zone and came back later as globs and strings.**

**The lesson is about what the artifacts can say.** G-code, `slice_meta.json`, the embedded config,
the preset diff — every one of them describes what was *commanded*. None of them can describe what
the hardware did with the command. So when the symptom is physical and the commands are all stock,
**the machine is the remaining variable, and the next step is hands on the printer, not another
slice.** Three signals I walked past:

1. **The globs were burnt.** Material that dark has been sitting hot *outside* the normal flow path.
   I named that correctly (accumulation vs. leak), and then closed the mechanical thread the moment
   cleaning the nozzle removed the symptom — without asking why material was getting there at all.
2. **The symptom survived the fixes.** Clean nozzle, `avoid_crossing_perimeters` on, retraction up
   50%, still bad. That is the point to stop proposing settings, not to propose more of them.
3. **Burnt material arriving *later* means something upstream is shedding into the melt zone.**
   Stringing does not manufacture its own debris.

What follows is still measured and still true about this part's toolpath — it is an optimisation,
not the fix that was needed. Measured on a GUI-sliced vendor part (PVC rack "Center support", PETG
on HF0.4, stock presets throughout):

- A ribbed/latticed part is ~80 separate extrusion islands per layer: **8,009 retractions and 159 m
  of travel per copy**, 16,000 and 318 m on a two-up plate. Stringing scales with travel **count**,
  and that count is a property of the geometry, not of the spool.
- **The HF recipe raises ooze pressure and leaves retraction alone.** Prusa's HF PETG presets run
  250 °C at 21–22 mm³/s through a longer melt zone, but `filament_retract_length` stays **0.8 mm**,
  exactly the standard nozzle's number. Expect more stringing on HF for the same part.
- **Reduce the retraction COUNT, not the distance.** 0.8 mm is already Prusa's direct-drive number
  (Bowden runs 4–6 mm); there is nowhere to go down, and going there trades straight into more ooze.
  Measured on the same part, one copy:

  | | retraction events | filament pulled | time |
  |---|---:|---:|---:|
  | as printed (stock HF) | 7,790 | 5.8 m | 3h24m49s |
  | `avoid_crossing_perimeters=1`, detour 20 mm | 7,787 | 6.1 m | 3h22m27s |
  | **+ `only_retract_when_crossing_perimeters=1`** | **298** | **0.2 m** | **3h04m55s** |
  | instead, retraction 0.8 → 0.5 mm | 7,787 | 3.8 m | 3h19m06s |

  `avoid_crossing_perimeters` alone is free and moves travels inside the part, but it barely touches
  the count. Adding `only_retract_when_crossing_perimeters` on top takes it down **96%** and saves 18
  minutes, because a travel that stays inside the part can ooze where a later layer covers it.
  **Test it, do not commit blind:** it deliberately allows ooze, and the trade is ~165 m of
  unretracted travel deposited inside the part (order 1% of its volume, buried in infill).
  Shrinking retraction distance instead keeps every cycle and only weakens each one.
- **Check the flow before dropping temperature.** That part's p99 volumetric flow was 16 mm³/s, so
  dropping to 240 °C means cutting perimeter speed too. Worth knowing: this same HF0.4 nozzle has
  printed PETG at **240 °C** (the gutter-backstop feet, on the standard-0.4 presets) with no
  stringing reported — but those are 24-minute coupons with almost no travel, so that is evidence
  the nozzle handles 240, not evidence that 240 fixes a lattice.
- **Rule out the machine before mining the G-code.** The config work below is cheap and worth
  doing, but do it *after* a look at the hotend: fasteners tight, filament path straight, no
  shavings or dust in the gears, nothing welded above the nozzle. A slicer diff cannot see any of it.
- **Diagnosis is cheap and does not need the original project.** Pull the plate off the printer
  (`/api/v1/files/usb`, newest `m_timestamp`), read the config out of the `.bgcode` metadata blocks
  (plain or deflate — `zlib` is enough; the G-code body is heatshrink+MeatPack and is not worth
  decoding), then `--load` that config against the source STL. It reproduced a 6h49m print to 13
  seconds. Diff the effective config against the stock preset stack before blaming hardware or
  filament: on that print, only four of ~370 values differed, and all four were deliberate.

**PrusaSlicer practices (hard-won — full reference in KB wiki `prusaslicer-core-one`):**
- **Brim choice follows the rule above:** explicit no-brim default; necessary exceptions only.
- **Read the support config, not the hope.** `support_material = 1` + `support_material_auto = 0` in the
  gcode header means supports are configured but *never generated* (Prusa's "none"). Check `auto` before
  claiming a plate is supported or not.
- **The auto-support threshold is a surface-angle heuristic, not a layer-overlap model.** On leaning-wall /
  helix geometry it wraps every underside (on the carrier corkscrew: 40% of filament as support, 39m→1h41m).
  Judge by the staircase (`layer_h/tan(angle)` step vs footprint; the study computes it) and by
  **support-removal access** — support packed between the turns of a rigid coil is unreachable, so prefer
  changing geometry (steeper pitch) over accepting trapped support. Leading-edge droop on a self-supporting
  flight is cosmetic; prototype and inspect before paying the support bill.
- **GUI vs headless disagreement is always config, never the slicer** — diff `.overrides.ini` vs the GUI
  profile first (`support_material*`, profile choice). Review the `.3mf` as the config/arrangement source
  of truth and gcode as the immutable machine artifact.
- **Choose support by removal path:** Grid = stable broad support (may leak along walls); Snug = follows
  contours (tall thin pillars less stable); Organic = accessible exterior, low-scar branches — none fixes
  support trapped inside a rigid volume. For one local defect, paint/enforce it instead of auto-supporting
  the whole part. Start top contact Z at 50–75% of layer height; coupon-tune any visible supported face.
- **Support STYLE is settled by a print, not by the slicer's numbers — change it LAST.** Support share,
  mass, time and island counts measure what support costs to *produce*; they say nothing about what it
  costs to get *off*, and removal is what ruins a finished part. On 2026-09-17 every metric favoured grid
  over organic on the same part (2.4% vs 9.5% support, 5 vs 15 mid-air starts) and the physical result was
  the reverse: organic released cleanly, the snug plate's columns were hard to remove. Those metrics are
  still correct for comparing settings *within* one style — they caught a real 4× waste on that part.
  **A support recommendation with no physical result behind it is a hypothesis; say so when presenting it.**
  Trees specifically want a wider stem base than stock: `slice.sh --support=tree` applies
  `raft_first_layer_expansion=7` (stock 3) — with `raft_layers=0` that key expands the first *support*
  layer. Qualified on one ASA part on HF0.4; re-check it elsewhere. See
  `decisions/2026-09-17-support-style-is-decided-by-removal-not-by-metrics` in the knowledge base.
- **A support-free or zero-support claim needs the G-code, and the checker must exclude support's own runs.**
  `platform/pipeline/verify/island_check.py <gcode>` — looks back by a **z window** (PrusaSlicer support
  layers are not synchronised with object layers) and ignores `;TYPE:`-tagged support runs while still
  letting support anchor the model. Counting a tree's own unanchored stems as defects makes every strategy
  look worse the more support it adds, which inverted a recommendation once already. Read the reported
  gaps, not the count: under ~1.5 mm at 0.2 mm layers is an ordinary bridge.
- **Core One uses Pressure Advance, not legacy Linear Advance.** Material tuning belongs in the filament
  preset; global layer/perimeter/infill in the print preset; one local feature gets a modifier or recorded
  `--set`. Never silently poison the global PLA preset to solve one part.
- Slice CLI facts: multi-file input collapses to the last STL (`--merge` segfaults → `arrange.py`); the
  override .ini must live beside the output (flatpak can't read `/tmp`); Core One profiles default to
  binary `.bgcode` (we force ASCII for the verify chain); Prusa writes `;TYPE:Support material`; the start
  gcode purges off-bed by design (the off-bed check whitelists it).

**Probe the solid before you slice an internal mechanism.** `verify` proves conformance to the spec;
it cannot see that a *helper* silently changed meaning. A constant-offset relief cutter written for a
straight envelope, reused behind a tapered one, produced a "2 mm compliant wall" that measured 0.50 mm
at the mouth and 9.75 mm at the floor — and passed mesh, verify-slice, and handoff. Intersect the
exported STEP with a thin probe slab along the feature axis and print the material spans; it is exact,
takes seconds, and belongs in the cheap loop. **A constant offset is only an offset against a parallel
face** — when a face is lofted or tapered, loft its relief from the same profile so they cannot diverge.

## Versioning: where a revision lives before it is good
The loops above assume you can throw a revision away. That is `platform/bench.sh`: geometry work
happens on `rev/<slug>` so `main` stays the last state that was good on the bench, and the two gates
in this document are the two things worth pinning — `green/<slug>-N` when the fast digital loop goes
green (②), `passed/<slug>-N` when the **reality/functional gate** clears (④). `passed` is what
`bench.sh back` offers as the last version that worked, so — like `APPROVED=1` — it is the human's
to type (`CONFIRMED=1`), never an agent's inference. It now requires the committed, current passing
record explicitly: `CONFIRMED=1 bench.sh passed "<note>" <part>/qa/iterations/<id>.yaml`; the tag
stores that path and SHA-256. Full model: `docs/versioning.md`.

## Feedback: data-driven when possible
Give caliper **numbers** and I compute the exact parameter delta *and* add a labeled row to
`results.csv` (nominal / measured / deviation / material / printer / orientation / feature). A
joint coupon also fills the **`sample`** column with its registry sample number, so an
observation joins back to the `parts/_lib/joints.py` row it qualifies — the CSV is the
append-only observation log, the registry is the curated result of deciding what it proved. For a
fastener joint also record hardware/SKU, method, screw length, pocket/pilot, roof/boss, coupon result,
and failure mode. Freeform ("base too tight") still works — I just can't compound it. **Keep this a
rich CSV, not a "library" or a model, until a stable pattern proves out** — FDM error is not a single
scalar (it varies by wall thickness, orientation, feature, plate position, and drifts with
humidity/batch/nozzle wear).

**Your words go in the print's record.** When you say how a print did ("okay 1 is the best, but 2 also works"), I
file exactly that in the iteration record made at its handoff, with when and where you said it
(`qualification_check.py report`; the record's state becomes `reported`). Justin, 2026-11-11, said yes to this: until
then only he could fill a record, and none of the sixty-one was filled. A report is not a verdict: no check is marked,
nothing measured or physical is filled in, no status changes, and `passed` stays his to type.

The prospective ledger is:

```bash
python3 platform/pipeline/verify/qualification_check.py metrics .
```

It reports recorded coupon/full-part states, first-pass full-part success, loops to first pass,
failure-class recurrence, and separate actual vs plate-estimated time/material per accepted design.
Only structurally valid records are counted; contradictions are reported malformed. Zero records
means **no future evidence yet**, not success; plate estimates are not actual consumption and
multi-part plates are not apportioned.

## Platform vs venture (why this stays generic)
This workflow is the **generic engine**. A vertical that sells parts consumes it and adds what's
domain-specific — and those additions must **not** leak back into this doc:

| This workflow (generic platform) | A venture layers on (e.g. car-parts) |
|---|---|
| the two loops, the gates, stakes-scaled rigor | domain functional-test protocols (e.g. engine-bay heat/vibration) |
| spec.yaml · verify · test coupon · results.csv | IP/legal scope policy, customer/price, fulfillment |
| generic reality + functional + exit gates | the sellable catalog, labor economics, marque data |

## Glossary
- **Measurement gauge** — a labelled printed instrument whose purpose is to turn an inaccessible or
  relational unknown into a number (sweep comb, combined apparatus, registration gauge). It does
  not qualify the eventual fit; it repairs the spec.
- **Test coupon** — a small print of *just the fit-critical features* (e.g. the two mating ends of a
  long part), printed to check fit/function before committing to the full part.
- **Decision drawing** — labelled orthographic real-mesh view with explicit axes/view direction;
  resolves spatial language, not dimensional truth.
- **Reality gate / functional gate** — physical checks against the actual mate / actual application,
  not against the model.

## Deferred (stress-test verdict)
A formal autonomy "dial", an offset *model/library*, and marketplace/catalog framing are
**deferred** until real validated parts and (for a venture) real customers justify them. Dimension
provenance is no longer ceremony: the venture's measured/estimated/unknown export gate proved the
friction and is now structural. Keep the rich measured CSV; build an offset model only when the
friction of not having it actually stops you.

## Next validation
Dogfood each new generic mechanism on a consumer project: spec provenance must block a real unknown,
a printed gauge must upgrade it, a labelled drawing must close a spatial decision, and fit-core must
let a cosmetic variant inherit a real fit without changing its mating ROI. Record where those tools
fail; do not add another layer merely because it can be imagined.
