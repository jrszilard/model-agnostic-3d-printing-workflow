"""Private coordinator inside the evaluation namespace; never run on the host."""
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, "/engine")
from staging import collect, encode


def living_descendants():
    result = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) in {1, os.getpid()}:
            continue
        try:
            state = (entry / "stat").read_text().split(")", 1)[1].split()[0]
        except FileNotFoundError:
            continue
        if state != "Z":
            result.append(int(entry.name))
    return result


def main():
    job = json.loads(Path("/engine/job.json").read_text())
    Path("/work/output").mkdir()
    result = subprocess.run(job["command"], stdin=subprocess.DEVNULL,
                            stdout=sys.stderr, stderr=sys.stderr, close_fds=True)
    if result.returncode != 0:
        raise RuntimeError("child failed: " + str(result.returncode))
    # A successful parent with a live detached writer is NOT a successful stage.
    # Reject; the outer cgroup supervisor kills/reaps the entire job.
    if living_descendants():
        raise RuntimeError("child left living descendants")
    files = collect("/work/output", job["outputs"])
    sys.stdout.buffer.write(encode(files))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
