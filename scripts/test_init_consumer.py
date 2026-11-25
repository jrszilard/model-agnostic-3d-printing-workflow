#!/usr/bin/env python3
"""Tests for scripts/init-consumer.sh and the consumer wrapper template."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

WORKFLOW_ROOT = Path(__file__).resolve().parent.parent
INIT_SCRIPT = WORKFLOW_ROOT / "scripts" / "init-consumer.sh"


class InitConsumerTests(unittest.TestCase):
    def test_scaffolds_and_invokes_workflow_wrappers(self):
        with tempfile.TemporaryDirectory() as tmp:
            consumer = Path(tmp) / "my-parts"
            res = subprocess.run(
                [str(INIT_SCRIPT), "--platform-root", str(WORKFLOW_ROOT), str(consumer)],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Initializing consumer", res.stdout)
            self.assertTrue((consumer / "platform.consumer.yaml").is_file())
            self.assertEqual(
                (consumer / "PLATFORM_VERSION").read_text(encoding="utf-8").strip(),
                (WORKFLOW_ROOT / "VERSION").read_text(encoding="utf-8").strip(),
            )

            plate = consumer / "build" / "demo-plate"
            plate.mkdir(parents=True)
            (plate / "plate.3mf").write_bytes(b"demo")

            out = subprocess.run(
                [str(consumer / "scripts/platform/next-action.sh"), str(plate), "--json"],
                text=True,
                capture_output=True,
                check=True,
            )
            data = json.loads(out.stdout)
            self.assertEqual(data["schema"], 1)
            self.assertEqual(data["action"], "review_project")
            self.assertTrue(data["stop"])

    def test_version_mismatch_fails_loudly_unless_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            consumer = Path(tmp) / "my-parts"
            subprocess.run(
                [str(INIT_SCRIPT), "--platform-root", str(WORKFLOW_ROOT), str(consumer)],
                check=True,
                capture_output=True,
            )
            (consumer / "PLATFORM_VERSION").write_text("0.0.1\n", encoding="utf-8")

            fail = subprocess.run(
                [str(consumer / "scripts/platform/next-action.sh"), "--help"],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(fail.returncode, 0)
            self.assertIn("VERSION mismatch", fail.stderr)

            env = os.environ.copy()
            env["PLATFORM_VERSION_ALLOW_MISMATCH"] = "1"
            ok = subprocess.run(
                [str(consumer / "scripts/platform/next-action.sh"), "--help"],
                text=True,
                capture_output=True,
                env=env,
            )
            self.assertEqual(ok.returncode, 0)

    def test_does_not_overwrite_existing_files_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            consumer = Path(tmp) / "my-parts"
            subprocess.run(
                [str(INIT_SCRIPT), "--platform-root", str(WORKFLOW_ROOT), str(consumer)],
                check=True,
                capture_output=True,
            )
            manifest = consumer / "platform.consumer.yaml"
            manifest.write_text("# custom consumer config\n", encoding="utf-8")

            subprocess.run(
                [str(INIT_SCRIPT), "--platform-root", str(WORKFLOW_ROOT), str(consumer)],
                check=True,
                capture_output=True,
            )
            self.assertEqual(manifest.read_text(encoding="utf-8"), "# custom consumer config\n")

            subprocess.run(
                [str(INIT_SCRIPT), "--force", "--platform-root", str(WORKFLOW_ROOT), str(consumer)],
                check=True,
                capture_output=True,
            )
            self.assertIn("entrypoints:", manifest.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
