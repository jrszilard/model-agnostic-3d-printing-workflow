import concurrent.futures
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation_journal import Journal
from repair_budget import claim_once
from staging import digest


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

    def test_input_precedes_dispatch_and_record_precedes_return(self):
        def runner(*args,**kw):
            self.assertEqual(b'code',(self.root/'case/inputs/main.py').read_bytes())
            return {'status':'rejected','cgroup_removed':True},{}
        j=Journal(self.root,stage_runner=runner)
        row,files=j.run_stage(None,'case',{'main.py':b'code'},('out',),runtime='python')
        self.assertEqual(row,json.loads((self.root/'case/stage-record.json').read_text()))
        self.assertEqual({},files)

    def test_cleanup_exception_retains_inputs_without_fabricating_result(self):
        j=Journal(self.root,stage_runner=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('cleanup')))
        with self.assertRaises(RuntimeError):j.run_stage(None,'case',{'main.py':b'code'},('out',))
        self.assertFalse((self.root/'case/stage-record.json').exists())
        self.assertFalse(json.loads((self.root/'case/exception.json').read_text())['cleanup_proven'])

    def test_host_control_is_journaled_before_policy_check(self):
        def runner(*a,**k):
            self.assertTrue((self.root/'host-control/inputs/control.py').exists())
            return {'exit':1,'reason':'failed'}
        j=Journal(self.root,control_runner=runner)
        self.assertEqual(1,j.run_control(None,None,'control','pass',5,900,memory=64)['exit'])
        self.assertTrue((self.root/'host-control/control-record.json').exists())

    def test_reusing_label_or_bad_names_refused(self):
        j=Journal(self.root,stage_runner=lambda *a,**k:({},{}))
        j.run_stage(None,'case',{'main.py':b'code'},())
        with self.assertRaises(FileExistsError):j.run_stage(None,'case',{'main.py':b'code'},())
        with self.assertRaises(ValueError):j.run_stage(None,'../other',{},())

    def budget(self):
        p=self.root/'budget.json';p.write_text(json.dumps(dict(started_epoch=100,deadline_epoch=1000,maximum_launches_including_supervisor=32)))
        return p,digest(p.read_bytes())

    def test_concurrent_claims_only_one_winner(self):
        p,sha=self.budget();dest=self.root/'claim'
        def go(_):
            try:claim_once(p,sha,dest,now=101);return True
            except FileExistsError:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(go,range(4)))
        self.assertEqual(1,sum(results))
        self.assertTrue(json.loads(dest.read_text())['supervisor_reserved'])

    def test_partial_claim_write_still_consumes_attempt(self):
        p,sha=self.budget();dest=self.root/'claim'
        with patch('repair_budget.json.dump',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):claim_once(p,sha,dest,now=101)
        self.assertTrue(dest.exists())
        with self.assertRaises(FileExistsError):claim_once(p,sha,dest,now=101)

    def test_identity_expiry_or_oversize_window_refused_before_claim(self):
        p,sha=self.budget();dest=self.root/'claim'
        for expected,now in (('0'*64,101),(sha,999),(sha,99)):
            with self.assertRaises(ValueError):claim_once(p,expected,dest,now=now)
            self.assertFalse(dest.exists())


if __name__=='__main__':unittest.main()
