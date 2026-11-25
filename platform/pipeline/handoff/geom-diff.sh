#!/usr/bin/env bash
# geom-diff.sh — what changed between this geometry and the last version that PASSED.
#
# WHY
# The geom id proves every artefact in a handoff came from one version. It says nothing about how
# that version differs from the one you already printed and approved -- and that is the question a
# human actually has at the gate: "what did we change since the part that worked?" Renders answer it
# badly; a 9.4 mm misalignment looks right from every camera. Five scalars catch what the eye does
# not: a moved centroid, a grown bbox, volume changing while the bbox does not (hollowed or filled),
# or a facet jump with everything else equal (re-tessellated, not redesigned).
#
# The baseline is the newest passed/* tag holding this path -- i.e. the last state that cleared a
# PHYSICAL gate, not merely the previous commit. Comparing against a version that was never proven
# tells you nothing about whether a change is a regression.
#
# Usage: geom-diff.sh <current.stl> <outdir> [baseline-ref]
# Exit: 0 diffed · 1 no baseline (not an error -- a new part has nothing to compare against)
set -uo pipefail
HERE=$(dirname "$(readlink -f "$0")")
CUR=${1:?usage: geom-diff.sh <current.stl> <outdir> [baseline-ref]}
OUT=${2:?outdir}; REF=${3:-}
mkdir -p "$OUT"
ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 1
REL=$(realpath --relative-to="$ROOT" "$CUR" 2>/dev/null)
b=$(basename "${CUR%.stl}")

git -C "$ROOT" ls-files --error-unmatch "$REL" >/dev/null 2>&1 || {
    echo "no baseline: $REL is not tracked (regenerable geometry has no committed history)"; exit 1; }

if [ -z "$REF" ]; then
    for t in $(git -C "$ROOT" for-each-ref --sort=-creatordate --format='%(refname:short)' refs/tags/passed); do
        git -C "$ROOT" cat-file -e "$t:$REL" 2>/dev/null && { REF=$t; break; }
    done
fi
[ -n "$REF" ] || { echo "no baseline: no passed/* tag contains $REL yet"; exit 1; }

base=$(mktemp --suffix=.stl)
git -C "$ROOT" show "$REF:$REL" > "$base" 2>/dev/null || { rm -f "$base"; echo "no baseline: cannot read $REF:$REL"; exit 1; }

{
  echo "=== GEOMETRY DIFF: $REL ==="
  echo "baseline: $REF   (the last version that cleared a physical gate)"
  echo "current : $(sha256sum "$CUR" | cut -c1-8)"
  echo
  GEOM_METRICS="$HERE/geom_metrics.py" python3 - "$base" "$CUR" <<'PY'
import json, subprocess, sys, os
# Passed in from the shell: this block runs from stdin, so __file__ is "<stdin>" and any path
# derived from it resolves against the CWD instead of the script's directory.
mod = os.environ['GEOM_METRICS']
def m(p): return json.loads(subprocess.check_output(['python3', mod, p]).splitlines()[0])
a, b = m(sys.argv[1]), m(sys.argv[2])
def row(label, x, y, unit='', tol=0.0005):
    d = y - x
    flag = '' if abs(d) <= tol else '   <-- CHANGED'
    print(f"  {label:<14} {x:>14,.3f} -> {y:>14,.3f}   {d:+12.3f} {unit}{flag}")
print(f"  {'metric':<14} {'baseline':>14} {'current':>14}   {'delta':>12}")
row('facets', a['facets'], b['facets'], '', 0)
row('volume', a['volume_mm3'], b['volume_mm3'], 'mm3', 0.001)
row('surface area', a['area_mm2'], b['area_mm2'], 'mm2', 0.001)
for i, ax in enumerate('xyz'):
    row(f'size {ax}', a['size'][i], b['size'][i], 'mm')
for i, ax in enumerate('xyz'):
    row(f'centroid {ax}', a['centroid'][i], b['centroid'][i], 'mm')
# Position matters. A pure translation leaves facets, volume, area and size untouched -- the very
# error this tool exists to catch -- so bbox and centroid have to be part of the identity test.
same = (a['facets'] == b['facets']
        and abs(a['volume_mm3'] - b['volume_mm3']) < 0.001
        and a['size'] == b['size']
        and a['bbox_min'] == b['bbox_min'] and a['bbox_max'] == b['bbox_max']
        and a['centroid'] == b['centroid'])
moved = (a['size'] == b['size'] and a['facets'] == b['facets']
         and abs(a['volume_mm3'] - b['volume_mm3']) < 0.001
         and (a['bbox_min'] != b['bbox_min'] or a['centroid'] != b['centroid']))
print()
if same:
    print("  IDENTICAL geometry.")
elif moved:
    d = [round(b['centroid'][i] - a['centroid'][i], 4) for i in range(3)]
    print(f"  MOVED, not reshaped: same solid, translated by {d} mm.")
    print("  This is the class of error renders cannot show -- every camera looks correct.")
else:
    print("  Read the deltas above against what you INTENDED to change.")
PY
} | tee "$OUT/diff_${b}.txt"

# Side-by-side at the same camera, so the eye has something to check the numbers against.
"$HERE/../preview/render.sh" "$base" "$OUT/.diffbase" >/dev/null 2>&1
for v in iso front; do
    [ -f "$OUT/.diffbase/$(basename "${base%.stl}")_$v.png" ] && \
        mv "$OUT/.diffbase/$(basename "${base%.stl}")_$v.png" "$OUT/diff_${b}_was_$v.png"
done
rm -rf "$OUT/.diffbase" "$base"
echo
echo "  baseline renders: $OUT/diff_${b}_was_{iso,front}.png"
echo "  report:           $OUT/diff_${b}.txt"
