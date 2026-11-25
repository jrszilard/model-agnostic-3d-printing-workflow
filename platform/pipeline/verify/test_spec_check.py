"""Tests for the pure spec-checking logic (no FreeCAD needed).
Run:  python3 -m unittest discover -s platform/pipeline/verify -p 'test_*.py'
"""
import unittest
from spec_check import (check_value, evaluate, evaluate_cad, bbox_divergence,
                        STEP_STL_TOL_MM)


class CheckValue(unittest.TestCase):
    def test_within_tolerance_passes(self):
        ok, dev = check_value(nominal=75.0, tol=0.2, measured=75.1)
        self.assertTrue(ok)
        self.assertAlmostEqual(dev, 0.1)

    def test_outside_tolerance_fails(self):
        ok, dev = check_value(nominal=70.6, tol=0.2, measured=71.0)
        self.assertFalse(ok)
        self.assertAlmostEqual(dev, 0.4)

    def test_boundary_is_inclusive(self):
        ok, _ = check_value(nominal=100.0, tol=0.3, measured=100.3)
        self.assertTrue(ok)

    def test_negative_deviation_out_of_tol_fails(self):
        ok, dev = check_value(nominal=94.0, tol=0.3, measured=93.6)
        self.assertFalse(ok)
        self.assertAlmostEqual(dev, -0.4)


class Evaluate(unittest.TestCase):
    def _dims(self):
        return [
            {"name": "a", "nominal": 75.0, "tol": 0.2},
            {"name": "b", "nominal": 70.6, "tol": 0.2},
            {"name": "c", "nominal": 2.2, "tol": 0.2},  # e.g. a derived wall -> not measured
        ]

    def test_mixed_pass_fail_skip(self):
        rep = evaluate(self._dims(), {"a": 75.1, "b": 71.2, "c": None})
        self.assertFalse(rep["passed"])
        by = {r["name"]: r for r in rep["rows"]}
        self.assertEqual(by["a"]["status"], "PASS")
        self.assertEqual(by["b"]["status"], "FAIL")
        self.assertEqual(by["c"]["status"], "SKIP")

    def test_all_measured_pass(self):
        rep = evaluate(self._dims(), {"a": 75.0, "b": 70.5, "c": None})
        self.assertTrue(rep["passed"])
        self.assertEqual(rep["measured_count"], 2)

    def test_missing_key_is_skip_not_fail(self):
        rep = evaluate(self._dims(), {"a": 75.0})  # b, c absent entirely
        by = {r["name"]: r for r in rep["rows"]}
        self.assertEqual(by["b"]["status"], "SKIP")
        self.assertTrue(rep["passed"])

    def test_derived_dimension_without_tolerance_is_skip(self):
        rep = evaluate([{"name": "envelope", "nominal": "60 x 50 x 21"}], {"envelope": None})
        self.assertTrue(rep["passed"])
        self.assertEqual(rep["rows"][0]["status"], "SKIP")
        self.assertIsNone(rep["rows"][0]["tol"])

    def test_geometry_can_conform_while_fit_provenance_blocks(self):
        dims = [{"name": "bore", "nominal": 10.0, "tol": 0.1,
                 "provenance": "estimated", "fit_critical": True}]
        rep = evaluate(dims, {"bore": 10.0})
        self.assertTrue(rep["dimensions_passed"])
        self.assertFalse(rep["provenance"]["passed"])
        self.assertFalse(rep["passed"])


class TestCadSplit(unittest.TestCase):
    """The B-rep/mesh split. Every real part in the tree passes the hard set today (measured over
    246 STEP files); every current verify failure sits in the advisory set. These tests pin that
    the split is by evidence class, not by convenience."""

    HEALTHY = {"step_present": True, "step_valid": True, "closed": True, "no_bad_faces": True,
               "single_solid": True, "manifold": True, "no_self_intersection": True}

    def test_healthy_part_passes_and_is_proven(self):
        rep = evaluate_cad(self.HEALTHY)
        self.assertTrue(rep["passed"])
        self.assertTrue(rep["proven"])

    def test_self_intersecting_mesh_only_warns(self):
        """parts/tools/radius-gauge: documented as failing this check and printed successfully."""
        checks = dict(self.HEALTHY, no_self_intersection=False)
        rep = evaluate_cad(checks)
        self.assertTrue(rep["passed"])
        self.assertIn("no_self_intersection", rep["advisory"])

    def test_multi_solid_export_only_warns(self):
        """parts/tools/photo-calibration-corner exports 89 solids on purpose."""
        rep = evaluate_cad(dict(self.HEALTHY, single_solid=False, manifold=False))
        self.assertTrue(rep["passed"])

    def test_invalid_brep_blocks(self):
        for key in ("step_valid", "closed", "no_bad_faces"):
            with self.subTest(key=key):
                self.assertFalse(evaluate_cad(dict(self.HEALTHY, **{key: False}))["passed"])

    def test_no_step_is_unproven_not_passed(self):
        """An OpenSCAD-only part has no B-rep to check. The hard set is vacuously true, which the
        report must distinguish from proven — otherwise `all({})` silently reads as a PASS."""
        rep = evaluate_cad({"step_present": False, "manifold": True, "no_self_intersection": True})
        self.assertTrue(rep["passed"])
        self.assertFalse(rep["proven"])
        self.assertEqual(rep["hard"], {})

    def test_advisory_keys_never_reach_the_verdict(self):
        rep = evaluate_cad(dict(self.HEALTHY, step_present=False, single_solid=False,
                                manifold=False, no_self_intersection=False))
        self.assertTrue(rep["passed"])
        self.assertEqual(sorted(rep["hard"]), ["closed", "no_bad_faces", "step_valid"])


class StepStlDivergence(unittest.TestCase):
    """A part's two exports must describe the same solid. Nothing checked this until 2026-08-22,
    and three parts turned out not to — including a released one and the venture's fitted showcase."""

    def test_identical_exports_agree(self):
        self.assertTrue(bbox_divergence((10.0, 20.0, 30.0), (10.0, 20.0, 30.0))["agree"])

    def test_tessellation_noise_is_tolerated(self):
        """Triangulating a curved face shrinks its bbox by the sagitta. Measured ceiling across
        both repos: 0.0118 mm on bottle-lamp-stopper."""
        self.assertTrue(bbox_divergence((10.0, 20.0, 30.0), (10.0, 19.9882, 30.0))["agree"])

    def test_the_k1c_elbow_class_is_caught(self):
        """The real numbers: STEP 100.001 x 149.888 x 174.888 against STL 100 x 140 x 165, on a
        part marked status: released."""
        result = bbox_divergence((100.001, 149.888, 174.888), (100.0, 140.0, 165.0))
        self.assertFalse(result["agree"])
        self.assertAlmostEqual(result["worst_mm"], 9.888, places=3)

    def test_a_sub_millimetre_divergence_is_still_caught(self):
        """sun-visor-clip diverges by 0.8325 mm — small enough to look like noise, 70x the noise
        ceiling, and on the venture's only physically fit-confirmed part."""
        self.assertFalse(bbox_divergence((36.0, 20.0, 12.0), (35.1675, 20.0, 12.0))["agree"])

    def test_threshold_sits_between_the_two_populations(self):
        self.assertGreater(STEP_STL_TOL_MM, 0.0118)   # worst measured tessellation noise
        self.assertLess(STEP_STL_TOL_MM, 0.5743)      # smallest measured real divergence


if __name__ == "__main__":
    unittest.main()
