"""Import-safe FreeCAD geometry observations shared with verify.py.

Run only in an appropriate CAD runtime. No CLI, spec/registry loading, stamps,
normalization, manufacturing or physical verdict. Callers supply private frozen
files for the lifetime of a process: the STEP cache is keyed by resolved path.
Returned shapes are shared; never tessellate/mutate them. Use a fresh process
for changed files. Deterministic/advisory classification remains in spec_check.
"""
import os
import Part
import Mesh


_STEP_SHAPES = {}


def _read_step(path):
    """Read a STEP once per process; never mutate the cached shape.

    FreeCAD's BoundBox can change after tessellation. The static cache tests
    cover both this module and verify.py to prohibit that regression.
    """
    key = os.path.realpath(path)
    shape = _STEP_SHAPES.get(key)
    if shape is None:
        shape = Part.Shape()
        shape.read(path)
        _STEP_SHAPES[key] = shape
    return shape


def _pick(part_dir, sub, ext):
    d = os.path.join(part_dir, sub)
    if not os.path.isdir(d):
        return None
    cands = sorted(f for f in os.listdir(d)
                   if f.lower().endswith(ext) and "coupon" not in f.lower() and not f.startswith("_"))
    return os.path.join(d, cands[0]) if cands else None


def cad_integrity(part_dir, spec):
    checks = {}
    step = spec.get("primary_step") and os.path.join(part_dir, spec["primary_step"]) or _pick(part_dir, "step", ".step")
    stl = spec.get("primary_stl") and os.path.join(part_dir, spec["primary_stl"]) or _pick(part_dir, "stl", ".stl")
    have_step = bool(step and os.path.exists(step))
    checks["step_present"] = have_step        # advisory: OpenSCAD-only parts cannot export STEP
    if have_step:
        shp = _read_step(step)
        checks["step_valid"] = bool(shp.isValid())
        checks["single_solid"] = (len(shp.Solids) == 1)
        # EVERY solid, not just Solids[0].
        checks["closed"] = bool(shp.Solids) and all(s.isClosed() for s in shp.Solids)
        checks["no_bad_faces"] = all(f.isValid() for f in shp.Faces)
    if stl and os.path.exists(stl):
        m = Mesh.Mesh(stl)
        checks["manifold"] = (not m.hasNonManifolds())
        checks["no_self_intersection"] = (not m.hasSelfIntersections())
    return checks, step, stl
