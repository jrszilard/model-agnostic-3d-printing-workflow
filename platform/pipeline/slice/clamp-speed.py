#!/usr/bin/env python3
"""clamp-speed.py — cap EXTRUSION feedrate above a Z plane in sliced gcode.

Why: the color-swap graphics band is 3 layers of tiny raised islands printed right after an
M600 filament change. At profile speeds the fresh-loaded filament's pressure never stabilises
across micro-features (2026-07-24 swap plate: the first rail printed after the resume came out
faint and ragged). Capping extrusion speed in the band gives even, well-bonded deposition for a
couple of extra minutes of print time.

Only EXTRUDING moves are slowed: G1 lines carrying an E word, and bare `G1 F...` modal feed
lines (PrusaSlicer emits those before extrusion runs). Travel moves (X/Y with no E) keep their
explicit fast F — slowing travel would only add ooze/stringing time between islands.

Usage: clamp-speed.py <gcode> --above-z <mm> [--max-speed <mm/s, default 20>] [--dry-run]
Exit codes: 0 ok · 2 usage · 4 already clamped
"""
import re
import shutil
import sys

MARKER = "; lakeshore: black-band feed clamp"


def main(argv):
    if len(argv) < 3:
        sys.exit("usage: clamp-speed.py <gcode> --above-z <mm> [--max-speed <mm/s>] [--dry-run]")
    path, above_z, max_speed, dry = argv[1], None, 20.0, False
    i = 2
    while i < len(argv):
        a = argv[i]
        if a == "--above-z":
            i += 1; above_z = float(argv[i])
        elif a == "--max-speed":
            i += 1; max_speed = float(argv[i])
        elif a == "--dry-run":
            dry = True
        else:
            sys.exit(f"unknown option: {a}")
        i += 1
    if above_z is None:
        sys.exit("usage: --above-z is required")
    max_f = max_speed*60.0

    with open(path) as stream:
        lines = stream.read().splitlines(keepends=True)
    if any(MARKER in ln for ln in lines):
        print(f"ERROR: {path} already contains a feed clamp", file=sys.stderr)
        return 4

    z, in_band, clamped, top_seen = 0.0, False, 0, 0.0
    out = []
    f_re = re.compile(r"F([0-9.]+)")
    for ln in lines:
        m = re.match(r"^;Z:([0-9.]+)", ln)
        if m:
            z = float(m.group(1))
            in_band = z > above_z+1e-6
            out.append(ln)
            continue
        if in_band and ln.startswith("G1"):
            has_e = re.search(r"E[-0-9.]", ln)
            has_xyz = re.search(r"[XYZ][-0-9.]", ln)
            fm = f_re.search(ln)
            # extruding move, or a bare modal-feed line (no axis words, no E)
            if fm and (has_e or not has_xyz):
                f = float(fm.group(1))
                top_seen = max(top_seen, f)
                if f > max_f:
                    ln = f_re.sub(f"F{max_f:.0f}", ln, count=1)
                    clamped += 1
        out.append(ln)

    print(f"{path}")
    print(f"  band              Z>{above_z}")
    print(f"  extrusion cap     {max_speed} mm/s ({max_f:.0f} mm/min); travels untouched")
    print(f"  feeds clamped     {clamped}  (fastest seen {top_seen/60:.0f} mm/s)")
    if dry:
        print("  (dry run - not modified)")
        return 0
    shutil.copyfile(path, path+".bak-clamp")
    out.insert(0, f"{MARKER}: Z>{above_z} extrusion <= {max_speed}mm/s\n")
    with open(path, "w") as stream:
        stream.write("".join(out))
    print(f"  written  (backup: {path}.bak-clamp)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
