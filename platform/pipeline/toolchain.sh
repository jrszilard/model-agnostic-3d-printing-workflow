#!/usr/bin/env bash
# Report whether every declared version in platform/toolchain.lock matches this host.
# This establishes environment identity only; it does not prove that a historical STL was built
# here or that source and export agree. rebuild-all.sh --check is the separate reproduction test.
set -uo pipefail
HERE=$(dirname "$(readlink -f "$0")")
ROOT=$(readlink -f "$HERE/../..")
LOCK=${TOOLCHAIN_LOCK:-"$ROOT/platform/toolchain.lock"}

if [ ! -f "$LOCK" ]; then
    echo "toolchain lock missing: $LOCK" >&2
    exit 1
fi

want() {
    awk -F= -v key="$1" '
        { lhs=$1; gsub(/[[:space:]]/, "", lhs) }
        lhs == key { value=$2; sub(/^[[:space:]]+/, "", value); sub(/[[:space:]]+$/, "", value);
                     print value; exit }
    ' "$LOCK"
}

expand_home() {
    case "$1" in
        '~') printf '%s\n' "$HOME" ;;
        '~/'*) printf '%s/%s\n' "$HOME" "${1#\~/}" ;;
        *) printf '%s\n' "$1" ;;
    esac
}

ok=1
checked=0
check() {
    local name=$1 actual=${2:-missing} expected=${3:-}
    checked=$((checked + 1))
    if [ -z "$expected" ]; then
        printf '%-13s %-16s  [UNPINNED]\n' "$name" "$actual"
        ok=0
    elif [ "$actual" = "$expected" ]; then
        printf '%-13s %-16s  [ok]\n' "$name" "$actual"
    else
        printf '%-13s %-16s  [want %s]\n' "$name" "$actual" "$expected"
        ok=0
    fi
}

venv=$(expand_home "$(want cadquery_venv)")
CADQUERY_PY=${CADQUERY_PY:-"$venv/bin/python"}

if [ -x "$CADQUERY_PY" ]; then
    py=$($CADQUERY_PY --version 2>&1 | awk '{print $2; exit}')
    cq=$($CADQUERY_PY -c 'import cadquery; print(cadquery.__version__)' 2>/dev/null || echo missing)
    ocp=$($CADQUERY_PY -c 'import OCP; print(OCP.__version__)' 2>/dev/null || echo missing)
else
    py=missing; cq=missing; ocp=missing
fi

if command -v openscad >/dev/null 2>&1; then
    osc=$(openscad --version 2>&1 | awk '{print $NF; exit}')
else
    osc=missing
fi

if command -v prusa-slicer >/dev/null 2>&1; then
    ps=$(prusa-slicer --help 2>&1 | awk '
        match($0, /PrusaSlicer-[0-9][^ +]*/) {
            value = substr($0, RSTART + 12, RLENGTH - 12); print value; exit
        }')
    [ -n "$ps" ] || ps=missing
else
    ps=missing
fi

check python "$py" "$(want python)"
check cadquery "$cq" "$(want cadquery)"
check ocp "$ocp" "$(want ocp)"
check openscad "$osc" "$(want openscad)"
check prusaslicer "$ps" "$(want prusaslicer)"

# A newly pinned producer must not disappear behind a stale checker and another broad MATCH result.
# cadquery_venv is a location, not a version; every other lock key needs an implementation above.
while IFS='=' read -r raw_key _; do
    key=$(printf '%s' "${raw_key%%#*}" | tr -d '[:space:]')
    [ -n "$key" ] || continue
    case "$key" in
        cadquery|ocp|python|openscad|prusaslicer|cadquery_venv) ;;
        *) echo "$key          [NO CHECK IMPLEMENTED]"; ok=0 ;;
    esac
done < "$LOCK"

echo "cadquery python: $CADQUERY_PY"
echo "lock:            $LOCK"
if [ "$ok" = 1 ]; then
    echo "ALL DECLARED VERSION ENTRIES MATCH ($checked checked; coverage/build provenance not attested)"
    exit 0
else
    echo "TOOLCHAIN DRIFT OR MISSING PIN — rebuilds may not match committed geometry" >&2
    exit 1
fi
