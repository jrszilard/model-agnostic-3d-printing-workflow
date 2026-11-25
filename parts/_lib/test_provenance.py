import unittest

from provenance import ProvenanceError, require_fit_provenance


class GeneratorProvenanceHelperTests(unittest.TestCase):
    def test_reexported_gate_is_dependency_free(self):
        require_fit_provenance([
            {"name": "shaft", "provenance": "standard", "fit_critical": True}])
        with self.assertRaises(ProvenanceError):
            require_fit_provenance([
                {"name": "spacing", "provenance": "placeholder", "fit_critical": True}])


if __name__ == "__main__":
    unittest.main()
