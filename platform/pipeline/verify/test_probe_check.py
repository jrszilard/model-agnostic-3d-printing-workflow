import unittest

from probe_check import evaluate_probes, requires_probes, validate_declarations


class ValidateDeclarations(unittest.TestCase):
    def test_no_probes_is_empty(self):
        self.assertEqual(validate_declarations(None), [])

    def test_probes_root_must_be_a_list(self):
        for value in ({}, {"id": "not-a-list"}, "also-not-a-list"):
            with self.subTest(value=value):
                rows = validate_declarations(value)
                self.assertEqual(rows[0]["status"], "FAIL")
                self.assertIn("must be a list", rows[0]["message"])
        self.assertEqual(evaluate_probes("also-not-a-list", {}),
                         [{"id": "probes", "status": "FAIL",
                           "message": "probes must be a list"}])

    def test_box_geometry_is_checked(self):
        rows = validate_declarations([{"id": "p", "expect": "inside",
                                       "region": {"shape": "box", "xmin": 5.0, "xmax": 2.0}}])
        self.assertEqual(rows[0]["status"], "FAIL")
        self.assertIn("xmin", rows[0]["message"])

    def test_non_box_shape_is_rejected(self):
        rows = validate_declarations([{"id": "p", "expect": "inside",
                                       "region": {"shape": "cylinder", "center": [0, 0, 0]}}])
        self.assertIn("box", rows[0]["message"])

    def test_clear_requires_an_of_region(self):
        rows = validate_declarations([{"id": "p", "expect": "clear",
                                       "region": {"shape": "box"}}])
        self.assertIn("of:", rows[0]["message"])

    def test_spans_axis_requires_station_and_count(self):
        for probe, fragment in (
            ({"id": "p", "expect": "spans_axis", "region": {"shape": "box"}}, "axis"),
            ({"id": "p", "expect": "spans_axis", "axis": "z", "region": {"shape": "box"}}, "at"),
            ({"id": "p", "expect": "spans_axis", "axis": "z", "at": 10.0,
              "region": {"shape": "box"}}, "count"),
        ):
            with self.subTest(fragment=fragment):
                rows = validate_declarations([probe])
                self.assertTrue(any(row["status"] == "FAIL" and fragment in row["message"]
                                    for row in rows))

    def test_non_mapping_and_missing_region_fail_cleanly(self):
        rows = validate_declarations(["not-a-probe",
                                      {"id": "missing-region", "expect": "inside"}])
        self.assertEqual([row["status"] for row in rows], ["FAIL", "FAIL"])
        self.assertIn("mapping", rows[0]["message"])
        self.assertIn("region", rows[1]["message"])

    def test_ids_are_required_and_unique(self):
        probes = [{"expect": "inside", "region": {"shape": "box"}},
                  {"id": "same", "expect": "inside", "region": {"shape": "box"}},
                  {"id": "same", "expect": "outside", "region": {"shape": "box"}}]
        rows = validate_declarations(probes)
        self.assertTrue(any("non-empty string id" in row["message"] for row in rows))
        self.assertTrue(any("unique" in row["message"] for row in rows))

    def test_tolerance_must_be_finite_and_non_negative(self):
        base = {"id": "p", "expect": "inside", "region": {"shape": "box"}}
        for value in (-1, float("inf"), True):
            with self.subTest(value=value):
                rows = validate_declarations([dict(base, tol_mm3=value)])
                self.assertTrue(any("tol_mm3" in row["message"] for row in rows))


class EvaluateProbes(unittest.TestCase):
    PROBES = [{"id": "wall", "expect": "inside",
               "region": {"shape": "box", "xmin": -1, "xmax": 1}},
              {"id": "bore", "expect": "outside",
               "region": {"shape": "box", "xmin": 40, "xmax": 42}}]

    def test_whole_region_inside_and_outside_pass(self):
        geometry = {
            "wall": {"occupied_mm3": 8.0, "region_volume_mm3": 8.0},
            "bore": {"occupied_mm3": 0.0, "region_volume_mm3": 8.0},
        }
        rows = evaluate_probes(self.PROBES, geometry)
        self.assertEqual([row["status"] for row in rows], ["PASS", "PASS"])

    def test_partial_intersection_fails_both_predicates(self):
        geometry = {
            "wall": {"occupied_mm3": 4.0, "region_volume_mm3": 8.0},
            "bore": {"occupied_mm3": 4.0, "region_volume_mm3": 8.0},
        }
        rows = evaluate_probes(self.PROBES, geometry)
        self.assertEqual([row["status"] for row in rows], ["FAIL", "FAIL"])

    def test_prejudged_boolean_payload_fails_closed(self):
        """Regression: the FreeCAD side once returned predicate-satisfied booleans, which made
        every successful `outside` probe fail when the pure side read True as material present."""
        geometry = {"wall": {"measured": True}, "bore": {"measured": True}}
        rows = evaluate_probes(self.PROBES, geometry)
        self.assertEqual([row["status"] for row in rows], ["FAIL", "FAIL"])
        self.assertTrue(all("occupancy volumes" in row["message"] for row in rows))

    def test_clear_probe_respects_tolerance(self):
        probe = {"id": "joint", "expect": "clear",
                 "region": {"shape": "box"}, "of": {"region": {"shape": "box"}}}
        ok = evaluate_probes([probe], {"joint": {"measured": 0.0, "detail": "disjoint"}})
        self.assertEqual(ok[0]["status"], "PASS")
        bad = evaluate_probes([probe], {"joint": {"measured": 12.5, "detail": "merged"}})
        self.assertEqual(bad[0]["status"], "FAIL")
        self.assertIn("merged", bad[0]["message"])

    def test_spans_axis_counts_sections(self):
        probe = {"id": "taper", "expect": "spans_axis", "axis": "z", "at": 15.0, "count": 1,
                 "region": {"shape": "box"}}
        ok = evaluate_probes([probe], {"taper": {"measured": 1, "detail": "one wall"}})
        self.assertEqual(ok[0]["status"], "PASS")
        bad = evaluate_probes([probe], {"taper": {"measured": 2, "detail": "split"}})
        self.assertEqual(bad[0]["status"], "FAIL")

    def test_missing_geometry_result_is_a_failure(self):
        """A probe that cannot be evaluated protects nothing — FAIL, not SKIP."""
        probe = {"id": "p", "expect": "inside", "region": {"shape": "box"}}
        rows = evaluate_probes([probe], {})
        self.assertEqual(rows[0]["status"], "FAIL")
        self.assertIn("could not be evaluated", rows[0]["message"])


class RequiresProbes(unittest.TestCase):
    def test_fit_critical_dimension_requires_probes(self):
        self.assertTrue(requires_probes({"dimensions": [{"name": "bore", "fit_critical": True}]}))

    def test_fit_core_requires_probes(self):
        self.assertTrue(requires_probes({"fit_core": {"fingerprint": "x"}, "dimensions": []}))

    def test_joints_and_fasteners_require_probes(self):
        self.assertTrue(requires_probes({"joints": [{"id": "j"}], "dimensions": []}))
        self.assertTrue(requires_probes({"fasteners": [{"id": "f"}], "dimensions": []}))

    def test_plain_envelope_does_not(self):
        self.assertFalse(requires_probes({"dimensions": [{"name": "len", "nominal": 10.0}]}))
        self.assertFalse(requires_probes({}))


if __name__ == "__main__":
    unittest.main()
