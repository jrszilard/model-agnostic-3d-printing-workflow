#!/usr/bin/env python3
"""Insert explicit `M148` after homing: the printer's chamber filtration OFF for this print, so the chamber stays warm.

For a printer on the DIY filtration backend printing a material that curls when the chamber is cool (ASA). Use it with
`core-one-filter-blower.py`, which runs the Advanced Filtration blower by itself, and never with
`core-one-filtration-on.py` (`M147`): each refuses a file the other has marked.

Justin, 2026-11-27, after deer B ring 1 i2 (ASA, job 429) came off with the top faces rough at the ends of both long
guides: "let's also not rule out turning off the chamber fan and only leaving the advanced filtration fan on to help
keep the chamber hot since this is the first time I ama runing the chamber fan for asa for the whole print. before i
would sometimes just manually turn it on for part of the print."

Firmware 8.0.0 (Prusa-Firmware-Buddy):
- `feature/xbuddy_extension/xbuddy_extension.cpp`, DIY backend ("the cooling fans do both filtration and cooling"):
  rear fans = max(chamber cooling, filtration power). With ASA loaded, or after `M147`, the filtration power is the
  menu's Minimum Power for as long as the nozzle is hot, so the rear fans run for the whole print whatever
  `M106 P3` says. The blower on `P4` then sends that air outside.
- `marlin_stubs/M147_148.cpp`: `M148` "Turns off the chamber filtration for the current print only (overrides fillament
  settings)". `chamber_filtration.cpp`: with that override `needs_filtration()` is false, so the filtration power is 0
  and the rear fans follow chamber cooling alone: off below the chamber target (`M141`), on above it.
- `cooling.cpp` `apply_pwm_overrides()`: overheating and critical chamber temperatures still force the fans to full.
- The override ends with the print. No post-print filtration follows, since the print never "needed" it.

Placed after the first G28, before the chamber soak and the purge. Idempotent. Refuses a file that turns filtration on
(`M147`).
"""
from __future__ import annotations

import sys


def inject(path):
    with open(path) as stream:
        lines = stream.readlines()
    codes = [line.lstrip().split(None, 1)[0] if line.strip() else "" for line in lines]
    if "M147" in codes:
        raise RuntimeError("the gcode already turns chamber filtration on (M147); refusing to override it")
    if "M148" in codes:
        return "M148 already present; nothing to do"
    for index, command in enumerate(codes):
        if command == "G28":
            lines.insert(index + 1, "M148 ; chamber filtration off for this print: the rear fans only cool above the chamber target\n")
            with open(path, "w") as stream:
                stream.writelines(lines)
            return "inserted M148 after G28 at line %d" % (index + 1)
    raise RuntimeError("no G28 homing command found; refusing to place the filtration command outside the start code")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: core-one-filtration-off.py <gcode>", file=sys.stderr)
        return 2
    try:
        print(inject(argv[0]))
    except (OSError, RuntimeError) as exc:
        print("FAIL:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
