#!/usr/bin/env bash
# build.sh — run a part's parametric SOURCE to produce printable geometry.
# Usage: build.sh <source.scad|source.py> <outdir> [extra openscad -D args...]
#   .scad -> STL via OpenSCAD/CGAL.   .py (CadQuery) -> the script exports STL+STEP itself.
set -euo pipefail
SRC=${1:?source file}; OUT=${2:?outdir}; shift 2 || true
mkdir -p "$OUT"
OSC=${OPENSCAD:-openscad}
case "$SRC" in
  *.scad) b=$(basename "${SRC%.scad}")
    "$OSC" -o "$OUT/$b.stl" --export-format binstl "$@" "$SRC"
    # OpenSCAD orders facets nondeterministically: identical geometry, different bytes every run.
    # Canonicalise so git can tell a real change from a rebuild. (CadQuery needs no such fix.)
    python3 "$(dirname "$(readlink -f "$0")")/c14n_stl.py" "$OUT/$b.stl" >/dev/null
    echo "built $OUT/$b.stl" ;;
  *.py)   PY=${CADQUERY_PY:-$HOME/cadquery-env/bin/python}
    _here=$(dirname "$(readlink -f "$0")")
    _partdir=$(dirname "$(dirname "$(readlink -f "$SRC")")")
    if [ -f "$_partdir/spec.yaml" ] && python3 - "$_partdir/spec.yaml" <<'PY'
import sys, yaml
spec = yaml.safe_load(open(sys.argv[1])) or {}
raise SystemExit(0 if 'build' in spec else 1)
PY
    then
        "$PY" "$_here/build_provenance.py" run "$SRC" "$OUT"
        exit $?
    fi
    # Historical non-declared generators remain buildable, but cannot obtain a new handoff
    # without declaring build.source/dependencies and rebuilding through the producer above.
    _mark=$(mktemp)
    "$PY" "$SRC"
    # CadQuery's STL export is byte-deterministic; its STEP export stamps the wall clock into the
    # ISO-10303-21 header, so an unchanged part would look modified on every rebuild. Neutralise it.
    find "$_partdir" "$PWD" -maxdepth 3 -name '*.step' -newer "$_mark" -print0 2>/dev/null \
        | xargs -0 -r python3 "$_here/c14n_step.py" >/dev/null
    find "$_partdir" "$PWD" -maxdepth 3 -name '*.stl' -newer "$_mark" -print0 2>/dev/null \
        | xargs -0 -r python3 "$_here/c14n_stl.py" >/dev/null
    rm -f "$_mark"
    echo "ran $SRC (CadQuery export)" ;;
  *) echo "unknown source type: $SRC" >&2; exit 2 ;;
esac
