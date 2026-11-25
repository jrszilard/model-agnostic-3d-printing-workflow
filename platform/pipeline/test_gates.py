#!/usr/bin/env python3
"""Conformance tests for gates.txt.

A registry that drifts is worse than no registry: it reads like an index, so the next agent trusts
it instead of grepping, and is then confidently wrong. That is not hypothetical here — 2026-09-06
lost three days to a session note asserting a blocker that had stopped being true, and half a day to
a hand-maintained belief about which gates required PASS. So the registry is not maintained by
discipline. These tests derive the truth from the tree and fail when the file disagrees:

  * every token EMITTED anywhere has a row
  * every token SCRAPED anywhere has a row
  * every row's emitter really emits it
  * every declared exit code really appears in the file said to raise it
  * the shell and Python readers agree, verdict for verdict

Add a token without a row and this fails. Retire a gate without deleting its row and this fails.
"""
from __future__ import annotations

import os
import re
import subprocess
import unittest

import gates

HERE = os.path.dirname(os.path.realpath(__file__))
ROOT = os.path.realpath(os.path.join(HERE, ".."))
TOKEN = re.compile(r"\b([A-Z][A-Z0-9_]*_RESULT)\b")
# The registry describes the pipeline's own gates. A consumer's local checker may print its own
# token; those are not this file's business, so the scan stays inside the pipeline tree.
SCAN = ("pipeline",)


def sources():
    for top in SCAN:
        for base, _dirs, names in os.walk(os.path.join(ROOT, top)):
            if "__pycache__" in base:
                continue
            for name in names:
                if name.endswith((".py", ".sh")) and not name.startswith("test_"):
                    yield os.path.join(base, name)


def tokens_in(path, pattern):
    with open(path, encoding="utf-8", errors="replace") as stream:
        return set(pattern.findall(stream.read()))


class RegistryMatchesTheTree(unittest.TestCase):
    def setUp(self):
        self.gates = gates.load()

    def test_every_emitted_token_is_registered(self):
        """The failure this whole file exists for: a gate nobody listed."""
        emitted = re.compile(r'(?:print\(|echo )\s*[\'"]?([A-Z][A-Z0-9_]*_RESULT):')
        missing = {}
        for path in sources():
            for token in tokens_in(path, emitted):
                if token not in self.gates:
                    missing.setdefault(token, []).append(os.path.relpath(path, ROOT))
        self.assertEqual(missing, {},
                         "tokens emitted but absent from gates.txt — add a row deciding which "
                         "verdicts pass: %s" % missing)

    def test_every_scraped_token_is_registered(self):
        """A consumer reading a token nobody registered is a gate with an undocumented contract."""
        scraped = re.compile(r"grep -q(?:E)? ['\"]?\(?([A-Z][A-Z0-9_]*_RESULT):")
        missing = {}
        for path in sources():
            for token in tokens_in(path, scraped):
                if token not in self.gates:
                    missing.setdefault(token, []).append(os.path.relpath(path, ROOT))
        self.assertEqual(missing, {}, "tokens consumed but absent from gates.txt: %s" % missing)

    def test_each_row_names_a_file_that_really_emits_it(self):
        for token, gate in self.gates.items():
            path = os.path.join(ROOT, "..", gate.emitter)
            with self.subTest(token=token):
                self.assertTrue(os.path.isfile(path), "%s: emitter %s does not exist"
                                % (token, gate.emitter))
                with open(path, encoding="utf-8", errors="replace") as stream:
                    self.assertIn(token, stream.read(),
                                  "%s: %s does not mention it" % (token, gate.emitter))

    def test_each_declared_exit_code_is_actually_raised(self):
        """Exit codes are the pipeline's real API — an agent gets a number and nothing else. A
        registry that maps a token to an exit nobody raises sends it looking for a gate that is
        not there."""
        enforcers = {}
        for name in ("handoff/handoff.sh", "verify/verify-slice.sh"):
            with open(os.path.join(ROOT, "pipeline", name), encoding="utf-8") as stream:
                enforcers[name] = stream.read()
        joined = "\n".join(enforcers.values())
        for token, gate in self.gates.items():
            if gate.exit_code is None:
                continue
            with self.subTest(token=token):
                self.assertRegex(joined, r"exit %s\b" % re.escape(gate.exit_code),
                                 "%s claims exit %s, which no enforcer raises"
                                 % (token, gate.exit_code))

    def test_flag_dependent_checkers_declare_which_mode_they_ran_in(self):
        """A checker whose verdict depends on its flags must say whether this run is the gate.

        This is the enforceable form of the lesson that cost the most time on 2026-09-06. Bare
        platform_boundary.py is STRICTER than the pre-commit hook: it exits 1 where the hook warns
        and exits 0, and three sessions read that as "the commit is blocked", wrote it into their
        notes, and inherited it from each other without retesting. The same silence in the other
        direction is worse — bare dim_provenance.py is LOOSER than the handoff, so a hand-run green
        can precede a gate refusal. Neither is avoidable by reading more carefully; the output has
        to say which run it is, and this test is what keeps the next such checker from shipping
        without saying it.
        """
        undeclared = []
        for token, gate in self.gates.items():
            if not gate.enforced_as:
                continue
            if not any(word.startswith("--") for word in gate.enforced_as.split()):
                continue  # bare run IS the gate; there is no second mode to confuse it with
            path = os.path.join(ROOT, "..", gate.emitter)
            with open(path, encoding="utf-8", errors="replace") as stream:
                if "declare_mode" not in stream.read():
                    undeclared.append("%s (%s)" % (token, gate.emitter))
        self.assertEqual(undeclared, [],
                         "these gates are enforced with flags but their checker never says whether "
                         "a given run is the gate — call gates.declare_mode(): %s" % undeclared)

    def test_unknown_verdicts_block_rather_than_slipping_through(self):
        """The default that makes the registry safe to extend: a word nobody has decided about is
        refused, not ignored. Getting this backwards is how a new verdict silently ships."""
        gate = self.gates["VERIFY_RESULT"]
        self.assertEqual(gate.status("PASS"), "PASS")
        self.assertEqual(gate.status("DEBT"), "BLOCK")
        self.assertEqual(gate.status("DEBT", condition_met=True), "CONDITIONAL")
        self.assertEqual(gate.status("PROBABLY_FINE"), "BLOCK")
        self.assertEqual(gate.status("FAIL"), "BLOCK")

    def test_a_missing_verdict_line_is_not_a_verdict(self):
        """None means the stage produced nothing — a toolchain fault, not a failed part. verify.sh
        already separates those (ERROR vs FAIL) and callers must be able to as well."""
        self.assertIsNone(gates.verdict("nothing here", "VERIFY_RESULT"))
        self.assertFalse(gates.allows("nothing here", "VERIFY_RESULT", gates=self.gates))
        self.assertEqual(gates.verdict("VERIFY_RESULT: DEBT\n", "VERIFY_RESULT"), "DEBT")


class ShellAndPythonReadersAgree(unittest.TestCase):
    """Two readers of one file is the compromise that avoids a fork per gate question. The cost is
    that they can disagree, so the disagreement is what gets tested."""

    CASES = [("VERIFY_RESULT", "VERIFY_RESULT: PASS", 0, True),
             ("VERIFY_RESULT", "VERIFY_RESULT: DEBT", 0, False),
             ("VERIFY_RESULT", "VERIFY_RESULT: DEBT", 1, True),
             ("VERIFY_RESULT", "VERIFY_RESULT: FAIL", 1, False),
             ("VERIFY_RESULT", "VERIFY_RESULT: SOMETHING_NEW", 1, False),
             ("SUPPORT_RESULT", "  SUPPORT_RESULT: PASS", 0, True),
             ("SUPPORT_RESULT", "SUPPORT_RESULT: FAIL", 1, False)]

    def shell_allows(self, token, text, condition):
        script = ('. "%s/gates.sh"; if gate_allows "%s" "$(cat)" %d; then echo YES; else echo NO; fi'
                  % (HERE, token, condition))
        out = subprocess.run(["bash", "-c", script], input=text, text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return out.stdout.strip().endswith("YES")

    def test_readers_agree_on_every_case(self):
        loaded = gates.load()
        for token, text, condition, expected in self.CASES:
            with self.subTest(token=token, text=text, condition=condition):
                python = gates.allows(text, token, condition_met=bool(condition), gates=loaded)
                self.assertEqual(python, expected, "python reader")
                self.assertEqual(self.shell_allows(token, text, condition), expected,
                                 "shell reader disagrees with python")


if __name__ == "__main__":
    unittest.main()
