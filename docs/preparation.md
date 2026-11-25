# Bounded preparation and source identity (platform 0.5)

The coordinator **calls the existing stages**. It does not replace CAD, verification, slicing,
rendering, postprocessing or handoff, and has no send stage. `READY` means **present and STOP**.
A recipe's `kind` describes the question; it does not relax any gate or supply physical evidence.

## Start here

Before preparing a new print plate, record its independently requested ID/quantity list and named CAD references in the exact output directory. [Inventory commands and limits](../platform/pipeline/README.md#requested-versus-sliced-inventory). Preflight checks that both are present; final handoff checks the actual sliced pieces by ID. An installed assembly or an input-file count isn't a plate inventory. Changed requests use a fresh output.

```sh
# Consumer: its thin wrapper supplies the canonical owning checkout.
scripts/platform/prepare.sh parts/<category>/<part>/prepare.yaml --preflight
scripts/platform/prepare.sh parts/<category>/<part>/prepare.yaml

# Platform bench: the same coordinator, with explicit ownership.
platform/pipeline/prepare/prepare.sh --root "$PWD" parts/<category>/<part>/prepare.yaml
```

Preflight aggregates missing tools/resources, malformed intent/options, incorrect ownership,
uncommitted selected inputs, and the existing per-part design/status qualification errors. An invalid reference role is a spec fix, not a reason to build first. This early feedback does not replace the final handoff. It is read-only. Source/spec/declared inputs/recipe/check code must be
checkpointed before preparation; new exports may need their own focused checkpoint afterward.
Commit **only the relevant paths**. Never stash, reset, stage or finish another part for this job.

**One pass, not two.** While iterating, build with the DECLARED build and render with the declared
render, commit the source together with what they wrote, then prepare; its build stage then says
`REUSE`:

```sh
platform/pipeline/generate/build.sh parts/<category>/<part>/src/<part>.py parts/<category>/<part>/stl
platform/pipeline/preview/render.sh parts/<category>/<part>/stl/<part>.stl parts/<category>/<part>/preview
git add parts/<category>/<part> && git commit          # source, spec, recipe, stl, step, preview stamps
platform/pipeline/prepare/prepare.sh --root "$PWD" parts/<category>/<part>/prepare.yaml
```

Running the bare generator (`python src/<part>.py`) while iterating and leaving the declared build to
prepare makes every plate two runs: the first stops on its own new exports being uncommitted, and the
bare run's bytes are not the declared build's (STEP timestamps, triangle order), so they cannot be
committed ahead. Measured 2026-10-01 to 2026-11-11: 2.6 prepare runs a plate here, 126 of 175 repair
notes being that checkpoint, against 1.0 in the consumer repo, which follows the order above.

The first checkout in Git's worktree registry is the canonical owner. Linked worktrees remain
useful for software development, not physical delivery. Both declared build and final handoff
reject them. The recipe lives with the part; its plate must be under the same owner's `build/`.
A preparation record freezes absolute owner/part locations and cannot be relocated as authority.

## Part source contract

```yaml
primary_stl: stl/example.stl
primary_step: step/example.step
build:
  source: src/example.py
  outputs: [qa/geometry.json]   # additional generated outputs, optional
  tool_resources: []           # installed non-repository resource files, optional
source_dependencies:
  - repository: .
    paths: [parts/another-part/src/interface.py, measurements/interface.csv]
  - repository: ../shared-platform
    paths: [parts/_lib/probe.py]
```

Paths are literal, repository-relative, existing files/directories. No globs, `..` escapes,
symlinks, whole-repository path selectors, empty directories or malformed entries. A dependency's
repository location is relative to the owner and must resolve to a Git root. List genuine native
STEP/data dependencies too, not just imports. The selected `spec.yaml` and `src/` are implicit;
a local `parts/_lib` is a conservative implicit shared scope. Prefer precise explicit file lists
for external shared/cross-part inputs so unrelated revisions are not accidentally coupled.

`build.sh` invokes `generate/build_provenance.py` for declared Python/CadQuery generators. It:

1. snapshots declared source/data plus producer code and interpreter/package/font identities;
2. removes **only declared outputs**, then executes the actual generator in a fresh process;
3. rejects observed undeclared repository imports/Python file reads and non-installed external
   reads; explicitly declared installed resources are content-bound, not falsely called Git-clean;
4. requires new nonempty outputs, canonicalizes STEP/STL, counts valid STEP solids and rechecks
   inputs before writing `build/.producers/<part>/build_manifest.json`.

This observer is **not** a sandbox or a proof of arbitrary native/C++/subprocess dependency
closure. Authors must declare those inputs. Installed tool resources and runtime versions are
part of the toolchain contract; unresolved coverage is a blocker, never a reason to guess clean.
A missing installed cache/resource is a tool-setup task, not permission to omit its identity.

Handoff requires current producer inputs/tools/outputs plus committed selected inputs and exact
exports. Actual file bytes are compared to Git HEAD blobs, so `assume-unchanged`, ignored or
untracked relevant files cannot conceal a dirty input. External repositories carry their own
commits and file hashes. `source.dirty: false` means **this recorded scope**, not the whole
workspace. Producer tool code is SHA-bound (like compiler binaries), not a global cleanliness gate.
An unrelated HEAD change cannot make a stale export fresh; a changed generator with yesterday's
committed STL still requires generation. Never manufacture a producer record for existing bytes.

Migration is forward-only at the next plate. Older non-declared generators remain buildable, but
cannot obtain a new authored-part handoff without producer evidence. The initial captured path is
Python/CadQuery with explicit STL and STEP; other producers are not silently cacheable.

## Recipe

Use `parts/_TEMPLATE/prepare.yaml` and replace its deliberate placeholders. It declares:

- experiment/prototype/release kind, bounded objective, stopping condition and owner-relative plate;
- explicit machine/process/filament and other `slice.sh` options (no model/output positionals);
- complete installed profile stores and actual executable/deployment resources behind wrappers;
- other tool resources affecting drawing/verification;
- optional argument-array checks and their bounded input paths; repository file/directory arguments
  are captured too (including a unittest discovery directory);
- tracked post-hooks, separately declared rather than hidden in `--set post_process`.

**New recipes explicitly default to no brim:** include `--brim`, `'0'` in `slice_args` (as in
`parts/_TEMPLATE/prepare.yaml`), and verify effective `brim_type=no_brim` / `brim_width=0`.
Omitting the option can inherit a preset; reusing an old recipe can carry forward an unnecessary
brim. Nonzero settings require demonstrated necessity for this plate, a recorded rationale and
removal plan, and disclosure before approval. See [the owning brim rule](workflow.md#brims-are-an-exception-not-a-default).
Do not rewrite completed plates as brimless; use a fresh recipe/output/handoff for any changed
print settings. No new automatic brim gate is implied by this policy.

Recipes are trusted local source, not a security sandbox. The coordinator does not set approval,
call send, run autonomous fixes or contact a printer. It strips inherited `APPROVED`, `FORCE` and
`*_OK` bypass flags. Domain checks/generators must also remain preparation-only.

The initial coordinator prepares **one part's primary STL**, which may contain many detached
samples. Its count comes from the valid primary STEP, not the number of input files. The normal
slice/handoff stages still support multi-input plates; non-primary exports need their own explicit
count evidence rather than borrowing the primary STEP's count. CAD views use export coordinates;
the support plot depicts the actual sliced pose. Neither is a physical fit claim.

## Complete artifacts and safe reuse

The coordinator owns build, exact verify + declared checks, five stamped views, three labelled
orthographic drawings and label map, 3MF/G-code/config/identity, deterministic slice verification,
and the support plot **even for zero support**. Independent review failures are collected in one
blocker report. A failed CAD gate does not proceed to slicing. Required old outputs are removed
before a producer reruns, so a best-effort render cannot inherit yesterday's missing drawing.

`<plate>/preparation.json` records stage keys, every output SHA, actions/durations, attempts and
READY/BLOCKED state. Keys use relevant producer inputs, dependencies, executable/code hashes,
package/resource identity, settings/preset bytes and post-hook hashes—not mtime or global HEAD.

| Change | Reused / invalidated |
|---|---|
| Nothing relevant | Reuse build/verify/views/slice/plots; run final readiness/identity/handoff again |
| Unrelated part/docs or HEAD only | No invalidation |
| Generator/spec/CAD dependency | New producer required; all affected geometry stages invalidated |
| Recipe process/material/presets only | CAD and CAD views/checks reused; slice and affected final-G-code stages run |
| Check source/input | Relevant verify stage, not CAD generation |
| Missing/tampered output | Its producing stage reruns; downstream changed-byte consumers invalidate |
| Post-hook/final G-code change | Current coarse slice stage is regenerated, then affected final checks/plot/handoff; CAD reused |
| Uncertain semantics of a spec/tool change | Conservative invalidation, never guessed non-geometric |

Slice owns postprocessing today; the coordinator deliberately does not invent a parallel metadata
writer or trust a mutated final G-code as a raw slice. Finer post-only reuse needs a separately
bound pre-post artifact contract. Broad installed preset directories may conservatively invalidate
slice reuse when an unrelated preset changes. These are bounded extra work, not false cache hits.

A lock prevents two coordinators writing one plate concurrently. Inputs/tools/recipe/check source
are rechecked at the end. Final handoff is never cached and no approval is reused.

## Stop rules and measuring improvement

One initial pass; after a blocker, **one** changed-input repair:

```sh
scripts/platform/prepare.sh <part>/prepare.yaml \
  --repair-reason 'specific blocker; changed input; next action'
```

Further attempts require `--escalate-reason` with the concrete blocker/change/next action.
An unchanged failed attempt is refused even with a reason. An interrupted pass is a failed pass,
not permission to start an invisible loop. No script makes the repair or spends another lap by
itself. Missing/failed/stale artifacts never become READY to meet the 15-minute operating target.

Use the first three bounded jobs to compare brief-to-handoff time, stage reuse/repetition and
causes, repair loops, print cost, and whether the physical observations answer the question.
Recorded command durations are **not** full agent lead time or a proven SLA. After READY, obtain
separate human approval; only a subsequent authorized send action may reach the printer.
