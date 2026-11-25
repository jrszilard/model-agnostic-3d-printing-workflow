"""Bed fit is judged on the part AS THE SLICER PLACES IT, not as the STL was exported.

Until 2026-09-18 mesh_check.py measured the raw STL's bounding box, while slice.sh hands PrusaSlicer
the plate's --rotate-x/-y/-z and records them in slice_meta.json. The check was wrong both ways:
  - a 1 ft gutter-backstop segment (12.1 x 304.8) that fits the 250 x 220 bed turned 49 deg was
    refused, although its G-code extruded X 6.3..243.7, Y 5.8..214.2;
  - a 240 x 20 part turned 90 deg (20 x 240, past the 220 axis) would have PASSED.
verify-slice.sh now passes the recorded rotation as MESH_ROT="x y z" (degrees, applied x then y
then z, the order slice.sh gives them to PrusaSlicer), and mesh_check.py measures the turned mesh.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MESH_CHECK = os.path.join(HERE, "mesh_check.py")
VERIFY = os.path.join(HERE, "verify-slice.sh")
SLICE_IDENTITY = os.path.realpath(os.path.join(HERE, "..", "slice", "slice_identity.py"))
POST = os.path.realpath(os.path.join(HERE, "..", "slice", "postprocess.py"))
FREECADCMD = shutil.which("freecadcmd")


def box_stl(path, dx, dy, dz):
    """An ASCII STL of an axis-aligned box from the origin; 12 outward-wound triangles."""
    v = [(x, y, z) for x in (0, dx) for y in (0, dy) for z in (0, dz)]
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    with open(path, "w") as s:
        s.write("solid box\n")
        for a, b, c, d in quads:
            for tri in ((a, b, c), (a, c, d)):
                s.write(" facet normal 0 0 0\n  outer loop\n")
                for i in tri:
                    s.write("   vertex %g %g %g\n" % v[i])
                s.write("  endloop\n endfacet\n")
        s.write("endsolid box\n")


@unittest.skipUnless(FREECADCMD, "freecadcmd not installed")
class MeshCheckRotation(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory(); self.addCleanup(self.td.cleanup)

    def run_check(self, dims, rot=None, batch=False):
        stl = os.path.join(self.td.name, "part.stl")
        box_stl(stl, *dims)
        env = {k: v for k, v in os.environ.items() if k not in ("MESH", "MESH_LIST", "MESH_ROT")}
        env["MESH_LIST" if batch else "MESH"] = stl
        if rot is not None:
            env["MESH_ROT"] = rot
        return subprocess.run([FREECADCMD, MESH_CHECK], env=env, text=True, timeout=120,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def test_segment_unturned_is_oversize(self):
        r = self.run_check((12.1, 304.8, 127.0))
        self.assertIn("MESH_RESULT: FAIL", r.stdout)

    def test_segment_turned_49_fits(self):
        r = self.run_check((12.1, 304.8, 127.0), rot="0 0 49")
        self.assertIn("MESH_RESULT: PASS", r.stdout, r.stdout[-800:])
        self.assertEqual(r.returncode, 0)

    def test_turn_that_breaks_the_fit_is_caught(self):
        self.assertIn("MESH_RESULT: PASS", self.run_check((240.0, 20.0, 10.0)).stdout)
        self.assertIn("MESH_RESULT: FAIL", self.run_check((240.0, 20.0, 10.0), rot="0 0 90").stdout)

    def test_order_is_x_then_y_then_z(self):
        # PrusaSlicer applies transforms in argv order, and slice.sh passes x, y, z. 240 x 20 x 10:
        #   x 90 then z 90: (240, 10, 20) -> (10, 240, 20), 240 on the 220 axis: FAIL
        #   z 90 then x 90: (20, 240, 10) -> (20, 10, 240), 240 under the 270 z: PASS
        self.assertIn("MESH_RESULT: FAIL", self.run_check((240.0, 20.0, 10.0), rot="90 0 90").stdout)

    def test_batch_mode_turns_too(self):
        r = self.run_check((12.1, 304.8, 127.0), rot="0 0 49", batch=True)
        self.assertIn("MESH_RESULT: PASS", r.stdout, r.stdout[-800:])

    def test_malformed_rotation_is_a_hard_error_not_a_pass(self):
        # A box that fits unturned, so ignoring the bad rotation would read as PASS.
        r = self.run_check((10.0, 10.0, 10.0), rot="0 0 forty-nine")
        self.assertNotIn("MESH_RESULT: PASS", r.stdout)
        self.assertNotEqual(r.returncode, 0)


FAKE_FREECAD = '''#!/usr/bin/env python3
import os, sys
rot = os.environ.get("MESH_ROT", "<unset>")
items = os.environ.get("MESH_LIST")
paths = items.split("\\n") if items is not None else [os.environ.get("MESH", "")]
for i, p in enumerate(paths):
    if items is not None:
        print("\\nMESH_ITEM_BEGIN %d" % i)
    print("bbox 1.0 x 1.0 x 1.0 rot=%s" % rot)
    print("MESH_RESULT: PASS")
    if items is not None:
        print("\\nMESH_ITEM_END %d" % i)
'''


class VerifySlicePassesRotation(unittest.TestCase):
    """verify-slice.sh reads the rotation slice.sh recorded and hands it to mesh_check."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory(); self.addCleanup(self.td.cleanup)
        self.out = self.td.name
        self.fake = os.path.join(self.out, "fake-freecadcmd")
        with open(self.fake, "w") as s:
            s.write(FAKE_FREECAD)
        os.chmod(self.fake, 0o755)
        self.stl = os.path.join(self.out, "part.stl")
        box_stl(self.stl, 10, 10, 10)
        gcode = os.path.join(self.out, "plate_1.gcode")
        with open(gcode, "w") as s:
            s.write("; generated by PrusaSlicer test\nM83\n;LAYER_CHANGE\nG1 Z0.20\n"
                    ";TYPE:Perimeter\nG1 X10 Y10 E1\n; prusaslicer_config = begin\n"
                    "; layer_height = 0.2\n; prusaslicer_config = end\n")
        with open(os.path.join(self.out, "slice_exit.txt"), "w") as s:
            s.write("0\n")
        with open(os.path.join(self.out, "plate.3mf"), "wb") as s:
            s.write(b"3mf")
        with open(os.path.join(self.out, ".overrides.ini"), "w") as s:
            s.write("binary_gcode = 0\n")
        subprocess.run(["python3", POST, "--gcode", gcode,
                        "--manifest", os.path.join(self.out, "gcode_manifest.json")],
                       check=True, stdout=subprocess.PIPE, text=True)
        self.gcode = gcode

    def write_meta(self, rz):
        subprocess.run([
            "python3", SLICE_IDENTITY, "write",
            "--meta", os.path.join(self.out, "slice_meta.json"),
            "--gcode", self.gcode, "--project", os.path.join(self.out, "plate.3mf"),
            "--overrides", os.path.join(self.out, ".overrides.ini"),
            "--slicer", "prusa-slicer", "--machine", "m", "--process", "p", "--filament", "f",
            "--rotate-x", "0", "--rotate-y", "0", "--rotate-z", rz],
            check=True, stdout=subprocess.PIPE, text=True)

    def verify(self):
        return subprocess.run([VERIFY, self.out, self.stl], text=True, timeout=120,
                              env=dict(os.environ, FREECADCMD=self.fake),
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def test_recorded_rotation_reaches_the_mesh_check(self):
        self.write_meta("49")
        self.assertIn("rot=0.0 0.0 49.0", self.verify().stdout)

    def test_no_slice_meta_means_no_rotation(self):
        self.assertIn("rot=<unset>", self.verify().stdout)


if __name__ == "__main__":
    unittest.main()
