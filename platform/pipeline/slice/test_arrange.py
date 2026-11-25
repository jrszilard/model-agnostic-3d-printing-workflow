"""Tests for arrange.py — the guard against PrusaSlicer's silent multi-file collapse.

The bug this whole module exists to prevent is silent: hand the CLI N STLs and it slices only
the last one, exit 0, no warning. So the tests that matter most assert that every part survives
into the plate, not just that the call succeeded.
"""
import os
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arrange


def write_box_stl(path, size, origin=(0.0, 0.0, 0.0)):
    """Minimal binary STL of an axis-aligned box — enough for bbox and OpenSCAD import."""
    (sx, sy, sz), (ox, oy, oz) = size, origin
    v = [(ox, oy, oz), (ox + sx, oy, oz), (ox + sx, oy + sy, oz), (ox, oy + sy, oz),
         (ox, oy, oz + sz), (ox + sx, oy, oz + sz), (ox + sx, oy + sy, oz + sz), (ox, oy + sy, oz + sz)]
    faces = [(0, 3, 2), (0, 2, 1), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    with open(path, "wb") as f:
        f.write(b"\0" * 80)
        f.write(struct.pack("<I", len(faces)))
        for a, b, c in faces:
            f.write(struct.pack("<3f", 0.0, 0.0, 0.0))
            for idx in (a, b, c):
                f.write(struct.pack("<3f", *v[idx]))
            f.write(b"\0\0")


class TestBbox(unittest.TestCase):
    def test_reads_a_binary_stl_bbox(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "b.stl")
            write_box_stl(p, (10, 20, 5), origin=(3, 4, 1))
            self.assertEqual(arrange.stl_bbox(p), (3, 4, 1, 13, 24, 6))

    def test_reads_an_ascii_stl_bbox(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.stl")
            with open(p, "w") as f:
                f.write("solid t\nfacet normal 0 0 1\nouter loop\n"
                        "vertex 0 0 0\nvertex 2 0 0\nvertex 0 3 4\n"
                        "endloop\nendfacet\nendsolid t\n")
            self.assertEqual(arrange.stl_bbox(p), (0, 0, 0, 2, 3, 4))


class TestPacking(unittest.TestCase):
    def test_parts_do_not_overlap(self):
        sizes = [(30, 30)] * 6
        place, _ = arrange.shelf_pack(sizes, bed=(250, 220), gap=6)
        for i in range(len(sizes)):
            for j in range(i + 1, len(sizes)):
                (ax, ay), (aw, ah) = place[i], sizes[i]
                (bx, by), (bw, bh) = place[j], sizes[j]
                apart = ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay
                self.assertTrue(apart, f"parts {i} and {j} overlap")

    def test_wraps_to_a_second_shelf_when_a_row_is_full(self):
        place, (w, h) = arrange.shelf_pack([(100, 20)] * 4, bed=(250, 220), gap=6)
        self.assertLessEqual(w, 250)
        self.assertGreater(h, 20, "four 100mm parts cannot fit on one 250mm shelf")

    def test_reports_a_plate_too_big_for_the_bed(self):
        with tempfile.TemporaryDirectory() as d:
            stls = []
            for i in range(3):
                p = os.path.join(d, f"big{i}.stl")
                write_box_stl(p, (200, 200, 5))
                stls.append(p)
            rc = arrange.main(["--out", os.path.join(d, "plate.stl")] + stls)
            self.assertEqual(rc, 1, "an oversized plate must fail, not silently truncate")


@unittest.skipIf(subprocess.run(["which", os.environ.get("OPENSCAD", "openscad")],
                                stdout=subprocess.DEVNULL).returncode != 0,
                 "openscad not installed")
class TestPlateBuild(unittest.TestCase):
    def test_every_part_survives_into_the_plate(self):
        """The regression that matters: 3 parts in, 3 parts' worth of geometry out."""
        with tempfile.TemporaryDirectory() as d:
            stls = []
            for i in range(3):
                p = os.path.join(d, f"p{i}.stl")
                write_box_stl(p, (10, 10, 10))
                stls.append(p)
            out = os.path.join(d, "plate.stl")
            self.assertEqual(arrange.main(["--out", out, "--gap", "5"] + stls), 0)
            b = arrange.stl_bbox(out)
            width = b[3] - b[0]
            # 3 parts of 10mm with 5mm gaps span 40mm; one surviving part would span 10mm.
            self.assertAlmostEqual(width, 40.0, delta=0.5,
                                   msg=f"plate spans {width}mm — parts were dropped")

    def test_parts_are_seated_on_the_bed(self):
        with tempfile.TemporaryDirectory() as d:
            a = os.path.join(d, "a.stl"); write_box_stl(a, (10, 10, 10), origin=(0, 0, 17))
            b = os.path.join(d, "b.stl"); write_box_stl(b, (10, 10, 10), origin=(0, 0, -4))
            out = os.path.join(d, "plate.stl")
            self.assertEqual(arrange.main(["--out", out] + [a, b]), 0)
            self.assertAlmostEqual(arrange.stl_bbox(out)[2], 0.0, delta=0.01,
                                   msg="plate does not sit on z=0")



class OrientationFallback(unittest.TestCase):
    def test_many_long_copies_fall_back_to_as_modelled(self):
        box = (0, 0, 0, 103.0, 25.5, 4.4)
        boxes = [box] * 12
        rots = [True] * 12                      # what the portrait rule picks for this shape
        rs, sizes, offsets, (pw, ph) = arrange.choose_orientation(boxes, rots, (250, 220), 6)
        self.assertEqual(rs, [False] * 12)
        self.assertLessEqual(pw, 250); self.assertLessEqual(ph, 220)

    def test_portrait_kept_when_it_fits(self):
        boxes = [(0, 0, 0, 80, 20, 3), (0, 0, 0, 100, 150, 10)]
        rots = [True, False]
        rs, _, _, (pw, ph) = arrange.choose_orientation(boxes, rots, (250, 220), 6)
        self.assertEqual(rs, [True, False])

if __name__ == "__main__":
    unittest.main()
