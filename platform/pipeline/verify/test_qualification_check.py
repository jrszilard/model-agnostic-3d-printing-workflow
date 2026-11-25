import contextlib
import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

import qualification_check as qc
from provenance_fixture import fixture_producer


SHA = "a" * 64
COMMIT = "b" * 40


def restore_spec(status="draft"):
    return {
        "part_id": "test/widget", "status": status,
        "design": {
            "schema": 1, "mode": "restore", "purpose": "replace a broken locator",
            "references": [{"id": "donor-a", "role": "source",
                            "evidence": ["db:reference/donor-a"]}],
        },
        "dimensions": [{"name": "width", "nominal": 10.0, "tol": 0.1,
                        "provenance": "measured", "fit_critical": True,
                        "reference": "replicate"}],
        "acceptance": {"cad": ["single_solid"],
                       "printed": ["all_dimensions_within_tol", "fits_real_mate"]},
    }


def base_record(state="planned"):
    record = {
        "schema": 1, "iteration_id": "2026-09-04-i1", "part_id": "test/widget",
        "parent": None, "attempt_kind": "full-part", "objective": "check donor fit",
        "design_mode": "restore",
        "artifact": {
            "handoff_manifest": {"path": "build/i1/qualification_manifest.json", "sha256": SHA},
            "source": {"commit": COMMIT, "dirty": False},
            "models": [{"path": "parts/test/widget/stl/widget.stl", "geom_id": "a" * 8,
                        "sha256": SHA}],
            "spec_sha256": "b" * 64, "verify_stamp_sha256": "e" * 64,
            "verify_step_sha256": "f" * 64, "verify_report_sha256": "1" * 64,
            "gcode_sha256": "c" * 64, "project_3mf_sha256": "2" * 64,
            "slice_meta_sha256": "3" * 64, "effective_config_sha256": "d" * 64,
            "profiles": {"machine": "core-one", "process": "0.20", "filament": "PLA"},
            "slicer": {"executable": "/usr/bin/prusa-slicer",
                       "reported_by_gcode": "PrusaSlicer 2.9.6"},
            "overrides": [], "post_hooks": [],
            "rotation": {"x": 0.0, "y": 0.0, "z": 0.0},
            "support_requested": False,
            "estimate": {"filament_g": 3.5, "print_time_seconds": 600.0},
        },
        "execution": {
            "printer_id": None, "material": None, "material_brand": None,
            "filament_lot": None, "dry_state": None, "build_plate": None,
            "nozzle_mm": None, "layer_height_mm": None,
            "ambient_c": None, "ambient_rh_pct": None,
            "actual_material_g": None, "actual_print_time_minutes": None,
            "deviations": [], "post_processing": [],
        },
        "outcome": {
            "state": state, "printed_at": None, "operator": None,
            "evaluated_at": None, "evaluator": None, "mate_or_application": None,
            "checks": [
                {"id": "all_dimensions_within_tol", "result": "not-evaluated",
                 "observation": None, "evidence": []},
                {"id": "fits_real_mate", "result": "not-evaluated",
                 "observation": None, "evidence": []},
            ],
            "measurements": [],
        },
        "learning": {"failure_class": None, "observation": None,
                     "next_change": None, "promoted_sample": None},
        "attestation": None,
    }
    return record


def evaluated_failure():
    record = base_record("failed")
    record["execution"].update(passing_record()["execution"])
    record["outcome"].update({
        "printed_at": "2026-09-04T10:00:00-04:00", "operator": "Human Operator",
        "evaluated_at": "2026-09-04T11:00:00-04:00", "evaluator": "Human Evaluator",
        "mate_or_application": "donor-a physical locator",
    })
    record["outcome"]["checks"][0].update(
        result="fail", observation="0.4 mm interference", evidence=["qa/photo.jpg"])
    record["learning"].update(failure_class="fit", observation="locator interfered",
                              next_change="increase declared clearance")
    record["attestation"] = {"statement": "physical-observation", "by": "Human Evaluator",
                             "at": "2026-09-04T11:00:00-04:00"}
    return record


def passing_record():
    record = base_record("passed")
    record["execution"].update({
        "printer_id": "COREONE-1", "material": "PLA", "material_brand": "Prusament",
        "filament_lot": "spool-2026-09-a", "dry_state": "sealed until print",
        "build_plate": "satin-1", "nozzle_mm": 0.4, "layer_height_mm": 0.2,
        "ambient_c": 22.0, "ambient_rh_pct": 42.0,
        "actual_material_g": 3.7, "actual_print_time_minutes": 11.0,
    })
    record["outcome"].update({
        "printed_at": "2026-09-04T10:00:00-04:00", "operator": "Human Operator",
        "evaluated_at": "2026-09-04T11:00:00-04:00", "evaluator": "Human Evaluator",
        "mate_or_application": "donor-a physical locator",
        "measurements": [{
            "dimension": "width", "raw_readings_mm": [9.99, 10.01],
            "instrument": {"id": "CAL-1", "resolution_mm": 0.01},
            "uncertainty": {"value_mm": 0.02, "basis": "repeat spread + resolution"},
            "result": "pass",
        }],
    })
    for check in record["outcome"]["checks"]:
        check.update(result="pass", observation="criterion observed on identified print",
                     evidence=["qa/photos/i1.jpg"])
    record["learning"]["observation"] = "The identified print fit without rework."
    record["attestation"] = {"statement": "physical-observation", "by": "Human Evaluator",
                             "at": "2026-09-04T11:00:00-04:00"}
    return record


class TemplateSafetyTests(unittest.TestCase):
    def test_template_cannot_claim_a_physical_result(self):
        path = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", "..",
                                             "parts", "_TEMPLATE", "qa", "iteration.yaml"))
        with open(path) as stream: template = yaml.safe_load(stream)
        self.assertEqual(template["outcome"]["state"], "planned")
        self.assertIsNone(template["outcome"]["operator"])
        self.assertIsNone(template["outcome"]["evaluator"])
        self.assertIsNone(template["execution"]["printer_id"])
        self.assertIsNone(template["execution"]["filament_lot"])
        self.assertIsNone(template["execution"]["ambient_c"])
        self.assertIsNone(template["attestation"])
        self.assertTrue(all(row["result"] == "not-evaluated"
                            for row in template["outcome"]["checks"]))


class DesignIntentTests(unittest.TestCase):
    def test_restore_requires_source_evidence_and_explicit_relationships(self):
        spec = restore_spec()
        self.assertTrue(qc.evaluate_design(spec)["passed"])
        del spec["design"]["references"][0]["evidence"]
        del spec["dimensions"][0]["reference"]
        errors = qc.evaluate_design(spec)["errors"]
        self.assertTrue(any("evidence" in error for error in errors))
        self.assertTrue(any("must declare reference" in error for error in errors))
        empty = restore_spec(); empty["dimensions"] = []
        self.assertTrue(any("at least one replicated" in error
                            for error in qc.evaluate_design(empty)["errors"]))

    def test_originate_allows_interface_evidence_but_not_source_part_relationships(self):
        spec = restore_spec()
        spec["design"] = {
            "schema": 1, "mode": "originate", "purpose": "make a new cable guide",
            "references": [{"id": "slot-envelope", "role": "interface",
                            "evidence": ["measurements/slot.csv"]}],
        }
        spec["dimensions"][0]["reference"] = "originate"
        self.assertTrue(qc.evaluate_design(spec)["passed"])
        spec["dimensions"][0]["reference"] = "replicate"
        self.assertFalse(qc.evaluate_design(spec)["passed"])

    def test_printed_acceptance_ids_are_required_and_unique(self):
        spec = restore_spec(); spec["acceptance"]["printed"] = ["fit", "fit"]
        self.assertIn("acceptance.printed criterion ids must be unique",
                      qc.evaluate_design(spec)["errors"])


class QualificationRecordTests(unittest.TestCase):
    def test_planned_record_is_valid_and_cannot_claim_human_fields(self):
        spec, record = restore_spec(), base_record()
        self.assertTrue(qc.evaluate_record(record, spec, check_files=False)["passed"])
        record["outcome"]["operator"] = "AI"
        record["outcome"]["checks"][0].update(observation="invented", evidence=["fake"])
        record["outcome"]["measurements"] = [{"dimension": "width"}]
        record["execution"]["printer_id"] = "invented"
        record["learning"]["observation"] = "invented"
        record["attestation"] = {"statement": "physical-observation", "by": "AI", "at": "now"}
        errors = qc.evaluate_record(record, spec, check_files=False)["errors"]
        self.assertTrue(any("must leave outcome.operator null" in error for error in errors))
        self.assertTrue(any("physical execution fields" in error for error in errors))
        self.assertTrue(any("observations/evidence empty" in error for error in errors))
        self.assertTrue(any("must not contain physical measurements" in error for error in errors))
        self.assertTrue(any("observed learning fields null" in error for error in errors))
        self.assertTrue(any("must not carry" in error for error in errors))

    def test_complete_human_pass_is_consistent(self):
        result = qc.evaluate_record(passing_record(), restore_spec(), check_files=False,
                                    require_state="passed")
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(result["measurements"], {"width": "pass"})

    def test_pass_cannot_be_asserted_without_evidence_or_attestation(self):
        record = passing_record()
        record["attestation"] = None
        record["outcome"]["checks"][0]["evidence"] = []
        errors = qc.evaluate_record(record, restore_spec(), check_files=False)["errors"]
        self.assertTrue(any("physical-observation attestation" in error for error in errors))
        self.assertTrue(any("needs one or more evidence refs" in error for error in errors))

    def test_completed_record_requires_actual_process_context_and_zoned_times(self):
        record = passing_record()
        record["execution"]["filament_lot"] = None
        record["execution"]["ambient_rh_pct"] = 140
        record["outcome"]["printed_at"] = "2026-09-04 10:00"
        record["outcome"]["operator"] = "AI"
        record["outcome"]["evaluator"] = "assistant"
        record["attestation"]["by"] = "assistant"
        errors = qc.evaluate_record(record, restore_spec(), check_files=False)["errors"]
        self.assertTrue(any("execution.filament_lot" in error for error in errors))
        self.assertTrue(any("execution.ambient_rh_pct" in error for error in errors))
        self.assertTrue(any("printed_at with timezone" in error for error in errors))
        self.assertTrue(any("human operator" in error for error in errors))
        self.assertTrue(any("human identity in outcome.evaluator" in error for error in errors))
        self.assertTrue(any("human physical-observation attestation" in error for error in errors))

    def test_passing_record_cannot_hide_an_extra_failed_check(self):
        record = passing_record()
        record["outcome"]["checks"].append({
            "id": "service_cycle", "result": "fail", "observation": "cracked",
            "evidence": ["qa/photo.jpg"],
        })
        errors = qc.evaluate_record(record, restore_spec(), check_files=False)["errors"]
        self.assertTrue(any("every recorded and required" in error for error in errors))

    def test_measurement_result_is_recomputed_with_uncertainty(self):
        record = passing_record()
        record["outcome"]["measurements"][0]["raw_readings_mm"] = [10.09, 10.09]
        # Reading alone is in tolerance; +0.02 uncertainty crosses the +0.10 limit.
        errors = qc.evaluate_record(record, restore_spec(), check_files=False)["errors"]
        self.assertTrue(any("result must be fail" in error for error in errors))
        self.assertTrue(any("lack passing repeated measurements" in error for error in errors))

    def test_failure_requires_class_and_actionable_next_change(self):
        record = evaluated_failure()
        record["learning"]["failure_class"] = None
        record["learning"]["next_change"] = None
        errors = qc.evaluate_record(record, restore_spec(), check_files=False)["errors"]
        self.assertTrue(any("failure_class" in error for error in errors))
        self.assertTrue(any("next_change" in error for error in errors))

    def test_malformed_model_hash_fails_closed_without_crashing(self):
        record = base_record()
        record["artifact"]["models"][0]["sha256"] = None
        result = qc.evaluate_record(record, restore_spec(), check_files=False)
        self.assertFalse(result["passed"])
        self.assertTrue(any("models[0].sha256" in error for error in result["errors"]))

    def test_current_model_bytes_are_bound(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "parts/test/widget/stl/widget.stl")
            os.makedirs(os.path.dirname(path)); Path(path).write_bytes(b"model")
            record = passing_record()
            digest = hashlib.sha256(b"model").hexdigest()
            record["artifact"]["models"][0].update(sha256=digest, geom_id=digest[:8])
            self.assertTrue(qc.evaluate_record(record, restore_spec(), repo_root=root)["passed"])
            Path(path).write_bytes(b"changed")
            errors = qc.evaluate_record(record, restore_spec(), repo_root=root)["errors"]
            self.assertTrue(any("model bytes moved" in error for error in errors))


def reported_record():
    record = base_record("reported")
    record["reports"] = [{
        "by": "Human Evaluator", "said": "okay 1 is the best, but 2 also works",
        "at": "2026-09-05T09:30:00-04:00", "recorded_by": "claude",
        "source": "qa/notes/2026-09-05-fit.md",
        "reading": "works", "next_change": None,
    }]
    return record


class ReportedRecordTests(unittest.TestCase):
    """The person's words about a print, written down by someone else: recorded, and evaluating nothing."""

    def test_the_persons_words_make_a_valid_reported_record(self):
        result = qc.evaluate_record(reported_record(), restore_spec(), check_files=False,
                                    require_state="reported")
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(result["state"], "reported")

    def test_a_report_cannot_carry_anything_physical(self):
        record = reported_record()
        record["outcome"]["operator"] = "Human Operator"
        record["outcome"]["checks"][0].update(result="pass", observation="it fits", evidence=["said so"])
        record["outcome"]["measurements"] = [{"dimension": "width"}]
        record["execution"]["printer_id"] = "COREONE-1"
        record["learning"]["observation"] = "fits"
        record["attestation"] = {"statement": "physical-observation", "by": "Human Evaluator",
                                 "at": "2026-09-05T09:30:00-04:00"}
        errors = qc.evaluate_record(record, restore_spec(), check_files=False)["errors"]
        for needed in ("reported record must leave outcome.operator null", "physical execution fields",
                       "reported record checks must remain not-evaluated", "observations/evidence empty",
                       "must not contain physical measurements", "observed learning fields null",
                       "must not carry a human attestation"):
            self.assertTrue(any(needed in error for error in errors), needed)

    def test_a_reading_is_never_a_pass(self):
        record = reported_record()
        self.assertFalse(qc.evaluate_record(record, restore_spec(), check_files=False,
                                            require_state="passed")["passed"])
        record["outcome"]["state"] = "passed"                    # the words alone, relabelled
        errors = qc.evaluate_record(record, restore_spec(), check_files=False)["errors"]
        self.assertTrue(any("attestation" in error for error in errors))
        self.assertTrue(any("every recorded and required printed check to pass" in error for error in errors))

    def test_each_part_of_a_report_is_required(self):
        cases = [("by", "claude", "must name the person who handled the print"),
                 ("by", None, "must name the person who handled the print"),
                 ("said", "  ", "must hold the person's own words"),
                 ("at", "yesterday", "ISO-8601 with timezone"),
                 ("at", "2026-09-05T09:30:00", "ISO-8601 with timezone"),
                 ("recorded_by", None, "must say who wrote the words down"),
                 ("source", "TBD", "must say where the words can be found"),
                 ("reading", "pass", "must be works, does-not-work, or mixed"),
                 ("next_change", "", "next_change must be null or say what changes next"),
                 ("verdict", "pass", "fields a report may not carry")]
        for field, value, reason in cases:
            record = reported_record()
            record["reports"][0][field] = value
            with self.subTest(field=field, value=value):
                errors = qc.evaluate_record(record, restore_spec(), check_files=False)["errors"]
                self.assertTrue(any(reason in error for error in errors), errors)

    def test_reported_needs_words_and_planned_may_not_have_them(self):
        empty = reported_record(); empty["reports"] = []
        errors = qc.evaluate_record(empty, restore_spec(), check_files=False)["errors"]
        self.assertTrue(any("needs one or more reports" in error for error in errors))
        planned = reported_record(); planned["outcome"]["state"] = "planned"
        errors = qc.evaluate_record(planned, restore_spec(), check_files=False)["errors"]
        self.assertTrue(any("planned record must not carry reports" in error for error in errors))

    def test_a_completed_record_keeps_the_words_said_before_it(self):
        record = passing_record()
        record["reports"] = reported_record()["reports"]
        self.assertTrue(qc.evaluate_record(record, restore_spec(), check_files=False)["passed"])

    def test_add_report_appends_and_refuses_a_record_the_person_filled_in(self):
        record = qc.add_report(base_record(), by="Human Evaluator", said="3 works well", reading="works",
                               source="session 2026-09-05", recorded_by="claude")
        self.assertEqual(record["outcome"]["state"], "reported")
        self.assertTrue(qc._timestamp(record["reports"][0]["at"]))          # now, with its timezone
        qc.add_report(record, by="Human Evaluator", said="it loosened after a day", reading="mixed",
                      source="session 2026-09-06", recorded_by="claude", at="2026-09-06T08:00:00-04:00",
                      next_change="one more rib")
        self.assertEqual([row["said"] for row in record["reports"]], ["3 works well", "it loosened after a day"])
        self.assertTrue(qc.evaluate_record(record, restore_spec(), check_files=False)["passed"])
        for theirs in (passing_record(), evaluated_failure(), base_record("printed")):
            with self.assertRaisesRegex(ValueError, "theirs to change"):
                qc.add_report(theirs, by="Human Evaluator", said="x", reading="works", source="s",
                              recorded_by="claude")

    def test_the_command_changes_only_the_state_and_the_reports(self):
        with tempfile.TemporaryDirectory() as root:
            part = Path(root) / "parts/widget"
            (part / "qa/iterations").mkdir(parents=True)
            (part / "spec.yaml").write_text(yaml.safe_dump(restore_spec()))
            path = part / "qa/iterations/2026-09-04-i1.yaml"
            qc.write_record(str(path), base_record())
            before = path.read_text()
            argv = ["report", "--record", str(path), "--by", "Human Evaluator", "--said", "3 works well",
                    "--reading", "works", "--source", "session 2026-09-05", "--recorded-by", "claude",
                    "--at", "2026-09-05T09:30:00-04:00"]
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(qc.main(argv), 0)
            self.assertIn("No check was evaluated and no status changes.", out.getvalue())
            after = yaml.safe_load(path.read_text())
            want = yaml.safe_load(before)
            want["outcome"]["state"] = "reported"
            want["reports"] = [{"by": "Human Evaluator", "said": "3 works well",
                                "at": "2026-09-05T09:30:00-04:00", "recorded_by": "claude",
                                "source": "session 2026-09-05", "reading": "works", "next_change": None}]
            self.assertEqual(after, want)
            self.assertEqual(path.read_text().replace("state: reported", "state: planned").split("reports:")[0],
                             before)                                   # every other byte as it was

            # a paraphrase by a non-human "by" is refused, and the file is left alone
            reported = path.read_text()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(qc.main(argv[:4] + ["claude"] + argv[5:]), 1)
            self.assertEqual(path.read_text(), reported)

            # a record the person completed is refused outright
            done = part / "qa/iterations/2026-09-04-i2.yaml"
            done.write_text(yaml.safe_dump(passing_record(), sort_keys=False))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(qc.main(["report", "--record", str(done)] + argv[3:]), 1)
            self.assertIn("theirs to change", err.getvalue())
            self.assertEqual(yaml.safe_load(done.read_text()), passing_record())


class ReportAfterTheSpecMovedOnTests(unittest.TestCase):
    """A coupon's spec gains criteria as it iterates. The words about an earlier print stay recordable and counted;
    that record still cannot carry an evaluation against today's spec."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory(); self.addCleanup(self.td.cleanup)
        self.part = Path(self.td.name) / "parts/widget"
        (self.part / "qa/iterations").mkdir(parents=True)
        self.path = self.part / "qa/iterations/2026-09-04-i1.yaml"
        qc.write_record(str(self.path), base_record())
        later = restore_spec()
        later["acceptance"]["printed"].append("clicks_at_every_notch")          # added for the next iteration
        (self.part / "spec.yaml").write_text(yaml.safe_dump(later))
        self.later = later

    def test_the_words_about_the_earlier_print_are_still_recorded_and_counted(self):
        self.assertEqual(qc.collect_metrics(self.td.name)["malformed"], 1)       # planned against today's spec
        argv = ["report", "--record", str(self.path), "--by", "Human Evaluator", "--said", "2 came loose",
                "--reading", "does-not-work", "--source", "session 2026-09-05", "--recorded-by", "claude"]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(qc.main(argv), 0)
        report = qc.collect_metrics(self.td.name)
        self.assertEqual((report["records"], report["malformed"]), (1, 0))
        self.assertEqual(report["reported_readings"], {"does-not-work": 1})
        self.assertEqual(report["evaluated"], 0)

    def test_it_still_cannot_be_evaluated_against_todays_spec(self):
        record = passing_record()                                               # the earlier criteria only
        errors = qc.evaluate_record(record, self.later, check_files=False)["errors"]
        self.assertTrue(any("missing printed acceptance checks: clicks_at_every_notch" in e for e in errors))
        record["reports"] = reported_record()["reports"]
        self.path.write_text(yaml.safe_dump(record, sort_keys=False))
        self.assertEqual(qc.collect_metrics(self.td.name)["malformed"], 1)       # words do not rescue a pass


class HandoffManifestAndPartTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory(); self.addCleanup(self.td.cleanup)
        self.root = self.td.name
        subprocess.run(["git", "init", "-q", self.root], check=True)
        subprocess.run(["git", "-C", self.root, "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", self.root, "config", "user.name", "Test"], check=True)
        Path(self.root, ".gitignore").write_text("build/\n")
        self.part = os.path.join(self.root, "parts/test/widget")
        self.out = os.path.join(self.root, "build/i1")
        os.makedirs(os.path.join(self.part, "stl")); os.makedirs(self.out)
        self.spec_path = os.path.join(self.part, "spec.yaml")
        with open(self.spec_path, "w") as stream: yaml.safe_dump(restore_spec(), stream)
        self.model = os.path.join(self.part, "stl/widget.stl")
        Path(self.model).write_bytes(b"canonical model")
        model_sha = qc.sha256_file(self.model)
        with open(os.path.join(self.part, "verify.stamp"), "w") as stream:
            stream.write(f"verdict=PASS\nsha256={'e' * 64}\nstl={model_sha[:8]} stl/widget.stl\n")
        self.gcode = os.path.join(self.out, "plate_1.gcode")
        Path(self.gcode).write_text(
            "; generated by PrusaSlicer 2.9.6\n"
            "; filament used [g] = 4.25\n"
            "; estimated printing time (normal mode) = 12m 30s\n"
            "; prusaslicer_config = begin\n; layer_height = 0.2\n"
            "; prusaslicer_config = end\n")
        Path(os.path.join(self.out, "plate.3mf")).write_bytes(b"3mf")
        Path(os.path.join(self.out, ".overrides.ini")).write_text("binary_gcode = 0\n")
        Path(os.path.join(self.out, "verify_report.txt")).write_text("BREP_VERDICT_RESULT: PASS\n")
        with open(os.path.join(self.out, "plate_geom.txt"), "w") as stream:
            stream.write(f"{model_sha[:8]}  {model_sha}  {self.model}\n")
        qc.slice_identity.write_metadata(
            os.path.join(self.out, "slice_meta.json"), gcode=self.gcode,
            project=os.path.join(self.out, "plate.3mf"),
            overrides_path=os.path.join(self.out, ".overrides.ini"), slicer="prusa-slicer",
            machine="Core One", process="0.20 SPEED", filament="PLA",
            rotation={"x": 0, "y": 0, "z": 0}, support_requested=False,
            spec=self.spec_path, overrides=[], post_hooks=[])
        fixture_producer(self.root, self.part)
        subprocess.run(["git", "-C", self.root, "add", ".gitignore", "parts"], check=True)
        subprocess.run(["git", "-C", self.root, "commit", "-qm", "part"], check=True)

    def test_manifest_binds_model_gcode_verify_and_process_then_initializes_planned_record(self):
        manifest_path = qc.write_handoff_manifest(self.out, [self.part])
        manifest = json.loads(Path(manifest_path).read_text())
        self.assertEqual(manifest["human_evaluation"], "not-evaluated")
        self.assertEqual(manifest["plate"]["estimate"]["filament_g"], 4.25)
        self.assertEqual(manifest["plate"]["estimate"]["print_time_seconds"], 750.0)
        self.assertEqual(manifest["parts"][0]["models"][0]["geom_id"],
                         qc.sha256_file(self.model)[:8])
        record = qc.init_record(manifest_path, self.part, iteration_id="2026-09-04-i1",
                                attempt_kind="full-part", objective="check donor fit")
        self.assertEqual(record["outcome"]["state"], "planned")
        self.assertEqual(record["artifact"]["spec_sha256"], qc.sha256_file(self.spec_path))
        self.assertEqual(record["artifact"]["verify_step_sha256"], "e" * 64)
        self.assertIsNone(record["attestation"])
        self.assertTrue(qc.evaluate_record(record, restore_spec(), repo_root=self.root)["passed"])

    def test_manifest_refuses_stale_model_identity(self):
        Path(self.model).write_bytes(b"moved")
        with self.assertRaisesRegex(ValueError, "identity is stale"):
            qc.build_handoff_manifest(self.out, [self.part])

    def test_manifest_refuses_dirty_part_or_shared_source(self):
        with open(self.spec_path, "a") as stream: stream.write("# uncommitted design change\n")
        with self.assertRaisesRegex(ValueError, "changed since build"):
            qc.build_handoff_manifest(self.out, [self.part])
        subprocess.run(["git", "-C", self.root, "checkout", "--", self.spec_path], check=True)
        shared = Path(self.root, "parts/_lib/shared.py"); shared.parent.mkdir(parents=True)
        shared.write_text("UNCOMMITTED = True\n")
        with self.assertRaisesRegex(ValueError, "changed since build"):
            qc.build_handoff_manifest(self.out, [self.part])

    def test_unrelated_dirty_and_untracked_parts_do_not_block_or_change(self):
        unrelated = Path(self.root, "parts/other/draft.py")
        unrelated.parent.mkdir(parents=True); unrelated.write_text("untouched draft\n")
        before = unrelated.read_bytes()
        result = qc.build_handoff_manifest(self.out, [self.part])
        self.assertEqual(result["parts"][0]["source"]["scope"], "part-and-dependencies")
        self.assertEqual(unrelated.read_bytes(), before)
        self.assertIn("?? parts/other/", subprocess.check_output(
            ["git", "-C", self.root, "status", "--porcelain"], text=True))

    def test_non_draft_status_needs_current_exact_record(self):
        spec = restore_spec("released")
        with open(self.spec_path, "w") as stream: yaml.safe_dump(spec, stream)
        result = qc.evaluate_part(self.part)
        self.assertFalse(result["passed"])
        self.assertTrue(any("qualification.current" in error for error in result["errors"]))

    def test_no_status_accepts_a_reported_record(self):
        record = reported_record()
        model_sha = qc.sha256_file(self.model)
        record["artifact"]["models"][0].update(sha256=model_sha, geom_id=model_sha[:8])
        record["artifact"]["source"]["commit"] = subprocess.check_output(
            ["git", "-C", self.root, "rev-parse", "HEAD"], text=True).strip()
        record_path = os.path.join(self.part, "qa/iterations/2026-09-04-i1.yaml")
        os.makedirs(os.path.dirname(record_path))
        with open(record_path, "w") as stream: yaml.safe_dump(record, stream, sort_keys=False)
        wanted = {"printed": "status printed needs a record whose physical print is recorded",
                  "dim-verified": "status dim-verified needs a passed physical record",
                  "released": "status released needs a passed physical record"}
        for status, reason in wanted.items():
            spec = restore_spec(status)
            spec["qualification"] = {"current": "qa/iterations/2026-09-04-i1.yaml"}
            with open(self.spec_path, "w") as stream: yaml.safe_dump(spec, stream)
            result = qc.evaluate_part(self.part)
            with self.subTest(status=status):
                self.assertFalse(result["passed"])
                self.assertTrue(any(reason in error for error in result["errors"]), result["errors"])

    def test_accepted_status_needs_human_tag_that_contains_exact_record_bytes(self):
        record = passing_record()
        model_sha = qc.sha256_file(self.model)
        record["artifact"]["models"][0].update(sha256=model_sha, geom_id=model_sha[:8])
        record["artifact"]["source"]["commit"] = subprocess.check_output(
            ["git", "-C", self.root, "rev-parse", "HEAD"], text=True).strip()
        record_rel = "parts/test/widget/qa/iterations/2026-09-04-i1.yaml"
        record_path = os.path.join(self.root, record_rel)
        os.makedirs(os.path.dirname(record_path))
        with open(record_path, "w") as stream: yaml.safe_dump(record, stream, sort_keys=False)
        spec = restore_spec("released")
        spec["qualification"] = {"current": "qa/iterations/2026-09-04-i1.yaml"}
        with open(self.spec_path, "w") as stream: yaml.safe_dump(spec, stream)
        subprocess.run(["git", "-C", self.root, "add", "parts"], check=True)
        subprocess.run(["git", "-C", self.root, "commit", "-qm", "synthetic evidence fixture"],
                       check=True)

        result = qc.evaluate_part(self.part)
        self.assertFalse(result["passed"])
        self.assertTrue(any("human passed/* tag" in error for error in result["errors"]))

        digest = qc.sha256_file(record_path)
        message = ("synthetic unit-test tag; asserts no physical event\n\n"
                   f"evidence={record_rel}\nevidence_sha256={digest}\n")
        subprocess.run(["git", "-C", self.root, "tag", "-a", "passed/test/fixture",
                        "-m", message], check=True)
        result = qc.evaluate_part(self.part)
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(qc.matching_passed_tag(self.root, record_path), "passed/test/fixture")

        with open(record_path, "a") as stream: stream.write("# changed after tag\n")
        self.assertIsNone(qc.matching_passed_tag(self.root, record_path))


class MetricsTests(unittest.TestCase):
    def test_reports_only_valid_records_and_keeps_estimated_vs_actual_separate(self):
        with tempfile.TemporaryDirectory() as root:
            widget = Path(root) / "parts/widget"
            other = Path(root) / "parts/other"
            for part in (widget, other):
                (part / "qa/iterations").mkdir(parents=True)
            widget_spec = restore_spec()
            other_spec = restore_spec(); other_spec["part_id"] = "test/other"
            (widget / "spec.yaml").write_text(yaml.safe_dump(widget_spec))
            (other / "spec.yaml").write_text(yaml.safe_dump(other_spec))

            failed = evaluated_failure(); failed["iteration_id"] = "i1"
            passed = passing_record(); passed["iteration_id"] = "i2"
            second = evaluated_failure(); second["part_id"] = "test/other"
            second["iteration_id"] = "i1"
            for target, record in ((widget, failed), (widget, passed), (other, second)):
                path = target / "qa/iterations" / (record["iteration_id"] + ".yaml")
                path.write_text(yaml.safe_dump(record))
            # A schema-shaped but non-evaluated fake must not improve or dilute the metrics.
            bogus = base_record("passed"); bogus["iteration_id"] = "bogus"
            (other / "qa/iterations/bogus.yaml").write_text(yaml.safe_dump(bogus))

            said = reported_record(); said["iteration_id"] = "i3"
            said["reports"].append(dict(said["reports"][0], said="2 came loose", reading="mixed"))
            (widget / "qa/iterations/i3.yaml").write_text(yaml.safe_dump(said))

            report = qc.collect_metrics(root)
            self.assertEqual(report["records"], 4)
            self.assertEqual(report["states"]["reported"], 1)
            self.assertEqual(report["reported_readings"], {"mixed": 1})        # its latest report's reading
            self.assertEqual(report["malformed"], 1)
            self.assertEqual(report["evaluated"], 3)
            self.assertEqual(report["first_pass_parts"], 0)
            self.assertEqual(report["mean_full_part_loops_to_pass"], 2.0)
            self.assertEqual(report["failure_classes"], {"fit": 2})
            self.assertEqual(report["repeated_failure_count"], 1)
            self.assertEqual(report["mean_plate_estimated_material_g_per_accept"], 7.0)
            self.assertEqual(report["mean_actual_material_g_per_accept"], 7.4)
            self.assertEqual(report["mean_actual_minutes_per_accept"], 22.0)


if __name__ == "__main__":
    unittest.main()
