# Non-CAD host containment controls

The separate explicit [digital-evaluation API](EVALUATION.md) adds sealed inputs, bounded output
admission and fresh-worker orchestration. This page still describes only the original fixed probe.

`check_host.py` is a **fixed control experiment**, not a general command/CAD runner, production
sandbox, intake adapter or permission to process files. It does not change existing producer,
verification, advisory-AI or physical gates. No CAD library is imported.

It checks an already approved Linux/systemd-user/Bubblewrap evaluation profile:
- Required outer cgroup: `cpu.max=200000 100000`, `memory.max=2147483648`,
  `memory.swap.max=0`, `pids.max=64`, delegated cpu/memory/pids controllers.
- Six disposable worker namespaces: isolation/dummy canaries, 128 MiB scratch ENOSPC,
  cgroup OOM, process EAGAIN, combined 1 MiB stdout/stderr cap, detached-descendant deadline cleanup.
- Exhaustion uses **stricter child controls** (64/256 MiB and 16 tasks); outer values are read back,
  not inferred from `systemd-run` success. Two-CPU scheduling affinity is observed; CPU quota caps
  equivalent CPU time. This does not prove an adversary cannot widen affinity or select other cores.
- No whole checkout, `/etc`, host writable workspace, network route, device passthrough, inherited
  sockets or secret-bearing environment is provided to workers. `/usr` is an existing trusted
  read-only runtime, not an immutable dependency image. Minimal pseudo-devices are read-only.
- `/tmp` aliases the sole 128 MiB writable tmpfs. Root and `/dev` are read-only. No final CAD artifact
  acceptance or 8-file/32 MiB output validator is implemented by this program.
- Kill/reap the **entire worker cgroup**, wait for `populated 0`, then remove it, even after a worker
  exits normally. The user manager collects the transient supervisor unit afterward. Outer runtime
  and stop deadlines are still needed if the supervisor crashes.

The persistent `platform/ai/benchmark.py` worker remains separate: its per-process RLIMITs, broad
`/etc` mount and writable host workspace do **not** satisfy this profile. No local copy/fork or
semantic change to that worker was made. Any eventual shared runner extraction needs focused tests.

## Explicit invocation

Only after approval of this local resource test, choose a **single batch deadline** no more than
15 minutes away, and keep that same deadline across repairs; do not silently reset it. Track every
control/CAD/verifier/render launch against the caller's batch allowance. This fixed program launches
six workers; its deadline check is not a persistent aggregate launch ledger or a concurrent-job broker.
It is not safe to treat repeated invocations as an automatically enforced aggregate quota.

```sh
# DEADLINE is the existing approved batch deadline (Unix seconds), not a per-retry refresh.
UNIT="cad-isolation-controls-$(date +%s)-$$"
timeout --kill-after=2 35 systemd-run --user --wait --pipe --collect \
  --unit="$UNIT" --service-type=exec \
  -p Delegate=yes -p CPUQuota=200% -p MemoryMax=2147483648 -p MemorySwapMax=0 \
  -p TasksMax=64 -p RuntimeMaxSec=30 -p TimeoutStopSec=2 -p KillMode=control-group \
  -p StandardOutput=inherit -p StandardError=inherit \
  /usr/bin/python3 -I "$PWD/platform/pipeline/isolation/check_host.py" --deadline-epoch "$DEADLINE"
```

`--pipe`/inherited streams keep worker logs out of a separate journal data sink; the supervisor reads
both worker streams with a combined cap before emitting bounded diagnostic records. No persistent
service is installed. No root/sudo, policy change, package install or unrestricted fallback follows
from a failure. Confirm the named unit is inactive/collected, not merely that the client returned.

## Focused offline tests

```sh
python3 -m unittest discover -s platform/pipeline/isolation -v
```

These six tests check guard contracts, command construction and compilation of fixed control sources;
they launch no namespaces or exhaustion controls. The broad `platform/pipeline/test.sh` also launches
CAD suites and repository checks: **it was not run as part of this non-CAD increment**. No full-platform
regression or CAD compatibility claim follows. No commit requested/performed.

## Actual consumer evidence

CAD Studio's approved local evaluation on 2026-09-10 exercised all six controls successfully after
fixing a test assumption: Bubblewrap sets `PWD=/work`, which must be explicitly checked rather than
mistaken for inherited host environment. Its Git-free disposable-staging reproduction then hit the
existing producer's `repo_root()` refusal **before generator execution**. Those source/spec copies
were writable in bounded scratch; producer-input sealing was not demonstrated. That is an unresolved staging/evidence
mapping, not a reason to weaken source/physical gates or mount a workshop checkout. See
[consumer evidence](../../../../cad-studio/docs/evaluation/2026-09-10-host-controls.json) and
[feedback](../../../../cad-studio/docs/platform-feedback.md).
