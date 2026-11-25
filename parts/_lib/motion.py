"""Move a part the way a hand, gravity or its own play moves it, and check it at every step.

A check that places a part only where it ends up passes parts that cannot get there, cannot be taken out, fall out, or
rock off what they should hold. Each function here is one of those, with the print that proved the need:

    sweep       TM1's magnets jammed 1 mm short on a channel's lip while every final-pose check passed (2026-10)
    must_stop   TR8's battery box, held by crush ribs only, fell out upside down; the lamp's lens repeated it
    free_turn   TR11 i2's shoe rolled 3.5 degrees in 0.35 of room and dropped its arm's pad off a 2 mm fin

Exactness: every pose is tested with the kernel's own boolean and distance. The fixed body is first cut to the box the
moving part sweeps through, grown by a margin, which changes nothing inside that box; a reported gap larger than the
margin only means "at least the margin". Poses are samples: choose the step from the smallest feature in the way.
CadQuery is imported lazily.
"""
from __future__ import annotations

import math

from probe import ProbeError, shape

TOUCH = 1e-4          # mm3: under this two solids only touch


def slide(vector, steps, start=0.0, end=1.0):
    """Locations from `start` x vector to `end` x vector, both included."""
    import cadquery as cq
    vx, vy, vz = vector
    return [cq.Location(cq.Vector(vx * f, vy * f, vz * f))
            for f in (start + (end - start) * k / steps for k in range(steps + 1))]


def about(pivot, axis, degrees):
    """The location that turns a shape `degrees` about the line through `pivot` along `axis`.

    `cq.Location(point, axis, angle)` is NOT this: it turns about the axis through the ORIGIN and then moves by
    `point`. The first version of this module used it and passed its tests only because they pivoted at the origin."""
    import cadquery as cq
    px, py, pz = pivot
    return (cq.Location(cq.Vector(px, py, pz)) * cq.Location(cq.Vector(0, 0, 0), cq.Vector(*axis), degrees)
            * cq.Location(cq.Vector(-px, -py, -pz)))


def turn(pivot, axis, degrees, steps):
    """Locations turning from 0 to `degrees` about the line through `pivot` along `axis`."""
    return [about(pivot, axis, degrees * k / steps) for k in range(steps + 1)]


def _local(fixed, poses, margin):
    """The fixed body cut to the box every pose stays inside, grown by `margin`."""
    import cadquery as cq
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    for pose in poses:
        bb = pose.BoundingBox()
        lo = [min(a, b) for a, b in zip(lo, (bb.xmin, bb.ymin, bb.zmin))]
        hi = [max(a, b) for a, b in zip(hi, (bb.xmax, bb.ymax, bb.zmax))]
    corner = cq.Vector(*(a - margin for a in lo))
    box = cq.Solid.makeBox(*(b - a + 2 * margin for a, b in zip(lo, hi)), corner)
    return shape(fixed).intersect(box)


def _meets(local, pose):
    hit = local.intersect(pose) if local.Solids() else None
    return float(hit.Volume()) if hit is not None and hit.Solids() else 0.0


def sweep(part, fixed, locations, clearance=0.0, label="part", margin=None):
    """`part` at each location must not cut into `fixed`, and must stay `clearance` off it when that is over zero.

    Returns the least gap seen (0.0 when clearance is 0 and it only ever touches). Raises ProbeError naming the first
    location that fails, so an insertion path that jams says where."""
    part = shape(part)
    poses = [part.moved(loc) for loc in locations]
    margin = max(2.0, clearance + 2.0) if margin is None else margin
    local = _local(fixed, poses, margin)
    least = math.inf
    for index, pose in enumerate(poses):
        amount = _meets(local, pose)
        if amount > TOUCH:
            raise ProbeError("%s cuts %.4f mm3 into what it passes at step %d of %d" % (label, amount, index,
                                                                                         len(poses) - 1))
        if clearance > 0.0:
            gap = min(float(pose.distance(local)), margin) if local.Solids() else margin
            if gap < clearance:
                raise ProbeError("%s comes within %.3f at step %d of %d (needs %.3f)" % (label, gap, index,
                                                                                          len(poses) - 1, clearance))
            least = min(least, gap)
    return 0.0 if least is math.inf else least


def must_stop(part, fixed, direction, travel, step=0.25, label="part"):
    """Moved along `direction` (gravity, or the way a knock would take it), `part` must run into `fixed` within
    `travel`. Returns how far it got. Raises when it is already cut into at rest, or when nothing stops it: a part
    that nothing stops is held by friction only."""
    part = shape(part)
    length = math.sqrt(sum(c * c for c in direction))
    unit = tuple(c / length for c in direction)
    steps = max(1, int(math.ceil(travel / step)))
    locations = slide(tuple(c * travel for c in unit), steps)
    poses = [part.moved(loc) for loc in locations]
    local = _local(fixed, poses, 2.0)
    if _meets(local, poses[0]) > TOUCH:
        raise ProbeError("%s already cuts into its holder where it rests" % label)
    for index, pose in enumerate(poses[1:], start=1):
        if _meets(local, pose) > TOUCH:
            return travel * (index - 1) / steps
    raise ProbeError("%s moves %.2f and meets nothing: only friction holds it" % (label, travel))


def free_turn(part, fixed, pivot, axis, limit, step=0.1, shifts=((0.0, 0.0, 0.0),), label="part"):
    """How far `part` can turn each way about the line through `pivot` along `axis` before it must cut into `fixed`.

    `shifts` are the translations its room allows. Sample the room's MIDDLE as well as its corners (a part hard
    against one side cannot turn at all): an angle counts as reachable when ANY shift gives a pose that cuts into
    nothing, because a loose part finds that pose. Returns (back, forward) in
    degrees, each the last reachable sample up to `limit`. Multiply by what reaches out from the part: an arm's far
    end moves reach x tan(angle)."""
    import cadquery as cq
    part = shape(part)
    steps = max(1, int(round(limit / step)))
    out = []
    for sign in (-1.0, 1.0):
        candidates = []
        for k in range(1, steps + 1):
            turned = part.moved(about(pivot, axis, sign * limit * k / steps))
            candidates.append([turned.moved(cq.Location(cq.Vector(*s))) for s in shifts])
        local = _local(fixed, [p for row in candidates for p in row] + [part], 2.0)
        if _meets(local, part) > TOUCH:
            raise ProbeError("%s already cuts into its guide before it turns" % label)
        reached = 0.0
        for k, row in enumerate(candidates, start=1):
            if not any(_meets(local, pose) <= TOUCH for pose in row):
                break
            reached = limit * k / steps
        out.append(reached)
    return tuple(out)
