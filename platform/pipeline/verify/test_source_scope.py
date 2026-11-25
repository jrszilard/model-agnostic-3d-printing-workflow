"""Source/dependency and producer freshness regressions (isolated temporary repositories)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

import source_scope as scope
from provenance_fixture import fixture_producer, producer


class SourceScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "owner"; self.root.mkdir()
        self.external = Path(self.tmp.name) / "external"; self.external.mkdir()
        for root in (self.root, self.external):
            scope.git(root, "init", "-q"); scope.git(root, "config", "user.email", "test@example.com")
            scope.git(root, "config", "user.name", "Test")
            (root / ".gitignore").write_text("build/\n__pycache__/\n")
        self.part = self.root / "parts/selected"; (self.part / "src").mkdir(parents=True)
        (self.part / "stl").mkdir(); (self.part / "step").mkdir()
        (self.part / "src/generate.py").write_text("# selected source\n")
        (self.part / "stl/model.stl").write_bytes(b"synthetic STL")
        (self.part / "step/model.step").write_bytes(b"synthetic STEP")
        self.shared = self.root / "parts/shared/parameter.py"; self.shared.parent.mkdir()
        self.shared.write_text("WIDTH = 8\n")
        (self.external / "library.py").write_text("RADIUS = 4\n")
        self.spec = {"primary_stl": "stl/model.stl", "primary_step": "step/model.step",
                     "build": {"source": "src/generate.py"}, "source_dependencies": [
                         {"repository": ".", "paths": ["parts/shared/parameter.py"]},
                         {"repository": "../external", "paths": ["library.py"]}]}
        self.save_spec(); self.checkpoint()

    def save_spec(self):
        (self.part / "spec.yaml").write_text(yaml.safe_dump(self.spec))

    def checkpoint(self):
        fixture_producer(self.root, self.part)
        for root in (self.root, self.external):
            scope.git(root, "add", "-A"); scope.git(root, "commit", "--allow-empty", "-qm", "fixture")

    def test_committed_scope_records_both_repositories_and_outputs(self):
        _, identity = producer.validate(self.part, require_committed=True)
        self.assertFalse(identity["dirty"])
        self.assertEqual({r["repository"] for r in identity["repositories"]}, {".", "../external"})
        self.assertTrue(all(len(r["commit"]) == 40 for r in identity["repositories"]))

    def test_unrelated_tracked_dirty_untracked_and_docs_do_not_invalidate(self):
        unrelated = self.root / "parts/other.py"; unrelated.write_text("initial\n")
        scope.git(self.root, "add", str(unrelated)); scope.git(self.root, "commit", "-qm", "other part")
        unrelated.write_text("leave my work alone\n")
        untracked = self.root / "parts/new.py"; untracked.write_text("draft\n")
        docs = self.root / "README.md"; docs.write_text("unrelated context\n")
        before = {p: p.read_bytes() for p in (unrelated, untracked, docs)}
        producer.validate(self.part, require_committed=True)
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assertEqual(scope.git(self.root, "diff", "--cached", "--name-only"), "")

    def test_changed_generator_with_old_committed_export_is_stale(self):
        (self.part / "src/generate.py").write_text("# changed generator, old STL\n")
        scope.git(self.root, "add", "parts"); scope.git(self.root, "commit", "-qm", "stale export")
        with self.assertRaisesRegex(ValueError, "changed since build"):
            producer.validate(self.part, require_committed=True)

    def test_dirty_cross_part_and_external_inputs_fail(self):
        for p in (self.shared, self.external / "library.py"):
            original = p.read_bytes(); p.write_bytes(original + b"# changed\n")
            with self.assertRaisesRegex(ValueError, "changed since build"):
                producer.validate(self.part, require_committed=True)
            p.write_bytes(original)

    def test_untracked_declared_dependency_cannot_be_checkpointed(self):
        p = self.external / "new.py"; p.write_text("NEW = True\n")
        self.spec["source_dependencies"][1]["paths"].append("new.py")
        self.save_spec(); fixture_producer(self.root, self.part)
        scope.git(self.root, "add", "parts"); scope.git(self.root, "commit", "-qm", "declare input")
        with self.assertRaisesRegex(ValueError, "not committed: new.py"):
            producer.validate(self.part, require_committed=True)

    def test_assume_unchanged_cannot_hide_actual_dirty_input(self):
        scope.git(self.root, "update-index", "--assume-unchanged", "parts/shared/parameter.py")
        self.shared.write_text("WIDTH = 99\n")
        rows = scope.snapshot(self.root, {self.root: {self.shared}})
        with self.assertRaisesRegex(ValueError, "uncommitted change"):
            scope.assert_committed(self.root, rows)

    def test_deleted_or_modified_export_fails(self):
        p = self.part / "stl/model.stl"; original = p.read_bytes()
        for value in (b"changed", None):
            if value is None: p.unlink()
            else: p.write_bytes(value)
            with self.assertRaises(ValueError): producer.validate(self.part)
            p.write_bytes(original)

    def test_missing_producer_fails(self):
        scope.producer_path(self.root, self.part).unlink()
        with self.assertRaisesRegex(ValueError, "missing build provenance"):
            producer.validate(self.part)

    def test_invalid_escaping_missing_glob_and_symlink_declarations_fail(self):
        link = self.root / "parts/link"; link.symlink_to(self.external, target_is_directory=True)
        cases = ["../external/library.py", "/tmp/file", "parts/missing.py", "parts/*.py",
                 ":(glob)parts/*", "parts/link/library.py", "."]
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                scope.local_path(self.root, value)
        for value in ({}, [{"repository": ".", "paths": []}],
                      [{"repository": ".", "paths": ["parts/shared/parameter.py"], "extra": True}],
                      [{"repository": "parts/shared", "paths": ["parameter.py"]}]):
            self.spec["source_dependencies"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                scope.declarations(self.root, self.part, self.spec)

    def test_source_directory_symlink_cannot_hide_a_dependency(self):
        (self.part / "src/hidden").symlink_to(self.external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            producer.build_inputs(self.root, self.part, self.spec)

    def test_relocated_record_fails(self):
        path = scope.producer_path(self.root, self.part); data = json.loads(path.read_text())
        data["owner_root"] = "/historical/worktree"
        producer.atomic_json(path, data)
        with self.assertRaisesRegex(ValueError, "relocated"):
            producer.validate(self.part)

    def test_git_hook_environment_cannot_redirect_dependency_identity(self):
        with patch.dict(os.environ, {"GIT_DIR": str(self.root / ".git"), "GIT_WORK_TREE": str(self.root)}):
            self.assertEqual(scope.repo_root(self.external), self.external)
            producer.validate(self.part, require_committed=True)

    def test_wrong_root_detected_before_generation(self):
        worktree = Path(self.tmp.name) / "linked"
        scope.git(self.root, "worktree", "add", "-q", "-b", "linked", str(worktree))
        self.assertEqual(scope.canonical_root(worktree), self.root)
        self.assertNotEqual(scope.canonical_root(worktree), worktree)

    def test_producer_tool_change_invalidates(self):
        with patch.object(producer, "tools_snapshot", return_value=[]):
            with self.assertRaisesRegex(ValueError, "changed since build"):
                producer.validate(self.part)

    def test_noop_generator_cannot_rebind_old_outputs(self):
        result = subprocess.run([sys.executable, str(producer.HERE / "build_provenance.py"), "run",
            str(self.part / "src/generate.py"), str(self.part / "stl")], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("did not produce", result.stderr)
        self.assertFalse(scope.producer_path(self.root, self.part).exists())

    def test_observed_undeclared_read_is_rejected(self):
        secret = self.root / "parts/undeclared.txt"; secret.write_text("genuine input\n")
        (self.part / "src/generate.py").write_text(
            f"from pathlib import Path\nPath({str(secret)!r}).read_text()\n")
        result = subprocess.run([sys.executable, str(producer.HERE / "build_provenance.py"), "run",
            str(self.part / "src/generate.py"), str(self.part / "stl")], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("undeclared", result.stderr)
        self.assertIn(str(secret), result.stderr)


if __name__ == "__main__":
    unittest.main()
