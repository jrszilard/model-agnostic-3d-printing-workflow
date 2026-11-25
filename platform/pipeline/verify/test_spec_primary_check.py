"""Tests for the primary-artifact ratchet.

Every fixture is a real git repo carrying the repo's own untracked-namespace patterns, the
directory rules that sit beside them and the `releases/` re-includes, because the thing under test
is not our parsing — it is that we ask git and believe the answer, including when the answer is
"no". `FixtureRulesMirrorTheRepo` fails if `.gitignore` grows or loses a rule these fixtures do not
cover, so "all four infixes" and "negations are handled" stay true rather than being true on the
day they were written.
"""
import ast
import contextlib
import io
import json
import glob
import os
import subprocess
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from spec_primary_check import evaluate, find_specs, git_ignored, main  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

# Verbatim from .gitignore:102-109 — see FixtureRulesMirrorTheRepo.
GITIGNORE_RULES = [
    "**/*--draft-*.stl", "**/*--draft-*.step",
    "**/*--opt[0-9]*.stl", "**/*--opt[0-9]*.step",
    "**/*--test[0-9]*.stl", "**/*--test[0-9]*.step",
    "**/*--proto*.stl", "**/*--proto*.step",
]
# .gitignore:112-115 — a rule that only matches on the DIRECTORY part of the path. Without one of
# these in the fixture, asking git about the basename instead of the repo-relative path passes
# every other test in this file, which is the `.gitignore:100-101` incident all over again.
DIR_RULES = ["**/stl/assembly/", "**/stl/mockup/"]
# .gitignore:131-132 — `-v` prints these for a matching path and they mean the OPPOSITE.
REINCLUDE_RULES = ["!**/releases/**/*.stl", "!**/releases/**/*.step"]

GIT_ID = ["-c", "user.email=t@example.invalid", "-c", "user.name=test"]


def make_repo(tmp):
    subprocess.run(["git", "init", "-q", tmp], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(os.path.join(tmp, ".gitignore"), "w") as stream:
        stream.write("\n".join(GITIGNORE_RULES + DIR_RULES + REINCLUDE_RULES) + "\n")
    return tmp


def make_part(root, name, primaries=None, on_disk=(), spec_text=None, links=()):
    """One part dir: spec.yaml with the given primary keys, plus whichever files exist."""
    part = os.path.join(root, "parts", name)
    os.makedirs(part, exist_ok=True)
    if spec_text is None:
        lines = ["part_id: media/%s" % name, "units: mm"]
        for key, value in (primaries or {}).items():
            lines.append("%s: %s" % (key, json.dumps(value)))
        spec_text = "\n".join(lines) + "\n"
    with open(os.path.join(part, "spec.yaml"), "w") as stream:
        stream.write(spec_text)
    for rel in on_disk:
        path = os.path.join(part, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as stream:
            stream.write("solid x\nendsolid x\n")
    for link, target in links:
        path = os.path.join(part, link)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        os.symlink(target, path)
    return part


def kinds(result):
    """{(spec_dir_name, key): [IGNORED, MISSING]} — the shape assertions read against."""
    return {(os.path.basename(os.path.dirname(o["spec"])), o["key"]): o["kinds"]
            for o in result["offenses"]}


class FindSpecs(unittest.TestCase):
    def test_walks_nested_parts_and_keeps_the_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "cat/deep-part")
            make_part(tmp, "_TEMPLATE")
            cached = os.path.join(tmp, "parts", "cat", "deep-part", "__pycache__")
            os.makedirs(cached)
            with open(os.path.join(cached, "spec.yaml"), "w") as stream:
                stream.write("part_id: x\n")
            found = [os.path.relpath(p, tmp) for p in find_specs(tmp)]
            self.assertIn(os.path.join("parts", "cat", "deep-part", "spec.yaml"), found)
            self.assertIn(os.path.join("parts", "_TEMPLATE", "spec.yaml"), found)
            self.assertEqual(len(found), 2)


class TrackedAndPresent(unittest.TestCase):
    def test_a_released_primary_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "good", {"primary_stl": "stl/good.stl", "primary_step": "step/good.step"},
                      on_disk=("stl/good.stl", "step/good.step"))
            result = evaluate(tmp)
            self.assertTrue(result["passed"], result["offenses"])
            self.assertEqual(result["declared"], 2)
            self.assertEqual((result["undeclared"], result["fallbacks"]), (0, 0))

    def test_no_primary_keys_and_nothing_exported_yet_passes(self):
        # Declaring nothing stays legal — A1's exit 14 owns "this part has no artifact at all".
        # What is NOT legal is declaring nothing while the only export is a draft: see TheFallback.
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "silent")
            result = evaluate(tmp)
            self.assertTrue(result["passed"], result["offenses"])
            self.assertEqual((result["declared"], result["undeclared"], result["fallbacks"]),
                             (0, 1, 0))

    def test_a_reincluded_releases_primary_is_not_refused(self):
        # `git check-ignore -v` PRINTS the matching pattern even when it is a re-include, and exits
        # 1 (= not ignored). Reading that line as a match refused a shipped revision while quoting
        # `!**/releases/**/*.stl` as the reason a clone would not have it. .gitignore:97 makes
        # releases/ an immutable record on purpose.
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            rel = "parts/shipped/releases/r1/x--draft-a.stl"
            make_part(tmp, "shipped", {"primary_stl": "releases/r1/x--draft-a.stl"},
                      on_disk=("releases/r1/x--draft-a.stl",))
            self.assertEqual(subprocess.run(["git", "-C", tmp, "check-ignore", "--no-index",
                                             "-q", rel]).returncode, 1,
                             "premise: git itself says this path is NOT ignored")
            self.assertTrue(evaluate(tmp)["passed"], evaluate(tmp)["offenses"])


class TheGateFires(unittest.TestCase):
    def test_ignored_primary_that_exists_on_disk_still_fails(self):
        # The original defect exactly: the author's disk has it, a clean clone does not.
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "drafty", {"primary_stl": "stl/drafty--draft-a.stl"},
                      on_disk=("stl/drafty--draft-a.stl",))
            result = evaluate(tmp)
            self.assertFalse(result["passed"])
            self.assertEqual(kinds(result), {("drafty", "primary_stl"): ["IGNORED"]})
            self.assertIn(".gitignore:1", result["offenses"][0]["why"][0])

    def test_missing_primary_fails_on_its_own(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "gone", {"primary_step": "step/gone.step"})
            result = evaluate(tmp)
            self.assertFalse(result["passed"])
            self.assertEqual(kinds(result), {("gone", "primary_step"): ["MISSING"]})

    def test_ignored_and_missing_are_reported_separately(self):
        # The three real offenders are both at once; the report must not collapse them, or the
        # fix ("regenerate" vs "rename") reads as one action when it is two.
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "both", {"primary_stl": "stl/both--draft-a.stl"})
            result = evaluate(tmp)
            self.assertEqual(kinds(result), {("both", "primary_stl"): ["IGNORED", "MISSING"]})

    def test_all_four_infixes_are_covered(self):
        # We get these for free by asking git; this proves we actually do. --opt/--test carry a
        # [0-9] class, --proto has no trailing dash: three shapes, one authority.
        for infix in ("--draft-a", "--opt3", "--test7", "--proto"):
            with self.subTest(infix=infix), tempfile.TemporaryDirectory() as tmp:
                make_repo(tmp)
                for ext in ("stl", "step"):
                    make_part(tmp, "v%s%s" % (infix.strip("-"), ext),
                              {"primary_%s" % ext: "%s/v%s.%s" % (ext, infix, ext)},
                              on_disk=("%s/v%s.%s" % (ext, infix, ext),))
                result = evaluate(tmp)
                self.assertEqual(len(result["offenses"]), 2, result)
                for off in result["offenses"]:
                    self.assertEqual(off["kinds"], ["IGNORED"])

    def test_nested_directory_matches_the_way_git_says_it_does(self):
        # .gitignore:100-101: `parts/**/stl/*--draft-*.stl` did NOT match stl/coil-set/, and 202
        # variants stayed tracked. A regex reading of the rule gets this wrong; git does not.
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "nested", {"primary_stl": "stl/coil-set/n--draft-a.stl"},
                      on_disk=("stl/coil-set/n--draft-a.stl",))
            self.assertEqual(kinds(evaluate(tmp)), {("nested", "primary_stl"): ["IGNORED"]})

    def test_git_is_asked_about_the_repo_relative_path_not_the_basename(self):
        # `**/stl/mockup/` excludes on the DIRECTORY. Every other fixture here would answer the
        # same for a basename, so without this one, shortening the question to os.path.basename()
        # passes the whole suite — the `.gitignore:100-101` failure in a new costume.
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "mocked", {"primary_stl": "stl/mockup/m.stl"},
                      on_disk=("stl/mockup/m.stl",))
            self.assertEqual(git_ignored(tmp, ["m.stl"]), {},
                             "premise: the basename alone is not ignored")
            self.assertEqual(kinds(evaluate(tmp)), {("mocked", "primary_stl"): ["IGNORED"]})

    def test_a_primary_path_containing_a_space(self):
        # NUL framing (-z) rather than newline framing: a space in the name must not shear the
        # path in half and silently drop the offense.
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "spaced", {"primary_stl": "stl/two words--draft-a.stl",
                                      "primary_step": "step/two words.step"},
                      on_disk=("stl/two words--draft-a.stl", "step/two words.step"))
            result = evaluate(tmp)
            self.assertEqual(kinds(result), {("spaced", "primary_stl"): ["IGNORED"]})
            self.assertEqual(result["offenses"][0]["declared"], "stl/two words--draft-a.stl")

    def test_tracked_does_not_excuse_the_namespace(self):
        # THE failure path a default `git check-ignore` gets wrong: with the index consulted, a
        # force-added draft reports clean, so the gate's verdict would depend on local index
        # history — and DFM would still skip it, since verify.sh:20 keys off the NAME.
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            part = make_part(tmp, "forced", {"primary_stl": "stl/forced--draft-a.stl"},
                             on_disk=("stl/forced--draft-a.stl",))
            rel = os.path.relpath(os.path.join(part, "stl/forced--draft-a.stl"), tmp)
            subprocess.run(["git", "-C", tmp, "add", "-f", rel], check=True)
            subprocess.run(["git", "-C", tmp] + GIT_ID + ["commit", "-qm", "forced"], check=True,
                           stdout=subprocess.DEVNULL)
            self.assertEqual(subprocess.run(["git", "-C", tmp, "check-ignore", "-q", rel]).returncode,
                             1, "index-aware git calls this tracked file clean")
            self.assertEqual(kinds(evaluate(tmp)), {("forced", "primary_stl"): ["IGNORED"]})

    def test_a_symlink_cannot_launder_a_draft_name(self):
        # realpath() before asking git was an evasion: link a released x.stl in under a --draft-
        # name and the resolved target answers clean, while the name a clone would need is the
        # link's — and the link itself matches the rule, so the clone gets neither. .gitignore
        # matching is lexical, so the question has to be asked lexically.
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "laundered", {"primary_stl": "stl/l--draft-a.stl"},
                      on_disk=("stl/real.stl",), links=(("stl/l--draft-a.stl", "real.stl"),))
            self.assertEqual(kinds(evaluate(tmp)), {("laundered", "primary_stl"): ["IGNORED"]})

    def test_zero_specs_is_a_failure_not_a_pass(self):
        # A provenance gate at 0/16 specs and `green/*` tags at 0 created are this repo's recorded
        # disease. A green line over an empty corpus is how a gate joins that list unnoticed.
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            os.makedirs(os.path.join(tmp, "parts"))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main([tmp]), 1)
            self.assertIn("checked nothing", out.getvalue())
            self.assertIn("SPEC_PRIMARY_RESULT: FAIL", out.getvalue())


class TheFallback(unittest.TestCase):
    """verify.py:125-126 does not skip an undeclared primary — it picks one off the disk."""

    def test_declaring_nothing_does_not_hide_a_draft(self):
        # Measured 2026-09-04 on Justin's checkout: five parts that declare no primary resolve to
        # a --draft- STL and STEP this way, bottle-lamp-carrier among the plan's seven offenders.
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "quiet", on_disk=("stl/q--draft-a.stl", "step/q--draft-a.step"))
            result = evaluate(tmp)
            self.assertFalse(result["passed"])
            self.assertEqual(kinds(result), {("quiet", "primary_stl"): ["IGNORED"],
                                             ("quiet", "primary_step"): ["IGNORED"]})
            self.assertEqual((result["declared"], result["fallbacks"]), (0, 2))

    def test_a_released_fallback_is_not_an_offense(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "calm", on_disk=("stl/c.stl", "step/c.step"))
            result = evaluate(tmp)
            self.assertTrue(result["passed"], result["offenses"])
            self.assertEqual(result["fallbacks"], 2)

    def test_the_fallback_is_taken_per_key(self):
        # parts/vent/window-fan-adapter declares primary_stl and nothing else; its STEP still comes
        # from _pick. A per-SPEC test would call that spec "declared" and check only half of it.
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "half", {"primary_stl": "stl/h.stl"},
                      on_disk=("stl/h.stl", "step/h--draft-a.step"))
            result = evaluate(tmp)
            self.assertEqual(kinds(result), {("half", "primary_step"): ["IGNORED"]})
            self.assertEqual((result["declared"], result["fallbacks"]), (1, 1))

    def test_a_fallback_verify_py_would_not_take_is_not_reported(self):
        # _pick skips `coupon` names and `_` prefixes, so verify.py would find no STL here and
        # this gate must not invent one. Mirroring the rule loosely produces a refusal naming a
        # file the pipeline never touches.
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "couponly", on_disk=("stl/c-coupon--draft-a.stl",
                                                "stl/_scratch--draft-a.stl"))
            result = evaluate(tmp)
            self.assertTrue(result["passed"], result["offenses"])
            self.assertEqual(result["fallbacks"], 0)

    def test_the_refusal_names_declaring_a_primary_as_the_action(self):
        # A1's exit-14 note: a refusal with no action attached is a wall. The fallback's fix is
        # not the declared one's — nothing is misnamed here, something is unnamed.
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "quiet", on_disk=("stl/q--draft-a.stl",))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main([tmp]), 1)
            report = out.getvalue()
            self.assertIn("no primary_stl declared, so verify.py:125 uses -> stl/q--draft-a.stl",
                          report)
            self.assertIn("declare primary_stl in spec.yaml", report)

    def test_pick_mirrors_verify_py(self):
        # verify.sh:20-22 refuses to re-derive the primary for exactly this reason; we cannot
        # import verify.py (it needs FreeCAD's Part/Mesh at module scope) so the copy is pinned by
        # comparing ASTs. Comments and formatting may drift; the rule may not.
        def fn(path):
            with open(path, encoding="utf-8") as stream:
                tree = ast.parse(stream.read())
            found = [n for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef) and n.name == "_pick"]
            self.assertEqual(len(found), 1, "one _pick in %s" % path)
            return ast.dump(found[0])
        self.assertEqual(fn(os.path.join(HERE, "spec_primary_check.py")),
                         fn(os.path.join(HERE, "geometry.py")),
                         "geometry.py's _pick changed; copy it into spec_primary_check.py verbatim")


class Malformed(unittest.TestCase):
    def test_unparseable_spec_is_an_error_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "broken", spec_text="part_id: [unterminated\n")
            result = evaluate(tmp)
            self.assertFalse(result["passed"])
            self.assertEqual(result["offenses"], [])
            self.assertIn("cannot read spec", result["errors"][0])

    def test_non_string_primary_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "listy", spec_text="primary_stl: [a, b]\n")
            result = evaluate(tmp)
            self.assertFalse(result["passed"])
            self.assertIn("must be a path", result["errors"][0])

    def test_primary_escaping_the_repo_is_named_not_fatal(self):
        # git check-ignore exits 128 on a path outside the work tree, taking the whole batch with
        # it. Caught before the call so the other specs still get an answer.
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "escapee", {"primary_stl": "../../../../elsewhere.stl"})
            make_part(tmp, "fine", {"primary_stl": "stl/fine.stl"}, on_disk=("stl/fine.stl",))
            result = evaluate(tmp)
            self.assertFalse(result["passed"])
            self.assertIn("outside the repository", result["errors"][0])
            self.assertEqual(result["declared"], 1)

    def test_not_a_git_work_tree_fails_loudly(self):
        # A gate that cannot run must not print PASS — that indistinguishability is what let seven
        # specs sit unverified.
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "parts"))
            env = dict(os.environ, GIT_CEILING_DIRECTORIES=os.path.dirname(tmp))
            proc = subprocess.run([sys.executable,
                                   os.path.join(HERE, "spec_primary_check.py"), tmp],
                                  capture_output=True, text=True, env=env)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("not a git work tree", proc.stdout)
            self.assertIn("SPEC_PRIMARY_RESULT: FAIL", proc.stdout)
            self.assertNotIn("PASS", proc.stdout)


class ExitCodes(unittest.TestCase):
    def test_main_returns_0_clean_and_1_dirty(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            make_part(tmp, "ok", {"primary_stl": "stl/ok.stl"}, on_disk=("stl/ok.stl",))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main([tmp]), 0)
            self.assertIn("SPEC_PRIMARY_RESULT: PASS", out.getvalue())

            make_part(tmp, "bad", {"primary_stl": "stl/bad--proto.stl"},
                      on_disk=("stl/bad--proto.stl",))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main([tmp]), 1)
            report = out.getvalue()
            # A refusal that does not say what to do is a wall, not a gate (A1's exit-14 note).
            self.assertIn("parts/bad/spec.yaml: primary_stl -> stl/bad--proto.stl", report)
            self.assertIn("VARIANTS key", report)
            self.assertIn("SPEC_PRIMARY_RESULT: FAIL", report)


class GitIgnoredBatch(unittest.TestCase):
    def test_empty_input_launches_no_process(self):
        self.assertEqual(git_ignored("/nonexistent-repo", []), {})

    def test_a_git_failure_raises_rather_than_reading_as_clean(self):
        # rc 128 (here: a path outside the work tree) must never be mistaken for rc 1, "nothing
        # matched" — that is the difference between "no defect" and "no answer".
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            with self.assertRaises(RuntimeError):
                git_ignored(tmp, [os.path.join("..", "outside.stl")])

    def test_a_reinclude_match_is_not_an_ignore(self):
        # The trap in full, measured with git 2.x on 2026-09-04: `-v` changes what the EXIT CODE
        # means. Without it this query exits 1 ("none of the provided paths are ignored"); with it
        # the same query exits 0, because -v counts "matched a pattern" — negated or not. So
        # neither the exit code nor the presence of output separates an exclude from a re-include.
        # The `!` on the pattern is the only signal there is, which is why git_ignored reads it.
        with tempfile.TemporaryDirectory() as tmp:
            make_repo(tmp)
            rel = "parts/p/releases/r1/x--draft-a.stl"
            self.assertEqual(git_ignored(tmp, [rel]), {})
            raw = subprocess.run(["git", "-C", tmp, "check-ignore", "--no-index", "-v", "-z",
                                  "--stdin"], input=rel + "\0", capture_output=True, text=True)
            self.assertIn("!**/releases/**/*.stl", raw.stdout, "premise: -v prints the re-include")
            self.assertEqual(raw.returncode, 0, "premise: -v reports rc 0 for a re-include match")
            self.assertEqual(subprocess.run(["git", "-C", tmp, "check-ignore", "--no-index",
                                             "-q", rel]).returncode, 1,
                             "premise: without -v the same path is correctly rc 1, NOT ignored")


class FixtureRulesMirrorTheRepo(unittest.TestCase):
    def test_every_untracked_namespace_rule_is_in_the_fixtures(self):
        # `!` lines are excluded because they say the OPPOSITE of the rules this asserts, and they
        # are pinned separately below. Sweeping them in here made A3's primary re-includes read as
        # six new untracked namespaces and failed this test for adding tracking.
        namespace = [r for r in self.live()
                     if "--" in r and r.endswith((".stl", ".step")) and not r.startswith("!")]
        self.assertEqual(sorted(namespace), sorted(GITIGNORE_RULES),
                         "the untracked namespace changed; extend GITIGNORE_RULES and the "
                         "four-infix test with it")

    def test_every_declared_primary_has_a_reinclude(self):
        """The half of Option C that .gitignore states but cannot enforce.

        Option C keeps option studies untracked and re-includes exactly the artifact each spec
        points at. spec_primary_check.py already covers one direction: a primary with no re-include
        resolves to an ignored path and fails the run. This covers the other, which nothing else
        would notice -- a re-include that outlives the spec line it was written for goes on quietly
        tracking a draft nobody declares, which is how the 202-file class at `.gitignore:100-101`
        accumulated in the first place.
        """
        namespaced = ("--draft-", "--opt", "--test", "--proto")
        needed = set()
        for spec in find_specs(REPO_ROOT):
            with open(spec, encoding="utf-8") as stream:
                doc = yaml.safe_load(stream) or {}
            rel = os.path.relpath(os.path.dirname(spec), REPO_ROOT).replace(os.sep, "/")
            for key in ("primary_stl", "primary_step"):
                value = doc.get(key)
                if value and any(mark in value for mark in namespaced):
                    needed.add("!%s/%s" % (rel, value))
        # Scoped to part artifacts: .gitignore also re-includes .gitkeep files and slice testdata,
        # which are nobody's primary and would read as drift.
        have = {r for r in self.live()
                if r.startswith("!parts/") and r.endswith((".stl", ".step"))
                and "releases/" not in r}
        self.assertEqual(sorted(have), sorted(needed),
                         "a primary re-include and the spec it was written for have drifted apart")

    def test_the_directory_rules_and_releases_reincludes_still_exist(self):
        # Both fixture groups exist to make a specific bug fail: a basename-only question, and a
        # `!` pattern read as a match. If the live file drops them the tests keep passing while
        # testing nothing, so pin their presence rather than their exact set.
        live = self.live()
        for rule in DIR_RULES + REINCLUDE_RULES:
            self.assertIn(rule, live, "%s left .gitignore; re-aim the fixture that needs it" % rule)

    @staticmethod
    def live():
        with open(os.path.join(REPO_ROOT, ".gitignore")) as stream:
            return [ln.strip() for ln in stream if ln.strip() and not ln.startswith("#")]


class RealRepo(unittest.TestCase):
    def test_the_machinery_runs_against_this_repo(self):
        # Deliberately asserts no OFFENCE count: the three offenders are A3's to fix, and a test
        # pinned to them would go red the day they are fixed. What must hold either way is that
        # every spec parsed and git answered.
        result = evaluate(REPO_ROOT)
        self.assertEqual(result["errors"], [])
        self.assertGreater(result["specs"], 0)
        self.assertGreater(result["declared"], 0)


if __name__ == "__main__":
    unittest.main()
