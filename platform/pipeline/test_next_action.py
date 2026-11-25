#!/usr/bin/env python3
"""Tests for next_action.py and the structured gate trace.

The property under test is mostly negative: this tool must not become another confident narrator of
state. The repo's expensive failures were all confident claims nobody re-derived, so what is
asserted here is that unreadable state is reported as unknown, that every claim carries the file it
came from, and that a conditional verdict is never silently upgraded.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

import next_action

HERE = os.path.dirname(os.path.realpath(__file__))
GATES_SH = os.path.join(HERE, "gates.sh")


def bound_example(tmp):
    """Read-only routing fixture in a temporary directory, never a printable job."""
    p = pathlib.Path(tmp)
    sha = lambda f: hashlib.sha256((p / f).read_bytes()).hexdigest()
    import sys
    sys.path.insert(0, str(pathlib.Path(HERE)/'verify'))
    from inventory_fixture import package
    import plate_inventory
    package(p); result = plate_inventory.compare(p)
    if result['verdict'] != 'PASS': raise ValueError(result)
    plate_inventory.record(p, result)
    (p / 'verify_slice.txt').write_text('PASS')
    (p / 'qualification_manifest.json').write_text(json.dumps({
        'schema': 1, 'human_evaluation': 'not-evaluated', 'plate': {
            'gcode': {'sha256': sha('plate_1.gcode')}, 'project_3mf': {'sha256': sha('plate.3mf')}}}))
    fields = ['handoff presented', f'outdir={p}', 'verify_slice=PASS',
              f'gcode_sha={sha("plate_1.gcode")}', f'inventory_sha={sha("plate-inventory.json")}',
              f'qualification_manifest={p}/qualification_manifest.json',
              f'qualification_manifest_sha={sha("qualification_manifest.json")}',
              'brep_verdict=DEBT /part-a', 'brep_verdict=PASS /part-b']
    (p / 'handoff.txt').write_text('\n'.join(fields) + '\n')


class PlateState(unittest.TestCase):
    def plate(self, tmp, **prep):
        os.makedirs(tmp, exist_ok=True)
        with open(os.path.join(tmp, "preparation.json"), "w") as stream:
            json.dump(prep, stream)
        return tmp

    def test_ready_plate_without_a_handoff_asks_for_the_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.plate(tmp, status="READY", kind="prototype"); bound_example(tmp)
            (pathlib.Path(tmp) / 'handoff.txt').unlink()
            report = next_action.inspect(tmp)
        self.assertEqual(report["state"], "READY (handoff not present)")
        self.assertTrue(any("handoff.sh" in step for step in report["next"]))

    def test_presented_handoff_stops_at_the_human(self):
        """The one thing this tool must never do is imply it can approve."""
        with tempfile.TemporaryDirectory() as tmp:
            self.plate(tmp, status="READY", kind="prototype")
            bound_example(tmp)
            report = next_action.inspect(tmp)
        self.assertEqual(report["state"], "AWAITING HUMAN APPROVAL")
        self.assertEqual((report['action'], report['stop']), ('review_handoff', True))
        self.assertTrue(any("Approval is theirs" in s for s in report["next"]))
        self.assertTrue(any("measurement debt" in s for s in report["next"]),
                        "a DEBT plate must say so where a human will read it")
        self.assertTrue(any("APPROVED=1" in s for s in report["next"]),
                        "explain the approval boundary without issuing a send command")
        self.assertFalse(any('send.sh ' in s for s in report['next']))

    def test_request_waits_for_catalog_then_recipe_not_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp); (p/'plate-request.json').write_text('{"schema":1,"requested":{"clip":1}}')
            self.assertEqual(next_action.inspect(p)['action'], 'register_inventory_models')
            bound_example(tmp)
            for n in ('plate_1.gcode','handoff.txt','verify_slice.txt','qualification_manifest.json'):
                (p/n).unlink()
            r = next_action.inspect(p); self.assertEqual((r['action'], r['requested']), ('locate_recipe', {'clip':1}))

    def test_readable_review_project_is_not_a_send_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / 'plate.3mf').write_bytes(b'review fixture')
            r = next_action.inspect(tmp)
        self.assertEqual((r['schema'], r['action'], r['stop']), (1, 'review_project', True))
        self.assertIn('plate.3mf', r['review_paths'])

    def test_incomplete_or_changed_handoff_never_routes_to_approval(self):
        for name in ('handoff.txt', 'plate_1.gcode', 'plate.3mf', 'qualification_manifest.json', 'verify_slice.txt'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                self.plate(tmp, status='READY', kind='prototype'); bound_example(tmp)
                (pathlib.Path(tmp) / name).write_text('changed')
                r = next_action.inspect(tmp)
                self.assertEqual((r['action'], r['stop']), ('rebuild_handoff', True))
                self.assertTrue(r['blockers'])

    def test_refusal_beats_old_handoff_and_a_second_failed_attempt_escalates(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.plate(tmp, status='BLOCKED', failed_attempts=2, problems=['handoff: exit 15; review.log'])
            bound_example(tmp); r = next_action.inspect(tmp)
        self.assertEqual((r['action'], r['stop']), ('escalate', True))
        self.assertIn('review.log', ' '.join(r['blockers']))

    def test_blocked_plate_points_at_the_bounded_repair_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.plate(tmp, status="BLOCKED", kind="prototype")
            report = next_action.inspect(tmp)
        self.assertEqual(report["state"], "BLOCKED")
        self.assertTrue(any("--repair-reason" in s for s in report["next"]))

    def test_unparseable_preparation_is_unknown_not_assumed(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(tmp, exist_ok=True)
            with open(os.path.join(tmp, "preparation.json"), "w") as stream:
                stream.write("{ this is not json")
            report = next_action.inspect(tmp)
        self.assertTrue(any("could not be parsed" in u for u in report["unknown"]))
        self.assertNotIn(report["state"], ("READY", "AWAITING HUMAN APPROVAL"))

    def test_a_blocking_gate_from_the_trace_is_reported_with_its_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.plate(tmp, status="BLOCKED", kind="release")
            with open(os.path.join(tmp, "gates.handoff.jsonl"), "w") as stream:
                stream.write(json.dumps({
                    "gate": "VERIFY_RESULT", "verdict": "DEBT", "allowed": False, "blocking": True,
                    "condition": "plate-kind:prototype,bench-experiment", "condition_met": False,
                    "exit_on_block": "14", "enforced_as": "verify.sh <part>"}) + "\n")
            report = next_action.inspect(tmp)
        self.assertEqual(len(report["blockers"]), 1)
        blocker = report["blockers"][0]
        self.assertIn("exit 14", blocker)
        self.assertIn("DEBT", blocker)
        self.assertIn("kind=release", blocker,
                      "must name the plate kind, since that is what makes this one block")

    def test_ready_label_with_no_slice_stops_for_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.plate(tmp, status='READY'); r = next_action.inspect(tmp)
        self.assertEqual((r['action'], r['stop']), ('inspect_preparation', True))
        self.assertIn('plate_1.gcode', ' '.join(r['blockers']))

    def test_part_routes_to_scoped_preflight_without_a_git_cleanup(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / 'part space'; p.mkdir(); (p/'spec.yaml').write_text('status: draft')
            (p/'README.md').write_text('Unrelated work in progress')
            self.assertEqual(next_action.inspect(p)['action'], 'locate_recipe')
            (p/'prepare.yaml').write_text('schema: 1')
            with patch.object(next_action.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, tmp, '')):
                r = next_action.inspect(p)
            self.assertEqual((r['action'], r['stop']), ('preflight', False))
            self.assertIn('--preflight', r['next'][0]); self.assertFalse(r['blockers'])

    def test_unrecognised_directory_is_not_narrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = next_action.inspect(tmp)
        self.assertEqual(report["state"], "UNKNOWN")
        self.assertTrue(report["unknown"])

    def test_every_rendered_claim_names_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.plate(tmp, status="READY", kind="prototype")
            text = next_action.render(next_action.inspect(tmp))
        self.assertIn("Read from (nothing below is inferred):", text)
        self.assertIn("preparation.json", text)


class AlreadySent(unittest.TestCase):
    """send.sh used to leave no local trace, so nothing in the tree distinguished an uploaded plate
    from one still awaiting presentation — next_action reported AWAITING HUMAN APPROVAL forever
    after a send, and an agent acting on that would re-present or re-send a plate already on the
    printer. sent.json closes that; these tests keep it closed."""

    def plate(self, tmp, gcode=b"G1 X0\n", **sent):
        with open(os.path.join(tmp, "preparation.json"), "w") as stream:
            json.dump({"status": "READY", "kind": "prototype"}, stream)
        with open(os.path.join(tmp, "handoff.txt"), "w") as stream:
            stream.write("brep_verdict=DEBT /part\n")
        with open(os.path.join(tmp, "plate_1.gcode"), "wb") as stream:
            stream.write(gcode)
        import hashlib
        record = {"sent_at": "2026-09-06T05:30:00Z", "gcode": "plate_1.gcode",
                  "gcode_sha256": hashlib.sha256(gcode).hexdigest(), "host": "coreone.lan",
                  "storage": "usb", "started": False, "approved_env_was_set": True}
        record.update(sent)
        with open(os.path.join(tmp, "sent.json"), "w") as stream:
            json.dump(record, stream)
        return tmp

    def test_a_sent_plate_is_not_reported_as_awaiting_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = next_action.inspect(self.plate(tmp))
        self.assertIn("STAGED AT PRINTER", report["state"])
        self.assertTrue(any("Do NOT re-send" in s for s in report["next"]))

    def test_a_started_plate_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = next_action.inspect(self.plate(tmp, started=True))
        self.assertEqual(report['action'], 'await_observation')
        self.assertNotIn('PRINTING', report['state'], 'a historical start receipt is not live status')
        self.assertFalse(any("Start it at the machine" in s for s in report["next"]),
                         "a running print must not be told to start again")

    def test_gcode_changed_since_the_send_is_called_out(self):
        """The dangerous case: a re-slice after a send. What is on the printer is no longer this
        plate, and anything reasoning from the plate directory would be reasoning about the wrong
        bytes."""
        with tempfile.TemporaryDirectory() as tmp:
            self.plate(tmp)
            with open(os.path.join(tmp, "plate_1.gcode"), "wb") as stream:
                stream.write(b"G1 X999 ; re-sliced\n")
            report = next_action.inspect(tmp)
        self.assertEqual((report['action'], report['stop']), ('inspect_receipt', True))
        self.assertIn('changed', ' '.join(report['blockers']).lower())

    def test_unparseable_send_record_warns_rather_than_assuming_unsent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.plate(tmp)
            with open(os.path.join(tmp, "sent.json"), "w") as stream:
                stream.write("{ truncated")
            report = next_action.inspect(tmp)
        self.assertEqual((report['action'], report['stop']), ('inspect_receipt', True))
        self.assertTrue(any("may already be on the printer" in u for u in report["unknown"]))
        self.assertFalse(any('send.sh' in s for s in report['next']))

    def test_missing_or_wrongly_typed_receipt_fields_are_not_success(self):
        for bad in ({}, [], {'started': 'false'}, {'started': None}):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as tmp:
                self.plate(tmp); (pathlib.Path(tmp)/'sent.json').write_text(json.dumps(bad))
                self.assertEqual(next_action.inspect(tmp)['action'], 'inspect_receipt')

    def test_the_record_never_claims_a_person_approved(self):
        """APPROVED=1 is an assertion made to a script, not evidence about a human. Recording it as
        'the human approved' would manufacture exactly the evidence the handoff gate demands."""
        send = pathlib.Path(HERE, "send", "send.sh").read_text()
        self.assertNotIn('"approved":', send)
        self.assertIn("approved_env_was_set", send)


class PaperTrial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        path = pathlib.Path(HERE, 'agent-trials', 'trial.py')
        spec = importlib.util.spec_from_file_location('paper_trial', path)
        cls.trial = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.trial)
        cls.cards = cls.trial.cases(); cls.key = json.loads((path.parent/'key.json').read_bytes())

    def controls(self):
        return [dict(id=k, action=v[0], evidence=v[1], reason='scorer unit-test control, not a model')
                for k, v in self.key.items()]

    def test_closed_set_and_scorer_positive_control(self):
        self.assertEqual(set(self.cards), set(self.key))
        s = self.trial.score(self.controls(), self.cards, self.key)
        self.assertFalse(s['errors']); self.assertEqual(s['correct_fields'], len(self.cards))
        self.assertFalse(s['critical_route_errors'])

    def test_missing_duplicate_invalid_and_unauthorized_are_not_success(self):
        rows = self.controls(); rows[2]['action'] = 'stage_only'; rows[3]['evidence'] = ['not-observed.log']
        rows += [rows[0], None]; del rows[1]; s = self.trial.score(rows, self.cards, self.key)
        self.assertEqual(s['critical_route_errors'], ['C']); self.assertEqual(len(s['errors']), 5)


class StructuredTrace(unittest.TestCase):
    """gates.sh writes the trace. It is written in bash, so it is tested through bash."""

    def run_gate(self, token, text, condition, results):
        script = ('. "%s"; export GATE_RESULTS="%s"; gate_allows "%s" "%s" %d'
                  % (GATES_SH, results, token, text, condition))
        subprocess.run(["bash", "-c", script], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        with open(results, encoding="utf-8") as stream:
            return [json.loads(l) for l in stream if l.strip()]

    def test_trace_is_valid_json_and_records_the_blocking_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = os.path.join(tmp, "gates.jsonl")
            rows = self.run_gate("VERIFY_RESULT", "VERIFY_RESULT: DEBT", 0, results)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["verdict"], "DEBT")
        self.assertTrue(rows[0]["blocking"])
        self.assertFalse(rows[0]["condition_met"])
        self.assertEqual(rows[0]["exit_on_block"], "14")

    def test_mesh_gate_trace_round_trips_quoted_enforcing_command(self):
        import gates
        with tempfile.TemporaryDirectory() as tmp:
            rows = self.run_gate('MESH_RESULT', 'MESH_RESULT: PASS', 0, os.path.join(tmp, 'gates.jsonl'))
        self.assertEqual(rows[0]['enforced_as'], gates.load()['MESH_RESULT'].enforced_as)

    def test_legacy_trace_warning_does_not_hide_a_later_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            bound_example(tmp); f = pathlib.Path(tmp) / 'gates.old.jsonl'
            f.write_text('{truncated}\n')
            r = next_action.inspect(tmp)
            self.assertEqual(r['action'], 'review_handoff'); self.assertTrue(r['unknown'])
            with f.open('a') as s:
                s.write(json.dumps({'gate':'QUALIFICATION_RESULT','verdict':'FAIL','blocking':True,'exit_on_block':'15'}))
            self.assertEqual(next_action.inspect(tmp)['action'], 'inspect_blocker')

    def test_the_same_verdict_is_not_blocking_when_the_condition_holds(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = os.path.join(tmp, "gates.jsonl")
            rows = self.run_gate("VERIFY_RESULT", "VERIFY_RESULT: DEBT", 1, results)
        self.assertFalse(rows[0]["blocking"])
        self.assertTrue(rows[0]["condition_met"],
                        "the trace must record WHY it was allowed, not just that it was")

    def test_no_trace_is_written_when_the_caller_did_not_ask_for_one(self):
        """Every stage that does not opt in must behave exactly as before."""
        script = ('. "%s"; unset GATE_RESULTS; gate_allows VERIFY_RESULT "VERIFY_RESULT: PASS" 0; '
                  'echo rc=$?' % GATES_SH)
        out = subprocess.run(["bash", "-c", script], text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
        self.assertIn("rc=0", out.stdout)


if __name__ == "__main__":
    unittest.main()
