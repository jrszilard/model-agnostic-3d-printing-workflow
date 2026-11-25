"""verify.py — assert a part's exports against its spec.yaml.
Run under FreeCAD:  freecadcmd platform/pipeline/verify/verify.py <part_dir>
Exit 0 = all measured dims within tolerance AND CAD integrity OK; nonzero otherwise.

CAD integrity splits by evidence class (AGENTS.md: deterministic BLOCKS, heuristic WARNS):
  BLOCK  step_valid · closed (every solid) · no_bad_faces   — exact OCCT facts about the B-rep
  WARN   step_present · single_solid · manifold · no_self_intersection
A part with no STEP reports B-rep validity as UNPROVEN rather than passed.
Dimensions: each spec dim may carry a `measure:` recipe -
  {method: bbox,  file: <stl>,  axis: x|y|z}                      -> mesh bbox length
  {method: slice, file: <step>, axis: x|y|z, at: <v>, ring: outer|inner}  -> section extent
Dims without a recipe are SKIP (e.g. derived walls)."""
import math
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yaml
import Part, Mesh
from FreeCAD import Vector
from spec_check import evaluate, evaluate_cad, bbox_divergence, STEP_STL_TOL_MM
from fastener_check import evaluate_fasteners
from joint_check import evaluate_joints
from fitcore_check import evaluate_fit_core
from probe_check import evaluate_probes, requires_probes


# One cache shared by all read sites; no registry imports in the geometry API.
from geometry import _read_step, _pick, cad_integrity


def _occupied_volume(shape, region):
    """Solid volume inside a probe region, boolean'd against only the solids that reach it.

    Exact, not a heuristic: a solid whose BoundBox misses the region's contributes exactly
    zero to the common, and this site already commoned the whole 26-solid compound, so OCCT
    sums the per-solid results either way. On balloon-lamp's hoop-68-front-blocks-inboard it
    keeps 2 of 26 solids and takes the boolean 1,098 ms -> 130 ms, returning the bit-identical
    2.664000000000007; that part's 10 volume probes went 10,402 ms -> 1,128 ms.

    A shape that is not made of solids alone (loose faces or shells, a nested compound) is
    commoned whole, and that guard is load-bearing, not defensive: OCCT's volume properties
    count an open shell. parts/lighting/bottle-lamp-carrier/vendor/umiki-bottle--hollow.step
    is a Compound<Shell,Solid>, and over its lower half the solids-only form returns
    166,637.97 mm3 where the whole-shape common returns 319,570.01. Three STEPs in the corpus
    are not solids-only today — that one, plus the lantern-open and sprung-open drafts under
    parts/lighting/balloon-lamp/step (Compound<Compound,Solid>).
    """
    solids_only = (shape.ShapeType == "Solid"
                   or (shape.ShapeType == "Compound"
                       and all(k.ShapeType == "Solid" for k in shape.childShapes())))
    if not solids_only:
        return float(shape.common(region).Volume)
    reaching = [s for s in shape.Solids if s.BoundBox.intersect(region.BoundBox)]
    if not reaching:
        # Proved on the compound, not just the easy single-solid case: a region parked
        # clear of balloon-lamp's 26-solid envelope makes OCCT's own whole-compound common
        # return 0.0 too, so the shortcut and the boolean agree to the bit.
        return 0.0
    return float(Part.Compound(reaching).common(region).Volume)


def _in_plane_extent(bb, axis):
    return {"z": max(bb.XLength, bb.YLength),
            "x": max(bb.YLength, bb.ZLength),
            "y": max(bb.XLength, bb.ZLength)}[axis]


def _measure(part_dir, rec):
    path = os.path.join(part_dir, rec["file"])
    if not os.path.exists(path):
        return None, "missing file %s" % rec["file"]
    if rec["method"] == "bbox":
        bb = Mesh.Mesh(path).BoundBox
        return {"x": bb.XLength, "y": bb.YLength, "z": bb.ZLength}[rec["axis"]], None
    if rec["method"] == "slice":
        shp = _read_step(path)
        nvec = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[rec["axis"]]
        wires = shp.slice(Vector(*nvec), rec["at"])
        exts = sorted(_in_plane_extent(w.BoundBox, rec["axis"]) for w in wires)
        if not exts:
            return None, "empty section at %s=%s" % (rec["axis"], rec["at"])
        return (exts[-1] if rec.get("ring", "outer") == "outer" else exts[0]), None
    return None, "unknown method %s" % rec["method"]


def _probe_region_shape(region, step):
    """Build a probe region solid from a STEP path. Only boxes today: xmin/xmax/ymin/ymax/
    zmin/zmax (None = the solid's own bound on that side, so a slab is `{xmin: 10, xmax: 10.5}`
    and a window is everything below z=0)."""
    if not isinstance(region, dict) or region.get("shape") != "box":
        return None
    if not step or not os.path.exists(step):
        return None
    shape = _read_step(step)
    bb = shape.BoundBox
    raw = (region.get("xmin", bb.XMin), region.get("xmax", bb.XMax),
           region.get("ymin", bb.YMin), region.get("ymax", bb.YMax),
           region.get("zmin", bb.ZMin), region.get("zmax", bb.ZMax))
    try:
        x0, x1, y0, y1, z0, z1 = (float(value) for value in raw)
    except (TypeError, ValueError):
        return None
    if (not all(math.isfinite(value) for value in (x0, x1, y0, y1, z0, z1))
            or x0 >= x1 or y0 >= y1 or z0 >= z1):
        return None
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, Vector(x0, y0, z0))


def evaluate_spec_probes(part_dir, probes, step):
    """Score a spec's probes against the exported STEP. verify-side; probe_check.py is pure.

    A region is a box. `inside` means the region's full volume is inside the solid; `outside`
    means its full volume is outside. `clear` means no solid occupies two regions' overlap. `spans_axis`
    is the thin-section check (the tapered-wall incident). A probe that cannot answer is FAIL.
    """
    geometry = {}
    shape = None
    if step and os.path.exists(step):
        shape = _read_step(step)
    if probes is not None and not isinstance(probes, list):
        return evaluate_probes(probes, geometry)
    for probe in probes or []:
        if not isinstance(probe, dict):
            continue
        pid = probe.get("id")
        if not pid:
            continue
        if shape is None:
            geometry[pid] = {"measured": None, "detail": "no STEP to probe"}
            continue
        region = _probe_region_shape(probe.get("region"), step)
        if region is None:
            geometry[pid] = {"measured": None, "detail": "region could not be built"}
            continue
        expect = probe.get("expect")
        region_volume = float(region.Volume)
        if expect in ("inside", "outside"):
            occupied = _occupied_volume(shape, region)
            geometry[pid] = {"occupied_mm3": occupied,
                             "region_volume_mm3": region_volume}
        elif expect == "clear":
            other = _probe_region_shape((probe.get("of") or {}).get("region"), step)
            if other is None:
                geometry[pid] = {"measured": None, "detail": "other region could not be built"}
            else:
                # The forbidden zone is where the two declared envelopes overlap. Measure actual
                # exported material there; region.cut(other) measured the opposite zone and made
                # disjoint declarations fail whenever the first region contained ordinary solid.
                forbidden = region.common(other)
                overlap = 0.0 if forbidden.isNull() else float(shape.common(forbidden).Volume)
                geometry[pid] = {"measured": overlap,
                                 "detail": "solid volume in region intersection"}
        elif expect == "spans_axis":
            axis = probe.get("axis", "z")
            try:
                at = float(probe.get("at"))
            except (TypeError, ValueError):
                geometry[pid] = {"measured": None, "detail": "station is not numeric"}
                continue
            if axis not in ("x", "y", "z") or not math.isfinite(at):
                geometry[pid] = {"measured": None, "detail": "station or axis is invalid"}
                continue
            bbox = shape.BoundBox
            dims = {"x": (0.2, bbox.YLength * 3, bbox.ZLength * 3),
                    "y": (bbox.XLength * 3, 0.2, bbox.ZLength * 3),
                    "z": (bbox.XLength * 3, bbox.YLength * 3, 0.2)}[axis]
            origin = {"x": Vector(at, bbox.YMin - bbox.YLength, bbox.ZMin - bbox.ZLength),
                      "y": Vector(bbox.XMin - bbox.XLength, at, bbox.ZMin - bbox.ZLength),
                      "z": Vector(bbox.XMin - bbox.XLength, bbox.YMin - bbox.YLength, at)}[axis]
            slab = Part.makeBox(*dims, origin)
            # Scope the station to the declared region. The first implementation built `region`
            # and then ignored it, so a remote feature elsewhere in the part changed the count.
            scoped_slab = slab.common(region)
            pieces = shape.common(scoped_slab)
            geometry[pid] = {"measured": len(pieces.Solids),
                             "detail": "section at %s=%.3f inside declared region" % (axis, at)}
        else:
            geometry[pid] = {"measured": None, "detail": "unsupported expect"}
    return evaluate_probes(probes, geometry)


def observe(part_dir, step, stl):
    """The OBSERVE step: exact kernel scalars, and the two exports checked against each other.

    Nothing in this pipeline compared a part's STEP against its own STL, which is how
    parts/vent/k1c-elbow reached `status: released` with a 9.887 mm divergence on two axes — its
    archival master does not describe the thing that was printed and fitted. This is ~30 lines and
    catches that class on every verify.

    The scalars are the published feedback channel, not an invention: Embodied CAD grounds its
    agent on exactly these fields from FreeCAD's kernel, and CADSmith's Judge consumes the same
    list from OpenCASCADE. Emitting them here is what a model critique would later read.
    """
    report = {"scalars": None, "divergence": None, "agree": None}
    if not (step and os.path.exists(step)):
        return report
    shp = _read_step(step)
    box = shp.BoundBox
    com = shp.Solids[0].CenterOfMass if shp.Solids else None
    report["scalars"] = {
        "volume_mm3": shp.Volume,
        "bbox_mm": (box.XLength, box.YLength, box.ZLength),
        "center_of_mass": (com.x, com.y, com.z) if com else None,
        "solids": len(shp.Solids), "faces": len(shp.Faces),
        "edges": len(shp.Edges), "vertices": len(shp.Vertexes),
    }
    if stl and os.path.exists(stl):
        mb = Mesh.Mesh(stl).BoundBox
        step_bbox = (box.XLength, box.YLength, box.ZLength)
        stl_bbox = (mb.XLength, mb.YLength, mb.ZLength)
        div = bbox_divergence(step_bbox, stl_bbox)
        report["divergence"] = dict(div, step_bbox=step_bbox, stl_bbox=stl_bbox)
        report["agree"] = div["agree"]
    return report


def main(part_dir):
    with open(os.path.join(part_dir, "spec.yaml")) as stream:
        spec = yaml.safe_load(stream)
    dims = spec.get("dimensions", [])
    measured, notes = {}, {}
    for d in dims:
        rec = d.get("measure")
        if not rec:
            continue
        val, err = _measure(part_dir, rec)
        measured[d["name"]] = val
        if err:
            notes[d["name"]] = err
    rep = evaluate(dims, measured)
    fasteners = evaluate_fasteners(spec.get("fasteners"))
    joints = evaluate_joints(spec.get("joints"))
    fitcore = evaluate_fit_core(spec.get("fit_core"))
    cad, step, stl = cad_integrity(part_dir, spec)
    probes = evaluate_spec_probes(part_dir, spec.get("probes"), step)
    obs = observe(part_dir, step, stl)

    print("\n=== verify: %s ===" % spec.get("part_id", part_dir))
    print("primary STEP: %s" % (os.path.relpath(step, part_dir) if step else "(none)"))
    print("primary STL:  %s" % (os.path.relpath(stl, part_dir) if stl else "(none)"))
    print("\nCAD integrity (B-rep kernel facts BLOCK; mesh/topology heuristics WARN):")
    cadrep = evaluate_cad(cad)
    cad_ok = cadrep["passed"]
    for k in sorted(cadrep["hard"]):
        print("  [%s] %s" % ("PASS" if cadrep["hard"][k] else "FAIL", k))
    for k in sorted(cadrep["advisory"]):
        v = cadrep["advisory"][k]
        print("  [%s] %s" % ("ok  " if v else "WARN", k))
    if not cadrep["proven"]:
        print("  [NOTE] no STEP export — B-rep validity is UNPROVEN, not passed. "
              "The verdict below rests on the spec and the mesh alone.")
    if obs["scalars"]:
        sc = obs["scalars"]
        print("\nObserved solid (exact kernel scalars — the feedback channel, informational):")
        print("  volume %.2f mm3 · bbox %.3f x %.3f x %.3f · solids %d · faces %d · edges %d · verts %d"
              % (sc["volume_mm3"], sc["bbox_mm"][0], sc["bbox_mm"][1], sc["bbox_mm"][2],
                 sc["solids"], sc["faces"], sc["edges"], sc["vertices"]))
        if sc["center_of_mass"]:
            print("  center of mass  %.3f, %.3f, %.3f" % sc["center_of_mass"])
    if obs["divergence"] is not None:
        dv = obs["divergence"]
        if obs["agree"]:
            print("  [ok  ] step_stl_agree — exports match within %.2f mm" % STEP_STL_TOL_MM)
        else:
            print("  [WARN] step_stl_agree — THE TWO EXPORTS ARE NOT THE SAME SOLID")
            print("         STEP %.3f x %.3f x %.3f" % dv["step_bbox"])
            print("         STL  %.3f x %.3f x %.3f" % dv["stl_bbox"])
            print("         delta %.4f, %.4f, %.4f mm (tolerance %.2f)"
                  % (dv["delta_mm"][0], dv["delta_mm"][1], dv["delta_mm"][2], STEP_STL_TOL_MM))
            print("         One of them is stale. The STL is what gets sliced and printed; the STEP")
            print("         is the archival master downstream consumers read. Diagnose before you")
            print("         trust either for a remake. ADVISORY for now — see docs/llm-in-the-loop-plan.md A1b.")

    print("\nDimensions (nominal +/- tol vs measured):")
    print("  %-26s %8s %6s %10s %9s  %s" % ("name", "nominal", "tol", "measured", "dev", "status"))
    for r in rep["rows"]:
        nominal = "%.2f" % r["nominal"] if isinstance(r["nominal"], (int, float)) else str(r["nominal"])
        tol = "-" if r["tol"] is None else "%.2f" % r["tol"]
        meas = "-" if r["measured"] is None else "%.3f" % r["measured"]
        dev = "" if r["deviation"] is None else "%+.3f" % r["deviation"]
        note = " (%s)" % notes[r["name"]] if r["name"] in notes else ""
        print("  %-26s %8s %6s %10s %9s  %s%s" %
              (r["name"], nominal, tol, meas, dev, r["status"], note))

    provenance = rep["provenance"]
    counts = provenance["counts"]
    print("\nDimension provenance (truth of the spec, independent of CAD conformance):")
    print("  measured %d · standard %d · estimated %d · placeholder %d · pending %d · unrecorded %d" %
          (counts["measured"], counts["standard"], counts["estimated"], counts["placeholder"],
           counts.get("pending-measurement", 0), counts["unrecorded"]))
    for row in provenance["rows"]:
        if row["status"] in ("FAIL", "PASS", "DEBT"):
            print("  [%s] %-24s %-11s fit_critical=%s — %s" %
                  (row["status"], row["name"], row["provenance"],
                   str(row["fit_critical"]).lower(), row["message"]))
    if counts["unrecorded"] and provenance["passed"]:
        print("  [NOTE] legacy unrecorded dimensions are allowed only because none declares fit_critical")

    reference = rep.get("reference") or {"declared": 0, "passed": True, "rows": []}
    if reference["declared"] or not reference["passed"]:
        print("\nReference relationship (replicate=compare to original; deviate=assert intent; "
              "originate=assert only):")
        print("  %d declared" % reference["declared"])
        for row in reference["rows"]:
            if row["status"] == "FAIL":
                print("  [FAIL] %-24s %s" % (row["name"], row["message"]))

    print("\nFasteners (declared strategy; source assertion + coupon still prove the joint):")
    if not fasteners["rows"]:
        print("  (none declared)")
    for row in fasteners["rows"]:
        print("  [%s] %-24s %s" % (row["status"], row["id"], row["message"]))

    print("\nJoints (registry-backed declaration; coupon + reality gate still prove the fit):")
    if not joints["rows"]:
        print("  (none declared)")
    for row in joints["rows"]:
        print("  [%s] %-24s %s" % (row["status"], row["id"], row["message"]))

    print("\nFit core (semantic mating identity; final-solid ROI assertions remain source-owned):")
    if not fitcore["declared"]:
        print("  (none declared)")
    else:
        print("  core %s · source %s · %d variant(s)" %
              (fitcore["fingerprint"], fitcore.get("source"), len(fitcore["variants"])))
        for status, name, message in fitcore["rows"]:
            print("  [%s] %-24s %s" % (status, name, message))

    print("\nProbes (exact B-rep assertions over the final solid — A5):")
    probe_coverage_ok = bool(spec.get("probes")) or not requires_probes(spec)
    if not spec.get("probes"):
        print("  (none declared)")
        if not probe_coverage_ok:
            print("  [FAIL] this spec has fit-critical geometry but declares no probes")
    for row in probes:
        print("  [%s] %-24s %s" % (row["status"], row["id"], row["message"]))
    probes_ok = (probe_coverage_ok
                 and all(row["status"] != "FAIL" for row in probes))

    overall = (rep["passed"] and cad_ok and fasteners["passed"] and joints["passed"]
               and fitcore["passed"] and probes_ok)
    # DEBT is a third verdict, not a softer PASS. Everything checkable checks out AND at least one
    # fit-critical nominal is declared unproven with the iteration and date that close it. It is
    # reported as its own word so nobody downstream has to infer it, and so a reader of the stamp
    # cannot mistake this part for one whose numbers are known.
    debt = provenance.get("debt") or []
    verdict = "PASS" if overall else "FAIL"
    if overall and debt:
        verdict = "DEBT"
    print("\nmeasured %d dim(s); dims %s; spec truth %s; CAD %s; fasteners %s; joints %s; fit core %s; probes %s  ->  %s" % (
        rep["measured_count"], "PASS" if rep["dimensions_passed"] else "FAIL",
        "PASS" if (provenance["passed"] and reference["passed"]) else "FAIL",
        ("PASS" if cadrep["proven"] else "UNPROVEN") if cad_ok else "FAIL",
        "PASS" if fasteners["passed"] else "FAIL", "PASS" if joints["passed"] else "FAIL",
        "PASS" if fitcore["passed"] else "FAIL",
        "PASS" if probes_ok else "FAIL",
        verdict))
    if verdict == "DEBT":
        print("  measurement debt: %s" % ", ".join(debt))
        print("  a prototype plate may be fabricated to CLOSE this debt; a release may not carry it.")
    print("VERIFY_RESULT: %s" % verdict)  # machine-readable for the wrapper
    sys.stdout.flush()  # freecadcmd can exit without flushing block-buffered stdout
    return 0 if overall else 1


# NOTE: run unconditionally — freecadcmd sets __name__ to the module basename, not
# "__main__", so a standard guard would never fire. This file is only ever executed as a
# FreeCAD script (it imports Part/Mesh/FreeCAD), never imported, so this is safe.
# PART_DIR env is preferred: freecadcmd tries to OPEN any path passed as an argv.
_part = os.environ.get("PART_DIR") or next((a for a in sys.argv[1:] if os.path.isdir(a)), None)
if not _part:
    print("usage: PART_DIR=<dir> freecadcmd verify.py"); sys.exit(2)
sys.exit(main(_part))
