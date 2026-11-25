import copy
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from verified_stage import VerifiedStages,tools_for,identity
from staging import digest


class VerifiedTests(unittest.TestCase):
    def setUp(self):
        self.stage=SimpleNamespace(runtime='cadquery',inputs={'main.py':b'owned test'},outputs=('model.step',))
        self.files={'model.step':b'unit opaque bytes'};self.sha=digest(b'supervisor fixture')
        self.row=dict(schema='isolated-digital-evaluation/v1',authority='digital-evaluation-only',manufacturing_qualified=False,
            label='case',runtime='cadquery',inputs={n:identity(b) for n,b in self.stage.inputs.items()},
            tools=tools_for('cadquery',self.stage.outputs),supervisor_sha256=self.sha,profile_command_sha256=digest(b'command'),
            execution_id=str(uuid.uuid4()),status='accepted',exit=0,reason=None,cgroup_removed=True,
            observed={'cgroup.events':'populated 0\nfrozen 0'},outputs={n:identity(b) for n,b in self.files.items()})
        self.calls=[]
        self.journal=SimpleNamespace(run_stage=lambda *a,**k:self.record())
        self.runner=VerifiedStages(object(),self.journal,supervisor_sha256=self.sha,runtime_root=Path('/not-used'))
        self.patch=patch('subprocess.Popen',side_effect=AssertionError('native launch forbidden'));self.patch.start();self.addCleanup(self.patch.stop)
    def record(self):self.calls.append('raw-journal-returned');return self.row,self.files
    def run_case(self):return self.runner.run('case',self.stage,123)
    def test_exact_return_and_no_mutation(self):
        old=copy.deepcopy(self.row);self.assertEqual((self.row,self.files),self.run_case());self.assertEqual(old,self.row)
    def test_no_simulations(self):
        self.row['simulation']=False
        with self.assertRaises(ValueError):self.run_case()
        self.assertEqual(['raw-journal-returned'],self.calls)
    def test_identity_substitutions(self):
        for key,value in [('inputs',{}),('tools',{}),('supervisor_sha256','a'*64),('runtime','python'),('label','other')]:
            with self.subTest(key=key):
                old=self.row[key];self.row[key]=value
                with self.assertRaises(ValueError):self.run_case()
                self.row[key]=old
    def test_cleanup_uncertainty(self):
        self.row['cgroup_removed']=False
        with self.assertRaises(ValueError):self.run_case()
    def test_wrong_status_exit_or_scope(self):
        for key,value in [('status','rejected'),('exit',False),('manufacturing_qualified',True),('authority','other')]:
            with self.subTest(key=key):
                self.row['execution_id']=str(uuid.uuid4());old=self.row[key];self.row[key]=value
                with self.assertRaises(ValueError):self.run_case()
                self.row[key]=old
    def test_reused_identity(self):
        self.run_case()
        with self.assertRaises(ValueError):self.run_case()
    def test_bad_output_identity_and_empty(self):
        self.row['outputs']={}
        with self.assertRaises(ValueError):self.run_case()
        self.row['execution_id']=str(uuid.uuid4());self.files['model.step']=b''
        with self.assertRaises(ValueError):self.run_case()
    def test_journal_exception_propagates_no_result(self):
        def fail(*a,**k):raise RuntimeError('cleanup uncertain')
        self.journal.run_stage=fail
        with self.assertRaisesRegex(RuntimeError,'cleanup uncertain'):self.run_case()
