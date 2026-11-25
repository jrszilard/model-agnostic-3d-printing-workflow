#!/usr/bin/env bash
# test.sh — software suites, INCLUDING CadQuery execution and broad corpus/registry checks.
#
# These guarantees only hold if something actually runs them: the joint registry's schema
# validation fires at import, `docs/joinery.md` staleness is a test, and the measurements log's
# foreign key into the registry is checked here. Nothing else in this repo runs them, so run
# this before committing.
#
# THE STAGES RUN CONCURRENTLY; THE TRANSCRIPT DOES NOT.
# Twelve independent suites used to run one after another on a 16-core box. Each stage's output is
# now captured to its own file and replayed in the original fixed order once every one has been
# waited on, so what a human reads is what the serial run printed — the concurrency is in the
# scheduling, not in the report.
#
# Two things this must not get wrong, both recorded because the obvious version gets them wrong:
#
#   1. STATUS COMES FROM `wait`, NEVER FROM AN ASSIGNMENT INSIDE THE JOB. The old `run()` helper
#      set FAIL=1 in its own shell. Append a bare `&` to that and the assignment happens in a
#      SUBSHELL, where it is discarded — and with no `set -e` here, the script would go on to
#      print ALL GREEN and exit 0 over a red suite. There is no worse defect available in a test
#      runner than one that cannot fail.
#   2. A HANG MUST STILL NAME ITSELF. `run()` printed `=== name ===` BEFORE running, so a stuck
#      suite was identifiable by the last header on screen. Buffer-and-replay prints nothing until
#      every job is waited, which would take that away. The `  · name` line on stderr at launch is
#      that identification. It is different content from the transcript, not a duplicate of it.
#
# Usage: platform/pipeline/test.sh [--require-cadquery]   exit 0 = all green
set -uo pipefail
REQUIRE_CADQUERY=0
for arg in "$@"; do
    case "$arg" in
        --require-cadquery) REQUIRE_CADQUERY=1 ;;
        *) echo "usage: platform/pipeline/test.sh [--require-cadquery]" >&2; exit 2 ;;
    esac
done
HERE=$(dirname "$(readlink -f "$0")")
ROOT=$(readlink -f "$HERE/../..")
cd "$ROOT" || exit 2
FAIL=0

LOGDIR=$(mktemp -d) || exit 2
trap 'rm -rf "$LOGDIR"' EXIT
NAMES=(); PIDS=(); LOGS=()

launch() {
    local name=$1; shift
    local log; log=$(printf '%s/%02d.log' "$LOGDIR" "${#NAMES[@]}")
    "$@" >"$log" 2>&1 &
    NAMES+=("$name"); PIDS+=("$!"); LOGS+=("$log")
    printf '  · %s\n' "$name" >&2
}

CQPY=${CADQUERY_PY:-$HOME/cadquery-env/bin/python}

# Launched FIRST and read LAST. The ledger blocks nothing and cannot fail the run (adoption.py:13-14
# — "a THERMOMETER, NOT A GATE"), so its full-repo walk has no business sitting between the verdict
# and the prompt.
python3 "$HERE/adoption.py" "$ROOT" >"$LOGDIR/adoption.log" 2>&1 &
ADOPTION_PID=$!

launch "joint registry (parts/_lib)"        python3 -m unittest discover -s parts/_lib -p 'test_*.py'
# ONE interpreter for both cadquery-env suites. `import cadquery` is ~1.9 s and ~471 MB resident,
# and two stages each paid it; with the stages concurrent that is 471 MB in the same instant, not
# merely 1.9 s twice in sequence.
if [ -x "$CQPY" ]; then
    launch "CadQuery suites (cadquery-env)" "$CQPY" "$HERE/cadquery_suites.py"
elif [ "$REQUIRE_CADQUERY" = 1 ]; then
    launch "CadQuery suites (cadquery-env)" bash -c "echo 'FAIL: CADQUERY_PY not executable: $CQPY' >&2; exit 1"
else
    printf '  · CadQuery suites (skipped: %s not found; pass --require-cadquery to fail)\n' "$CQPY" >&2
fi
# The gate registry sits at platform/pipeline/ because verify/, slice/ and handoff/ all read it,
# which put it outside every per-directory discovery root below — a conformance test that never runs
# is the same failure as the stale index it exists to prevent. Pattern-scoped so the recursive walk
# from this root picks up only this file and does not re-run the suites launched separately.
launch "gate registry conformance"          python3 -m unittest discover -s platform/pipeline -t platform/pipeline -p 'test_gates.py'
launch "next-action / gate trace"           python3 -m unittest discover -s platform/pipeline -t platform/pipeline -p 'test_next_action.py'
launch "plate scope / clarification (offline)" python3 -m unittest discover -s platform/pipeline -t platform/pipeline -p 'test_plate_scope.py'
# Offline only: never auto-launch the opt-in namespace/CAD evaluation controls here.
launch "isolated-evaluation offline tooling" python3 -m unittest discover -s platform/pipeline/isolation -p 'test_*.py'
launch "verify gates (platform/pipeline)"   python3 -m unittest discover -s platform/pipeline/verify -p 'test_*.py'
launch "slice tooling"                      python3 -m unittest discover -s platform/pipeline/slice -p 'test_*.py'
launch "preview/drawing tooling"            python3 -m unittest discover -s platform/pipeline/preview -p 'test_*.py'
launch "working model"                      python3 -m unittest discover -s platform/pipeline/working-model -p 'test_*.py'
launch "bounded preparation/reuse"          python3 -m unittest discover -s platform/pipeline/prepare -p 'test_*.py'
if [ -d platform/ai ]; then
    launch "advisory AI tooling"            python3 -m unittest discover -s platform/ai -p 'test_*.py'
fi
launch "codegen template syntax"            python3 -m unittest discover -s platform/codegen-templates -p 'test_*.py'
launch "docs/joinery.md mirrors the registry" python3 parts/_lib/render_registry.py --check
if [ -f research/results/measurements.csv ]; then
    launch "measurements.csv sample references" python3 platform/pipeline/verify/measurements_check.py
fi
launch "generator cross-references"         python3 platform/pipeline/verify/generator_refs.py parts
# A2. The primary a spec NAMES — or the one verify.py:125 PICKS when it names none — must be an
# artifact a clean clone actually gets: seven specs pointed theirs at a --draft- variant, which
# .gitignore:102-109 untracks, and the resulting UNPROVEN B-rep + skipped DFM were invisible
# because the files sat on the author's disk. There is no allow-list; A3 re-includes the one
# artifact each spec declares, whatever its status segment says.
launch "spec primary artifacts"             python3 platform/pipeline/verify/spec_primary_check.py
# A gate that cannot fire is worse than none: it produces confidence instead of caution, which is
# how BL1 shipped. On 2026-09-04 a review found three assertions in parts/**/src that can never
# fail -- including the one keeping the anchor out of the protected nOOd channel, BL1's own scar --
# and this check found a fourth nobody had looked at. Structural only; it cannot see a gate that
# merely has too much slack.
launch "dead gates (assertions that cannot fail)" python3 platform/pipeline/verify/dead_gate_check.py
if [ -d scripts ]; then
    launch "repo scripts & public guard tests" python3 -m unittest discover -s scripts -p 'test_*.py'
fi

for i in "${!NAMES[@]}"; do
    wait "${PIDS[$i]}" || FAIL=1
    printf '\n=== %s ===\n' "${NAMES[$i]}"
    cat "${LOGS[$i]}"
done

printf '\n'
if [ "$FAIL" = 0 ]; then echo "ALL GREEN"; else echo "FAILURES ABOVE"; fi

# The suite above answers "does the machinery work?". This answers "is anyone using it?" — the
# question that went unasked while provenance sat at 0/16 specs and probe.py at 1/69 generators.
# It blocks nothing and cannot fail the run; it is here because this is the command already run on
# every checkpoint and every land, so a mechanism landing at zero adoption is visible the same day.
wait "$ADOPTION_PID" || true
cat "$LOGDIR/adoption.log"

exit "$FAIL"
