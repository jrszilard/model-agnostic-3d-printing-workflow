#!/usr/bin/env python3
"""A mechanism's checks, written once from the shared library: copy the pattern, not the numbers.

The example is a small box hung under a deck between two walls, held by a catch under each end. It shows the five
habits that would have saved a print each (docs: knowledge base, shared/stack-references/fdm-design-techniques):

1. `mech.require(...)` states each requirement with ITS limit before any geometry is trusted (the mechanism sheet).
2. `probe_fast.cut(...)` refuses a cutter that misses; a missed cut is otherwise a valid solid with the feature gone.
3. `motion.sweep(...)` takes the part in along the way a hand takes it, not only to where it ends up.
4. `motion.must_stop(...)` lets it fall: something must stop it, or only friction holds it.
5. `motion.free_turn(...)` rolls it through its room; what reaches out from it moves reach x tan(angle).

Sections are module-level functions that take their solids as arguments, so `checks.run` can give each its own
process. The part's negative controls go beside it in qa/negatives.py (platform/pipeline/verify/negatives.py), one
broken value per case with the refusal it must produce.
"""
import math
from pathlib import Path
import sys

import cadquery as cq

ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "parts" / "_lib").is_dir())
sys.path.insert(0, str(ROOT / "parts" / "_lib"))
import mech            # noqa: E402
import motion          # noqa: E402
import probe_fast      # noqa: E402
from checks import run  # noqa: E402

BOX = (20.0, 16.0, 8.0)                 # the bought part: measured, not chosen
BOX_G = 60.0
SIDE_GAP, DROP, LIP, WALL = 0.2, 0.3, 1.0, 2.0
ARM = 20.0                              # something on the box reaches this far out and must stay put


def box():
    return cq.Solid.makeBox(*BOX, cq.Vector(-BOX[0] / 2, -BOX[1] / 2, -BOX[2]))


def holder(catch=True):
    """The deck (z 0 to 3), a wall past each end of the box, and a lip under each end `DROP` below it."""
    half = BOX[0] / 2 + SIDE_GAP
    body = cq.Solid.makeBox(2 * (half + WALL) + 10, BOX[1] + 14, 3.0, cq.Vector(-(half + WALL) - 5, -BOX[1] / 2 - 7, 0))
    deep = BOX[2] + DROP + 1.2
    for sign in (-1, 1):
        x0 = half if sign > 0 else -half - WALL
        body = body.fuse(cq.Solid.makeBox(WALL, BOX[1], deep, cq.Vector(x0, -BOX[1] / 2, -deep)))
        if catch:
            lx = half - LIP if sign > 0 else -half
            body = body.fuse(cq.Solid.makeBox(LIP, BOX[1], 1.2, cq.Vector(lx, -BOX[1] / 2, -deep)))
    # a wire hole through the deck: `cut` refuses if the cutter is not where the deck is
    return probe_fast.cut(body, cq.Solid.makeCylinder(1.5, 10.0, cq.Vector(0, BOX[1] / 2 + 4, -2)), "wire hole")


def requirements():
    """The mechanism sheet: each line is a requirement and the limit it is held to."""
    return [
        mech.require("the box drops before its catch takes it", DROP, at_most=0.5),
        mech.require("each catch reaches under the box", LIP - SIDE_GAP, at_least=0.6),
        mech.require("the box's weight", mech.weight(BOX_G), at_most=2.0, unit="N"),
    ]


def fit_checks(body, part):
    """The way in: slid in from the open side, carried between the deck and the catches, the box never comes within
    0.1 of the holder. (Placed against the deck it would pass a final-pose check and scrape all the way in.)"""
    carried = part.moved(cq.Location(cq.Vector(0.0, 0.0, -DROP / 2)))
    gap = motion.sweep(carried, body, motion.slide((0.0, -30.0, 0.0), 12, start=1.0, end=0.0), clearance=0.1,
                       label="box")
    return ["slides in from the open side, never nearer than %.2f" % gap]


def hold_checks(body, part):
    """Gravity and play: it must meet a catch, and what its room lets it roll must not move the arm's end too far."""
    fall = motion.must_stop(part, body, (0.0, 0.0, -1.0), travel=5.0, step=0.1, label="box")
    back, forward = motion.free_turn(part, body, (0.0, 0.0, -BOX[2] / 2), (0.0, 1.0, 0.0), limit=6.0, step=0.25,
                                     shifts=((0, 0, 0), (0, 0, -DROP / 2), (0, 0, -DROP)), label="box")
    swing = ARM * math.tan(math.radians(max(back, forward)))
    return [mech.require("it falls onto its catches after", fall, at_most=0.5),
            mech.require("rolled through its room, the arm's end moves", swing, at_most=1.0)]


def all_checks(body, part, jobs=None):
    return requirements() + run([("fit", fit_checks, (body, part)), ("hold", hold_checks, (body, part))], jobs=jobs)


if __name__ == "__main__":
    for line in all_checks(holder(), box()):
        print(line)
