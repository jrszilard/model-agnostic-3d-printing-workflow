import datetime
import os
import tempfile
import unittest

from dim_provenance import (FIT_TRUSTED, ProvenanceError, evaluate_provenance, evaluate_reference,
                            is_fit_bearing, read_allow, require_fit_provenance)


class DimensionProvenanceTests(unittest.TestCase):
    def test_measured_and_standard_can_control_fit(self):
        result = evaluate_provenance([
            {"name": "bore", "provenance": "measured", "fit_critical": True},
            {"name": "hook", "provenance": "standard", "fit_critical": True},
        ])
        self.assertTrue(result["passed"])
        self.assertEqual(result["counts"]["measured"], 1)
        self.assertEqual(result["counts"]["standard"], 1)

    def test_estimated_or_placeholder_fit_dimension_blocks(self):
        for provenance in ("estimated", "placeholder"):
            with self.subTest(provenance=provenance):
                result = evaluate_provenance([
                    {"name": "spacing", "provenance": provenance, "fit_critical": True}])
                self.assertFalse(result["passed"])

    def test_missing_provenance_blocks_only_when_fit_critical(self):
        self.assertTrue(evaluate_provenance([{"name": "cosmetic"}])["passed"])
        self.assertFalse(evaluate_provenance(
            [{"name": "mate", "fit_critical": True}])["passed"])

    def test_placeholder_is_allowed_for_review_only_geometry(self):
        self.assertTrue(evaluate_provenance([
            {"name": "crest", "provenance": "placeholder", "fit_critical": False}])["passed"])

    def test_unknown_value_and_non_boolean_flag_fail_closed(self):
        self.assertFalse(evaluate_provenance([
            {"name": "x", "provenance": "confirmed"}])["passed"])
        self.assertFalse(evaluate_provenance([
            {"name": "x", "provenance": "measured", "fit_critical": "yes"}])["passed"])

    def test_generator_helper_raises_with_dimension_names(self):
        with self.assertRaisesRegex(ProvenanceError, "spacing"):
            require_fit_provenance([
                {"name": "spacing", "provenance": "estimated", "fit_critical": True}],
                "fixture")


class MeasurementDebt(unittest.TestCase):
    """The state that breaks the originate deadlock: a fit-critical nominal may be declared
    unproven, but only as debt someone is on the hook for. Every test here is about what it
    costs to make that declaration, because a debt state nobody has to repay is just a
    placeholder with a nicer name."""

    TODAY = datetime.date(2026, 9, 6)

    def debt(self, **overrides):
        row = {"name": "seat_thickness", "provenance": "pending-measurement", "fit_critical": True,
               "closes_with": "PLA prototype, six-receiver plate", "next_review": "2026-10-04"}
        row.update(overrides)
        return [row]

    def evaluate(self, dims):
        return evaluate_provenance(dims, today=self.TODAY)

    def test_declared_debt_does_not_fail_and_is_reported_as_debt(self):
        result = self.evaluate(self.debt())
        self.assertTrue(result["passed"])
        self.assertEqual(result["debt"], ["seat_thickness"])
        self.assertEqual(result["rows"][0]["status"], "DEBT")

    def test_debt_is_never_trusted(self):
        """It must not join measured/standard: the row passes the gate and the NUMBER is still
        unproven. Anything that reads FIT_TRUSTED to decide what a nominal may control has to
        keep excluding it."""
        self.assertNotIn("pending-measurement", FIT_TRUSTED)
        self.assertEqual(self.evaluate(self.debt())["rows"][0]["provenance"], "pending-measurement")

    def test_undated_debt_fails_exactly_like_a_placeholder(self):
        for missing in ({"next_review": None}, {"closes_with": None}, {"closes_with": "   "}):
            with self.subTest(missing=missing):
                result = self.evaluate(self.debt(**missing))
                self.assertFalse(result["passed"])
                self.assertEqual(result["debt"], [])

    def test_overdue_debt_returns_to_fail(self):
        """The whole safeguard. Debt that can be parked forever is worse than no debt state,
        because it launders an unmeasured nominal into a permanent pass."""
        result = self.evaluate(self.debt(next_review="2026-09-05"))
        self.assertFalse(result["passed"])
        self.assertIn("overdue", result["rows"][0]["message"])

    def test_due_today_is_still_open(self):
        self.assertTrue(self.evaluate(self.debt(next_review="2026-09-06"))["passed"])

    def test_yaml_date_object_is_accepted_like_an_iso_string(self):
        """An unquoted YAML date parses to datetime.date, a quoted one to str. A spec author
        should not have to know which one the loader handed us."""
        self.assertTrue(self.evaluate(self.debt(next_review=datetime.date(2026, 10, 4)))["passed"])

    def test_unparseable_date_fails_rather_than_being_guessed(self):
        for value in ("next month", "04-10-2026", 20261004):
            with self.subTest(value=value):
                self.assertFalse(self.evaluate(self.debt(next_review=value))["passed"])

    def test_non_fit_critical_pending_needs_no_ceremony(self):
        """The closes_with/next_review demand exists because the dimension controls a fit.
        Without fit_critical there is nothing to be in debt about."""
        self.assertTrue(self.evaluate([
            {"name": "crest", "provenance": "pending-measurement", "fit_critical": False}])["passed"])

    def test_debt_satisfies_the_fit_bearing_recorded_rule(self):
        dims = self.debt()
        self.assertTrue(evaluate_provenance(dims, require_recorded=True, today=self.TODAY)["passed"])

    def test_generator_helper_still_builds_a_part_carrying_debt(self):
        """Generating the CAD is exactly what you must do to print the article that closes the
        debt, so require_fit_provenance must not raise on it.

        The helper reads the real clock, so the debt here is dated from it. The fixture's fixed
        2026-10-04 made this test fail from the day after, and the suite stayed red on it until
        2026-11-11: an overdue debt is refused, which is the rule working and is asserted below."""
        ahead = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
        require_fit_provenance(self.debt(next_review=ahead), "fixture")
        behind = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        with self.assertRaises(Exception) as caught:
            require_fit_provenance(self.debt(next_review=behind), "fixture")
        self.assertIn("overdue", str(caught.exception))


class FitBearingRule(unittest.TestCase):
    """Item 07: a spec that claims a mate must say where its numbers came from.

    Off by default because verify.py evaluates every part on every run and 15 legacy parts carry
    144 unrecorded dimensions between them. The handoff turns it on, which is where a plate is
    actually approved.
    """

    UNSOURCED = [{"name": "bore", "nominal": 10.0, "tol": 0.1}]

    def test_unrecorded_is_tolerated_by_default(self):
        self.assertTrue(evaluate_provenance(self.UNSOURCED)["passed"])

    def test_unrecorded_fails_when_required(self):
        result = evaluate_provenance(self.UNSOURCED, require_recorded=True)
        self.assertFalse(result["passed"])
        self.assertIn("must record provenance", result["rows"][0]["message"])

    def test_any_recorded_value_satisfies_the_rule(self):
        """The rule asks for an ANSWER, not a good one. `placeholder` is a legitimate answer;
        `fit_critical: true` is the separate, stricter gate that rejects it."""
        for value in ("measured", "standard", "estimated", "placeholder"):
            with self.subTest(value=value):
                dims = [dict(self.UNSOURCED[0], provenance=value)]
                self.assertTrue(evaluate_provenance(dims, require_recorded=True)["passed"])

    def test_fit_critical_still_rejects_untrusted_even_when_recorded(self):
        dims = [dict(self.UNSOURCED[0], provenance="placeholder", fit_critical=True)]
        self.assertFalse(evaluate_provenance(dims, require_recorded=True)["passed"])


class FitBearingDetection(unittest.TestCase):
    def test_declared_mate_is_fit_bearing(self):
        for key in ("fits", "joints", "fasteners"):
            with self.subTest(key=key):
                self.assertTrue(is_fit_bearing({key: [{"name": "x"}]}))

    def test_empty_list_is_not_a_claim(self):
        """`bom: []` and `fits: []` are boilerplate, not an assertion that the part mates."""
        self.assertFalse(is_fit_bearing({"fits": [], "joints": None}))
        self.assertFalse(is_fit_bearing({}))


class ReferenceRelationship(unittest.TestCase):
    """A3: verification follows the region's relationship to a reference, not the repo.
    Opt-in: a dimension with none of the new fields is UNDECLARED and stays green."""

    def test_undeclared_dimensions_stay_green(self):
        result = evaluate_reference([{"name": "bore"}])
        self.assertTrue(result["passed"])
        self.assertEqual(result["declared"], 0)
        self.assertEqual(result["rows"][0]["status"], "UNDECLARED")

    def test_replicate_and_originate_declarations_pass(self):
        result = evaluate_reference([
            {"name": "bore", "reference": "replicate"},
            {"name": "rib", "reference": "originate"},
        ])
        self.assertTrue(result["passed"])
        self.assertEqual(result["declared"], 2)

    def test_unknown_reference_fails_closed(self):
        self.assertFalse(evaluate_reference(
            [{"name": "x", "reference": "sometimes"}])["passed"])

    def test_deviation_needs_closed_kind_and_reason(self):
        bad = evaluate_reference([{"name": "len", "deviation": {"kind": "intentional"}}])
        self.assertFalse(bad["passed"])
        self.assertIn("deviation.kind", bad["rows"][0]["message"])
        bad2 = evaluate_reference([{"name": "len", "deviation": {"kind": "process"}}])
        self.assertFalse(bad2["passed"])
        self.assertIn("reason", bad2["rows"][0]["message"])

    def test_valid_correction_deviation_passes(self):
        result = evaluate_reference([{"name": "len", "reference": "deviate",
                                      "deviation": {"kind": "correction", "reason": "OEM interferes"}}])
        self.assertTrue(result["passed"])

    def test_replicate_with_deviation_block_is_a_contradiction(self):
        result = evaluate_reference([{"name": "len", "reference": "replicate",
                                      "deviation": {"kind": "process", "reason": "FDM draft"}}])
        self.assertFalse(result["passed"])

    def test_unavailable_is_debt_and_needs_a_review_date(self):
        missing = evaluate_reference([{"name": "x", "deviation": {"kind": "unavailable",
                                                                   "reason": "no donor"}}])
        self.assertFalse(missing["passed"])
        dated = evaluate_reference([{"name": "x", "deviation": {"kind": "unavailable",
                                                                 "reason": "no donor",
                                                                 "next_review": "2026-12-01"}}])
        self.assertTrue(dated["passed"])

    def test_oem_nominal_without_deviation_is_a_contradiction(self):
        self.assertFalse(evaluate_reference(
            [{"name": "len", "oem_nominal": 37.01}])["passed"])
        self.assertTrue(evaluate_reference(
            [{"name": "len", "oem_nominal": 37.01,
              "deviation": {"kind": "correction", "reason": "see notes"}}])["passed"])

    def test_scalar_deviation_is_rejected_as_a_mapping(self):
        result = evaluate_reference([{"name": "x", "deviation": "intentional"}])
        self.assertFalse(result["passed"])
        self.assertIn("mapping", result["rows"][0]["message"])


class AllowFileParsing(unittest.TestCase):
    """generator_refs.py strips the line for the value but tests startswith('#') on the RAW line,
    so an indented comment becomes an entry and a trailing comment becomes part of the path. This
    parser must not inherit either bug."""

    def _write(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".allow", delete=False)
        self.addCleanup(os.unlink, handle.name)
        handle.write(text); handle.close()
        return handle.name

    def test_comments_blanks_and_trailing_comments(self):
        path = self._write("# header\n\n  # indented comment\n"
                           "parts/a/b/spec.yaml\n"
                           "parts/c/d/spec.yaml  # why this is debt\n")
        self.assertEqual(read_allow(path), {"parts/a/b/spec.yaml", "parts/c/d/spec.yaml"})

    def test_missing_file_is_empty_not_an_error(self):
        self.assertEqual(read_allow("/nonexistent/.spec-truth.allow"), set())


if __name__ == "__main__":
    unittest.main()
