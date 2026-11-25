"""Slicer CLI exit code -> verdict.

Historically OrcaSlicer-only; the bench moved to PrusaSlicer on 2026-07-20 and the mapping did
not follow. PrusaSlicer returns a plain **1** for any config or slicing error, which was unmapped,
classified "unknown", and — because verify-slice only blocked on severity `hard` — **PASSED THE
GATE**. A failed slice leaves the previous run's gcode in place, so the gate would have waved
through a stale plate that no longer matches its source. Found 2026-07-25 when a
`fill_density=100%` override was rejected ("the selected fill pattern is not supposed to work at
100% density") and verify-slice still said PASS over the old 15% gcode.

The rule now: **a nonzero exit NEVER passes.** An unrecognised code is treated as hard, not as a
shrug — the KB's own `fail-loud-or-safe` pattern. Naming an unknown code is a diagnostic nicety;
letting it through is a safety bug.
"""

# PrusaSlicer: small positive codes. 1 covers config validation and slicing errors alike.
_PRUSA = {
    1: ("PS_ERROR", "PrusaSlicer error — config validation or slicing failed; read "
                    ".prusa_slice.log. NOTE any existing plate_1.gcode is STALE."),
    2: ("PS_BAD_ARGS", "bad command line / unknown option"),
}

# OrcaSlicer 2.4.1: signed values printed as 'found error, return -N'
# (CLI ref: printago.io/blog/orca-slicer-cli-reference). Retained for legacy build dirs.
_HARD = {
    -6:  ("CLI_DATA_FILE_ERROR",      "input data/model file error"),
    -14: ("CLI_OUT_OF_MEMORY",        "out of memory"),
    -20: ("CLI_PRINTABLE_SIZE_REDUCED","object exceeds printable size (reduced)"),
    -21: ("CLI_ARRANGE_FAILED",       "arrange failed"),
    -22: ("CLI_ORIENT_FAILED",        "orient failed"),
    -50: ("CLI_NO_OBJECTS",           "empty plate / no printable objects"),
    -52: ("CLI_OBJECTS_PARTLY_INSIDE","object is partly/fully off the bed"),
    -58: ("CLI_SLICING_TIME_LIMIT",   "slicing time limit exceeded"),
    -59: ("CLI_TRIANGLE_LIMIT",       "triangle-count limit exceeded"),
    -61: ("CLI_FILAMENT_BED_MISMATCH","filament not compatible with bed type"),
    -63: ("CLI_OBJECT_COLLISION",     "object/skirt collision"),
    -64: ("CLI_OBJECT_COLLISION",     "object collision"),
    -100:("CLI_SLICING_ERROR",        "slicing error"),
    -101:("CLI_GCODE_PATH_CONFLICTS", "gcode path conflicts"),
    -102:("CLI_GCODE_PATH_UNPRINTABLE","gcode path in unprintable area"),
}


def classify_exit(code):
    """Every nonzero code is `hard`. Only 0 passes."""
    if code == 0:
        return {"code": 0, "name": "CLI_SUCCESS", "severity": "ok", "message": "sliced cleanly"}
    for table in (_PRUSA, _HARD):
        if code in table:
            name, msg = table[code]
            return {"code": code, "name": name, "severity": "hard", "message": msg}
    return {"code": code, "name": "UNKNOWN", "severity": "hard",
            "message": "unmapped slicer exit code %d — treated as a failure. Any existing "
                       "plate_1.gcode may be STALE output from an earlier run." % code}
