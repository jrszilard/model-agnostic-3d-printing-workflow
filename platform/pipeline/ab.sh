#!/usr/bin/env bash
# ab.sh — run a command against an old revision of ONE file, then the working copy, in place.
#
# WHY THIS IS A SCRIPT
# The obvious way to A/B a pipeline change is to copy the old file somewhere and run it there. That
# does not work here and fails in the WORST possible direction. verify.py resolves parts/_lib off
# its own path; platform_boundary.py derives ROOT from __file__ (run from /tmp it walked the whole
# of /tmp and had to be killed); handoff.sh sources ../stamp.sh; render.sh sources ../../stamp.sh.
# Run any of them from a scratch directory and the OLD side dies on a missing sibling while the NEW
# side works — a 28-line diff that reads exactly like a finding, and a "speedup" that is really a
# broken baseline. That happened three times in one session on 2026-09-04.
#
# So: swap the file IN PLACE, run, restore. The tree is left exactly as it was found, including on
# a failure or an interrupt.
#
# Usage:
#   platform/pipeline/ab.sh <tracked-file> <git-ref> -- <command...>
#
# Example:
#   platform/pipeline/ab.sh platform/pipeline/verify/verify.sh HEAD -- \
#       platform/pipeline/verify/verify.sh parts/clips/hose-clip
set -uo pipefail
FILE=${1:?usage: ab.sh <tracked-file> <git-ref> -- <command...>}
REF=${2:?usage: ab.sh <tracked-file> <git-ref> -- <command...>}
shift 2
[ "${1:-}" = "--" ] || { echo "ab.sh: expected -- before the command" >&2; exit 2; }
shift
[ $# -gt 0 ] || { echo "ab.sh: no command given" >&2; exit 2; }

ROOT=$(git rev-parse --show-toplevel) || exit 2
cd "$ROOT" || exit 2
git ls-files --error-unmatch "$FILE" >/dev/null 2>&1 || {
    echo "ab.sh: $FILE is not tracked; there is no old revision to compare against" >&2; exit 2; }

TMP=$(mktemp -d) || exit 2
cp "$FILE" "$TMP/working" || exit 2
git show "$REF:$FILE" > "$TMP/old" 2>/dev/null || {
    echo "ab.sh: $FILE does not exist at $REF" >&2; rm -rf "$TMP"; exit 2; }
# Restore on ANY exit, including SIGINT — a half-swapped tree is the thing this script exists to
# prevent, and leaving one behind would be worse than the copy-to-scratch mistake it replaces.
restore(){ cp "$TMP/working" "$FILE" 2>/dev/null; rm -rf "$TMP"; }
trap restore EXIT INT TERM

run_side(){
    cp "$2" "$FILE" || return 2
    local s e
    s=$(date +%s%3N); "${CMD[@]}" > "$TMP/$1.out" 2>&1; local rc=$?; e=$(date +%s%3N)
    printf '%-4s rc=%-3s %6d ms\n' "$1" "$rc" "$((e - s))" >&2
    echo "$rc" > "$TMP/$1.rc"
}
CMD=("$@")
run_side old "$TMP/old"
run_side new "$TMP/working"

echo "--- diff old -> new (empty means the outputs are identical) ---" >&2
diff "$TMP/old.out" "$TMP/new.out"
d=$?
[ "$d" = 0 ] && echo "OUTPUT IDENTICAL" >&2
exit "$d"
