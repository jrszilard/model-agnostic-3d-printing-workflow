#!/usr/bin/env bash
# slice.sh — headless PrusaSlicer -> arranged Core One gcode, with real slicer features.
# Options are applied by writing an override .ini and passing it via --load, which MERGES on
# top of the named profiles (unlike OrcaSlicer, no full-preset copy is needed).
#
# Usage: slice.sh [options] <outdir> <part.stl>...
#   --support[=normal|tree]   enable supports (normal=grid, tree=organic). Applies a
#                             removal-friendly interface by default -- see SUP_EASY below.
#   --support-angle <deg>     overhang threshold angle. Applies to grid, snug AND organic -- on
#                             2.9.6 / COREONE, one part, organic + buildplate-only measured
#                             25deg->6.4%, 40deg->10.8%, 55deg->11.3% of extrusion (2026-09-17).
#                             This line used to say organic ignored it entirely; that was wrong
#                             and got repeated into a handoff as fact. Re-measure before editing.
#   --on-build-plate-only     supports only from the build plate
#   --brim <mm>               brim width (0 => no brim)
#   --infill <pct>            sparse infill density (e.g. 20 or 20%)
#   --rotate-x/-y/-z <deg>    rotation before slicing (native; no STL pre-bake needed)
#   --process <name>          print profile   (default: 0.20mm SPEED @COREONE HF0.4)
#   --machine <name>          printer profile (default: Prusa CORE One HF0.4 nozzle)
#   --filament <name>         material profile (default: Prusament PLA @COREONE HF0.4, or $FIL)
#   --spec <path>             spec.yaml or part dir; records support/orientation policy
#   --post <script>           post-slice gcode hook, repeatable; runs before final hash/verification
#   --set key=value           arbitrary config override, PrusaSlicer .ini key (repeatable)
set -euo pipefail
HERE=$(dirname "$(readlink -f "$0")")
PS=${PRUSA_SLICER:-prusa-slicer}
# THE FITTED NOZZLE IS HF0.4 AND ALWAYS HAS BEEN (Justin, 2026-09-21: "the nozzle has never been
# swapped ... I only bought the regular .4 and .6 as a backup"). These defaults were wrong, not the
# hardware: until now slice.sh selected `Prusa CORE One 0.4 nozzle`, so every plate this pipeline
# built carried the standard nozzle's recipe — PETG at 240 C and a 12 mm3/s cap where the HF preset
# says 250 and 21. Conservative rather than dangerous, and those plates printed fine, but it is the
# wrong recipe and it left speed on the table.
#
# The three names must agree on high flow or PrusaSlicer refuses the whole run: a `@COREONE 0.4`
# print or filament preset declares `! nozzle_high_flow[0]` and pairing it with the HF printer
# profile exits 1 with NO G-code ("... is not compatible with printer profile ..."). That is the
# safe direction. The silent one: `*STRUCTURAL*` presets and this project's TPU presets carry no
# high-flow clause at all, so they slice on either nozzle while their speeds and flow caps were
# qualified on one of them. A self-consistent all-standard triple also slices perfectly and emits
# `M862.1 ... F0`; the printer does NOT refuse that (four F0 plates have printed here), so send.sh
# only reports it. Change these together with PRUSALINK_NOZZLE in prusalink.env.
MACHINE_SEL="Prusa CORE One HF0.4 nozzle"
PROCESS_SEL="0.20mm SPEED @COREONE HF0.4"
FIL_SEL="${FIL:-Prusament PLA @COREONE HF0.4}"
OVR=(); ROTX=0; ROTY=0; ROTZ=0; OUT=""; STLS=(); POSTS=(); SPEC=""; SUPPORT_REQUESTED=0

# REMOVAL-FRIENDLY SUPPORT INTERFACE, applied by every --support flag below.
#
# The stock profile's interface is nearly SOLID (interface_spacing 0.2) with 3 interface layers
# and 80% XY spacing. Prusa's own support article: "set to 0 to get a solid interface", a denser
# interface "complicates removal", and "bigger XY separation ... makes them easier to remove and
# less prone to fusing to the model". Sliced on the LED risers those defaults produced supports
# welded hard enough to be the same complaint the cleat tabs drew (2026-08-11).
#
# These are DEFAULTS, not a policy: a later --set on the same key wins, because the .ini writer
# below dedupes last-occurrence-wins. It did NOT always: PrusaSlicer rejects the whole file on a
# repeated key ("duplicate key name" -> no G-code at all), so `--support=normal --set
# support_material_style=snug` used to silently produce nothing. Keep the dedupe if you touch it.
#
# They live here rather than in a doc because this shop has repeatedly found that a rule written
# down does not get applied — see R8, the handoff gate, and the active-job guard in send.sh.
SUP_EASY=("support_material_interface_layers=2"
          "support_material_bottom_interface_layers=0"
          "support_material_interface_spacing=0.6"
          "support_material_xy_spacing=120%"
          "support_material_with_sheath=0")

# TREE BASE STURDINESS — organic only, because a tree stands on a stem and a stem that lifts
# takes its branch and the overhang with it. Grid walls are already self-bracing.
#
# PHYSICAL RESULT (Justin, 2026-09-17, 12gaplusone v12, ASA on COREONE HF0.4): organic supports
# with the first support layer expanded to 7 mm printed BEST of every strategy tried that day and
# released cleanly. SNUG at the same loose interface printed acceptably but its columns were HARD
# TO REMOVE. PrusaSlicer ships 3 mm. Despite the name, `raft_first_layer_expansion` with
# raft_layers=0 expands the first SUPPORT layer — the footprint each stem stands on.
#
# ONE part, ONE material, ONE printer. A starting value, not a qualified sample: no passed/* tag,
# no coupon. Re-check before carrying it to another material or a much taller part, where a wider
# stem base costs bed area.
TREE_BASE=("raft_first_layer_expansion=7")

# COLOUR REGIONS: `--colour <region.stl>=<n>` (repeatable, n = 2, 3 ...) prints the one model given
# in filament 1 except where a region overlaps it, which prints in filament n — on the SAME layer,
# so a road line can sit flush in the road (printed face-down). The Core One has one nozzle: every
# change is a manual M600, with a purge line + wipe after it. colour_plate.py says how and why;
# the regions are bound in slice_meta.json like a post hook, so a regenerated one is a stale plate.
COLOURS=(); COLOUR_NAMES=""      # --colour-names black,white,yellow: one per filament, for the M117
while [ $# -gt 0 ]; do case "$1" in
  --support)             SUPPORT_REQUESTED=1; OVR+=("support_material=1" "support_material_auto=1" "support_material_style=grid" "${SUP_EASY[@]}");;
  --support=normal)      SUPPORT_REQUESTED=1; OVR+=("support_material=1" "support_material_auto=1" "support_material_style=grid" "${SUP_EASY[@]}");;
  --support=tree)        SUPPORT_REQUESTED=1; OVR+=("support_material=1" "support_material_auto=1" "support_material_style=organic" "${SUP_EASY[@]}" "${TREE_BASE[@]}");;
  --support-angle)       shift; OVR+=("support_material_threshold=$1");;
  --on-build-plate-only) OVR+=("support_material_buildplate_only=1");;
  --brim)                shift; OVR+=("brim_width=$1"); [ "$1" = "0" ] && OVR+=("brim_type=no_brim") || OVR+=("brim_type=outer_only");;
  --infill)              shift; OVR+=("fill_density=${1%\%}%");;
  --orient)              echo "note: PrusaSlicer has no CLI auto-orient; use --rotate-x/-y/-z" >&2;;
  --rotate-x)            shift; ROTX="$1";; --rotate-y) shift; ROTY="$1";; --rotate-z) shift; ROTZ="$1";;
  --process)             shift; PROCESS_SEL="$1";; --machine) shift; MACHINE_SEL="$1";; --filament) shift; FIL_SEL="$1";;
  --spec)                shift; SPEC="$1";;
  --post)                shift; POSTS+=("$1");;
  --set)                 shift; OVR+=("$1");;
  --colour)              shift; COLOURS+=("$1");;
  --colour-names)        shift; COLOUR_NAMES="$1";;
  -*)                    echo "unknown option: $1" >&2; exit 2;;
  *)                     if [ -z "$OUT" ]; then OUT="$1"; else STLS+=("$1"); fi;;
esac; shift; done
[ -n "$OUT" ] && [ ${#STLS[@]} -gt 0 ] || { echo "usage: slice.sh [opts] <outdir> <stl>..." >&2; exit 2; }
mkdir -p "$OUT"
python3 "$HERE/../plate_scope.py" check "$OUT" || exit 18

# A re-slice invalidates every prior approval and verification. Remove stale success artifacts
# BEFORE invoking the slicer so a failed run cannot pass over yesterday's gcode/handoff.
rm -f "$OUT/plate_1.gcode" "$OUT/plate.3mf" "$OUT/slice_exit.txt" \
      "$OUT/verify_slice.txt" "$OUT/handoff.txt" "$OUT/qualification_manifest.json" \
      "$OUT/gcode_manifest.json" "$OUT/slice_meta.json" "$OUT/plate_geom.txt" \
      "$OUT/supports.png"
SPEC_PATH=""
if [ -n "$SPEC" ]; then
    [ -d "$SPEC" ] && SPEC="$SPEC/spec.yaml"
    [ -f "$SPEC" ] || { echo "no such spec: $SPEC" >&2; exit 2; }
    SPEC_PATH=$(readlink -f "$SPEC")
fi

if [ ${#COLOURS[@]} -gt 0 ]; then
    [ ${#STLS[@]} -eq 1 ] || { echo "--colour needs exactly one model (the body); got ${#STLS[@]}" >&2; exit 2; }
    _regs=(); for _c in "${COLOURS[@]}"; do _regs+=(--region "$_c"); done
    # Canonical bytes before anything hashes them, the same as the body below.
    python3 "$HERE/../generate/c14n_stl.py" "${COLOURS[@]%=*}" >/dev/null 2>&1 || :
    _cov=$(python3 "$HERE/colour_plate.py" overrides --machine "$MACHINE_SEL" "${_regs[@]}" \
        --names "$COLOUR_NAMES") || exit 2
    while IFS= read -r _kv; do OVR+=("$_kv"); done <<< "$_cov"
    POSTS+=("$HERE/hooks/colour_swaps.py")
    "$PS" --printer-profile "$MACHINE_SEL" --print-profile "$PROCESS_SEL" \
        --material-profile "$FIL_SEL" --save "$OUT/.printer.ini" >/dev/null 2>&1 || :
    _centre=$(python3 "$HERE/colour_plate.py" centre --config "$OUT/.printer.ini") || exit 2
fi

# The flatpak is sandboxed to $HOME — /tmp is invisible to it, so the override .ini must live
# beside the output (a mktemp in /tmp silently reads as an empty/missing config).
OVR_INI="$OUT/.overrides.ini"
# ASCII gcode, not the Core One's default binary .bgcode: the whole verify/preview chain
# (gcode_check.py, plot-supports.py, thumbnails.py) is a line parser. The printer accepts both.
: > "$OVR_INI"
echo "binary_gcode = 0" >> "$OVR_INI"
# LAST VALUE WINS, and it has to be enforced here rather than left to the reader: PrusaSlicer
# rejects the WHOLE file on a repeated key ("duplicate key name" -> no G-code, no slice), so
# `--support=tree --set support_material_style=snug` used to produce nothing at all. Dedupe
# keeping the last occurrence, which is what every caller already assumed happened.
_seen_keys=""
_deduped=()
for (( _i=${#OVR[@]}-1 ; _i>=0 ; _i-- )); do
    _k=${OVR[_i]%%=*}
    case " $_seen_keys " in *" $_k "*) continue ;; esac
    _seen_keys="$_seen_keys $_k"
    _deduped=("${OVR[_i]}" "${_deduped[@]+${_deduped[@]}}")
done
OVR=(${_deduped[@]+"${_deduped[@]}"})
for kv in ${OVR[@]+"${OVR[@]}"}; do echo "${kv%%=*} = ${kv#*=}" >> "$OVR_INI"; done

# ONE canonicalisation for the whole plate, HERE, before arrange.py and either slicer reads a
# byte. It used to happen in the geom loop at the very end: geom_id and geom_sha each run
# canon_stl (stamp.sh:23-24), so a 9-part plate paid 18 c14n_stl.py launches -- 541 ms measured on
# the balloon-lamp clip set -- and paid them AFTER the gcode was already cut. c14n_stl.py:48-51
# rewrites in place, so on a freshly exported STL the plate was sliced from one set of bytes and
# stamped with the sha256 of another: the drift stamp.sh:11-13 exists to prevent. A fresh export
# is the normal input, not a corner case -- bench.sh:66-70 canonicalises at the COMMIT gate
# precisely because every part README documents running the exporter directly. c14n_stl.py's
# __main__ already takes a list, so all of them cost one process (541 -> 108 ms with the batched
# sha256sum below, plate_geom.txt byte-identical on canonical and non-canonical input alike).
# UNIQUES, not rows. A plate is how this shop prints multiples, so the same STL is passed N times:
# 54 of the 110 plate_geom.txt in build/ repeat a path, six of them 20 rows of one file.
# c14n_stl.py re-parses every argument it is given, so the raw list canonicalises one file 20 times
# -- 355 ms against 32 ms measured on 20 copies of the 220 KB clip-throat, i.e. the whole saving
# this hoist exists for, handed straight back. Pure bash on purpose: the six real 20-up plates in
# build/ repeat a 3.5 KB strip, where the dedup is only worth 21 -> 15 ms, and a `sort -zu` fork
# costs 2.4 ms against this loop's 1.0 -- a quarter of the win, to reorder the arguments.
declare -A _seen=(); _c14n=()
for _s in "${STLS[@]}"; do
    case "$_s" in *.stl) ;; *) continue;; esac                              # canon_stl's own guard
    [ -n "${_seen["$_s"]-}" ] || { _seen["$_s"]=1; _c14n+=("$_s"); }
done
[ ${#_c14n[@]} -eq 0 ] || python3 "$HERE/../generate/c14n_stl.py" "${_c14n[@]}" >/dev/null 2>&1 || :

# Multi-part plates must be merged BEFORE the slicer sees them. PrusaSlicer's CLI runs its action
# once per input file, each overwriting --output, so N STLs silently yield only the last one
# (exit 0, no warning); --merge, the documented fix, segfaults. See arrange.py.
SLICE_IN=("${STLS[@]}")
if [ ${#STLS[@]} -gt 1 ]; then
    python3 "$HERE/arrange.py" --out "$OUT/plate.stl" "${STLS[@]}" || exit 1
    SLICE_IN=("$OUT/plate.stl")
fi

THUMB_IN=("${SLICE_IN[@]}")
if [ ${#COLOURS[@]} -gt 0 ]; then
    python3 "$HERE/colour_plate.py" build --out "$OUT/colour_plate.3mf" --base "${STLS[0]}" \
        "${_regs[@]}" || exit 1
    SLICE_IN=("$OUT/colour_plate.3mf")
fi

# Record what was ASKED for, so the handoff can prove the plate holds every part (see arrange.py:
# PrusaSlicer silently slices only the last of several inputs, and weight is the sole symptom).
printf '%s\n' "${STLS[@]}" > "$OUT/plate_parts.txt"

echo "machine:  $MACHINE_SEL"
echo "process:  $PROCESS_SEL$([ ${#OVR[@]} -gt 0 ] && echo "  + overrides: ${OVR[*]}")"
echo "filament: $FIL_SEL"
ARGS=(--printer-profile "$MACHINE_SEL" --print-profile "$PROCESS_SEL" --material-profile "$FIL_SEL" --load "$OVR_INI")
[ ${#COLOURS[@]} -gt 0 ] && ARGS+=(--center "$_centre")
[ "$ROTX" != 0 ] && ARGS+=(--rotate-x "$ROTX")
[ "$ROTY" != 0 ] && ARGS+=(--rotate-y "$ROTY")
[ "$ROTZ" != 0 ] && ARGS+=(--rotate "$ROTZ")

# The .3mf export is started FIRST and left running. It reads the same merged STL and the same
# override .ini as the gcode export and writes a different file, so the two slicer runs overlap
# instead of queueing: measured on the LED riser, 4,311-4,562 ms sequential -> 2,782-2,882 ms for
# the pair, 4,696-4,899 -> 3,106-3,258 ms for the whole script. It also runs through thumbnails,
# postprocess and slice_meta below, but NOT through the geom stamp loop -- see wait_3mf's call site.
#
# The two exit codes must stay APART, which is why this is a background job and not a second
# action on one invocation. A failed .3mf has always been non-fatal here — it is the review
# convenience, not the shipped bytes — whereas slice_exit.txt is what verify-slice.sh:28-36
# hard-fails on. One collapsed status would fail a perfectly good plate.
_3mflog="$OUT/.prusa_3mf.log"
"$PS" "${ARGS[@]}" --export-3mf --output "$OUT/plate.3mf" "${SLICE_IN[@]}" \
    > "$_3mflog" &                                                              # 2) GUI project
_3mfpid=$!
_3mfreaped=0
# Only its STDOUT is held back and replayed in one block: two slicers sharing a terminal would
# otherwise give a different transcript on every run. stderr stays live and uncaptured, because
# that is the stream a failed export talks on -- on 2.9.6 a bad profile prints "Printer profile
# ... wasn't found" and an unwritable target "File export to <p> failed", both on stderr, while a
# successful export writes 0 bytes there. Folding it into stdout would move the one message that
# matters onto the stream the sequential version never sent it on.
wait_3mf() {
    [ "$_3mfreaped" = 0 ] || return 0
    _3mfreaped=1
    local rc=0
    wait "$_3mfpid" || rc=$?
    cat "$_3mflog" 2>/dev/null || :
    [ "$rc" = 0 ] || echo "note: .3mf export skipped (exit $rc) — gcode is fine"
}
# The steps between here and that call are unguarded under `set -e` (the slice_meta heredoc, the
# stamp.sh source), so without this trap an abort would return while a slicer was still writing
# plate.3mf: measured, slice.sh returns in 131 ms with plate.3mf MISSING and the file appears 3 s
# later. handoff.sh:147-149 sizes that file for review.
trap wait_3mf EXIT

_slog="$OUT/.prusa_slice.log"
if "$PS" "${ARGS[@]}" --export-gcode --output "$OUT/plate_1.gcode" "${SLICE_IN[@]}" 2>&1 | tee "$_slog"; then
    echo 0 > "$OUT/slice_exit.txt"
else
    echo "${PIPESTATUS[0]:--1}" > "$OUT/slice_exit.txt"
fi                                                                              # 1) gcode

# 3) thumbnails. Like Orca's, PrusaSlicer's CLI runs headless with no GL context and silently
# skips the thumbnail render the Core One preset asks for, so PrusaLink shows a blank tile.
# Advisory: a missing openscad must never fail an otherwise-good slice.
if [ -f "$OUT/plate_1.gcode" ]; then
    python3 "$HERE/thumbnails.py" --gcode "$OUT/plate_1.gcode" "${THUMB_IN[@]}" \
        || echo "note: thumbnail embedding skipped (exit $?) — gcode is fine, preview will be blank"
fi

# 4) recorded post-slice hooks. These run on the final thumbnail-bearing gcode, then bind its
# sha256 into gcode_manifest.json. verify-slice, handoff and send all refuse if bytes move later.
POST_RC=0
python3 "$HERE/postprocess.py" --gcode "$OUT/plate_1.gcode" \
    --manifest "$OUT/gcode_manifest.json" ${POSTS[@]+"${POSTS[@]}"} || POST_RC=$?

# The .3mf slicer is reaped HERE rather than after the loop below. It used to have to be: the loop
# ran canon_stl, and c14n_stl.py:48-51 rewrites a non-canonical STL IN PLACE and non-atomically
# (open(path,'wb'), no temp+rename) -- on a single-part plate that is the very file the background
# slicer is reading. Canonicalisation now happens before either slicer starts, so that hazard is
# gone, and the position is kept only because the overlap it would buy is worth 0 ms, not "little":
# --export-3mf skips slicing and takes 1,593-1,604 ms against --export-gcode's 2,897-2,966 ms on
# the same riser, so it is always reaped before the tail starts anyway.
wait_3mf                                                                        # 2) collected

# Machine-readable print-process identity. This binds the named profiles, explicit overrides,
# rotation, post-hook bytes, final G-code, 3MF (when its advisory export succeeded), and the exact
# effective configuration PrusaSlicer embedded in the G-code. It says WHICH process produced the
# plate, never that the process is suitable. verify-slice and handoff fail if the record is absent,
# malformed, or stale.
_META=(write --meta "$OUT/slice_meta.json" --gcode "$OUT/plate_1.gcode"
       --project "$OUT/plate.3mf" --overrides "$OVR_INI" --slicer "$PS"
       --machine "$MACHINE_SEL" --process "$PROCESS_SEL" --filament "$FIL_SEL"
       --rotate-x "$ROTX" --rotate-y "$ROTY" --rotate-z "$ROTZ")
[ "$SUPPORT_REQUESTED" = 1 ] && _META+=(--support-requested)
[ -n "$SPEC_PATH" ] && _META+=(--spec "$SPEC_PATH")
for _kv in "${OVR[@]}"; do _META+=(--override "$_kv"); done
for _hook in "${POSTS[@]}"; do _META+=(--post-hook "$_hook"); done
for _c in "${COLOURS[@]}"; do _META+=(--colour-region "$_c"); done
python3 "$HERE/slice_identity.py" "${_META[@]}" || exit 1

# Geometry identity is recorded only after the final gcode exists. handoff.sh re-hashes these
# sources and also checks gcode_manifest.json, so preview, plate and shipped bytes form one chain.
. "$HERE/../stamp.sh"
: > "$OUT/plate_geom.txt"
# One sha256sum for the whole plate, replacing the two forks per row geom_id + geom_sha cost. The
# hashes are read into a path-keyed map rather than paired by array index, because sha256sum SKIPS
# a file it cannot read: paired by index, one missing STL would hand every later row its
# neighbour's hash. A missing or unreadable file leaves both columns empty here, which is what
# geom_id/geom_sha's own `sha256sum 2>/dev/null | cut` already produced.
declare -A _plate_sha=()
while IFS= read -r _line; do _plate_sha["${_line#*  }"]=${_line%% *}; done \
    < <(sha256sum "${STLS[@]}" 2>/dev/null)
for _s in "${STLS[@]}"; do
    _h=${_plate_sha["$_s"]-}
    printf '%s  %s  %s\n' "${_h:0:8}" "$_h" "$(readlink -f "$_s")" >> "$OUT/plate_geom.txt"
done
echo "version=$(version_line)" >> "$OUT/plate_geom.txt"

echo "gcode -> $OUT/plate_1.gcode   |   PrusaSlicer project -> $OUT/plate.3mf"
[ "$POST_RC" = 0 ] || { echo "post-slice hook/manifest failed; see $OUT/gcode_manifest.json" >&2; exit "$POST_RC"; }
