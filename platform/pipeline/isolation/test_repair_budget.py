import json
from pathlib import Path
import tempfile
import time
import unittest

from evaluate import Batch, namespace_command
from repair_budget import reserve, window


class RepairBudget(unittest.TestCase):
    def records(self, directory):
        budget = Path(directory, 'budget.json')
        closed = Path(directory, 'closed.json')
        budget.write_text(json.dumps({'deadline_epoch': 1000, 'started_epoch': 100, 'maximum_launches_including_supervisor': 32}))
        rows = [{} for _ in range(14)] + [{'label': 'runtime-freecad', 'status': 'rejected'}]
        closed.write_text(json.dumps({'batch_deadline_epoch': 1000, 'batch_closed': True, 'status': 'incomplete',
                                     'launches_including_supervisor': 16, 'records': rows, 'batch_finished_epoch': 200,
                                     'controls_passed_before_cad': True, 'cases': {}}))
        return budget, closed

    def test_one_shot_counts_failed_start_and_preserves_prior(self):
        with tempfile.TemporaryDirectory() as directory:
            budget, closed = self.records(directory)
            original = closed.read_bytes()
            value, path = reserve(budget, closed, now=500)
            self.assertEqual(value['carried_launches'], 16)
            self.assertEqual(value['launch_limit'], 29)
            self.assertTrue(value['reserved_supervisor'])
            # Even when no supervisor starts, the exclusive reservation remains spent.
            with self.assertRaises(FileExistsError):
                reserve(budget, closed, now=501)
            self.assertEqual(closed.read_bytes(), original)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_expired_missing_and_inconsistent_records_refuse(self):
        with tempfile.TemporaryDirectory() as directory:
            budget, closed = self.records(directory)
            with self.assertRaises(ValueError):
                reserve(budget, closed, now=999)
            record = json.loads(closed.read_text())
            record['launches_including_supervisor'] = 31
            closed.write_text(json.dumps(record))
            with self.assertRaises(ValueError):
                reserve(budget, closed, now=500)
            closed.unlink()
            with self.assertRaises(OSError):
                reserve(budget, closed, now=500)
            self.assertFalse(Path(directory, 'repair-reservation.json').exists())

    def test_outer_shutdown_fits_original_window(self):
        runtime, outer = window(1000, 500)
        self.assertLessEqual(runtime + 1, outer)
        self.assertLess(outer + 1, 500)
        with self.assertRaises(ValueError):
            window(1000, 999)

    def test_carried_budget_is_not_a_fresh_quota(self):
        batch = Batch(time.time()+100, carried_launches=16, launch_limit=29)
        self.assertEqual(batch.launches, 17)
        for _ in range(12):
            batch.reserve()
        with self.assertRaises(ValueError):
            batch.reserve()

    def test_only_freecad_gets_synthetic_identity_not_host_etc(self):
        tools = {'worker.py': 10, 'passwd': 11, 'group': 12}
        plain = namespace_command({'main.py': 13}, tools, 'python', None)
        freecad = namespace_command({'main.py': 13}, tools, 'freecad', None)
        self.assertNotIn('/etc/passwd', plain)
        self.assertNotIn('/etc', freecad)
        self.assertIn('/etc/passwd', freecad)
        self.assertIn('/etc/group', freecad)
        self.assertNotIn('/engine/passwd', freecad)
        self.assertNotIn('/engine/group', freecad)
        descriptors = [freecad[i+1] for i, value in enumerate(freecad) if value == '--ro-bind-data']
        self.assertEqual(len(descriptors), len(set(descriptors)), 'bwrap consumes each data FD once')
        self.assertNotIn('--bind', freecad)
        self.assertEqual(freecad[freecad.index('/etc/passwd')-2:freecad.index('/etc/passwd')], ['--ro-bind-data', '11'])
