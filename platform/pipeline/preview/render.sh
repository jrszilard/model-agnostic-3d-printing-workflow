#!/usr/bin/env bash
# render.sh — render the REAL exported STL to review views or a model-input view pack.
# Usage: render.sh [--profile review-5|zero-to-cad-8] <part.stl> <outdir>
set -euo pipefail
# shellcheck source=../stamp.sh
. "$(dirname "$(readlink -f "$0")")/../stamp.sh"
PROFILE=review-5
if [ "${1:-}" = --profile ]; then PROFILE=${2:?--profile needs a value}; shift 2; fi
case "$PROFILE" in review-5|zero-to-cad-8) ;; *) echo "unknown render profile: $PROFILE" >&2; exit 2;; esac
STL=${1:?stl}; OUT=${2:?outdir}; mkdir -p "$OUT"
OSC=${OPENSCAD:-openscad}

# ONE canonicalisation per render, here, before anything reads the STL. It used to happen six
# times and all six ran too LATE: geom_id and geom_sha each run canon_stl (stamp.sh:23-24),
# write_stamp calls both, :106 calls geom_id again, and plan-drawing.py redid it once per view
# -- so the five views below were rendered from the PRE-canonical bytes the stamp at :105 then
# says they depict. c14n_stl.py:48-51 rewrites its input IN PLACE and non-atomically
# (open(path,'wb'), no temp+rename): polling a 3.5 MB STL through that rewrite catches it at
# 0 bytes on every run, so any reader that overlaps it -- a sibling drawing, or these five
# OpenSCAD views once they are parallelised -- hashes or renders a truncated file. A freshly
# exported STL is the normal input here (bench.sh:66-70 canonicalises at the COMMIT gate exactly
# because every part README documents running the exporter directly), so it is not hypothetical.
canon_stl "$STL" || :   # non-fatal as before: the old calls sat inside $( ), where set -e stops
                        # at the subshell and the render carried on regardless
canon_stl(){ :; }       # canonical for the rest of the run. write_stamp still hashes the file
                        # itself, so identity still travels with the bytes (stamp.sh:11-13) --
                        # only the re-normalisation of bytes it cannot change is dropped.
b=$(basename "${STL%.stl}")
tmp=$(mktemp --suffix=.scad)
trap 'rm -f "$tmp"' EXIT
printf 'import("%s");\n' "$(readlink -f "$STL")" > "$tmp"

if [ "$PROFILE" = zero-to-cad-8 ]; then
    # Zero-to-CAD publishes the model-facing contract as eight 256px renders: four upper/front
    # quadrants and four lower/rear quadrants. It does not publish exact camera matrices. This
    # versioned local profile therefore pins the observed convention (45-degree azimuth, 90-degree
    # steps; +55/-55 degree elevation) without claiming pixel identity with private training code.
    # Keep the order stable: image_0..3 upper, image_4..7 lower.
    # Eight independent renders; same per-PID discipline as the review-5 set below. The manifest
    # step that follows already refuses a missing or zero-byte view, so a failed render cannot
    # reach the JSON -- but collect the statuses anyway so the diagnosis names the render, not the
    # manifest.
    _angles=(45 135 225 315)
    _index=0
    _z2c_pids=()
    for _tilt in 55 125; do
        for _azimuth in "${_angles[@]}"; do
            "$OSC" -o "$OUT/${b}_image_${_index}.png" --imgsize=256,256 --viewall --autocenter \
                --camera="0,0,0,$_tilt,0,$_azimuth,0" --colorscheme=Tomorrow "$tmp" &
            _z2c_pids+=("$!")
            _index=$((_index + 1))
        done
    done
    _z2c_rc=0
    for _p in "${_z2c_pids[@]}"; do wait "$_p" || _z2c_rc=1; done
    [ "$_z2c_rc" = 0 ] || { echo "render.sh: a zero-to-cad view failed to render" >&2; exit 1; }
    python3 - "$STL" "$OUT" "$b" <<'PY'
import hashlib, json, os, sys
stl, out, stem = sys.argv[1:]
angles = [(55, a) for a in (45, 135, 225, 315)] + [(125, a) for a in (45, 135, 225, 315)]
def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
views = []
for index, (tilt, azimuth) in enumerate(angles):
    path = os.path.join(out, "%s_image_%d.png" % (stem, index))
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise SystemExit("renderer did not produce a non-empty view: " + path)
    views.append({
        "index": index, "path": os.path.basename(path), "sha256": digest(path),
        "camera": {"rotation_x_deg": tilt, "rotation_z_deg": azimuth},
        "hemisphere": "upper-front" if index < 4 else "lower-rear",
    })
manifest = {
    "schema": 1,
    "profile": "zero-to-cad-8-v1",
    "source_stl": {"path": os.path.realpath(stl), "sha256": digest(stl)},
    "image_size": [256, 256],
    "views": views,
    "compatibility": {
        "dataset": "ADSKAILab/Zero-To-CAD-1m",
        "dataset_revision": "09dbd1805a5e73a2757f380b93042b8089cd4f3f",
        "published_contract": "four front-facing plus four rear-facing 256x256 renders",
        "exact_upstream_camera_matrices_published": False,
    },
    "authority": "model input only; no dimensional, fit, or fabrication approval",
}
with open(os.path.join(out, stem + ".zero-to-cad-8.json"), "w", encoding="utf-8") as stream:
    json.dump(manifest, stream, indent=2, sort_keys=True)
PY
    rm -f "$tmp"; trap - EXIT
    echo "rendered $OUT/${b}_image_{0..7}.png (zero-to-cad-8-v1)   [geom $(geom_id "$STL")]"
    exit 0
fi

# FIVE views, not three. iso/top/front cannot show a back face, and on 2026-08-11 that cost a
# print: LFB2's debossed label was mirrored and read backwards (commit 7a9f08c) -- a defect that
# lives entirely on the surface no camera was pointed at. The two added angles are the ones
# agentcad settled on for agent self-review: an orthographic BACK (catches mirrored lettering) and
# a second ISO from the opposite quadrant (catches geometry hiding behind the near face).
# Camera is translate_xyz, rot_xyz, dist -- rot_z + 180 is the opposite side.
# The five are independent OpenSCAD processes reading one .scad, and 93% of each is fixed
# process+GL startup, so serially they cost 687 ms to do ~50 ms of drawing. Safe to overlap only
# because the canonicalisation above now happens ONCE and BEFORE them: while plan-drawing.py still
# rewrote the STL in place per view, five concurrent readers of that file was a race, not a saving.
#
# Each PID is waited INDIVIDUALLY. A bare `wait` returns the status of the last job only, and under
# `set -e` the serial version aborted before write_stamp on a failed view -- with a bare wait the
# script would sail on and stamp a preview set that is missing an image, which handoff.sh:186-192
# then accepts on the stamp's geom= alone because it never opens the PNGs.
render_view(){ "$OSC" -o "$OUT/${b}_$1.png" --imgsize=800,600 --viewall --autocenter \
                     --camera="0,0,0,$2,0,$3,0" --colorscheme=Tomorrow "$tmp"; }
_view_pids=()
render_view iso       55  25  & _view_pids+=("$!")   # front-right
render_view iso_back  55  205 & _view_pids+=("$!")   # back-left  (25 + 180)
render_view top        0   0  & _view_pids+=("$!")
render_view front     90   0  & _view_pids+=("$!")
render_view back      90 180  & _view_pids+=("$!")
_view_rc=0
for _p in "${_view_pids[@]}"; do wait "$_p" || _view_rc=1; done
rm -f "$tmp"; trap - EXIT
if [ "$_view_rc" != 0 ]; then
    echo "render.sh: a view failed to render — refusing to stamp an incomplete preview set" >&2
    exit 1
fi
# Stamp: these PNGs depict THESE bytes. handoff.sh refuses if the plate was sliced from others.
write_stamp "$OUT/${b}.stamp" "$STL" "views=${b}_iso.png ${b}_iso_back.png ${b}_top.png ${b}_front.png ${b}_back.png"
echo "rendered $OUT/${b}_{iso,iso_back,top,front,back}.png   [geom $(geom_id "$STL")]"

# --- labelled decision drawings, automatically ----------------------------------------------------
# A bare render can only be discussed in prose: "the front left face, slightly above the peg".
# That sentence is a guess the next revision acts on, and resolving it is the dominant published
# failure mode in text-to-CAD. A labelled drawing turns it into "F16", which is not ambiguous.
#
# Generated HERE, not by a separate command, because a separate command does not get run. Every
# preview now carries its labelled counterpart, so presenting geometry for a design decision never
# requires remembering an extra step.
#
# Best-effort by design: it needs a STEP (a mesh has no faces) and freecadcmd. An OpenSCAD-only
# part or a missing kernel skips it with a note and does NOT fail the render.
_step=$(dirname "$(readlink -f "$STL")")/../step/$b.step
if [ -f "$_step" ] && command -v "${FREECADCMD:-freecadcmd}" >/dev/null 2>&1; then
    _here=$(dirname "$(readlink -f "$0")")
    # ONE freecadcmd for all three views. Reading and cataloguing the STEP does not depend on the
    # view -- only annotations_for_view does, and it is a comprehension over rows already in memory
    # -- so the old per-view loop re-read and re-tessellated the same STEP three times and rewrote
    # the identical labelmap.json three times.
    if STEP="$_step" LABEL_VIEW=top,front,side LABEL_OUT="$OUT" LABEL_MAX="${LABEL_MAX:-14}" \
           "${FREECADCMD:-freecadcmd}" "$_here/label-map.py" >/dev/null 2>&1; then
        # plan-drawing.py imports matplotlib+pyplot+numpy at module scope: ~505 ms of import to do
        # ~338 ms of drawing, three times over. Forking the three is safe only after the
        # canonicalisation hoist above -- plan-drawing.py used to rewrite the STL in place per view,
        # and three children racing on one non-atomic truncate+write is how a drawing came to record
        # the sha256 of a half-written file.
        _draw_pids=()
        for _view in top front side; do
            python3 "$_here/plan-drawing.py" "$STL" "$OUT/${b}_${_view}_labelled.png" \
                --view "$_view" --title "$b — $_view · faces labelled from the STEP" \
                --annotations "$OUT/${b}_${_view}.labels.json" >/dev/null 2>&1 &
            _draw_pids+=("$!")
        done
        # Best-effort, exactly as before: a drawing that fails is reported by its absence below,
        # never by failing the render. The five review views are the required artifact.
        for _p in "${_draw_pids[@]}"; do wait "$_p" || :; done
    fi
    if [ -f "$OUT/${b}.labelmap.json" ]; then
        echo "labelled  $OUT/${b}_{top,front,side}_labelled.png   ids -> $OUT/${b}.labelmap.json"
        echo "          present THESE for a design decision — a reply of \"F16\" needs no interpreting"
    fi
else
    echo "no labelled drawing: $( [ -f "$_step" ] || echo "no STEP beside the STL" )$( command -v "${FREECADCMD:-freecadcmd}" >/dev/null 2>&1 || echo "freecadcmd not found" )"
fi
