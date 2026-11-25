"""Tests for color-change.py, in particular the post-swap purge line.

The purge block drives the nozzle down to the sheet and back mid-print, so the parts worth
pinning are the ones that would crash it: that it returns to the exact position the pause
interrupted, that it refuses a lane the print is sitting in, and that the machine's own
start-gcode purge does not count as "the print" when checking that lane.
"""
import importlib.util
import os
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("color_change",
                                               os.path.join(_HERE, "color-change.py"))
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)


def _gcode(layers=("0.2", "0.4", "0.6"), last_xy=(60.0, 70.0)):
    """A minimal but structurally honest PrusaSlicer gcode: start block, layer table, config."""
    L = ["M83 ; extruder relative mode\n", ";TYPE:Custom\n",
         "G1 X249 Y-2.5 Z0.2 E5 F500 ; the machine's own purge line\n",
         "G1 X199 Y-2.5 E4 F800\n"]
    for z in layers:
        L += [";Z:%s\n" % z, ";AFTER_LAYER_CHANGE\n", ";TYPE:External perimeter\n",
              "G1 X%.3f Y%.3f E0.5 F1200\n" % (last_xy[0] + 40, last_xy[1] + 40),
              "G1 X%.3f Y%.3f E0.5 F1200\n" % last_xy]
    L += ["; filament_retract_length = 0.4\n", "; retract_length = 0.7\n"]
    return L


class TestFootprint(unittest.TestCase):
    def test_start_purge_is_not_the_print(self):
        # Y=-2.5 is extruded in the start block. Counting it would make the lane look
        # permanently occupied by the very line this tool is imitating.
        fp = cc.printed_footprint(_gcode())
        self.assertGreater(fp[1], 0.0, "start-gcode purge leaked into the footprint")

    def test_lane_clear_when_the_print_is_up_the_bed(self):
        self.assertIsNone(cc.lane_is_clear((20.0, 20.0, 230.0, 200.0)))

    def test_lane_blocked_when_the_print_reaches_the_front(self):
        why = cc.lane_is_clear((20.0, 0.5, 230.0, 200.0))
        self.assertIsNotNone(why)
        self.assertIn("purge lane", why)

    def test_lane_clear_when_the_print_is_off_to_one_side(self):
        # Same front margin, but nowhere near the lane in X.
        self.assertIsNone(cc.lane_is_clear((215.0, 0.5, 245.0, 200.0)))

    def test_no_extrusion_at_all_is_reported_not_assumed_clear(self):
        self.assertIsNotNone(cc.lane_is_clear((float("inf"), float("inf"),
                                               float("-inf"), float("-inf"))))


class TestResumePosition(unittest.TestCase):
    def test_finds_the_last_xy_before_the_pause(self):
        lines = _gcode(last_xy=(61.5, 72.25))
        idx = len(lines)
        self.assertEqual(cc.resume_position(lines, idx), (61.5, 72.25))

    def test_scans_backwards_for_a_split_x_and_y(self):
        lines = ["G1 X10 Y20 E1\n", "G1 X15 E1\n"]
        self.assertEqual(cc.resume_position(lines, 2), (15.0, 20.0))


class TestPrimeBlock(unittest.TestCase):
    def block(self, **kw):
        return cc.prime_block(60.0, 70.0, 33.0, 0.4, True, **kw)

    def test_returns_to_the_position_the_pause_interrupted(self):
        b = self.block()
        moves = [ln for ln in b if ln.startswith("G1 X")]
        self.assertIn("X60.000 Y70.000", moves[-1])
        # ...and the last Z command puts it back on the substrate, not left in the air.
        zs = [ln for ln in b if ln.startswith("G1 Z")]
        self.assertIn("Z33.000", zs[-1])

    def test_travels_above_the_part_in_both_directions(self):
        b = self.block()
        zs = [float(ln.split("Z")[1].split()[0]) for ln in b if ln.startswith("G1 Z")]
        self.assertEqual(zs[0], 33.0 + cc.PRIME_LIFT)     # lift before leaving
        self.assertEqual(zs[-2], 33.0 + cc.PRIME_LIFT)    # lift before coming back

    def test_purges_the_requested_volume(self):
        b = self.block(vol=80.0)
        e = sum(float(ln.split("E")[1].split()[0])
                for ln in b if ln.startswith("G1 X") and " E" in ln and "E-" not in ln)
        self.assertAlmostEqual(e * cc.FIL_AREA, 80.0, places=1)

    def test_is_marked_custom_so_the_off_bed_gate_ignores_the_lane(self):
        # The lane is deliberately in front of the print area; gcode_check.py excludes
        # ;TYPE:Custom extrusion for exactly this reason.
        self.assertIn(";TYPE:Custom\n", self.block())

    def test_absolute_e_gcode_switches_modes_around_the_block(self):
        b = cc.prime_block(60.0, 70.0, 33.0, 0.4, False)
        self.assertTrue(any(ln.startswith("M83") for ln in b))
        self.assertTrue(any(ln.startswith("M82") for ln in b))
        self.assertTrue(any(ln.startswith("G92 E0") for ln in b))

    def test_wipe_runs_past_the_bead_not_back_over_it(self):
        b = self.block()
        wipes = [ln for ln in b if "wipe close to the sheet" in ln or "snap away" in ln]
        xs = [float(ln.split("X")[1].split()[0]) for ln in wipes]
        self.assertTrue(all(x > cc.PRIME_X0 for x in xs), "wipe went back over the purge")


class TestEndToEnd(unittest.TestCase):
    def run_on(self, lines, *args):
        fd, path = tempfile.mkstemp(suffix=".gcode")
        with os.fdopen(fd, "w") as fh:
            fh.write("".join(lines))
        try:
            rc = cc.main(["color-change.py", path, "--at-z", "0.4"] + list(args))
            with open(path, encoding="utf-8") as stream:
                out = stream.read()
        finally:
            for p in (path, path + ".bak"):
                if os.path.exists(p):
                    os.unlink(p)
        return rc, out

    def test_pause_only(self):
        rc, out = self.run_on(_gcode())
        self.assertEqual(rc, 0)
        self.assertIn("M600", out)
        self.assertNotIn("purge line after the change", out)

    def test_pause_with_prime(self):
        rc, out = self.run_on(_gcode(), "--prime")
        self.assertEqual(rc, 0)
        self.assertIn("purge line after the change", out)
        self.assertLess(out.index("M600"), out.index("purge line after the change"),
                        "the purge must follow the swap, not precede it")

    def test_prime_refuses_a_lane_the_print_sits_in(self):
        lines = _gcode(last_xy=(160.0, 2.0))
        rc, out = self.run_on(lines, "--prime")
        self.assertEqual(rc, 5)
        self.assertNotIn("purge line after the change", out)

    def test_second_run_refuses_rather_than_stacking_pauses(self):
        lines = _gcode()
        fd, path = tempfile.mkstemp(suffix=".gcode")
        with os.fdopen(fd, "w") as fh:
            fh.write("".join(lines))
        try:
            self.assertEqual(cc.main(["cc", path, "--at-z", "0.4", "--prime"]), 0)
            self.assertEqual(cc.main(["cc", path, "--at-z", "0.4", "--prime"]), 4)
        finally:
            for p in (path, path + ".bak"):
                if os.path.exists(p):
                    os.unlink(p)


if __name__ == "__main__":
    unittest.main()
