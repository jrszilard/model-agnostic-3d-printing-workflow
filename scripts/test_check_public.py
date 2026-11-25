#!/usr/bin/env python3
"""Unit tests for scripts/check-public.py."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parent / "check-public.py"
SPEC = importlib.util.spec_from_file_location("check_public", SCRIPT)
assert SPEC and SPEC.loader
check_public = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_public)


class PublicGuardTests(unittest.TestCase):
    def _write(self, root: Path, rel: str, content: str | bytes = "ok\n") -> Path:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content, encoding="utf-8")
        return p

    def test_clean_tree_with_curated_example_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "README.md", "# Workflow\nMaintainer: Justin Szilard\n")
            self._write(root, "prusalink.env.example", "PRUSALINK=your-printer.local\nPRUSALINK_PASSWORD=<password>\n")
            self._write(root, "examples/clip/README.md", "Worked example clip.\n")
            self._write(root, "parts/_lib/sample.py", "VALUE = 1.0\n")
            self._write(root, "parts/_TEMPLATE/spec.yaml", "part_id: example/widget\n")
            self._write(root, "platform/pipeline/slice/testdata/sample.gcode", "; synthetic fixture\n")
            self.assertEqual(check_public.scan_tree(root), [])

    def test_blocks_personal_parts_and_print_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "parts/decor/private-hook/spec.yaml", "part_id: decor/private-hook\n")
            self._write(root, "build/plate/plate_1.gcode", "G28\n")
            self._write(root, "examples/clip/plate_1.gcode", "G28\n")
            self._write(root, "photoref/dog/img.jpg", b"\xff\xd8\xff")
            issues = check_public.scan_tree(root)
            joined = "\n".join(issues)
            self.assertIn("parts/decor/private-hook/spec.yaml", joined)
            self.assertIn("build/plate/plate_1.gcode", joined)
            self.assertIn("examples/clip/plate_1.gcode", joined)
            self.assertIn("photoref/dog/img.jpg", joined)

    def test_blocks_credentials_and_lan_ips(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "prusalink.env", "PRUSALINK=coreone.lan\n")
            self._write(root, "docs/note.md", "PRUSALINK_PASSWORD=" + "superSecret99" + "\n")
            self._write(root, "docs/token.md", "key = " + "ghp_" + "A" * 36 + "\n")
            self._write(root, "docs/ip.md", "printer at " + "192." + "168.1.42\n")
            issues = check_public.scan_tree(root)
            joined = "\n".join(issues)
            self.assertIn("prusalink.env", joined)
            self.assertIn("docs/note.md", joined)
            self.assertIn("docs/token.md", joined)
            self.assertIn("docs/ip.md", joined)

    def test_blocks_local_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "docs/a.md", "see " + "/home/" + "alice/projects/repo\n")
            self._write(root, "docs/b.md", "see " + "/Users/" + "alice/work\n")
            self._write(root, "docs/c.md", "see " + "lakeshore" + "-studio/notes\n")
            issues = check_public.scan_tree(root)
            self.assertEqual(len(issues), 3)

    def test_blocks_oversized_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root, "examples/clip/big.step", b"x" * 2048)
            issues = check_public.scan_tree(root, max_bytes=1024)
            self.assertTrue(any("exceeds public size cap" in i for i in issues))


if __name__ == "__main__":
    unittest.main()
