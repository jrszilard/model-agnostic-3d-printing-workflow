#!/usr/bin/env bash
# rebuild-all.sh — regenerate every part's geometry from source.
#
# WHY THIS EXISTS
# The repo stopped tracking assembly/mockup visualisations and option-study variants (907 MB, 78%
# of history) on the promise that they rebuild from src/. A promise with no entry point is not a
# promise: build.sh takes ONE source at a time and there are ~70 generators, so "just regenerate
# it" was, in practice, unavailable to anyone with a fresh clone.
#
# --check is the real payoff. It rebuilds everything in place and then asks git whether any TRACKED
# geometry moved. Zero changes proves the determinism the untracking trade rests on — CadQuery STL
# natively, CadQuery STEP via c14n_step.py, OpenSCAD STL via c14n_stl.py. If that check ever goes
# red, the trade is broken and the geometry has to come back into git.
#
# WIDTH IS OPT-IN AND THE DEFAULT STAYS 1 (78 generators, 16 cores, 2026-09-04)
# --jobs N is worth using deliberately: interleaved A/B over photo-calibration-corner's 18
# generators, alternating P1,P4,P1,P4 so both widths see the same box, gave 99.9/87.9 s at
# --jobs 1 against 37.8/30.9 s at --jobs 4 — 2.6x and 2.8x, all four runs 14 ok / 4 fail with
# a byte-identical sorted verdict list (an earlier A/B on bottle-lamp-base measured 1.8x — take
# 2-3x as the range, not a headline). The DEFAULT is 1 anyway, because build.sh's canonicalisation
# is not per-generator and the fix for that is not in this file. Three hazards, worst first:
#  * CANONICALISATION IS SHARED STATE — this is what blocks the raise. build.sh:22-25 hands
#    c14n every *.step/*.stl under the PART dir newer than a mark it takes at its own start. At
#    --jobs 1 that only ever matches the generator's own exports (instrumented: one file per
#    build.sh). At --jobs 4 the windows overlap — the same instrumentation logged two sibling
#    build.sh processes handing c14n_step.py the SAME three files 3 ms apart, one of them still
#    being written by a third generator. Two concurrent c14n_step.py on one not-yet-canonical
#    STEP left it PERMANENTLY TRUNCATED in 16 and 10 of 300 trials, twice (3.5-7.0 MB against a
#    7.0 MB original), silently, both processes exiting 0: c14n_step.py:25-31 reads, a sibling's
#    open(path,'wb') truncates, the first writes its short prefix back. The preconditions are the
#    normal case, not an edge — 69 of the 78 generators sit in a part that has other generators,
#    and 69 export more than once, so a STEP stays non-canonical while its own script models on.
#    A truncated tracked STEP is what --check then reports as DRIFT, so at width the determinism
#    proof can cause its own red and blame a generator for it. pipeline-speed-plan.md already
#    forbids this shape for the render fan-out (T1.7/T2.5: "canonicalise() must not run inside
#    forked children, because c14n_stl.py:50 is a non-atomic in-place truncate+write of the
#    shared input"); G2's own safety row, "independent processes, no shared state", is wrong.
#    Raise this default when c14n_step.py and c14n_stl.py write temp+rename, not before.
#  * MEMORY. bottle-lamp-carrier.py alone is OOM-killed at 25 s against a 6 GB cgroup cap with
#    the box to itself (systemd scope, 3 min 6 s of CPU burnt in 25 s of wall clock);
#    docs/versioning.md books it as "OCC process abort", but it is a memory blowup as much as an
#    abort. At --jobs 1 that kills one python, build.sh returns nonzero, the generator is
#    reported FAIL and the run still finishes a complete report. At width the kernel picks its
#    victim among the siblings and the run dies with no summary line at all.
#  * ORDER. Three generators read another PART's geometry — bottle-lamp-stopper.py:105 and
#    b2b-r2/...-review.py:35 importStep bottle-lamp-carrier/vendor/umiki-bottle--hollow.step,
#    which umiki_mesh_from_photo.py:104 writes, and led-risers.py:96 reads the carrier's spiral
#    STL. At --jobs 1 the only thing keeping producer and consumer apart is that git ls-files
#    hands them over in sorted order. A reader racing that write saw a torn file in 200 of 4000
#    reads; importStep raises ValueError on a torn STEP, so this one fails loudly - but it still
#    makes --check's verdict depend on timing.
#
# A KILLED CHILD USED TO BE INVISIBLE, at any width. "built N - failed M" counted only the lines
# children printed, so a child killed outright vanished: matched pair, one worker SIGKILLed under
# --check --jobs 4, and the old script reported "built 5 - failed 0", then CLEAN, and exited 0 -
# a determinism verdict about a rebuild that did not happen. That is what LOST and VOID below fix:
# they do not make width safe, they make a run that died at width say so.
#
# Usage:
#   rebuild-all.sh [--list] [--check] [--jobs N] [--strict] [filter]
#     --list     show what would run, run nothing
#     --check    refuse a dirty tree, rebuild, then report tracked geometry that changed
#     --jobs N   build N generators at once (default 1; see WIDTH IS OPT-IN above)
#     --strict   stop at the first failing generator (default: run all, report at the end)
#     --all-sources  also run a .scad that a same-named .py supersedes (they collide)
#     filter     substring; only generators whose path contains it
# Exit: 0 all built (and, with --check, nothing moved) · 1 a generator failed, or one was killed
#       without reporting, or --check could not run because the rebuild stopped · 3 --check found drift
set -uo pipefail
HERE=$(dirname "$(readlink -f "$0")")
ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2

LIST=0; CHECK=0; JOBS=1; STRICT=0; FILTER=""; ALLSRC=0
while [ $# -gt 0 ]; do case "$1" in
    --list) LIST=1;; --check) CHECK=1;; --strict) STRICT=1;; --all-sources) ALLSRC=1;;
    --jobs) shift; JOBS=${1:-1};;
    -*) echo "unknown option: $1" >&2; exit 2;;
    *) FILTER=$1;;
esac; shift; done

# A generator is a source under a part's src/ that actually exports geometry. Helpers (joint
# builders, outline data, process tables) live alongside and must not be run.
mapfile -t GENS < <(
    { git ls-files 'parts/**/src/*.py' 'decor/**/src/*.py' 'parts/**/src/*.scad' 'decor/**/src/*.scad'
      git ls-files 'parts/**/src/**/*.py' 'decor/**/src/**/*.scad'; } | sort -u |
    while read -r f; do
        case "$f" in */_lib/*|*/preview/*) continue;; esac
        [ -n "$FILTER" ] && case "$f" in *"$FILTER"*) :;; *) continue;; esac
        case "$f" in
            *.py)   grep -q 'exporters\.export\|export_step\|\.export(' "$f" && echo "$f";;
            *.scad)
                # A part with BOTH src/x.py and src/x.scad has two generators racing for the same
                # stl/x.stl, and whichever runs last wins. hose-clip is the live case: the .py is
                # what produced the committed bytes, the .scad is the superseded original. Prefer
                # the .py and say so, rather than silently clobbering a part on every rebuild.
                if [ "$ALLSRC" != 1 ] && [ -f "${f%.scad}.py" ]; then
                    echo "SKIP:$f" >&2
                else
                    echo "$f"
                fi;;
        esac
    done
)

[ ${#GENS[@]} -gt 0 ] || { echo "no generators matched${FILTER:+ filter '$FILTER'}"; exit 0; }

if [ "$LIST" = 1 ]; then
    printf '%s\n' "${GENS[@]}"; echo; echo "${#GENS[@]} generator(s)"; exit 0
fi

if [ "$CHECK" = 1 ] && [ -n "$(git status --porcelain)" ]; then
    echo "REFUSING: --check needs a clean tree — it reads git status as its result." >&2
    echo "  commit or stash first." >&2
    exit 2
fi

# outdir for .scad is the part's stl/; .py generators anchor their own paths on __file__.
build_one(){
    local src=$1 out rc=0
    case "$src" in
        *.scad) out="$(dirname "$(dirname "$src")")/stl"; mkdir -p "$out";;
        *)      out=$(mktemp -d);;
    esac
    if "$HERE/build.sh" "$src" "$out" >/dev/null 2>&1; then echo "ok   $src"
    else echo "FAIL $src"; rc=1; fi
    case "$src" in *.py) rmdir "$out" 2>/dev/null;; esac
    # 255 is the one exit status xargs reads as "abort the whole run", so --strict means the same
    # thing at every width. Without this it was silently ignored above --jobs 1: measured, --strict
    # stopped after 1 generator at --jobs 1 and ran all 3 at --jobs 3.
    [ "$rc" = 1 ] && [ "$STRICT" = 1 ] && exit 255
    return 0
}
export -f build_one; export HERE STRICT

echo "rebuilding ${#GENS[@]} generator(s), jobs=$JOBS"
start=$SECONDS
RESULTS=$(mktemp); trap 'rm -f "$RESULTS"' EXIT
stopped=0
if [ "$JOBS" -gt 1 ]; then
    # Completion order above --jobs 1 is a race: three --jobs 6 runs of the same 12 generators gave
    # two different orders, identical once sorted. A rebuild proof that reorders run to run cannot
    # be diffed, so stdout gets the sorted report at the end — while the live lines still go to
    # stderr, because this takes minutes and a hang has to stay visible. They are bulleted because
    # unprefixed they read, on a terminal where both streams land, as the report printed twice.
    # -0: xargs' default quote processing eats the input. A generator at parts/.../q'uote.py was
    # silently dropped at --jobs 4 ("unmatched single quote"), counted by nothing but LOST below.
    printf '%s\0' "${GENS[@]}" | xargs -0 -P "$JOBS" -I{} bash -c 'build_one "$@"' _ {} \
        | tee "$RESULTS" | sed -u 's/^/  · /' >&2
    [ "${PIPESTATUS[1]}" = 124 ] && { echo "--strict: stopping" >&2; stopped=1; }
    sort "$RESULTS"
else
    for g in "${GENS[@]}"; do
        r=$(build_one "$g"); echo "$r"; echo "$r" >> "$RESULTS"
        if [ "$STRICT" = 1 ] && [ "${r#FAIL}" != "$r" ]; then echo "--strict: stopping" >&2; stopped=1; break; fi
    done
fi
fails=$(grep -c '^FAIL' "$RESULTS"); oks=$(grep -c '^ok' "$RESULTS")
lost=0; [ "$stopped" = 0 ] && lost=$(( ${#GENS[@]} - oks - fails ))
echo
echo "built $oks · failed $fails · $((SECONDS-start))s"

rc=0
[ "$fails" -gt 0 ] && rc=1

# A child that is killed outright prints neither ok nor FAIL, so built/failed silently under-counts
# and a run that lost generators can still exit 0 — measured, at --jobs 4, with a --check verdict
# attached to it. The OOM killer is the cause seen here; the gate asserts the arithmetic, not the
# cause, so it also catches a generator that never reached a worker at all. Name what never reported.
if [ "$lost" -gt 0 ]; then
    echo
    echo "LOST — $lost generator(s) produced no result at all:"
    comm -13 <(cut -c6- "$RESULTS" | sort) <(printf '%s\n' "${GENS[@]}" | sort) | sed 's/^/  /'
    echo "  Nothing above counts these — a killed child prints neither ok nor FAIL."
    echo "  Retry at --jobs 1 before reading anything into the counts above."
    rc=1
fi

if [ "$CHECK" = 1 ]; then
    echo
    echo "=== determinism check: did any TRACKED geometry move? ==="
    moved=$(git status --porcelain -- '*.stl' '*.step' '*.3mf' | grep -c .)
    if [ "$lost" -gt 0 ] || [ "$stopped" = 1 ]; then
        # A generator that never ran cannot have moved its exports, so a clean tree here would say
        # "determinism holds" about work that was not done. The proof is void, not passing.
        echo "VOID — the rebuild did not complete, so this check proves nothing."
        rc=1
    elif [ "$moved" = 0 ]; then
        echo "CLEAN — every tracked export rebuilt byte-identical."
    else
        echo "DRIFT — $moved tracked geometry file(s) changed on a rebuild:"
        git status --porcelain -- '*.stl' '*.step' '*.3mf' | head -20 | sed 's/^/  /'
        echo
        echo "Untracking regenerable geometry assumed this stays clean. Investigate before"
        echo "trusting a rebuild: check platform/pipeline/toolchain.sh for version drift first."
        rc=3
    fi
fi
exit "$rc"
