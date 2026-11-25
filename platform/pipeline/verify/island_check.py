#!/usr/bin/env python3
"""island_check.py — does every extrusion run start over material already laid down?

WHY THIS IS IN THE REPO. A "0% support" or "support-free" claim is about the G-CODE, not the
model: verify-slice counts support segments, which says nothing about an overhang that got no
support and no bridge either. This checker has now been written from scratch in a session
scratchpad TWICE (2026-09-11 on the StackDrawer frame, 2026-09-17 on 12gaplusone) and lost both
times. It lives here now.

    island_check.py <gcode> [z_window_mm] [near_mm]
    exit 0 = every model run starts anchored · exit 1 = mid-air starts listed

TWO THINGS IT GETS RIGHT THAT A NAIVE VERSION DOES NOT:

1. It looks back by a Z WINDOW, not by layer index. PrusaSlicer support layers are not
   synchronised with object layers (7.441 vs 7.738 on the StackDrawer drawer), so "two layers
   down" misses the support sitting under the overhang.

2. It ignores runs that BELONG to support (;TYPE:), while still counting support as material
   that anchors the model. A tree's own stems start unanchored constantly; counting those as
   defects made every support strategy look worse the more support it added, and on 2026-09-17
   that inverted a recommendation — organic looked like it had 15 defects when the model had 9.

KNOWN LIMITS. Arcs (G2/G3) are treated as chords, so a long arc's midpoint is not sampled; the
start point, which is what this checks, is exact. A flagged start is a CANDIDATE: a gap under
~1.5 mm at 0.2 mm layers is an ordinary bridge, not a defect. Read the distances, not the count.
"""

import math, re, sys

import numpy as np

GC = sys.argv[1]
ZWIN = float(sys.argv[2]) if len(sys.argv) > 2 else 0.45   # >= layer height + contact gap
NEAR = float(sys.argv[3]) if len(sys.argv) > 3 else 0.60   # one extrusion width or so

num = lambda s, k: (lambda m: float(m.group(1)) if m else None)(re.search(k + r'(-?[\d.]+)', s))

x = y = z = 0.0
e = 0.0
kind = ""      # ;TYPE: — support lays material that anchors the MODEL, but its own thin
               # stems start unanchored constantly. Counting those as defects made every
               # support strategy look worse the more support it added.
abs_e = True
layers = {}           # z -> list of (x, y) sampled along every extrusion
starts = []           # (z, x, y) of each run that began after a travel
travelled = True

def sample(x0, y0, x1, y1, out):
    d = math.hypot(x1 - x0, y1 - y0)
    n = max(1, int(d / 0.4))
    for i in range(n + 1):
        out.append((x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n))

for line in open(GC, 'r', errors='replace'):
    if line.startswith(';TYPE:'):
        kind = line.strip()[6:]
        continue
    if line.startswith(';'):
        continue
    code = line[:3].strip()
    if code == 'G92' and 'E' in line:
        e = num(line, 'E') or 0.0
        continue
    if code in ('M82', 'M83'):
        abs_e = code == 'M82'
        continue
    if code not in ('G0', 'G1', 'G2', 'G3'):
        continue
    nx, ny, nz, ne = num(line, 'X'), num(line, 'Y'), num(line, 'Z'), num(line, 'E')
    x1 = nx if nx is not None else x
    y1 = ny if ny is not None else y
    if nz is not None:
        z = nz
    de = (ne - e) if (ne is not None and abs_e) else (ne if ne is not None else 0.0)
    if ne is not None:
        e = ne if abs_e else e + ne
    extruding = de > 1e-9 and (x1 != x or y1 != y)
    if extruding:
        pts = layers.setdefault(round(z, 3), [])
        if travelled and 'upport' not in kind:
            starts.append((round(z, 3), x1, y1))
        sample(x, y, x1, y1, pts)
        travelled = False
    elif x1 != x or y1 != y:
        travelled = True
    x, y = x1, y1

zs = sorted(layers)
trees = {zz: np.array(layers[zz]) for zz in zs}
first = zs[0]
bad = []
for sz, sx, sy in starts:
    if sz <= first + 1e-6:
        continue
    below = [trees[zz] for zz in zs if sz - ZWIN - 1e-6 <= zz < sz - 1e-6]
    if not below:
        bad.append((sz, sx, sy, None))
        continue
    pts = np.vstack(below)
    d = float(np.min(np.hypot(pts[:, 0] - sx, pts[:, 1] - sy)))
    if d > NEAR:
        bad.append((sz, sx, sy, d))

print(f"{len(zs)} layers, {len(starts)} MODEL runs after a travel, z window {ZWIN}, near {NEAR} mm")
if not bad:
    print("ISLAND CHECK: PASS — every run starts over material within the z window")
else:
    print(f"ISLAND CHECK: {len(bad)} mid-air start(s)")
    for sz, sx, sy, d in bad[:25]:
        print("  z=%.3f  x=%.2f y=%.2f  nearest below %s" % (sz, sx, sy, "none" if d is None else "%.2f mm" % d))
sys.exit(1 if bad else 0)
