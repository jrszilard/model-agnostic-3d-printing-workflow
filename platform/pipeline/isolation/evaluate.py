"""Explicit local digital-evaluation API, not build/physical provenance or a service.

Single-threaded trusted supervisor only, inside the documented transient unit.
Untrusted bytes stay in read-only namespace inputs and bounded artifact pipes.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
import uuid

from check_host import ROOT_LIMITS, read_values, verify_limits
from staging import (MiB, MAX_WIRE, SealedInputs, decode, digest, name_ok,
                     output_names, read_regular, require, sealed_fd)

HERE = Path(__file__).resolve().parent
SCHEMA = "isolated-digital-evaluation/v1"    # deliberately NOT manufacturing schema 1
MODULE_SHA256 = digest(read_regular(Path(__file__)))


class Batch:
    """One process, no retries/reset, conservatively includes this supervisor launch."""
    def __init__(self, deadline_epoch, *, carried_launches=0, launch_limit=32):
        require(type(deadline_epoch) in (int, float) and math.isfinite(deadline_epoch), "invalid deadline")
        now = time.time()
        require(3 < deadline_epoch - now <= 900, "invalid batch window")
        self.deadline_epoch = deadline_epoch
        self.ends = time.monotonic() + deadline_epoch - now
        self.started_epoch = now
        require(type(carried_launches) is int and type(launch_limit) is int
                and 0 <= carried_launches < launch_limit <= 32, "invalid carried launch budget")
        self.launches = carried_launches + 1
        self.launch_limit = launch_limit
        self.records = []
        self.closed = False
        self.root = None

    def attach(self):
        require(self.root is None and not self.closed, "batch already attached/closed")
        root = Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().strip().split("::", 1)[1].lstrip("/")
        require(root.name.startswith("cad-evaluation-"), "requires bounded evaluation unit")
        verify_limits(read_values(root, ROOT_LIMITS), ROOT_LIMITS)
        require(set((root / "cgroup.controllers").read_text().split()) >= {"cpu", "memory", "pids"},
                "missing delegated controllers")
        leaf = root / "supervisor"
        leaf.mkdir()
        (leaf / "cgroup.procs").write_text(str(os.getpid()))
        (root / "cgroup.subtree_control").write_text("+cpu +memory +pids")
        self.root = root

    def reserve(self):
        require(not self.closed and self.launches < self.launch_limit and time.monotonic() + 3 < self.ends,
                "batch exhausted; no launch/retry")
        self.launches += 1       # before Popen; failed startup still consumes reservation

    def case(self):
        return min(self.ends - 2, time.monotonic() + 90)

    def close(self):
        self.closed = True


def command_for(runtime):
    if runtime == "python":
        return ["/usr/bin/python3", "-I", "/inputs/main.py"]
    if runtime == "cadquery":
        return ["/runtime/bin/python", "-I", "/inputs/main.py"]
    if runtime == "freecad":
        return ["/usr/bin/python3", "-I", "-c",
                "import sys,runpy; sys.path.insert(0,'/usr/lib/freecad/lib'); "
                "runpy.run_path('/inputs/main.py',run_name='__main__')"]
    raise ValueError("unknown evaluation runtime")


def namespace_command(inputs, tools, runtime, runtime_root):
    command = ["/usr/bin/bwrap", "--unshare-user", "--unshare-pid", "--unshare-ipc",
               "--unshare-uts", "--unshare-net", "--unshare-cgroup", "--disable-userns",
               "--assert-userns-disabled", "--new-session", "--die-with-parent",
               "--cap-drop", "ALL", "--clearenv", "--ro-bind", "/usr", "/usr",
               "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib",
               "--symlink", "usr/lib", "/lib64", "--proc", "/proc", "--dev", "/dev",
               "--remount-ro", "/dev", "--size", str(128 * MiB), "--tmpfs", "/work",
               "--symlink", "work", "/tmp"]
    if runtime == "cadquery":
        # Explicit installed runtime only; never a checkout, home, or writable mount.
        require(runtime_root is not None and Path(runtime_root).is_absolute(), "runtime root required")
        command += ["--ro-bind", str(runtime_root), "/runtime"]
    for prefix, fds in (("/inputs", inputs), ("/engine", tools)):
        for name, fd in fds.items():
            # bwrap consumes/closes a --ro-bind-data FD. Mount each exactly ONCE.
            target = "/etc" if prefix == "/engine" and runtime == "freecad" and name in {"passwd", "group"} else prefix
            command += ["--ro-bind-data", str(fd), target + "/" + name]
    command += ["--setenv", "PATH", "/usr/bin", "--setenv", "HOME", "/work",
                "--setenv", "TMPDIR", "/work", "--setenv", "OPENBLAS_NUM_THREADS", "2",
                "--setenv", "OMP_NUM_THREADS", "2", "--setenv", "QT_QPA_PLATFORM", "offscreen",
                "--setenv", "LD_LIBRARY_PATH", "/usr/lib/freecad/lib",
                "--chdir", "/work", "--remount-ro", "/",
                "/usr/bin/python3", "-I", "/engine/evaluation_worker.py"]
    return command


def drain(process, ends):
    """Both EOF AND successful process exit matter; EOF alone cannot admit output."""
    wire, logs = bytearray(), bytearray()
    reason = None
    with selectors.DefaultSelector() as poller:
        for stream, dest, bound in ((process.stdout, wire, MAX_WIRE), (process.stderr, logs, MiB)):
            os.set_blocking(stream.fileno(), False)
            poller.register(stream, selectors.EVENT_READ, (dest, bound))
        while poller.get_map() or process.poll() is None:
            if time.monotonic() >= ends:
                reason = "deadline"
                break
            for key, _ in poller.select(.01):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    poller.unregister(key.fileobj)
                    continue
                dest, bound = key.data
                if len(dest) + len(chunk) > bound:
                    reason = "log-limit" if dest is logs else "artifact-transport-limit"
                    break
                dest.extend(chunk)
            if reason:
                break
    return bytes(wire), bytes(logs), reason


def run_stage(batch, label, inputs, expected, *, runtime="python", runtime_root=None,
              case_deadline, seconds=30):
    require(batch.root is not None and not batch.closed, "batch not attached")
    name_ok(label)
    expected = output_names(expected)
    require("main.py" in inputs, "missing selected entrypoint")
    require(type(seconds) in (int, float) and 0 < seconds <= 30, "invalid stage time")
    require(type(case_deadline) in (int, float) and math.isfinite(case_deadline)
            and time.monotonic() < case_deadline <= batch.ends
            and case_deadline <= time.monotonic() + 90, "invalid case deadline")
    job = json.dumps({"command": command_for(runtime), "outputs": expected}).encode()
    tool_bytes = {name: read_regular(HERE / name) for name in ("staging.py", "evaluation_worker.py")}
    tool_bytes["job.json"] = job
    if runtime == "freecad":
        tool_bytes["passwd"] = f"worker:x:{os.getuid()}:{os.getgid()}:Evaluation:/work:/usr/bin/false\n".encode()
        tool_bytes["group"] = f"worker:x:{os.getgid()}:\n".encode()
    artifacts = {}
    process = None
    wire = logs = b""
    reason = None
    started = time.monotonic()
    ends = min(started + seconds, case_deadline, batch.ends - 2)
    group = batch.root / ("stage-" + uuid.uuid4().hex)
    with SealedInputs(inputs) as sealed, SealedInputs(tool_bytes) as tools:
        command = namespace_command(sealed.fds, tools.fds, runtime, runtime_root)
        batch.reserve()
        group.mkdir()
        try:
            for name, value in ROOT_LIMITS.items():
                (group / name).write_text(value)
            (group / "memory.oom.group").write_text("1")
            verify_limits(read_values(group, ROOT_LIMITS), ROOT_LIMITS)

            def enter():
                (group / "cgroup.procs").write_text(str(os.getpid()))
                os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])

            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, close_fds=True,
                                       pass_fds=tuple(sealed.fds.values()) + tuple(tools.fds.values()),
                                       preexec_fn=enter, env={"PATH": "/usr/bin"})
            wire, logs, reason = drain(process, ends)
        except (OSError, subprocess.SubprocessError) as exc:
            reason = "startup-or-supervision-error: " + type(exc).__name__
        finally:
            (group / "cgroup.kill").write_text("1")
            if process is not None:
                process.wait(timeout=2)
                process.stdout.close()
                process.stderr.close()
            until = time.monotonic() + 2
            while "populated 1" in (group / "cgroup.events").read_text() and time.monotonic() < until:
                time.sleep(.01)
            require("populated 0" in (group / "cgroup.events").read_text(), "cleanup failed; NO acceptance")
            observed = read_values(group, [*ROOT_LIMITS, "memory.events", "memory.peak", "pids.events",
                                          "pids.peak", "cpu.stat", "cgroup.events"])
            group.rmdir()
        if reason is None and process is not None and process.returncode == 0:
            try:
                artifacts = decode(wire, expected)
            except ValueError as exc:
                reason = str(exc)
        else:
            reason = reason or "worker-failed"
        record = {"schema": SCHEMA, "execution_id": str(uuid.uuid4()), "label": label,
                  "authority": "digital-evaluation-only", "manufacturing_qualified": False,
                  "status": "accepted" if artifacts else "rejected", "reason": reason,
                  "exit": process.returncode if process is not None else None,
                  "inputs": sealed.identities, "tools": tools.identities, "runtime": runtime,
                  "supervisor_sha256": MODULE_SHA256,
                  "profile_command_sha256": digest(json.dumps(command).encode()),
                  "outputs": {n: {"sha256": digest(v), "bytes": len(v)} for n, v in artifacts.items()},
                  "seconds": round(time.monotonic() - started, 3), "observed": observed,
                  "cgroup_removed": not group.exists(), "log_bytes": len(logs),
                  "log_sha256": digest(logs), "log": logs.decode(errors="replace")[:12000]}
        batch.records.append(record)
    return record, artifacts
