"""Foreign-key and false-metrology-confidence checks for the observation log.

`research/results/measurements.csv` is the append-only log; `parts/_lib/joints.py` is the curated
registry distilled from it. The `sample` column is the join between them, and a join nobody
validates is a join that silently rots — a typo'd or renamed sample number quietly orphans the
evidence for a qualified fit. Aggregate warnings also keep a qualitative gate log from silently
being described as an uncertainty-bearing dimensional dataset.

Rules:
  - a blank `sample` is fine (most rows are not joint coupons)
  - a non-blank `sample` MUST resolve in the registry
  - the row's material/printer should match the sample's qualified context, or the row is
    recording an off-context observation, which is exactly what wants flagging for review

Usage: python3 platform/pipeline/verify/measurements_check.py [csv]   exit 0 = clean
"""
import csv
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.abspath(os.path.join(_HERE, "..", "..", "..", "parts", "_lib"))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from joints import MATERIALS, SAMPLES  # noqa: E402

DEFAULT_CSV = os.path.abspath(os.path.join(_HERE, "..", "..", "..",
                                           "research", "results", "measurements.csv"))
METROLOGY_FIELDS = ("instrument_id", "instrument_resolution_mm", "operator", "repeats_n",
                    "observations_mm", "uncertainty_mm", "uncertainty_basis", "filament_lot",
                    "dry_state", "ambient_c", "ambient_rh_pct", "gcode_sha256")


def _present(row, key):
    return bool((row.get(key) or "").strip())


def check(path):
    """Returns (errors, warnings) as lists of human-readable strings."""
    errors, warnings = [], []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        fields = set(reader.fieldnames or [])
    if "sample" not in fields:
        return ["%s has no 'sample' column — the registry join is missing" % path], []

    missing_metrology = [field for field in METROLOGY_FIELDS if field not in fields]
    if missing_metrology:
        warnings.append("metrology-v2 fields absent (%d): %s; qualitative rows remain valid, but "
                        "the CSV cannot support repeatability/uncertainty claims"
                        % (len(missing_metrology), ", ".join(missing_metrology)))

    measured = [row for row in rows if _present(row, "measured_mm")]
    if not missing_metrology and measured:
        incomplete = [(field, sum(not _present(row, field) for row in measured))
                      for field in METROLOGY_FIELDS]
        incomplete = [(field, count) for field, count in incomplete if count]
        if incomplete:
            warnings.append("metrology-v2 dimensional rows missing values: %s"
                            % ", ".join("%s %d/%d" % (field, count, len(measured))
                                        for field, count in incomplete))
    comparable = [row for row in measured if _present(row, "nominal_mm")]
    missing_deviation = [row for row in comparable if not _present(row, "deviation_mm")]
    if missing_deviation:
        warnings.append("%d/%d dimensional rows with nominal+measured values lack deviation_mm"
                        % (len(missing_deviation), len(comparable)))
    for line, row in enumerate(rows, start=2):
        values = {}
        for field in ("nominal_mm", "measured_mm", "deviation_mm", "deviation_pct"):
            if _present(row, field):
                try:
                    values[field] = float(row[field])
                except ValueError:
                    errors.append("line %d: %s is not numeric: %r" % (line, field, row[field]))
        if all(field in values for field in ("nominal_mm", "measured_mm", "deviation_mm")):
            expected = values["measured_mm"] - values["nominal_mm"]
            if abs(values["deviation_mm"] - expected) > 0.0005:
                errors.append("line %d: deviation_mm %.6g != measured-nominal %.6g"
                              % (line, values["deviation_mm"], expected))
            if "deviation_pct" in values and values["nominal_mm"] != 0:
                expected_pct = 100.0 * expected / values["nominal_mm"]
                if abs(values["deviation_pct"] - expected_pct) > 0.001:
                    errors.append("line %d: deviation_pct %.6g != 100*deviation/nominal %.6g"
                                  % (line, values["deviation_pct"], expected_pct))

    printer_spellings = {}
    for row in rows:
        raw = (row.get("printer") or "").strip()
        if raw:
            printer_spellings.setdefault("".join(ch for ch in raw.lower() if ch.isalnum()), set()).add(raw)
    aliases = [sorted(values) for values in printer_spellings.values() if len(values) > 1]
    if aliases:
        warnings.append("printer identity has alias spellings: %s"
                        % "; ".join(" / ".join(values) for values in aliases))

    non_material = sorted({(row.get("material") or "").strip() for row in rows
                           if (row.get("material") or "").strip().lower()
                           in {"cad", "measure", "measurement", "none", "n/a"}})
    if non_material:
        warnings.append("material column contains non-material context values: %s"
                        % ", ".join(non_material))

    seen = set()
    for i, row in enumerate(rows, start=2):        # header is line 1
        sid = (row.get("sample") or "").strip()
        if not sid:
            continue
        seen.add(sid)
        s = SAMPLES.get(sid)
        if s is None:
            errors.append("line %d: sample %r is not in the registry "
                          "(typo, or removed without migrating the log)" % (i, sid))
            continue
        material = (row.get("material") or "").strip()
        printer = (row.get("printer") or "").strip().lower()
        if material and material in MATERIALS and material != s.context.material:
            warnings.append("line %d: %s observed in %s but qualified in %s — off-context "
                            "observation, confirm it is deliberate"
                            % (i, sid, material, s.context.material))
        if printer and printer.replace(" ", "-") not in s.context.printer:
            warnings.append("line %d: %s observed on %r but qualified on %r"
                            % (i, sid, printer, s.context.printer))

    # A qualified sample with no observation backing it is not an error — evidence may live only
    # in a KB decision — but it is worth surfacing as the registry grows.
    unbacked = sorted(s.id for s in SAMPLES.values()
                      if s.status == "qualified" and s.id not in seen)
    if unbacked:
        warnings.append("qualified samples with no row in the log yet: %s" % ", ".join(unbacked))
    return errors, warnings


def main(argv):
    path = argv[0] if argv else DEFAULT_CSV
    errors, warnings = check(path)
    for w in warnings:
        print("WARN  %s" % w)
    for e in errors:
        print("FAIL  %s" % e)
    print("measurements.csv: %d error(s), %d warning(s)" % (len(errors), len(warnings)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
