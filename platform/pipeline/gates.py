#!/usr/bin/env python3
"""Read gates.txt: what every pipeline gate reports, and what each verdict means.

The pipeline's machine interface is a line of text per stage — `<TOKEN>: <VERDICT>` — read by
consumers that hand-wrote `grep -q '<TOKEN>: PASS'`. That works until a gate grows a third verdict,
at which point every call site is a place the new word is silently treated as failure and there is
no list of call sites. gates.txt is the list; this module is how Python reads it and gates.sh is how
shell reads it, so there is exactly one copy of the answer.

For agents: `python3 gates.py list` prints every gate, `explain <TOKEN>` prints one in full, and
`exit <N>` answers "what does this exit code mean and what do I do about it" without reading the
script that raised it.
"""
from __future__ import annotations

import os
import re
import sys

REGISTRY = os.path.join(os.path.dirname(os.path.realpath(__file__)), "gates.txt")
NONE = "-"


class Gate:
    __slots__ = ("token", "passing", "conditional", "condition", "exit_code", "bypass", "emitter",
                 "enforced_as")

    def __init__(self, token, passing, conditional, condition, exit_code, bypass, emitter,
                 enforced_as=None):
        self.token = token
        self.passing = passing
        self.conditional = conditional
        self.condition = condition
        self.exit_code = exit_code
        self.bypass = bypass
        self.emitter = emitter
        self.enforced_as = enforced_as

    def status(self, verdict, condition_met=False):
        """One of PASS, CONDITIONAL, BLOCK — never a bare boolean.

        A caller that only wants a yes/no still has to say whether the condition holds, because the
        answer genuinely depends on it. Returning three states rather than two keeps "allowed
        because the condition was met" distinguishable from "allowed outright" at the call site,
        which is what stops a prototype's latitude leaking into a release.
        """
        if verdict in self.passing:
            return "PASS"
        if verdict in self.conditional:
            return "CONDITIONAL" if condition_met else "BLOCK"
        return "BLOCK"

    def allows(self, verdict, condition_met=False):
        return self.status(verdict, condition_met) in ("PASS", "CONDITIONAL")

    def describe(self):
        lines = ["%s — emitted by %s" % (self.token, self.emitter),
                 "  passing:      %s" % (", ".join(self.passing) or "(none)")]
        if self.conditional:
            lines.append("  conditional:  %s   ONLY IF %s"
                         % (", ".join(self.conditional), self.condition))
        lines.append("  anything else BLOCKS (unknown verdicts are refused, not ignored)")
        lines.append("  on block:     %s" %
                     ("exit %s" % self.exit_code if self.exit_code else
                      "reports only; blocks its own caller, not a plate"))
        lines.append("  bypass:       %s" % (self.bypass or "none — there is no bypass, by design"))
        lines.append("  the gate is:  %s" %
                     (self.enforced_as or "this checker run bare — no flags change its verdict"))
        return "\n".join(lines)


def _split(field):
    if field in ("", NONE):
        return ()
    return tuple(part.strip() for part in field.split(",") if part.strip())


def load(path=REGISTRY):
    gates = {}
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = [f.strip() for f in line.split("|")]
            if len(parts) != 8:
                raise ValueError("gates.txt row needs 8 |-separated fields, got %d: %r"
                                 % (len(parts), line))
            token, passing, conditional, condition, exit_code, bypass, emitter, enforced = parts
            gates[token] = Gate(token, _split(passing), _split(conditional),
                                None if condition == NONE else condition,
                                None if exit_code == NONE else exit_code,
                                None if bypass in (NONE, "none") else bypass, emitter,
                                None if enforced == NONE else enforced)
    return gates


def verdict(text, token):
    """The verdict a report announced, or None when it announced nothing.

    None is not a failure — it is the separate, worse case of a stage that produced no verdict at
    all, which verify.sh already distinguishes as ERROR because a toolchain that died is not a part
    that failed. Callers must keep those apart.
    """
    match = re.search(r"^\s*%s:\s*(\S+)" % re.escape(token), text, re.MULTILINE)
    return match.group(1) if match else None


def allows(text, token, condition_met=False, gates=None):
    gates = gates or load()
    found = verdict(text, token)
    return found is not None and gates[token].allows(found, condition_met)


def declare_mode(token, argv, out=None):
    """Print whether THIS run is the gate, or only a report that resembles it.

    A checker whose verdict depends on its flags answers a different question when run by hand, and
    the mistake lands both ways. Bare platform_boundary.py is stricter than the pre-commit hook and
    produced a false "the commit is blocked" that three sessions inherited from each other's notes
    without retesting. Bare dim_provenance.py is looser than the handoff, so the same silence would
    produce the opposite error — a green that the real gate refuses. Neither is a reasoning failure
    an agent can be expected to avoid unread; the output simply did not say which run it was.
    """
    out = out or sys.stdout
    gates = load()
    gate = gates.get(token)
    enforced = gate.enforced_as if gate else None
    if not enforced:
        return
    flags = {a for a in argv if a.startswith("--")}
    needed = {a for a in enforced.split() if a.startswith("--")}
    if needed <= flags:
        print("MODE: enforcing — this run matches how the pipeline invokes it (%s)." % enforced,
              file=out)
    else:
        print("MODE: report-only — THIS RUN IS NOT THE GATE. The gate is `%s`;\n"
              "      it applies %s, which this run does not. Do not conclude from this\n"
              "      output that the gate agrees — run it as above, or ask gates.py."
              % (enforced, ", ".join(sorted(needed - flags))), file=out)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    gates = load()
    if not argv or argv[0] == "list":
        for gate in gates.values():
            extra = ("  (+%s if %s)" % (",".join(gate.conditional), gate.condition)
                     if gate.conditional else "")
            print("%-30s passing=%-6s exit=%-4s%s"
                  % (gate.token, ",".join(gate.passing), gate.exit_code or "-", extra))
        return 0
    if argv[0] == "explain" and len(argv) > 1:
        if argv[1] not in gates:
            print("no such gate: %s (try `gates.py list`)" % argv[1], file=sys.stderr)
            return 2
        print(gates[argv[1]].describe())
        return 0
    if argv[0] == "exit" and len(argv) > 1:
        matches = [g for g in gates.values() if g.exit_code == argv[1]]
        if not matches:
            print("exit %s is not a gate refusal. It is either a usage/IO error or an exit this "
                  "registry does not cover; read the script's usage banner." % argv[1])
            return 0
        print("exit %s is raised when any of these blocks:" % argv[1])
        for gate in matches:
            print()
            print(gates[gate.token].describe())
        return 0
    if argv[0] == "verdict" and len(argv) > 2:
        with open(argv[2], encoding="utf-8", errors="replace") as stream:
            found = verdict(stream.read(), argv[1])
        print(found or "(no verdict announced)")
        return 0 if found else 1
    print(__doc__.strip().splitlines()[0], file=sys.stderr)
    print("usage: gates.py [list | explain <TOKEN> | exit <N> | verdict <TOKEN> <file>]",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
