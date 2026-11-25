import importlib.util
import json
import os
import tempfile
import unittest

import numpy as np


HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "plan-drawing.py")
SPEC = importlib.util.spec_from_file_location("plan_drawing", PATH)
plan = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(plan)


TRI = np.array([
    [(0, 0, 0), (2, 0, 0), (0, 3, 0)],
    [(2, 0, 0), (2, 3, 0), (0, 3, 0)],
    [(0, 0, 1), (0, 3, 1), (2, 0, 1)],
    [(2, 0, 1), (0, 3, 1), (2, 3, 1)],
], dtype=float)


class PlanDrawingTests(unittest.TestCase):
    def test_top_view_reports_real_mesh_dimensions_and_writes_svg(self):
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "plan.svg")
            result = plan.draw(TRI, out, view="top", title="fixture",
                               annotations=[{"text": "Edge B", "at": [1, 0]}])
            self.assertAlmostEqual(result["width"], 2.0)
            self.assertAlmostEqual(result["height"], 3.0)
            self.assertEqual(result["annotations"], 1)
            self.assertGreater(os.path.getsize(out), 1000)

    def test_view_mapping_is_explicit(self):
        projected, _ = plan.project(TRI, "front")
        self.assertEqual(projected.shape, (4, 3, 2))
        self.assertAlmostEqual(projected[:, :, 0].max(), 2.0)  # X
        self.assertAlmostEqual(projected[:, :, 1].max(), 1.0)  # Z

    def test_ascii_stl_and_json_annotations_load(self):
        with tempfile.TemporaryDirectory() as td:
            stl = os.path.join(td, "x.stl")
            annotations = os.path.join(td, "labels.json")
            with open(stl, "w") as stream:
                stream.write("solid x\nfacet normal 0 0 1\nouter loop\n"
                             "vertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\n"
                             "endloop\nendfacet\nendsolid x\n")
            with open(annotations, "w") as stream:
                json.dump([{"text": "datum", "at": [0, 0]}], stream)
            self.assertEqual(plan.load_stl(stl).shape, (1, 3, 3))
            self.assertEqual(plan.load_annotations(annotations)[0]["text"], "datum")
            stamp = plan.write_stamp(stl, os.path.join(td, "x_plan.png"))
            with open(stamp) as stream:
                self.assertIn("geom=", stream.read())


if __name__ == "__main__":
    unittest.main()
