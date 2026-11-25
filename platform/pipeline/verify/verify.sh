#!/usr/bin/env bash
# verify.sh — assert a part's exports against its spec.yaml (CAD integrity + dimensions).
# Usage: verify.sh <part_dir>          exit 0 = PASS, 1 = FAIL
#
# It also RECORDS the verdict beside the part, in <part_dir>/verify.stamp. Until 2026-09-03 it did
# not: verify.py is the only thing in either repo that proves step_valid / closed / no_bad_faces,
# nothing automated runs it, and it wrote nothing to disk — so by the time a plate reached the
# handoff there was no way to tell whether the B-rep had ever been checked, on which bytes, or what
# it said. handoff.sh now refuses (exit 14) without that record.
set -uo pipefail
PART=${1:?part_dir}
FREECADCMD=${FREECADCMD:-$(command -v freecadcmd || echo freecadcmd)}
HERE=$(dirname "$(readlink -f "$0")")
. "$HERE/../stamp.sh"
. "$HERE/../gates.sh"
PART_ABS=$(readlink -f "$PART")
TMP=$(mktemp)
PART_DIR="$PART_ABS" "$FREECADCMD" "$HERE/verify.py" >"$TMP" 2>&1 || true
# show the report, hide FreeCAD's \r progress bars + banner
tr '\r' '\n' < "$TMP" | sed -n '/=== verify/,/VERIFY_RESULT/p' | grep -vE '\([0-9]+ %\)|^Checking'
# Which verdicts may proceed is gates.txt's answer, not this file's. It was written here as a
# literal `(PASS|DEBT)` on 2026-09-06 and that is precisely the habit that hid the second gate: a
# verdict set spelled out at a call site is a copy, and copies are what stop agreeing.
#
# The condition argument is 1 because the plate-kind question is not this layer's. verify.sh records
# what the part is; handoff.sh decides whether a plate of that kind may cut material against it.
# Answering it here would put the prototype's latitude in front of every consumer at once.
rc=0; gate_allows VERIFY_RESULT "$(cat "$TMP")" 1 || rc=1
_report=$(tr '\r' '\n' < "$TMP")
# When verify.py dies there is no VERIFY_RESULT line, and the sed range above then prints from
# "=== verify" to end of file — which does not hold the traceback. stdout is block-buffered when
# redirected (verify.py:409 flushes by hand for exactly this reason) while stderr is not, so a
# crash lands its diagnosis BEFORE the marker and the filter drops it. Silent before A1; expensive
# now, because the stamp records ERROR and the handoff refusal says "fix the part" with nothing on
# screen naming what broke. Reproduced 2026-09-04 against a toolchain that exits mid-run.
[ -n "$(gate_verdict VERIFY_RESULT "$(cat "$TMP")")" ] || {
    echo "*** verify.py produced no verdict. Raw output (this is a toolchain fault, not the part):" >&2
    printf '%s\n' "$_report" | tail -20 | sed 's/^/    /' >&2
}
rm -f "$TMP"

# --- the verdict, recorded (A1) ------------------------------------------------------------------
# "verify passed" is not checkable at the plate on its own — it is only meaningful next to WHICH
# bytes it passed on. So the stamp carries the sha256 of the STEP verify.py read plus the geom id of
# every STL the part held at that moment, and handoff.sh matches the plate's geom ids against that
# list. Same binding that already refuses a stale preview at exit 10: identity travels with the
# bytes, so it cannot drift the way a filename or a timestamp can.
if [ -n "$PART_ABS" ] && [ -d "$PART_ABS" ]; then
    # Ask verify.py which STEP it resolved rather than re-deriving it here: it picks
    # spec.primary_step, else the first non-coupon file in step/ (verify.py:125), and a second
    # implementation of that rule would drift from the one that produced the verdict.
    _step_rel=$(printf '%s\n' "$_report" | sed -n 's/^primary STEP: //p' | head -1)
    _step=""
    case "$_step_rel" in ""|"(none)") _step_rel="(none)";; *) _step="$PART_ABS/$_step_rel";; esac
    # UNPROVEN is verify.py's own word (verify.py:307-309) for "no STEP export, so B-rep validity
    # was never tested" — it is not a pass. An OpenSCAD-only part has no B-rep to validate, and per
    # Justin's 2026-09-03 directive that blocks the handoff rather than being grandfathered.
    # ERROR is separate on purpose: freecadcmd not producing a verdict at all is not a FAIL verdict.
    _announced=$(gate_verdict VERIFY_RESULT "$_report")
    if [ -z "$_announced" ]; then _verdict=ERROR
    elif [ "$rc" != 0 ]; then _verdict=FAIL
    elif [ -z "$_step" ] || [ ! -f "$_step" ]; then _verdict=UNPROVEN
    # Order matters: no STEP is checked FIRST, so a part with declared debt and no B-rep to validate
    # is still UNPROVEN. Debt is a statement about one nominal, never a substitute for having looked
    # at the solid, and letting DEBT outrank UNPROVEN would have handed the weaker word the win.
    elif [ "$_announced" = DEBT ]; then _verdict=DEBT
    else _verdict=PASS
    fi

    # Every *.stl under the PART, at any depth — not stl/, and not stl/'s top level. Both narrower
    # scans lose real geometry: bottle-lamp-base holds 187 STLs of which only 88 are at the top of
    # stl/ (the rest in stl/coil-set/ and stl/b2b-r4/), and bottle-lamp-carrier has no stl/ at all.
    # handoff.sh binds a plated model to a part by walking up to the nearest spec.yaml at ANY depth,
    # so anything this scan misses is a model it can never match: measured 2026-09-04, a part whose
    # STL sat beside its spec recorded stls=0 and the plate refused at exit 14 twice in a row —
    # once, then again after running the `verify.sh <part_dir>` the refusal itself named.
    _stls=()
    while IFS= read -r -d '' _f; do _stls+=("$_f"); done \
        < <(find "$PART_ABS" -type f -name '*.stl' -print0 2>/dev/null | sort -z)
    _rows=()
    if [ ${#_stls[@]} -gt 0 ]; then
        # One c14n launch for the whole set. geom_id() canonicalises per call, which is a python
        # process per STL — 187 of them on bottle-lamp-base. c14n_stl.py already takes a list and
        # rewrites only when the bytes change, so the geom ids are identical either way.
        #
        # RECORD everything under the part; REWRITE only what the part authored. c14n_stl.py writes
        # IN PLACE, so canonicalising releases/ would have a *verification* command mutate a shipped
        # revision (.gitignore:97 keeps one as an immutable record) and vendor/ would rewrite a
        # third-party mesh nobody here authored — dirtying the tree, which then makes version_line()
        # stamp +dirty into the very verify.stamp being written. They are still HASHED and recorded:
        # a plate may legitimately be sliced from a release artifact, and a verdict that omitted its
        # id would refuse that plate at exit 14 for geometry it had actually checked.
        _canon=()
        for _f in "${_stls[@]}"; do
            case "$_f" in */releases/*|*/vendor/*) continue;; esac
            _canon+=("$_f")
        done
        [ ${#_canon[@]} -eq 0 ] || python3 "$HERE/../generate/c14n_stl.py" "${_canon[@]}" >/dev/null 2>&1
        for _f in "${_stls[@]}"; do
            _h=$(sha256sum "$_f" 2>/dev/null) || continue
            _rows+=("stl=${_h:0:8} ${_f#"$PART_ABS"/}")
        done
    fi
    # write_stamp's own geom=/sha256=/source= then name the STEP these checks ran on. With no STEP
    # they come out empty, which is the honest record for UNPROVEN: there were no B-rep bytes.
    #
    # In the PART's directory, because write_stamp's version= comes from version_line(), which runs
    # git wherever it is standing. handoff.sh prints that line back as "recorded by verify.sh at
    # <version>", so run from the wrong tree it attributes the verdict to a branch and sha that
    # never saw the part: observed 2026-09-04 stamping "rev/balloon-clip@13bd9f0" onto a part under
    # /tmp that is in no repository at all. Everything else here is already an absolute path.
    ( cd "$PART_ABS" && write_stamp "$PART_ABS/verify.stamp" "$_step" \
        "verdict=$_verdict" "step=$_step_rel" "stls=${#_rows[@]}" ${_rows[@]+"${_rows[@]}"} )
    echo "verdict recorded: $_verdict  ->  $PART_ABS/verify.stamp"
fi

# DFM advisory. Never affects rc: these are mesh heuristics and AGENTS.md reserves blocking for
# deterministic checks. It runs AFTER the verdict so a warning cannot be mistaken for a failure.
if [ "${DFM:-1}" = 1 ]; then
    # WHICH FILES. The skip list is a naming convention, and a naming convention is the wrong thing
    # to hang coverage on: seven specs named a `--draft-` path as their primary_stl, so the one
    # artifact the part IS got no DFM at all — 8 of 22 spec'd parts, on a check whose own docstring
    # (dfm_check.py:6-16) lists three prints this shop paid for. The declared primary is therefore
    # always checked, whatever its filename says; the skips still apply to everything else, which is
    # what they were written for (option studies, mockups, preview composites).
    _primary=""
    if [ -f "$PART_ABS/spec.yaml" ]; then
        _primary=$(python3 -c '
import sys, yaml
try:
    doc = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
except Exception:
    doc = {}
print(doc.get("primary_stl") or "")' "$PART_ABS/spec.yaml" 2>/dev/null)
    fi
    _primary_abs=""
    [ -n "$_primary" ] && _primary_abs=$(readlink -f "$PART_ABS/$_primary" 2>/dev/null)

    _dfm=()
    for _stl in "$PART"/stl/*.stl; do
        [ -f "$_stl" ] || continue
        if [ -n "$_primary_abs" ] && [ "$(readlink -f "$_stl")" = "$_primary_abs" ]; then
            _dfm+=("$_stl"); continue
        fi
        case "$_stl" in *--draft-*|*mockup-*|*_preview-*) continue;; esac
        _dfm+=("$_stl")
    done

    # Fanned out, because rc was fixed at :20 before this block ever runs — DFM cannot change the
    # verdict, so nothing here is ordered by a data dependency. Bounded at 8: on a near-idle box
    # -P16 measured SLOWER than -P8 (30,886 ms against 29,222), the signature of a saturated memory
    # bus rather than idle cores. Each file's warnings are buffered and emitted in sorted filename
    # order after the wait, so the report text stays byte-identical to the serial run.
    if [ ${#_dfm[@]} -gt 0 ]; then
        _dfmdir=$(mktemp -d)
        _running=0
        for _stl in "${_dfm[@]}"; do
            {
                python3 "$HERE/dfm_check.py" "$_stl" 2>/dev/null                     | sed -n '/WARN:/p' | sed "s#^#  $(basename "$_stl"): #"
            } > "$_dfmdir/$(basename "$_stl").warn" &
            _running=$((_running + 1))
            # `|| true`, not `|| wait`. wait -n returns the finished JOB's exit status, and this
            # pipeline runs under `set -o pipefail`, so a dfm_check.py crash on a bad mesh makes the
            # job non-zero -- which sent control to a blocking `wait` for every outstanding job while
            # _running was decremented by one. _running then stayed at the cap for the rest of the
            # loop and the fan-out silently degenerated to one file at a time, which is the whole of
            # this item's saving. DFM is advisory and rc was fixed at :20, so a failed job is
            # correctly ignored here; its absent WARN lines are the report.
            if [ "$_running" -ge 8 ]; then wait -n 2>/dev/null || true; _running=$((_running - 1)); fi
        done
        wait
        for _w in "$_dfmdir"/*.warn; do [ -f "$_w" ] && cat "$_w"; done
        rm -rf "$_dfmdir"
    fi
fi
exit "$rc"
