import csv
import importlib.util
import os
import sys
import tempfile
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_PATH = os.path.join(HERE, "measurements_check.py")
spec = importlib.util.spec_from_file_location("measurements_check_under_test", MODULE_PATH)
measurements_check = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = measurements_check
spec.loader.exec_module(measurements_check)


class MeasurementsCheckTest(unittest.TestCase):
    def _csv(self, fields, rows):
        temp = tempfile.NamedTemporaryFile("w", newline="", suffix=".csv", delete=False)
        self.addCleanup(lambda: os.path.exists(temp.name) and os.unlink(temp.name))
        with temp:
            writer = csv.DictWriter(temp, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return temp.name

    def test_missing_sample_join_is_an_error_even_for_empty_csv(self):
        path = self._csv(["part_id", "feature"], [])
        errors, warnings = measurements_check.check(path)
        self.assertEqual(len(errors), 1)
        self.assertIn("sample", errors[0])
        self.assertEqual(warnings, [])

    def test_legacy_log_surfaces_aggregate_metrology_debt(self):
        fields = ["sample", "nominal_mm", "measured_mm", "deviation_mm", "printer", "material"]
        rows = [
            {"sample": "", "nominal_mm": "20", "measured_mm": "19.9", "deviation_mm": "",
             "printer": "Core One", "material": "PLA"},
            {"sample": "", "nominal_mm": "", "measured_mm": "", "deviation_mm": "",
             "printer": "core-one", "material": "CAD"},
        ]
        errors, warnings = measurements_check.check(self._csv(fields, rows))
        self.assertEqual(errors, [])
        report = "\n".join(warnings)
        self.assertIn("metrology-v2 fields absent", report)
        self.assertIn("1/1 dimensional rows", report)
        self.assertIn("alias spellings", report)
        self.assertIn("non-material", report)

    def test_recorded_deviation_must_match_the_raw_values(self):
        fields = ["sample", "nominal_mm", "measured_mm", "deviation_mm", "deviation_pct",
                  "printer", "material"]
        row = {"sample": "", "nominal_mm": "20", "measured_mm": "19.9",
               "deviation_mm": "1", "deviation_pct": "5", "printer": "core-one",
               "material": "PLA"}
        errors, _ = measurements_check.check(self._csv(fields, [row]))
        report = "\n".join(errors)
        self.assertIn("deviation_mm", report)
        self.assertIn("deviation_pct", report)

    def test_v2_columns_without_values_do_not_silence_debt(self):
        fields = ["sample", "nominal_mm", "measured_mm", "deviation_mm", "printer", "material",
                  *measurements_check.METROLOGY_FIELDS]
        row = {field: "" for field in fields}
        row.update(nominal_mm="20", measured_mm="19.9", deviation_mm="-0.1",
                   printer="core-one", material="PLA")
        errors, warnings = measurements_check.check(self._csv(fields, [row]))
        self.assertEqual(errors, [])
        self.assertTrue(any("dimensional rows missing values" in warning for warning in warnings),
                        warnings)

    def test_v2_dimensional_row_can_be_complete(self):
        fields = ["sample", "nominal_mm", "measured_mm", "deviation_mm", "printer", "material",
                  *measurements_check.METROLOGY_FIELDS]
        row = {field: "" for field in fields}
        row.update(nominal_mm="20", measured_mm="19.9", deviation_mm="-0.1",
                   printer="core-one", material="PLA", instrument_id="caliper-1",
                   instrument_resolution_mm="0.01", operator="human", repeats_n="3",
                   observations_mm="19.90|19.91|19.89", uncertainty_mm="0.03",
                   uncertainty_basis="repeatability+resolution", filament_lot="lot-7",
                   dry_state="dry", ambient_c="22", ambient_rh_pct="40", gcode_sha256="a" * 64)
        errors, warnings = measurements_check.check(self._csv(fields, [row]))
        self.assertEqual(errors, [])
        self.assertFalse(any("metrology-v2" in warning or "dimensional rows" in warning
                             for warning in warnings), warnings)


if __name__ == "__main__":
    unittest.main()
