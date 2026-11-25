import json
import os
import tempfile
import unittest

from support_check import check_support, load_policy, parse_toolpaths, toolpath_bbox


BASE = """M83
;TYPE:Perimeter
G1 X0 Y0 Z0.2
G1 X10 Y0 E1
{support}
"""
SUPPORT = """;TYPE:Support material
G1 X0 Y0
G1 X10 Y0 E1
"""


class SupportCheckTests(unittest.TestCase):
    def gcode(self, support=""):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".gcode", delete=False)
        tmp.write(BASE.format(support=support)); tmp.close()
        self.addCleanup(lambda: os.path.exists(tmp.name) and os.unlink(tmp.name))
        return tmp.name

    def test_required_support_cannot_pass_vacuously(self):
        result = check_support(self.gcode(), {"required": True, "keepouts": []})
        self.assertFalse(result["passed"])
        self.assertIn("zero support extrusion", result["hard"][0])

    def test_requested_support_is_detected(self):
        result = check_support(self.gcode(SUPPORT), {"required": True, "keepouts": []})
        self.assertTrue(result["passed"])
        self.assertGreater(len(result["paths"]["support"]), 0)

    def test_segment_crossing_cylinder_is_blocked_even_if_endpoints_are_outside(self):
        policy = {"required": True, "keepouts": [
            {"id": "bore", "shape": "cylinder", "axis": "z",
             "center": [5, 0], "radius": 0.5, "frame": "plate"}]}
        result = check_support(self.gcode(SUPPORT), policy)
        self.assertFalse(result["passed"])
        self.assertIn("keepout bore", result["hard"][0])

    def test_segment_crossing_oriented_finite_cylinder_is_blocked(self):
        policy = {"required": True, "keepouts": [
            {"id": "rotated-bore", "shape": "finite-cylinder", "center": [5, 0, 0.2],
             "axis": [0, 1, 0], "half_length": 3, "radius": 0.5, "frame": "plate"}]}
        result = check_support(self.gcode(SUPPORT), policy)
        self.assertFalse(result["passed"])
        self.assertIn("keepout rotated-bore", result["hard"][0])

    def test_oriented_finite_cylinder_bbox_min_tracks_translation(self):
        text = """M83
;TYPE:Perimeter
G1 X20 Y10 Z0.2
G1 X30 Y10 E1
;TYPE:Support material
G1 X20 Y10
G1 X30 Y10 E1
"""
        tmp = tempfile.NamedTemporaryFile("w", suffix=".gcode", delete=False)
        tmp.write(text); tmp.close(); self.addCleanup(lambda: os.unlink(tmp.name))
        policy = {"required": True, "keepouts": [
            {"id": "relative-rotated-bore", "shape": "finite-cylinder", "center": [5, 0, 0.2],
             "axis": [0, 1, 0], "half_length": 3, "radius": 0.5, "frame": "bbox-min"}]}
        self.assertFalse(check_support(tmp.name, policy)["passed"])

    def test_oriented_finite_cylinder_rejects_zero_axis(self):
        policy = {"required": False, "keepouts": [
            {"id": "bad", "shape": "finite-cylinder", "center": [5, 0, 0.2],
             "axis": [0, 0, 0], "half_length": 3, "radius": 0.5}]}
        result = check_support(self.gcode(), policy)
        self.assertFalse(result["passed"])
        self.assertIn("non-zero", result["hard"][0])

    def test_bbox_min_frame_tracks_translation(self):
        text = """M83
;TYPE:Skirt
G1 X0 Y0 Z0.2
G1 X5 Y0 E1
;TYPE:Perimeter
G1 X20 Y10 Z0.2
G1 X30 Y10 E1
;TYPE:Support material
G1 X20 Y10
G1 X30 Y10 E1
"""
        tmp = tempfile.NamedTemporaryFile("w", suffix=".gcode", delete=False)
        tmp.write(text); tmp.close(); self.addCleanup(lambda: os.unlink(tmp.name))
        policy = {"required": True, "keepouts": [
            {"id": "relative-bore", "axis": "z", "center": [5, 0],
             "radius": 0.5, "frame": "bbox-min"}]}
        self.assertFalse(check_support(tmp.name, policy)["passed"])

    def test_model_extrusion_in_keepout_is_not_a_support_violation(self):
        policy = {"required": False, "keepouts": [
            {"id": "model-only", "axis": "z", "center": [5, 0], "radius": 0.5}]}
        self.assertTrue(check_support(self.gcode(), policy)["passed"])

    def test_meta_and_spec_combine_support_intent_and_keepouts(self):
        with tempfile.TemporaryDirectory() as td:
            spec = os.path.join(td, "spec.yaml")
            meta = os.path.join(td, "slice_meta.json")
            with open(spec, "w") as stream:
                stream.write("slice:\n  support:\n    keepouts:\n"
                             "      - {id: bore, axis: z, center: [5, 0], radius: 1}\n")
            with open(meta, "w") as stream:
                json.dump({"support_requested": True, "spec": spec}, stream)
            policy = load_policy(meta)
            self.assertTrue(policy["required"])
            self.assertEqual(policy["keepouts"][0]["id"], "bore")

    def test_support_arcs_are_interpolated(self):
        arc = """;TYPE:Support material
G1 X0 Y0
G3 X10 Y0 I5 J0 E1
"""
        self.assertGreater(len(parse_toolpaths(self.gcode(arc))["support"]), 2)


class ToolpathBbox(unittest.TestCase):
    """toolpath_bbox is public API: `frame: bbox-min` keep-outs are declared against it."""

    def test_bbox_spans_every_segment_endpoint(self):
        segments = [[(0.0, 1.0, 0.2), (4.0, 1.0, 0.2)], [(2.0, -3.0, 1.5), (2.0, 5.0, 1.5)]]
        self.assertEqual(toolpath_bbox(segments), (0.0, -3.0, 0.2, 4.0, 5.0, 1.5))

    def test_bbox_of_nothing_is_none(self):
        self.assertIsNone(toolpath_bbox([]))


if __name__ == "__main__":
    unittest.main()
