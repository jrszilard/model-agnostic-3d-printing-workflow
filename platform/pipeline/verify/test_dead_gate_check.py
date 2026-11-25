"""Tests for dead_gate_check.py.

The fixtures are the three real defects, reduced to their smallest reproducing shape and named
after the source they came from, plus the negatives that keep the checker usable. A checker that
reports a legitimate idiom gets an allow-list bolted on and then gets ignored, so the
`StaysQuiet` cases matter as much as the `Fires` ones.

Each rule carries a mutation below: change the fixture so the gate becomes live, and the finding
must disappear. That is the difference between "this test passes" and "this test can fail".
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dead_gate_check import check_source, find_sources, main  # noqa: E402

# bottle-lamp-carrier.py:794 — the gate keeping the anchor out of the protected nOOd channel.
R1_SOURCE = '''
ANCHOR_BOND = 0.60
ANCHOR_CHANNEL_CLEAR = 0.15
def _ANCHOR_REACH(r0, r1, frac):
    return r0 + (r1 - r0) * frac
def _channel_inner_edge(t, b, o, s):
    return -(t / 2.0)
def _anchor_reach_clear_channel(r0, r1, frac, t, b, o, s):
    return _ANCHOR_REACH(r0, r1, frac) + _channel_inner_edge(t, b, o, s) - ANCHOR_BOND
def gate(r0, r1, frac, rt, bore):
    inner = _channel_inner_edge(rt, bore, 1.25, 0.55)
    r_at = _ANCHOR_REACH(r0, r1, frac)
    reach = _anchor_reach_clear_channel(r0, r1, frac, rt, bore, 1.25, 0.55)
    protected = r_at + inner + ANCHOR_CHANNEL_CLEAR
    if reach > protected:
        raise AssertionError("anchor in the channel")
'''

# bottle-lamp-carrier.py:811 — the BL1 "rungs must reach the ribbon" regression check.
R2_SOURCE = '''
def _ANCHOR_REACH(r0, r1, frac):
    return r0 + (r1 - r0) * frac
def gate(r0, r1, frac, rt):
    r_at = r0 + (r1 - r0) * frac
    reach = _ANCHOR_REACH(r0, r1, frac)
    if reach < r_at - rt / 2.0 - 0.01:
        raise AssertionError("rung does not touch the ribbon")
'''

# balloon-lamp-sprung.py:247 — the hoop-fold exemption.
R3_SOURCE = '''
FOLD_MARGIN = 1.15
RING_R = [1, 2, 3]
RING_F = [1, 2, 3]
def fold_radius():
    return 10.0
def folds(i):
    return RING_R[i] > fold_radius() * FOLD_MARGIN
def gate():
    rf = fold_radius()
    exempt = [i for i in range(len(RING_F)) if not folds(i)]
    for i in exempt:
        if RING_R[i] > rf * FOLD_MARGIN:
            raise AssertionError("exempt but outside the bundle")
'''


def rules(source):
    return sorted(f[2] for f in check_source(source))


class Fires(unittest.TestCase):
    def test_r1_every_term_cancels(self):
        found = check_source(R1_SOURCE, "r1")
        self.assertEqual([f[2] for f in found], ["R1"])
        self.assertIn("-0.75", found[0][3])

    def test_r1_needs_the_module_constants_folded(self):
        # ANCHOR_BOND and ANCHOR_CHANNEL_CLEAR are module-level, and the difference IS them. If
        # constants stop being substituted into an inlined callee's scope the finding vanishes,
        # which is exactly how the first version of this checker missed it.
        without = R1_SOURCE.replace("ANCHOR_BOND = 0.60", "ANCHOR_BOND = float(input())")
        self.assertEqual(rules(without), [])

    def test_r2_two_names_one_expression(self):
        found = check_source(R2_SOURCE, "r2")
        self.assertEqual([f[2] for f in found], ["R2"])
        self.assertIn("r0 + (r1 - r0) * frac", found[0][3])

    def test_r3_loop_tests_its_own_selector(self):
        self.assertEqual(rules(R3_SOURCE), ["R3"])

    def test_findings_carry_a_line_number(self):
        for source in (R1_SOURCE, R2_SOURCE, R3_SOURCE):
            for finding in check_source(source):
                self.assertGreater(finding[1], 0)


class MutationsMakeTheGateLive(unittest.TestCase):
    """Make each dead gate real; the finding must go away. Without this the tests above only
    prove the checker says something, not that it says it for the right reason."""

    def test_r1_goes_quiet_when_the_difference_is_data_dependent(self):
        live = R1_SOURCE.replace("protected = r_at + inner + ANCHOR_CHANNEL_CLEAR",
                                 "protected = r_at + inner + ANCHOR_CHANNEL_CLEAR * rt")
        self.assertEqual(rules(live), [])

    def test_r2_goes_quiet_when_the_two_names_differ(self):
        live = R2_SOURCE.replace("    r_at = r0 + (r1 - r0) * frac",
                                 "    r_at = r0 + (r1 - r0) * frac * 0.5")
        self.assertEqual(rules(live), [])

    def test_r3_goes_quiet_when_the_loop_tests_something_else(self):
        live = R3_SOURCE.replace("if RING_R[i] > rf * FOLD_MARGIN:",
                                 "if RING_R[i] > rf * 2.0:")
        self.assertEqual(rules(live), [])


class StaysQuiet(unittest.TestCase):
    def test_an_ordinary_tolerance_gate(self):
        self.assertEqual(rules('''
def gate(measured, nominal, tol):
    if abs(measured - nominal) > tol:
        raise AssertionError("out of tolerance")
'''), [])

    def test_a_constant_drift_tripwire(self):
        # photo-calibration-corner: `if (TOOTH_PITCH, GROOVE_WIDTH) != (2.4, 1.8): raise`. Always
        # False by construction, and that is the POINT — it exists to fire the day someone edits a
        # qualified constant. Reporting it would teach people to ignore this checker.
        self.assertEqual(rules('''
TOOTH_PITCH = 2.4
GROOVE_WIDTH = 1.8
def gate():
    if (TOOTH_PITCH, GROOVE_WIDTH) != (2.4, 1.8):
        raise AssertionError("qualified constants drifted")
'''), [])

    def test_a_reassigned_local_is_not_substituted(self):
        # `total` has no single value, so standing one in would be a lie.
        self.assertEqual(rules('''
def gate(xs, limit):
    total = 0
    for x in xs:
        total = total + x
    if total > limit:
        raise AssertionError("over")
'''), [])

    def test_branches_do_not_leak_into_each_other(self):
        # `v` is assigned differently in each arm; the comparison in the second must not be judged
        # using the first arm's value.
        self.assertEqual(rules('''
def gate(flag, a, b, tol):
    if flag:
        v = a
        if v > b + tol:
            raise AssertionError("x")
    else:
        v = b
        if v > a + tol:
            raise AssertionError("y")
'''), [])

    def test_a_multi_statement_function_is_not_inlined(self):
        self.assertEqual(rules('''
def helper(x):
    y = x * 2
    return y
def gate(a, b):
    if helper(a) > b:
        raise AssertionError("nope")
'''), [])


class TooDeepToExpand(unittest.TestCase):
    def test_an_expression_too_deep_to_expand_is_left_unjudged_not_a_crash(self):
        """lighthouse-cap.py crashed the whole check from 2026-11-06 to 2026-11-11: a long fluent chain,
        substituted through six levels of names, overflowed the recursion limit and no generator was
        checked at all. One unjudged comparison must not cost every other file its check."""
        import dead_gate_check
        chain = "base" + "".join(".fuse(part_%d)" % i for i in range(400))
        source = "def build(base, limit):\n    a = %s\n    b = a\n    c = b\n    d = c\n" % chain + \
                 "    if d.Volume() > limit:\n        raise RuntimeError('too big')\n" + \
                 "    r_at = 3.0 + limit\n    reach = 3.0 + limit\n" + \
                 "    if reach < r_at - 0.5:\n        raise RuntimeError('dead')\n"
        del dead_gate_check.TOO_DEEP[:]
        findings = check_source(source, "deep.py")
        self.assertEqual([f[2] for f in findings], ["R2"])           # the real dead gate after it is still found
        self.assertEqual(dead_gate_check.TOO_DEEP, [("deep.py", 6)])


class RealCorpus(unittest.TestCase):
    def test_it_runs_over_this_repo_and_reports_a_line_for_every_finding(self):
        # Deliberately asserts no COUNT: the findings are real defects for a human to resolve, and
        # a test pinned to today's number goes red the day one is fixed. What must hold is that the
        # scan reaches real sources and every finding is actionable.
        root = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        sources = find_sources(root)
        self.assertGreater(len(sources), 20)
        for path in sources:
            with open(path, "r", encoding="utf-8", errors="replace") as stream:
                for finding in check_source(stream.read(), path):
                    self.assertIn(finding[2], {"R1", "R2", "R3", "PARSE"})
                    self.assertTrue(finding[3])

    def test_main_returns_nonzero_when_something_is_dead(self):
        import contextlib
        import io
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "parts", "x", "src"))
            with open(os.path.join(tmp, "parts", "x", "src", "g.py"), "w") as stream:
                stream.write(R3_SOURCE)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main(["dead_gate_check.py", tmp])
            self.assertEqual(rc, 1)
            self.assertIn("DEAD_GATE_RESULT: FAIL", buf.getvalue())

    def test_main_returns_zero_on_a_clean_tree(self):
        import contextlib
        import io
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "parts", "x", "src"))
            with open(os.path.join(tmp, "parts", "x", "src", "g.py"), "w") as stream:
                stream.write("def gate(a, b):\n    if a > b:\n        raise AssertionError('x')\n")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main(["dead_gate_check.py", tmp])
            self.assertEqual(rc, 0)
            self.assertIn("DEAD_GATE_RESULT: PASS", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
