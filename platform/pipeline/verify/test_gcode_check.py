import unittest, tempfile, os
from gcode_check import parse_gcode, check_gcode

GOOD = """M104 S210
M140 S60
;LAYER_CHANGE
;Z:0.2
G1 X10 Y10 Z0.2 F600
G1 X20 Y20 E1.5 F600
;LAYER_CHANGE
;Z:0.4
G1 X20 Y20 Z0.4
G1 X30 Y30 E1.2
"""
OFFBED = GOOD.replace("X30 Y30 E1.2", "X400 Y30 E1.2")   # extrudes to X=400 (off a 220 bed)

NEGATIVE_Z = """M104 S210
M140 S60
;LAYER_CHANGE
;Z:-0.5
G1 X10 Y10 Z-0.5 F600
G1 X20 Y20 E1.5 F600
;LAYER_CHANGE
;Z:0.4
G1 X20 Y20 Z0.4
G1 X30 Y30 E1.2
"""

LAYER_COLON = """M104 S210
M140 S60
;LAYER:0
G1 X10 Y10 Z0.2 F600
G1 X20 Y20 E1.5 F600
;LAYER:1
G1 X20 Y20 Z0.4
G1 X30 Y30 E1.2
"""

COOLDOWN_S0 = """M104 S210
M140 S60
;LAYER_CHANGE
;Z:0.2
G1 X10 Y10 Z0.2 F600
G1 X20 Y20 E1.5 F600
;LAYER_CHANGE
;Z:0.4
G1 X20 Y20 Z0.4
G1 X30 Y30 E1.2
M104 S0
"""


class GcodeCheck(unittest.TestCase):
    def setUp(self):
        self._paths = []

    def tearDown(self):
        for p in self._paths:
            try:
                os.remove(p)
            except OSError:
                pass

    def _w(self, txt):
        f = tempfile.NamedTemporaryFile("w", suffix=".gcode", delete=False)
        f.write(txt); f.close()
        self._paths.append(f.name)
        return f.name

    def test_parse_layers_and_temps(self):
        info = parse_gcode(self._w(GOOD))
        self.assertEqual(info["layers"], 2)
        self.assertTrue(info["first_layer_extrudes"])
        self.assertEqual(info["nozzle_temp"], 210.0)
        self.assertEqual(info["bed_temp"], 60.0)
    def test_good_passes(self):
        self.assertTrue(check_gcode(parse_gcode(self._w(GOOD)))["passed"])
    def test_offbed_hard_fails(self):
        r = check_gcode(parse_gcode(self._w(OFFBED)))
        self.assertFalse(r["passed"]); self.assertTrue(any("bed" in h.lower() for h in r["hard"]))
    def test_empty_gcode_hard_fails(self):
        r = check_gcode(parse_gcode(self._w("M104 S210\n")))
        self.assertFalse(r["passed"])   # 0 layers / no extrusion
    def test_negative_z_hard_fails(self):
        r = check_gcode(parse_gcode(self._w(NEGATIVE_Z)))
        self.assertFalse(r["passed"])
        self.assertTrue(any("bed" in h.lower() for h in r["hard"]))
    def test_layer_colon_marker_counted(self):
        info = parse_gcode(self._w(LAYER_COLON))
        self.assertEqual(info["layers"], 2)
    def test_cooldown_s0_keeps_prior_nozzle_temp(self):
        info = parse_gcode(self._w(COOLDOWN_S0))
        self.assertEqual(info["nozzle_temp"], 210.0)

if __name__ == "__main__": unittest.main()
