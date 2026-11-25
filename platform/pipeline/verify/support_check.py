#!/usr/bin/env python3
"""Deterministic support checks over the final ASCII gcode.

Two failures this closes:
1. `support_material=1` with auto-generation off produced a plausible slice and ZERO support;
   every location check then passed vacuously while a cantilever printed in air.
2. Support inside a bore/socket can be impossible to remove. A numeric keep-out is stronger than
   eyeballing the support percentage.

Policy comes from slice_meta.json and optionally spec.yaml::slice.support. Keep-outs are evaluated
in PRINT coordinates, after the declared orientation. `frame: bbox-min` makes the two coordinates
relative to the model-extrusion bbox minimum; useful for a translated single-part plate.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
from dataclasses import dataclass

try:
    import yaml
except ImportError:  # pragma: no cover - CLI environment provides PyYAML; tests exercise it.
    yaml = None

_NUM = re.compile(r"([XYZEIJ])(-?[\d.]+)")  # accepts Orca's leading-dot E.01 / I.38
_SUPPORT_PREFIX = "support"


def _is_support(kind: str | None) -> bool:
    return bool(kind and kind.lower().startswith(_SUPPORT_PREFIX))


def _arc_points(px, py, pz, nx, ny, nz, i, j, clockwise):
    cx, cy = px + i, py + j
    radius = math.hypot(px - cx, py - cy)
    a0, a1 = math.atan2(py - cy, px - cx), math.atan2(ny - cy, nx - cx)
    if clockwise:
        while a1 > a0:
            a1 -= 2 * math.pi
    else:
        while a1 < a0:
            a1 += 2 * math.pi
    delta = a1 - a0
    count = max(2, int(abs(delta) * radius / 0.8))
    return [(cx + radius * math.cos(a0 + delta * k / count),
             cy + radius * math.sin(a0 + delta * k / count),
             pz + (nz - pz) * k / count) for k in range(count + 1)]


def parse_toolpaths(path):
    """Return extruding support/model line segments from Prusa- or Orca-flavoured gcode."""
    x = y = z = last_e = 0.0
    xyz_relative = False
    e_relative = False
    kind = None
    support, model, perimeter = [], [], []
    support_e = total_e = 0.0

    with open(path, "rb") as stream:
        for raw in stream:
            line = raw.decode("latin-1", errors="ignore").strip()
            if line.startswith(";TYPE:"):
                kind = line[6:].strip()
                continue
            if line.startswith("G90"):
                xyz_relative = False
                continue
            if line.startswith("G91"):
                xyz_relative = True
                continue
            if line.startswith("M82"):
                e_relative = False
                continue
            if line.startswith("M83"):
                e_relative = True
                continue
            if line.startswith("G92"):
                vals = {k: float(v) for k, v in _NUM.findall(line)}
                x, y, z = vals.get("X", x), vals.get("Y", y), vals.get("Z", z)
                last_e = vals.get("E", last_e)
                continue

            command = line.split(None, 1)[0] if line else ""
            if command not in ("G0", "G1", "G2", "G3"):
                continue
            vals = {k: float(v) for k, v in _NUM.findall(line)}
            px, py, pz = x, y, z
            if xyz_relative:
                nx, ny, nz = x + vals.get("X", 0.0), y + vals.get("Y", 0.0), z + vals.get("Z", 0.0)
            else:
                nx, ny, nz = vals.get("X", x), vals.get("Y", y), vals.get("Z", z)

            de = 0.0
            if "E" in vals:
                de = vals["E"] if e_relative else vals["E"] - last_e
                if not e_relative:
                    last_e = vals["E"]
            if de > 1e-6:
                if command in ("G2", "G3") and ("I" in vals or "J" in vals):
                    pts = _arc_points(px, py, pz, nx, ny, nz, vals.get("I", 0.0),
                                      vals.get("J", 0.0), command == "G2")
                    segments = list(zip(pts, pts[1:]))
                elif (px, py, pz) != (nx, ny, nz):
                    segments = [((px, py, pz), (nx, ny, nz))]
                else:
                    segments = []
                if segments:
                    if _is_support(kind):
                        support.extend(segments)
                        support_e += de
                    elif not (kind and kind.lower() == "custom"):
                        model.extend(segments)
                        if kind and "perimeter" in kind.lower():
                            perimeter.extend(segments)
                    total_e += de
            x, y, z = nx, ny, nz

    return {"support": support, "model": model, "perimeter": perimeter,
            "support_extrusion": support_e, "total_extrusion": total_e}


def toolpath_bbox(segments):
    """(min_x, min_y, min_z, max_x, max_y, max_z) over parse_toolpaths() segments, or None.

    PUBLIC because `frame: bbox-min` keep-outs are declared relative to it, so any consumer
    computing its own oriented keep-out geometry needs the same origin the gate uses. It was
    `_bbox`, and a venture checker imported it through the underscore -- coupling a downstream
    safety gate to a private symbol this module was free to rename. Keep it public and tested.
    """
    pts = [p for segment in segments for p in segment]
    if not pts:
        return None
    return tuple(min(p[i] for p in pts) for i in range(3)) + \
        tuple(max(p[i] for p in pts) for i in range(3))


# Legacy alias retained for older consumer scripts importing `_bbox`.
# Retire this alias once legacy consumer forks are migrated.
_bbox = toolpath_bbox


def _point_segment_distance(point, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]
    wx, wy = point[0] - a[0], point[1] - a[1]
    vv = vx * vx + vy * vy
    t = 0.0 if vv == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / vv))
    qx, qy = a[0] + t * vx, a[1] + t * vy
    return math.hypot(point[0] - qx, point[1] - qy)


def _add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _scale(v, scalar):
    return tuple(x * scalar for x in v)


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _unit(v):
    length = math.sqrt(_dot(v, v))
    if length <= 1e-10:
        raise ValueError("finite-cylinder axis must be non-zero")
    return _scale(v, 1.0 / length)


def _closest_segment_points(a0, a1, b0, b1):
    """Closest points on finite 3-D segments (Ericson, RTCD §5.1.9)."""
    d1, d2, r = _sub(a1, a0), _sub(b1, b0), _sub(a0, b0)
    aa, ee, ff = _dot(d1, d1), _dot(d2, d2), _dot(d2, r)
    if aa <= 1e-10 and ee <= 1e-10:
        return a0, b0
    if aa <= 1e-10:
        s, t = 0.0, max(0.0, min(1.0, ff / ee)) if ee > 1e-10 else 0.0
    else:
        cc = _dot(d1, r)
        if ee <= 1e-10:
            s, t = max(0.0, min(1.0, -cc / aa)), 0.0
        else:
            bb, denom = _dot(d1, d2), aa * ee - _dot(d1, d2) ** 2
            s = max(0.0, min(1.0, (bb * ff - cc * ee) / denom)) if abs(denom) > 1e-10 else 0.0
            t = (bb * s + ff) / ee
            if t < 0.0:
                t, s = 0.0, max(0.0, min(1.0, -cc / aa))
            elif t > 1.0:
                t, s = 1.0, max(0.0, min(1.0, (bb - cc) / aa))
    return _add(a0, _scale(d1, s)), _add(b0, _scale(d2, t))


def _segment_distance_3d(a0, a1, b0, b1):
    p, q = _closest_segment_points(a0, a1, b0, b1)
    return math.sqrt(_dot(_sub(p, q), _sub(p, q)))


def _cylinder_hit(segment, keepout, model_bbox):
    shape = keepout.get("shape", "cylinder")
    if shape == "finite-cylinder":
        center, axis = keepout.get("center"), keepout.get("axis")
        if not isinstance(center, (list, tuple)) or len(center) != 3:
            raise ValueError("finite-cylinder center must have three coordinates")
        if not isinstance(axis, (list, tuple)) or len(axis) != 3:
            raise ValueError("finite-cylinder axis must have three coordinates")
        center, axis = tuple(float(v) for v in center), _unit(tuple(float(v) for v in axis))
        frame = keepout.get("frame", "plate")
        if frame == "bbox-min":
            if model_bbox is None:
                raise ValueError("bbox-min keepout needs model extrusion")
            center = _add(center, model_bbox[:3])
        elif frame != "plate":
            raise ValueError("keepout frame must be plate or bbox-min")
        half, radius = float(keepout.get("half_length")), float(keepout["radius"])
        if half <= 0 or radius <= 0:
            raise ValueError("finite-cylinder radius and half_length must be positive")
        axis0, axis1 = _sub(center, _scale(axis, half)), _add(center, _scale(axis, half))
        distance = _segment_distance_3d(segment[0], segment[1], axis0, axis1)
        return distance < radius, distance

    axes = {"x": (0, (1, 2)), "y": (1, (0, 2)), "z": (2, (0, 1))}
    if shape != "cylinder":
        raise ValueError("unsupported keepout shape %r" % shape)
    axis = keepout.get("axis", "z").lower()
    if axis not in axes:
        raise ValueError("keepout axis must be x, y or z")
    axis_i, perp = axes[axis]
    center = list(keepout["center"])
    if len(center) != 2:
        raise ValueError("cylinder center must have two coordinates perpendicular to its axis")
    if keepout.get("frame", "plate") == "bbox-min":
        if model_bbox is None:
            raise ValueError("bbox-min keepout needs model extrusion")
        center[0] += model_bbox[perp[0]]
        center[1] += model_bbox[perp[1]]
    elif keepout.get("frame", "plate") != "plate":
        raise ValueError("keepout frame must be plate or bbox-min")

    a, b = segment
    axis_range = keepout.get("range")
    if axis_range is not None:
        lo, hi = sorted(float(v) for v in axis_range)
        if keepout.get("frame") == "bbox-min":
            lo += model_bbox[axis_i]
            hi += model_bbox[axis_i]
        seg_lo, seg_hi = sorted((a[axis_i], b[axis_i]))
        if seg_hi < lo or seg_lo > hi:
            return False, math.inf
    pa, pb = (a[perp[0]], a[perp[1]]), (b[perp[0]], b[perp[1]])
    distance = _point_segment_distance(center, pa, pb)
    return distance < float(keepout["radius"]), distance


def load_policy(meta_path=None, spec_path=None, force_required=False):
    required = bool(force_required)
    keepouts = []
    meta = {}
    if meta_path and os.path.exists(meta_path):
        with open(meta_path) as stream:
            meta = json.load(stream)
        required = required or bool(meta.get("support_requested"))
        spec_path = spec_path or meta.get("spec")
    if spec_path:
        if os.path.isdir(spec_path):
            spec_path = os.path.join(spec_path, "spec.yaml")
        if yaml is None:
            raise RuntimeError("PyYAML is required to read support policy from spec.yaml")
        with open(spec_path) as stream:
            spec = yaml.safe_load(stream) or {}
        support = (spec.get("slice") or {}).get("support") or {}
        required = required or bool(support.get("required"))
        keepouts = list(support.get("keepouts") or [])
    return {"required": required, "keepouts": keepouts, "spec": spec_path, "meta": meta}


def check_support(path, policy):
    paths = parse_toolpaths(path)
    hard, notes = [], []
    count = len(paths["support"])
    if policy.get("required") and count == 0:
        hard.append("support was requested/required but gcode has zero support extrusion")
    elif count:
        pct = 100.0 * paths["support_extrusion"] / paths["total_extrusion"] \
            if paths["total_extrusion"] else 0.0
        notes.append("%d support segment(s), %.1f%% of parsed extrusion" % (count, pct))
    else:
        notes.append("zero support segments (support not required)")

    # Translation anchor = object perimeter, not skirt/infill. Normalize a normal first-layer
    # centre (Z~0.2) back to the physical bed face Z=0 so CAD offsets remain meaningful.
    model_bbox = toolpath_bbox(paths["perimeter"] or paths["model"])
    if model_bbox and 0 <= model_bbox[2] <= 0.5:
        model_bbox = model_bbox[:2] + (0.0,) + model_bbox[3:]
    for keepout in policy.get("keepouts", []):
        label = keepout.get("id", "unnamed")
        hits, nearest = 0, math.inf
        try:
            # Validate the declared primitive even if the slicer emitted no support.
            # Otherwise a malformed safety policy passes exactly in the vacuous case
            # it was meant to guard.
            _cylinder_hit(((0.0, 0.0, 0.0), (0.0, 0.0, 0.0)), keepout, model_bbox)
            for segment in paths["support"]:
                hit, distance = _cylinder_hit(segment, keepout, model_bbox)
                nearest = min(nearest, distance)
                hits += int(hit)
        except (KeyError, TypeError, ValueError) as exc:
            hard.append("support keepout %s is invalid: %s" % (label, exc))
            continue
        if hits:
            hard.append("support enters keepout %s: %d segment(s), nearest %.3f mm < radius %.3f"
                        % (label, hits, nearest, float(keepout["radius"])))
        else:
            notes.append("keepout %s clear (nearest support %s)" %
                         (label, "none" if math.isinf(nearest) else "%.3f mm" % nearest))
    return {"passed": not hard, "hard": hard, "notes": notes, "paths": paths}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("gcode")
    parser.add_argument("--meta")
    parser.add_argument("--spec")
    parser.add_argument("--required", action="store_true")
    args = parser.parse_args(argv)
    # Say whether THIS run is the gate. Imported lazily and inside main() so the module stays
    # cheap for the callers that import it as a library rather than run it.
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.realpath(__file__)), ".."))
    import gates as _gates
    _gates.declare_mode("SUPPORT_RESULT", argv if argv is not None else _sys.argv[1:])
    policy = load_policy(args.meta, args.spec, args.required)
    result = check_support(args.gcode, policy)
    print("SUPPORT CHECK")
    for note in result["notes"]:
        print("  [PASS]", note)
    for failure in result["hard"]:
        print("  [HARD]", failure)
    print("SUPPORT_RESULT:", "PASS" if result["passed"] else "FAIL")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
