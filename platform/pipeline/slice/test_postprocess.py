import os
import stat
import tempfile
import unittest

from postprocess import check_manifest, run_hooks


HERE = os.path.dirname(os.path.abspath(__file__))
VENT_HOOK = os.path.join(HERE, "hooks", "core-one-close-vent.py")
FILTER_HOOK = os.path.join(HERE, "hooks", "core-one-filtration-on.py")
BLOWER_HOOK = os.path.join(HERE, "hooks", "core-one-filter-blower.py")
QUIET_HOOK = os.path.join(HERE, "hooks", "core-one-filtration-off.py")


class PostprocessTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.gcode = os.path.join(self.td.name, "plate.gcode")
        self.manifest = os.path.join(self.td.name, "gcode_manifest.json")
        with open(self.gcode, "w") as stream:
            stream.write("G28 ; home\n;TYPE:Perimeter\nG1 X1 Y1 E1\n")

    def hook(self, body):
        path = os.path.join(self.td.name, "hook.py")
        with open(path, "w") as stream:
            stream.write(body)
        return path

    def test_hook_output_and_final_bytes_are_bound(self):
        hook = self.hook("import sys\nwith open(sys.argv[1], 'a') as stream:\n"
                         "    stream.write(';HOOK\\n')\n")
        data = run_hooks(self.gcode, [hook], self.manifest)
        self.assertTrue(data["passed"])
        self.assertTrue(check_manifest(self.gcode, self.manifest)["passed"])
        with open(self.gcode, "a") as stream:
            stream.write(";changed later\n")
        result = check_manifest(self.gcode, self.manifest)
        self.assertFalse(result["passed"])
        self.assertTrue(any("changed after" in item for item in result["hard"]))

    def test_failed_hook_is_recorded_and_blocks(self):
        hook = self.hook("raise SystemExit(7)\n")
        data = run_hooks(self.gcode, [hook], self.manifest)
        self.assertFalse(data["passed"])
        self.assertFalse(check_manifest(self.gcode, self.manifest)["passed"])

    def test_zero_hooks_still_records_final_identity(self):
        self.assertTrue(run_hooks(self.gcode, [], self.manifest)["passed"])
        self.assertTrue(check_manifest(self.gcode, self.manifest)["passed"])

    def test_core_one_vent_hook_is_idempotent(self):
        first = run_hooks(self.gcode, [VENT_HOOK], self.manifest)
        self.assertTrue(first["passed"])
        second = run_hooks(self.gcode, [VENT_HOOK], self.manifest)
        self.assertTrue(second["passed"])
        with open(self.gcode) as stream:
            self.assertEqual(sum(1 for line in stream if line.startswith("M870 C")), 1)

    def test_missing_homing_blocks_vent_hook(self):
        with open(self.gcode, "w") as stream:
            stream.write("G1 X1 Y1 E1\n")
        self.assertFalse(run_hooks(self.gcode, [VENT_HOOK], self.manifest)["passed"])

    def test_filtration_hook_is_idempotent_and_runs_after_homing(self):
        for _ in range(2):
            self.assertTrue(run_hooks(self.gcode, [FILTER_HOOK, VENT_HOOK], self.manifest)["passed"])
        with open(self.gcode) as stream:
            lines = [line.split(None, 1)[0] for line in stream if line.strip()]
        self.assertEqual(lines.count("M147"), 1)
        self.assertLess(lines.index("G28"), lines.index("M147"))

    def test_filtration_hook_refuses_m148_and_missing_homing(self):
        with open(self.gcode, "w") as stream:
            stream.write("G28\nM148\nG1 X1 Y1 E1\n")
        self.assertFalse(run_hooks(self.gcode, [FILTER_HOOK], self.manifest)["passed"])
        with open(self.gcode, "w") as stream:
            stream.write("G1 X1 Y1 E1\n")
        self.assertFalse(run_hooks(self.gcode, [FILTER_HOOK], self.manifest)["passed"])

    def test_filtration_off_hook_is_idempotent_and_keeps_the_blower(self):
        with open(self.gcode, "w") as stream:
            stream.write("G28\nM191 S40\nM141 S55\nG1 X1 Y1 E1\n")
        for _ in range(2):
            self.assertTrue(run_hooks(self.gcode, [VENT_HOOK, QUIET_HOOK, BLOWER_HOOK], self.manifest)["passed"])
        lines = self.blower_lines()
        self.assertEqual((lines.count("M148"), lines.count("M147"), lines.count("M106 P4")), (1, 0, 1))
        self.assertLess(lines.index("G28"), lines.index("M148"))
        self.assertLess(lines.index("M148"), lines.index("M191"))
        self.assertEqual(lines.index("M106 P4"), lines.index("M191") + 1)

    def test_filtration_on_and_off_hooks_refuse_each_other(self):
        self.assertTrue(run_hooks(self.gcode, [FILTER_HOOK], self.manifest)["passed"])
        self.assertFalse(run_hooks(self.gcode, [QUIET_HOOK], self.manifest)["passed"])
        with open(self.gcode, "w") as stream:
            stream.write("G28\nG1 X1 Y1 E1\n")
        self.assertTrue(run_hooks(self.gcode, [QUIET_HOOK], self.manifest)["passed"])
        self.assertFalse(run_hooks(self.gcode, [FILTER_HOOK], self.manifest)["passed"])
        with open(self.gcode, "w") as stream:
            stream.write("G1 X1 Y1 E1\n")
        self.assertFalse(run_hooks(self.gcode, [QUIET_HOOK], self.manifest)["passed"])

    def blower_lines(self):
        with open(self.gcode) as stream:
            return [line.split(None, 1)[0] + (" " + line.split()[1] if line.startswith("M106") else "")
                    for line in stream if line.strip()]

    def test_blower_hook_goes_after_the_soak_once(self):
        with open(self.gcode, "w") as stream:
            stream.write("G28\nM191 S40\nM141 S55\nG1 X1 Y1 E1\n")
        for _ in range(2):
            self.assertTrue(run_hooks(self.gcode, [BLOWER_HOOK, FILTER_HOOK, VENT_HOOK], self.manifest)["passed"])
        lines = self.blower_lines()
        self.assertEqual(lines.count("M106 P4"), 1)
        self.assertEqual(lines.index("M106 P4"), lines.index("M191") + 1)

    def test_blower_hook_without_a_soak_goes_after_homing(self):
        self.assertTrue(run_hooks(self.gcode, [BLOWER_HOOK], self.manifest)["passed"])
        lines = self.blower_lines()
        self.assertEqual(lines.index("M106 P4"), lines.index("G28") + 1)

    def test_blower_hook_refuses_another_p4_setting_and_missing_homing(self):
        with open(self.gcode, "w") as stream:
            stream.write("G28\nM106 P4 S255\nG1 X1 Y1 E1\n")
        self.assertFalse(run_hooks(self.gcode, [BLOWER_HOOK], self.manifest)["passed"])
        with open(self.gcode, "w") as stream:
            stream.write("M191 S40\nG1 X1 Y1 E1\n")
        self.assertFalse(run_hooks(self.gcode, [BLOWER_HOOK], self.manifest)["passed"])


if __name__ == "__main__":
    unittest.main()
