#!/usr/bin/env python3
"""Every cadquery-env suite in ONE interpreter.

`import cadquery` costs ~1.9 s and ~471 MB resident, and test.sh paid it twice: once to discover
`parts/_lib/cadquery_test_*.py` and again for `platform/codegen-templates/cadquery_test_*.py`.
Sequentially that was 1.9 s of pure duplication; now that test.sh runs its stages concurrently it
was also a second 471 MB process alive at the same instant as the first, on a box this plan has
already recorded hitting full swap.

Run with the cadquery-env interpreter, from the repo root:
    ~/cadquery-env/bin/python platform/pipeline/cadquery_suites.py

Exit 0 = every test passed, matching what `unittest discover` returned for each stage separately.

The start directories are discovered into one suite rather than run back to back so that a
single TextTestRunner prints one "Ran N tests" summary and one verdict. `discover()` inserts each
start dir at the front of sys.path, so the modules import exactly as they did when each stage owned
its own interpreter; the suites share no names (`cadquery_test_probes.py` against
`cadquery_test_templates.py`) and neither writes into the repo.
"""
import os
import sys
import unittest

START_DIRS = [
    ("parts/_lib", "cadquery_test_*.py"),
    ("platform/codegen-templates", "cadquery_test_*.py"),
    ("platform/pipeline/working-model", "cadquery_test_*.py"),
]


def main():
    root = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    os.chdir(root)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for start, pattern in START_DIRS:
        if not os.path.isdir(start):
            print("no such start dir: %s" % start, file=sys.stderr)
            return 2
        suite.addTest(loader.discover(start, pattern=pattern, top_level_dir=start))
    # discover() swallows an unimportable module into a _FailedTest rather than raising, which is
    # the behaviour we want (it reports as a failure), but loader.errors is the only place a
    # discovery-time problem with no test to attach to shows up. Surface it rather than exiting 0
    # over a suite that found nothing.
    if loader.errors:
        for error in loader.errors:
            print(error, file=sys.stderr)
        return 2
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
