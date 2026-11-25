import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import prepare


class CacheAndBoundedPassTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.part = self.root / "parts/a"; self.part.mkdir(parents=True)
        self.out = self.root / "build/plate"; self.out.mkdir(parents=True)
        self.job = prepare.Preparation(self.root, {}, self.part, self.out, {}, {})
        self.artifact = self.out / "result.txt"; self.counter = self.out / "calls.txt"
        script = (f"from pathlib import Path; p=Path({str(self.counter)!r}); "
                  "n=int(p.read_text())+1 if p.exists() else 1; p.write_text(str(n)); "
                  f"Path({str(self.artifact)!r}).write_text('result '+str(n))")
        self.command = [sys.executable, "-c", script]

    def stage(self, key=None):
        return self.job.stage("example", key or {"source": "a", "tool": "b", "config": "c"},
                              [self.command], [self.artifact])

    def test_unchanged_inputs_reuse_without_invocation(self):
        self.assertTrue(self.stage()); self.assertTrue(self.stage())
        self.assertEqual(self.counter.read_text(), "1")
        self.assertEqual(self.job.events[-1]["action"], "reuse")

    def test_each_source_dependency_tool_config_change_invalidates(self):
        for field in ("source", "dependency", "tool", "config", "profile", "post_hook"):
            self.assertTrue(self.stage({field: "one"})); before = int(self.counter.read_text())
            self.assertTrue(self.stage({field: "two"}))
            self.assertEqual(int(self.counter.read_text()), before + 1)

    def test_missing_or_tampered_artifact_invalidates(self):
        self.stage(); self.artifact.unlink(); self.stage()
        self.artifact.write_text("tampered"); self.stage()
        self.assertEqual(self.counter.read_text(), "3")

    def test_incomplete_output_manifest_is_not_reusable(self):
        self.stage()
        self.job.state["stages"]["example"]["outputs"] = {}
        self.stage(); self.assertEqual(self.counter.read_text(), "2")

    def test_failed_command_cannot_reuse_old_success(self):
        self.stage()
        self.assertFalse(self.job.stage("example", {"changed": True},
            [[sys.executable, "-c", "raise SystemExit(7)"]], [self.artifact]))
        self.assertNotIn("example", self.job.state["stages"])
        self.assertFalse(self.artifact.exists())
        self.assertIn("exit 7", self.job.problems[-1])

    def test_success_without_required_output_fails_not_inherits_old_file(self):
        self.stage()
        self.assertFalse(self.job.stage("example", {"changed": True},
            [[sys.executable, "-c", "pass"]], [self.artifact]))
        self.assertIn("missing required outputs", self.job.problems[-1])

    def test_zero_support_plot_is_still_required(self):
        image = self.out / "supports.png"
        self.assertFalse(self.job.stage("supports", {"support": 0},
            [[sys.executable, "-c", "pass"]], [image]))
        self.assertIn("supports.png", self.job.problems[-1])

    def test_source_and_plate_location_are_frozen(self):
        self.job.save()
        with self.assertRaisesRegex(ValueError, "relocated"):
            prepare.Preparation(self.root / "linked", {}, self.part, self.out, {}, {})

    def test_only_one_targeted_repair_then_explicit_escalation(self):
        prepare.attempt_allowed({})
        with self.assertRaisesRegex(ValueError, "repair-reason"):
            prepare.attempt_allowed({"failed_attempts": 1})
        prepare.attempt_allowed({"failed_attempts": 1}, repair="correct missing dependency")
        with self.assertRaisesRegex(ValueError, "escalate-reason"):
            prepare.attempt_allowed({"failed_attempts": 2}, repair="another lap")
        prepare.attempt_allowed({"failed_attempts": 2}, escalation="specific blocker, changed input, next action")

    def test_no_changed_input_means_no_repeat_even_with_escalation(self):
        with self.assertRaisesRegex(ValueError, "no relevant input"):
            prepare.attempt_allowed({"failed_attempts": 1}, repair="same pass", changed=False)
        with self.assertRaises(ValueError):
            prepare.attempt_allowed({"failed_attempts": 2}, escalation="same pass", changed=False)

    def test_approval_and_force_bypasses_are_not_inherited(self):
        with patch.dict(prepare.os.environ, {"APPROVED": "1", "FORCE": "1", "UNSTAMPED_OK": "1"}):
            job = prepare.Preparation(self.root, {}, self.part, self.out, {}, {})
        self.assertNotIn("APPROVED", job.env); self.assertNotIn("FORCE", job.env)
        self.assertNotIn("UNSTAMPED_OK", job.env)

    def test_failed_preparation_removes_handoff_authority(self):
        for name in ("handoff.txt", "qualification_manifest.json"):
            (self.out / name).write_text("old authority")
        self.job.problems.append("failed slice")
        with patch.object(self.job, "attempt_identity", return_value="blocked"):
            self.assertEqual(self.job.finish(prepare.time.monotonic(), "before"), 1)
        self.assertFalse((self.out / "handoff.txt").exists())
        self.assertFalse((self.out / "qualification_manifest.json").exists())
        self.assertEqual(json.loads(self.job.path.read_text())["status"], "BLOCKED")

    def test_resource_bytes_not_mtime_control_cache(self):
        profile = self.root / "profile.ini"; profile.write_text("layer_height=0.2")
        first = prepare.resource_hash([str(profile)])
        prepare.os.utime(profile, (1, 1))
        self.assertEqual(first, prepare.resource_hash([str(profile)]))
        profile.write_text("layer_height=0.3"); prepare.os.utime(profile, (1, 1))
        self.assertNotEqual(first, prepare.resource_hash([str(profile)]))

    def test_slice_options_cannot_redirect_paths_or_hide_postprocessors(self):
        for args in (["build/elsewhere"], ["--spec", "another/spec.yaml"],
                     ["--set", "post_process=send.sh"], ["--set"], ["--unknown"],
                     ["--set", "bad" + chr(10) + "second=value"]):
            with self.subTest(args=args), self.assertRaises(ValueError):
                prepare.validate_slice_args(args)
        prepare.validate_slice_args(["--machine", "Example", "--infill", "15", "--set", "perimeters=2"])

    def test_colour_regions_must_be_declared_outputs(self):
        ok = {"parts/x/stl/x-white.stl"}
        prepare.validate_slice_args(["--colour", "parts/x/stl/x-white.stl=2",
                                     "--colour-names", "black,white"], ok)
        with self.assertRaises(ValueError):
            prepare.validate_slice_args(["--colour-names", "black;send.sh"], ok)
        for value in ("parts/elsewhere/white.stl=2", "parts/x/stl/x-white.stl=1",
                      "parts/x/stl/x-white.stl", "parts/x/stl/x-white.stl=b"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                prepare.validate_slice_args(["--colour", value], ok)

    def test_check_discovery_directory_is_bound_not_just_one_test_file(self):
        qa = self.part / "qa"; qa.mkdir(); (qa / "test_one.py").write_text("# test one")
        recipe = {"checks": [["python", "-m", "unittest", "discover", "-s", "{part}/qa"]]}
        first = prepare.check_input_snapshot(self.root, self.part, recipe, sys.executable)
        (qa / "test_new.py").write_text("# a newly discovered test must invalidate verify reuse")
        self.assertNotEqual(first, prepare.check_input_snapshot(self.root, self.part, recipe, sys.executable))

    def test_interrupted_pass_requires_a_reasoned_repair(self):
        self.job.state["status"] = "PREPARING"; self.job.save()
        resumed = prepare.Preparation(self.root, {}, self.part, self.out, {}, {})
        self.assertEqual(resumed.state["failed_attempts"], 1)
        with self.assertRaises(ValueError): prepare.attempt_allowed(resumed.state)

    def test_preflight_surfaces_the_actual_design_gate_without_building(self):
        import contextlib
        self.part = self.root / 'parts/demo'; self.part.mkdir()
        (self.part/'prepare.yaml').write_text('schema: 1\nkind: prototype\nobjective: Fit test\nstop_condition: Review\nplate: build/demo\nprofile_resources: []\nslice_args: []\n')
        (self.part/'spec.yaml').write_text('part_id: demo\nstatus: draft\ndesign:\n  schema: 1\n  mode: originate\n  references: [{id: art, role: form, evidence: [drawing]}]\n')
        # Only stub Git/tool discovery; run real YAML loading, real preflight and real qualification.
        with contextlib.ExitStack() as stack:
            for obj, name, val in [(prepare.scope, 'repo_root', self.root), (prepare.scope, 'canonical_root', self.root),
                                   (prepare.scope, 'assert_committed', []), (prepare.producer, 'build_inputs', {'files': []}),
                                   (prepare.producer, 'interpreter_identity', {}), (prepare, 'executable', {})]:
                stack.enter_context(patch.object(obj, name, return_value=val))
            with self.assertRaisesRegex(ValueError, r'design.references\[0\].role must be source, interface, or standard'):
                prepare.preflight(self.root, self.part/'prepare.yaml')
        self.assertFalse((self.root/'build/demo').exists())

    def test_missing_profile_resource_fails(self):
        with self.assertRaisesRegex(ValueError, "missing tool/profile"):
            prepare.resource_hash([str(self.root / "absent")])


if __name__ == "__main__":
    unittest.main()
