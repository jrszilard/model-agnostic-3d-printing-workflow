# pipeline/ — AI-CAD stages (runnable)

Each stage is an executable script. This is the authoritative in-repo reference for every stage.

**Start or resume from any client:** [operator card](AGENT-START.md) · [offline cross-model trial](agent-trials/README.md). `python3 platform/pipeline/next_action.py <directory> --json` returns an evidence-backed action and stop bit, not an approval. Preparatory preflight now surfaces the same per-part design/status check that handoff still enforces independently.

## Stages & usage
| Stage | Script | Usage |
|---|---|---|
| prepare | `prepare/prepare.sh` | `prepare.sh --root <canonical checkout> <part>/prepare.yaml [--preflight]` → bounded complete preparation + hash-validated stage reuse; READY and STOP, never send. [Contract](../../docs/preparation.md) |
| build   | `generate/build.sh` | `build.sh <src.scad\|src.py> <outdir> [openscad -D args]` → STL (+STEP for CadQuery) |
| preview | `preview/render.sh` | `render.sh <part.stl> <outdir>` → five stamped review PNGs; `--profile zero-to-cad-8` → eight 256px model-input views + hash manifest (never a handoff stamp) |
| decision drawing | `preview/plan-drawing.py` | `plan-drawing.py <part.stl> <out.png> --view top --annotations labels.yaml` → stamped labelled orthographic drawing with axes + overall dimensions |
| preview (supports) | `preview/plot-supports.py` | `plot-supports.py <plate_1.gcode> <out.png> ["label"]` → FRONT/SIDE/TOP plot of **support vs model** + support-% of extrusion, parsed from the sliced gcode (run after `slice`, for the handoff) |
| verify  | `verify/verify.sh`  | `verify.sh <part_dir>` → CAD integrity + dims/probes vs `spec.yaml`; exit 0=PASS, 1=FAIL. B-rep facts and declared probes BLOCK; `step_present`, `single_solid`, `manifold`, `no_self_intersection` WARN. No STEP → **UNPROVEN**, not passed |
| slice   | `slice/slice.sh`    | `slice.sh [opts] [--spec <part>] [--post <hook>] <outdir> <part.stl>...` → arranged Core One **gcode + `.3mf`**, final-byte manifest, and exact named-profile/effective-config identity |
| arrange | `slice/arrange.py`  | `arrange.py --out <plate.stl> <stl>...` → shelf-packs parts into ONE plate STL (run automatically by `slice.sh` for >1 part) |
| thumbnails | `slice/thumbnails.py` | `thumbnails.py --gcode <f> [--machine <m.json>] <stl>...` → embeds preview PNGs the headless slicer CLI skips (run automatically by `slice.sh`) |
| verify-slice | `verify/verify-slice.sh` | `verify-slice.sh [--spec <part>] <outdir> [<stl>...]` → machine gate: mesh + slicer/post hooks + final gcode + profile/effective-config identity + support intent/keep-outs; exit 0=PASS 1=FAIL |
| handoff | `handoff/handoff.sh` | `handoff.sh <outdir> [<part_dir>]` → checks/presents artifacts and writes `handoff.txt` + an explicitly **not-evaluated** `qualification_manifest.json`; exits 10 stale geometry, 12 spec truth, 13 no spec, 14 absent/stale exact B-rep verdict, 15 incomplete next-touch design/status qualification, 16 unbound manifest, 17 non-PASS deterministic slice gate |
| physical iteration | `verify/qualification_check.py` | `... init --manifest <build/...json> --part <dir> --id <id> --kind coupon\|full-part --objective <q> --output <qa/...yaml>` → machine-filled `planned` record with all human fields null; `record`, `part`, and `metrics` validate completed evidence/status and report only structurally valid prospective outcomes |
| send    | `send/send.sh`      | `APPROVED=1 send.sh [--start] <gcode>` → require exact handoff + qualification manifest, upload to the Core One (PrusaLink), optionally guarded-start |
| scan    | `scan-process/`     | (stub) scan mesh → surface → STEP — reverse-engineering path |

`build → preview → verify → slice → verify-slice → handoff → APPROVE → send → human evaluate →
record → revise/release` is the full loop. Approval, physical observations/readings, and the final
attestation are human-only; the scripts bind and validate their artifacts but never supply them.

### Source and reuse (0.5)

Declare `build.source`, primary STL/STEP and actual `source_dependencies` at the next plate.
The build runner captures producer evidence; handoff verifies committed selected inputs/exports
and external dependency identities. A changed generator cannot reuse yesterday's export, even
when both are committed. The recorded scope is not a claim that the whole repository is clean.
Do not park unrelated work, synthesize producer records or transfer path-bound authority.

Preparation creates the complete review set (including labelled drawings and zero-support plots),
records keys/output hashes/durations in `<plate>/preparation.json`, and performs a fresh final
handoff. One changed-input repair needs `--repair-reason`; additional passes need
`--escalate-reason`. The Python/CadQuery producer and one-primary-model coordinator are the initial
supported path. Exact syntax, limitations and invalidation rules: [preparation](../../docs/preparation.md).

## Explicit digital-only evaluation API

[`isolation/EVALUATION.md`](isolation/EVALUATION.md) documents the approved-local-evaluation
entrypoints: sealed source/byte mapping, bounded `Batch`/`run_stage`, artifact admission after
successful exit and whole-cgroup cleanup, and runtime inventory/probes. Separate digital schema,
**not manufacturing producer evidence or a gate exemption**. Consumers keep specimen policy local.
`verify/geometry.py` is the import-safe geometry implementation shared by the unchanged manufacturing
CLI; no registries, stamps or physical verdict. Focused tests do not establish full-platform coverage.
[Passive numeric mesh diagnostics](preview/MESH_REPORT.md) project bounded saved-STL reports without
CAD or normalization; consumers own exact report/artifact linkage and actual visual review. This
is not manufacturing `render.sh`, a general hidden-surface renderer or a product GUI.

## Explicit non-CAD host-control experiment

[`isolation/check_host.py`](isolation/check_host.py) exercises a fixed approved local Linux profile:
Bubblewrap namespaces, delegated cgroup limits, bounded scratch/logs and descendant cleanup.
[Scope, invocation and six focused offline tests](isolation/README.md). It is **not a CAD runner,
production sandbox or gate bypass**, and changes no build/verify/handoff semantics. The broad
`test.sh` includes CAD suites; it was not run in this non-CAD increment. No full-platform regression
or CAD capability claim follows from those focused/control tests.

## supports — design them out first, then tune them

**The order matters.** Every support is a bench chore and a scar; the cheapest support is the
overhang you removed in CAD. On the LED risers, four separate overhangs were found and deleted
before any setting was touched, and the part that had none left slices to **zero support toolpaths
with tree enabled**. Reach for settings only for what survives that.

**Re-slice to find overhangs; do not reason about them.** All four were invisible in the model and
obvious in `plot-supports.py`. Two were mine and wrong in ways no amount of staring would have
caught: a cone fused *inside* the column it was meant to flare from, and a circular cone base
overhanging the *triangular* peg beneath it (a circumscribing circle stands proud of its triangle
everywhere between the vertices).

**Check that support was GENERATED before checking where it lands.** `--support` now records exact
intent in `slice_meta.json`; `verify/support_check.py` blocks if the final gcode has zero support
extrusion. This closes the visor v8 trap: `support_material=1` plus `support_material_auto=0` looked
configured, sliced cleanly, and left a floating cantilever in air while every location check passed
vacuously.

**Check WHERE the support lands, not just how much.** Support ran to within 0.5 mm of a riser's
axis — inside a Ø3.6 wire bore, where no tool could reach it and it would have blocked the wire the
channel exists for. `%` of extrusion would never have shown that; the XY footprint did. Declare
exact cylindrical exclusions under `spec.yaml: slice.support.keepouts`; use `shape: cylinder`
for an axis-aligned bore or `shape: finite-cylinder` with a 3-D centre/unit axis/half-length for
an oriented bore in its real print frame. Violations are deterministic HARD failures over the final
gcode, unlike a visual support heuristic.

| the test | why |
|---|---|
| does it enter a bore, socket or slot? | unreachable — worse than the overhang |
| is it fused into a gap a tool cannot enter? | the cleat-tab failure, twice |
| is it an external face? | fine — snips reach it from every side |

**`--support` applies a removal-friendly interface automatically** (`SUP_EASY` in `slice.sh`). The
stock profile's is nearly solid — `interface_spacing 0.2`, 3 interface layers, 80% XY — and Prusa's
own guidance says a dense interface "complicates removal" and "bigger XY separation … makes them
easier to remove and less prone to fusing". Defaults are now 2 interface layers, 0.6 spacing, 120%
XY, no sheath; a later `--set` still overrides any of them.

**`--support-angle` does nothing for tree supports.** PrusaSlicer applies the overhang threshold to
GRID supports only; organic/tree ignores it. Tested at 55/40/30/20° with identical output. If you
need the threshold to bite, use `--support=normal`.

**One plate is one support setting.** A plate mixing a part that needs support with one that does
not will support both. Two plates, or design the overhang out.

**A support that cannot be removed is a design failure, not a slicing one.** Where a part cannot be
made support-free at all — the peg riser could not, because TK10's 1.65 mm inradius is smaller than
the 1.80 mm the wire bore needs — that is a signal about the *design*, and it is worth reading as
one before spending another round on settings.

## Requested versus sliced inventory

For each **new** plate, record its intended **printable pieces** (not the entire kit or nonprinted hardware) in a fresh output directory. Use the brief/selected BOM for the first command; independently use the CAD library for the second. The operator needn't type this: an agent transcribes unambiguous IDs and asks only about a real choice. Example (substitute the actual directory and single-body STLs):

```sh
p=build/plates/example-fit-i1
python3 platform/pipeline/plate_inventory.py request "$p" clip=2 foot=1
python3 platform/pipeline/plate_inventory.py catalog "$p" clip=parts/example/stl/clip.stl foot=parts/example/stl/foot.stl
# Run the normal preparation/verify-slice chain. To inspect final bytes without writing:
python3 platform/pipeline/plate_inventory.py check "$p" --json
```

`plate-request.json` freezes the quantities independently of the slice. The catalog snapshots one named reference STL per distinct ID under `inventory-models/`, addressed by hash. One ID may appear many times; cataloguing extra known IDs is fine. Do not feed a merged plate in as a piece reference. If contents change, use a new output; never backfill an implicit order from the finished print. Raw standalone slicing remains available for digital studies, but cannot produce an upload handoff without the check.

`handoff.sh` runs `record`, writes `plate-inventory.json`, prints **requested / in 3MF / in G-code** plus per-ID shortfalls and extras, and refuses at **exit 19** unless all three agree. `UNPROVEN` means the check could not establish the inventory, not that a physical piece is missing. The handoff binds the report, which binds the request, catalog, actual 3MF, effective slice record and final G-code. `send.sh` checks these, the exact selected file, and the reference hashes again before any printer access. Inventory never overrides a scope hold or supplies approval. Existing receipts keep their historical meaning; no archive rewrite is needed.

**Method and limits:** Local Python 3 + NumPy, Prusa ASCII G-code and supported millimetre 3MF core meshes. Count printable build *instances*, including disconnected bodies inside one object. Match their complete oriented triangle meshes to catalog geometry under translation and bed-plane quarter-turns (0.0002 mm serialization tolerance). The model name, weight, shell count alone or toolpath object label is not a part ID. For flat-bed, separated prints, require positive, typed model moves in the exclusive projected area of each matched body from the first layer to its top, with no missing nominal layers. Do not count purge, skirt/brim, support, travel or unretraction. The 1 mm conservative projection grid, 0.12 mm XY allowance and exact line/arc endpoints test **presence**, not bead-by-bead shape or physical success. The standard CLI centers the geometry on the bed; `catalog ... --placement as-saved` explicitly selects already-registered project coordinates. No best-fit guessing. Touching/overlapping or nested articles, modifier/negative volumes, ambiguous IDs, different tessellations, unsupported motion/layer modes or unreadable artifacts may stop as unresolved. Use independently identifiable print-ready reference meshes or a separately checked extension, not a manual pass. [Operator card](AGENT-START.md).

## When a ready plate is not the requested plate

- `python3 platform/pipeline/next_action.py PATH_A PATH_B --json` compares **explicit** candidates without selecting one. `clarify_target` returns a question and each candidate's evidence. For one directory (or aliases of one), normal schema-1 routing is unchanged. No global search, ranking or provider dependency.
- `python3 platform/pipeline/plate_scope.py hold PATH --reason 'what no longer matches' --question 'which version or pieces?'` adds an exclusive `scope-hold.json` to the exact existing plate. Put the operator's scope issue here as soon as it is known, not just in a note. No plate yet? Ask before building one. `.../plate_scope.py check PATH` is read-only; `PLATE_SCOPE_RESULT: PASS` means **only** that no hold marker was found.
- On the local bench, a held or unreadable marker takes precedence over READY. Preparation, slice, handoff and send refuse at **exit 18** before replacing outputs or contacting a printer. Historical receipts still take precedence when reporting an action that already happened. This is an entry check, not cancellation, a live printer check or a way to recall a file already staged. An unrecorded hold in legacy prose is not detected automatically.
- Different or still-unclear scope? Leave the old dir held. Use a distinct output for any new version **after** the operator clarifies. Same unsent scope explicitly selected? `python3 platform/pipeline/plate_scope.py reopen-for-review PATH --answer 'actual operator reply'` preserves the reason, answer and old handoff under `scope-history/` before removing the marker. Do not delete the marker, copy an old stamp, or use an approval token to resolve a question. Recheck with `next_action.py`, run the proper digital gates, present fresh paths, and wait for fresh approval. The tool does not attest who supplied the answer.

## handoff — the human gate before anything reaches the printer
```
platform/pipeline/handoff/handoff.sh build/<name> parts/<cat>/<part>   # present these paths, then STOP
```
After a **fresh, separate approval of this exact packet**, use `send.sh` without `--start` for upload-only. Starting needs its own explicit intent; never chain the two steps.
`send.sh` **hard-refuses** an active scope hold (exit 18), without `handoff.txt` (exit 8) and without `APPROVED=1` (exit 9). It also
**reports, without blocking,** when the plate's own `M862.1 ... F<0|1>` disagrees with the fitted
nozzle recorded as `PRUSALINK_NOZZLE` in `$PRUSALINK_ENV` (default `~/.config/3d-printing-workflow/prusalink.env`) — PrusaLink reports
nozzle diameter but never high-flow, so the fitted nozzle is recorded, not discovered. That one does
not block because the printer does not either: four `F0` plates have printed on this bench's HF0.4
nozzle. What it flags is a plate carrying the other nozzle's speeds, flow cap and temperatures. The
gate covers the **upload**, not just `--start` — a staged plate is one tap from printing, so
uploading before the human has seen the geometry defeats the point. New uploads also require the
exact `qualification_manifest.json` produced during that handoff; archived handoffs are not future
upload authority. The manifest records machine-known identity and explicitly says **not evaluated**—
it is neither approval nor a physical claim. The [per-ID inventory](#requested-versus-sliced-inventory) is mandatory at handoff and upload; weight is an additional sanity check.

`send.sh` also **refuses to overwrite the file of an ACTIVE job** (exit 6, `FORCE=1` overrides).
The upload PUT carries `Overwrite: ?1`, so it replaces a file wholesale — including one the
printer is mid-way through reading. `--start` has refused a busy printer since day one, but a
bare upload checked nothing, on the reasoning that staging is a safe half-step. **Staging OVER the
running file is not staging; it is editing the job in flight.** Found 2026-08-05 when six plates
were re-uploaded as a batch while `rt1base` was 27 minutes into printing: the job went `PAUSED`
and the printer to `ATTENTION`. Uploading a *different* file during a print is allowed but warns,
since it shares the link. The lesson generalises past this script — **a gate that names a verb
(`--start`) guards that verb only, and the damage came through the one nobody gated.**

Human approval and deterministic verification answer different questions. `APPROVED=1` confirms
intent after review; it cannot overrule a known bad/missing `verify_slice.txt`, and `FORCE=1` is not
a bypass for that gate. Mesh/DFM findings remain warnings because they guess; the deterministic
slice facts do not.

## post-slice hooks — the transformed gcode is the verified artifact

Use repeatable `--post <script>` for a required machine/material transform. Each hook receives the
gcode path; `.py` hooks need not be executable. Hooks run after thumbnail embedding and before any
verification/handoff. `gcode_manifest.json` records each hook path/hash/exit and the final gcode
sha256. `verify-slice`, `handoff`, and `send` fail if those bytes move later.

Core One+ ASA example (explicit actuated-vent close after homing):

```bash
slice.sh --post platform/pipeline/slice/hooks/core-one-close-vent.py --spec <part-dir> out part.stl
```

Do not edit gcode after the handoff: `handoff.txt` binds the reviewed sha and `send.sh` exits 11 on
a mismatch. Re-run the hook through `slice.sh`, then verify and hand off again.

## slice — real slicer features (headless)
**PrusaSlicer 2.9.6** (flatpak) targeting the **Prusa Core One**. Supports/brim/infill live in the
*print settings*, not as CLI flags; `slice.sh` writes them to an override `.ini` and passes it via
`--load`, which **merges on top of** the named profiles (unlike Orca, no full-preset copy needed).
```
--support[=normal|tree]  --support-angle <deg>  --on-build-plate-only
--brim <mm>              --infill <pct>          --rotate-x/-y/-z <deg>
--process/--machine/--filament <name>            --set key=value  (repeatable, any print-config key)
--spec <part-dir|spec.yaml>                       --post <script>  (repeatable)
FIL="Prusament PETG @COREONE"                    (env; Prusament PLA @COREONE by default)
```
Defaults: machine `Prusa CORE One 0.4 nozzle`, process `0.20mm SPEED @COREONE 0.4`, filament
`Prusament PLA @COREONE`. e.g. `slice.sh --support=tree --brim 0 --rotate-x 90 out/ part.stl`

**No brim by default, explicitly `--brim 0`.** Omitting the option inherits the preset rather than
asserting zero. Only use a brim when necessary for the specific plate, with evidence, minimum
justified width and removal plan disclosed before approval. Verify effective `brim_type=no_brim`
and `brim_width=0` for the default case. The authority is
[workflow: brims](../../docs/workflow.md#brims-are-an-exception-not-a-default); this is not a new
runtime gate. Do not copy nonzero settings from historical plates as adhesion insurance.

**Gotchas (PrusaSlicer 2.9.6 CLI) — each one cost a debugging cycle:**
- **Several input STLs are NOT one plate.** The CLI runs its action *once per file*, each
  overwriting `--output`, so an N-part plate silently becomes whichever file came **last** — exit 0,
  no warning. A 6-coupon plate came out at 2.83 g (less than *one* coupon). `--merge`, the
  documented fix, **segfaults** (exit 139). `slice.sh` therefore pre-packs multi-part plates into a
  single STL via `slice/arrange.py` before the slicer sees them. Compare the independent requested inventory with model extrusion, not just the number of input files or the weight.
- **The flatpak is sandboxed to `$HOME` and cannot see `/tmp`.** A `mktemp` override file reads as
  empty/missing *without erroring*, so every override is silently dropped. All inputs (STLs, the
  override `.ini`, `--output`) must live under `$HOME` — `slice.sh` keeps the `.ini` in `<outdir>`.
- **`fill_density = 100%` ERRORS** ("the selected fill pattern is not supposed to work at 100%
  density") unless `fill_pattern` is also set to a pattern that can — `rectilinear`. The error goes
  to stderr, the `.3mf` export is skipped, and a gcode is still written, so it looks survivable.
  Every 100%-infill plate must pass `--set fill_pattern=rectilinear`.
- **`solid_infill_below_area` is accepted and does NOTHING** (2.9.6). It lands in the gcode config
  header, so it *looks* applied, but small regions still get sparse infill: 8 keys weighed 2.55 g
  with 76 sparse-infill sections at `fill_density=15% solid_infill_below_area=20`, byte-for-byte
  the same as with the override absent, against 2.98 g at true 100%. **There is therefore no way
  to mix infill densities within one CLI plate** — parts needing different densities need
  different plates. Checked 2026-07-30 while trying to put 15% socket blocks and 100% keys on one
  plate; verify with an infill knob by *weight*, never by the config header.
- `--binary-gcode 0` is parsed as a flag **plus a filename** ("No such file: 0"); the negation is
  `--no-binary-gcode`. `slice.sh` sets `binary_gcode = 0` in the override ini instead, because the
  whole verify/preview chain (`gcode_check.py`, `plot-supports.py`, `thumbnails.py`) is a line
  parser. The Core One accepts both ASCII `.gcode` and binary `.bgcode`.
- Profiles resolve only against a populated **datadir**. A fresh flatpak has none, and every run
  dies with `Configuration wasn't found` until the vendor bundle is seeded (see Setup below).
- Filament names are printer-scoped: `Prusament PLA` is rejected as *not compatible* with the Core
  One — it must be `Prusament PLA @COREONE`.
- `--rotate-x/-y/-z` **work natively** (no segfault, unlike OrcaSlicer 2.4.1), so print orientation
  no longer needs baking into a dedicated `…-print.stl`. There is **no CLI auto-orient**;
  `--orient` warns and is ignored.

## Setup — PrusaSlicer flatpak (reproducing this machine)
```bash
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user -y flathub com.prusa3d.PrusaSlicer
# PATH wrapper (the pipeline calls `prusa-slicer`):
printf '#!/usr/bin/env bash\nexec flatpak run --command=prusa-slicer com.prusa3d.PrusaSlicer "$@"\n' \
  > ~/.local/bin/prusa-slicer && chmod +x ~/.local/bin/prusa-slicer
# Seed the datadir, else every CLI run fails with "Configuration wasn't found":
D=~/.var/app/com.prusa3d.PrusaSlicer/config/PrusaSlicer
P=~/.local/share/flatpak/app/com.prusa3d.PrusaSlicer/current/active/files/share/PrusaSlicer/profiles
mkdir -p $D/vendor && cp $P/PrusaResearch.ini $P/PrusaResearch.idx $D/vendor/
printf '[vendor:PrusaResearch]\nmodel:COREONE = 0.4\n' > $D/PrusaSlicer.ini
```
The `.flatpakref` in `~/Downloads` is just a pointer file — it is not the app and cannot be
"opened" directly; installing from flathub as above is the working path.

## thumbnails — why `slice.sh` embeds them itself
Both slicers' CLIs run **headless with no GL context**, so they silently skip the thumbnail render
the machine preset asks for. The gcode still slices and prints fine — but PrusaLink (and the
printer's LCD) show a **blank preview tile**, which is easy to misread as "the upload failed".

`slice/thumbnails.py` re-adds them after slicing (OpenSCAD offscreen render → PNG → base64 block).
It runs automatically at the end of `slice.sh` and is **advisory**: a missing `openscad` prints a
note and leaves an otherwise-good gcode alone. It handles **two flavours**, because the shapes are
not interchangeable — emitting Orca's into Prusa gcode gets it silently ignored:

| | anchor | block shape | default sizes |
|---|---|---|---|
| OrcaSlicer | `; HEADER_BLOCK_END` | wrapped in `; THUMBNAIL_BLOCK_START/END` | 96x96, 300x300 |
| PrusaSlicer | `; generated by PrusaSlicer` line | bare `;` fences, no wrapper | 380x285 |

The Core One preset asks for `16x16/QOI, 313x173/QOI, 480x240/QOI, 380x285/PNG`. Only the **PNG**
size is emitted: the QOI-tagged sizes must genuinely be QOI-encoded, and PNG bytes under a
`thumbnail_QOI` tag are read as a corrupt image rather than ignored.

- Embed only what the preset requests. Moonraker **derives** the extra sizes its UI wants (48x48,
  195x195) from the largest embedded image — that is why a GUI file reports 4 thumbnails but
  contains 2.
- **GOTCHA:** the number on `; thumbnail begin 96x96 2592` is the **base64 character count**, not the
  decoded byte count (1943 here). Get it wrong and Moonraker reads a truncated image.
- The format is pinned byte-for-byte against real GUI output in
  `slice/testdata/gui_sliced_header.gcode` (`slice/test_thumbnails.py`). Run: `cd slice && pytest -q`.

Standalone: `thumbnails.py --gcode <f.gcode> [--machine <m.json>] [--sizes 96x96,300x300] <stl>...`

## verify-slice — machine gate before send
`verify-slice.sh [--spec <part>] <outdir> [<stl>...]` runs after `slice` and before `handoff`.
Exit 0 = PASS; exit 1 = FAIL; writes `<outdir>/verify_slice.txt`. It composes six checks:

1. **mesh pre-check** (per STL, under `freecadcmd`): **HARD** only on bbox-oversize against the
   Core One's **250×220×270 mm** bed. Non-manifold, self-intersection and disconnected-component
   findings remain advisory WARNs. The bbox is orientation-naive; the final gcode bed check is not.
2. **slicer exit code** (`slice_exit.txt`): every nonzero code is **HARD**, including unknown codes.
   PrusaSlicer returns plain 1 for many failures; naming it is optional, letting stale output pass is
   not. `slice.sh` now deletes previous gcode/handoff/verdicts before every attempt.
3. **postprocess/final-byte identity** (`gcode_manifest.json`): every recorded hook must exit zero
   and the current gcode sha256 must match the post-hook artifact. A later edit is a HARD stale-file
   failure, and handoff/send check the same identity again.
4. **slice/profile identity** (`slice_meta.json`): **HARD** unless the machine/process/filament
   profile names, rotations, explicit overrides, post-hook bytes, final G-code/3MF, slicer generator
   line, and exact effective config embedded in G-code remain bound. Identity is not suitability.
5. **gcode printability** (`plate_1.gcode`): **HARD** on <2 layers, no first-layer extrusion,
   off-bed toolpath, no nozzle temperature, or missing/empty gcode. `;TYPE:Custom` purge extrusion
   is excluded so an off-bed machine purge neither fails nor satisfies the model checks.
6. **support intent/keep-outs** (`slice_meta.json` + optional spec): `--support` with zero support
   extrusion is **HARD**. Support segments crossing an exact declared cylindrical keep-out are also
   HARD; support amount/quality remains a review judgment in `supports.png`.

This is a **hard gate** for deterministic failures: handoff exits 17 and `send.sh` exits 7 when
`verify_slice.txt` is missing or not exactly `PASS`. `FORCE=1` cannot override it. Sampled mesh/DFM
findings remain warnings inside the report; turning those into blockers would overstate their
authority.

OrcaSlicer 2.4.1 CLI exit codes (source: `verify/orca_exit.py`'s `_HARD` dict; CLI ref:
[printago.io/blog/orca-slicer-cli-reference](https://printago.io/blog/orca-slicer-cli-reference)):

| code | name | meaning |
|---|---|---|
| 0 | `CLI_SUCCESS` | sliced cleanly (not hard) |
| -6 | `CLI_DATA_FILE_ERROR` | input data/model file error |
| -14 | `CLI_OUT_OF_MEMORY` | out of memory |
| -20 | `CLI_PRINTABLE_SIZE_REDUCED` | object exceeds printable size (reduced) |
| -21 | `CLI_ARRANGE_FAILED` | arrange failed |
| -22 | `CLI_ORIENT_FAILED` | orient failed |
| -50 | `CLI_NO_OBJECTS` | empty plate / no printable objects |
| -52 | `CLI_OBJECTS_PARTLY_INSIDE` | object is partly/fully off the bed |
| -58 | `CLI_SLICING_TIME_LIMIT` | slicing time limit exceeded |
| -59 | `CLI_TRIANGLE_LIMIT` | triangle-count limit exceeded |
| -61 | `CLI_FILAMENT_BED_MISMATCH` | filament not compatible with bed type |
| -63 / -64 | `CLI_OBJECT_COLLISION` | object/skirt collision / object collision |
| -100 | `CLI_SLICING_ERROR` | slicing error |
| -101 | `CLI_GCODE_PATH_CONFLICTS` | gcode path conflicts |
| -102 | `CLI_GCODE_PATH_UNPRINTABLE` | gcode path in unprintable area |

Any code not in this table (and not 0) is `unknown` — treated as non-hard.

## send — upload + guarded start (PrusaLink)
The Core One runs **PrusaLink** (Buddy firmware) on port 80 at `coreone.lan` (`$PRUSALINK` to
override). `send.sh`: 1. reads `GET /api/v1/status`, 2. `PUT`s the gcode to
`/api/v1/files/<storage>/<name>`, 3. with `--start`, refuses unless the printer is **idle**.
```
send.sh <gcode>                     # upload only (stage); start on the printer or in PrusaLink
send.sh --start <gcode>             # upload + start (only if idle)
send.sh --name x.gcode --start ...  # custom remote filename
send.sh --storage local ...         # default storage is `usb`
```
**Credentials** live in `~/.config/3d-printing-workflow/prusalink.env` (or `$PRUSALINK_ENV`, outside the repo so they can never be
committed) — get them on the printer under **Settings → Network → PrusaLink**. Current Buddy
firmware shows a **username + password** (HTTP digest), *not* an API key:
```
PRUSALINK=coreone.lan
PRUSALINK_USER=maker             # whatever the printer screen shows
PRUSALINK_PASSWORD=<password>    # HTTP digest auth
#PRUSALINK_KEY=<API key>         # older firmware only; sent as X-Api-Key
```
Debugging auth: `curl -sv --digest -u maker:<pw> http://<host>/api/v1/status`. A 401 whose
`WWW-Authenticate` says **`stale=false`** *after* curl has sent its `Authorization: Digest` header
means the handshake was fine and the **password is simply wrong** — not a protocol/realm problem.
Gotchas:
- Every endpoint answers **401 with `WWW-Authenticate: Digest realm="Printer API"`** when
  unauthenticated — that 401 (rather than 404) is also the reliable way to *identify* a Core One on
  the network, since it advertises no mDNS service and serves a gzipped blob at `/`.
- **v1 has no separate "start file X" call** — starting is the `Print-After-Upload: ?1` header on
  the upload itself, so `--start` has to be decided *before* the transfer, not after.
- `Overwrite: ?1` is set so re-sending the same plate name replaces it instead of 409-ing.
- **The USB storage is FAT, so the printer renames your file to an 8.3 short name**:
  `coupon-ladder.gcode` is stored as `COUPON~1.GCO`, with the full name kept only in
  `display_name`. Any follow-up call that addresses the file by path (status, thumbnail, delete)
  must use the **short** name — look it up via `GET /api/v1/files/usb/<name-you-uploaded>`, which
  does resolve the long name and returns the short one in `name`.
- Verify a send actually landed by fetching the thumbnail the printer itself serves
  (`refs.thumbnail`, e.g. `/thumb/l/usb/COUPON~1.GCO`). That round-trips the *printer's own* parse
  of the gcode, so it proves the upload, the file's validity, and the embedded thumbnail in one
  request — and for a multi-part plate you can literally count the parts in the image.

## verify — how it checks a part
- **CAD integrity** (generic): STEP valid + single solid + closed; STL manifold + no self-intersection.
- **Fit core** (optional contract): `fit_core:` names the owning source, stable v1 fingerprint and
  every variant claiming that identity. `verify` reports agreement; generators use
  `parts/_lib/fitcore.py::assert_fit_regions` to prove the final solids match frozen mating
  references inside exact ROIs. This complements geom id; it never replaces byte identity.
- **Fasteners** (optional contract): `fasteners:` is checked by `verify/fastener_check.py` for a complete,
  non-contradictory method declaration (hardware, receiver, source assertion, coupon, physical gate).
  It does **not** certify joint strength; see `docs/fasteners.md`.
- **Dimension truth**: `provenance: measured|standard|estimated|placeholder` is independent of
  geometric conformance. `fit_critical: true` blocks verify/handoff unless measured or standard;
  missing provenance remains legacy-compatible only on non-fit-critical dimensions.
- **Exact solid probes** (optional unless fit-bearing): `probes:` declares boxes in final-STEP model
  coordinates. `inside` requires the whole box occupied, `outside` requires zero overlap, `clear`
  checks material in two regions' intersection, and `spans_axis` counts connected section solids.
  Omitted box bounds inherit the STEP bbox. `verify` blocks failed probes or missing required
  coverage; handoff independently requires and statically validates declarations. Pure
  schema/verdict logic lives in `verify/probe_check.py`.
- **Dimensions**: each `spec.yaml` dim may carry a `measure:` recipe -
  - `{method: bbox,  file: <stl>,  axis: x|y|z}` — mesh bounding-box length
  - `{method: slice, file: <step>, axis: x|y|z, at: <v>, ring: outer|inner}` — section extent
  - no recipe → SKIP (e.g. a derived wall). Pure compare logic is unit-tested (`test_spec_check.py`).
- `verify.py` runs under **freecadcmd**, which sets `__name__` to the module name (no `__main__`
  guard), tries to *open* any path passed as argv (part dir via **`PART_DIR` env**), and can exit
  without flushing stdout (we flush explicitly). Tests: `python3 -m unittest discover -s platform/pipeline/verify -p 'test_*.py'`.

## Preview render (real geometry)
```bash
printf 'import("part.stl");\n' > _preview.scad
openscad -o preview.png --imgsize=800,800 --viewall --autocenter --camera=0,0,0,55,0,25,0 _preview.scad
```

## Support illustration (from the sliced gcode)
`plot-supports.py` answers "show me the supports, not just the model" for the handoff — the model
preview (`render.sh`) can't show support structure. It separates support extrusion
(`;TYPE:Support` / `Support interface`) from model extrusion and plots FRONT/SIDE/TOP with support
in red over the model in gray, and prints the support share of extrusion.
```bash
python3 platform/pipeline/preview/plot-supports.py build/<name>/plate_1.gcode build/<name>/supports.png "outlet-up, tree, no brim"
# e.g. the k1c-elbow reprint -> support = 5.7% of extrusion, tree trunk under the bend overhang
```
**gcode-parsing gotchas (baked into the tool — don't regress):**
- OrcaSlicer writes numbers with **no leading zero** (`E.01152`, `I.384`). The coordinate regex
  MUST be `([XYZEIJ])(-?[\d.]+)`; the stricter `\d+\.?\d*` silently drops those values (most
  support/arc moves) → the plot looks empty and the % is garbage.
- Handle **G2/G3 arcs** (interpolate via I/J) and **relative extrusion** (`M83`) — tree supports
  are mostly arcs, so a G1-only parser also empties the plot.
