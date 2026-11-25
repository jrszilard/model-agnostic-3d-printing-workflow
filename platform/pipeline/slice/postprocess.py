#!/usr/bin/env python3
"""Run recorded post-slice gcode hooks and bind verification to the final bytes.

Hooks receive exactly one argument: the gcode path. Python files need not be executable. The JSON
manifest records hook paths/hashes, exit status, and final gcode sha256. `--check` fails closed on a
failed hook, missing file, or any edit after the manifest was written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _command(hook, gcode):
    return [sys.executable, hook, gcode] if hook.lower().endswith(".py") else [hook, gcode]


def run_hooks(gcode, hooks, manifest):
    records = []
    passed = True
    for hook in hooks:
        path = os.path.realpath(hook)
        record = {"path": path, "sha256": sha256(path) if os.path.isfile(path) else None,
                  "command": _command(path, os.path.realpath(gcode)), "exit_code": 127,
                  "stdout": "", "stderr": ""}
        if not os.path.isfile(path):
            record["stderr"] = "hook does not exist"
            records.append(record)
            passed = False
            break
        try:
            proc = subprocess.run(record["command"], text=True, capture_output=True, check=False)
            record.update(exit_code=proc.returncode, stdout=proc.stdout[-4000:], stderr=proc.stderr[-4000:])
        except OSError as exc:
            record["stderr"] = str(exc)
        records.append(record)
        if record["exit_code"] != 0:
            passed = False
            break

    final_sha = sha256(gcode) if os.path.isfile(gcode) else None
    data = {"schema": 1, "gcode": os.path.realpath(gcode), "gcode_sha256": final_sha,
            "passed": passed and final_sha is not None, "hooks": records}
    os.makedirs(os.path.dirname(os.path.realpath(manifest)), exist_ok=True)
    with open(manifest, "w") as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return data


def check_manifest(gcode, manifest):
    hard, notes = [], []
    try:
        with open(manifest) as stream:
            data = json.load(stream)
    except (OSError, ValueError) as exc:
        return {"passed": False, "hard": ["cannot read gcode manifest: %s" % exc], "notes": []}
    for record in data.get("hooks", []):
        if record.get("exit_code") != 0:
            hard.append("post hook %s exited %s" % (record.get("path"), record.get("exit_code")))
        elif record.get("path"):
            notes.append("post hook PASS: %s" % os.path.basename(record["path"]))
    if not data.get("passed"):
        hard.append("post-slice manifest is not passed")
    if not os.path.isfile(gcode):
        hard.append("final gcode is missing")
    else:
        current = sha256(gcode)
        expected = data.get("gcode_sha256")
        if not expected:
            hard.append("post-slice manifest has no final gcode hash")
        elif current != expected:
            hard.append("gcode changed after post-slice recording: expected %s, got %s"
                        % (expected[:12], current[:12]))
        else:
            notes.append("final gcode sha256 %s" % current[:12])
    return {"passed": not hard, "hard": hard, "notes": notes, "data": data}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcode", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("hooks", nargs="*")
    args = parser.parse_args(argv)
    if args.check:
        result = check_manifest(args.gcode, args.manifest)
        for note in result["notes"]:
            print("  [PASS]", note)
        for failure in result["hard"]:
            print("  [HARD]", failure)
        print("POSTPROCESS_RESULT:", "PASS" if result["passed"] else "FAIL")
        return 0 if result["passed"] else 1

    data = run_hooks(args.gcode, args.hooks, args.manifest)
    for record in data["hooks"]:
        if record["stdout"].strip():
            print(record["stdout"].strip())
        if record["stderr"].strip():
            print(record["stderr"].strip(), file=sys.stderr)
        print("post hook %s -> exit %s" % (record["path"], record["exit_code"]))
    print("final gcode sha256", (data.get("gcode_sha256") or "MISSING")[:12])
    return 0 if data["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
