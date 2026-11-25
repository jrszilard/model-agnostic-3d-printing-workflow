# Consumer contract — use the platform, feed the platform

`platform/` is reusable engine code. A consumer repository owns its domain data, official parts,
plates, customer claims, and release records. The platform owns generic CAD/print machinery.

This contract exists to prevent two failure modes:

1. a consumer silently reimplements or forks the workflow;
2. a hard-won consumer lesson stays local even though the next consumer will hit the same issue.

## Dependency direction

```text
consumer repo  ──invokes/imports──►  3d-printing platform
platform       ──never imports────►  consumer repo
```

Consumers should call pipeline entry points through a thin local adapter. The adapter may resolve
paths, environment variables, and domain defaults. It must not change gate semantics or copy
pipeline stages locally.

Curated reusable CAD libraries may be imported from `parts/_lib`. Domain-specific data, schemas,
and policy stay in the consumer.

## Forward-only adoption

Platform adoption is evaluated at the **next design/plate boundary**, not by bulk-repairing a
consumer's archive. Existing prints and records remain historical; missing evidence is never
reconstructed. Any new, revised, or reprinted geometry uses the current platform contract when it
next enters the workflow. A legacy file that stays archived needs no migration; a legacy file put on
a future plate gets no legacy bypass.

For a replication/Restore task, the consumer owns reference identity, measured interfaces,
replicate/deviate decisions, fitment, and real-mate acceptance. For an Improve/Originate task, it
owns purpose, envelope, interfaces, load/environment, and functional acceptance. In both cases the
platform supplies the same digital/physical iteration spine, and only generic, context-qualified
lessons flow upstream.

At that boundary each consumer part uses the platform's `design:` contract and structured
`qa/iterations` record. `handoff.sh` writes a machine-only, explicitly not-evaluated manifest bound
to source/spec/verify/model/G-code/profile/config bytes; an agent may initialize a planned record
from it. Only the observing human fills actual printer/spool/lot/environment, process deviations,
raw readings, actual-mate/function results, and attestation. Consumer-domain IDs and evidence refs
stay in the consumer record.

## Consumer adapter

A consumer should provide a small manifest and wrappers, for example:

```text
platform.consumer.yaml
scripts/platform/prepare.sh
scripts/platform/build.sh
scripts/platform/render.sh
scripts/platform/verify.sh
scripts/platform/slice.sh
scripts/platform/verify-slice.sh
scripts/platform/handoff.sh
scripts/platform/qualification.sh
scripts/platform/send.sh
```

The manifest names the platform root, contract, workflow, and entry points. Wrappers should be
one-line executors after environment resolution. If a wrapper grows policy, that policy needs a
review: is it consumer-domain policy, or is the platform missing a mechanism?

Platform 0.5 adds [bounded preparation and producer identity](preparation.md). The consumer's
`prepare.sh` supplies its canonical root; per-part recipes specify domain checks and print intent.
Declare actual cross-part/external source dependencies in the part spec. The source gate binds
committed selected inputs/exports, not a whole-repository clean status; other parts must remain
untouched. Versioned source plus old output is insufficient without current producer evidence.
Installed tool/preset/resource bytes participate in reuse; profiles never attest an actual spool.

## Digital-only local evaluation

For separately approved synthetic software evaluation, the explicit
[isolated evaluation interface](../platform/pipeline/isolation/EVALUATION.md) binds selected sealed
source/base/runtime/output identities without manufacturing a Git checkpoint. This is not a fallback
for part preparation or a physical gate exemption. Its distinct digital schema is rejected by the
manufacturing producer validator. Consumer specimen/rights/context policy stays local; containment
and artifact machinery stay upstream. `verify/geometry.py` provides the shared import-safe geometry
observations without manufacturing CLI/registry imports. No upload/production runtime is implied.
[Passive mesh-report projection](../platform/pipeline/preview/MESH_REPORT.md) is a separate generic
no-CAD diagnostic seam: consumers bind admitted saved-file reports/parents/hashes and actually inspect
the views. No canonicalization of originals, manufacturing stamp or hidden-surface/fit proof.

## Upstream-back rule

When a consumer hits a workflow gap, classify it before fixing it:

- **platform-generic** — any consumer could hit it. Land the mechanism in this repo with tests and
  docs, then switch the consumer to it.
- **consumer-domain** — tied to catalog, customer, vehicle, legal, brand, or business policy. Keep
  it in the consumer.
- **mixed** — split the generic mechanism from the domain policy. Upstream the mechanism; keep the
  domain rule local.

If the classification is unclear, treat it as mixed and stop for review. Do not hide uncertainty by
forking a pipeline stage.

**These three strings are the contract, and this file is where they are defined.** A consumer's
validator must accept exactly `platform-generic`, `consumer-domain`, `mixed` and must not invent a
local spelling — within hours of this contract being written, one consumer's validator hardcoded
`venture-domain` instead. No record was ever actually rejected, because every record happened to be
`platform-generic`; the two vocabularies overlapped everywhere except the one case, so the first
record that needed `consumer-domain` would have been the one to fail.
The generic word is deliberate: the next consumer may not be a venture. A consumer document
may **point at** this list; it may not restate it, because a restatement is a copy that drifts.

## Feedback record

A consumer should keep a lightweight feedback register for platform issues and local workarounds.
Minimum fields:

- what happened and where;
- classification: `platform-generic`, `consumer-domain`, or `mixed`;
- local workaround, if any;
- upstream fix status;
- next review date while unresolved;
- platform commit/files and consumer cleanup once upstreamed.

An unresolved generic/mixed record without a review date is drift. An `upstreamed` record without
consumer cleanup is not done.

## Definition of done for upstreaming

A consumer lesson is upstreamed only when all of these are true:

1. the platform mechanism exists here;
2. platform tests cover success and failure behavior;
3. platform docs/templates teach the intended use;
4. the consumer adopts the mechanism;
5. the local workaround is removed or reduced to a thin domain adapter;
6. the consumer feedback record points at the platform commit/files.

## What each version added, for a consumer deciding what it is pinning

- **0.6.0** — `provenance: pending-measurement`, a fit-critical nominal declared unproven with the
  iteration (`closes_with`) and date (`next_review`) that close it. It never joins `FIT_TRUSTED`
  and an overdue date fails again. `verify.py` reports it as a third verdict word, `DEBT`, which a
  `kind: prototype`/`bench-experiment` plate may cross and a `release` may not — because the
  measurement that clears it can only come off a printed article, and refusing to print one was a
  closed loop. **A consumer on 0.5.0 that writes `pending-measurement` gets a hard refusal**, which
  is why the pin moved rather than staying quiet. Also: `platform/pipeline/gates.txt` registers
  every gate's verdicts and exit codes, and `next_action.py` answers what state a part or plate is
  in — both read-only additions that change no existing behavior.

## Versioning

`PLATFORM_VERSION` names the platform capability set against which the consumer was last
re-verified. The consumer boundary validator compares it with this repo's `VERSION`, so drift is
visible. It remains a **staleness detector, not a compatibility guarantee or frozen API**; entrypoint
stability remains deferred under `docs/roadmap.md`. A behavior/schema bump is complete only after
the consumer pin/test is updated or an explicit migration blocker is recorded.
