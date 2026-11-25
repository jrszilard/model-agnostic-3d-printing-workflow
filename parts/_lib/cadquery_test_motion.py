import math
import os
import sys
import unittest

import cadquery as cq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import motion
from probe import ProbeError


def block_with_hole(lip=False):
    """A 20 cube with a 4.4 hole down its middle; `lip` narrows it to 3.6 between z 8 and 10."""
    block = cq.Solid.makeBox(20, 20, 20, cq.Vector(-10, -10, 0)).cut(cq.Solid.makeCylinder(2.2, 30, cq.Vector(0, 0, -5)))
    if lip:
        ring = cq.Solid.makeCylinder(2.2, 2, cq.Vector(0, 0, 8)).cut(cq.Solid.makeCylinder(1.8, 2, cq.Vector(0, 0, 8)))
        block = block.fuse(ring)
    return block


class MotionTests(unittest.TestCase):
    def test_a_pin_slides_home_with_its_gap_measured(self):
        pin = cq.Solid.makeCylinder(2.0, 18, cq.Vector(0, 0, 22))                 # starts above the block
        path = motion.slide((0, 0, -20), 10)
        self.assertEqual(len(path), 11)
        self.assertAlmostEqual(motion.sweep(pin, block_with_hole(), path, clearance=0.1, label="pin"), 0.2, places=3)

    def test_a_lip_in_the_way_stops_the_sweep_and_says_where(self):
        pin = cq.Solid.makeCylinder(2.0, 18, cq.Vector(0, 0, 22))
        final = pin.moved(motion.slide((0, 0, -20), 10)[-1])
        plain = block_with_hole()
        self.assertLess(plain.intersect(final).Volume() if plain.intersect(final).Solids() else 0.0, 1e-6)
        with self.assertRaises(ProbeError) as caught:
            motion.sweep(pin, block_with_hole(lip=True), motion.slide((0, 0, -20), 10), label="pin")
        self.assertIn("step 7 of 10", str(caught.exception))    # tip at z 8 is still clear at step 6 (z 10), cut at 7

    def test_a_sweep_that_comes_too_close_is_refused(self):
        pin = cq.Solid.makeCylinder(2.0, 18, cq.Vector(0.15, 0, 22))                # 0.05 off one side of the hole
        with self.assertRaises(ProbeError) as caught:
            motion.sweep(pin, block_with_hole(), motion.slide((0, 0, -20), 5), clearance=0.1, label="pin")
        self.assertIn("comes within 0.05", str(caught.exception))

    def test_far_from_everything_the_gap_is_at_least_the_margin(self):
        pin = cq.Solid.makeCylinder(2.0, 5, cq.Vector(100, 100, 100))
        self.assertEqual(motion.sweep(pin, block_with_hole(), motion.slide((5, 0, 0), 2), clearance=0.5), 2.5)

    def test_a_ledge_stops_a_falling_box_and_bare_walls_do_not(self):
        box = cq.Solid.makeBox(10, 10, 6, cq.Vector(-5, -5, 2))
        walls = cq.Solid.makeBox(14, 14, 12, cq.Vector(-7, -7, -4)).cut(cq.Solid.makeBox(10.1, 10.1, 30, cq.Vector(-5.05, -5.05, -10)))
        ledge = walls.fuse(cq.Solid.makeBox(3, 14, 1, cq.Vector(-7, -7, -1)))        # a catch 2 under the box's bottom
        stopped = motion.must_stop(box, ledge, (0, 0, -1), travel=8.0, step=0.25, label="box")
        self.assertAlmostEqual(stopped, 2.0, delta=0.25)
        with self.assertRaises(ProbeError) as caught:
            motion.must_stop(box, walls, (0, 0, -1), travel=8.0, label="box")
        self.assertIn("only friction holds it", str(caught.exception))

    def test_a_part_already_cut_into_at_rest_is_refused(self):
        box = cq.Solid.makeBox(10, 10, 6, cq.Vector(-5, -5, 2))
        with self.assertRaises(ProbeError):
            motion.must_stop(box, cq.Solid.makeBox(4, 4, 4, cq.Vector(-2, -2, 3)), (0, 0, -1), travel=2.0)

    def test_a_shoe_turns_as_far_as_its_room_lets_it(self):
        shoe = cq.Solid.makeBox(20, 10, 5, cq.Vector(-10, -5, 0))
        channel = cq.Solid.makeBox(60, 30, 5, cq.Vector(-30, -15, 0)).cut(cq.Solid.makeBox(60, 10.4, 5, cq.Vector(-30, -5.2, 0)))
        # 10 cos t + 20 sin t = 10.4  ->  t = 1.15 degrees
        exact = math.degrees(2 * math.atan((20 - math.sqrt(400 + 100 - 10.4 ** 2)) / (10 + 10.4)))
        self.assertAlmostEqual(exact, 1.15, delta=0.01)
        back, forward = motion.free_turn(shoe, channel, (0, 0, 0), (0, 0, 1), limit=3.0, step=0.05, label="shoe")
        self.assertAlmostEqual(forward, exact, delta=0.06)
        self.assertAlmostEqual(back, exact, delta=0.06)
        self.assertLessEqual(forward, exact + 1e-9)                                # never more than it can really turn
        tight = cq.Solid.makeBox(60, 30, 5, cq.Vector(-30, -15, 0)).cut(cq.Solid.makeBox(60, 10.05, 5, cq.Vector(-30, -5.025, 0)))
        self.assertLess(motion.free_turn(shoe, tight, (0, 0, 0), (0, 0, 1), limit=3.0, step=0.05)[1], 0.2)

    def test_a_turn_is_about_the_pivot_given_not_the_origin(self):
        far = cq.Solid.makeBox(20, 10, 5, cq.Vector(90, 45, 30))                    # its centre at (100, 50, 32.5)
        centre = far.Center()
        for location in motion.turn((100.0, 50.0, 32.5), (0, 0, 1), 90.0, 3)[1:]:
            moved = far.moved(location)
            self.assertAlmostEqual((moved.Center() - centre).Length, 0.0, places=9)
        quarter = far.moved(motion.about((100.0, 50.0, 32.5), (0, 0, 1), 90.0)).BoundingBox()
        self.assertAlmostEqual(quarter.xlen, 10.0, places=6)
        self.assertAlmostEqual(quarter.ylen, 20.0, places=6)
        # and free_turn uses it: the same shoe and channel as below, 100 away from the origin
        shoe = cq.Solid.makeBox(20, 10, 5, cq.Vector(90, 95, 0))
        channel = cq.Solid.makeBox(60, 30, 5, cq.Vector(70, 85, 0)).cut(cq.Solid.makeBox(60, 10.4, 5, cq.Vector(70, 94.8, 0)))
        back, forward = motion.free_turn(shoe, channel, (100.0, 100.0, 0.0), (0, 0, 1), limit=3.0, step=0.05)
        self.assertAlmostEqual(forward, 1.15, delta=0.06)
        self.assertAlmostEqual(back, 1.15, delta=0.06)

    def test_room_to_shift_lets_it_turn_further(self):
        shoe = cq.Solid.makeBox(20, 10, 5, cq.Vector(-10, -5, 0))
        # a wall on one side only at y 5.2, and a stop block the far corner would meet unless the shoe shifts away
        wall = cq.Solid.makeBox(60, 5, 5, cq.Vector(-30, 5.2, 0))
        fixed_only = motion.free_turn(shoe, wall, (0, 0, 0), (0, 0, 1), limit=3.0, step=0.1)[1]
        with_shift = motion.free_turn(shoe, wall, (0, 0, 0), (0, 0, 1), limit=3.0, step=0.1,
                                      shifts=((0, 0, 0), (0, -0.5, 0)))[1]
        self.assertLess(fixed_only, 1.5)
        self.assertGreater(with_shift, fixed_only)


if __name__ == "__main__":
    unittest.main()
