import gc
import os
import random
import sys
import unittest

import cadquery as cq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_fast as pf
from probe import ProbeError


def plate():
    """200 x 150 x 5 with 108 through holes: 114 faces, larger than a tile, so it earns tiles."""
    return (cq.Workplane("XY").box(200, 150, 5).faces(">Z").workplane().rarray(10, 10, 12, 9).hole(3.0)).val()


def plain(a, b):
    hit = a.intersect(b)
    return hit.Volume() if hit.Solids() else 0.0


class ProbeFastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = plate()

    def setUp(self):
        pf.reset_stats()

    def test_inside_answers_as_isinside_does_from_one_classifier(self):
        body = plate()
        rnd = random.Random(7)
        points = [(rnd.uniform(-65, 65), rnd.uniform(-50, 50), rnd.uniform(-4, 4)) for _ in range(60)]
        points += [(5.0, 0.0, 0.0), (5.0, 1.5, 0.0), (0.0, 5.0, 2.5), (0.0, 5.0, 2.5 + 1e-7)]   # in a hole, on its wall, on the face
        self.assertFalse(pf.inside(body, (5.0, 0.0, 0.0)))
        self.assertTrue(pf.inside(body, (0.0, 5.0, 0.0)))
        for p in points:
            self.assertEqual(pf.inside(body, p), body.isInside(cq.Vector(*p)), p)
        self.assertEqual(pf.inside(body, cq.Vector(0.0, 0.0, 0.0)), body.isInside(cq.Vector(0.0, 0.0, 0.0)))
        self.assertEqual(pf.STATS["classifiers"], 1)
        self.assertEqual(pf.STATS["points"], len(points) + 3)

    def test_volume_matches_the_whole_solid_boolean_once_tiles_engage(self):
        body = plate()
        rnd = random.Random(11)
        for _ in range(16):
            w = rnd.uniform(0.5, 8.0)
            probe = cq.Solid.makeBox(w, rnd.uniform(0.5, 8.0), rnd.uniform(0.5, 8.0),
                                     cq.Vector(rnd.uniform(-64, 60), rnd.uniform(-48, 42), rnd.uniform(-5, 2)))
            self.assertAlmostEqual(pf.volume(body, probe), plain(body, probe), places=7)
            self.assertAlmostEqual(pf.volume(probe, body), plain(body, probe), places=7)   # either order
        self.assertGreater(pf.STATS["tile_volumes"], 20)
        self.assertGreater(pf.STATS["tiles"], 3)

    def test_a_probe_too_large_for_a_tile_is_measured_against_the_whole_solid(self):
        body = plate()
        small = cq.Solid.makeBox(2, 2, 2, cq.Vector(1, 1, -1))
        for _ in range(4):
            pf.volume(body, small)
        before = pf.STATS["whole_volumes"]
        long_bar = cq.Solid.makeBox(60, 2, 2, cq.Vector(-30, 1, -1))
        self.assertAlmostEqual(pf.volume(body, long_bar), plain(body, long_bar), places=7)
        self.assertEqual(pf.STATS["whole_volumes"], before + 1)

    def test_empty_space_and_a_probe_wholly_in_a_hole_measure_zero(self):
        body = plate()
        outside = cq.Solid.makeBox(2, 2, 2, cq.Vector(150, 0, 0))
        in_hole = cq.Solid.makeCylinder(1.0, 3.0, cq.Vector(5.0, 0.0, -1.5))    # the holes are 3.0 across at (5 + 10 i, 10 j)
        for _ in range(4):
            self.assertEqual(pf.volume(body, outside), 0.0)
            self.assertAlmostEqual(pf.volume(body, in_hole), 0.0, places=9)

    def test_a_small_or_little_used_solid_is_never_tiled(self):
        cube = cq.Solid.makeBox(10, 10, 10)
        probe = cq.Solid.makeBox(2, 2, 2, cq.Vector(9, 9, 9))
        for _ in range(6):
            self.assertAlmostEqual(pf.volume(cube, probe), 1.0, places=9)
        self.assertEqual(pf.STATS["tile_volumes"], 0)

    def test_volumes_batches_probes_that_are_apart_and_measures_the_rest_alone(self):
        body = plate()
        probes = [cq.Solid.makeBox(4, 4, 4, cq.Vector(-58 + 9 * i, -44 + 7 * i, -2)) for i in range(12)]
        overlapping = cq.Solid.makeBox(4, 4, 4, cq.Vector(-56, -42, -2))          # meets the first probe's box
        touching = cq.Solid.makeBox(4, 4, 4, cq.Vector(-58 + 9 + 4, -44 + 7, -2))  # shares a face with the second
        missing = cq.Solid.makeBox(4, 4, 4, cq.Vector(150, 100, 20))              # nowhere near the body
        every = probes + [overlapping, touching, missing]
        got = pf.volumes(body, every)
        want = [plain(body, p) for p in every]
        self.assertEqual(len(got), len(every))
        for g, w in zip(got, want):
            self.assertAlmostEqual(g, w, places=7)
        self.assertEqual(got[-1], 0.0)
        self.assertGreater(sum(1 for g in got if g > 1.0), 8)                      # not a comparison of zeros
        self.assertEqual(pf.STATS["alone"], 2)
        self.assertEqual(pf.STATS["batched"], len(every) - 2)

    def test_volumes_of_one_probe_and_of_none(self):
        body = plate()
        one = cq.Solid.makeBox(4, 4, 4, cq.Vector(0, 0, -2))
        self.assertAlmostEqual(pf.volumes(body, [one])[0], plain(body, one), places=7)
        self.assertEqual(pf.volumes(body, []), [])

    def test_a_moved_copy_has_its_own_cache(self):
        body = plate()
        moved = body.moved(cq.Location(cq.Vector(3.0, 0, 0)))
        point = (5.0, 0.0, 0.0)                                   # in a hole of the original, in plastic of the copy
        self.assertFalse(pf.inside(body, point))
        self.assertTrue(pf.inside(moved, point))
        self.assertEqual(pf.STATS["classifiers"], 2)

    def test_caches_die_with_the_shape(self):
        import weakref
        body = plate()
        probe = cq.Solid.makeBox(2, 2, 2)
        pf.inside(body, (0, 0, 0))
        for _ in range(4):
            pf.volume(body, probe)
        self.assertGreater(pf.STATS["tiles"], 0)
        alive = weakref.ref(body)
        before = len(pf._CLASSIFIERS), len(pf._TILED)
        del body
        gc.collect()
        self.assertIsNone(alive())
        self.assertEqual((len(pf._CLASSIFIERS), len(pf._TILED)), (before[0] - 1, before[1] - 1))

    def test_near_is_an_exact_local_copy(self):
        body = plate()
        region = cq.Solid.makeBox(20, 20, 6, cq.Vector(10, 10, -3))
        local = pf.near(body, region, margin=3.0)
        probe = cq.Solid.makeBox(6, 6, 6, cq.Vector(17, 17, -3))
        self.assertAlmostEqual(plain(local, probe), plain(body, probe), places=7)
        self.assertLess(len(local.Faces()), len(body.Faces()) / 4)

    def test_cut_refuses_a_cutter_that_misses(self):
        block = cq.Solid.makeBox(10, 10, 10)
        hit = cq.Solid.makeCylinder(2, 30, cq.Vector(5, 5, -10))
        miss = cq.Solid.makeCylinder(2, 30, cq.Vector(50, 50, -10))
        self.assertLess(pf.cut(block, hit, "hole").Volume(), 1000.0)
        with self.assertRaises(ProbeError):
            pf.cut(block, miss, "hole")
        self.assertTrue(block.cut(miss).isValid())                 # the plain cut passes every integrity check


if __name__ == "__main__":
    unittest.main()
