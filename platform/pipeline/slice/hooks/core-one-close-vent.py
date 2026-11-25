#!/usr/bin/env python3
"""Insert explicit `M870 C` after homing for Core One+ ASA/high-chamber prints.

The actuated top vent relies on firmware memory of its position; a hand-moved flap can make that
memory false. PrusaSlicer 2.9.6 emits no M870. The head must be homed before it pushes the grille,
so insertion is after the first G28 and before chamber heating. Idempotent.
"""
from __future__ import annotations

import sys


def inject(path):
    with open(path) as stream:
        lines = stream.readlines()
    if any(line.lstrip().startswith("M870") for line in lines):
        return "M870 already present; nothing to do"
    for index, line in enumerate(lines):
        command = line.lstrip().split(None, 1)[0] if line.strip() else ""
        if command == "G28":
            lines.insert(index + 1,
                         "M870 C ; close chamber vent (explicit; do not trust flap-position memory)\n")
            with open(path, "w") as stream:
                stream.writelines(lines)
            return "inserted M870 C after G28 at line %d" % (index + 1)
    raise RuntimeError("no G28 homing command found; refusing an unplaced vent move")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: core-one-close-vent.py <gcode>", file=sys.stderr)
        return 2
    try:
        print(inject(argv[0]))
    except (OSError, RuntimeError) as exc:
        print("FAIL:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
