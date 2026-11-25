"""probe_check.py — evaluate a spec's ``probes:`` block against the exported solid.

A5 of docs/llm-in-the-loop-plan.md. CADTests showed reference-free B-rep assertions are the
strongest cheap signal of a broken generation, and this repo has had parts/_lib/probe.py since
day one — at 1/86 adoption. The plan's fix is to move the check from an idiom to a declaration:
a spec with fit-critical geometry declares the probes that protect it, and verify runs them
against the exported STEP.

WHAT A PROBE IS: an exact question about the final solid — "this wall box is entirely solid",
"this bore window is empty", "the overlap volume is zero". NOT a heuristic about how the author
thinks the part was built. Same rule as probe.py: the check measures the real geometry.

Region shapes: boxes only. A box needs no solver and covers the bore/window/ROI cases this repo
has paid for. Spheres/cylinders centred on a feature need nearest-point search; adding them is a
follow-up with a real need behind it.

probe forms:
  - {id, region, expect: inside|outside}              — the whole box must be occupied/empty
  - {id, region, expect: clear, of: {region: [...]}}  — no solid occupies the regions' overlap
  - {id, region, expect: spans_axis, axis, at, count} — a thin slab at `at` along `axis`, bounded
                                                         by `region`, must produce exactly `count`
                                                         connected section solids (topology only)

This module is PURE (no FreeCAD): evaluate_probes takes geometry summaries so it is unit-testable;
verify.py supplies them from the STEP. The FreeCAD-side evaluator lives in verify.py.
"""
from __future__ import annotations

import math
import os

_REGION_SHAPES = {"box"}
_SPAN_AXES = {"x", "y", "z"}


def _row(pid, status, message):
    return {"id": pid, "status": status, "message": message}


def _validate_region(pid, region, label="region"):
    rows = []
    if not isinstance(region, dict):
        return [_row(pid, "FAIL", "%s must be a mapping" % label)]
    shape = region.get("shape")
    if shape not in _REGION_SHAPES:
        return [_row(pid, "FAIL", "%s shape must be box (got %r)" % (label, shape))]
    for lo_key, hi_key in (("xmin", "xmax"), ("ymin", "ymax"), ("zmin", "zmax")):
        lo, hi = region.get(lo_key), region.get(hi_key)
        if lo is None and hi is None:
            continue
        numeric = (isinstance(lo, (int, float)) and not isinstance(lo, bool)
                   and isinstance(hi, (int, float)) and not isinstance(hi, bool))
        if not numeric:
            rows.append(_row(pid, "FAIL", "%s %s/%s must both be numeric" %
                             (label, lo_key, hi_key)))
        elif not math.isfinite(float(lo)) or not math.isfinite(float(hi)):
            rows.append(_row(pid, "FAIL", "%s %s/%s must be finite" %
                             (label, lo_key, hi_key)))
        elif lo >= hi:
            rows.append(_row(pid, "FAIL", "%s %s must be < %s" %
                             (label, lo_key, hi_key)))
    return rows


def validate_declarations(probes):
    """Static checks, runnable with no geometry at all. Every failure here is FAIL — these are
    schema errors, not marginal measurements."""
    rows = []
    if probes is None:
        return rows
    if not isinstance(probes, list):
        return [_row("probes", "FAIL", "probes must be a list")]
    if not probes:
        return rows
    seen = set()
    for idx, probe in enumerate(probes):
        fallback = "probe-%d" % (idx + 1)
        if not isinstance(probe, dict):
            rows.append(_row(fallback, "FAIL", "probe must be a mapping"))
            continue
        raw_id = probe.get("id")
        valid_id = isinstance(raw_id, str) and bool(raw_id.strip())
        pid = raw_id if valid_id else fallback
        if not valid_id:
            rows.append(_row(pid, "FAIL", "probe requires a non-empty string id"))
        elif pid in seen:
            rows.append(_row(pid, "FAIL", "probe id must be unique"))
        seen.add(pid)

        expect = probe.get("expect")
        region = probe.get("region")
        if expect not in ("inside", "outside", "clear", "spans_axis"):
            rows.append(_row(pid, "FAIL",
                             "expect must be inside|outside|clear|spans_axis, got %r" % (expect,)))
        elif expect == "clear":
            other = probe.get("of")
            if not isinstance(other, dict) or not other.get("region"):
                rows.append(_row(pid, "FAIL", "expect: clear requires `of: {region: ...}`"))
            else:
                rows.extend(_validate_region(pid, other["region"], "of.region"))
        elif expect == "spans_axis":
            if probe.get("axis") not in _SPAN_AXES:
                rows.append(_row(pid, "FAIL", "spans_axis requires axis: x|y|z"))
            at = probe.get("at")
            if (not isinstance(at, (int, float)) or isinstance(at, bool)
                    or not math.isfinite(float(at))):
                rows.append(_row(pid, "FAIL", "spans_axis requires a finite numeric `at` station"))
            count = probe.get("count")
            if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                rows.append(_row(pid, "FAIL", "spans_axis requires integer `count` >= 1"))

        rows.extend(_validate_region(pid, region))
        tol = probe.get("tol_mm3")
        if tol is not None and (not isinstance(tol, (int, float)) or isinstance(tol, bool)
                                or not math.isfinite(float(tol)) or tol < 0):
            rows.append(_row(pid, "FAIL", "tol_mm3 must be a finite number >= 0"))
    return rows


def evaluate_probes(probes, geometry):
    """Score declared probes against geometry results supplied by the caller.

    For inside/outside, geometry carries ``occupied_mm3`` and ``region_volume_mm3``. Using the
    observed volumes rather than a pre-judged boolean keeps the contract unambiguous and makes a
    partial intersection fail both predicates. Other probe forms carry ``measured`` (overlap
    volume or span count). A probe whose geometry could not be evaluated is FAIL, not SKIP — a
    probe that cannot answer is a probe that protects nothing.
    """
    if probes is None:
        return []
    rows = validate_declarations(probes)
    if not isinstance(probes, list):
        return rows
    for idx, probe in enumerate(probes):
        if not isinstance(probe, dict):
            continue
        raw_id = probe.get("id")
        pid = raw_id if isinstance(raw_id, str) and raw_id.strip() else "probe-%d" % (idx + 1)
        if any(row["id"] == pid and row["status"] == "FAIL" for row in rows):
            continue
        result = (geometry or {}).get(pid)
        if not isinstance(result, dict):
            rows.append(_row(pid, "FAIL", "probe could not be evaluated on the exported solid"))
            continue
        measured = result.get("measured")
        detail = result.get("detail", "")
        expect = probe.get("expect")
        if expect in ("inside", "outside"):
            occupied = result.get("occupied_mm3")
            region_volume = result.get("region_volume_mm3")
            numeric = (isinstance(occupied, (int, float)) and not isinstance(occupied, bool)
                       and isinstance(region_volume, (int, float))
                       and not isinstance(region_volume, bool)
                       and math.isfinite(float(occupied)) and math.isfinite(float(region_volume))
                       and region_volume > 0)
            if not numeric:
                rows.append(_row(pid, "FAIL", "probe returned no valid occupancy volumes"))
                continue
            occupied = float(occupied)
            region_volume = float(region_volume)
            tol = float(probe.get("tol_mm3", 1e-6))
            if occupied < -tol or occupied > region_volume + tol:
                rows.append(_row(pid, "FAIL",
                                 "occupancy %.6f is outside region-volume range 0..%.6f" %
                                 (occupied, region_volume)))
                continue
            if expect == "inside":
                error = max(0.0, region_volume - occupied)
                ok = error <= tol
                message = ("occupied %.6f/%.6f mm3; unfilled %.6f mm3 (limit %.6g)" %
                           (occupied, region_volume, error, tol))
            else:
                error = max(0.0, occupied)
                ok = error <= tol
                message = ("occupied %.6f/%.6f mm3 (limit %.6g)" %
                           (occupied, region_volume, tol))
            rows.append(_row(pid, "PASS" if ok else "FAIL",
                             message + (" — " + detail if detail else "")))
        elif expect == "clear":
            volume = (float(measured)
                      if isinstance(measured, (int, float)) and not isinstance(measured, bool)
                      and math.isfinite(float(measured)) and measured >= 0 else None)
            ok = volume is not None and volume <= float(probe.get("tol_mm3", 1e-6))
            rows.append(_row(pid, "PASS" if ok else "FAIL",
                             "overlap volume %s mm3 (limit %.6g)%s"
                             % ("%.6f" % volume if volume is not None else "unmeasured",
                                float(probe.get("tol_mm3", 1e-6)),
                                " — " + detail if detail else "")))
        elif expect == "spans_axis":
            want = probe.get("count")
            ok = isinstance(measured, int) and not isinstance(measured, bool) and measured == want
            rows.append(_row(pid, "PASS" if ok else "FAIL",
                             "section spans: %s (expected %s)%s"
                             % (measured, want, " — " + detail if detail else "")))
    return rows


def requires_probes(spec):
    """A spec must declare probes when it claims fit-critical geometry or fit-affecting
    structures. Gauges and pure envelopes (`fits:` without fit-critical dims) are exempt: a
    registration gauge's point is to BE measured, and an envelope has no internal mechanism."""
    dims = spec.get("dimensions") or []
    return bool(spec.get("fit_core") or spec.get("joints") or spec.get("fasteners")
                or any(isinstance(d, dict) and d.get("fit_critical") for d in dims))


def main(argv=None):
    import argparse
    import sys
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", nargs="?", help="a spec.yaml path")
    parser.add_argument("--requires", action="store_true",
                        help="exit 0 when the spec should declare probes, 1 otherwise")
    parser.add_argument("--validate-required", action="store_true",
                        help="validate declarations and fail if a fit-bearing spec has none")
    args = parser.parse_args(argv)
    # Say whether THIS run is the gate. Imported lazily and inside main() so the module stays
    # cheap for the callers that import it as a library rather than run it.
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.realpath(__file__)), ".."))
    import gates as _gates
    _gates.declare_mode("PROBE_DECLARATIONS_RESULT", argv if argv is not None else _sys.argv[1:])
    if not args.spec:
        parser.error("spec is required")
    import yaml
    try:
        with open(args.spec, encoding="utf-8") as stream:
            spec = yaml.safe_load(stream) or {}
    except (OSError, yaml.YAMLError) as exc:
        print("[FAIL] cannot read spec: %s" % exc)
        return 2
    need = requires_probes(spec)
    if args.validate_required:
        rows = validate_declarations(spec.get("probes"))
        if need and not spec.get("probes"):
            part = spec.get("part_id") or os.path.basename(os.path.dirname(args.spec))
            rows.append(_row("coverage", "FAIL",
                             "%s has fit-critical geometry but declares no probes" % part))
        for row in rows:
            print("[%s] %s — %s" % (row["status"], row["id"], row["message"]))
        passed = not any(row["status"] == "FAIL" for row in rows)
        print("PROBE_DECLARATIONS_RESULT:", "PASS" if passed else "FAIL")
        return 0 if passed else 2
    print("requires probes:", "yes" if need else "no")
    return 0 if need else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
