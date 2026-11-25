#!/usr/bin/env python3
"""color-change.py — insert a single filament-change pause into sliced gcode.

The Core One has one nozzle, so a two-colour part is printed by pausing at a known Z, swapping
filament by hand, and resuming. PrusaSlicer's CLI cannot place a colour change (it lives in the
GUI's per-object layer slider), so the pause is inserted here, after slicing, by scanning the
layer table in the gcode itself.

Why scan rather than compute: the swap must land on the FIRST layer printed at or above the
colour plane, and that layer's Z is whatever the slicer's layer stack actually produced -- not
necessarily plane/layer_height. Guessing the layer index puts the black graphics one layer low
(white bleeding into the markings) or one layer high (a white ghost band).

--prime adds a PURGE LINE after the swap, in the machine's own purge lane at the front lip of
the sheet (Y=-2.5), which is where the printer lays its intro line at the start of every job.
This exists because the first raised lettering printed after an M600 came out stringy even
after purging by hand at the printer: hand-purging clears the COLOUR, but the nozzle then sits
idle while the door is open, and the first thing it is asked to draw is a set of small
disconnected glyph islands -- no pressure, no flow history, nothing to wipe against. A prime
line restores both, and the ooze that would have become the first letter ends up on the lip
instead. It is deliberately the same move the start gcode makes: same lane, same fat bead.

The block travels above the part (Z + PRIME_LIFT) both ways and returns to the exact position
the pause interrupted, so the stream that follows resumes from where it thinks it is.

It is OPT-IN, and should stay that way. However carefully the crossings are lifted, this adds a
bed-level excursion and a return over the part to a print that had none, partway through a job
that may be a day long. Spend that risk when there is evidence the restart is what is wrong --
ragged FIRST features and clean later ones -- not pre-emptively. On the usb-cloud lockup the
stroke width was fixed first and this was deliberately left off, so the print could say which
of the two the fault actually was (2026-08-15).

Usage:
  color-change.py <gcode> --at-z <mm> [--gcode M600] [--prime] [--prime-vol <mm3>]
                          [--prime-flow <mm3/s>] [--prime-lane x0,x1,y] [--prime-z <mm>]
                          [--dry-run]

Exit codes: 0 ok · 2 usage · 3 no layer found at/above the plane · 4 already contains a pause (--allow-existing overrides for deliberate extra events)
            5 the purge lane is not clear of the print
"""
import re
import shutil
import sys

MARKER = "; lakeshore: filament change"

# Purge lane: the strip in FRONT of the print area that the machine's own start gcode purges
# onto (it runs X249->X199 at Y=-2.5). Ours sits to the left of that, on virgin sheet.
PRIME_X0, PRIME_X1, PRIME_Y = 190.0, 140.0, -2.5
PRIME_Y_STEP = 1.7      # second pass, laid back-to-front alongside the first
PRIME_Z = 0.3           # a hair above the machine's 0.2: this lane is outside the probed mesh
PRIME_VOL = 80.0        # mm3 total. The start-gcode intro line is ~41 mm3 over 50 mm.
PRIME_FLOW = 2.4        # mm3/s -- under the 2.5 TPU volumetric cap; purge slowly, not fast
PRIME_LIFT = 3.0        # travel this far above the substrate top on the way there and back
PRIME_CLEAR = 5.0       # required clearance between the lane and the printed footprint
FIL_AREA = 2.405        # mm2 of 1.75 mm filament


def parse_layers(lines):
    """Return [(index_of_;Z:_line, z_value)] from the slicer's layer table."""
    out = []
    for i, ln in enumerate(lines):
        m = re.match(r"^;Z:([0-9.]+)\s*$", ln)
        if m:
            out.append((i, float(m.group(1))))
    return out


def _config(lines, key):
    """Read one setting out of the config block PrusaSlicer appends to the gcode."""
    pat = re.compile(r"^;\s*" + re.escape(key) + r"\s*=\s*([0-9.]+)\s*$")
    for ln in reversed(lines):
        m = pat.match(ln)
        if m:
            return float(m.group(1))
    return None


def _num(line, letter):
    m = re.search(letter + r"(-?[0-9]*\.?[0-9]+)", line)
    return float(m.group(1)) if m else None


def printed_footprint(lines):
    """(xmin, ymin, xmax, ymax) of the extruding moves, ignoring ;TYPE:Custom blocks.

    The start gcode's own purge line lives at Y=-2.5 and is not part of the print, so
    counting it would make the lane look permanently occupied by itself.
    """
    x = y = 0.0
    custom = False
    box = [float("inf"), float("inf"), float("-inf"), float("-inf")]
    for ln in lines:
        s = ln.strip()
        if s.startswith(";TYPE:"):
            custom = s.startswith(";TYPE:Custom")
            continue
        if s.startswith(";") or not s.startswith(("G0", "G1")):
            continue
        nx, ny, e = _num(s, "X"), _num(s, "Y"), _num(s, "E")
        if nx is not None: x = nx
        if ny is not None: y = ny
        if e is not None and e > 0 and not custom:
            box[0] = min(box[0], x); box[1] = min(box[1], y)
            box[2] = max(box[2], x); box[3] = max(box[3], y)
    return tuple(box)


def resume_position(lines, idx):
    """The X/Y the print was at when the pause interrupted it.

    Scanned backwards from the insertion point rather than assumed, because the purge
    block has to put the nozzle back exactly there: the moves that follow a layer change
    are absolute in X/Y but were PLANNED from this position, and the first of them
    travels diagonally up to the next island. Starting that move from the purge lane
    would drag the nozzle across the part at bed height.
    """
    x = y = None
    for ln in reversed(lines[:idx]):
        s = ln.strip()
        if not s.startswith(("G0", "G1")):
            continue
        if x is None: x = _num(s, "X")
        if y is None: y = _num(s, "Y")
        if x is not None and y is not None:
            return x, y
    return None, None


def prime_block(x_res, y_res, z_res, retract, relative_e, lane=None,
                z=PRIME_Z, vol=PRIME_VOL, flow=PRIME_FLOW):
    """The purge-line gcode inserted after the pause. Returns a list of lines."""
    x0, x1, y0 = lane or (PRIME_X0, PRIME_X1, PRIME_Y)
    span = abs(x1 - x0)
    path = 2 * span                       # two passes down the lane and back
    e_per_mm = vol / FIL_AREA / path
    feed = round(flow / (vol / path) * 60, 1)     # mm/min at the requested volumetric rate
    e_pass = round(e_per_mm * span, 4)
    z_safe = round(z_res + PRIME_LIFT, 3)
    r = round(retract, 3)
    # The return pass ends at x0 having come from x1, so carrying on past x0 wipes onto
    # sheet the bead has not touched. Wiping back over it would just pick it up again.
    wipe = 1.0 if x0 > x1 else -1.0
    L = ["; lakeshore: purge line after the change ---------------------------------\n",
         ";TYPE:Custom\n",   # the lane is outside the print area on purpose; see gcode_check
         "G1 E-%.3f F2700 ; retract for the trip to the purge lane\n" % r,
         "G1 Z%.3f F720\n" % z_safe,
         "G1 X%.3f Y%.3f F9000 ; front lip, clear of the print\n" % (x0, y0),
         "G1 Z%.3f F720\n" % z,
         "G1 E%.3f F2700 ; deretract\n" % r,
         "G1 X%.3f Y%.3f E%.4f F%.1f ; purge %.0f mm3 at %.1f mm3/s\n"
         % (x1, y0, e_pass, feed, vol, flow),
         "G1 Y%.3f F1200\n" % (y0 + PRIME_Y_STEP),
         "G1 X%.3f Y%.3f E%.4f F%.1f ; purge, return pass\n"
         % (x0, y0 + PRIME_Y_STEP, e_pass, feed),
         "G1 X%.3f Z%.3f F8000 ; wipe close to the sheet\n" % (x0 + wipe * 8.0, z * 0.5),
         "G1 X%.3f Z%.3f F8000 ; snap away\n" % (x0 + wipe * 11.0, z),
         "G1 E-%.3f F2700\n" % r,
         "G1 Z%.3f F720\n" % z_safe,
         "G1 X%.3f Y%.3f F9000 ; back over the print, at the position the pause left\n"
         % (x_res, y_res),
         "G1 Z%.3f F720\n" % z_res,
         "G1 E%.3f F2700\n" % r,
         "; lakeshore: end purge line ------------------------------------------------\n"]
    if not relative_e:
        L.insert(2, "M83 ; the purge block is written in relative E\n")
        L.insert(-1, "M82\n")
        L.insert(-1, "G92 E0\n")
    return L


def lane_is_clear(footprint, lane=None, clear=PRIME_CLEAR):
    """The purge lane must not run into the print, and must be reachable."""
    x0, x1, y0 = lane or (PRIME_X0, PRIME_X1, PRIME_Y)
    fxmin, fymin, fxmax, fymax = footprint
    if fxmin == float("inf"):
        return "the gcode has no extrusion moves to check the lane against"
    lo, hi = min(x0, x1) - 12.0, max(x0, x1) + 12.0   # includes the wipe run-out either way
    top = max(y0, y0 + PRIME_Y_STEP)
    if top + clear > fymin and not (hi + clear < fxmin or lo - clear > fxmax):
        return ("purge lane Y=%.1f X[%.1f,%.1f] is within %.1f mm of the print "
                "(footprint X[%.1f,%.1f] Y[%.1f,%.1f])"
                % (y0, lo, hi, clear, fxmin, fxmax, fymin, fymax))
    return None


def main(argv):
    if len(argv) < 3:
        sys.exit("usage: color-change.py <gcode> --at-z <mm> [--gcode M600] [--dry-run]")
    path = argv[1]
    at_z = None
    change = "M600"
    dry = False
    allow_existing = False
    prime = False
    lane = None
    p_z, p_vol, p_flow = PRIME_Z, PRIME_VOL, PRIME_FLOW
    i = 2
    while i < len(argv):
        a = argv[i]
        if a == "--at-z":
            i += 1; at_z = float(argv[i])
        elif a == "--gcode":
            i += 1; change = argv[i]
        elif a == "--prime":
            prime = True
        elif a == "--prime-vol":
            i += 1; p_vol = float(argv[i]); prime = True
        elif a == "--prime-flow":
            i += 1; p_flow = float(argv[i]); prime = True
        elif a == "--prime-z":
            i += 1; p_z = float(argv[i]); prime = True
        elif a == "--prime-lane":
            i += 1; lane = tuple(float(v) for v in argv[i].split(",")); prime = True
        elif a == "--dry-run":
            dry = True
        elif a == "--allow-existing":
            allow_existing = True
        else:
            sys.exit(f"unknown option: {a}")
        i += 1
    if at_z is None:
        sys.exit("usage: --at-z is required")

    with open(path, encoding="utf-8") as stream:
        lines = stream.read().splitlines(keepends=True)
    if any(MARKER in ln for ln in lines) and not allow_existing:
        # Guard against accidentally double-inserting the SAME plane. A part that
        # genuinely has several colour events (e.g. a first-layer inlay: base colour,
        # inlay colour, back) passes --allow-existing explicitly, once per extra event,
        # each at a DIFFERENT --at-z.
        print(f"ERROR: {path} already contains a filament change "
              f"(pass --allow-existing for a deliberate additional event)", file=sys.stderr)
        return 4

    layers = parse_layers(lines)
    if not layers:
        print("ERROR: no ';Z:' layer markers found -- is this ASCII gcode?", file=sys.stderr)
        return 3

    # Swap before the first layer whose material lies entirely ABOVE the colour plane.
    # A layer labelled Z=k deposits material from (k - layer_height) to k, so the layer whose
    # label equals the plane is the LAST layer of the substrate (its top face IS the plane, and
    # it is the surface that shows through any gaps in the raised graphics). Swapping before it
    # paints that surface the new colour -- the "whole top went black" bug. The first layer that
    # actually lays raised-feature material is the next one up, whose BOTTOM sits at the plane.
    target = None
    for k, (idx, z) in enumerate(layers):
        bottom = layers[k-1][1] if k > 0 else 0.0     # this layer's bottom = previous layer's top
        if bottom >= at_z-1e-6:
            prev_z = bottom
            target = (idx, z)
            break
    if target is None:
        top = layers[-1][1]
        print(f"ERROR: no layer sits entirely above Z={at_z} (top layer is Z={top}); "
              f"the colour plane is at or above the last layer", file=sys.stderr)
        return 3
    idx, z = target

    n = sum(1 for _, zz in layers if zz < z)          # layers fully printed before the swap
    print(f"{path}")
    print(f"  colour plane      Z={at_z}")
    print(f"  swap before layer {n+1} of {len(layers)}  (first layer above the plane, Z={z})")
    print(f"  substrate top     Z={prev_z}  (last layer printed in the original colour)")
    print(f"  pause gcode       {change}")
    if abs(prev_z-at_z) > 1e-6:
        print(f"  note: no layer top lands exactly on Z={at_z}; the substrate ends at Z={prev_z} "
              f"and the new colour begins at Z={z}.")

    block = [f"{MARKER} at Z={z} (plane Z={at_z}) ---------------------------------\n",
             f"{change} ; swap filament, then resume\n",
             "; lakeshore: end filament change ------------------------------------\n"]
    if prime:
        why = lane_is_clear(printed_footprint(lines), lane)
        if why:
            print(f"ERROR: {why}", file=sys.stderr)
            return 5
        x_res, y_res = resume_position(lines, idx)
        if x_res is None or y_res is None:
            print("ERROR: could not find the position the pause interrupts", file=sys.stderr)
            return 5
        relative_e = not any(ln.startswith("M82") for ln in lines[:idx])
        retract = _config(lines, "filament_retract_length") or _config(lines, "retract_length") or 0.7
        block += prime_block(x_res, y_res, prev_z, retract, relative_e,
                             lane=lane, z=p_z, vol=p_vol, flow=p_flow)
        lx0, lx1, ly = lane or (PRIME_X0, PRIME_X1, PRIME_Y)
        print(f"  purge line        {p_vol:.0f} mm3 at {p_flow:.1f} mm3/s, "
              f"X{lx0:.0f}->{lx1:.0f} Y{ly} Z{p_z}")
        print(f"  resumes at        X{x_res} Y{y_res} Z{prev_z}  "
              f"(retract {retract} mm, {'relative' if relative_e else 'absolute'} E)")
    if dry:
        print("  (dry run - not modified)")
        return 0

    shutil.copyfile(path, path+".bak")
    lines.insert(idx, "".join(block))
    with open(path, "w", encoding="utf-8") as stream:
        stream.write("".join(lines))
    print(f"  inserted {change} before the Z={z} layer  (backup: {path}.bak)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
