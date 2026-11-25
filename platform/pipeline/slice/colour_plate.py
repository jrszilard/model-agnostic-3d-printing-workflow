#!/usr/bin/env python3
"""colour_plate.py — colours that share a layer, on a one-nozzle printer, by swapping by hand.

color-change.py swaps BETWEEN layers: everything above a plane is the new colour. That cannot put
two colours side by side on one layer, which is what a flush inlay is (a white road line level with
the black road around it, printed face-down). This does, the way PrusaSlicer does it for an MMU:
the plate is one object whose colour regions are MODIFIER volumes with their own extruder, sliced
as single-extruder multi-material, and every tool change becomes a manual M600.

Why modifiers and not separate parts: the printed body stays ONE solid STL (the part's primary
model), so verify, previews, bed fit and the plate's geometry identity see the real shape. A
region only says which filament prints the body where it overlaps. Measured 2026-10-05 on 2.9.6:
an `extruder` on a ParameterModifier moves perimeters and solid infill inside it to that filament.

Three commands (slice.sh drives them when it is given `--colour <region.stl>=<n>`):

  build      --out <plate.3mf> --base <body.stl> --region <region.stl>=<n> ...
             One object: the body as a model part on filament 1, each region a modifier on
             filament n (2..). Coordinates are kept; the slicer centres the object as usual.
  overrides  --machine <printer profile> --region <region.stl>=<n> ... [--names black,white,...]
             The config lines slice.sh adds: single-extruder multi-material, one nozzle entry per
             filament (the nozzle read from the profile name), no wipe tower, and a tool-change
             macro that emits `M600` on every change except the start of the print, preceded by
             `M117 Load <NAME>` (the pause screen does not say which colour comes next; whether the
             Core One shows an M117 during the pause is untested as of 2026-10-06).
  centre     --config <saved .ini>
             The bed centre as "x,y", read from the printer's bed_shape. A 3MF keeps its own
             coordinates (an STL is centred by the slicer, a 3MF is not), so slice.sh passes this
             to --center.
  swaps      <gcode>     (the post-slice hook, via hooks/colour_swaps.py)
             Comments out the T<n> lines (the Core One has one tool; plain plates carry none), and
             after every swap inserts color-change.py's purge line + wipe in its own lane at the
             front of the sheet, then returns to where the swap interrupted. Collapses the per-filament
             metadata to one tool (see single_tool_metadata). Prints the swap table.

Exit codes: 0 ok · 2 usage · 3 bad input (unreadable STL, filament numbers) · 5 no clear purge lane
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import struct
import sys
import zipfile

HERE = os.path.dirname(os.path.realpath(__file__))
_spec = importlib.util.spec_from_file_location("color_change", os.path.join(HERE, "color-change.py"))
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)

SWAP_TAG = "; lakeshore: colour swap"
LOAD_TAG = "M117 Load "


def toolchange_gcode(names=()):
    """The macro: on every change but the first, name the colour to load, then pause for it."""
    pick = "".join("{%s next_extruder == %d}%s" % ("if" if i == 0 else "elsif", i, n.upper())
                   for i, n in enumerate(names))
    pick = (pick + "{else}filament {next_extruder + 1}{endif}") if names else "filament {next_extruder + 1}"
    return ("{if previous_extruder >= 0}" + LOAD_TAG + pick + "\\nM600 " + SWAP_TAG +
            ", filament {previous_extruder + 1} -> {next_extruder + 1}{endif}")


TOOLCHANGE_GCODE = toolchange_gcode()
# Purge lanes, in the order they are used: along the front of the sheet, clear of the start
# gcode's own purge (X249 -> X199, wipe to X199, at Y-2.5). Each lane is (x0, x1, y): two passes
# x0 -> x1 at y and back at y + 1.7, then a wipe out to x0 + 11, so a lane occupies
# [x1, x0 + 11] x [y, y + 1.7]. Columns 45 apart leave 4 mm between neighbours; rows 3.5 apart.
LANE_X0 = (185.0, 140.0, 95.0, 50.0)
LANE_LEN = 30.0
LANE_Y = (-2.5, 1.0, 4.5)
LANES = tuple((x0, x0 - LANE_LEN, y) for y in LANE_Y for x0 in LANE_X0)
PRIME_VOL = 40.0     # mm3: restores flow and wipes. The firmware's M600 load purges the colour.


def parse_region(text):
    """'path=N' -> (path, N). N is the filament number, 2 or more (the body is filament 1)."""
    path, sep, num = text.rpartition("=")
    if not sep or not path or not num.isdigit() or int(num) < 2:
        raise ValueError(f"a colour region is <stl>=<filament 2..>, got {text!r}")
    return path, int(num)


def check_regions(regions):
    nums = sorted({n for _, n in regions})
    if nums != list(range(2, 2 + len(nums))):
        raise ValueError(f"filament numbers must run 2..k without gaps, got {nums}")
    return 1 + len(nums)


def read_stl(path):
    """Indexed mesh from an ASCII or binary STL: (vertices, triangles), vertices deduplicated."""
    with open(path, "rb") as stream:
        data = stream.read()
    tris = []
    if len(data) >= 84:
        n = struct.unpack_from("<I", data, 80)[0]
        if 84 + 50 * n == len(data):
            for i in range(n):
                v = struct.unpack_from("<12f", data, 84 + 50 * i)
                tris.append((v[3:6], v[6:9], v[9:12]))
    if not tris:
        text = data.decode("ascii", errors="replace")
        pts = [tuple(float(c) for c in m.groups())
               for m in re.finditer(r"vertex\s+(\S+)\s+(\S+)\s+(\S+)", text)]
        if not pts or len(pts) % 3:
            raise ValueError(f"not a readable STL: {path}")
        tris = [tuple(pts[i:i + 3]) for i in range(0, len(pts), 3)]
    index, verts, faces = {}, [], []
    for tri in tris:
        face = []
        for p in tri:
            key = tuple(round(c, 5) for c in p)
            if key not in index:
                index[key] = len(verts)
                verts.append(key)
            face.append(index[key])
        if len(set(face)) == 3:
            faces.append(tuple(face))
    return verts, faces


_CT = ('<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/'
       'package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.'
       'openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType='
       '"application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
_RELS = ('<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxml'
         'formats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" '
         'Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
         '</Relationships>')


def build_3mf(out, base, regions):
    """Write a one-object 3MF: base = model part on filament 1, regions = modifiers on theirs."""
    check_regions(regions)
    vols = [(base, 1, "ModelPart")] + [(p, n, "ParameterModifier") for p, n in regions]
    verts, faces, ranges = [], [], []
    for path, fil, kind in vols:
        vs, fs = read_stl(path)
        b0, f0 = len(verts), len(faces)
        verts += vs
        faces += [(a + b0, b + b0, c + b0) for a, b, c in fs]
        ranges.append((os.path.basename(path), fil, kind, f0, len(faces) - 1))
    model = ['<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">'
             '<resources><object id="1" type="model"><mesh><vertices>']
    model += ['<vertex x="%.5f" y="%.5f" z="%.5f"/>' % v for v in verts]
    model += ["</vertices><triangles>"]
    model += ['<triangle v1="%d" v2="%d" v3="%d"/>' % f for f in faces]
    model += ['</triangles></mesh></object></resources><build><item objectid="1"/></build></model>']
    cfg = ['<?xml version="1.0" encoding="UTF-8"?>\n<config><object id="1" instances_count="1">'
           '<metadata type="object" key="name" value="%s"/>' % os.path.basename(base)]
    for name, fil, kind, a, b in ranges:
        cfg.append('<volume firstid="%d" lastid="%d">'
                   '<metadata type="volume" key="name" value="%s"/>'
                   '<metadata type="volume" key="volume_type" value="%s"/>'
                   '<metadata type="volume" key="extruder" value="%d"/></volume>'
                   % (a, b, name, kind, fil))
    cfg.append("</object></config>")
    tmp = out + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("3D/3dmodel.model", "".join(model))
        z.writestr("Metadata/Slic3r_PE_model.config", "".join(cfg))
    os.replace(tmp, out)
    return ranges


def nozzle_of(machine):
    m = re.search(r"(?:HF)?(\d+(?:\.\d+)?) nozzle", machine)
    if not m:
        raise ValueError(f"cannot read the nozzle diameter from the printer profile {machine!r}")
    return m.group(1)


def parse_names(text, filaments):
    names = [n.strip() for n in text.split(",")] if text else []
    if names and (len(names) != filaments or not all(re.fullmatch(r"[A-Za-z0-9-]{1,12}", n) for n in names)):
        raise ValueError(f"--names wants {filaments} short words, one per filament, got {text!r}")
    return names


def overrides(machine, filaments, names=()):
    d = nozzle_of(machine)
    return ["single_extruder_multi_material=1",
            "nozzle_diameter=" + ",".join([d] * filaments),
            "wipe_tower=0",
            "toolchange_gcode=" + toolchange_gcode(names)]


def bed_centre(config_text):
    m = re.search(r"^bed_shape\s*=\s*(.+)$", config_text, re.M)
    if not m:
        raise ValueError("no bed_shape in the saved printer configuration")
    pts = [tuple(float(c) for c in p.split("x")) for p in m.group(1).strip().split(",")]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return "%g,%g" % ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)


# The printer's firmware (Prusa-Firmware-Buddy, gcode_info.cpp) reads these comments to decide how many
# TOOLS the file needs: a second entry in any of them makes it a multi-tool file, and a Core One
# refuses it ("not enough tools", TR2 tr2-i1, 2026-10-06). Lists are ',' for the amounts and ';' for
# the names. The swaps are M600s on the one tool, so the file must say ONE: amounts summed, the name
# and colour of filament 1 kept.
_SUM_KEYS = ("filament used [mm]", "filament used [cm3]", "filament used [g]", "filament cost")
_FIRST_KEYS = ("filament_type", "extruder_colour")


def single_tool_metadata(lines):
    out, changed = [], []
    for ln in lines:
        m = re.match(r"^; (.+?) = (.*)$", ln.rstrip("\n"))
        key = m.group(1) if m else None
        if key in _SUM_KEYS and "," in m.group(2):
            total = sum(float(v) for v in m.group(2).split(","))
            ln = "; %s = %.2f\n" % (key, total)
            changed.append(key)
        elif key in _FIRST_KEYS and ";" in m.group(2):
            ln = "; %s = %s\n" % (key, m.group(2).split(";")[0])
            changed.append(key)
        elif key == "total toolchanges" and m.group(2).strip() not in ("", "0"):
            ln = "; total toolchanges = 0\n"     # the changes are M600 pauses, not tool changes
            changed.append(key)
        out.append(ln)
    return out, changed


def _layer_z(lines, idx):
    for ln in reversed(lines[:idx]):
        m = re.match(r"^;Z:([0-9.]+)\s*$", ln)
        if m:
            return float(m.group(1))
    return None


def rewrite_swaps(lines, lanes=LANES, vol=PRIME_VOL):
    """Return (new_lines, report). Raises ValueError when a swap has no clear purge lane."""
    swaps = [i for i, ln in enumerate(lines) if ln.startswith("M600") and SWAP_TAG in ln]
    footprint = cc.printed_footprint(lines)
    usable = [lane for lane in lanes if cc.lane_is_clear(footprint, lane) is None]
    if len(usable) < len(swaps):
        raise ValueError(f"{len(swaps)} swaps but only {len(usable)} purge lanes clear of the print")
    relative_e = not any(ln.startswith("M82") for ln in lines)
    retract = cc._config(lines, "retract_length") or 0.7
    inserts, report, counted = {}, [], {}
    for k, idx in enumerate(swaps):
        # number the colour message the macro put before this pause: "M117 Load WHITE 2/9"
        j = idx - 1
        while j >= 0 and not lines[j].strip():
            j -= 1
        if j >= 0 and lines[j].startswith(LOAD_TAG):
            counted[j] = "%s %d/%d\n" % (lines[j].rstrip("\n"), k + 1, len(swaps))
        x, y = cc.resume_position(lines, idx)
        z = _layer_z(lines, idx)
        if x is None or y is None or z is None:
            raise ValueError(f"cannot find where swap {k + 1} interrupts the print")
        layer = sum(1 for ln in lines[:idx] if ln.startswith(";LAYER_CHANGE"))
        change = lines[idx].split(",", 1)[1].strip() if "," in lines[idx] else ""
        inserts[idx] = cc.prime_block(x, y, z, retract, relative_e, lane=usable[k], vol=vol)
        load = lines[idx - 1].strip()[len(LOAD_TAG):] if lines[idx - 1].startswith(LOAD_TAG) else ""
        report.append(f"  swap {k + 1}: layer {layer}, Z {z:.2f}, {change}"
                      f"{' (load ' + load + ')' if load else ''}; "
                      f"purge lane X{usable[k][0]:.0f}->{usable[k][1]:.0f} Y{usable[k][2]}")
    out, stripped = [], 0
    for i, ln in enumerate(lines):
        if i in counted:
            out.append(counted[i])
            continue
        if re.match(r"^T\d+\s*$", ln):
            out.append("; lakeshore: %s (one-tool printer; the swap is the M600)\n" % ln.strip())
            stripped += 1
            continue
        out.append(ln)
        if i in inserts:
            out.extend(inserts[i])
    out, collapsed = single_tool_metadata(out)
    report.insert(0, f"{len(swaps)} manual swaps; {stripped} tool-select lines commented out; "
                     f"one-tool metadata: {', '.join(collapsed) or 'already one tool'}")
    return out, report


def swaps(path):
    with open(path, encoding="utf-8") as stream:
        lines = stream.read().splitlines(keepends=True)
    if any("lakeshore: end purge line" in ln for ln in lines) and \
            any(ln.startswith("; lakeshore: T") for ln in lines):
        print("colour swaps already processed; nothing to do")
        return 0
    try:
        new, report = rewrite_swaps(lines)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 5
    with open(path + ".tmp", "w", encoding="utf-8") as stream:
        stream.write("".join(new))
    os.replace(path + ".tmp", path)
    print("\n".join(report))
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--out", required=True)
    b.add_argument("--base", required=True); b.add_argument("--region", action="append", default=[])
    o = sub.add_parser("overrides"); o.add_argument("--machine", required=True)
    o.add_argument("--region", action="append", default=[])
    o.add_argument("--names", default="")
    s = sub.add_parser("swaps"); s.add_argument("gcode")
    c = sub.add_parser("centre"); c.add_argument("--config", required=True)
    args = p.parse_args(argv)
    try:
        if args.cmd == "swaps":
            return swaps(args.gcode)
        if args.cmd == "centre":
            with open(args.config, encoding="utf-8") as stream:
                print(bed_centre(stream.read()))
            return 0
        regions = [parse_region(r) for r in args.region]
        if not regions:
            raise ValueError("no colour regions given")
        if args.cmd == "build":
            for name, fil, kind, a, b_ in build_3mf(args.out, args.base, regions):
                print(f"  {kind:<17} filament {fil}: {name} ({b_ - a + 1} triangles)")
            return 0
        n = check_regions(regions)
        for line in overrides(args.machine, n, parse_names(args.names, n)):
            print(line)
        return 0
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
