"""Exact, faster forms of the probes a generator's checks run thousands of times.

Measured on the touge road's S module (2026-11-11): its checks are 4,723 small booleans and 1,036 point tests against a
1,645-face body. With `inside` and `volume` below they print the same 22 lines in 79 s instead of 132 s; 26 magnet
probes through `volumes` take 0.19 s instead of 3.4 s.

What keeps each one exact:

- `inside` classifies a point against the WHOLE solid with the classifier `Solid.isInside` builds, but builds it once
  per solid instead of once per point.
- `volume` cuts a big, reused solid into overlapping tiles. A probe is measured against a tile only when the probe's
  box sits inside that tile's box with GUARD to spare, so `body ∩ probe` and `tile ∩ probe` are the same set and no face
  of the probe lies on a tile's cut. Anything else is measured against the whole solid.
- `volumes` is one boolean against a compound of probes whose boxes are apart. A probe whose box meets another's is
  measured alone, and a result solid that cannot be given to exactly one probe is an error, never a guess.

Caches hang off the shape object by weak reference: they die with the shape, so a rebuilt body starts clean, and a
moved copy (another location) is another key. CadQuery is imported lazily; `import probe_fast` stays dependency-free.
"""
from __future__ import annotations

import math
import weakref

from probe import ProbeError, bbox, shape

CORE = 24.0          # a tile's own cell, mm
MARGIN = 12.0        # each tile reaches this far past its cell on every side
GUARD = 1.0          # a probe must stay this far inside its tile's box
BIG_FACES = 100      # smaller solids are not worth tiling
USES_BEFORE_TILING = 3
BOX_GAP = 0.05       # probes batched together have boxes at least this far apart

_CLASSIFIERS = weakref.WeakKeyDictionary()
_TILED = weakref.WeakKeyDictionary()
STATS = {"classifiers": 0, "points": 0, "tiles": 0, "tile_volumes": 0, "whole_volumes": 0, "batched": 0, "alone": 0}


def reset_stats():
    for key in STATS:
        STATS[key] = 0


def _vol(obj):
    if obj is None:
        return 0.0
    return float(sum(s.Volume() for s in obj.Solids())) if obj.Solids() else 0.0


def inside(solid, point, tol=1.0e-6):
    """`solid.isInside(point, tol)`, with the solid's classifier built once and reused."""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN
    solid = shape(solid)
    classifier = _CLASSIFIERS.get(solid)
    if classifier is None:
        classifier = _CLASSIFIERS[solid] = BRepClass3d_SolidClassifier(solid.wrapped)
        STATS["classifiers"] += 1
    to_tuple = getattr(point, "toTuple", None)
    x, y, z = to_tuple() if callable(to_tuple) else point
    classifier.Perform(gp_Pnt(float(x), float(y), float(z)), tol)
    STATS["points"] += 1
    return classifier.State() == TopAbs_IN or classifier.IsOnAFace()


class _Tiles:
    def __init__(self, solid):
        self.solid = weakref.ref(solid)      # never a strong reference: the cache must die with the shape
        self.box = solid.BoundingBox()
        self.cache = {}

    def worth_it(self):
        bb = self.box
        return max(bb.xlen, bb.ylen, bb.zlen) > 2.5 * (CORE + 2 * MARGIN)

    def fits(self, pb):
        limit = 2 * (MARGIN - GUARD)
        return pb.xlen <= limit and pb.ylen <= limit and pb.zlen <= limit

    def tile(self, pb):
        import cadquery as cq
        bb = self.box
        centre = ((pb.xmin + pb.xmax) / 2, (pb.ymin + pb.ymax) / 2, (pb.zmin + pb.zmax) / 2)
        key = tuple(math.floor((c - lo) / CORE) for c, lo in zip(centre, (bb.xmin, bb.ymin, bb.zmin)))
        if key not in self.cache:
            side = CORE + 2 * MARGIN
            corner = cq.Vector(*(lo + k * CORE - MARGIN for k, lo in zip(key, (bb.xmin, bb.ymin, bb.zmin))))
            self.cache[key] = self.solid().intersect(cq.Solid.makeBox(side, side, side, corner))
            STATS["tiles"] += 1
        return self.cache[key]


def _tiles_for(solid):
    """The solid's tile cache once it has earned one (big, reused, larger than a tile), else None."""
    entry = _TILED.get(solid)
    if entry is None:
        entry = _TILED[solid] = [len(solid.Faces()), 0, None]
    entry[1] += 1
    if entry[0] < BIG_FACES or entry[1] < USES_BEFORE_TILING:
        return None
    if entry[2] is None:
        tiles = _Tiles(solid)
        entry[2] = tiles if tiles.worth_it() else False
    return entry[2] or None


def volume(a, b):
    """Intersection volume of `a` and `b`: what `a.intersect(b)` holds, 0.0 when they do not meet."""
    a, b = shape(a), shape(b)
    for big, small in ((a, b), (b, a)):
        tiles = _tiles_for(big)
        if tiles is not None:
            pb = small.BoundingBox()
            if tiles.fits(pb):
                STATS["tile_volumes"] += 1
                tile = tiles.tile(pb)
                return _vol(tile.intersect(small)) if tile.Solids() else 0.0    # an empty tile: no body there
    STATS["whole_volumes"] += 1
    return _vol(a.intersect(b))


def _boxes_apart(p, q, gap):
    return (p.xmin - q.xmax > gap or q.xmin - p.xmax > gap or p.ymin - q.ymax > gap or q.ymin - p.ymax > gap
            or p.zmin - q.zmax > gap or q.zmin - p.zmax > gap)


def _box_holds(outer, inner, tol=BOX_GAP / 4):
    return (outer.xmin - tol <= inner.xmin and inner.xmax <= outer.xmax + tol
            and outer.ymin - tol <= inner.ymin and inner.ymax <= outer.ymax + tol
            and outer.zmin - tol <= inner.zmin and inner.zmax <= outer.zmax + tol)


def volumes(body, probes, label="probes"):
    """Intersection volume of `body` with each probe, in order, from as few booleans as their boxes allow."""
    import cadquery as cq
    body = shape(body)
    items = [shape(p) for p in probes]
    boxes = [p.BoundingBox() for p in items]
    out = [0.0] * len(items)
    batch = []
    for i, box in enumerate(boxes):
        if all(_boxes_apart(box, boxes[j], BOX_GAP) for j in batch):
            batch.append(i)
        else:
            out[i] = volume(body, items[i])
            STATS["alone"] += 1
    if len(batch) == 1:
        out[batch[0]] = volume(body, items[batch[0]])
        STATS["alone"] += 1
    elif batch:
        hit = body.intersect(cq.Compound.makeCompound([items[i] for i in batch]))
        for piece in hit.Solids():
            owners = [i for i in batch if _box_holds(boxes[i], piece.BoundingBox())]
            if len(owners) != 1:
                raise ProbeError("%s: a piece of the batched intersection belongs to %d probes; measure these one at "
                                 "a time" % (label, len(owners)))
            out[owners[0]] += float(piece.Volume())
        STATS["batched"] += len(batch)
    return out


def near(body, region, margin=2.0):
    """`body` cut to the box round `region` (a shape or anything with a BoundingBox) grown by `margin`: an exact local
    copy for a run of probes in one neighbourhood. Probes must stay inside that box."""
    import cadquery as cq
    rb = bbox(region)
    corner = cq.Vector(rb.xmin - margin, rb.ymin - margin, rb.zmin - margin)
    return shape(body).intersect(cq.Solid.makeBox(rb.xlen + 2 * margin, rb.ylen + 2 * margin, rb.zlen + 2 * margin,
                                                  corner))


def cut(body, tool, label="cut", at_least=1e-3):
    """`body.cut(tool)`, refused when the tool removed less than `at_least` mm3.

    A cutter that misses leaves a valid single solid with the feature absent, and nothing downstream notices: the
    wiper adaptor lost a hook this way and passed every integrity gate. One line per cut makes the miss a failure."""
    body = shape(body)
    result = body.cut(shape(tool))
    removed = float(body.Volume()) - _vol(result)
    if removed < at_least:
        raise ProbeError("%s removed %.6f mm3 (under %.6f): the cutter misses the body" % (label, removed, at_least))
    return result
