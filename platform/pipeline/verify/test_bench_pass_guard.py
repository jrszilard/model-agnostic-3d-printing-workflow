import os
import subprocess
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.realpath(os.path.join(HERE, "..", "..", ".."))
BENCH = os.path.join(ROOT, "platform", "bench.sh")


class BenchPhysicalPassGuardTests(unittest.TestCase):
    def test_agent_or_unconfirmed_call_stops_before_evidence_or_branch_logic(self):
        env = os.environ.copy(); env.pop("CONFIRMED", None)
        result = subprocess.run([BENCH, "passed", "synthetic note"], cwd=ROOT, env=env,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(result.returncode, 9, result.stdout)
        self.assertIn("human's to type", result.stdout)
        self.assertIn("<qa-record>", result.stdout)


if __name__ == "__main__":
    unittest.main()
