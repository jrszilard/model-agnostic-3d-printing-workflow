#!/usr/bin/env python3
"""Insert explicit `M147` after homing: chamber filtration ON for this print, whatever the filament.

Justin, 2026-11-26: "Can we start the print with the chamber fans on to help get the fumes out of the
chamber and into the advance filtration? ideally, this would be a setting we use regularly".

On a Core One with the Advanced Filtration System the firmware runs the filtration blower only while
the print "needs filtration": the loaded filament type's flag (ASA/ABS yes, PLA/PETG no) or the
printer's Filter All Materials setting. `M147` marks the current print as needing it
(Prusa-Firmware-Buddy src/marlin_stubs/M147_148.cpp: "Turns on the chamber filtration for the
current print only (overrides fillament settings) (the filtration has to be enabled in the
settings)"); marlin_server resets the override when the print ends.
`feature/chamber_filtration/chamber_filtration.cpp`:
- the blower starts once the nozzle is hot, so it never runs during an ASA chamber soak;
- it runs at the printer's Minimum Power, and only if Print Filtration is ON in its Chamber
  Filtration settings;
- post-print filtration follows the printer's own Post-print settings.

Placed after the first G28, before the chamber soak and the purge, like the vent close. Idempotent.
Refuses a file that already turns filtration off (`M148`).
"""
from __future__ import annotations

import sys


def inject(path):
    with open(path) as stream:
        lines = stream.readlines()
    codes = [line.lstrip().split(None, 1)[0] if line.strip() else "" for line in lines]
    if "M148" in codes:
        raise RuntimeError("the gcode already turns chamber filtration off (M148); refusing to override it")
    if "M147" in codes:
        return "M147 already present; nothing to do"
    for index, command in enumerate(codes):
        if command == "G28":
            lines.insert(index + 1, "M147 ; chamber filtration on for this print (needs Print Filtration ON on the printer)\n")
            with open(path, "w") as stream:
                stream.writelines(lines)
            return "inserted M147 after G28 at line %d" % (index + 1)
    raise RuntimeError("no G28 homing command found; refusing to place the filtration command outside the start code")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: core-one-filtration-on.py <gcode>", file=sys.stderr)
        return 2
    try:
        print(inject(argv[0]))
    except (OSError, RuntimeError) as exc:
        print("FAIL:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
