#!/usr/bin/env python3
"""Verify and report the declarative fit-core convention in spec.yaml."""
import argparse
import os
import sys

_LIB = os.path.realpath(os.path.join(os.path.dirname(__file__), "../../../parts/_lib"))
sys.path.insert(0, _LIB)
from fitcore import evaluate_declaration  # noqa: E402


def evaluate_fit_core(value):
    return evaluate_declaration(value)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("spec")
    args = parser.parse_args(argv)
    try:
        import yaml
        with open(args.spec) as stream:
            spec = yaml.safe_load(stream) or {}
        result = evaluate_fit_core(spec.get("fit_core"))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print("  [FAIL] cannot read fit core:", exc)
        print("FITCORE_RESULT: FAIL")
        return 1
    if not result["declared"]:
        print("fit core: not declared (legacy/one-variant part)")
    else:
        print("fit core: %s · source %s" % (result["fingerprint"], result.get("source")))
        for status, name, message in result["rows"]:
            print("  [%s] %-24s %s" % (status, name, message))
    print("FITCORE_RESULT:", "PASS" if result["passed"] else "FAIL")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
