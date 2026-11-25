"""Tests for colour_plate.py: the colour-region 3MF, the slicer overrides, and the swap rewrite."""
import os
import re
import struct
import tempfile
import unittest
import zipfile

import colour_plate as cp


def write_box_stl(path, x0, x1, y0, y1, z0, z1, binary=True):
    p = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
         (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    if binary:
        with open(path, "wb") as s:
            s.write(b"\0" * 80 + struct.pack("<I", len(f)))
            for a, b, c in f:
                s.write(struct.pack("<12fH", 0, 0, 0, *p[a], *p[b], *p[c], 0))
    else:
        with open(path, "w") as s:
            s.write("solid t\n")
            for a, b, c in f:
                s.write("facet normal 0 0 0\nouter loop\n")
                for v in (p[a], p[b], p[c]):
                    s.write("vertex %f %f %f\n" % v)
                s.write("endloop\nendfacet\n")
            s.write("endsolid t\n")


# A swap the way PrusaSlicer 2.9.6 writes one with the overrides below (trimmed).
GCODE = """M83 ; use relative distances for extrusion
;LAYER_CHANGE
;Z:0.2
G1 X100 Y80 E1.0
G1 X120 Y80 E1.0
G1 X120 Y140 E1.0
M486 S-1
; Filament-specific end gcode
M117 Load WHITE
M600 ; lakeshore: colour swap, filament 1 -> 2
T1
M107
G1 E-.7 F2700
G1 X110 Y90 F21000
G1 E.7 F1500
G1 X130 Y90 E1.0
;LAYER_CHANGE
;Z:0.4
M117 Load BLACK
M600 ; lakeshore: colour swap, filament 2 -> 1
T0
G1 X100 Y100 E1.0
; filament used [mm] = 3777.76, 142.25, 142.39
; filament used [g] = 11.27, 0.42, 0.42
; total toolchanges = 9
; extruder_colour = ""
; filament_type = PLA;PLA;PLA
; retract_length = 0.7
"""


class RegionArgs(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(cp.parse_region("a/b=c.stl=2"), ("a/b=c.stl", 2))
        for bad in ("x.stl", "x.stl=1", "x.stl=0", "=2", "x.stl=a"):
            with self.assertRaises(ValueError):
                cp.parse_region(bad)

    def test_filaments_run_without_gaps(self):
        self.assertEqual(cp.check_regions([("a", 2), ("b", 3), ("c", 2)]), 3)
        with self.assertRaises(ValueError):
            cp.check_regions([("a", 3)])


class Build3mf(unittest.TestCase):
    def test_one_object_body_part_and_modifier_regions(self):
        with tempfile.TemporaryDirectory() as d:
            base, line = os.path.join(d, "base.stl"), os.path.join(d, "line.stl")
            write_box_stl(base, 0, 80, 0, 60, 0, 3)
            write_box_stl(line, 0, 80, 9, 11, 0, 0.6, binary=False)
            out = os.path.join(d, "plate.3mf")
            cp.build_3mf(out, base, [(line, 2)])
            with zipfile.ZipFile(out) as z:
                model = z.read("3D/3dmodel.model").decode()
                cfg = z.read("Metadata/Slic3r_PE_model.config").decode()
            self.assertEqual(model.count("<object "), 1)
            self.assertEqual(model.count("<vertex "), 16)        # deduplicated, 8 per box
            self.assertEqual(model.count("<triangle "), 24)
            vols = re.findall(r'firstid="(\d+)" lastid="(\d+)".*?volume_type" value="(\w+)"'
                              r'.*?extruder" value="(\d+)"', cfg)
            self.assertEqual(vols, [("0", "11", "ModelPart", "1"),
                                    ("12", "23", "ParameterModifier", "2")])
            self.assertIn('z="0.60000"', model)


class Overrides(unittest.TestCase):
    def test_one_nozzle_entry_per_filament_from_the_profile(self):
        o = cp.overrides("Prusa CORE One HF0.4 nozzle", 3)
        self.assertIn("nozzle_diameter=0.4,0.4,0.4", o)
        self.assertIn("single_extruder_multi_material=1", o)
        self.assertIn("wipe_tower=0", o)
        tc = [x for x in o if x.startswith("toolchange_gcode=")][0]
        self.assertTrue(tc.startswith("toolchange_gcode={if previous_extruder >= 0}M117 Load "))  # none at start
        self.assertIn("M600 ; lakeshore: colour swap", tc)

    def test_the_macro_names_the_colour_to_load(self):
        tc = cp.toolchange_gcode(["black", "white", "yellow"])
        self.assertIn("M117 Load {if next_extruder == 0}BLACK{elsif next_extruder == 1}WHITE"
                      "{elsif next_extruder == 2}YELLOW{else}filament {next_extruder + 1}{endif}", tc)
        self.assertLess(tc.index("M117"), tc.index("M600"))
        self.assertIn("\\nM600", tc)               # an escaped newline, as the .ini stores it
        self.assertEqual(cp.parse_names("black,white,yellow", 3), ["black", "white", "yellow"])
        for bad in ("black,white", "black,white,yel low", "a,b,averyveryverylongname"):
            with self.assertRaises(ValueError):
                cp.parse_names(bad, 3)

    def test_unknown_nozzle_refuses(self):
        with self.assertRaises(ValueError):
            cp.overrides("Some Printer", 2)


class BedCentre(unittest.TestCase):
    def test_centre_of_the_bed_shape(self):
        self.assertEqual(cp.bed_centre("x = 1\nbed_shape = 0x0,250x0,250x220,0x220\n"), "125,110")
        with self.assertRaises(ValueError):
            cp.bed_centre("nothing here")


class Swaps(unittest.TestCase):
    def lines(self):
        return GCODE.splitlines(keepends=True)

    def test_tool_lines_commented_and_purge_after_each_swap(self):
        out, report = cp.rewrite_swaps(self.lines())
        text = "".join(out)
        self.assertFalse(re.search(r"^T\d+\s*$", text, re.M))
        self.assertEqual(text.count("lakeshore: purge line after the change"), 2)
        self.assertIn("2 manual swaps; 2 tool-select lines commented out", report[0])
        # the purge follows its M600 and returns to where the swap interrupted, at the layer's Z
        i = out.index("M600 ; lakeshore: colour swap, filament 1 -> 2\n")
        block = "".join(out[i + 1:i + 20])
        self.assertIn("X120.000 Y140.000 F9000 ; back over the print", block)
        self.assertIn("G1 Z0.200 F720", block)

    def test_colour_messages_are_numbered(self):
        out, report = cp.rewrite_swaps(self.lines())
        self.assertIn("M117 Load WHITE 1/2\n", out)
        self.assertIn("M117 Load BLACK 2/2\n", out)
        self.assertEqual(out.index("M117 Load WHITE 1/2\n") + 1,
                         out.index("M600 ; lakeshore: colour swap, filament 1 -> 2\n"))
        self.assertIn("(load WHITE)", report[1])

    def test_the_file_says_one_tool(self):
        """Prusa-Firmware-Buddy's is_singletool_gcode(): no second entry in filament_type /
        extruder_colour (';') or filament used [mm] / [g] (',')."""
        out, report = cp.rewrite_swaps(self.lines())
        meta = dict(re.match(r"^; (.+?) = (.*)$", ln.rstrip("\n")).groups()
                    for ln in out if re.match(r"^; .+? = ", ln))
        for key, sep in (("filament_type", ";"), ("extruder_colour", ";"),
                         ("filament used [mm]", ","), ("filament used [g]", ",")):
            self.assertNotIn(sep, meta[key], key)
        self.assertEqual(meta["filament used [g]"], "12.11")
        self.assertEqual(meta["filament used [mm]"], "4062.40")
        self.assertEqual(meta["filament_type"], "PLA")
        self.assertEqual(meta["total toolchanges"], "0")
        self.assertIn("one-tool metadata", report[0])

    def test_each_swap_gets_its_own_lane(self):
        out, report = cp.rewrite_swaps(self.lines())
        lanes = re.findall(r"purge lane (X\S+ Y\S+)", "\n".join(report))
        self.assertEqual(len(lanes), 2)
        self.assertEqual(len(set(lanes)), 2)

    def test_lanes_clear_the_start_purge_and_each_other(self):
        spans = [(min(x1, x0), x0 + 11.0, y) for x0, x1, y in cp.LANES]
        for lo, hi, y in spans:
            if y == -2.5:
                self.assertLess(hi, 199.0)                  # start gcode purges X249 -> X199
        for a in spans:
            for b in spans:
                if a is not b and a[2] == b[2]:
                    self.assertTrue(a[1] < b[0] or b[1] < a[0])

    def test_too_many_swaps_refuses(self):
        with self.assertRaises(ValueError):
            cp.rewrite_swaps(self.lines(), lanes=cp.LANES[:1])

    def test_hook_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "plate_1.gcode")
            with open(path, "w") as s:
                s.write(GCODE)
            self.assertEqual(cp.swaps(path), 0)
            with open(path) as s:
                once = s.read()
            self.assertEqual(cp.swaps(path), 0)
            with open(path) as s:
                self.assertEqual(s.read(), once)


if __name__ == "__main__":
    unittest.main()
