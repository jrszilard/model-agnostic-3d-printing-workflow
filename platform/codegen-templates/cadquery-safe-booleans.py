"""Boolean patterns that fail silently when expressed as convenient wire chaining."""
import cadquery as cq

from pathlib import Path
import sys
ROOT = next(parent for parent in Path(__file__).resolve().parents
            if (parent / "parts" / "_lib").is_dir())
sys.path.insert(0, str(ROOT / "parts" / "_lib"))
from probe import assert_pieces_apart, assert_single_solid  # noqa: E402

OVERRUN = 0.05


def overlapping_pads(centres, radii, height):
    """DO: one solid per circle, explicit unions.

    DON'T: Workplane.moveTo(...).circle(...).moveTo(...).circle(...).extrude(height).
    Nested/overlapping wires use even-odd fill and can delete the overlap as a void.
    """
    if len(centres) != len(radii) or not centres:
        raise ValueError("centres/radii must be non-empty and the same length")
    pads = [cq.Workplane("XY").moveTo(x, y).circle(radius).extrude(height)
            for (x, y), radius in zip(centres, radii)]
    result = pads[0]
    for pad in pads[1:]:
        result = result.union(pad)
    return result


def explicit_boss(host, x, y, face_z, radius, height):
    """Volumetric overlap beats a coplanar kiss after a previous cut."""
    boss = (cq.Workplane("XY").workplane(offset=face_z - OVERRUN)
            .center(x, y).circle(radius).extrude(height + OVERRUN))
    result = host.union(boss)
    assert_single_solid(result, "host + boss")
    return result


def cutter_compound(cutters):
    """Cut-only pieces need no sequential fuse (95 s -> 0.3 s on an 18-sector socket)."""
    shapes = [c.val() if hasattr(c, "val") else c for c in cutters]
    return cq.Compound.makeCompound(shapes)


def one_closed_tangent_profile(points, height):
    """Author tangent bar/curl boundaries as one wire; do not union across line contact."""
    return cq.Workplane("XY").polyline(points).close().extrude(height)


def assert_disjoint_plate(parts, min_gap=1.0):
    """Every piece one solid and every two at least `min_gap` apart, measured piece to piece.

    DON'T: `len(cq.Compound.makeCompound(parts).Solids()) == len(parts)`, or the compound's volume.
    A compound never merges its solids, so both hold while pieces touch or overlap, and the slicer
    prints them as one block (TR3S i4's lettered tabs). `parts` may be (name, shape) pairs.
    """
    return assert_pieces_apart(parts, min_gap, label="plate")
