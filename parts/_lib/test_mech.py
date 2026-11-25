import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mech


class MechTests(unittest.TestCase):
    """Each number is one this studio printed, so a changed formula shows as a changed print."""

    def cover_load(self, section_area):
        magnets = 13 * math.pi / 4 * 12.7 ** 2 * 3.175 * 7.5e-3          # grams of N52 in a lane
        self.assertAlmostEqual(magnets, 39.2, delta=0.1)
        return mech.weight(magnets) / 200.0 + section_area * 1.27e-3 * mech.G

    def test_the_touge_road_cover_sags_as_it_did(self):
        flat = mech.beam_sag(self.cover_load(17 * 1.6), 200.0, 1800.0, mech.rect_i(17.0, 1.6))
        self.assertAlmostEqual(mech.rect_i(17.0, 1.6), 5.80, places=2)
        self.assertAlmostEqual(flat, 4.5, delta=0.1)                      # Justin: "can bend out of the slot"
        ribbed = self.cover_load(17 * 1.6 + 2 * 2 * 3)
        self.assertAlmostEqual(mech.beam_sag(ribbed, 200.0, 1800.0, 58.85, "propped"), 0.19, delta=0.01)   # v5
        self.assertAlmostEqual(mech.beam_sag(ribbed, 200.0, 1800.0, 58.85, "fixed"), 0.09, delta=0.01)     # screwed
        self.assertGreater(mech.beam_sag(ribbed, 200.0, 1800.0, 58.85, "pinned"), 0.25)                    # its limit

    def test_supports_rank_as_beam_theory_says(self):
        sag = {ends: mech.beam_sag(1e-3, 100.0, 2000.0, 10.0, ends) for ends in ("fixed", "propped", "pinned", "cantilever")}
        self.assertLess(sag["fixed"], sag["propped"]); self.assertLess(sag["propped"], sag["pinned"])
        self.assertAlmostEqual(sag["pinned"] / sag["fixed"], 5.0, places=9)
        self.assertAlmostEqual(sag["cantilever"] / sag["pinned"], 9.6, places=9)
        self.assertAlmostEqual(mech.beam_sag_point(1.0, 100.0, 2000.0, 10.0), 100.0 ** 3 / (48 * 2000 * 10), places=12)

    def test_the_slider_rocks_five_at_its_arm(self):
        self.assertAlmostEqual(mech.rock_angle(0.35, 5.7), 3.5, delta=0.02)     # TR11 i2: "up to 3.5 degrees"
        self.assertAlmostEqual(mech.rock_drop(0.35, 5.7, 80.6), 4.95, delta=0.01)
        spread = mech.corners(mech.rock_drop, room=(0.25, 0.35, 0.50), width=(5.6, 5.7, 5.8), reach=(80.6, 80.6, 80.6))
        self.assertAlmostEqual(spread["nominal"], 4.95, delta=0.01)
        self.assertAlmostEqual(spread["low"], 3.47, delta=0.01)
        self.assertAlmostEqual(spread["high"], 7.20, delta=0.01)
        with self.assertRaises(mech.Refused):                                    # i2's 2.0 of engagement
            mech.require("the pad's drop at the fin", spread["high"], at_most=2.0)

    def test_a_hooked_shelf_tips_nine_times_its_play(self):
        self.assertAlmostEqual(mech.hook_tip(0.3, 146.0, 16.0), 2.74, delta=0.01)

    def test_the_far_handle_jams(self):
        self.assertAlmostEqual(mech.jam_ratio(0.3, 61.0, 35.0), 1.05, delta=0.01)
        self.assertLess(mech.jam_ratio(0.3, 20.0, 35.0), 1.0)

    def test_a_catch_face_multiplies_the_spring(self):
        self.assertAlmostEqual(mech.mating_force(1.0, 0.5, 45.0), 3.0, places=9)
        self.assertEqual(mech.mating_force(1.0, 0.5, 64.0), math.inf)
        mu = 0.3                                                                 # the slider coupon's own form
        self.assertAlmostEqual(mech.mating_force(2.0, mu, 45.0), 2.0 * math.tan(math.radians(45.0) + math.atan(mu)), places=9)

    def test_a_snap_arm_strain_travel_and_force(self):
        strain = mech.cantilever_strain(1.0, 20.0, 2.0)
        self.assertAlmostEqual(strain, 0.0075, places=9)
        self.assertAlmostEqual(mech.cantilever_travel(strain, 20.0, 2.0), 1.0, places=9)
        self.assertAlmostEqual(mech.cantilever_travel(0.01, 20.0, 2.0, tapered=True) /
                               mech.cantilever_travel(0.01, 20.0, 2.0), 1.09 * 1.5, places=9)   # "over 60 % more"
        self.assertAlmostEqual(mech.cantilever_force(1.0, 20.0, 12.0, 2.0, 1800.0), 1800 * 12 * 8 / (4 * 8000), places=9)
        self.assertLess(mech.STRAIN_LIMIT["PETG"]["across_layers"], 0.0109)      # TR8: 1.09 % went loose
        self.assertGreater(mech.STRAIN_LIMIT["PETG"]["across_layers"], 0.006)    # and 0.6 % held

    def test_a_long_strip_bows_before_it_slides(self):
        self.assertAlmostEqual(mech.euler_load(2000.0, 1.0, 100.0), math.pi ** 2 * 0.2, places=9)
        self.assertGreater(mech.euler_load(2000.0, 1.0, 100.0, "fixed"), mech.euler_load(2000.0, 1.0, 100.0))
        # the road's PLA line strip, a T 2.2 tall (flange 7.14 x 1.0, stem 2.14 x 1.2), pushed in over 240:
        # "it is like pushing rope" (2026-10-12). One to two newtons, whichever modulus is believed.
        a1, y1, a2, y2 = 7.14 * 1.0, 0.5, 2.14 * 1.2, 1.6
        yc = (a1 * y1 + a2 * y2) / (a1 + a2)
        i_t = mech.rect_i(7.14, 1.0) + a1 * (yc - y1) ** 2 + mech.rect_i(2.14, 1.2) + a2 * (y2 - yc) ** 2
        self.assertAlmostEqual(i_t, 3.19, delta=0.01)
        self.assertAlmostEqual(mech.euler_load(2300.0, i_t, 240.0), 1.26, delta=0.02)
        self.assertLess(mech.euler_load(3500.0, i_t, 240.0), 2.0)

    def test_friction_is_not_a_hold(self):
        self.assertFalse(mech.friction_holds(mech.weight(60.0), normal=1.0, mu=0.3))   # the 60 g battery box
        self.assertTrue(mech.friction_holds(mech.weight(60.0), normal=10.0, mu=0.3))

    def test_require_states_the_limit_and_refuses_past_it(self):
        self.assertEqual(mech.require("cover sag", 0.19, at_most=0.25), "cover sag: 0.19 mm (at most 0.25)")
        self.assertIn("at least 6", mech.require("pull tab to pinch", 7.0, at_least=6.0))
        with self.assertRaises(mech.Refused):
            mech.require("cover sag", 0.4, at_most=0.25)
        with self.assertRaises(ValueError):
            mech.require("no limit", 1.0)


if __name__ == "__main__":
    unittest.main()
