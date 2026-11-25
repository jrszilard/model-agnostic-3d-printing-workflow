"""Offline tests: owned text/temp files and mocks, no namespaces or CAD."""
import fcntl
import io
import os
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import patch, Mock

import evaluate
import staging as s


class Bytes(unittest.TestCase):
    def test_round_trip_and_exact_hash(self):
        data = {"model.step": b"owned text, not CAD", "report.json": b"{}"}
        self.assertEqual(s.decode(s.encode(data), tuple(data)), data)
        with s.SealedInputs(data) as inputs:
            self.assertEqual(inputs.identities["model.step"]["sha256"], s.digest(data["model.step"]))
            self.assertEqual(os.read(inputs.fds["model.step"], 100), data["model.step"])
        self.assertEqual(inputs.fds, {})

    def test_seals_block_write_grow_shrink_and_seal_removal(self):
        with s.SealedInputs({"main.py": b"original"}) as inputs:
            fd = inputs.fds["main.py"]
            for action in (lambda: os.write(fd, b"bad"), lambda: os.ftruncate(fd, 1),
                           lambda: os.ftruncate(fd, 100),
                           lambda: fcntl.fcntl(fd, fcntl.F_ADD_SEALS, fcntl.F_SEAL_FUTURE_WRITE)):
                with self.assertRaises(OSError):
                    action()
            self.assertEqual(os.pread(fd, 8, 0), b"original")

    def test_input_name_count_and_size_limits(self):
        for inputs in ({}, {"../x": b"x"}, {"/x": b"x"}, {"a//x": b"x"},
                       {"A": b"x", "a": b"x"}, {"a": b"x", "a/b": b"x"},
                       {"x": b""}, {"x": bytearray(b"x")},
                       {"x": b"x" * (s.MAX_FILE + 1)},
                       {str(i): b"x" for i in range(s.MAX_INPUTS + 1)}):
            with self.subTest(keys=list(inputs)), self.assertRaises(ValueError):
                s.SealedInputs(inputs)
        with self.assertRaises(ValueError):
            s.SealedInputs({str(i): b"x" * s.MAX_FILE for i in range(3)})

    def test_reject_truncated_trailing_malformed_and_duplicate_frames(self):
        wire = s.encode({"a": b"hello", "b": b"world"})
        for bad in [wire[:i] for i in range(len(wire))] + [wire + b"x", b"\xff", b""]:
            with self.assertRaises(ValueError):
                s.decode(bad, ("a", "b"))
        for name, length in ((b"../x", 1), (b"\xff", 1), (b"z", 1), (b"a", s.MAX_TOTAL + 1), (b"a", 0)):
            with self.assertRaises(ValueError):
                s.decode(b"\x01" + struct.pack("!HQ", len(name), length) + name + b"x", ("a",))
        duplicate = b"\x02" + (struct.pack("!HQ", 1, 1) + b"a" + b"x") * 2
        with self.assertRaises(ValueError):
            s.decode(duplicate, ("a", "b"))

    def test_output_manifest_rejects_ambiguity_and_paths(self):
        for names in ((), ("x",) * 2, ("A", "a"), ("../x",), ("x/y",), tuple(str(i) for i in range(9))):
            with self.assertRaises(ValueError):
                s.output_names(names)


class Files(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.file = self.root / "original"
        self.file.write_bytes(b"original bytes")

    def test_owned_source_hash_and_path_mapping(self):
        data, mapping = s.source(self.root, "original", s.digest(b"original bytes"))
        self.assertEqual(mapping["owner"], str(self.root))
        self.assertEqual(mapping["path"], "original")
        self.assertEqual(data, b"original bytes")
        with self.assertRaises(ValueError):
            s.source(self.root, "original", "0" * 64)
        with s.SealedInputs({"base.step": data}) as sealed:
            self.file.write_bytes(b"replacement")
            self.assertEqual(os.pread(sealed.fds["base.step"], 100, 0), b"original bytes")

    def test_links_specials_ancestors_empty_and_oversize(self):
        link = self.root / "link"
        link.symlink_to(self.file)
        hard = self.root / "hard"
        os.link(self.file, hard)
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        for path in (link, hard, self.file, fifo, self.root):
            with self.subTest(path=path), self.assertRaises((ValueError, OSError)):
                s.read_regular(path)
        hard.unlink()
        self.assertEqual(s.read_regular(self.file), b"original bytes")
        with self.assertRaises(ValueError):
            s.read_regular(self.file, maximum=2)
        ancestor = self.root / "alias"
        ancestor.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            s.read_regular(ancestor / "original")
        self.file.write_bytes(b"")
        with self.assertRaises(ValueError):
            s.read_regular(self.file)

    def test_output_collection_needs_exact_regular_files(self):
        self.assertEqual(s.collect(self.root, ("original",)), {"original": b"original bytes"})
        (self.root / "extra").write_bytes(b"x")
        with self.assertRaises(ValueError):
            s.collect(self.root, ("original",))


class BudgetAndProfile(unittest.TestCase):
    def test_reservation_exhaustion_closed_expired_and_failed_start(self):
        batch = evaluate.Batch(time.time() + 100)
        with patch.object(evaluate.subprocess, "Popen", side_effect=OSError("startup")):
            batch.reserve()  # reservation survives an attempted startup failure
            try:
                evaluate.subprocess.Popen([])
            except OSError:
                pass
        self.assertEqual(batch.launches, 2)
        for _ in range(30):
            batch.reserve()
        with self.assertRaises(ValueError):
            batch.reserve()
        batch.close()
        with self.assertRaises(ValueError):
            batch.reserve()
        for deadline in (True, float("inf"), float("nan"), time.time() - 1, time.time() + 901):
            with self.assertRaises(ValueError):
                evaluate.Batch(deadline)
        batch = evaluate.Batch(time.time() + 100)
        batch.ends = time.monotonic() - 1
        with self.assertRaises(ValueError):
            batch.reserve()

    def test_mandatory_namespace_ro_inputs_and_no_checkout(self):
        command = evaluate.namespace_command({"main.py": 20}, {"worker.py": 21}, "python", None)
        for flag in ("--unshare-user", "--unshare-pid", "--unshare-net", "--unshare-cgroup",
                     "--disable-userns", "--assert-userns-disabled", "--clearenv", "--cap-drop"):
            self.assertIn(flag, command)
        self.assertNotIn("--bind", command)
        self.assertNotIn("/etc", command)
        self.assertNotIn("/home", command)
        self.assertEqual(command.count("--ro-bind-data"), 2)
        self.assertNotEqual(evaluate.SCHEMA, 1)
        with self.assertRaises(ValueError):
            evaluate.command_for("shell")

    def test_eof_before_exit_waits_to_deadline(self):
        # No processes started. Simulate both streams EOF while process is still living.
        stdout, stderr = Mock(), Mock()
        stdout.fileno.return_value, stderr.fileno.return_value = 30, 31
        process = Mock(stdout=stdout, stderr=stderr)
        process.poll.return_value = None
        poller = Mock()
        poller.__enter__ = Mock(return_value=poller)
        poller.__exit__ = Mock(return_value=None)
        poller.get_map.return_value = {}
        poller.select.return_value = []
        with patch.object(evaluate.selectors, "DefaultSelector", return_value=poller), \
             patch.object(evaluate.os, "set_blocking"), \
             patch.object(evaluate.time, "monotonic", side_effect=[1, 2, 4]):
            wire, logs, reason = evaluate.drain(process, 3)
        self.assertEqual((wire, logs, reason), (b"", b"", "deadline"))
        self.assertGreater(process.poll.call_count, 1)


if __name__ == "__main__":
    unittest.main()
