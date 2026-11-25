"""Offline contract tests; never launch namespaces, CAD or exhaustion controls."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('check_host', Path(__file__).with_name('check_host.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HostControlTests(unittest.TestCase):
    def test_exact_kernel_limits_required(self):
        module.verify_limits(dict(module.ROOT_LIMITS), module.ROOT_LIMITS)
        for key in module.ROOT_LIMITS:
            for bad in (None, 'max', '', '0'):
                actual = dict(module.ROOT_LIMITS, **{key:bad})
                if actual != module.ROOT_LIMITS:
                    with self.subTest(key=key,value=bad), self.assertRaises(RuntimeError):
                        module.verify_limits(actual, module.ROOT_LIMITS)
        with self.assertRaises(RuntimeError):
            module.verify_limits({}, module.ROOT_LIMITS)

    def test_budget_is_checked_before_any_cgroup_mutation_or_launch(self):
        with tempfile.TemporaryDirectory() as d, patch.object(module.time,'time',return_value=1000), patch.object(module.subprocess,'Popen') as spawn:
            root=Path(d)
            for deadline in (1000,1008,1901,float('inf'),float('nan'),True):
                with self.subTest(deadline=deadline), self.assertRaises(RuntimeError):
                    module.run_control(root,root/'input','unused','raise RuntimeError()',5,deadline)
            self.assertEqual(list(root.iterdir()),[])
            spawn.assert_not_called()

    def test_valid_and_invalid_local_bounds(self):
        with patch.object(module.time,'time',return_value=1000):
            module.check_budget(.5,1900,64*module.MiB)
            module.check_budget(30,1900,2048*module.MiB)
            for seconds in (0,-1,31,True,'5',float('nan'),float('inf')):
                with self.subTest(seconds=seconds), self.assertRaises(RuntimeError):
                    module.check_budget(seconds,1500,64*module.MiB)
            for memory in (0,True,1.0,2048*module.MiB+1):
                with self.subTest(memory=memory), self.assertRaises(RuntimeError):
                    module.check_budget(5,1500,memory)

    def test_namespace_flags_are_mandatory_not_try_fallbacks(self):
        command=module.namespace_command(Path('/tmp/canary'), 'print(1)')
        for flag in ('--unshare-user','--unshare-pid','--unshare-ipc','--unshare-uts','--unshare-net','--unshare-cgroup','--disable-userns','--assert-userns-disabled','--clearenv','--die-with-parent','--new-session'):
            self.assertIn(flag,command)
        self.assertFalse(any('try' in word for word in command))
        self.assertIn('--cap-drop',command)
        self.assertEqual(command[command.index('--cap-drop')+1],'ALL')

    def test_mounts_have_no_writable_host_checkout_or_etc(self):
        command=module.namespace_command(Path('/tmp/canary'), 'print(1)')
        self.assertNotIn('--bind',command)
        self.assertNotIn('--dev-bind',command)
        self.assertNotIn('/etc',command)
        self.assertNotIn('/home',command)
        self.assertEqual(command[command.index('--size')+1:command.index('--size')+4],['134217728','--tmpfs','/work'])
        self.assertEqual(command[-4:],['/usr/bin/python3','-I','-c','print(1)'])
        self.assertIn(['--remount-ro','/'],[command[i:i+2] for i in range(len(command)-1)])

    def test_fixed_control_sources_compile_without_running(self):
        for name in ('SMOKE','DISK','MEMORY','PIDS','LOG','DESCENDANT'):
            compile(getattr(module,name),name,'exec')


if __name__ == '__main__':
    unittest.main()
