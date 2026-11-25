"""Acceptance state-machine tests with a mocked cgroup/process; no live worker."""
import time
import unittest
from unittest.mock import MagicMock, patch

import evaluate as e
from staging import encode


class Acceptance(unittest.TestCase):
    def exercise(self, *, exit_code=0, reason=None, cleanup_error=False, startup_error=False):
        batch = e.Batch(time.time() + 100)
        root = MagicMock()
        group = root.__truediv__.return_value
        group.__truediv__.return_value.read_text.return_value = "populated 0"
        group.exists.return_value = False
        if cleanup_error:
            group.rmdir.side_effect = OSError("cannot remove")
        batch.root = root
        process = MagicMock(returncode=exit_code)
        wire = encode({"out.txt": b"actual output"})
        with patch.object(e, "read_values", return_value=e.ROOT_LIMITS), \
             patch.object(e.subprocess, "Popen", side_effect=OSError("startup") if startup_error else None,
                          return_value=process) as popen, \
             patch.object(e, "drain", return_value=(wire, b"", reason)), \
             patch.object(e, "decode", wraps=e.decode) as decode:
            if cleanup_error:
                with self.assertRaises(OSError):
                    e.run_stage(batch, "test", {"main.py": b"owned"}, ("out.txt",), case_deadline=batch.case())
                decode.assert_not_called()
                self.assertEqual(batch.records, [])
                return
            record, artifacts = e.run_stage(batch, "test", {"main.py": b"owned"}, ("out.txt",),
                                            case_deadline=batch.case())
            self.assertEqual(batch.launches, 2)
            self.assertEqual(popen.call_count, 1)
            group.rmdir.assert_called_once()
            if exit_code == 0 and reason is None and not startup_error:
                self.assertEqual(artifacts, {"out.txt": b"actual output"})
                self.assertEqual(record["status"], "accepted")
            else:
                self.assertEqual(artifacts, {})
                self.assertEqual(record["outputs"], {})
                decode.assert_not_called()

    def test_accept_only_after_exit_and_cleanup(self):
        self.exercise()

    def test_nonzero_exit_discards_complete_frames(self):
        self.exercise(exit_code=1)

    def test_deadline_discards_complete_frames(self):
        self.exercise(reason="deadline")

    def test_cleanup_failure_never_decodes_or_accepts(self):
        self.exercise(cleanup_error=True)

    def test_startup_failure_is_counted_and_cleaned(self):
        self.exercise(startup_error=True)
