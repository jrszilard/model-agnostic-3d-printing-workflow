"""Pure spec checks: geometry conformance plus the independent dimension-truth gate.
No FreeCAD/geometry here — that lives in verify.py. This part is unit-tested."""

from dim_provenance import evaluate_provenance, evaluate_reference

# CAD integrity splits along the line AGENTS.md already draws: deterministic checks may BLOCK,
# sampled/heuristic ones may only WARN. These three are exact kernel facts about the B-rep —
# OCCT either reports the shape valid, its solids closed and its faces sound, or it does not.
CAD_HARD = ("step_valid", "closed", "no_bad_faces")

# Everything else is advisory ON PURPOSE, and each for its own reason:
#   single_solid           — a legitimate multi-part export has one solid per part
#                            (iris-circle-jig 11, photo-calibration-corner 89).
#   manifold /             — mesh heuristics. This project's hand-rolled twist-extruded threads
#   no_self_intersection     are self-intersecting by construction and print fine; see
#                            mesh_check.py's header and parts/tools/radius-gauge/README.md.
#   step_present           — three parts are OpenSCAD-only and cannot export STEP at all.


def evaluate_cad(checks):
    """Split raw CAD integrity checks into the blocking set and the advisory set.

    `passed` is the verdict: it depends ONLY on the hard set. `proven` is false when there is no
    STEP to check — the hard set is then vacuously true, which is not the same as proven, and the
    report must say so rather than printing a bare PASS.
    """
    hard = {k: v for k, v in checks.items() if k in CAD_HARD}
    advisory = {k: v for k, v in checks.items() if k not in CAD_HARD}
    # A part with NO artifact at all — no STEP and no STL — must not pass. Before the split the
    # verdict was `all(cad.values()) if cad else False`, so an empty check set failed; after it,
    # `checks` always contains step_present, so a bare `all(hard.values())` on an empty hard set
    # returned True and a part with nothing to check acquired a green CAD verdict.
    examined = bool(hard) or "manifold" in checks
    return {"hard": hard, "advisory": advisory,
            "passed": bool(examined) and all(hard.values()), "proven": bool(hard)}


# Chosen from measurement, not taste. Across every part in both repos that has both exports,
# tessellation noise tops out at 0.0118 mm — a curved face's bbox shrinks by the sagitta when it is
# triangulated — while the smallest REAL divergence is 0.5743 mm. A ~50x gap; 0.10 mm sits between
# them with room on both sides.
STEP_STL_TOL_MM = 0.10


def bbox_divergence(step_bbox, stl_bbox, tol=STEP_STL_TOL_MM):
    """Do a part's two exports describe the same solid?

    Nothing compared them until 2026-08-22, which is how parts/vent/k1c-elbow reached
    `status: released` with its STEP 9.887 mm larger than its STL on two axes — the archival master
    does not describe the thing that was printed and fitted.
    """
    delta = tuple(abs(a - b) for a, b in zip(step_bbox, stl_bbox))
    return {"delta_mm": delta, "worst_mm": max(delta), "agree": max(delta) <= tol, "tol_mm": tol}


def check_value(nominal, tol, measured):
    """Return (passed, deviation). passed if |measured - nominal| <= tol (inclusive)."""
    deviation = measured - nominal
    return (abs(deviation) <= tol, deviation)


def evaluate(dimensions, measured):
    """Evaluate a list of spec dimensions against measured values.

    dimensions: [{name, nominal, tol}, ...]
    measured:   {name: value_or_None}  (missing/None -> SKIP, not FAIL)
    Returns conformance rows plus `provenance`. `passed` requires both measured geometry
    conformance and trusted provenance for every dimension marked fit_critical.
    """
    rows = []
    measured_count = 0
    any_fail = False
    for d in dimensions:
        name = d["name"]
        val = measured.get(name)
        # A derived/string dimension may document a requirement without a numeric tolerance
        # or machine measurement recipe. It remains a deliberate SKIP rather than crashing verify.
        tol = d.get("tol")
        row = {"name": name, "nominal": d["nominal"], "tol": tol,
               "measured": val, "deviation": None, "status": "SKIP"}
        if val is not None and tol is not None:
            measured_count += 1
            ok, dev = check_value(d["nominal"], tol, val)
            row["deviation"] = dev
            row["status"] = "PASS" if ok else "FAIL"
            any_fail = any_fail or not ok
        rows.append(row)
    provenance = evaluate_provenance(dimensions)
    reference = evaluate_reference(dimensions)
    return {"passed": not any_fail and provenance["passed"] and reference["passed"],
            "dimensions_passed": not any_fail,
            "measured_count": measured_count, "rows": rows,
            "provenance": provenance, "reference": reference}
