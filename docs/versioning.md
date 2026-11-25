# Versioning — how a change happens without losing the version that worked

**Date:** 2026-08-20 · **Status:** active. Supersedes the "commit directly to `main`" rule.
Mechanised by `platform/bench.sh`. Read this once; after that the verbs are the whole interface.

## Why this exists

`main` used to be the only branch, and every revision landed on it directly. That is fine until a
revision is wrong. Then "go back to the last version that worked" means reading twenty prose commit
titles to guess which one was physically proven — and the commits are 50–110 files wide, because
regenerating geometry rewrites every STL, STEP and PNG at once (LFC3: `107 files changed`).
Nothing was ever unrecoverable, but nothing was **findable** either.

The fix is not really branching. It is **naming the states that earned keeping**. The branch is
just what stops half-finished geometry from landing on `main` while you find out.

## The model

| ref | what it is |
|---|---|
| `main` | the last state that was **good on the bench**. Stays printable at all times. |
| `rev/<slug>` | one revision in progress. Checkpoint freely — cheap, disposable, local. |
| `green/<slug>-N` | tag: the fast digital loop went green (`workflow.md` ②). Machine-checkable, so an agent may set it. |
| `passed/<slug>-N` | tag: cleared the **reality / functional gate** (④). **This is "the last version that worked."** |
| `landed/<slug>` | a revision that shipped to `main`, its checkpoints retained. Swept after `KEEP_REVS` (2) more revisions. |
| `abandoned/<slug>` | a revision walked away from. Renamed out of the way, never deleted. |
| `restore/<tag>` | a known-good state brought back to work on. Landing it rolls `main` back. |

## When a branch is required

**Geometry and spec.** If the change touches `parts/**/src/`, a `spec.yaml`, `parts/_lib/`, or
regenerates anything under `stl/ step/ preview/` — start a revision.

**Prose still goes straight to `main`.** `qa/` notes, `docs/`, `sell-details/`, a README. The last
two commits before this document were single-file writeups; branching those is pure ceremony.

## The one hard rule

> **Source is the merge unit. Geometry is regenerated, never merged.**

`stl · step · 3mf · png · FCStd` are binary. Git cannot three-way-merge them and neither can you.
If both sides touched the same geometry, the resolution is always *take the revision's source and
rebuild* — never a hand-picked mesh. `land` refuses and splits the conflict list into TEXT (resolve
by hand) and BINARY (`--theirs`, then rebuild) rather than guessing.

## `passed` is the human's to type

`CONFIRMED=1 bench.sh passed "<note>" <qa-record>` deliberately mirrors `APPROVED=1` in `send.sh`.
"It cleared the reality gate" is a claim about a **physical object** — no machine can check it, and
an agent must never assert it. The named record must already be committed, be
`qualification.current`, carry the observing human's `physical-observation` attestation, pass every
printed acceptance criterion, and bind the current model bytes, G-code, source, and effective
slicer config. The annotated tag stores its repository path and SHA-256. It is also what
`bench.sh back` offers as the known-good version, so it has to be earned. `green` is
machine-checkable and carries no such gate.

## What is retained, and for how long

Checkpoints are noisy and geometry-heavy; this repo is already 1.23 GB. So:

- **`main` gets one commit per revision.** The log stays readable, in the existing prose style.
- **Tags are permanent.** `prune` never touches them. Every state you blessed survives forever —
  which is why the window is keyed on *approval*, not on a commit count that could age one out.
- **Unapproved checkpoints live on `landed/<slug>`** for the last **2** landed revisions
  (`KEEP_REVS`), then `bench.sh prune` sweeps the ref and `git gc` reclaims the geometry.

So: the working branch, the last approved checkpoint, and the one before it are all in full detail.
Behind that, only what you approved.

## The verbs

```
bench.sh start <slug>                branch off main, in place  (refuses a dirty tree)
bench.sh save  "<note>"              checkpoint                 (runs test.sh)
bench.sh green "<note>"              pin: digital loop green
CONFIRMED=1 bench.sh passed "<note>" <qa-record>  pin: physical gate + exact evidence
bench.sh land -m "<message>"         squash the revision onto main
bench.sh back                        list the restore ladder
bench.sh back passed/<slug>-N        bring a known-good state back
bench.sh status                      where am I, what is pinned, what would prune drop
CONFIRMED=1 bench.sh prune           sweep old landed/* refs, then gc
bench.sh drop                        abandon this revision; main untouched
```

### Rolling back

```
bench.sh back                        # which versions were physically proven?
bench.sh back passed/lfc4-1          # opens restore/passed-lfc4-1 — main untouched
bench.sh land -m "back out to LFC4 — LFC5's spine cracked"
```

A rollback is **not** a merge. Landing a `restore/*` branch replaces `main`'s tree wholesale in one
commit — zero conflicts, and the commits being backed out stay in history, reachable and unrewritten.
Merging an old tree back would instead conflict on every binary, which is how a rollback turns into
an afternoon.

## Artifact identity — one version, or the handoff refuses

A `passed/` tag names a version of the *repo*. A **geom id** names a version of the *bytes*: the
first 8 hex of an STL's sha256. It is stamped at export and carried by everything downstream, so a
preview and a plate can be proven to depict the same solid.

| stage | writes | holds |
|---|---|---|
| `preview/render.sh` | `<out>/<base>.stamp` | the geom id these PNGs depict |
| `slice/slice.sh` | `<out>/plate_geom.txt` | the geom id of every STL on the plate |
| `handoff/handoff.sh` | `<out>/handoff.txt` + `qualification_manifest.json` | `version=` (branch@commit, tag, dirty) · `geoms=` · `gcode_sha=` · machine-only source/spec/verify/model/profile/config identity explicitly marked `not-evaluated` · one `spec_part=` per checked part |

**The check is driven by the PLATE, not by the preview directory.** For every part on the plate it
demands a stamped preview of *that* geometry. Everything else in `preview/` — other components, hero
shots, mockups — is listed as `context (not on this plate)` and never blocks. Driving it the other
way round refuses every honest handoff: `pegboard-canister-holder/preview/` holds four component
sets, so no single-component plate could ever pass, and the only escape would be `UNSTAMPED_OK=1`,
which disables the real check. A gate that must be bypassed to work is not a gate.

**It BLOCKS on mismatch (exit 10), it does not warn.** It catches:

- **the plate went stale** — an STL regenerated after the slice
  (`GEOMETRY MOVED SINCE THE SLICE: sliced 2477c2e5, on disk now 18822c5e`);
- **a stale preview** — the preview for a plate part depicts different geometry
  (`STALE: preview is geom 18822c5e, plate is c0fd486a`);
- **a missing or unstamped preview** for a part that is on the plate;
- **an unstamped plate**, and **a recorded STL path it cannot resolve** — both fail CLOSED. That
  second one matters: it is the half of the gate that catches "regenerated after slicing", and
  `slice.sh` records absolute paths precisely so running `handoff.sh` from another directory cannot
  make it silently check nothing.

`UNSTAMPED_OK=1` relaxes **both** unstamped checks (preview and plate) — it is a migration door, not
a per-check switch. It does not bypass exact B-rep verification, future design/status qualification,
or the qualification manifest required for a new upload.

The reasoning is the same as `APPROVED=1`: approving a plate while looking at a preview of different
geometry means approving something you have not actually seen. Existence checks could not catch it —
every file was present and the gate said COMPLETE.

Migration: previews rendered before 2026-08-20 have no stamp. Re-run `render.sh` (seconds), or set
`UNSTAMPED_OK=1` to downgrade just that check while working through the backlog.

## Five views, and a diff against the last version that passed

**`render.sh` renders five views**, not three: `iso` (front-right), `iso_back` (back-left), `top`,
`front`, `back`. iso/top/front structurally cannot show a back face, and on 2026-08-11 that shipped
a print — LFB2's debossed label was mirrored and read backwards (`7a9f08c`). The two added angles
are the ones agent-CAD self-review tooling converged on. Renders cost ~60 ms and ~15 KB each.

**`handoff/geom-diff.sh` answers the question the gate actually raises:** *what changed since the
part that worked?* The baseline is the newest `passed/*` tag holding that path — the last state that
cleared a **physical** gate, not merely the previous commit; diffing against a version that was
never proven says nothing about whether a change is a regression.

It reports facets, volume, surface area, bbox size, and centroid, and names the two cases that
matter:

- `IDENTICAL geometry.`
- `MOVED, not reshaped: same solid, translated by [9.4, 0.0, 0.0] mm.`

That second one is the point. A pure translation leaves facets, volume, area and bbox *size*
untouched and looks correct from every camera — it is exactly the 9.4 mm misalignment that motivated
this, and only bbox *position* and centroid catch it. The handoff prints the summary inline and
writes `build/<name>/diff_<part>.txt` plus baseline renders `diff_<part>_was_{iso,front}.png`.

**This one does not block.** A diff is the expected result of intending a change. It exists so the
approval decision is made against the last proven version rather than against nothing.

## DFM: measuring the solid, not the spec

`verify` proves the model matches the spec. It cannot see that the spec asks for something FDM will
not give you — the 0.50 mm wall that measured 9.75 mm at the floor passed mesh, verify-slice *and*
handoff, because all three compare the model to the spec and none of them measures the solid.
`workflow.md` answers that with "probe the solid before you slice an internal mechanism", a manual
step. `verify/dfm_check.py` makes it automatic:

- **Wall thickness** — ray-cast from a sampled facet inward to the nearest opposing surface. That is
  what calipers would read, not a shell parameter. Validated against a synthetic 0.5 mm fin: reads
  `0.500` and reports where. mini-r1's 0.70–0.74 mm sample is its physically-proven flare lip, not
  a deboss floor (`parts/media/usb-cloud-holder/qa/DFM-THIN-WALL-ANALYSIS.md`).
- **Overhang** — the angle each downward facet makes with the bed, first layer excluded.
- **External gap / repeating-feature resolution** — ray-cast outward to an opposing-facing surface.
  Against the actual visor evidence, v7's fused 12-barb fir tree reads **0.343 mm < 0.4 nozzle**
  and warns; v8's six-barb correction reads **1.000 mm** and clears. The analytic valleys were
  0.234/0.747 mm; a sampled mesh heuristic need only separate the bad side of the nozzle floor.

**These WARN and never block** — `AGENTS.md` reserves blocking for deterministic checks, and these
are mesh heuristics. `verify.sh` prints them after the verdict so a warning can't read as a failure.

Limits, stated so the numbers aren't over-read: overhang measures **downward-facing** area, not
area with nothing beneath it (a tabletop reports its whole underside, legs included) — it's an upper
bound and an early warning, confirmed in `supports.png`. Thickness and gap rays are **sampled**:
they find regions a spot-check would miss but cannot prove none exists. Gap rays can also report an
intentional micro-slot or tessellation sliver. Raise `--samples` around internal or repeating detail.

## Generators rot silently, so `test.sh` now checks them

`rebuild-all.sh` found 11 dead generators. The pattern: a coupon reads a constant from its parent
production module, the parent gets refactored, and nothing notices — `test.sh` never ran a
generator and the exports were already committed.

`verify/generator_refs.py` resolves those attribute reads **statically** (AST only — no CadQuery, no
geometry, no execution), so it is fast enough to run before every commit. It handles the repo's
actual idiom: not `import x` but `importlib.util.spec_from_file_location(...)` followed by
`module_from_spec`. The first version of the check only looked at `Import` nodes and reported a
clean repo while three coupons were dead.

`generator_refs.allow` is a **ratchet, not a pardon**: the 9 known entries are reported as debt and
don't fail; anything new does. Those 9 are coupons for mechanisms that were *replaced* — the sign's
slots became TK page seats (`aa06766`), pcc2's tapered upright became uniform — so there is no
rename to apply. They need retiring or porting, which is a design call.

**This matters more than it looks:** several are *coupon* generators, the articles that qualify a
joint for `parts/_lib/joints.py`. A sample whose coupon can no longer be built cannot be
re-qualified when material, printer, or orientation changes — and the registry says that re-opens
the gate.

## Regenerable geometry is not tracked

`.gitignore` drops assembly/mockup/massing **visualisations** and `--draft-/--opt/--test/--proto`
**variants** — 461 files, 907 MB, measured at 78% of a 3.32 GB history for output that is never
printed. Tracked geometry is now 265 MB: the printable part, its coupons, and `releases/`.

This trade is only sound because a rebuild reproduces the same solid:

Determinism was measured, not assumed, and two of the three exporters needed fixing:

| exporter | out of the box | fix |
|---|---|---|
| CadQuery → **STL** | deterministic; reproduces the committed bytes | none needed |
| CadQuery → **STEP** | **not** — OCCT stamps the wall clock into the ISO-10303-21 header. Two runs 2 s apart differed in exactly one line | `generate/c14n_step.py` pins that timestamp to the epoch (header only) |
| OpenSCAD → **STL** | **not** — facet order is random. Two builds of `cable-clip.scad` gave the same 94484 bytes in a different order, differing from byte 488 | `generate/c14n_stl.py` rotates each facet's vertices to a canonical start (preserving winding) and sorts the facets — the fix NopSCADlib uses. After it: byte-identical, 1888 facets and the same bbox either way |

Canonicalisation runs at three points, because generation is not the only way bytes reach git:
`build.sh` after every build; `stamp.sh` before it hashes anything (so a geom id always names the
canonical form regardless of how the STL was made); and `bench.sh save` before staging — every part
README documents running the exporter directly, and on that path `build.sh` never sees the file.

## Regenerating: `rebuild-all.sh`

`generate/rebuild-all.sh` runs every generator (78 discovered; helpers and `_lib` excluded).
`--list` shows them, `--jobs N` parallelises, `--check` refuses a dirty tree, rebuilds, and reports
whether any **tracked** geometry moved — the standing proof that untracking was safe.

Two things the first full run exposed, both pre-existing and neither yet fixed:

- **11 generators fail outright** (several `photo-calibration-corner` coupon scripts, three
  `social-media-sign` coupons, `bottle-lamp-stopper`, `bottle-lamp-carrier`, and
  `social-media-sign-production.scad`). For those parts "regenerate it from source" is not currently
  true.
- **182 committed STLs do not match what their own source produces.** Not export noise — real
  divergence: `usb-cloud-holder--coupon-trp-line2-rail.stl` is 50784 facets / zmax 1.5 as committed
  and 53126 facets / zmax **1.6** when rebuilt. Sources moved on without the exports being re-run.

Until both are resolved, treat a rebuild as *newer* geometry rather than as a reproduction of what
is committed, and re-verify before printing from it.

### Generator triage — 2026-08-21

A fresh `rebuild-all.sh --check --jobs 4` run built **64** generators and failed **11**. The check
also changed 39 tracked exports; those diagnostic rebuilds were restored because a rebuild is newer
geometry, not an approved reproduction.

| Generator | Failure | Disposition |
|---|---|---|
| `bottle-lamp-base-rope-tower-coupons.py` | `vsocket()` now requires `open_off` | **FIX** on the rope-tower revision: active coupon, shared-helper API drift; recover the original opening offset rather than guess. |
| `bottle-lamp-stopper.py` | OCC `Null TopoDS_Shape` | **FIX** on next stopper geometry revision; live printed mechanism, genuine geometry failure. |
| `bottle-lamp-carrier.py` | OCC process abort | **FIX** using a minimal-turn repro and one build/process; live carrier, genuine swept-loft failure. |
| `social-media-sign-base-slot-coupon.py` | removed `SLOT_DEPTH` | **RETIRE**: the slot mechanism was replaced by TK page seats. |
| `social-media-sign-coil-seating-coupon.py` | removed `SLOT_DEPTH` | **PORT only if CBF is still needed**; split its coil fixture from the dead slot dependency. |
| `social-media-sign-leaf-swing-coupon.py` | removed `SLOT_DEPTH` | **RETIRE**: leaf architecture moved to one-piece MPL/TK seats. |
| `social-media-sign-production.scad` | OpenSCAD hard abort | **RETIRE** if the CadQuery production source is authoritative; otherwise isolate a minimal repro before re-enabling `--all-sources`. |
| `pcc2-compression-ratchet-coupons.py` | old preload assertion now reads 1031.6 mm3 | **RETIRE**: old tapered/ratchet context was replaced; QZ's current qualification lives in the registry. |
| `pcc2-coupons.py` | removed `UPRIGHT_BACK_W` | **RETIRE or rewrite against the current uniform upright** only if it remains a requalification article. |
| `pcc2-rib-coupons.py` | rejected rib now intersects by 4.35 mm3 | **RETIRE**: longitudinal rib family was rejected. |
| `pcc2-vjoint-gauges.py` | removed `UPRIGHT_FRONT_W` | **PORT** to current V-joint geometry if VOM/VOZ must be requalified in another context. |

The retire/conditional-port entries are design-history debt, not rename debt. Move them out of
generator discovery only when their corresponding registry samples/evidence remain traceable. The
FIX/PORT-live entries retain active requalification value.

A part with both `src/x.py` and `src/x.scad` has two generators racing for one `stl/x.stl`;
`rebuild-all.sh` prefers the `.py` (which is what produced the committed bytes for `hose-clip`) and
prints `SKIP:` for the `.scad`. `--all-sources` overrides.
- **The primary toolchain declarations are pinned** in `platform/toolchain.lock`;
  `pipeline/toolchain.sh` reports drift for every declared version. Coverage is not yet complete:
  tracked FreeCAD and NumPy/Pillow generators are outside the lock (see the 2026-09-04 audit).
  Confirm the actual producer is covered; if it or a version moves, re-verify rather than assume.

`releases/` is exempt and always tracked. A shipped revision is frozen evidence, not a rebuild target.

## Everything happens in `ai-projects/3d-printing`, never in a sibling copy

**Justin's rule, 2026-09-18:** all work on this repo happens in the checkout at
`ai-projects/3d-printing`. No `git worktree add`, no `ai-projects/3d-printing-<anything>` folders.
Agents kept creating them (`3d-printing-lap-shim`, `3d-printing-rev-filtration-downturn`,
`3d-printing-rev-gutter-backstop`), and each one stranded a part where the prepare contract and
`handoff.sh` refuse to build from it (`docs/preparation.md`: a linked worktree is not a delivery
root). `bench.sh start --worktree`, which made exactly these folders, now refuses.

When this checkout is dirty with **another session's** uncommitted work, `start` refuses (exit 4).
Do not stash that work and do not reach for a copy. Branch in place, `git switch -c rev/<slug>`
from wherever HEAD is, and stage only your own paths. The other work rides along in the working
tree, untouched. `main` can only be checked out once, so `land` from here.

## What this does not protect

- **The printer.** Gcode already uploaded does not roll back. `releases/<rev>/` freezes a shipped
  plate for exactly this reason.
- **`build/`.** Gitignored and regenerable — 913 MB of it. Nothing here versions it.
- **The disk.** There is **no git remote**: 1.23 GB of history exists on one machine. Branches and
  tags are recovery from *your own mistakes*, not from a dead drive.
