"""Explicit-datum placement: do not let the current solid choose the next feature's frame."""
from pathlib import Path
import sys
import cadquery as cq

ROOT = next(parent for parent in Path(__file__).resolve().parents
            if (parent / "parts" / "_lib").is_dir())
sys.path.insert(0, str(ROOT / "parts" / "_lib"))
from probe import assert_bbox_contains, assert_clear, assert_single_solid  # noqa: E402


def boss_at_z(x, y, host_top_z, diameter, height):
    # GOOD: boss two stays on the plate even after boss one becomes the highest face.
    return (cq.Workplane("XY").workplane(offset=host_top_z - 0.05)
            .center(x, y).circle(diameter / 2).extrude(height + 0.05))


def two_boss_plate():
    plate_z = 4.0
    plate = cq.Workplane("XY").box(50, 30, plate_z, centered=(True, True, False))
    b1 = boss_at_z(-12, 0, plate_z, 8, 5)
    b2 = boss_at_z(+12, 0, plate_z, 8, 5)
    result = plate.union(b1).union(b2)
    assert_single_solid(result, "two-boss plate")
    assert_bbox_contains(result, b1, label="boss one")
    assert_bbox_contains(result, b2, label="boss two")
    return result


# BAD (documented, not executed):
#   plate.faces(">Z").workplane().center(-12, 0).circle(4).extrude(5)
#        .faces(">Z").workplane().center(+24, 0).circle(4).extrude(5)
# The second faces(">Z") selects boss one's top; boss two floats 5 mm above the plate.


def through_feature_probe(part, x, y, diameter, z0, height, label="bore"):
    """A filled or roofed hole is manifold. Probe the actual final part."""
    probe = (cq.Workplane("XY").workplane(offset=z0).center(x, y)
             .circle(diameter / 2 - 0.1).extrude(height))
    assert_clear(probe, part, tol=1e-6, label=label)
