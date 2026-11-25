import unittest

from fitcore_check import evaluate_fit_core


class FitCoreDeclarationTests(unittest.TestCase):
    def test_absent_fitcore_is_legacy_compatible(self):
        self.assertTrue(evaluate_fit_core(None)["passed"])
        self.assertFalse(evaluate_fit_core(None)["declared"])

    def test_mismatch_and_missing_source_fail(self):
        result = evaluate_fit_core({
            "algorithm": "sha256-kv-repr-v1", "fingerprint": "1" * 16,
            "variants": {"a": "2" * 16}})
        self.assertFalse(result["passed"])

    def test_matching_declaration_passes(self):
        ident = "a" * 16
        result = evaluate_fit_core({
            "algorithm": "sha256-kv-repr-v1", "fingerprint": ident,
            "source": "src/fit_critical.py", "variants": {"v8": ident, "v9": ident}})
        self.assertTrue(result["passed"])


if __name__ == "__main__":
    unittest.main()
