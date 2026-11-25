#!/usr/bin/env python3
"""Post-slice hook for colour plates: manual swaps, tool lines commented out, purge + wipe after
each swap. slice.sh adds it on its own whenever `--colour` regions are given; see colour_plate.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import colour_plate  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: colour_swaps.py <gcode>")
    sys.exit(colour_plate.swaps(sys.argv[1]))
