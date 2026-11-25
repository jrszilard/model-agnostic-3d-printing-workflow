#!/usr/bin/env bash
# decision-drawing.sh — labelled orthographic drawings, so a human can POINT instead of describe.
#
# WHY
# `docs/workflow.md` has required a decision drawing since 2026-08-21, for approvals that turn on
# named edges, faces, handedness or a datum. But `plan-drawing.py`'s annotations were HAND-AUTHORED
# — you supplied the text and the coordinate — which means you had to already know which feature
# mattered before you could label it. That is backwards: the reason to look at the drawing is to
# work out which area needs revising.
#
# So this derives the labels from the B-rep. Every notable face gets a short id (F07), its surface
# type (flat / round / taper / curve) and its size. Review then reads "F12 is too shallow" instead
# of "the curved bit near the top on the left, no not that one" — which is the ambiguity the
# workflow already says to kill with a drawing, and the dominant published failure mode in
# text-to-CAD (Pro-CAD, arXiv:2602.03045).
#
# Usage: decision-drawing.sh <part_dir> [outdir]     default outdir: <part_dir>/preview
#   Needs a STEP (a mesh has no faces, only triangles) and an STL (what gets drawn).
set -euo pipefail
HERE=$(dirname "$(readlink -f "$0")")
PART=${1:?usage: decision-drawing.sh <part_dir> [outdir]}
OUT=${2:-$PART/preview}
FREECADCMD=${FREECADCMD:-$(command -v freecadcmd || echo freecadcmd)}

pick(){ # first non-coupon, non-underscore file of an extension
    local dir=$1 ext=$2
    [ -d "$dir" ] || return 1
    find "$dir" -maxdepth 1 -name "*$ext" ! -name '_*' ! -name '*coupon*' \
        | sort | head -1 | grep . || return 1
}

STEP=$(pick "$PART/step" .step) || {
    echo "no STEP in $PART/step — a decision drawing needs real faces, not a mesh." >&2
    echo "  OpenSCAD-only parts cannot produce one; label them by hand with plan-drawing.py." >&2
    exit 3; }
STL=$(pick "$PART/stl" .stl) || { echo "no STL in $PART/stl" >&2; exit 3; }
mkdir -p "$OUT"

# Canonicalise ONCE, here, before anything hashes the file. plan-drawing.py used to do this itself,
# once per view, and T1.7 removed it because c14n_stl.py:48-51 rewrites in place and non-atomically
# while five OpenSCAD processes read the same bytes. render.sh took over the hoist; this script is
# plan-drawing.py's OTHER live caller and had no such hoist, so on a freshly exported STL -- the
# normal input, since parts are exported by running the generator directly (bench.sh:63-68) -- the
# three <stem>_<view>_labelled.stamp files recorded the RAW sha256 where geom_id, plate_geom.txt and
# render.sh's own stamp all carry the canonical one. Measured: geom=c96902e8 against 433799de, and
# the STL left non-canonical on disk afterwards. handoff.sh:213 reads exactly that stamp, so it is
# the second identity convention stamp.sh:11-13 exists to prevent, arriving silently.
python3 "$HERE/../generate/c14n_stl.py" "$STL" >/dev/null 2>&1 || :

stem=$(basename "${STEP%.step}")

# One freecadcmd for all three views: reading and cataloguing the STEP does not depend on the view,
# so the per-view loop re-read and re-tessellated the same file three times to compute a
# comprehension over rows already in memory.
STEP="$STEP" LABEL_VIEW=top,front,side LABEL_OUT="$OUT" LABEL_MAX="${LABEL_MAX:-14}" \
    "$FREECADCMD" "$HERE/label-map.py" 2>/dev/null \
    | tr '\r' '\n' | grep -E '^labelled|^  F' | sed 's/^/  /'

for view in top front side; do
    python3 "$HERE/plan-drawing.py" "$STL" "$OUT/${stem}_${view}_labelled.png" \
        --view "$view" --title "$stem — $view · faces labelled from the STEP" \
        --annotations "$OUT/${stem}_${view}.labels.json" | sed 's/^/  /'
done

echo
echo "Point at a label, not a description:  \"F07 is too shallow\""
echo "  id -> geometry:  $OUT/${stem}.labelmap.json"
