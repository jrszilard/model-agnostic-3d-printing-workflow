import os
import tempfile
import unittest

from fitcore import (FitCoreError, assert_variants_share_core, declaration,
                     evaluate_declaration, fingerprint, write_manifest)


VISOR_V8 = [
    ("CRADLE_D", 8.10), ("WALL", 5.00), ("THROAT", 7.52), ("LEDGE", 8.33),
    ("MOUTH_DEG", -35.0), ("WIDTH", 20.62), ("JAW_PULL_IN", 3.0),
    ("PIN_LEN", 14.21), ("CORE_D", 3.07), ("BARB_D", 5.34), ("SMOOTH_D", 4.98),
    ("FIRST_BARB", 1.0), ("TIP_LEN", 2.0), ("PEG_HOLE_GAP", 9.0),
    ("HOLE_D", 6.05), ("HOLE_EDGE", 9.17), ("CBORE_D", 11.5),
    ("CBORE_DEPTH", 7.0), ("TIP_TO_AXIS", 5.60), ("N_BARBS", 6),
    ("BARB_RAMP_FRAC", 0.60), ("TIP_BLEND_R", 2.0),
]


class FitCoreTests(unittest.TestCase):
    def test_v1_preserves_the_existing_venture_identity(self):
        self.assertEqual(fingerprint(VISOR_V8), "40ccf5aca833a2cd")

    def test_mapping_order_is_canonical_and_pair_order_is_explicit(self):
        self.assertEqual(fingerprint({"b": 2, "a": 1}), fingerprint({"a": 1, "b": 2}))
        self.assertNotEqual(fingerprint([("b", 2), ("a", 1)]), fingerprint([("a", 1), ("b", 2)]))

    def test_variant_mismatch_fails(self):
        core = fingerprint(VISOR_V8)
        with self.assertRaises(FitCoreError):
            assert_variants_share_core({"v8": core, "v9": "0" * 16}, expected=core)

    def test_declaration_requires_source_algorithm_and_variant_agreement(self):
        data = declaration(VISOR_V8, {"v8": VISOR_V8, "v9": VISOR_V8},
                           source="src/fit_critical.py", regions=("cradle", "pin"))
        result = evaluate_declaration(data)
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["variants"]), 2)
        broken = dict(data); broken["variants"] = {"v9": "0" * 16}
        self.assertFalse(evaluate_declaration(broken)["passed"])

    def test_manifest_is_machine_readable(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "fit_core.json")
            data = write_manifest(path, VISOR_V8, {"v8": VISOR_V8}, "src/fit_critical.py")
            self.assertTrue(os.path.exists(path))
            self.assertEqual(data["fingerprint"], "40ccf5aca833a2cd")


if __name__ == "__main__":
    unittest.main()
