# Explicit isolated digital evaluation (local experiment)

Optional consumer-facing checks (September18): `verified_stage.VerifiedStages(batch, journal,
supervisor_sha256=..., runtime_root=...).run(label, stage, case_deadline)` delegates to the journal
and existing run_stage, then rejects identity/scope/cleanup/output drift and any simulation marker.
No alternate default transport or execution permission; callers still need the complete approved
Batch/control/runtime/source contract. `inventory_check.verify_inventory(root, pinned_inventory,
observations)` is passive installed-byte comparison, not native launch or provenance by itself.
46 focused offline tests now include eight returned-stage/three inventory checks. Studio's separately
approved browser/native27-launch attempt passed and CLOSED; no unused-budget or manufacturing grant.

Sanctioned Python entrypoints: `evaluate.Batch`, `evaluate.run_stage`, `staging.source`,
`staging.SealedInputs`; explicit live controls in `evaluation_controls.py`. This is **not** a fallback
for `generate/build.sh` / `build_provenance.py`, manufacturing provenance, or a job/API service.
Optional evidence helpers (September17): `evaluation_journal.Journal.run_stage/run_control` delegate
unchanged containment calls, saving input bytes before dispatch and raw records before semantic checks.
Unreturned/cleanup-uncertain calls retain exceptions, never manufactured success/cleanup. Existing
`evaluation_controls` functions accept optional `stage_runner`/`control_runner` for this journal;
default behavior is unchanged. `repair_budget.claim_once(budget_path, expected_sha256, destination)`
exclusively claims an independently pinned fresh budget. The consumer must fix ONE claim destination
per approved attempt, independent of output paths; partial/startup-failed claims remain spent. This
is trusted local single-controller tooling, not authority, durable concurrent application admission
or hostile-path isolation. Seven new offline checks;35 focused isolation tests pass. Studio's separate
hosted-envelope evaluation then used these helpers once at32/32; no generic geometry qualification.

The record schema is `isolated-digital-evaluation/v1`, not manufacturing schema 1. The actual
manufacturing validator rejects it. Existing source, verification, physical and handoff gates apply
unchanged to any future part/plate. No `.git` fabrication, source checkpoint or physical qualification.

Use only for a separately approved, trusted, synthetic-only local evaluation. A thin consumer wrapper
starts an existing systemd-user transient unit named `cad-evaluation-*`, with Delegate=yes,
CPUQuota=200%, MemoryMax=2147483648, MemorySwapMax=0, TasksMax=64, KillMode=control-group and
`--collect`. RuntimeMaxSec and the outer timeout must fit the **remaining original window**, including
stop/kill margins, not start a fresh 900-second supervisor allowance. The trusted single-threaded supervisor
constructs **one** `Batch(existing_deadline_epoch)`, calls `attach()`, reserves each fixed host control,
and uses `run_stage` for every remaining control/runtime/CAD/check. No automatic retries or reset.
Batch counts this supervisor plus at most 31 isolated workers; failed startup consumes a reservation.
This in-process ledger is NOT a persistent/concurrent admission service or an authorization boundary.

## Inputs, execution and acceptance

- `source(canonical_owner, relative_name, expected_sha256)` independently reads regular bytes,
  rejects symlinks including ancestors/hardlinks/specials/empty/oversized/changing files, and returns
  bytes plus truthful owner/path/hash/length mapping. The caller retains this mapping outside the
  worker; canonical ownership is operator-selected, not established by a hash or Git fiction.
- The caller supplies `inputs: dict[str, bytes]`, including `main.py`, and an exact output-name tuple.
  Separate broker-created requests and accepted parent bytes from selected source provenance.
  `SealedInputs` captures immutable Linux memfds with WRITE/GROW/SHRINK/SEAL seals. Inputs and the
  inspected coordinator/protocol code are installed with Bubblewrap `--ro-bind-data`, not scratch
  copies. Up to 32 selected code/data files, each <=16 MiB, <=32 MiB total, per sealed mapping.
- Mandatory user/PID/mount/IPC/UTS/network/cgroup isolation, disabled further user namespaces,
  cleared environment/capabilities, no-new-privileges, read-only root and minimal devices. Read-only
  `/usr` and optionally the explicitly selected installed CadQuery environment at `/runtime`;
  **no workshop, registries, /home, host /etc, /run, /sys, writable host directory, socket or printer**.
  FreeCAD alone gets sealed synthetic `/etc/passwd` and `/etc/group` (worker UID/GID, `/work` home);
  no host identity records are read/bound. Exact directory contents/bytes, NSS lookup and read-only
  behavior must pass a non-CAD control in that same profile. Other profiles retain no `/etc`.
  Only `/work` is writable: one 128 MiB tmpfs, `/tmp` alias. No host output directory is mounted.
- Runtimes are fixed command profiles: system Python, installed CadQuery Python, or system Python
  importing the installed FreeCAD/Part bindings. No shell command input or permissive fallback.
  Environment fixes HOME/TMPDIR in scratch, OpenBLAS/OMP to two threads, offscreen Qt and the selected
  FreeCAD library search directory. Installed tools remain host-mutable; not a production image pin.
- `case_deadline=batch.case()` covers the whole create/edit/check case (90s); each stage is <=30s,
  constrained by the original monotonic batch deadline (<=900s). Kernel quota/memory/swap/tasks are
  read back. Failed/timed-out stages are whole-cgroup killed, reaped and required unpopulated/removed.
- Child stdout AND stderr become the bounded 1 MiB log channel. A separate artifact channel carries
  a small binary length/name protocol: exact expected flat names, <=8 nonempty files, <=32 MiB total.
  Worker collector rejects links/specials/extra/missing/count/size violations and living descendants.
  Host independently bounds/decodes/hashes raw bytes. No archives, worker-supplied hashes or paths.
  **EOF is not success.** No bytes are admitted until exit 0 AND confirmed entire-cgroup cleanup.
  Deadline, nonzero exit, malformed/truncated/duplicate/oversized frame or cleanup failure admits none.
- Fresh verification is another stage with accepted exact bytes separately sealed read-only. Accepted
  byte transport is not a geometric check, publication, rights determination or fit/print approval.
  Keep originals and any later normalization as different bytes; this path never canonicalizes them.

## Geometry interface (shared, not copied)

`../verify/geometry.py:cad_integrity(part_dir, spec)` is the import-safe geometry-only implementation
extracted from `verify.py`; `_read_step` and `_pick` are shared helpers. It imports only os/Part/Mesh,
not the manufacturing CLI or parts registries. The existing CLI imports the same functions and keeps
its unconditional FreeCAD-script main, manufacturing checks and deterministic/advisory classification.
Cache: one resolved path → one shared shape per process. Inputs must stay frozen. Never mutate or
tessellate that cached shape; use another private read/copy. Changed bytes need a fresh process.
This API returns observations, **not a manufacturing stamp/verdict**. Consumer specimen assertions
(e.g. exactly one solid/no loose topology) remain local deterministic operation requirements.

## Passive saved-mesh diagnostics

After a fresh contained checker extracts bounded numeric topology from an exact saved STL,
[`preview/mesh_report.py:mesh_svg`](../preview/MESH_REPORT.md) can project iso/top/side SVGs without
any CAD parser/import/process or source normalization. The consumer must bind accepted report,
artifact and parent-stage identities, retain actual hashes and inspect the views. Back-face culling
and centroid ordering are diagnostic only; no general hidden-surface or geometry/fit proof.
Do not run manufacturing `render.sh` on retained originals or outside the live launch budget.

## One reasoned manual HOME-initialization repair

`repair_budget.py` reserves a separate one-shot repair **before** a supervisor launch. It retains
an exclusive 0600 reservation even on failed startup, links/hashes the unchanged closed attempt and
original budget, carries all prior consumption, and limits the repair to 13 further launches including
its supervisor. `Batch(carried_launches=..., launch_limit=...)` never resets that allowance. No deadline
renewal, reopening/editing the closed record or automatic retry. The studio's selected repair skips
maximum geometry to fit; the extra three unspent launches do not authorize another repair.

The original studio HOME-repair attempt and its reservation are closed/spent. The corrected
single-use identity FD routing was subsequently live-proven in a **new** September 11 batch:
exact identity/NSS/read-only control and real FreeCAD1.1.3/OCCT7.9.3 initialization pass. No host
identity records or broadened profile were needed. That31-launch batch closed after a studio negative
fixture exported as an assembly and hit a different rejection reason; positive nominal/min/max
saved-STEP cases pass, not the whole compatibility matrix. No automatic retry or reopening.

## Evidence and tests

`runtime_inventory.py` inventories installed environment bytes and dependency/license metadata
without importing CAD. `runtime_probe.py` imports real bindings **only inside a contained stage** and
hashes actually mapped native libraries for host comparison. Inventory/selected system hashes before
and after detect observed drift, not concurrent-host immutability, hostile isolation or redistribution
license clearance. Preserve license/source obligations before any later runtime distribution/service.

Offline (no namespaces/CAD):

```sh
python3 -m unittest discover -s platform/pipeline/isolation -v
python3 -m unittest discover -s platform/pipeline/verify -p test_geometry_api.py -v
python3 -m unittest discover -s platform/pipeline/verify -p test_verify_step_cache.py -v
PYTHONPATH=platform/pipeline/verify python3 -m unittest test_spec_primary_check.TheFallback.test_pick_mirrors_verify_py -v
```

Live controls consume the already-bounded caller batch; never run them automatically as unit tests.
The offline `isolation/test_*.py` suite is registered in the normal `platform/pipeline/test.sh` runner.
That broad runner still includes CAD/corpus work and has NOT been run for this increment; focused tests do not replace its
required pre-commit run or establish full regression coverage. No commit or production API promise.
