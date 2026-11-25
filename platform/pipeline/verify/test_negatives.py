import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

LIB = Path(__file__).resolve().parent

GENERATOR = '''
import importlib.util
from pathlib import Path
WIDTH = 5.0   # the slot
DEPTH = WIDTH * 2                      # derived when the module is executed
_spec = importlib.util.spec_from_file_location("dep", Path(__file__).resolve().parent / "dep.py")
dep = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(dep)

def checks(limit=WIDTH, sections=None):    # a default bound when the function is defined
    if sections == ["never"]:
        return ["skipped"]
    if DEPTH > 12:
        raise RuntimeError("too deep: %.1f" % DEPTH)
    if limit < 4:
        raise RuntimeError("too narrow: %.1f" % limit)
    if dep.LIMIT < 10:
        raise RuntimeError("the dependency's limit is %d" % dep.LIMIT)
    return ["ok"]

if __name__ == "__main__":
    raise SystemExit("main must not run under the harness")
'''

NEGATIVES = '''
import sys
sys.path.insert(0, %(lib)r)
from negatives import Negative, main
SOURCE = "../src/gen.py"
def run(module, case):
    module.checks(sections=None if case is None else case.sections)
CASES = [
%(cases)s
]
if __name__ == "__main__":
    main(__file__)
'''

ALL = '''
    Negative("derived constant", old="WIDTH = 5.0 ", new="WIDTH = 7.0 ", expect=["too deep"]),
    Negative("default argument", old="WIDTH = 5.0 ", new="WIDTH = 3.0 ", expect="too narrow"),
    Negative("in a dependency", old="LIMIT = 12", new="LIMIT = 8", expect=["dependency's limit"], file="../src/dep.py"),
'''


class NegativesHarnessTests(unittest.TestCase):
    def tree(self, cases, generator=GENERATOR):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (root / "src").mkdir(); (root / "qa").mkdir()
        (root / "src" / "gen.py").write_text(generator)
        (root / "src" / "dep.py").write_text("LIMIT = 12\n")
        (root / "qa" / "negatives.py").write_text(NEGATIVES % {"lib": str(LIB), "cases": cases})
        return root

    def harness(self, root, *args):
        return subprocess.run([sys.executable, "-B", str(root / "qa" / "negatives.py"), *args],
                              capture_output=True, text=True)

    def test_values_broken_in_the_text_reach_derived_constants_defaults_and_dependencies(self):
        root = self.tree(ALL)
        done = self.harness(root, "-j", "3")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("3 of 3 refused for the stated reason", done.stdout)
        self.assertEqual(done.stdout.count("CAUGHT"), 3)
        self.assertIn("too deep: 14.0", done.stdout)
        self.assertIn("too narrow: 3.0", done.stdout)

    def test_nothing_is_written_beside_the_source(self):
        root = self.tree(ALL)
        before = sorted(p.name for p in (root / "src").rglob("*"))
        self.harness(root)
        self.assertEqual(sorted(p.name for p in (root / "src").rglob("*")), before)
        self.assertEqual((root / "src" / "gen.py").read_text(), GENERATOR)
        self.assertEqual((root / "src" / "dep.py").read_text(), "LIMIT = 12\n")

    def test_a_missed_control_a_wrong_reason_and_a_stale_one_each_fail_the_run(self):
        root = self.tree('''
    Negative("harmless change", old="WIDTH = 5.0 ", new="WIDTH = 5.5 ", expect=["too deep"]),
    Negative("refused for another reason", old="WIDTH = 5.0 ", new="WIDTH = 7.0 ", expect=["too narrow"]),
    Negative("text no longer in the source", old="HEIGHT = 2.0", new="HEIGHT = 9.0", expect=["too tall"]),
    Negative("text that occurs twice", old="WIDTH", new="WIDE", expect=["x"]),
    Negative("breaks the syntax", old="DEPTH = WIDTH * 2", new="DEPTH = WIDTH * (2", expect=["too deep"]),
''')
        done = self.harness(root)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        rows = {line.split()[0]: line.split()[1] for line in done.stdout.splitlines() if line[:3].strip().isdigit()}
        self.assertEqual(rows, {"0": "MISSED", "1": "OTHER", "2": "STALE", "3": "STALE", "4": "OTHER"})
        self.assertIn("0 of 5 refused", done.stdout)

    def test_a_source_that_fails_as_it_is_stops_everything(self):
        root = self.tree(ALL, generator=GENERATOR.replace("WIDTH = 5.0 ", "WIDTH = 9.0 "))
        done = self.harness(root)
        self.assertEqual(done.returncode, 2)
        self.assertIn("does NOT pass its own checks", done.stdout)
        self.assertNotIn("CAUGHT", done.stdout)

    def test_only_list_and_sections(self):
        root = self.tree(ALL + '    Negative("sections reach run()", old="WIDTH = 5.0 ", new="WIDTH = 7.0 ", '
                               'expect=["too deep"], sections=["never"]),\n')
        listed = self.harness(root, "--list")
        self.assertEqual(len(listed.stdout.splitlines()), 4)
        one = self.harness(root, "--only", "1")
        self.assertEqual(one.returncode, 0, one.stdout + one.stderr)
        self.assertIn("1 of 1 refused", one.stdout)
        skipped = self.harness(root, "--only", "3")          # its section skips the check, so the control is MISSED
        self.assertEqual(skipped.returncode, 1)
        self.assertIn("MISSED", skipped.stdout)

    def test_a_negative_must_say_what_the_refusal_mentions(self):
        sys.path.insert(0, str(LIB))
        from negatives import Negative
        with self.assertRaises(ValueError):
            Negative("no reason given", old="a", new="b", expect=[])


if __name__ == "__main__":
    unittest.main()
