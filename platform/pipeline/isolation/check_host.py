#!/usr/bin/env python3
"""Explicit, NON-CAD Linux containment control experiment; not a CAD/job runner.

Run only inside an approved transient systemd-user unit with Delegate=yes and
outer limits. No exhaustion control starts until kernel limits are read back.
A success is host-control evidence, NOT production isolation or CAD admission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time


MiB = 1024 * 1024
ROOT_LIMITS = {"cpu.max": "200000 100000", "memory.max": str(2048 * MiB),
               "memory.swap.max": "0", "pids.max": "64"}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def read_values(group, names):
    return {name: (group / name).read_text().strip() for name in names}


def verify_limits(actual, expected):
    for name, value in expected.items():
        require(actual.get(name) == value, f"unverified kernel limit: {name}")


def namespace_command(canary, code):
    # Separate profile from ai/benchmark.py's persistent RLIMIT worker: no /etc,
    # host writable workspace, unbounded /tmp, CAD import or command input.
    return ["/usr/bin/bwrap", "--unshare-user", "--unshare-pid", "--unshare-ipc",
            "--unshare-uts", "--unshare-net", "--unshare-cgroup", "--disable-userns",
            "--assert-userns-disabled", "--new-session", "--die-with-parent",
            "--cap-drop", "ALL", "--clearenv", "--ro-bind", "/usr", "/usr",
            "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib",
            "--symlink", "usr/lib", "/lib64", "--proc", "/proc", "--dev", "/dev",
            "--remount-ro", "/dev", "--size", str(128 * MiB), "--tmpfs", "/work",
            "--symlink", "work", "/tmp", "--ro-bind", str(canary), "/input.txt",
            "--setenv", "PATH", "/usr/bin", "--setenv", "HOME", "/work",
            "--setenv", "TMPDIR", "/work", "--chdir", "/work", "--remount-ro", "/",
            "/usr/bin/python3", "-I", "-c", code]


SMOKE = r'''
import json, os, pathlib, socket
p = pathlib.Path
status = dict(line.split(":",1) for line in p("/proc/self/status").read_text().splitlines() if ":" in line)
assert status["NoNewPrivs"].strip() == "1"
assert all(int(status[k].strip(),16)==0 for k in ("CapInh","CapPrm","CapEff","CapBnd","CapAmb"))
assert {"PATH","HOME","TMPDIR","PWD"} <= set(os.environ) <= {"PATH","HOME","TMPDIR","PWD","LC_CTYPE"}, sorted(os.environ)
assert os.environ["PWD"] == "/work"
assert not p("/home").exists() and not p("/run").exists() and not p("/etc").exists()
assert not p("/sys").exists() and not p("/dev/dri").exists() and not p("/dev/kvm").exists()
assert p("/input.txt").read_text() == "owned dummy canary\n"
for target in ("/input.txt", "/root-write", "/dev/write-test"):
    try: p(target).write_text("bad")
    except OSError: pass
    else: raise AssertionError("unexpected write: " + target)
# No external connections: interface/routes and a dummy abstract-UNIX canary.
assert socket.if_nameindex() == [(1,"lo")]
assert len(p("/proc/net/route").read_text().splitlines()) == 1
s=socket.socket(socket.AF_UNIX); s.settimeout(.2)
try: s.connect("\0" + ABSTRACT_CANARY)
except OSError: pass
else: raise AssertionError("host abstract socket visible")
finally: s.close()
# Existing descriptors must be files/pipes/devices, not inherited sockets.
for fd in p("/proc/self/fd").iterdir():
    try: target = os.readlink(fd)
    except FileNotFoundError: continue
    assert not target.startswith("socket:"), "inherited socket descriptor"
assert os.statvfs("/work").f_blocks * os.statvfs("/work").f_frsize == 134217728
p("/tmp/write-test").write_text("scratch")
print(json.dumps({"no_new_privs":True,"capabilities":0,"interfaces":socket.if_nameindex(),
                  "scratch_bytes":134217728,"affinity":sorted(os.sched_getaffinity(0)),
                  "namespaces":{n:os.readlink("/proc/self/ns/"+n) for n in ("user","pid","mnt","net","ipc","uts","cgroup")}}))
'''
DISK = r'''
import errno,json,pathlib
written=0
try:
    with open("/work/fill", "wb", buffering=0) as f:
        for i in range(160):
            written += f.write(b"x" * 1048576)
except OSError as e:
    assert e.errno == errno.ENOSPC
    print(json.dumps({"enospc":True,"written":written}))
else: raise AssertionError("scratch exceeded 128 MiB")
'''
MEMORY = 'a=[]\nwhile True: a.append(bytearray(4*1024*1024))'
PIDS = r'''
import errno,json,os,time
children=[]
try:
    for i in range(80):
        pid=os.fork()
        if pid==0: time.sleep(10); os._exit(0)
        children.append(pid)
except OSError as e:
    assert e.errno==errno.EAGAIN
    print(json.dumps({"eagain":True,"children":len(children)}),flush=True)
else: raise AssertionError("pids limit not enforced")
finally:
    for pid in children: os.kill(pid,9)
    for pid in children: os.waitpid(pid,0)
'''
LOG = 'import os\nwhile True: os.write(1,b"x"*4096); os.write(2,b"y"*4096)'
DESCENDANT = 'import os,time\nif os.fork()==0: os.setsid(); time.sleep(20)\nelse: time.sleep(20)'


def check_budget(seconds, deadline, memory):
    require(type(seconds) in (int, float) and 0 < seconds <= 30, "invalid stage deadline")
    require(type(deadline) in (int, float) and math.isfinite(deadline), "invalid batch deadline")
    remaining = deadline - time.time()
    require(seconds + 3 < remaining <= 900, "batch deadline: no further launch")
    require(type(memory) is int and 0 < memory <= 2048 * MiB, "invalid memory bound")


def run_control(root, canary, label, code, seconds, deadline, *, memory=256 * MiB):
    check_budget(seconds, deadline, memory)
    group = root / ("probe-" + label)
    group.mkdir()
    limits = dict(ROOT_LIMITS, **{"memory.max": str(memory), "pids.max": "16"})
    for name, value in limits.items():
        (group / name).write_text(value)
    (group / "memory.oom.group").write_text("1")
    verify_limits(read_values(group, limits), limits)
    # preexec only in this single-threaded, fixed trusted control program.
    def enter():
        (group / "cgroup.procs").write_text(str(os.getpid()))
        os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    started = time.monotonic()
    out = bytearray()
    reason = None
    process = None
    try:
        process = subprocess.Popen(namespace_command(canary, code), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True,
                                   preexec_fn=enter, env={"PATH": "/usr/bin"})
        with selectors.DefaultSelector() as poller:
            for stream in (process.stdout, process.stderr):
                os.set_blocking(stream.fileno(), False)
                poller.register(stream, selectors.EVENT_READ)
            while poller.get_map():
                if time.monotonic() - started >= seconds:
                    reason = "deadline"
                    break
                for key, _ in poller.select(.02):
                    chunk = os.read(key.fileobj.fileno(), 4096)
                    if not chunk:
                        poller.unregister(key.fileobj)
                    elif len(out) + len(chunk) > MiB:
                        reason = "log-limit"
                        break
                    else:
                        out.extend(chunk)
                if reason:
                    break
    finally:
        # Kill the whole cgroup, not a process group an orphan can leave.
        (group / "cgroup.kill").write_text("1")
        if process is not None:
            process.wait(timeout=2)
            process.stdout.close()
            process.stderr.close()
        until = time.monotonic() + 2
        while "populated 1" in (group / "cgroup.events").read_text() and time.monotonic() < until:
            time.sleep(.01)
        require("populated 0" in (group / "cgroup.events").read_text(), "descendants remain")
        evidence = read_values(group, [*limits, "memory.events", "memory.peak", "pids.events", "pids.peak", "cpu.stat", "cgroup.events"])
        group.rmdir()
    return {"control": label, "exit": process.returncode, "reason": reason,
            "seconds": round(time.monotonic() - started, 3), "observed": evidence,
            "log_bytes_retained": len(out), "output": out.decode(errors="replace") if len(out)<8192 else "[bounded log discarded]",
            "cgroup_removed": not group.exists()}


def main(deadline):
    import socket
    root = Path("/sys/fs/cgroup") / Path("/proc/self/cgroup").read_text().strip().split("::",1)[1].lstrip("/")
    require(root.name.startswith("cad-isolation-controls-"), "run only inside the documented transient control unit")
    verify_limits(read_values(root, ROOT_LIMITS), ROOT_LIMITS)
    require(set((root/"cgroup.controllers").read_text().split()) >= {"cpu","memory","pids"}, "missing delegated controllers")
    supervisor = root / "supervisor"
    supervisor.mkdir()
    (supervisor / "cgroup.procs").write_text(str(os.getpid()))
    (root / "cgroup.subtree_control").write_text("+cpu +memory +pids")
    records = []
    host_ns = {n:os.readlink("/proc/self/ns/"+n) for n in ("user","pid","mnt","net","ipc","uts","cgroup")}
    with tempfile.TemporaryDirectory(prefix="isolation-canary-") as directory, socket.socket(socket.AF_UNIX) as server:
        canary = Path(directory) / "input.txt"
        canary.write_text("owned dummy canary\n")
        abstract = "isolation-canary-" + str(os.getpid())
        server.bind("\0" + abstract)
        server.listen(1)
        cases = [("isolation", "ABSTRACT_CANARY="+repr(abstract)+"\n"+SMOKE, 5, 256*MiB),
                 ("scratch", DISK, 5, 256*MiB), ("memory", MEMORY, 5, 64*MiB),
                 ("pids", PIDS, 5, 256*MiB), ("logs", LOG, 5, 256*MiB),
                 ("descendants", DESCENDANT, .5, 256*MiB)]
        for name, code, seconds, memory in cases:
            row = run_control(root, canary, name, code, seconds, deadline, memory=memory)
            records.append(row)
            print(json.dumps(row), flush=True)
            require(canary.read_text() == "owned dummy canary\n", "canary changed")
            if name == "isolation":
                require(row["exit"]==0 and row["reason"] is None, "namespace assertions failed")
                observed = json.loads(row["output"])
                require(all(observed["namespaces"][k] != host_ns[k] for k in host_ns), "namespace shared")
                require(len(observed["affinity"])==2, "worker affinity not bounded")
            elif name in {"scratch", "pids"}:
                require(row["exit"]==0 and row["reason"] is None, f"{name} control failed")
                field = "enospc" if name=="scratch" else "eagain"
                require(json.loads(row["output"])[field] is True, f"{name} denial missing")
                if name=="pids":
                    require(int(dict(x.split() for x in row["observed"]["pids.events"].splitlines())["max"])>0, "no kernel pids denial")
            elif name == "memory":
                events = dict(x.split() for x in row["observed"]["memory.events"].splitlines())
                require(row["exit"]!=0 and row["reason"] is None and int(events["oom_kill"])>0, "no kernel OOM kill")
            else:
                require(row["reason"] == ("log-limit" if name=="logs" else "deadline"), "supervisor did not stop control")
        print(json.dumps({"result":"HOST_CONTROLS_PASS", "cad_executed":False,
                          "source_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                          "worker_launches":len(records), "canary_unchanged":True}), flush=True)
    # The unit manager reaps/removes the supervisor leaf and unit after exit.


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deadline-epoch", type=float, required=True)
    args = parser.parse_args()
    main(args.deadline_epoch)
