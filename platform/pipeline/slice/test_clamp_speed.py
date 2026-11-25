"""Behavior and resource-lifecycle tests for clamp-speed.py."""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CLAMP = os.path.join(HERE, "clamp-speed.py")
GCODE = """;Z:0.20
G1 X0 E0.2 F3000
;Z:0.60
G1 X1 E0.4 F2400
G1 X2 F9000
G1 F1800
"""


class ClampSpeedTests(unittest.TestCase):
    def run_clamp(self, path, *arguments):
        result = subprocess.run(
            [sys.executable, "-X", "dev", "-W", "always::ResourceWarning",
             CLAMP, path, "--above-z", "0.5", *arguments],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertNotIn("ResourceWarning", result.stderr)
        return result

    def test_dry_run_leaves_input_and_backup_untouched(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "plate.gcode")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(GCODE)
            result = self.run_clamp(path, "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(path, encoding="utf-8") as stream:
                self.assertEqual(stream.read(), GCODE)
            self.assertFalse(os.path.exists(path + ".bak-clamp"))

    def test_write_clamps_extrusion_but_not_travel_and_preserves_backup(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "plate.gcode")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(GCODE)
            result = self.run_clamp(path)
            self.assertEqual(result.returncode, 0, result.stderr)
            with open(path, encoding="utf-8") as stream:
                output = stream.read()
            with open(path + ".bak-clamp", encoding="utf-8") as stream:
                self.assertEqual(stream.read(), GCODE)
            self.assertIn("G1 X1 E0.4 F1200\n", output)
            self.assertIn("G1 X2 F9000\n", output)
            self.assertIn("G1 F1200\n", output)


if __name__ == "__main__":
    unittest.main()
