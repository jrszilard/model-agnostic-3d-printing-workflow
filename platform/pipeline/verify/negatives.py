#!/usr/bin/env python3
"""Negative controls for a generator's checks: each broken value must be REFUSED, and for the reason stated.

A check that has never been seen to fail proves nothing. Until 2026-11 every part's negatives lived in a throwaway
script, ran one at a time (217 runs, 150 minutes of waiting in five weeks) and could not be run again. A part now keeps
them beside its source and this harness runs them side by side:

    parts/<category>/<part>/qa/negatives.py

        import sys
        from pathlib import Path
        ROOT = next(p for p in Path(__file__).resolve().parents if (p / "platform" / "pipeline").is_dir())
        sys.path.insert(0, str(ROOT / "platform" / "pipeline" / "verify"))
        from negatives import Negative, main

        SOURCE = "../src/<part>.py"

        def run(module, case):                          # how this part's checks are run on a mutated module
            module.checks(sections=case.sections)

        CASES = [
            Negative("slot 3.8", old="SLOT_W = 5.0 ", new="SLOT_W = 3.8 ", expect=["slot's edges"], sections=["sleds"]),
            Negative("skin 0.6", old="CAR_SKIN = 1.0", new="CAR_SKIN = 0.6", expect=["skin"], file="../../touge-road/src/touge-road.py"),
        ]

        if __name__ == "__main__":
            main(__file__)

    ~/cadquery-env/bin/python -B parts/<category>/<part>/qa/negatives.py [-j 8] [--only 0,3] [--list]

How a case runs, and the three mistakes that design removes:

- The mutation is a replacement in the SOURCE TEXT, which is then executed as a fresh module in a fresh interpreter.
  Setting a constant on an imported module misses default arguments and constants derived at import; a negative then
  "passes" as a harness artefact. Re-executing the text cannot miss them.
- Nothing is written: no mutated file, no bytecode. A mutated file restored within the same second left a stale .pyc
  behind twice (a false "restored" failure once, a false MISS once).
- `old` must occur exactly once. A negative whose text has gone from the source is reported STALE, not skipped: a
  renamed constant must not silently retire its control.

The file lives in the part's qa/, which is outside the part's build inputs, so adding a control does not make its
exports stale. (This harness lives here and not in parts/_lib for the same reason: every file in parts/_lib is an
input to every part.)

Outcomes: CAUGHT (refused, and the message holds one of `expect`), MISSED (the checks passed), OTHER (refused for
another reason: the control or its expectation is wrong), STALE. The unmutated source is run first and must pass.
Exit 0 only when every case is CAUGHT.
"""
from __future__ import annotations

import argparse
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


class Negative:
    def __init__(self, name, old, new, expect, sections=None, file=None):
        if not expect:
            raise ValueError("%s: say what the refusal must mention (expect=[...])" % name)
        self.name, self.old, self.new = name, old, new
        self.expect = [expect] if isinstance(expect, str) else list(expect)
        self.sections = sections
        self.file = file

    def __repr__(self):
        return "Negative(%r)" % self.name


def _load(path):
    path = Path(path).resolve()
    spec = importlib.util.spec_from_file_location("negatives_of_part", path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    spec.loader.exec_module(module)
    for name in ("SOURCE", "CASES", "run"):
        if not hasattr(module, name):
            raise SystemExit("%s must define %s" % (path, name))
    return path, module


def _mutate_dependency(target, text):
    """Make every import of `target` (by path, as generators load their siblings) read `text` instead of the file."""
    target = os.path.realpath(target)
    original = importlib.machinery.SourceFileLoader.get_data

    def get_data(self, path):
        real = os.path.realpath(path)
        if real == target:
            return text.encode()
        if real.endswith((".pyc", ".pyo")):
            try:
                if os.path.realpath(importlib.util.source_from_cache(real)) == target:
                    raise OSError("bytecode of the mutated file is never used")
            except ValueError:
                pass
        return original(self, path)

    importlib.machinery.SourceFileLoader.get_data = get_data


def _run_case(negatives_path, index):
    """One case in this (fresh) interpreter. Prints one JSON line."""
    sys.dont_write_bytecode = True
    started = time.monotonic()
    path, module = _load(negatives_path)
    source = (path.parent / module.SOURCE).resolve()
    case = None if index < 0 else module.CASES[index]
    out = {"index": index, "name": "the source as it is" if case is None else case.name}
    text = source.read_text()
    if case is not None:
        target = source if case.file is None else (path.parent / case.file).resolve()
        target_text = text if target == source else target.read_text()
        count = target_text.count(case.old)
        if count != 1:
            out.update(outcome="STALE", message="the text to replace occurs %d times in %s" % (count, target.name))
            print(json.dumps(out))
            return
        if target == source:
            text = text.replace(case.old, case.new)
        else:
            _mutate_dependency(target, target_text.replace(case.old, case.new))
    generator = types.ModuleType("negative_case")
    generator.__file__ = str(source)
    sys.modules["negative_case"] = generator
    sys.path.insert(0, str(source.parent))
    try:
        exec(compile(text, str(source), "exec"), generator.__dict__)
        module.run(generator, case)
        out.update(outcome="PASSED" if case is None else "MISSED", message="every check passed")
    except BaseException as exc:
        message = str(exc) or type(exc).__name__
        first = message.splitlines()[0][:300]
        if case is None:
            out.update(outcome="FAILED", message="%s: %s" % (type(exc).__name__, first))
        else:
            hit = any(fragment in message for fragment in case.expect)
            out.update(outcome="CAUGHT" if hit else "OTHER", message=first)
    out["seconds"] = round(time.monotonic() - started, 1)
    print(json.dumps(out))


def _spawn(negatives_path, index, check_jobs):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", CHECK_JOBS=str(check_jobs))
    started = time.monotonic()
    done = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), "--case", str(index),
                           str(negatives_path)], capture_output=True, text=True, env=env)
    for line in reversed(done.stdout.splitlines()):
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                break
    tail = (done.stderr or done.stdout).strip().splitlines()[-1:] or ["no output"]
    return {"index": index, "name": "?", "outcome": "ERROR", "seconds": round(time.monotonic() - started, 1),
            "message": "the case process exited %d: %s" % (done.returncode, tail[0][:300])}


def main(negatives_path=None, argv=None):
    """Run and EXIT with the verdict (0 only when every case is CAUGHT), so `main(__file__)` in a part's file is
    enough: a caller that forgets to pass the result on cannot turn a missed control into exit 0."""
    raise SystemExit(_main(negatives_path, argv))


def _main(negatives_path=None, argv=None):
    parser = argparse.ArgumentParser(description="Run a part's negative controls side by side.")
    if negatives_path is None:
        parser.add_argument("negatives", help="the part's qa/negatives.py")
    parser.add_argument("-j", "--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    parser.add_argument("--only", help="comma-separated case numbers")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--case", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    negatives_path = Path(negatives_path or args.negatives).resolve()
    if args.case is not None:
        _run_case(negatives_path, args.case)
        return 0
    _, module = _load(negatives_path)
    cases = list(module.CASES)
    names = [case.name for case in cases]
    if len(set(names)) != len(names):
        raise SystemExit("negatives need distinct names")
    chosen = list(range(len(cases)))
    if args.only:
        chosen = [int(i) for i in args.only.split(",")]
    if args.list:
        for i in chosen:
            print("%3d  %s" % (i, cases[i].name))
        return 0
    started = time.monotonic()
    jobs = max(1, min(args.jobs, len(chosen) or 1))
    inner = max(1, (os.cpu_count() or 2) // jobs)
    base = _spawn(negatives_path, -1, max(1, (os.cpu_count() or 2) - 2))
    if base["outcome"] != "PASSED":
        print("the source as it is does NOT pass its own checks, so no negative means anything:\n  %s"
              % base["message"])
        return 2
    print("the source as it is passes (%.1f s); %d negatives, %d at a time" % (base["seconds"], len(chosen), jobs))
    with ThreadPoolExecutor(jobs) as pool:
        results = list(pool.map(lambda i: _spawn(negatives_path, i, inner), chosen))
    tally = {}
    for i, result in zip(chosen, results):
        tally[result["outcome"]] = tally.get(result["outcome"], 0) + 1
        print("%3d  %-7s %6.1fs  %s: %s" % (i, result["outcome"], result.get("seconds", 0.0), cases[i].name,
                                            result["message"]))
    caught = tally.get("CAUGHT", 0)
    print("%d of %d refused for the stated reason in %.0f s%s" % (
        caught, len(chosen), time.monotonic() - started,
        "" if caught == len(chosen) else "  --  " + ", ".join(
            "%d %s" % (n, kind) for kind, n in sorted(tally.items()) if kind != "CAUGHT")))
    return 0 if caught == len(chosen) else 1


if __name__ == "__main__":
    main()
