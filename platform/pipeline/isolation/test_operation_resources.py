"""Mock kernel/process evidence ONLY. No CAD, subprocess or cgroup actions."""
import builtins
from contextlib import ExitStack, contextmanager
import os
import sys
import unittest
from unittest.mock import Mock, patch


@contextmanager
def guards():
 original=builtins.__import__
 def checked(name,*args,**kwargs):
  if name.split('.')[0] in {'cadquery','OCP','FreeCAD','Part','Mesh'}:
   raise AssertionError('native import forbidden')
  return original(name,*args,**kwargs)
 with ExitStack() as stack:
  stack.enter_context(patch('builtins.__import__',side_effect=checked))
  for name in ('subprocess.Popen','os.system','os.fork','os.posix_spawn','os.posix_spawnp'):
   stack.enter_context(patch(name,side_effect=AssertionError('process forbidden')))
  yield

with guards():
 import operation_resources as resources


class FakeKernel:
 """Explicit test double, never kernel measurement."""
 def __init__(self,*args):
  self.usage=0;self.pop=0;self.ident=('mock-boot','mock-mount',1,2);self.events=[]
 def identity(self):return self.ident
 def read(self,name):
  return f'usage_usec {self.usage}\n' if name=='cpu.stat' else f'populated {self.pop}\n'
 def kill(self):self.events.append('kill')
 def remove(self):self.events.append('remove')
 def close(self):self.events.append('close')


class ObserverTests(unittest.TestCase):
 def setUp(self):
  self.enterContext(guards());self.k=FakeKernel()
  self.enterContext(patch.object(resources,'LinuxGroup',return_value=self.k))
  self.o=resources.OperationObserver('/MOCK-NOT-A-CGROUP',resources.time.monotonic()+300)
  self.addCleanup(self.o.close)
 def test_order_final_before_remove_all_cpu_rejects(self):
  self.o.arm();self.k.usage=1200001
  child=Mock();child.wait.side_effect=lambda **kw:self.k.events.append('reap');self.o.register_child(child)
  def record(sample):
   self.assertEqual(1200001,sample['usage_usec']);self.k.events.append('durable-final')
  self.assertEqual(1200001,self.o.finish(record))
  self.assertEqual(['kill','reap','durable-final','remove'],self.k.events)
  with self.assertRaises(resources.ObservationError):self.o.arm()
  with self.assertRaises(resources.ObservationError):self.o.register_child(child)
 def test_dirty_initial_group(self):
  self.k.usage=1
  with self.assertRaises(resources.ObservationError):resources.OperationObserver('/MOCK',999999999)
 def test_replaced_identity(self):
  self.k.ident=('other',)
  with self.assertRaises(resources.ObservationError):self.o.sample()
 def test_regressing_counter(self):
  self.k.usage=9;self.o.sample();self.k.usage=8
  with self.assertRaises(resources.ObservationError):self.o.sample()
 def test_unknown_counter_never_zero(self):
  for raw in ('','usage_usec -1','usage_usec 1.0','usage_usec 1\nusage_usec 2'):
   with self.subTest(raw=raw),self.assertRaises(resources.ObservationError):resources.field(raw,'usage_usec')
 def test_populated_refuses_terminal(self):
  self.o.arm();self.k.pop=1;sink=Mock()
  with self.assertRaises(resources.ObservationError):self.o.finish(sink)
  sink.assert_not_called();self.assertNotIn('remove',self.k.events)
 def test_reap_failure_holds(self):
  self.o.arm();child=Mock();child.wait.side_effect=TimeoutError();self.o.register_child(child)
  with self.assertRaises(TimeoutError):self.o.finish(Mock())
  self.assertTrue(self.o.failed)
 def test_final_durability_failure_retains_counter(self):
  self.o.arm()
  with self.assertRaises(OSError):self.o.finish(Mock(side_effect=OSError('fsync')))
  self.assertNotIn('remove',self.k.events)
 def test_cleanup_failure_holds(self):
  self.o.arm();self.k.remove=Mock(side_effect=OSError())
  with self.assertRaises(OSError):self.o.finish(Mock())
  self.assertTrue(self.o.failed)
 def test_limit_monitor_reports_full_overrun(self):
  self.o.arm();self.k.usage=181000001;self.assertTrue(self.o.needs_stop())
  self.assertEqual(181000001,self.o.finish(Mock()))
 def test_deadline_fences_arm(self):
  self.o.deadline=0
  with self.assertRaises(resources.ObservationError):self.o.arm()
 def test_unarmed_no_terminal(self):
  with self.assertRaises(resources.ObservationError):self.o.finish(Mock())
 def test_abort_kill_failure_still_reaps_every_child_preserves_error(self):
  self.o.arm();one=Mock();two=Mock();original=OSError('original kill')
  one.wait.side_effect=TimeoutError('first child');self.o.register_child(one);self.o.register_child(two)
  with patch.object(self.k,'kill',side_effect=original):
   with self.assertRaises(OSError) as caught:self.o.abort()
  self.assertIs(caught.exception,original);one.wait.assert_called_once_with(timeout=3);two.wait.assert_called_once_with(timeout=3)
  self.assertTrue(self.o.failed);self.assertTrue(self.o.fenced);self.assertFalse(self.o.removed)
  self.assertNotIn('remove',self.k.events)
  with self.assertRaises(resources.ObservationError):self.o.finish(Mock())
 def test_abort_reap_failure_does_not_skip_later_child(self):
  self.o.arm();one=Mock();two=Mock();one.wait.side_effect=TimeoutError()
  self.o.register_child(one);self.o.register_child(two)
  with self.assertRaises(TimeoutError):self.o.abort()
  two.wait.assert_called_once_with(timeout=3);self.assertEqual(['kill'],self.k.events)
 def test_abort_never_claims_cleanup_even_when_empty(self):
  self.o.arm();self.o.abort()
  self.assertFalse(self.o.removed);self.assertTrue(self.o.failed)
  self.assertEqual(['kill'],self.k.events)
 def test_constructor_identity_failure_closes_owned_group(self):
  with patch.object(self.k,'identity',side_effect=OSError('identity')):
   with self.assertRaises(OSError):resources.OperationObserver('/MOCK',999999999)
  self.assertEqual(['close'],self.k.events)

class KernelInterfaceTests(unittest.TestCase):
 def setUp(self):
  self.enterContext(guards())
  self.group=object.__new__(resources.LinuxGroup);self.group.fd=77
 def test_counter_is_read_relative_to_anchor_and_closed(self):
  with patch.object(resources.os,'open',return_value=88) as opened,patch.object(resources.os,'read',return_value=b'usage_usec 19') as read,patch.object(resources.os,'close') as close:
   self.assertEqual('usage_usec 19',self.group.read('cpu.stat'))
   opened.assert_called_once_with('cpu.stat',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=77)
   read.assert_called_once_with(88,8193);close.assert_called_once_with(88)
 def test_kill_is_written_relative_to_anchor_and_short_write_refuses(self):
  with patch.object(resources.os,'open',return_value=88) as opened,patch.object(resources.os,'write',return_value=0),patch.object(resources.os,'close') as close:
   with self.assertRaises(resources.ObservationError):self.group.kill()
   opened.assert_called_once_with('cgroup.kill',os.O_WRONLY|os.O_NOFOLLOW,dir_fd=77)
   close.assert_called_once_with(88)
 def test_counter_read_bounded(self):
  with patch.object(resources.os,'open',return_value=88),patch.object(resources.os,'read',return_value=b'x'*8193),patch.object(resources.os,'close'):
   with self.assertRaises(resources.ObservationError):self.group.read('cpu.stat')

if __name__=='__main__':unittest.main()
