"""The adoption ledger must never break the suite it prints under.

It runs on every checkpoint and every land, after the verdict, purely to make a mechanism landing
at zero adoption visible. So the contract is narrow and absolute: always exit 0, never raise, and
count the things that actually moved.
"""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.realpath(os.path.join(HERE, "..", "..", ".."))
ADOPTION = os.path.join(ROOT, "platform", "pipeline", "adoption.py")
sys.path.insert(0, os.path.dirname(ADOPTION))


class AdoptionLedger(unittest.TestCase):
    def test_runs_clean_on_this_repo(self):
        result = subprocess.run([sys.executable, ADOPTION, ROOT], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("adoption", result.stdout)
        self.assertIn("DEBT", result.stdout)

    def test_exits_zero_on_a_tree_with_nothing_in_it(self):
        """A fresh consumer repo, or a bad path, must not turn the suite red over a count."""
        with tempfile.TemporaryDirectory() as empty:
            result = subprocess.run([sys.executable, ADOPTION, empty], text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(result.returncode, 0, result.stdout)

    def test_counts_a_spec_outside_parts(self):
        """decor/topo-coaster is a registered, verified part that does NOT live under parts/, and
        every audit count that globbed parts/*/*/spec.yaml missed it. The walk must not."""
        from adoption import _specs
        with tempfile.TemporaryDirectory() as root:
            odd = os.path.join(root, "decor", "thing")
            os.makedirs(odd)
            open(os.path.join(odd, "spec.yaml"), "w").close()
            self.assertEqual(len(_specs(root)), 1)

    def test_skips_templates_build_output_and_generated_ai_corpora(self):
        from adoption import _generators, _specs
        with tempfile.TemporaryDirectory() as root:
            for sub in ("parts/_TEMPLATE", "build/plate", "vendor/downloaded",
                        "platform/ai/corpus/generated", "platform/ai/index/generated",
                        "platform/ai/out/generated", "platform/ai/results/generated"):
                os.makedirs(os.path.join(root, sub))
                open(os.path.join(root, sub, "spec.yaml"), "w").close()
                src = os.path.join(root, sub, "src")
                os.makedirs(src)
                open(os.path.join(src, "generator.py"), "w").close()
            self.assertEqual(_specs(root), [])
            self.assertEqual(_generators(root), [])

    def test_forward_design_and_status_evidence_are_visible_without_becoming_a_gate(self):
        from adoption import collect
        with tempfile.TemporaryDirectory() as root:
            cases = {
                "draft": "status: draft\ndesign: {schema: 1, mode: originate}\ndimensions: []\n",
                "linked": "status: released\nqualification: {current: qa/iterations/i1.yaml}\ndimensions: []\n",
                "unlinked": "status: printed\ndimensions: []\n",
            }
            for name, content in cases.items():
                part = os.path.join(root, "parts", name)
                os.makedirs(part)
                with open(os.path.join(part, "spec.yaml"), "w", encoding="utf-8") as stream:
                    stream.write(content)
            rows, _, _ = collect(root)
            self.assertIn(("specs declaring Restore/Originate design intent", 1, 3), rows)
            self.assertIn(("non-draft specs naming a physical evidence record", 1, 2), rows)

    def test_probe_adoption_uses_only_fit_bearing_specs_as_denominator(self):
        from adoption import collect
        with tempfile.TemporaryDirectory() as root:
            cases = {
                "covered": "dimensions:\n  - {name: bore, fit_critical: true}\nprobes:\n  - {id: bore, expect: outside, region: {shape: box}}\n",
                "uncovered": "fit_core: {fingerprint: abc}\ndimensions: []\n",
                "plain": "dimensions:\n  - {name: width, fit_critical: false}\n",
            }
            for name, content in cases.items():
                part = os.path.join(root, "parts", name)
                os.makedirs(part)
                with open(os.path.join(part, "spec.yaml"), "w", encoding="utf-8") as stream:
                    stream.write(content)
            rows, _, _ = collect(root)
            probe_row = next(row for row in rows
                             if row[0] == "fit-bearing specs declaring B-rep probes")
            self.assertEqual(probe_row, ("fit-bearing specs declaring B-rep probes", 1, 2))


if __name__ == "__main__":
    unittest.main()
