#!/usr/bin/env bash
# verify-slice.sh — deterministic machine gate before handoff/send.
# Usage: verify-slice.sh [--spec <spec.yaml|part_dir>] <outdir> [<stl>...]
# Mesh/DFM geometry heuristics WARN. Bbox, slicer/postprocess, final-gcode, support intent/keepout
# and artifact-identity failures BLOCK.
set -uo pipefail
HERE=$(dirname "$(readlink -f "$0")")
. "$HERE/../gates.sh"
FREECADCMD=${FREECADCMD:-$(command -v freecadcmd || echo freecadcmd)}
SPEC=""; OUT=""; STLS=()
while [ $# -gt 0 ]; do case "$1" in
    --spec) shift; SPEC=${1:?--spec needs a path};;
    -*) echo "unknown option: $1" >&2; exit 2;;
    *) if [ -z "$OUT" ]; then OUT="$1"; else STLS+=("$1"); fi;;
esac; shift; done
[ -n "$OUT" ] || { echo "usage: verify-slice.sh [--spec path] <outdir> [stl...]" >&2; exit 2; }

hard=0
# Structured trace beside the human report — see gates.sh:_gate_record. Per-stage filename so this
# and handoff.sh never truncate each other's; an agent globs gates.*.jsonl for the whole plate.
GATE_RESULTS="$OUT/gates.verify-slice.jsonl"; export GATE_RESULTS
: > "$GATE_RESULTS" 2>/dev/null || GATE_RESULTS=""
echo "=== verify-slice: $OUT ==="

# 1) mesh pre-check per STL (geometry heuristics print WARN; only MESH_RESULT: FAIL is hard).
# T1.6: this launched a fresh FreeCAD per argument, and FreeCAD's ~80 ms start dwarfs the ~8 ms
# check. Resolve the arguments, check each distinct file once inside ONE freecadcmd, and report per
# argument exactly as before. Dedup is not hypothetical: 54 of the 110 plate_geom.txt files in
# build/ repeat a row — 20 plates at 6 rows over 1 STL, 14 at 10, six at 20.
# Batched, NOT parallel: xargs -P4 measured 782 ms against 556 ms serial on this box, a 40%
# regression, and -P7 was 5.7x slower. Batching wins by 4x and has no tuning constant.
MESH_GREP='bbox|WARN|HARD|MESH_RESULT'
# Bed fit is judged on the part as the slicer turns it: pass the rotation slice.sh recorded. No
# slice_meta.json means no rotation was recorded (legacy): measure unturned, as before. A meta that
# exists but cannot be read passes a value mesh_check.py refuses, rather than "unturned".
rotenv=()
if [ -f "$OUT/slice_meta.json" ]; then
    rot=$(python3 -c 'import json, sys
r = json.load(open(sys.argv[1])).get("rotation") or {}
print(" ".join(str(float(r.get(k, 0))) for k in "xyz"))' "$OUT/slice_meta.json" 2>/dev/null) || rot=unreadable
    rotenv=(MESH_ROT="$rot")
fi
mesh_one() {   # the pre-T1.6 path, kept as the fallback below
    # env -u: an exported MESH_LIST in the caller's environment flipped this single-file call into
    # batch mode and reported a passing STL as empty, i.e. hard=1 on good geometry. The fallback
    # must be the pre-T1.6 call, environment included.
    env -u MESH_LIST -u MESH_ROT MESH="$1" ${rotenv[@]+"${rotenv[@]}"} "$FREECADCMD" "$HERE/mesh_check.py" 2>&1 \
        | tr '\r' '\n' | grep -E "$MESH_GREP"
}
mkeys=(); muniq=(); declare -A mslot=() mblk=() mend=()
for stl in ${STLS[@]+"${STLS[@]}"}; do
    k=$(readlink -f "$stl")          # may be empty when a parent dir is missing; "k$k" keeps the
    mkeys+=("$k")                    # subscript non-empty, which bash requires
    [ -n "${mslot[k$k]+set}" ] || { mslot[k$k]=${#muniq[@]}; muniq+=("$k"); }
done
mbatch=1; mlist=""
for k in ${muniq[@]+"${muniq[@]}"}; do
    case $k in *$'\n'*) mbatch=0;; esac   # MESH_LIST is newline-framed; such a path must not batch
    mlist+=$k$'\n'
done
mlist=${mlist%$'\n'}
if [ "$mbatch" -eq 1 ] && [ ${#muniq[@]} -gt 0 ]; then
    while IFS=$'\t' read -r i kind line; do
        case $kind in END) mend[$i]=1;; L) mblk[$i]+=$line$'\n';; esac
    done < <(env -u MESH_ROT MESH_LIST="$mlist" ${rotenv[@]+"${rotenv[@]}"} "$FREECADCMD" "$HERE/mesh_check.py" 2>&1 | tr '\r' '\n' \
        | awk -v pat="$MESH_GREP" '
            /^MESH_ITEM_BEGIN /{ i=$2; f=1; next }
            /^MESH_ITEM_END /  { if (f) print $2 "\tEND"; f=0; next }
            f && $0 ~ pat      { print i "\tL\t" $0 }')
fi
i=0
for k in ${muniq[@]+"${muniq[@]}"}; do
    # No END marker means the batch process died before reaching this file (or never started).
    # A FreeCAD abort on one mesh must not silently drop the meshes queued behind it, so re-run it
    # the old way rather than report it as clean.
    [ -n "${mend[$i]+set}" ] || { mblk[$i]=$(mesh_one "$k")$'\n'; mend[$i]=1; }
    i=$((i+1))
done
i=0
for stl in ${STLS[@]+"${STLS[@]}"}; do
    r=${mblk[${mslot[k${mkeys[$i]}]}]-}; r=${r%$'\n'}; i=$((i+1))
    echo "mesh $(basename "$stl"): $(echo "$r" | tr '\n' ' ')"
    gate_allows MESH_RESULT "$r" || hard=1
done

# 2) slicer exit code.
code=$(cat "$OUT/slice_exit.txt" 2>/dev/null || echo "")
if [ -n "$code" ]; then
    v=$(python3 -c "import sys;sys.path.insert(0,'$HERE');from orca_exit import classify_exit;r=classify_exit(int('$code'));print(r['severity'],r['name'],r['message'])")
    echo "slicer exit $code -> $v"
    echo "$v" | grep -q '^hard' && hard=1
else
    echo "slicer exit: MISSING slice_exit.txt"
    hard=1
fi

# 3) final gcode identity + every post-slice hook. New slices always write this manifest;
# legacy plates may still be inspected, but re-slicing is required before a stamped handoff.
if [ -f "$OUT/gcode_manifest.json" ]; then
    p=$(python3 "$HERE/../slice/postprocess.py" --check --gcode "$OUT/plate_1.gcode" \
        --manifest "$OUT/gcode_manifest.json" 2>&1)
    echo "postprocess:"; echo "$p" | sed 's/^/  /'
    gate_allows POSTPROCESS_RESULT "$p" || hard=1
else
    echo "postprocess: MISSING gcode_manifest.json — future plates must record every hook result"
    hard=1
fi

# 4) exact slicer/profile/configuration identity. This is factual provenance, not an assertion
# that the selected process is suitable. Legacy slices must be re-sliced before a future plate can
# reach handoff; otherwise profile names and effective settings remain unknowable.
if [ -f "$OUT/slice_meta.json" ]; then
    si=$(python3 "$HERE/../slice/slice_identity.py" check \
        --meta "$OUT/slice_meta.json" --gcode "$OUT/plate_1.gcode" \
        --project "$OUT/plate.3mf" --overrides "$OUT/.overrides.ini" 2>&1)
    echo "slice identity:"; echo "$si" | sed 's/^/  /'
    gate_allows SLICE_IDENTITY_RESULT "$si" || hard=1
else
    echo "slice identity: MISSING slice_meta.json — re-slice to record the effective process"
    hard=1
fi

# 5) basic printability of the exact final gcode.
if [ -f "$OUT/plate_1.gcode" ]; then
    g=$(python3 -c "import sys;sys.path.insert(0,'$HERE');from gcode_check import parse_gcode,check_gcode;r=check_gcode(parse_gcode('$OUT/plate_1.gcode'));print('PASS' if r['passed'] else 'FAIL'); [print('  [HARD]',h) for h in r['hard']]")
    echo "gcode: $(echo "$g" | head -1)"; echo "$g" | grep '\[HARD\]'
    echo "$g" | head -1 | grep -q PASS || hard=1
else
    echo "gcode: MISSING plate_1.gcode"; hard=1
fi

# 6) support intent and numeric support keep-outs. A requested support set with zero extrusion is
# a deterministic contradiction, not "0% looks good". Keep-outs come from --spec or slice_meta.
if [ -f "$OUT/plate_1.gcode" ]; then
    sargs=("$OUT/plate_1.gcode")
    [ -f "$OUT/slice_meta.json" ] && sargs+=(--meta "$OUT/slice_meta.json")
    [ -n "$SPEC" ] && sargs+=(--spec "$SPEC")
    s=$(python3 "$HERE/support_check.py" "${sargs[@]}" 2>&1)
    echo "support:"; echo "$s" | sed 's/^/  /'
    gate_allows SUPPORT_RESULT "$s" || hard=1
fi

res=$([ "$hard" -eq 0 ] && echo PASS || echo FAIL)
echo "$res" > "$OUT/verify_slice.txt"
if [ "$hard" -ne 0 ]; then
    # A changed/failed plate cannot retain yesterday's human approval token.
    rm -f "$OUT/handoff.txt"
fi
echo "=== verify-slice: $res ==="
[ "$hard" -eq 0 ]
