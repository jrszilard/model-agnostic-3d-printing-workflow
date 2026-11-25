import os
import sys
import unittest

import cadquery as cq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe import (ProbeError, assert_bbox_contains, assert_clear, assert_contained,
                   assert_face_count, assert_frozen_region, assert_pieces_apart, assert_section_spans,
                   assert_single_solid, assert_volume_additive, intersection_volume,
                   outside_volume, section_spans)


class ProbeCadQueryTests(unittest.TestCase):
    def test_containment_and_clearance_use_real_booleans(self):
        host = cq.Workplane("XY").box(10, 10, 10)
        inside = cq.Workplane("XY").box(2, 2, 2)
        edge = cq.Workplane("XY").box(2, 2, 2).translate((5, 0, 0))
        self.assertAlmostEqual(outside_volume(inside, host), 0.0, places=6)
        self.assertGreater(outside_volume(edge, host), 0.0)
        assert_contained(inside, host)
        with self.assertRaises(ProbeError): assert_contained(edge, host)
        assert_clear(inside.translate((20, 0, 0)), host)
        with self.assertRaises(ProbeError): assert_clear(inside, host)

    def test_solid_bbox_and_face_assertions_catch_dropped_or_split_geometry(self):
        base = cq.Workplane("XY").box(10, 10, 2)
        hook = cq.Workplane("XY").box(2, 2, 8).translate((0, 0, 4))
        full = cq.Compound.makeCompound([base.val(), hook.val()])
        assert_bbox_contains(full, hook, label="hook")
        with self.assertRaises(ProbeError): assert_bbox_contains(base, hook, label="hook")
        with self.assertRaises(ProbeError): assert_single_solid(full)
        assert_face_count(base, expected=6)

    def test_volume_additivity_distinguishes_disjoint_plate_from_overlap(self):
        a = cq.Workplane("XY").box(4, 4, 4)
        b = cq.Workplane("XY").box(4, 4, 4).translate((10, 0, 0))
        plate = cq.Compound.makeCompound([a.val(), b.val()])
        assert_volume_additive([a, b], plate)
        overlap = a.union(cq.Workplane("XY").box(4, 4, 4).translate((2, 0, 0)))
        with self.assertRaises(ProbeError):
            assert_volume_additive([a, cq.Workplane("XY").box(4, 4, 4).translate((2, 0, 0))], overlap)

    def test_pieces_apart_sees_what_a_compound_count_cannot(self):
        a = cq.Solid.makeBox(10, 10, 2)
        for x, fires in ((9.0, True), (10.0, True), (10.5, True), (12.0, False)):
            b = cq.Solid.makeBox(10, 10, 2, cq.Vector(x, 0, 0))
            self.assertEqual(len(cq.Compound.makeCompound([a, b]).Solids()), 2)   # the old check, blind
            if fires:
                with self.assertRaises(ProbeError): assert_pieces_apart([("A", a), ("B", b)], 1.0)
            else:
                self.assertAlmostEqual(assert_pieces_apart([("A", a), ("B", b)], 1.0), 2.0, places=6)
        inside = cq.Solid.makeBox(2, 2, 1, cq.Vector(4, 4, 0.5))
        with self.assertRaises(ProbeError): assert_pieces_apart([a, inside], 1.0)
        split = cq.Compound.makeCompound([cq.Solid.makeBox(1, 1, 1, cq.Vector(30, 0, 0)),
                                          cq.Solid.makeBox(1, 1, 1, cq.Vector(40, 0, 0))])
        with self.assertRaises(ProbeError): assert_pieces_apart([a, split], 1.0)

    def test_frozen_region_ignores_outside_changes_and_blocks_interface_intrusion(self):
        reference = cq.Workplane("XY").box(4, 4, 4)
        roi = cq.Workplane("XY").box(5, 5, 5)
        outside = cq.Workplane("XY").box(2, 2, 2).translate((10, 0, 0))
        actual = cq.Compound.makeCompound([reference.val(), outside.val()])
        assert_frozen_region(actual, reference, roi, bbox_tol=1e-6)
        widened = reference.union(cq.Workplane("XY").box(2, 6, 2))
        with self.assertRaises(ProbeError):
            assert_frozen_region(widened, reference, roi)
        missed = cq.Workplane("XY").box(1, 1, 1).translate((50, 0, 0))
        with self.assertRaises(ProbeError):
            assert_frozen_region(reference, reference, missed)

    def test_section_spans_report_disconnected_material_bands(self):
        left = cq.Workplane("XY").box(2, 4, 4).translate((-4, 0, 0))
        right = cq.Workplane("XY").box(2, 4, 4).translate((4, 0, 0))
        solid = cq.Compound.makeCompound([left.val(), right.val()])
        slab = cq.Workplane("XY").box(20, 1, 1)
        self.assertEqual(section_spans(solid, slab, "x"), [(-5.0, -3.0), (3.0, 5.0)])
        assert_section_spans(solid, slab, [(-5, -3), (3, 5)], axis="x")


if __name__ == "__main__":
    unittest.main()
