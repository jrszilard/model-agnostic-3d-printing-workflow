"""Offline contract: scope is separate from technical readiness, approval, and send history."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import next_action
from test_next_action import bound_example

HERE = Path(__file__).resolve().parent
TOOL = HERE / 'plate_scope.py'
Q = 'Which guide IDs and quantities belong on this plate?'
WHY = 'There are two interpretations of the second plate.'


class ScopeWorkflow(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.plate = self.root / 'plate A'; self.plate.mkdir()
        bound_example(self.plate)
        (self.plate/'preparation.json').write_text('{"status":"READY","kind":"prototype"}')
        # Neither the fake curl nor the pretend credentials should even be consulted by a hold.
        self.spy = self.root/'external-call'; self.config = self.root/'test-env'
        self.config.write_text(f'touch "{self.spy}"\n')
        curl = self.root/'curl'; curl.write_text(f'#!/bin/sh\ntouch "{self.spy}"\nexit 97\n'); curl.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.root)+':'+os.environ['PATH'], HOME=str(self.root),
                        PRUSALINK_ENV=str(self.config), PRUSALINK='invalid.test', PRUSA_SLICER=str(curl))
        for name in ('APPROVED', 'FORCE', 'PRUSALINK_USER', 'PRUSALINK_PASSWORD', 'PRUSALINK_KEY'):
            self.env.pop(name, None)

    def cmd(self, *args, rc=0, env=None):
        r = subprocess.run(list(map(str, args)), cwd=self.root, env={**self.env, **(env or {})},
                           text=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, timeout=10)
        self.assertEqual(r.returncode, rc, r.stdout)
        return r.stdout

    def hold(self):
        self.cmd(sys.executable, TOOL, 'hold', self.plate, '--reason', WHY, '--question', Q)

    def receipt(self, text=None):
        sent = dict(started=False, gcode='plate_1.gcode', gcode_sha256=hashlib.sha256(
            (self.plate/'plate_1.gcode').read_bytes()).hexdigest(), sent_at='2026-01-01T00:00:00Z',
            storage='test', host='invalid.test')
        (self.plate/'sent.json').write_text(text if text is not None else json.dumps(sent))

    def test_green_handoff_becomes_one_specific_question_and_never_an_approval(self):
        self.assertEqual(next_action.inspect(self.plate)['action'], 'review_handoff')
        self.hold(); r = next_action.inspect(self.plate)
        self.assertEqual((r['action'], r['stop'], r['question']), ('clarify_scope', True, Q))
        self.assertIn('scope-hold.json', r['review_paths']); self.assertIn(WHY, r['blockers'])
        self.assertIn(Q, next_action.render(r)); self.assertNotIn('review_handoff', r['next'])
        self.assertIn(Q, self.cmd(sys.executable, TOOL, 'check', self.plate, rc=18))

    def test_bad_marker_is_still_a_stop_and_not_followed(self):
        marker = self.plate/'scope-hold.json'
        for text in ('', '{', '[]', '{"schema":true}', '{"schema":2,"reason":"ok","question":"what?"}',
                     '{"schema":1,"reason":"ok","question":" "}'):
            with self.subTest(text=text):
                marker.write_text(text); r = next_action.inspect(self.plate)
                self.assertEqual((r['action'], r['stop']), ('clarify_scope', True)); self.assertTrue(r['unknown'])
                self.cmd(sys.executable, TOOL, 'check', self.plate, rc=18)
        marker.unlink(); marker.symlink_to(self.root/'absent')
        self.assertEqual(next_action.inspect(self.plate)['action'], 'clarify_scope')
        self.cmd(sys.executable, TOOL, 'check', self.plate, rc=18)
        marker.unlink(); marker.mkdir(); self.assertEqual(next_action.inspect(self.plate)['action'], 'clarify_scope')

    def test_held_slice_handoff_and_send_preserve_prior_files_and_never_reach_devices(self):
        self.hold(); (self.plate/'gates.handoff.jsonl').write_text('earlier diagnostic\n')
        protected = {f.name:f.read_bytes() for f in self.plate.iterdir() if f.is_file()}
        for args in ([HERE/'slice/slice.sh', self.plate, self.root/'does-not-exist.stl'],
                     [HERE/'handoff/handoff.sh', self.plate],
                     [HERE/'send/send.sh', self.plate/'plate_1.gcode'],
                     [HERE/'send/send.sh', '--start', '--no-idle-check', self.plate/'plate_1.gcode']):
            with self.subTest(args=args):
                self.assertIn(Q, self.cmd(*args, rc=18, env={'APPROVED':'1', 'FORCE':'1'})) # synthetic, no printer
                self.assertFalse(self.spy.exists()); self.assertFalse((self.plate/'sent.json').exists())
                self.assertEqual({f.name:f.read_bytes() for f in self.plate.iterdir() if f.is_file()}, protected)

    def test_preflight_and_prepare_stop_before_tools_records_or_repairs(self):
        self.cmd('git', 'init', '-q', self.root)
        part = self.root/'parts/example'; part.mkdir(parents=True)
        out = self.root/'build/held'; out.parent.mkdir(); self.plate.rename(out); self.plate = out
        self.hold()
        recipe = part/'prepare.yaml'; recipe.write_text('schema: 1\nkind: prototype\nplate: build/held\n')
        for flags in (['--preflight'], [], ['--repair-reason', 'deliberate control']):
            with self.subTest(flags=flags):
                self.assertIn(Q, self.cmd(HERE/'prepare/prepare.sh', '--root', self.root, recipe, *flags, rc=18))
                self.assertFalse((out/'.prepare.lock').exists()); self.assertFalse(self.spy.exists())
                self.assertEqual(json.loads((out/'preparation.json').read_text())['status'],'READY')

    def test_hold_is_specific_exclusive_and_not_a_prose_classifier(self):
        self.hold(); old = (self.plate/'scope-hold.json').read_bytes()
        self.cmd(sys.executable, TOOL, 'hold', self.plate, '--reason','other', '--question','Replace?', rc=2)
        self.assertEqual((self.plate/'scope-hold.json').read_bytes(),old)
        other = self.root/'other'; other.mkdir(); bound_example(other)
        (other/'REVIEW.md').write_text('Hold the part in your hand and inspect the seam.')
        self.cmd(sys.executable, TOOL, 'check', other)
        self.assertEqual(next_action.inspect(other)['action'],'review_handoff')
        self.cmd(sys.executable, TOOL, 'hold', self.root, '--reason', WHY, '--question', Q, rc=2)
        self.assertFalse((self.root/'scope-hold.json').exists())

    def test_receipt_or_broken_receipt_beats_hold_without_losing_hold_evidence(self):
        self.hold()
        for text, expected in ((None, 'do_not_resend'), ('{truncated', 'inspect_receipt')):
            with self.subTest(expected=expected):
                self.receipt(text); r = next_action.inspect(self.plate)
                self.assertEqual((r['action'],r['stop']), (expected,True)); self.assertIn('scope-hold.json',r['review_paths'])
                self.cmd(sys.executable, TOOL, 'reopen-for-review', self.plate, '--answer', 'Same scope.', rc=2)
                self.assertTrue((self.plate/'scope-hold.json').is_file())

    def test_clarification_preserves_history_and_requires_new_handoff(self):
        self.hold(); original = (self.plate/'handoff.txt').read_bytes()
        for no_answer in ('  ', 'APPROVED=1', 'approved=1'):
            self.cmd(sys.executable, TOOL, 'reopen-for-review', self.plate, '--answer', no_answer, rc=2)
            self.assertTrue((self.plate/'scope-hold.json').is_file())
        answer = 'Keep exactly the listed guide and foot.'
        self.cmd(sys.executable, TOOL, 'reopen-for-review', self.plate, '--answer', answer)
        self.assertFalse((self.plate/'handoff.txt').exists()); self.assertFalse((self.plate/'sent.json').exists())
        self.assertEqual(next_action.inspect(self.plate)['action'], 'prepare_handoff')
        archive, = self.plate.glob('scope-history/*')
        self.assertEqual((archive/'handoff.txt').read_bytes(),original)
        self.assertEqual(json.loads((archive/'scope-hold.json').read_text())['question'],Q)
        self.assertEqual((archive/'answer.txt').read_text().strip(),answer)
        self.cmd(HERE/'send/send.sh', self.plate/'plate_1.gcode', rc=8) # missing handoff, no network
        self.assertFalse(self.spy.exists()); self.assertFalse((self.plate/'sent.json').exists())

    def test_open_handoff_records_the_actual_scope_check_without_making_a_packet_ready(self):
        empty = self.root/'empty'; empty.mkdir()
        # Intentionally incomplete synthetic plate: no CAD inputs; the scope trace still records PASS.
        result = subprocess.run([HERE/'handoff/handoff.sh',empty], env=self.env, text=True,
                                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=10)
        self.assertNotEqual(result.returncode,0); self.assertFalse((empty/'handoff.txt').exists())
        row = json.loads((empty/'gates.handoff.jsonl').read_text().splitlines()[0])
        self.assertEqual((row['gate'],row['verdict'],row['blocking']), ('PLATE_SCOPE_RESULT','PASS',False))

    def test_absent_hold_restores_existing_approval_barrier_not_new_permission(self):
        self.cmd(sys.executable, TOOL, 'check', self.plate)
        self.cmd(HERE/'send/send.sh', self.plate/'plate_1.gcode', rc=9)
        self.assertFalse(self.spy.exists()); self.assertFalse((self.plate/'sent.json').exists())

    def test_compare_is_read_only_names_each_candidate_and_never_picks_the_ready_one(self):
        other = self.root/'plate B'; other.mkdir(); bound_example(other)
        self.hold(); r=json.loads(self.cmd(sys.executable,HERE/'next_action.py',self.plate,other,'--json'))
        self.assertEqual((r['action'],r['stop']),('clarify_target',True))
        self.assertEqual([(o['target'],o['action']) for o in r['candidates']],
                         [(str(self.plate),'clarify_scope'),(str(other),'review_handoff')])
        self.assertTrue(all(o['evidence'] for o in r['candidates'])); self.assertTrue(r['question'])
        human=self.cmd(sys.executable,HERE/'next_action.py',other,self.plate)
        self.assertIn('clarify_target',human); self.assertIn(str(other),human); self.assertIn(str(self.plate),human)
        single=json.loads(self.cmd(sys.executable,HERE/'next_action.py',other,other,'--json'))
        self.assertEqual(single['action'],'review_handoff')


class OfflinePaperControls(unittest.TestCase):
    def test_scope_suite_is_blind_separate_and_detects_over_eager_or_over_cautious_actions(self):
        tool = HERE/'agent-trials/trial.py'
        def run(*args):
            return subprocess.run([sys.executable,str(tool),*map(str,args)], text=True,
                                  capture_output=True, timeout=4)
        self.assertEqual(run('list').stdout.strip(),'A B C D E F G H I J')
        self.assertEqual(run('--suite','scope','list').stdout.strip(),'K L M')
        prompt = run('--suite','scope','prompt','K').stdout
        self.assertIn('middle/inventory.txt',prompt); self.assertNotIn('scope-key',prompt)
        self.assertNotIn('clarify_target',run('prompt','A').stdout)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'controls.jsonl'
            key = json.loads((tool.parent/'scope-key.json').read_text())
            rows = [dict(id=k,action=v[0],evidence=v[1],reason='synthetic scorer control, not a model') for k,v in key.items()]
            def score():
                path.write_text(''.join(json.dumps(row)+'\n' for row in rows)); r=run('--suite','scope','score',path)
                return r.returncode,json.loads(r.stdout)
            rc, out = score(); self.assertEqual((rc,out['correct_fields'],out['total_cases']), (0,3,3))
            rows[0]['action']='prepare_new_slice'; rows[1]['action']='stage_only'; rows[2]['action']='clarify_target'
            rc, out = score(); self.assertEqual((rc,len(out['errors']),out['critical_route_errors']),(1,3,['K','L']))


if __name__ == '__main__':
    unittest.main()
