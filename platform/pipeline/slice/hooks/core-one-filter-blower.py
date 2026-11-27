#!/usr/bin/env python3
"""Insert `M106 P4 S102`, the Advanced Filtration blower at 40 % for this print: after the chamber soak (`M191`) when
the print has one, otherwise after homing.

Justin, 2026-11-26. His Core One runs the DIY filtration backend because his rear chamber fans push chamber air into the
Advanced Filtration housing. He asked whether the firmware runs both fans; it does not. Then "1 yes" to running the
filter's blower too, on every print.

Firmware 8.0.0:
- `xbuddy_extension.cpp`: on DIY the rear fans do filtration and cooling, and the filtration fan (P4) sits at its manual
  target, default off.
- `M106_M107.cpp`: `M106 P4 S<0-255>` sets that target.
- `chamber.cpp`: `Chamber::reset()` returns it to auto when the print ends, so the setting lasts one print.

It goes after `M191` so it doesn't slow an ASA chamber soak. 102/255 is 40 %, Prusa's minimum for filtering the whole
chamber. Idempotent; refuses a file that already sets P4 any other way.
"""
from __future__ import annotations

import sys

PWM = 102
LINE = "M106 P4 S%d ; Advanced Filtration blower 40 %% for this print (DIY backend: the rear fans feed it)\n" % PWM


def _sets_p4(line):
    words = line.split(";", 1)[0].split()
    return bool(words) and words[0] in ("M106", "M107") and "P4" in words[1:]


def inject(path):
    with open(path) as stream:
        lines = stream.readlines()
    p4 = [i for i, line in enumerate(lines) if _sets_p4(line)]
    if p4:
        if all(lines[i] == LINE for i in p4):
            return "M106 P4 already present; nothing to do"
        raise RuntimeError("the gcode already sets the filtration fan (P4); refusing to override it")
    codes = [line.lstrip().split(None, 1)[0] if line.strip() else "" for line in lines]
    soak = [i for i, command in enumerate(codes) if command == "M191"]
    homing = [i for i, command in enumerate(codes) if command == "G28"]
    if not homing:
        raise RuntimeError("no G28 homing command found; refusing to place the blower command outside the start code")
    at, where = (soak[-1] + 1, "after the chamber soak (M191)") if soak else (homing[0] + 1, "after G28")
    lines.insert(at, LINE)
    with open(path, "w") as stream:
        stream.writelines(lines)
    return "inserted M106 P4 S%d %s at line %d" % (PWM, where, at + 1)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: core-one-filter-blower.py <gcode>", file=sys.stderr)
        return 2
    try:
        print(inject(argv[0]))
    except (OSError, RuntimeError) as exc:
        print("FAIL:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
