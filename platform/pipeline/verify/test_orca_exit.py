import unittest
from orca_exit import classify_exit

class ClassifyExit(unittest.TestCase):
    def test_success_is_ok(self):
        r = classify_exit(0)
        self.assertEqual(r["severity"], "ok"); self.assertEqual(r["name"], "CLI_SUCCESS")
    def test_off_bed_is_hard(self):
        r = classify_exit(-52)
        self.assertEqual(r["severity"], "hard"); self.assertIn("bed", r["message"].lower())
    def test_unprintable_area_is_hard(self):
        self.assertEqual(classify_exit(-102)["severity"], "hard")
    def test_slicing_error_is_hard(self):
        self.assertEqual(classify_exit(-100)["severity"], "hard")
    def test_unknown_code_is_hard_not_crash(self):
        """Was 'unknown' (and therefore PASSED the gate) until 2026-07-25 — see
        NonzeroNeverPasses below. An unrecognised failure is still a failure."""
        r = classify_exit(-999)
        self.assertEqual(r["severity"], "hard"); self.assertEqual(r["code"], -999)

if __name__ == "__main__": unittest.main()


class NonzeroNeverPasses(unittest.TestCase):
    """2026-07-25: PrusaSlicer's exit 1 was unmapped, classified 'unknown', and PASSED the gate
    over a STALE gcode from the previous run. A nonzero exit must always block."""

    def test_prusaslicer_error_is_hard(self):
        r = classify_exit(1)
        self.assertEqual(r["severity"], "hard")
        self.assertIn("STALE", r["message"])

    def test_bad_args_is_hard(self):
        self.assertEqual(classify_exit(2)["severity"], "hard")

    def test_unmapped_codes_are_hard_not_unknown(self):
        for code in (3, 7, 99, -7, -999):
            r = classify_exit(code)
            self.assertEqual(r["severity"], "hard", "exit %d must block" % code)

    def test_no_nonzero_code_is_ever_ok(self):
        for code in list(range(-120, 0)) + list(range(1, 40)):
            self.assertNotEqual(classify_exit(code)["severity"], "ok", code)

    def test_zero_still_passes(self):
        self.assertEqual(classify_exit(0)["severity"], "ok")

    def test_legacy_orca_codes_still_map_by_name(self):
        self.assertEqual(classify_exit(-52)["name"], "CLI_OBJECTS_PARTLY_INSIDE")
