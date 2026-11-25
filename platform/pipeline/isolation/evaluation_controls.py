"""Explicit live NON-CAD acceptance controls; consume the caller's existing Batch."""
import json
import os
from pathlib import Path
import socket
import tempfile

import check_host as host
from evaluate import run_stage
from staging import require


def host_controls(batch, *, control_runner=host.run_control):
    host_namespaces = {n: os.readlink("/proc/self/ns/" + n) for n in ("user", "pid", "mnt", "net", "ipc", "uts", "cgroup")}
    with tempfile.TemporaryDirectory(prefix="evaluation-canary-") as directory, socket.socket(socket.AF_UNIX) as server:
        canary = Path(directory, "canary")
        canary.write_text("owned dummy canary\n")
        abstract = "evaluation-canary-" + str(os.getpid())
        server.bind("\0" + abstract)
        server.listen(1)
        cases = [("isolation", "ABSTRACT_CANARY=" + repr(abstract) + "\n" + host.SMOKE, 5, 256*host.MiB),
                 ("scratch", host.DISK, 5, 256*host.MiB), ("memory", host.MEMORY, 5, 64*host.MiB),
                 ("pids", host.PIDS, 5, 256*host.MiB), ("logs", host.LOG, 5, 256*host.MiB),
                 ("descendants", host.DESCENDANT, .5, 256*host.MiB)]
        for name, code, seconds, memory in cases:
            batch.reserve()
            row = control_runner(batch.root, canary, name, code, seconds, batch.deadline_epoch, memory=memory)
            batch.records.append(row)
            print(json.dumps(row), flush=True)
            require(canary.read_text() == "owned dummy canary\n", "host canary changed")
            if name in {"isolation", "scratch", "pids"}:
                require(row["exit"] == 0 and row["reason"] is None, "host control failed: " + name)
                result = json.loads(row["output"])
                if name == "isolation":
                    require(all(result["namespaces"][n] != host_namespaces[n] for n in host_namespaces), "shared namespace")
                    require(len(result["affinity"]) == 2, "wrong affinity")
                else:
                    require(result["enospc" if name == "scratch" else "eagain"] is True, "no denial")
                    if name == "pids":
                        require(int(dict(x.split() for x in row["observed"]["pids.events"].splitlines())["max"]) > 0, "no kernel pids denial")
            elif name == "memory":
                require(row["exit"] != 0 and row["reason"] is None and
                        int(dict(x.split() for x in row["observed"]["memory.events"].splitlines())["oom_kill"]) > 0, "no OOM kill")
            else:
                require(row["reason"] == ("log-limit" if name == "logs" else "deadline"), "control not stopped")


SEALED = '''import os,pathlib,socket
p=pathlib.Path
assert p('/inputs/original.txt').read_bytes() == b'original bytes'
for target in ('/inputs/original.txt','/inputs/main.py','/engine/job.json','/root-write','/dev/write-test'):
    try: p(target).write_bytes(b'changed')
    except OSError: pass
    else: raise AssertionError('writable input/root/device')
assert not any(p(x).exists() for x in ('/home','/run','/etc','/sys','/dev/kvm','/dev/dri'))
assert socket.if_nameindex()==[(1,'lo')]
assert len(p('/proc/net/route').read_text().splitlines())==1
assert not any('TOKEN' in x or 'KEY' in x for x in os.environ)
p('/work/output/out.txt').write_bytes(p('/inputs/original.txt').read_bytes())
'''


def identity_control(batch, *, stage_runner=run_stage):
    # Keep SEALED's no-/etc assertion for all unchanged profiles. This final profile
    # permits ONLY two read-only broker-authored identity files, never host records.
    code = SEALED.replace("'/etc',", "") + '''
import pwd,grp
assert sorted(x.name for x in p('/etc').iterdir()) == ['group','passwd']
assert p('/etc/passwd').read_text() == f'worker:x:{os.getuid()}:{os.getgid()}:Evaluation:/work:/usr/bin/false\\n'
assert p('/etc/group').read_text() == f'worker:x:{os.getgid()}:\\n'
assert pwd.getpwuid(os.getuid()).pw_dir == '/work'
assert pwd.getpwuid(os.getuid()).pw_name == 'worker'
assert grp.getgrgid(os.getgid()).gr_name == 'worker'
for target in ('/etc/passwd','/etc/group','/etc/extra'):
    try: p(target).write_text('bad')
    except OSError: pass
    else: raise AssertionError('writable synthetic identity')
status=dict(line.split(':',1) for line in p('/proc/self/status').read_text().splitlines() if ':' in line)
assert status['NoNewPrivs'].strip()=='1'
assert all(int(status[k].strip(),16)==0 for k in ('CapInh','CapPrm','CapEff','CapBnd','CapAmb'))
'''
    row, files = stage_runner(batch, "synthetic-identity", {"main.py": code.encode(), "original.txt": b"original bytes"},
                           ("out.txt",), runtime="freecad", case_deadline=batch.case(), seconds=5)
    print(json.dumps(row), flush=True)
    require(files == {"out.txt": b"original bytes"}, "synthetic identity control failed: " + row["log"])


def acceptance_controls(batch, *, stage_runner=run_stage):
    cases = [
        ("sealed-inputs", SEALED, True, None, 5),
        ("symlink-output", "import os; os.symlink('/inputs/original.txt','/work/output/out.txt')", False, "worker-failed", 5),
        ("oversized-output", "with open('/work/output/out.txt','wb') as f:\n f.truncate(33554433)", False, "worker-failed", 5),
        ("failed-partial", "from pathlib import Path; Path('/work/output/out.txt').write_text('partial'); raise SystemExit(1)", False, "worker-failed", 5),
        ("orphan-closed-pipes", "import os,time\nif os.fork()==0:\n os.setsid(); os.close(1); os.close(2); time.sleep(20)\nelse: os._exit(0)", False, "worker-failed", 5),
        ("deadline-closed-pipes", "import os,time; os.close(1); os.close(2); time.sleep(20)", False, "deadline", .5),
        ("combined-logs", host.LOG, False, "log-limit", 5),
    ]
    for name, code, accepted, reason, seconds in cases:
        row, files = stage_runner(batch, name, {"main.py": code.encode(), "original.txt": b"original bytes"},
                               ("out.txt",), case_deadline=batch.case(), seconds=seconds)
        print(json.dumps(row), flush=True)
        require(bool(files) == accepted and row["reason"] == reason, "acceptance control failed: " + name)
        if accepted:
            require(files == {"out.txt": b"original bytes"}, "sealed bytes changed")
        else:
            require(row["outputs"] == {}, "partial outputs admitted")
