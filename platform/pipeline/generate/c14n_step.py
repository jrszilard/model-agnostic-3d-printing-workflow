#!/usr/bin/env python3
"""c14n_step.py — neutralise the export timestamp in a STEP file.

WHY
CadQuery's STL export is byte-deterministic, but its STEP export is not: OCCT stamps the wall clock
into the ISO-10303-21 header. Two runs of hose-clip.py two seconds apart differed in exactly one
line --

    FILE_NAME('Open CASCADE Shape Model','2026-08-20T22:42:46',('Author'),(
    FILE_NAME('Open CASCADE Shape Model','2026-08-20T22:42:48',('Author'),(

-- and nothing else. Left alone, every rebuild rewrites every STEP, so `git status` reports parts as
changed when only the clock moved, and each rebuild adds a fresh multi-MB blob to history.

Pinning the timestamp to the epoch is a header-only edit; the geometry entities are untouched.

Usage: c14n_step.py <file.step> [...]     rewrites in place, only if the bytes change
"""
import re, sys

EPOCH = '1970-01-01T00:00:00'
PAT = re.compile(rb"(FILE_NAME\('[^']*',')[^']*(')")

def canonicalise(path):
    with open(path, 'rb') as f:
        data = f.read()
    out = PAT.sub(lambda m: m.group(1) + EPOCH.encode() + m.group(2), data, count=1)
    if out == data:
        return False
    with open(path, 'wb') as f:
        f.write(out)
    return True

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for p in sys.argv[1:]:
        try:
            print(f"c14n: {'rewrote' if canonicalise(p) else 'unchanged'} {p}")
        except Exception as e:
            print(f"c14n: skipped {p} ({e})", file=sys.stderr)
