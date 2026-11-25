import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from spec_source_check import evaluate, evaluate_part, scan_constants, spec_dimensions


def make_part(root, dims, sources):
    spec_dims = "\n".join(
        "  - name: %s\n    nominal: %s\n    tol: %s" % (name, nominal, tol)
        for name, nominal, tol in dims)
    with open(os.path.join(root, "spec.yaml"), "w") as stream:
        stream.write("part_id: tools/test\nunits: mm\ndimensions:\n%s\n" % spec_dims)
    src = os.path.join(root, "src")
    os.makedirs(src)
    for filename, body in sources.items():
        with open(os.path.join(src, filename), "w") as stream:
            stream.write(textwrap.dedent(body))


class ScanConstants(unittest.TestCase):
    def test_module_level_numeric_constants_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "gen.py")
            with open(path, "w") as stream:
                stream.write(textwrap.dedent("""
                    PLATE = 60.0
                    NEG = -2.5
                    FLAG = True
                    NAME = "sixty"
                    computed = 60.0 * 2
                    def build():
                        LOCAL = 99.0
                        return LOCAL
                """))
            found = scan_constants(path)
            self.assertEqual(found["plate"][0], 60.0)
            self.assertEqual(found["neg"][0], -2.5)
            self.assertNotIn("flag", found)
            self.assertNotIn("name", found)
            self.assertNotIn("computed", found)
            self.assertNotIn("local", found)

    def test_last_definition_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "gen.py")
            with open(path, "w") as stream:
                stream.write("WIDTH = 10.0\nWIDTH = 12.0\n")
            self.assertEqual(scan_constants(path)["width"][0], 12.0)


class EvaluatePart(unittest.TestCase):
    def test_matching_constant_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_part(tmp, [("plate_length", 60.0, 0.2)], {"gen.py": "PLATE_LENGTH = 60.05\n"})
            result = evaluate_part(tmp)
            self.assertEqual(result["checked"], 1)
            self.assertEqual(result["conflicts"], [])

    def test_contradicting_constant_is_a_conflict(self):
        """The card-tower failure: source 118.0 vs spec nominal 110.10."""
        with tempfile.TemporaryDirectory() as tmp:
            make_part(tmp, [("bolt_square", 110.10, 0.3)], {"gen.py": "BOLT_SQUARE = 118.0\n"})
            result = evaluate_part(tmp)
            self.assertEqual(len(result["conflicts"]), 1)
            self.assertIn("110.1", result["conflicts"][0]["message"])

    def test_unmatched_dimension_is_not_a_finding(self):
        """Derived or spec-read params are legitimate; no fuzzy matching by design."""
        with tempfile.TemporaryDirectory() as tmp:
            make_part(tmp, [("bore", 10.0, 0.1)], {"gen.py": "UNRELATED = 999.0\n"})
            result = evaluate_part(tmp)
            self.assertEqual(result["checked"], 0)
            self.assertEqual(result["conflicts"], [])

    def test_default_tolerance_is_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_part(tmp, [("width", 10.0, None)], {"gen.py": "WIDTH = 10.001\n"})
            with open(os.path.join(tmp, "spec.yaml")) as stream:
                text = stream.read().replace("tol: None", "")
            with open(os.path.join(tmp, "spec.yaml"), "w") as stream:
                stream.write(text)
            result = evaluate_part(tmp)
            self.assertEqual(len(result["conflicts"]), 1)

    def test_revision_subdirs_are_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_part(tmp, [("height", 30.0, 0.1)], {})
            nested = os.path.join(tmp, "src", "r2")
            os.makedirs(nested)
            with open(os.path.join(nested, "gen.py"), "w") as stream:
                stream.write("HEIGHT = 31.0\n")
            self.assertEqual(len(evaluate_part(tmp)["conflicts"]), 1)


class EvaluateRoot(unittest.TestCase):
    def test_root_scans_every_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, "parts", "tools", "a")
            b = os.path.join(tmp, "parts", "tools", "b")
            os.makedirs(a)
            os.makedirs(b)
            make_part(a, [("x", 1.0, 0.1)], {"gen.py": "X = 1.0\n"})
            make_part(b, [("y", 2.0, 0.1)], {"gen.py": "Y = 5.0\n"})
            result = evaluate(tmp)
            self.assertEqual(result["parts"], 2)
            self.assertEqual(len(result["conflicts"]), 1)
            self.assertFalse(result["passed"])

    def test_single_part_dir_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_part(tmp, [("x", 1.0, 0.1)], {"gen.py": "X = 1.0\n"})
            self.assertTrue(evaluate(tmp)["passed"])

    def test_ratchet_entry_turns_one_known_conflict_into_debt(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_part(tmp, [("socket_h", 8.0, 0.2)], {"gen.py": "SOCKET_H = 10.8\n"})
            entry = "%s::socket_h" % os.path.relpath(tmp, tmp)
            allow = os.path.join(tmp, ".spec-source.allow")
            with open(allow, "w") as stream:
                stream.write("%s  # source is newer; spec to be reconciled\n" % entry)
            result = evaluate(tmp)
            self.assertTrue(result["passed"])
            self.assertEqual(result["conflicts"], [])
            self.assertEqual(len(result["debt"]), 1)

    def test_ratchet_entry_never_hides_a_new_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_part(tmp, [("socket_h", 8.0, 0.2), ("bore", 3.0, 0.1)],
                      {"gen.py": "SOCKET_H = 10.8\nBORE = 9.9\n"})
            allow = os.path.join(tmp, ".spec-source.allow")
            with open(allow, "w") as stream:
                stream.write("%s::socket_h\n" % os.path.relpath(tmp, tmp))
            result = evaluate(tmp)
            self.assertFalse(result["passed"])
            self.assertEqual([row["name"] for row in result["conflicts"]], ["bore"])
            self.assertEqual([row["name"] for row in result["debt"]], ["socket_h"])


class SpecDimensions(unittest.TestCase):
    def test_non_numeric_nominals_are_skipped(self):
        dims = spec_dimensions({"dimensions": [
            {"name": "a", "nominal": 1.0, "tol": 0.1},
            {"name": "b", "nominal": "derived"},
            {"name": "c", "nominal": True},
        ]})
        self.assertEqual(list(dims), ["a"])


if __name__ == "__main__":
    unittest.main()
