#!/usr/bin/env python3
"""plot-supports.py — visualize a sliced plate's SUPPORT structure from the gcode.

Reads a sliced gcode (PrusaSlicer or OrcaSlicer), separates support extrusion from model
extrusion, and plots FRONT (X-Z), SIDE (Y-Z), TOP (X-Y) with support in red over
the model in gray. Also prints the support share of total extrusion. Fills the gap the handoff
wants (supports must be *visible* before approving a print) — before this, supports.png images
were made ad-hoc and not reproducible.

Usage:  plot-supports.py <plate_1.gcode> <out.png> ["title suffix"]

GOTCHA (do NOT reintroduce): OrcaSlicer writes small numbers with no leading zero — E.01152,
I.384 — so the coordinate regex MUST be  ([XYZEIJ])(-?[\\d.]+)  . The stricter  \\d+\\.?\\d*
silently drops those values, which are most support/arc moves -> the plot looks nearly empty and
the support % is garbage. Handle G2/G3 arcs (interpolate via I/J) and relative extrusion (M83);
tree supports are mostly arcs, so skipping arcs also empties the plot.
"""
import sys, re, math
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

if len(sys.argv) < 3:
    sys.exit("usage: plot-supports.py <gcode> <out.png> [title suffix]")
GCODE, OUT = sys.argv[1], sys.argv[2]
SUFFIX = sys.argv[3] if len(sys.argv) > 3 else ""
# Orca writes ";TYPE:Support" / "Support interface"; PrusaSlicer writes ";TYPE:Support material" /
# "Support material interface". Matching Orca's exact strings against Prusa gcode reported 0.0%
# support on a plate that genuinely had it — a silent failure of the one artifact whose whole job
# is making supports visible before approval. Prefix-match so both dialects (and interface//
# variants) are caught.
SUPPORT_PREFIXES = ("Support",)

def is_support(t):
    return t is not None and t.startswith(SUPPORT_PREFIXES)
num = re.compile(r"([XYZEIJ])(-?[\d.]+)")     # -?[\d.]+ so leading-dot values (E.01152, I.384) parse

def arc_pts(px, py, cx, cy, ex, ey, cw, pz, ez):
    r = math.hypot(px - cx, py - cy)
    a0, a1 = math.atan2(py - cy, px - cx), math.atan2(ey - cy, ex - cx)
    if cw:
        while a1 > a0: a1 -= 2 * math.pi
    else:
        while a1 < a0: a1 += 2 * math.pi
    da = a1 - a0
    n = max(2, int(abs(da) * r / 0.8))
    return [(cx + r * math.cos(a0 + da * k / n), cy + r * math.sin(a0 + da * k / n),
             pz + (ez - pz) * k / n) for k in range(n + 1)]

mode = "abs"; lastE = 0.0; x = y = z = 0.0; cur = None
sup_seg, mod_seg = [], []; sup_E = tot_E = 0.0
zmin, zmax = 1e9, -1e9

with open(GCODE, "rb") as f:
    for raw in f:
        line = raw.decode("latin-1").rstrip()
        if line.startswith(";TYPE:"): cur = line[6:].strip(); continue
        if line.startswith("M83"): mode = "rel"; continue
        if line.startswith("M82"): mode = "abs"; continue
        if line.startswith("G92"):
            m = dict(num.findall(line))
            if "E" in m: lastE = float(m["E"])
            continue
        is_arc = line.startswith("G2") or line.startswith("G3")
        if not (is_arc or line.startswith("G1") or line.startswith("G0")): continue
        m = dict(num.findall(line))
        px, py, pz = x, y, z
        nx = float(m["X"]) if "X" in m else x
        ny = float(m["Y"]) if "Y" in m else y
        nz = float(m["Z"]) if "Z" in m else z
        de = 0.0
        if "E" in m:
            ev = float(m["E"]); de = ev if mode == "rel" else ev - lastE
            if mode == "abs": lastE = ev
        if de > 1e-6:
            if is_arc and ("I" in m or "J" in m):
                cx, cy = px + float(m.get("I", 0)), py + float(m.get("J", 0))
                pts = arc_pts(px, py, cx, cy, nx, ny, line.startswith("G2"), pz, nz)
                segs = [(pts[k], pts[k + 1]) for k in range(len(pts) - 1)]
            elif ("X" in m or "Y" in m):
                segs = [((px, py, pz), (nx, ny, nz))]
            else:
                segs = []
            if segs:
                (sup_seg if is_support(cur) else mod_seg).extend(segs)
                tot_E += de
                if is_support(cur): sup_E += de
                zmin, zmax = min(zmin, pz, nz), max(zmax, pz, nz)
        x, y, z = nx, ny, nz

pct = 100.0 * sup_E / tot_E if tot_E else 0.0
print(f"support = {pct:.1f}% of extrusion  |  support segs {len(sup_seg)}  model segs {len(mod_seg)}  "
      f"|  z {zmin:.0f}-{zmax:.0f} mm")

def proj(seg, a, b): return [((s[0][a], s[0][b]), (s[1][a], s[1][b])) for s in seg]
fig, axes = plt.subplots(1, 3, figsize=(18, 6))
for ax, (title, a, b, la, lb) in zip(axes, [
        ("FRONT (X-Z)", 0, 2, "X", "Z"), ("SIDE (Y-Z)", 1, 2, "Y", "Z"),
        ("TOP (X-Y) — support footprint on the bed", 0, 1, "X", "Y")]):
    ax.add_collection(LineCollection(proj(mod_seg, a, b), colors="0.75", linewidths=0.25))
    ax.add_collection(LineCollection(proj(sup_seg, a, b), colors="#d62728", linewidths=0.45))
    ax.set_title(title, fontsize=11); ax.set_xlabel(f"{la} (mm)"); ax.set_ylabel(f"{lb} (mm)")
    ax.autoscale(); ax.set_aspect("equal", adjustable="datalim")
sub = f"  |  {SUFFIX}" if SUFFIX else ""
fig.suptitle(f"Supports (from sliced gcode)  |  support = {pct:.1f}% of extrusion  |  z {zmin:.0f}-{zmax:.0f} mm{sub}",
             fontsize=13)
fig.tight_layout(rect=[0, 0, 1, 0.96]); fig.savefig(OUT, dpi=110)
print("wrote", OUT)
