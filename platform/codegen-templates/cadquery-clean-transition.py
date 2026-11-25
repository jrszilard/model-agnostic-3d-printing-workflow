"""Clean plate→hook/root blend, distilled from the GPT-5.6 Sol→Terra wiper solution.

Sol: transition geometry carries load; use six smoothstep sections, not stacked pads + final fillet.
Terra: after it looks clean, prove the neighboring base did not widen the frozen mating region.
"""
from pathlib import Path
import math
import sys
import cadquery as cq

ROOT = next(parent for parent in Path(__file__).resolve().parents
            if (parent / "parts" / "_lib").is_dir())
sys.path.insert(0, str(ROOT / "parts" / "_lib"))
from fitcore import assert_fit_regions  # noqa: E402
from probe import assert_single_solid, assert_valid  # noqa: E402


def eased_sections(run0, run1, root_center, root_width, tip_center, tip_width,
                   root_z0, tip_z0, z1):
    sections = []
    for fraction in (0.0, 0.18, 0.42, 0.68, 0.86, 1.0):
        ease = fraction * fraction * (3.0 - 2.0 * fraction)  # zero slope at both joins
        lerp = lambda a, b: a + (b - a) * ease
        sections.append((run0 + (run1 - run0) * fraction,
                         lerp(root_center, tip_center), lerp(root_width, tip_width),
                         lerp(root_z0, tip_z0), z1))
    return sections


def smooth_transition(anchor_xy, run_xy, lateral_xy, sections, isolated_edge_radius=0.0):
    rx, ry = run_xy; lx, ly = lateral_xy
    if abs(math.hypot(rx, ry) - 1) > 1e-6 or abs(math.hypot(lx, ly) - 1) > 1e-6:
        raise ValueError("run/lateral vectors must be unit length")
    if abs(rx * lx + ry * ly) > 1e-6:
        raise ValueError("run/lateral vectors must be perpendicular")
    ax, ay = anchor_xy
    wires = []
    for run, lateral, width, z0, z1 in sections:
        plane = cq.Plane(origin=(ax + rx * run + lx * lateral,
                                 ay + ry * run + ly * lateral, (z0 + z1) / 2),
                         xDir=(lx, ly, 0), normal=(rx, ry, 0))
        wires.append(cq.Workplane(plane).rect(width, z1 - z0).val())
    shape = cq.Solid.makeLoft(wires, ruled=False)
    assert_valid(shape, "transition"); assert_single_solid(shape, "transition")
    transition = cq.Workplane(obj=shape)
    if isolated_edge_radius:
        # Only before fusion, only if both the next boolean and exported mesh pass. Narrow lofts
        # are intentionally left with clean rails rather than a corrupt soft edge.
        transition = transition.edges().fillet(isolated_edge_radius)
        assert_valid(transition, "rounded transition")
        assert_single_solid(transition, "rounded transition")
    return transition


def convex_hull_2d(points):
    """Tangent land outline from real pad/capsule points; avoids horns and boolean V-notches."""
    points = sorted(set(tuple(point) for point in points))
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0: lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0: upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def prove_frozen_mates(final_variants, reference, roi, label="grip"):
    """Hash inputs separately; this proves final neighboring solids leave the mate unchanged."""
    return assert_fit_regions(final_variants, {label: (reference, roi)},
                              volume_tol=1e-5, bbox_tol=1e-5)


def example_transition():
    sections = eased_sections(0, 14, 0, 12, 0, 4, 0, 4, 8)
    return smooth_transition((0, 0), (0, 1), (1, 0), sections)
