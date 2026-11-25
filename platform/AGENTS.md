# AI-CAD Pipeline — Portable Agent Contract

This file travels with `platform/`. A project invoking these scripts is a **consumer** of this
contract even when its parts, specs and `build/` artifacts live in another repository. The full
3d-printing bench adds repo-local versioning rules in `../AGENTS.md`; consumers add domain policy
in their own root `AGENTS.md`.

For a new client or a mid-task model switch, use the [start/resume card](pipeline/AGENT-START.md). It works by CLI or by pasting the JSON; no provider-specific memory or hook is assumed.

## Process authority

Use `../docs/workflow.md` as the canonical idea → spec → digital loop → physical gate process.
CAD geometry is refined by the fast digital loop, not by substituting a generic software-plan flow.
Formal plans/TDD remain appropriate for changes to the pipeline software itself.

## Hard rules — portable and non-negotiable

1. **Never upload or start a plate without a fresh human approval.** Run
   `pipeline/handoff/handoff.sh <outdir> [<part_dir>]`, present its artifact paths, and STOP.
   Only after the human approves that exact plate may their command set `APPROVED=1` for
   `pipeline/send/send.sh`. An agent must never supply `APPROVED=1` from its own initiative,
   earlier intent, or a chained “slice → handoff → send” command. Upload/staging counts as send.
2. **One version per handoff.** `slice.sh` records STL hashes and `render.sh` stamps previews.
   `handoff.sh` exit 10 means stale/mixed geometry; re-render or re-slice rather than bypassing it.
   Exit 12 means a spec exists and FAILED its truth, primary-artifact, fit-core, or probe gate —
   there is no bypass for that.
   Exit 18 means the output directory has a recorded scope hold: name the choices and ask the question; READY or an approval flag cannot clear it. See the [scope command contract](pipeline/README.md#when-a-ready-plate-is-not-the-requested-plate).
   Exit 13 means a model on the plate under `parts/` has no `spec.yaml` at all, so no gate ran on
   it; `NO_SPEC_OK=1` bypasses 13 only and is recorded into `handoff.txt` for the human and for
   `send.sh`. Exit 14 means exact B-rep validity is absent/stale; exit 15 means the future
   Restore/Originate or status-to-physical-evidence contract is incomplete; exit 17 means
   deterministic verify-slice is not PASS. None has a bypass.
   Part dirs are DERIVED from `plate_geom.txt`; the `[<part_dir>]` argument only adds one.
   A consumer repo may carry its own `.spec-truth.allow` ratchet for legacy specs, exactly as the
   platform does; without one, an unprovenanced fit-bearing spec refuses at 12.
   Any post-slice gcode transform invalidates the prior verification and handoff until all affected
   gates are rerun.
3. **Gate policy:** deterministic failures BLOCK — slicer failure, missing/empty/bad gcode,
   off-bed toolpaths, stale artifact identity, missing/stale profile + effective-config identity,
   or a declared exact invariant. Mesh/DFM heuristics
   WARN because they are sampled or approximate. Never promote a heuristic to a hard block merely
   because its warning looks severe; add a deterministic source assertion when the invariant is real.
4. **Orientation is part of the design evidence.** Prefer a broad flat bed footprint over a clever,
   tippy orientation. A mating surface changing orientation reopens its coupon gate. For structural
   parts, record orientation in the spec; also inspect support-removal paths — a supported bore can
   be a worse fit failure than weaker layer direction.
   **No brim by default: explicitly use `--brim 0`.** Only a necessary, evidence-backed exception
   for this plate may add one; disclose its reason, minimum width and removal plan before approval.
   See `../docs/workflow.md` → “Brims are an exception, not a default”. Copied recipes/material
   names are not proof of necessity. This is authoring/review policy, not a new automatic gate.
5. **Coupon before commitment.** Fit-critical, long, threaded or load-bearing work prints the
   smallest production-orientation/material article that answers the question before the full part.
6. **Physical claims belong to the human.** `CONFIRMED=1`/passed tags, fit confirmation, functional
   success and material qualification cannot be inferred by an agent from a clean print or green
   CAD. An agent may initialize a `planned` `qa/iterations` record from the handoff manifest, but
   must leave actual machine/material/lot/environment, operator/readings/observations/verdict/
   attestation empty. What the person SAYS about a print may be written down for them
   (`qualification_check.py report`: their own words, when, where they were said, who wrote them;
   state `reported`). That is a report and never an evaluation: no check is evaluated by it and no
   status or passed tag accepts it. A passed tag requires the
   committed current record and stores its path + SHA-256; `dim-verified`/`released` status is
   invalid until that tag contains the exact record bytes.
7. **Artifacts live with their canonical owner.** Resolve it before CAD; linked worktrees are not
   physical delivery roots. A consuming venture writes plates to its own `build/`, not the shared
   bench. Use `pipeline/prepare/prepare.sh` through the consumer wrapper for bounded preparation
   (see `../docs/preparation.md`). Part + declared dependency source identity replaces whole-repo
   cleanliness: never stash, reset, stage or finish unrelated parts to get a handoff. Missing/stale
   producer evidence blocks. One pass plus one reasoned repair, then explicit escalation; READY
   means STOP, not an invitation to add research or send.
8. **AI models and datasets are advisory inputs, not design authority.** Retrieved examples,
   benchmark output, and vision-intake drafts may inform a human-written or human-reviewed source
   change, but they never satisfy probes, dimension provenance, fit-critical checks, or handoff.
   Keep licensed/gated corpora inside their registered use tier; do not copy non-cleared examples
   into production source or training corpora.
9. **Consumers adapt invocation, not semantics.** A downstream repo may wrap platform entry points
   to resolve paths/defaults, but must not fork pipeline stages or weaken gate policy locally.
   Generic workflow gaps are upstreamed here with tests and docs; domain policy stays downstream.
   See `../docs/consumer-contract.md`.

## Required handoff artifacts

Present the `.3mf`, exact gcode, five real-geometry views, support plot, verify reports, geom stamp,
`slice_meta.json`, the explicitly-not-evaluated `qualification_manifest.json`, and any required
internal section/drawing. Quote part count, material, orientation, time and grams, plus the adhesion
decision: no brim by default, or its necessary exception and settings. A summary without paths is
not a handoff.

## Software changes

Run `pipeline/test.sh` before committing pipeline changes. Preserve fail-closed defaults, exercise
both success and failure paths, and update `pipeline/README.md` when an entry point changes.
