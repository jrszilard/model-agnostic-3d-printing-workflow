"""Tests for the joints: declaration gate (no FreeCAD, no cadquery needed).
Run:  python3 -m unittest discover -s platform/pipeline/verify -p 'test_*.py'
"""
import unittest

from joint_check import evaluate_joints

PLA = {"printer": "core-one", "material": "PLA", "nozzle": 0.4, "layer_h": 0.20}
PCTG = {"printer": "core-one", "material": "PCTG", "nozzle": 0.4, "layer_h": 0.20}


def joint(**kw):
    base = {"id": "j1", "sample": "TK12", "count": 2, "pitch": 14.0, "context": PLA,
            "evaluation": {"physical_gate": "insert, seat, remove x10",
                           "source_assertion": "containment_1.0"}}
    base.update(kw)
    return [base]


def statuses(report):
    return {r["id"]: r["status"] for r in report["rows"]}


class MissingSection(unittest.TestCase):
    def test_absent_joints_is_pass(self):
        rep = evaluate_joints(None)
        self.assertTrue(rep["passed"])
        self.assertEqual(rep["declared_count"], 0)

    def test_non_list_fails(self):
        self.assertFalse(evaluate_joints({"sample": "TK12"})["passed"])


class ForeignKey(unittest.TestCase):
    def test_known_sample_passes(self):
        rep = evaluate_joints(joint())
        self.assertTrue(rep["passed"], rep["rows"])

    def test_unknown_sample_fails(self):
        rep = evaluate_joints(joint(sample="TK99"))
        self.assertFalse(rep["passed"])
        self.assertEqual(rep["rows"][0]["rule"], "R4")

    def test_superseded_sample_fails_with_replacement(self):
        rep = evaluate_joints(joint(sample="QV5"))
        self.assertFalse(rep["passed"])
        self.assertIn("VC05", rep["rows"][0]["message"])

    def test_rejected_sample_fails(self):
        self.assertFalse(evaluate_joints(joint(sample="VDF10"))["passed"])

    def test_duplicate_ids_fail(self):
        j = joint() + joint()
        self.assertFalse(evaluate_joints(j)["passed"])


class MaterialAxis(unittest.TestCase):
    """The headline: PLA numbers must not silently become PCTG numbers."""

    def test_wrong_material_without_coupon_fails(self):
        rep = evaluate_joints(joint(context=PCTG))
        self.assertFalse(rep["passed"])
        self.assertIn("do not transfer", rep["rows"][0]["message"])

    def test_wrong_material_with_coupon_warns_but_passes(self):
        rep = evaluate_joints(joint(context=PCTG, evaluation={
            "physical_gate": "insert/remove", "coupon": "tk-pctg-r1",
            "source_assertion": "containment_1.0"}))
        self.assertTrue(rep["passed"], rep["rows"])
        self.assertEqual(statuses(rep)["j1"], "WARN")

    def test_unknown_material_fails(self):
        bad = dict(PLA, material="NYLON")
        self.assertFalse(evaluate_joints(joint(context=bad))["passed"])

    def test_retired_printer_warns(self):
        rep = evaluate_joints(joint(context=dict(PLA, printer="k1c"), evaluation={
            "physical_gate": "g", "coupon": "legacy", "source_assertion": "a"}))
        self.assertTrue(rep["passed"], rep["rows"])


class Orientation(unittest.TestCase):
    def test_orientation_change_without_coupon_fails(self):
        rep = evaluate_joints(joint(orientation="vertical"))
        self.assertFalse(rep["passed"])
        self.assertIn("R2", rep["rows"][0]["message"])

    def test_orientation_change_with_coupon_warns(self):
        rep = evaluate_joints(joint(orientation="vertical", evaluation={
            "physical_gate": "g", "coupon": "vo-r3", "source_assertion": "a"}))
        self.assertTrue(rep["passed"], rep["rows"])


class RuleR1FaceInterference(unittest.TestCase):
    """R1 as corrected by the VD R3 bench result: the quantity is ridge amp minus the MATING-FACE
    gap. The joint's depth clearance is a different surface pair and creates no face room."""

    def test_open_lap_wave_reused_captured_fails(self):
        rep = evaluate_joints(joint(sample="VOZ30E", retention="FXW", count=2,
                                    evaluation={"physical_gate": "g", "coupon": "vd-r3",
                                                "source_assertion": "a"}))
        self.assertFalse(rep["passed"])
        self.assertIn("face_gap", rep["rows"][0]["message"])

    def test_the_amplitude_that_jammed_is_blocked_outright(self):
        """VW20 stuck halfway in both VOZ30W and VOZ40W; it must not reach another part."""
        for female in ("VOZ30E",):
            rep = evaluate_joints(joint(sample=female, retention="VW20", count=2,
                                        evaluation={"physical_gate": "g", "coupon": "vd-r3",
                                                    "source_assertion": "a"}))
            self.assertFalse(rep["passed"], female)
            self.assertIn("rejected", rep["rows"][0]["message"])

    def test_the_two_failed_captured_trains_stay_blocked(self):
        """R4 qualified VW20E; the long train and the open-lap amplitude remain refused."""
        for ret in ("FXW", "VW20"):
            for female in ("VOZ30E",):
                rep = evaluate_joints(joint(sample=female, retention=ret, count=2,
                                            retention_location="captured",
                                            evaluation={"physical_gate": "g", "coupon": "c",
                                                        "source_assertion": "a"}))
                self.assertFalse(rep["passed"], "%s in %s" % (ret, female))

    def test_non_retention_sample_as_retention_fails(self):
        self.assertFalse(evaluate_joints(joint(sample="VDF40", retention="TK10"))["passed"])

    def test_shoulder_teeth_are_exempt_from_r1(self):
        """QZ sits OUTSIDE the dovetail on compression shoulders. Its 0.20 depth against QH2's
        0.10 depth clearance is the PASS_PERFECT corner, not a violation."""
        rep = evaluate_joints(joint(sample="QH2", retention="QZ", count=1))
        self.assertTrue(rep["passed"], rep["rows"])
        self.assertIn("outside", rep["rows"][0]["message"])

    def test_a_wave_declared_on_an_open_lap_is_exempt(self):
        rep = evaluate_joints(joint(sample="QH2", retention="FXW", count=1,
                                    retention_location="shoulder"))
        self.assertTrue(rep["passed"], rep["rows"])

    def test_the_same_wave_declared_captured_still_fails(self):
        rep = evaluate_joints(joint(sample="QH2", retention="FXW", count=1,
                                    retention_location="captured"))
        self.assertFalse(rep["passed"])

    def test_bad_retention_location_fails(self):
        self.assertFalse(evaluate_joints(
            joint(sample="QH2", retention="QZ", retention_location="sideways"))["passed"])


class Layout(unittest.TestCase):
    """count/pitch is the double-vs-triple axis; it must fit the part."""

    def test_triple_fits_a_wide_span(self):
        rep = evaluate_joints(joint(sample="TF", count=3, pitch=14.0, span=40.0))
        self.assertTrue(rep["passed"], rep["rows"])

    def test_triple_overflows_a_narrow_span(self):
        rep = evaluate_joints(joint(sample="TF", count=3, pitch=14.0, span=28.0))
        self.assertFalse(rep["passed"])
        self.assertIn("needs", rep["rows"][0]["message"])

    def test_zero_count_fails(self):
        self.assertFalse(evaluate_joints(joint(count=0))["passed"])


class Evidence(unittest.TestCase):
    def test_missing_physical_gate_fails(self):
        self.assertFalse(evaluate_joints(joint(evaluation={}))["passed"])

    def test_coupon_gate_sample_needs_a_coupon(self):
        rep = evaluate_joints(joint(sample="TR20", count=2))
        self.assertFalse(rep["passed"])
        self.assertIn("coupon", rep["rows"][0]["message"])

    def test_missing_source_assertion_warns_only(self):
        rep = evaluate_joints(joint(evaluation={"physical_gate": "g"}))
        self.assertTrue(rep["passed"], rep["rows"])
        self.assertEqual(statuses(rep)["j1"], "WARN")


if __name__ == "__main__":
    unittest.main()


class RulesFireAtTheDecisionPoint(unittest.TestCase):
    """A gate that only refuses teaches nothing. Findings cite the learned rule AND the trap —
    the naive fix someone would otherwise reach for."""

    def test_findings_cite_the_governing_rule(self):
        cases = [(joint(sample="TK99"), "R4"),
                 (joint(context=PCTG), "R3"),
                 (joint(orientation="vertical"), "R2")]
        for j, rule in cases:
            rep = evaluate_joints(j)
            self.assertEqual(rep["rows"][0].get("rule"), rule, rep["rows"])

    def test_a_cited_finding_carries_the_trap(self):
        rep = evaluate_joints(joint(orientation="vertical"))
        trap = rep["rows"][0].get("trap", "")
        self.assertIn("Reuse a clearance", trap)

    def test_r1_violation_cites_r1(self):
        rep = evaluate_joints(joint(sample="VOZ30E", retention="FXW", count=2,
                                    evaluation={"physical_gate": "g", "coupon": "c",
                                                "source_assertion": "a"}))
        self.assertEqual(rep["rows"][0].get("rule"), "R1")

    def test_no_shippable_sample_currently_hides_an_unrecorded_measure(self):
        """The gate warns on UNKNOWN measures as a safety net for future samples. Today the
        only samples carrying them (QH4, QV4/6/8) are all superseded, so they are refused
        earlier and more firmly — assert that invariant rather than a reachable warning."""
        import sys, os
        sys.path.insert(0, os.path.abspath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "parts", "_lib")))
        from joints import SAMPLES, UNKNOWN
        for s in SAMPLES.values():
            if s.usable:
                blank = [k for k, v in s.measures.items() if v is UNKNOWN]
                self.assertEqual(blank, [], "%s is shippable with unrecorded %s" % (s.id, blank))


class R4Qualified(unittest.TestCase):
    """2026-07-25: VOM4 x VOZ30E fit best. The short end train is now a legal configuration."""

    def test_the_qualified_pair_passes_the_gate(self):
        rep = evaluate_joints(joint(sample="VOZ30E", retention="VW20E", count=2,
                                    evaluation={"physical_gate": "seat, retain, hand-remove",
                                                "source_assertion": "seat interference 0.0"}))
        self.assertTrue(rep["passed"], rep["rows"])

    def test_the_same_amplitude_over_a_long_train_still_fails(self):
        rep = evaluate_joints(joint(sample="VOZ30E", retention="VW20", count=2,
                                    evaluation={"physical_gate": "g", "coupon": "c",
                                                "source_assertion": "a"}))
        self.assertFalse(rep["passed"])

    def test_the_failure_advises_shortening_not_softening(self):
        """The useful half of the message: the fix is fewer stations, not less amplitude."""
        import sys, os
        sys.path.insert(0, os.path.abspath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "parts", "_lib")))
        from joints import SAMPLES, check_retention
        _, msg = check_retention(SAMPLES["VDF40"], SAMPLES["VW20"], location="captured")
        self.assertIn("shorten the train", msg)
