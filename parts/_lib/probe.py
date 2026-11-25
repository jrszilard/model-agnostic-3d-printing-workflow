"""Reusable assertions over the SOLID, not over how an author thinks it was built.

This module deliberately does not import CadQuery: the functions duck-type Workplane/Shape objects,
so plain-Python registry tests remain dependency-free while generators use it under cadquery-env.

A guard must receive the REAL feature geometry it protects. Comparing a label against `END_PAD`,
when the hole edge lives somewhere else, is a proxy-constant check that can pass its own defect.
Construct the hole/cutter/ROI once, pass that object here, and measure the final result.

Worked patterns:
- USB cloud: containment, clashes, rim-wall growth, off-face glyph/rail probes.
- Wiper adaptor (GPT-5.6 Sol -> Terra): valid one-solid BReps still dropped a hook or widened its
  fit-proven grip. `assert_frozen_region` compares final and reference solids inside the same ROI;
  `assert_bbox_contains` proves a fused component was not silently lost.
- CadQuery/OCC folklore: union additivity catches fused plate parts; face count can prove a fillet
  when volume delta cannot; thin section slabs expose internal material spans before slicing.
- Plates: a compound's solid count never sees pieces that touch (TR3S i4); `assert_pieces_apart`
  measures the gaps.
"""
from __future__ import annotations

class ProbeError(RuntimeError):
    pass


def shape(obj):
    """Return a shape from either a CadQuery Workplane or an already-shape-like object."""
    if obj is None:
        return None
    val = getattr(obj, "val", None)
    return val() if callable(val) else obj


def is_null(obj):
    obj = shape(obj)
    if obj is None:
        return True
    check = getattr(obj, "isNull", None)
    return bool(check()) if callable(check) else False


def volume(obj):
    obj = shape(obj)
    if obj is None or is_null(obj):
        return 0.0
    measure = getattr(obj, "Volume", None)
    if not callable(measure):
        raise TypeError("object has no Volume(): %r" % type(obj))
    return float(measure())


def solids(obj):
    obj = shape(obj)
    if obj is None or is_null(obj):
        return []
    getter = getattr(obj, "Solids", None)
    if callable(getter):
        return list(getter())
    return [obj]


def solid_count(obj):
    return len(solids(obj))


def face_count(obj):
    obj = shape(obj)
    getter = getattr(obj, "Faces", None)
    if not callable(getter):
        raise TypeError("object has no Faces(): %r" % type(obj))
    return len(getter())


def bbox(obj):
    obj = shape(obj)
    getter = getattr(obj, "BoundingBox", None)
    if not callable(getter):
        raise TypeError("object has no BoundingBox(): %r" % type(obj))
    return getter()


def _boolean(a, method, b):
    a, b = shape(a), shape(b)
    fn = getattr(a, method, None)
    if not callable(fn):
        raise TypeError("object has no %s(): %r" % (method, type(a)))
    return fn(b)


def intersection(a, b):
    return _boolean(a, "intersect", b)


def difference(a, b):
    return _boolean(a, "cut", b)


def intersection_volume(a, b):
    return volume(intersection(a, b))


def outside_volume(feature, host):
    """Volume of `feature` that is not contained by `host`. Order is intentional."""
    return volume(difference(feature, host))


def assert_valid(obj, label="solid"):
    obj = shape(obj)
    check = getattr(obj, "isValid", None)
    if not callable(check) or not check():
        raise ProbeError("%s is not a valid BRep" % label)
    return obj


def assert_single_solid(obj, label="result"):
    count = solid_count(obj)
    if count != 1:
        raise ProbeError("%s has %d solids; expected exactly 1" % (label, count))
    return shape(obj)


def assert_clear(a, b, tol=1e-6, label="features"):
    amount = intersection_volume(a, b)
    if amount > tol:
        raise ProbeError("%s intersect by %.6f mm3 (limit %.6f)" % (label, amount, tol))
    return amount


def assert_contained(feature, host, tol=0.05, label="feature"):
    amount = outside_volume(feature, host)
    if amount > tol:
        raise ProbeError("%s has %.6f mm3 outside its host (limit %.6f)" %
                         (label, amount, tol))
    return amount


def assert_margin(grown_feature, host, margin, tol=0.05, label="feature"):
    """Assert a caller-grown feature stays contained; growth construction remains source-owned."""
    amount = outside_volume(grown_feature, host)
    if amount > tol:
        raise ProbeError("%s has less than %.3f mm margin (grown probe escapes by %.6f mm3)" %
                         (label, margin, amount))
    return amount


def _bounds(bb, axis):
    return getattr(bb, axis + "min"), getattr(bb, axis + "max")


def assert_bbox_contains(container, feature, tol=1e-5, label="feature"):
    """Catch an OCC fuse that returns one valid solid after silently dropping a component."""
    cb, fb = bbox(container), bbox(feature)
    failures = []
    for axis in "xyz":
        c0, c1 = _bounds(cb, axis)
        f0, f1 = _bounds(fb, axis)
        if c0 > f0 + tol:
            failures.append("%smin %.6f > %.6f" % (axis, c0, f0))
        if c1 < f1 - tol:
            failures.append("%smax %.6f < %.6f" % (axis, c1, f1))
    if failures:
        raise ProbeError("%s envelope was lost: %s" % (label, "; ".join(failures)))
    return cb


def assert_volume_range(obj, minimum=None, maximum=None, label="solid"):
    amount = volume(obj)
    if minimum is not None and amount < minimum:
        raise ProbeError("%s volume %.6f < minimum %.6f" % (label, amount, minimum))
    if maximum is not None and amount > maximum:
        raise ProbeError("%s volume %.6f > maximum %.6f" % (label, amount, maximum))
    return amount


def assert_volume_additive(parts, combined, abs_tol=1e-3, rel_tol=1e-6, label="union"):
    """A disjoint plate union must preserve sum(volume); loss means overlap/fusion.

    OCC recomputes B-spline solids, so use max(abs_tol, expected*rel_tol), not exact equality.
    """
    expected = sum(volume(part) for part in parts)
    actual = volume(combined)
    tolerance = max(abs_tol, abs(expected) * rel_tol)
    if abs(expected - actual) > tolerance:
        raise ProbeError("%s is not volume-additive: parts %.6f, result %.6f, delta %+.6f"
                         % (label, expected, actual, actual - expected))
    return expected, actual


def _box_gap(a, b):
    """The gap between two shapes' bounding boxes: never more than the gap between the shapes."""
    ga, gb = bbox(a), bbox(b)
    total = 0.0
    for axis in "xyz":
        a0, a1 = _bounds(ga, axis)
        b0, b1 = _bounds(gb, axis)
        total += max(b0 - a1, a0 - b1, 0.0) ** 2
    return total ** 0.5


def assert_pieces_apart(pieces, min_gap, label="plate"):
    """Each piece on a plate is one solid, and every two are at least `min_gap` apart.

    `len(Compound.makeCompound(pieces).Solids()) == len(pieces)` cannot see pieces that touch or
    overlap: a compound bundles shapes and never merges them, so the count holds while the slicer
    prints the overlap as one block (TR3S i4's lettered tabs). It does catch a piece that came apart,
    so this keeps that. `pieces` holds shapes or (name, shape) pairs. Pairs whose bounding boxes are
    `min_gap` apart are not measured exactly. Returns the least gap found.
    """
    named = [p if isinstance(p, tuple) else ("piece %d" % (i + 1), p) for i, p in enumerate(pieces)]
    named = [(name, shape(obj)) for name, obj in named]
    for name, obj in named:
        assert_single_solid(obj, "%s: %s" % (label, name))
    least = float("inf")
    for i, (name_a, a) in enumerate(named):
        for name_b, b in named[i + 1:]:
            gap = _box_gap(a, b)
            if gap < min_gap:
                gap = float(a.distance(b))
            if gap < min_gap:
                raise ProbeError("%s: %s and %s are %.2f mm apart (under %.2f): they print as one piece"
                                 % (label, name_a, name_b, gap, min_gap))
            least = min(least, gap)
    return least


def assert_face_count(obj, expected=None, minimum=None, maximum=None, label="solid"):
    """Face topology can prove a fillet when convex/concave volume deltas cancel to zero."""
    count = face_count(obj)
    if expected is not None and count != expected:
        raise ProbeError("%s has %d faces; expected %d" % (label, count, expected))
    if minimum is not None and count < minimum:
        raise ProbeError("%s has %d faces; minimum %d" % (label, count, minimum))
    if maximum is not None and count > maximum:
        raise ProbeError("%s has %d faces; maximum %d" % (label, count, maximum))
    return count


def _bbox_delta(a, b):
    out = {}
    for axis in "xyz":
        a0, a1 = _bounds(a, axis)
        b0, b1 = _bounds(b, axis)
        out[axis + "min"], out[axis + "max"] = a0 - b0, a1 - b1
    return out


def assert_frozen_region(actual, reference, roi, volume_tol=1e-5, bbox_tol=None,
                         label="frozen region", require_reference=True):
    """Prove neighboring geometry did not alter a fit-proven interface inside `roi`.

    Compare separate intersections. `actual.cut(reference).intersect(roi)` is attractive but OCC
    coincidence can produce a false residual where identical faces meet; direct ROI equality was
    stable on the H94 wiper grip.
    """
    got, want = intersection(actual, roi), intersection(reference, roi)
    got_v, want_v = volume(got), volume(want)
    if require_reference and want_v <= volume_tol:
        raise ProbeError("%s ROI misses the reference geometry; comparison would pass vacuously"
                         % label)
    if abs(got_v - want_v) > volume_tol:
        raise ProbeError("%s volume changed by %+.6f mm3 (actual %.6f, reference %.6f)" %
                         (label, got_v - want_v, got_v, want_v))
    deltas = None
    if bbox_tol is not None and got_v > 0 and want_v > 0:
        deltas = _bbox_delta(bbox(got), bbox(want))
        bad = {name: delta for name, delta in deltas.items() if abs(delta) > bbox_tol}
        if bad:
            raise ProbeError("%s bbox changed: %s" %
                             (label, ", ".join("%s=%+.6f" % item for item in bad.items())))
    return {"actual_volume": got_v, "reference_volume": want_v, "bbox_delta": deltas}


def section_spans(solid, slab, axis="x", merge_tol=1e-6):
    """Return occupied intervals where a caller-defined thin section slab crosses `solid`."""
    if axis not in "xyz":
        raise ValueError("axis must be x, y or z")
    intervals = sorted(_bounds(bbox(piece), axis) for piece in solids(intersection(solid, slab)))
    merged = []
    for lo, hi in intervals:
        if merged and lo <= merged[-1][1] + merge_tol:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def assert_section_spans(solid, slab, expected, axis="x", tol=1e-3, label="section"):
    got = section_spans(solid, slab, axis)
    if len(got) != len(expected):
        raise ProbeError("%s has %d span(s) %r; expected %d %r" %
                         (label, len(got), got, len(expected), expected))
    for index, ((g0, g1), (e0, e1)) in enumerate(zip(got, expected)):
        if abs(g0 - e0) > tol or abs(g1 - e1) > tol:
            raise ProbeError("%s span %d is %.6f..%.6f; expected %.6f..%.6f" %
                             (label, index, g0, g1, e0, e1))
    return got
