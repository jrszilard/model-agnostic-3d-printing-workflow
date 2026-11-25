#!/usr/bin/env bash
# handoff.sh — the REQUIRED review step between verify-slice and send.
#
# WHY THIS IS A SCRIPT AND NOT A CONVENTION
# `docs/workflow.md` has always required presenting the review artifacts (paths, not a summary)
# before anything reaches the printer. On 2026-07-20 that was skipped anyway: a plate was uploaded
# "just to stage it" before the preview was shown. Staging is not harmless — a staged plate is one
# screen tap from printing, and the whole point of the gate is that a human sees the geometry
# first. A rule that lives only in prose gets rationalised away; this one refuses to proceed.
#
# Usage: handoff.sh <outdir> [part_dir]      exit 0 = artifacts complete, 1 = incomplete
#   Part dirs are DERIVED from the plate; [part_dir] only adds one. Exits: 1 missing artifacts ·
#   10 geometry-version mismatch · 12 spec truth / primary / fit-core / probe declarations ·
#   13 a part on the plate has no spec (NO_SPEC_OK=1 bypasses 13 only, and the bypass is recorded) ·
#   14 no recorded B-rep verdict for the plate's geometry, or a release plate carrying declared
#      measurement debt (no bypass — run verify.sh; a prototype plate MAY cross DEBT) ·
#   15 future design/status qualification is incomplete · 16 qualification manifest could not bind ·
#   17 deterministic verify-slice verdict is not PASS · 18 scope hold · 19 missing/mismatched inventory (no bypass).
#   Verifies every review artifact exists, prints them WITH PATHS, and writes <outdir>/handoff.txt,
#   which send.sh requires. It deliberately does NOT approve anything — approval is the human's.
set -uo pipefail
. "$(dirname "$(readlink -f "$0")")/../stamp.sh"
. "$(dirname "$(readlink -f "$0")")/../gates.sh"
_stamp_version_line(){ :; }; eval "_stamp_version_line() $(declare -f version_line | tail -n +2)"
OUT=${1:?usage: handoff.sh <outdir> [part_dir]}
[ -d "$OUT" ] || { echo "no such outdir: $OUT" >&2; exit 2; }
# Stop before truncating a trace or invalidating the handoff we are preserving for review.
_scope=$(python3 "$(dirname "$(readlink -f "$0")")/../plate_scope.py" check "$OUT") || exit 18
printf '%s\n' "$_scope"
# Structured trace of every gate this run consults, beside the human report. Per-stage filename so
# handoff and verify-slice never truncate each other's; an agent globs gates.*.jsonl to see the
# whole plate without parsing a line of prose. Truncated here so a rerun replaces its own record.
GATE_RESULTS="$OUT/gates.handoff.jsonl"; export GATE_RESULTS; : > "$GATE_RESULTS" 2>/dev/null || true

# --- local, cheaper forms of three stamp.sh helpers (T2.11) --------------------------------------
# stamp.sh is sourced by render.sh and slice.sh as well, and stamp.sh:16-19 is a written warning
# about the drift that follows from editing it, so these are LOCAL redefinitions and nothing else
# sees them.
#
# geom_sha: hash only, and ONE batched canonicalisation up front covers every model on the plate.
#
# Dropping the canonicalisation outright was wrong, and it turned a correct plate into a refusal.
# plate_geom.txt records the CANONICAL sha (slice.sh:109 canonicalises the whole set before it
# slices). Re-running a generator between slice and handoff -- the flow every part README documents,
# and the reason bench.sh canonicalises at the commit gate -- leaves a file whose GEOMETRY is
# unchanged but whose bytes are not canonical. stamp.sh's geom_sha canonicalised, matched, and
# passed; a raw hash reports "*** GEOMETRY MOVED SINCE THE SLICE *** the gcode is stale" and refuses
# at exit 10. A false refusal on good geometry is how a gate gets bypassed on reflex.
#
# So: canonicalise once, for the whole plate, in one process (the fork-per-row this was avoiding),
# then hash raw.
geom_sha(){ sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }

# stamp_get: pure bash. It was a `sed | head` pipeline -- two forks -- called once per preview, per
# plate row and per part. The `|| [ -n "$_l" ]` is not optional: `read` returns false on a final
# line with no trailing newline, and without it the last key in a stamp is silently unreadable.
stamp_get(){
    [ -f "$1" ] || return 0
    local _l
    while IFS= read -r _l || [ -n "$_l" ]; do
        case "$_l" in "$2="*) printf '%s\n' "${_l#"$2="}"; return 0;; esac
    done < "$1"
}

# version_line: memoised, and LAZILY. An eager memo taken at the top would be wrong -- c14n can
# rewrite a tracked STL mid-run and flip the repo to +dirty -- and this line is printed into
# handoff.txt, which send.sh and the human both read as the provenance of the approval.
_VERSION_LINE_MEMO=""
version_line(){
    [ -n "$_VERSION_LINE_MEMO" ] || _VERSION_LINE_MEMO=$(_stamp_version_line)
    printf '%s\n' "$_VERSION_LINE_MEMO"
}

PART=${2:-}
# A new presentation invalidates yesterday's machine/human bridge before any gate runs. Never leave
# a stale complete handoff or qualification manifest beside a failed rerun.
rm -f "$OUT/handoff.txt" "$OUT/qualification_manifest.json"
gate_allows PLATE_SCOPE_RESULT "$_scope" || { echo 'Scope check not recognized by gate registry.' >&2; exit 18; }

miss=0
mism=0
policy=0
qualification=0
slice_gate=0
nospec=0
have(){ [ -f "$1" ]; }

# --- which part directories is this plate actually made of? --------------------------------------
# The part dir used to be an OPTIONAL second argument. A plate handed off without it skipped the
# spec-truth and fit-core gates completely and still wrote handoff.txt, so the strongest checks in
# the chain were opt-in via a positional parameter — and the venture's only physically fitted part
# went through the weak form. Derive the set instead: every model slice.sh recorded, walked up to
# the nearest ancestor holding a spec.yaml. $2 is still honoured and is added to the set.
#
# Scope of the REFUSAL is deliberate. A model under parts/ is an authored part and must have a
# spec. A model that lives in build/ is a slicing artefact — support blockers, arrangement 3mfs —
# and has no part dir by design; those are reported unchecked, never refused, because making them
# refuse would mean typing the bypass on every run of a validation loop, which is how a migration
# hatch becomes the default.
spec_ancestor(){
    # Every failure mode here has to be a hard `return 1`. The first version wrote
    #   d=$(dirname "$(readlink -f "$1")") || return 1
    # which cannot fail: on an unresolvable path `readlink -f` prints nothing, `dirname ""` prints
    # "." and exits 0, so the `||` never fired, `dirname .` is "." forever, and handoff.sh HUNG —
    # reproduced at 100% against the venture's own wiper-adaptors-all3-v2 plate. Worse, when it did
    # not hang it tested `./spec.yaml`, i.e. whatever part directory the operator happened to be
    # standing in, and reported SPEC TRUTH for a part that was not on the plate.
    local rp d prev
    rp=$(readlink -f "$1") || return 1
    [ -n "$rp" ] || return 1
    case "$rp" in /*) : ;; *) return 1;; esac      # only ever walk an absolute path
    d=$(dirname "$rp")
    while [ -n "$d" ] && [ "$d" != "/" ]; do
        [ -f "$d/spec.yaml" ] && { printf '%s\n' "$d"; return 0; }
        [ -e "$d/.git" ] && break                  # -e, not -d: a worktree's .git is a FILE
        prev=$d; d=$(dirname "$d")
        [ "$d" = "$prev" ] && break                # belt and braces: never loop on a fixed point
    done
    return 1
}

# Relative model paths are resolved against the PLATE'S repository, not the shell's cwd. Older
# venture plates record repo-relative entries; resolving those against $PWD fabricates a path in
# whatever repo the operator is standing in, which then refuses at exit 13 naming a file that does
# not exist — an unactionable refusal that teaches people to type the bypass.
PLATE_BASE=$(git -C "$OUT" rev-parse --show-toplevel 2>/dev/null) || PLATE_BASE=""
[ -n "$PLATE_BASE" ] || PLATE_BASE=$(dirname "$(readlink -f "$OUT")")
abs_model(){ case "$1" in /*) printf '%s\n' "$1";; *) printf '%s\n' "$PLATE_BASE/$1";; esac; }

# Newline-separated, not space-separated: a part directory containing a space would otherwise
# word-split into two nonexistent paths and refuse at exit 12 with no way past it.
SPEC_PARTS=""
UNCHECKED=""
MODEL_COUNT=0
# Which PART each model on the plate came from. verify.sh records a verdict per part; a plate is a
# set of models, often several from one part. Keeping the association is what lets exit 14 name the
# model that is missing from its part's verdict instead of just the part.
# TAB-separated because SPEC_PARTS is already newline-separated for the same reason: a part
# directory containing a space used to word-split into two nonexistent paths (see add_part).
BREP_ROWS=""
add_part(){
    local existing
    while IFS= read -r existing; do
        [ "$existing" = "$1" ] && return
    done <<EOF
$SPEC_PARTS
EOF
    SPEC_PARTS="${SPEC_PARTS}${SPEC_PARTS:+
}$1"
}
if [ -f "$OUT/plate_geom.txt" ]; then
    while read -r _g _sha _p; do
        case "$_g" in version=*|"") continue;; esac
        [ -n "$_p" ] || continue
        MODEL_COUNT=$((MODEL_COUNT + 1))
        _p=$(abs_model "$_p")
        if _pd=$(spec_ancestor "$_p"); then
            add_part "$_pd"
            BREP_ROWS="${BREP_ROWS}${BREP_ROWS:+
}$(printf '%s\t%s\t%s' "$_g" "$_pd" "${_p#"$_pd"/}")"
        elif printf '%s' "$_p" | grep -q '/parts/'; then
            echo "*** NO SPEC: $_p is under parts/ but no ancestor holds a spec.yaml" >&2
            nospec=1
        else
            UNCHECKED="${UNCHECKED}${UNCHECKED:+
}$(basename "$_p")"
        fi
    done < "$OUT/plate_geom.txt"
fi
if [ -n "$PART" ] && [ -f "$PART/spec.yaml" ]; then add_part "$(readlink -f "$PART")"; fi

# --- one canonicalisation for the whole plate, before any identity is compared -------------------
# See the geom_sha note at the top. Every model plate_geom.txt names, canonicalised in ONE
# c14n_stl.py process rather than a fork per row, so the raw hashes below are comparing canonical
# bytes to the canonical shas slice.sh recorded. c14n_stl.py rewrites only when the bytes change, so
# on the normal path (nothing re-exported since the slice) this reads every file and writes none.
if [ -f "$OUT/plate_geom.txt" ]; then
    _cn=()
    while read -r _g _sha _p; do
        case "$_g" in version=*|"") continue;; esac
        [ -n "$_p" ] || continue
        _p=$(abs_model "$_p")
        case "$_p" in */releases/*|*/vendor/*) continue;; esac   # same rule as verify.sh
        [ -f "$_p" ] && _cn+=("$_p")
    done < "$OUT/plate_geom.txt"
    if [ ${#_cn[@]} -gt 0 ]; then
        _seen_c=""; _uniq_c=()
        for _f in "${_cn[@]}"; do
            case " $_seen_c " in *" $_f "*) continue;; esac
            _seen_c="$_seen_c $_f"; _uniq_c+=("$_f")
        done
        python3 "$(dirname "$(readlink -f "$0")")/../generate/c14n_stl.py" \
            "${_uniq_c[@]}" >/dev/null 2>&1 || :
    fi
fi

# --- geometry identity of this plate (written by slice.sh) --------------------------------------
PLATE_GEOMS=""
if [ -f "$OUT/plate_geom.txt" ]; then
    while read -r g sha path; do
        case "$g" in version=*|"") continue;; esac
        PLATE_GEOMS="$PLATE_GEOMS $g"
        path=$(abs_model "$path")      # same base as the derivation above, never $PWD
        if [ -f "$path" ]; then
            now=$(geom_sha "$path")
            if [ "$now" != "$sha" ]; then
                echo "*** GEOMETRY MOVED SINCE THE SLICE: $path" >&2
                echo "      sliced $g, on disk now $(echo "$now" | cut -c1-8) — the gcode is stale." >&2
                mism=1
            fi
        else
            # Fails OPEN if we skip it: this is the half of the gate that catches "regenerated
            # after slicing", so an unresolvable path must block rather than quietly check nothing.
            echo "*** CANNOT VERIFY: $path (recorded by slice.sh) is not readable from here." >&2
            echo "      re-slice, or run handoff.sh from the directory slice.sh ran in." >&2
            mism=1
        fi
    done < "$OUT/plate_geom.txt"
    if [ "$MODEL_COUNT" = 0 ]; then
        # A plate_geom.txt holding only `version=` records no geometry, so every identity check
        # below iterates zero times and passes vacuously — the same hole as having no file at all.
        echo "*** PLATE RECORDS NO GEOMETRY: $OUT/plate_geom.txt has no model lines." >&2
        [ "${UNSTAMPED_OK:-0}" = 1 ] || mism=1
    fi
else
    # An unstamped PLATE has to block for the same reason an unstamped preview does: with no geom
    # id recorded, nothing can be checked against it, and the gate would quietly pass everything.
    # Blocking only the previews would leave "delete plate_geom.txt" as a working bypass.
    echo "*** PLATE NOT STAMPED: no $OUT/plate_geom.txt — re-slice to record its geometry." >&2
    [ "${UNSTAMPED_OK:-0}" = 1 ] || mism=1
fi
geom_on_plate(){ case " $PLATE_GEOMS " in *" $1 "*) return 0;; *) return 1;; esac; }
row(){ printf "  %-58s %s\n" "$1" "$2"; }

echo "=== HANDOFF: $OUT ==="
echo
echo "Review artifacts (open these before approving):"

for f in "$OUT/plate.3mf" "$OUT/plate_1.gcode" "$OUT/supports.png" "$OUT/verify_slice.txt"; do
    if have "$f"; then row "$f" "$(du -h "$f" | cut -f1)"
    else row "$f" "*** MISSING ***"; miss=1; fi
done

# Bind review and upload to the final gcode bytes and every post-slice hook result. A legacy plate
# selected for a future handoff must be re-sliced; current bytes alone cannot prove hooks succeeded.
GCODE_SHA=""
if have "$OUT/plate_1.gcode"; then
    GCODE_SHA=$(sha256sum "$OUT/plate_1.gcode" | awk '{print $1}')
    if have "$OUT/gcode_manifest.json"; then
        _pp=$(python3 "$(dirname "$(readlink -f "$0")")/../slice/postprocess.py" --check \
            --gcode "$OUT/plate_1.gcode" --manifest "$OUT/gcode_manifest.json" 2>&1)
        if gate_allows POSTPROCESS_RESULT "$_pp"; then
            row "$OUT/gcode_manifest.json" "post hooks/final gcode [sha ${GCODE_SHA:0:12}] OK"
        else
            row "$OUT/gcode_manifest.json" "*** FINAL GCODE IDENTITY FAILED ***"
            echo "$_pp" | sed 's/^/      /' >&2
            mism=1
        fi
    else
        row "$OUT/gcode_manifest.json" "*** MISSING — re-slice to bind hook results/final bytes ***"
        mism=1
    fi
fi
if [ -n "$PART" ]; then
    shopt -s nullglob
    pv=("$PART"/preview/*.png)
    shopt -u nullglob
    if [ ${#pv[@]} -gt 0 ]; then
        # Drive this from the PLATE, not from the directory. A part dir holds previews for every
        # component (pegboard-canister-holder has four) plus hero shots and mockups that render.sh
        # never made; checking all of them against a one-component plate refuses every honest
        # handoff and trains you to run with UNSTAMPED_OK=1, disabling the real check.
        # What must hold: each part ON THIS PLATE has a preview depicting THIS geometry.
        if [ -n "$PLATE_GEOMS" ]; then
            while read -r pg psha ppath; do
                case "$pg" in version=*|"") continue;; esac
                pb=$(basename "$ppath"); pb=${pb%.stl}
                pst="$PART/preview/$pb.stamp"
                sg=$(stamp_get "$pst" geom)
                if [ -z "$sg" ]; then
                    row "$PART/preview/${pb}_{iso,top,front}.png" "*** NO STAMPED PREVIEW for plate part $pb ***"
                    [ "${UNSTAMPED_OK:-0}" = 1 ] || mism=1
                elif [ "$sg" = "$pg" ]; then
                    for v in iso top front; do
                        [ -f "$PART/preview/${pb}_$v.png" ] && row "$PART/preview/${pb}_$v.png" "preview [geom $sg] OK"
                    done
                else
                    row "$PART/preview/${pb}_iso.png" "*** STALE: preview is geom $sg, plate is $pg ***"
                    mism=1
                fi
            done < "$OUT/plate_geom.txt"
        fi
        # Everything else in preview/ is context — other components, hero shots, mockups. Shown so
        # it is on the table, never a block: it is not claiming to depict this plate.
        for f in "${pv[@]}"; do
            b=$(basename "$f" .png); b=${b%_iso}; b=${b%_top}; b=${b%_front}
            g=$(stamp_get "$PART/preview/$b.stamp" geom)
            if [ -n "$g" ] && geom_on_plate "$g"; then continue; fi
            row "$f" "context (not on this plate)"
        done
    else
        row "$PART/preview/*.png" "*** MISSING — run preview/render.sh ***"; miss=1
    fi
fi

# Labelled decision drawings. The point of these is the REPLY: approval is a conversation, and
# "F12 is too shallow" is actionable where "the curved bit near the top on the left" is a guess the
# next revision acts on. Presented, never required — an OpenSCAD-only part has no faces to name.
if [ -n "$SPEC_PARTS" ]; then
    echo
    echo "DECISION DRAWINGS (point at a label, do not describe the area)"
    _found_drawing=0
    while IFS= read -r _pd; do
        [ -n "$_pd" ] || continue
        shopt -s nullglob
        _dw=("$_pd"/preview/*_labelled.png)
        _lm=("$_pd"/preview/*.labelmap.json)
        shopt -u nullglob
        for _d in "${_dw[@]}"; do row "$_d" "labelled faces"; _found_drawing=1; done
        for _m in "${_lm[@]}"; do row "$_m" "id -> surface type, area, centroid"; done
        if [ ${#_dw[@]} -eq 0 ] && [ -d "$_pd/step" ] && compgen -G "$_pd/step/*.step" >/dev/null; then
            echo "  none for $(basename "$_pd") — it has a STEP, so it can have them:"
            echo "      platform/pipeline/preview/decision-drawing.sh $_pd"
        fi
    done <<EOF
$SPEC_PARTS
EOF
    [ "$_found_drawing" = 0 ] && echo "  (review will fall back to describing areas in prose)"
fi

# Spec truth is cheap and deterministic: a fit-critical estimated/placeholder nominal may make a
# labelled review form or gauge, but cannot reach a fitting-part handoff. Runs over EVERY part on
# the plate, not just an optionally-named one.
if [ -n "$SPEC_PARTS" ] || [ -n "$UNCHECKED" ] || [ "$nospec" != 0 ]; then
    echo
    echo "SPEC TRUTH"
    _here=$(dirname "$(readlink -f "$0")")
    while IFS= read -r _pd; do
        [ -n "$_pd" ] || continue
        echo "  ── $(basename "$_pd")"
        _pr=$(python3 "$_here/../verify/dim_provenance.py" --require-recorded \
            "$_pd/spec.yaml" 2>&1)
        echo "$_pr" | sed 's/^/    /'
        gate_allows PROVENANCE_RESULT "$_pr" || policy=1
        _fc=$(python3 "$_here/../verify/fitcore_check.py" "$_pd/spec.yaml" 2>&1)
        echo "$_fc" | sed 's/^/    /'
        gate_allows FITCORE_RESULT "$_fc" || policy=1
        # `test.sh` reports this repo-wide, but an ignored legacy export may exist only in an old
        # working tree. At the next plate boundary there is no archive exemption: the primary
        # verify.py resolves must be present and live in a tracked namespace.
        echo "    PRIMARY ARTIFACT — strict at this next plate boundary"
        _pc=$(python3 "$_here/../verify/spec_primary_check.py" "$_pd" 2>&1)
        echo "$_pc" | sed 's/^/    /'
        gate_allows SPEC_PRIMARY_RESULT "$_pc" || policy=1
        # Forward-only boundary: untouched archives are never bulk-migrated. The moment a part is
        # placed on a new plate, however, it must identify Restore vs Originate intent; any claimed
        # non-draft status must link exact current-model physical evidence.
        _qc=$(python3 "$_here/../verify/qualification_check.py" part "$_pd" 2>&1)
        echo "$_qc" | sed 's/^/    /'
        gate_allows QUALIFICATION_RESULT "$_qc" || qualification=1
    done <<EOF
$SPEC_PARTS
EOF
    while IFS= read -r _u; do
        [ -n "$_u" ] || continue
        echo "  [unchecked] $_u — build-local slicing artefact, no part dir by design"
    done <<EOF
$UNCHECKED
EOF
    if [ "$nospec" != 0 ]; then
        echo "  [FAIL] a model under parts/ has no spec.yaml (see above)"
    fi
fi

echo
# --- probe coverage gate (A5): a fit-critical part must declare probes --------------------------
# Probes are the declarations the workflow cannot enforce for you: which exact B-rep checks must
# survive on the final solid. A part with fit-critical geometry and no probes is a part whose
# broken hook can still pass every other gate. Probes are declared in the spec and evaluated on
# the exported STEP by verify.py; this gate requires and statically validates their declarations
# when fit-critical geometry exists, so a malformed placeholder cannot satisfy coverage.
if [ -n "$SPEC_PARTS" ]; then
    while IFS= read -r _pd; do
        [ -n "$_pd" ] || continue
        if _probe_report=$(python3 "$_here/../verify/probe_check.py" --validate-required \
            "$_pd/spec.yaml" 2>&1); then
            echo "$_probe_report" | sed 's/^/  /'
        else
            echo "$_probe_report" | sed 's/^/  /' >&2
            echo "        add or correct the probes: block (see parts/_TEMPLATE/spec.yaml)" >&2
            policy=1
        fi
    done <<EOF
$SPEC_PARTS
EOF
fi

# --- B-rep verdict gate (A1) --------------------------------------------------------------------
# Everything above this line is the SPEC-truth side: provenance, fit core, probe declarations. None
# of it looks at the solid. step_valid / closed / no_bad_faces are proven only by verify.py, which
# nothing automated runs and which — until 2026-09-03 — wrote nothing to disk, so at the plate there
# was no record that the B-rep had ever been checked at all. verify.sh now stamps its verdict beside
# the part; this assembles those verdicts into verify_report.txt and refuses at exit 14 when the
# bytes on this plate are not in one.
#
# Bound to the BYTES, which is the same shape as the stale-preview refusal at exit 10: the verdict
# lists the geom id of every STL the part held when verify ran, and each plated model's geom id has
# to be one of them. Regenerate an STL after verifying and its id moves — which is exactly the
# "verified a different version" case, and the one a verdict without a binding cannot see.
#
# This block deliberately does not duplicate the primary-path check above. That earlier gate
# requires the STEP verify.py resolves to be present and outside an ignored namespace at this new
# plate boundary. Here the recorded SHA is the B-rep evidence and the question is only whether its
# verdict covers every plated STL byte.
#
# Scope matches the spec gates above: a model under build/ is a slicing artefact — support blockers,
# arrangement 3mfs — with no part dir by design, so it is reported unchecked and never refuses.
#
# DEBT is the third verdict (verify.py). It means every answerable check passed and a fit-critical
# nominal is declared unproven, naming the iteration and the date that close it. Refusing it here is
# what deadlocked originated parts: the measurement that would clear the row can only come off a
# printed article, and this gate is what stops the article being printed. So a PROTOTYPE plate may
# cross declared debt and a RELEASE plate may not — the kind comes from the recipe, via
# preparation.json. Absent or unreadable, the strict reading wins: no kind means release.
PLATE_KIND=$(sed -n 's/.*"kind"[[:space:]]*:[[:space:]]*"\([a-z-]*\)".*/\1/p' \
    "$OUT/preparation.json" 2>/dev/null | head -1)
case "$PLATE_KIND" in
    prototype|bench-experiment) DEBT_CROSSABLE=1 ;;
    *) DEBT_CROSSABLE=0 ;;
esac
brep=0
brep_unproven=0
brep_debt=0
BREP_TODO=""
brep_todo(){ BREP_TODO="${BREP_TODO}${BREP_TODO:+
}    $1"; }
{
    echo "=== B-REP VERDICT — $OUT ==="
    echo
    echo "verify.py is the only check that proves step_valid / closed / no_bad_faces on the"
    echo "exported solid. These are the verdicts verify.sh recorded, matched to this plate's bytes."
    echo "A model shown \"in the verdict\" was on disk, byte for byte, when that verdict was taken;"
    echo "the verdict itself is the part's, read off its primary STEP."
    echo
    if [ -z "$BREP_ROWS" ] && [ -z "$UNCHECKED" ]; then
        echo "  (this plate records no model that resolves to a part directory)"
    fi
    while IFS= read -r _pd; do
        [ -n "$_pd" ] || continue
        _vs="$_pd/verify.stamp"
        _vd=$(stamp_get "$_vs" verdict)
        _geoms=""
        _stale=0
        _rowsout=""
        while IFS="$(printf '\t')" read -r _g _rpd _rel; do
            [ -n "$_g" ] || continue
            [ "$_rpd" = "$_pd" ] || continue
            # A plate can name the same STL several times (an arrangement repeats a part); one
            # verdict line per distinct geometry, not per copy.
            case " $_geoms " in *" $_g "*) continue;; esac
            _geoms="$_geoms $_g"
            if [ -n "$_vd" ] && grep -q "^stl=$_g " "$_vs" 2>/dev/null; then
                _mark="in the verdict"
            else
                _mark="*** NOT IN THE VERDICT ***"
                _stale=1
            fi
            _rowsout="${_rowsout}$(printf '    %-8s  %-52s %s' "$_g" "$_rel" "$_mark")
"
        done <<EOF
$BREP_ROWS
EOF
        # Named as $2 but nothing of it is on this plate: there are no bytes here to bind a verdict
        # to, so reporting one would be reporting on a part the human is not approving.
        [ -n "$_geoms" ] || continue
        if [ -z "$_vd" ]; then
            echo "  ── $(basename "$_pd"): *** NO VERDICT — verify.sh has never recorded one here ***"
            brep=1
            brep_todo "platform/pipeline/verify/verify.sh $_pd"
        else
            echo "  ── $(basename "$_pd"): $_vd  ·  STEP $(stamp_get "$_vs" step)  sha $(stamp_get "$_vs" sha256 | cut -c1-12)"
            echo "        recorded by verify.sh at $(stamp_get "$_vs" version)"
            case "$_vd" in
                PASS) ;;
                DEBT)
                    if [ "$DEBT_CROSSABLE" = 1 ]; then
                        brep_debt=1
                        echo "        DECLARED MEASUREMENT DEBT — a fit-critical nominal on this"
                        echo "        part is unproven and says so. This plate is a ${PLATE_KIND},"
                        echo "        which is how the measurement gets taken; it is NOT evidence"
                        echo "        that the number is right, and it releases nothing."
                    else
                        brep=1
                        brep_todo "$_pd — verify.sh said DEBT and this plate is '${PLATE_KIND:-unknown}'. A release cannot carry an unproven fit-critical nominal: close the debt with the measurement, or prepare it as a prototype."
                    fi ;;
                UNPROVEN)
                    brep=1; brep_unproven=1
                    brep_todo "$_pd — exports no STEP; port it to CadQuery, or retire the part" ;;
                *)
                    brep=1
                    brep_todo "$_pd — verify.sh said $_vd; fix the part, then re-run it" ;;
            esac
        fi
        printf '%s' "$_rowsout"
        if [ "$_stale" != 0 ] && [ -n "$_vd" ]; then
            echo "        the geometry moved since that verdict — re-run:"
            echo "        platform/pipeline/verify/verify.sh $_pd"
            brep=1
            brep_todo "platform/pipeline/verify/verify.sh $_pd   (verdict is for other geometry)"
        fi
    done <<EOF
$SPEC_PARTS
EOF
    while IFS= read -r _u; do
        [ -n "$_u" ] || continue
        echo "  [unchecked] $_u — build-local slicing artefact, no part dir by design"
    done <<EOF
$UNCHECKED
EOF
    # Two states in which the loop above iterates zero times and this gate would report PASS having
    # examined nothing — the same vacuous hole handoff.sh already names for the identity check at
    # :136-141, arriving one gate later. Each is reachable with ONE environment variable, and both
    # were measured passing on 2026-09-04 before this block existed: plate_geom.txt removed with
    # UNSTAMPED_OK=1, and a spec-less part under parts/ with NO_SPEC_OK=1, each gave rc=0 and
    # BREP_VERDICT_RESULT: PASS. The usage line at the top of this file says NO_SPEC_OK "bypasses 13
    # only"; without this it also bypassed 14, which is the one gate the plan gives no hatch at all.
    if [ "$MODEL_COUNT" = 0 ]; then
        echo "  [FAIL] this plate records no geometry, so there are no bytes for any verdict to"
        echo "         bind to. Nothing on it has been checked."
        brep=1
        brep_todo "re-slice $OUT — its plate_geom.txt records no model to check a verdict against"
    fi
    if [ "$nospec" != 0 ]; then
        echo "  [FAIL] a model under parts/ has no spec.yaml, so it has no part directory to hold"
        echo "         a verdict either — its solid is unchecked whatever exit 13 is told to do."
        brep=1
        brep_todo "author spec.yaml for the part named NO SPEC above, then run verify.sh on it"
    fi
    echo
    if [ "$brep" = 0 ] && [ "$brep_debt" = 1 ]; then
        echo "BREP_VERDICT_RESULT: DEBT"
        echo
        echo "  This plate is approvable and carries a nominal nobody has measured yet. That is the"
        echo "  point of it — printing it is how the measurement gets taken — but read the debt rows"
        echo "  above before approving, and do not treat the resulting parts as qualified for use."
    else
        echo "BREP_VERDICT_RESULT: $([ "$brep" = 0 ] && echo PASS || echo FAIL)"
    fi
} > "$OUT/verify_report.txt"
echo
cat "$OUT/verify_report.txt"

# Slicer inputs are provenance, NOT a requested or observed piece count (a single STL can hold six).
if have "$OUT/plate_parts.txt"; then
    n=$(grep -cve '^[[:space:]]*$' "$OUT/plate_parts.txt")
    echo "Slicer inputs — $n file row(s); see the per-ID inventory below for actual piece counts:"
    while read -r p; do [ -n "$p" ] && echo "    - $(basename "$p")"; done < "$OUT/plate_parts.txt"
else
    echo "Plate contents: (no plate_parts.txt — re-slice to record it)"
fi

if have "$OUT/plate_1.gcode"; then
    g=$(grep -m1 -E '^; filament used \[g\]' "$OUT/plate_1.gcode" | sed 's/.*= *//')
    t=$(grep -m1 -E '^; estimated printing time \(normal' "$OUT/plate_1.gcode" | sed 's/.*= *//')
    echo
    echo "Plate: ${g:-?} g  ·  ${t:-?}"
    echo "  Weight is a sanity check, not proof of which pieces were sliced."
fi

vs=$(cat "$OUT/verify_slice.txt" 2>/dev/null || echo "MISSING")
echo
echo "verify-slice verdict: $vs"
if [ "$vs" != "PASS" ]; then
    echo "  BLOCK: deterministic slice checks are not overridable at handoff/send."
    slice_gate=1
fi

# --- what changed since the last version that PASSED -------------------------------------------
# Deliberately NOT a block: a diff is the expected outcome of intending a change. It is here so the
# approval decision is made against "what moved since the part that worked", which is the question
# the human actually has, and which renders answer badly.
if [ -n "$PLATE_GEOMS" ]; then
    _dh=0
    while read -r g sha path; do
        case "$g" in version=*|"") continue;; esac
        [ -f "$path" ] || continue
        if out=$("$(dirname "$(readlink -f "$0")")/geom-diff.sh" "$path" "$OUT" 2>/dev/null); then
            [ "$_dh" = 0 ] && { echo; echo "CHANGED SINCE THE LAST PASSED VERSION"; _dh=1; }
            echo "$out" | sed -n '2p;3p' | sed 's/^/  /'
            echo "$out" | grep -E 'CHANGED$|MOVED, not reshaped|IDENTICAL geometry' | sed 's/^ */    /'
            echo "    report: $OUT/diff_$(basename "${path%.stl}").txt"
        fi
    done < "$OUT/plate_geom.txt"
fi

echo
echo "VERSION"
echo "  repo:  $(version_line)"
if [ -n "$PLATE_GEOMS" ]; then
    while read -r g sha path; do
        case "$g" in version=*|"") continue;; esac
        printf "  geom:  %s  %s\n" "$g" "$(basename "$path")"
    done < "$OUT/plate_geom.txt"
else
    echo "  geom:  (none — plate predates geometry stamping; re-slice to record it)"
fi

if [ "$miss" != 0 ]; then
    echo
    echo "=== HANDOFF INCOMPLETE — artifacts missing above. Not writing handoff.txt. ===" >&2
    rm -f "$OUT/handoff.txt"
    exit 1
fi

# A version mismatch is a BLOCK, not a warning. Approving a plate while looking at a preview of
# different geometry is precisely the failure this gate exists to prevent — the human would be
# approving something they have not actually seen.
if [ "$mism" != 0 ]; then
    echo
    echo "=== HANDOFF REFUSED — artifacts are from different geometry versions (above). ===" >&2
    echo "  re-render the previews and/or re-slice so every artifact shares one geom id." >&2
    echo "  (migration only: UNSTAMPED_OK=1 tolerates previews that predate stamping.)" >&2
    rm -f "$OUT/handoff.txt"
    exit 10
fi

if [ "$slice_gate" != 0 ]; then
    echo
    echo "=== HANDOFF REFUSED — deterministic verify-slice verdict is not PASS. ===" >&2
    echo "  Fix and re-slice; FORCE cannot turn a known bad plate into upload authority." >&2
    rm -f "$OUT/handoff.txt" "$OUT/qualification_manifest.json"
    exit 17
fi

if [ "$policy" != 0 ]; then
    echo
    echo "=== HANDOFF REFUSED — unresolved spec truth / primary / fit-core / probe declaration gate. ===" >&2
    echo "  Measure/cite the nominal, fix variant identity/probes," >&2
    echo "  or print a labelled gauge/review form." >&2
    rm -f "$OUT/handoff.txt"
    exit 12
fi

# A part with no spec has no dimensional contract to check, so every truth gate above silently
# passed it by. That is not the same as approval, and it is the state the venture's most-iterated
# structural part shipped eleven plates in. There is NO bypass for exit 12 — a spec that exists and
# fails is a decision — but there is one here, because "author a spec" is real work and this gate
# arrives after the fact.
if [ "$nospec" != 0 ] && [ "${NO_SPEC_OK:-0}" != 1 ]; then
    echo
    echo "=== HANDOFF REFUSED — a part on this plate has no spec.yaml. ===" >&2
    echo "  Its dimensions, provenance and fit-core identity are unchecked; the gates did not run." >&2
    echo "  Author parts/<category>/<part>/spec.yaml (see parts/_TEMPLATE/spec.yaml)," >&2
    echo "  or, for migration only:  NO_SPEC_OK=1 $0 $*" >&2
    rm -f "$OUT/handoff.txt"
    exit 13
fi

# There is NO bypass here, and the repo's own precedent is what decides that. Exit 12 has none
# because a check that exists and fails is a decision; exit 13 has one because authoring a spec is
# real work that this gate arrives after. Running verify.sh is neither — it is one command, and
# after T1.1/T1.2 it is several times cheaper than it was. Justin, 2026-09-03: "those ones that were
# done in the past without a geometric check or verify were errors that got through without
# checking... we don't want to make exceptions for past parts."
if [ "$brep" != 0 ]; then
    echo
    echo "=== HANDOFF REFUSED — this plate's B-rep validity is not on record. ===" >&2
    echo "  verify.py is the only thing that proves step_valid / closed / no_bad_faces, and until" >&2
    echo "  its verdict is recorded AGAINST THESE BYTES, nothing in this chain has checked the" >&2
    echo "  solid the gcode came from. Details: $OUT/verify_report.txt" >&2
    echo "  Do this:" >&2
    printf '%s\n' "$BREP_TODO" >&2
    if [ "$brep_unproven" != 0 ]; then
        echo "  UNPROVEN is not a near-miss: the part exports no STEP, so there is no B-rep to" >&2
        echo "  validate. cable-clip and window-fan-adapter are OpenSCAD-only and radius-gauge has" >&2
        echo "  no parametric source; those three cannot reach a handoff as they stand. Port the" >&2
        echo "  part to CadQuery, or retire it." >&2
    fi
    echo "  There is no bypass variable for this gate." >&2
    rm -f "$OUT/handoff.txt" "$OUT/qualification_manifest.json"
    exit 14
fi

if [ "$qualification" != 0 ]; then
    echo
    echo "=== HANDOFF REFUSED — future design/status qualification is incomplete. ===" >&2
    echo "  This does not rewrite archived evidence. This part is on a new plate now, so add its" >&2
    echo "  design: Restore/Originate intent; if status is not draft, link qualification.current" >&2
    echo "  to a structured record for these exact model bytes. See parts/_TEMPLATE/spec.yaml." >&2
    rm -f "$OUT/handoff.txt" "$OUT/qualification_manifest.json"
    exit 15
fi

# Recompute from the independent request, source meshes, final project and final G-code. A stale
# success report is never a substitute. Check after the older gates to retain their diagnostics.
_inv=$(python3 "$(dirname "$(readlink -f "$0")")/../plate_inventory.py" record "$OUT" 2>&1); _inv_rc=$?
printf '\nREQUESTED vs SLICED (digital, not pieces recovered)\n%s\n' "$_inv"
if ! gate_allows INVENTORY_RESULT "$_inv" || [ "$_inv_rc" != 0 ]; then
    echo "=== HANDOFF REFUSED — missing, mismatched or unproven per-ID inventory; see $OUT/plate-inventory.json ===" >&2
    exit 19
fi
INVENTORY_SHA=$(sha256sum "$OUT/plate-inventory.json" | cut -d' ' -f1)
row "$OUT/plate-inventory.json" "part IDs/quantities and slice bindings [sha ${INVENTORY_SHA:0:12}]"

# Bind the machine-known half of the next physical iteration. No verdict, reading, operator, or
# approval is written here: the manifest is explicitly `not-evaluated`. It gives the eventual human
# record exact source/model/G-code/profile/config bytes instead of asking anyone to reconstruct them
# after the print. Every authored model has already passed all gates above.
_qargs=(manifest --outdir "$OUT")
while IFS= read -r _pd; do [ -n "$_pd" ] && _qargs+=(--part "$_pd"); done <<EOF
$SPEC_PARTS
EOF
_qout=$(python3 "$(dirname "$(readlink -f "$0")")/../verify/qualification_check.py" \
    "${_qargs[@]}" 2>&1)
echo
echo "PHYSICAL ITERATION IDENTITY"
echo "$_qout" | sed 's/^/  /'
if ! gate_allows QUALIFICATION_MANIFEST_RESULT "$_qout"; then
    echo "=== HANDOFF REFUSED — exact qualification manifest could not be written. ===" >&2
    rm -f "$OUT/handoff.txt" "$OUT/qualification_manifest.json"
    exit 16
fi
QUAL_MANIFEST=$(readlink -f "$OUT/qualification_manifest.json")
QUAL_SHA=$(sha256sum "$QUAL_MANIFEST" | awk '{print $1}')
row "$QUAL_MANIFEST" "machine identity only; human evaluation NOT EVALUATED [sha ${QUAL_SHA:0:12}]"
PHYSICAL_SAMPLES=$(python3 - "$QUAL_MANIFEST" <<'PY'
import json, sys
rows = json.load(open(sys.argv[1]))['parts']
counts = [p.get('physical_samples') for p in rows]
print(sum(counts) if counts and all(type(n) is int for n in counts) else 'unresolved for non-primary/build-only models')
PY
)
echo "Physical sample/solid instances (not input-file count): $PHYSICAL_SAMPLES"
echo "Source readiness: selected part + declared dependencies; unrelated repository dirt is not a blocker."

{ echo "handoff presented"; echo "outdir=$OUT"; echo "verify_slice=$vs";
  echo "version=$(version_line)"; echo "geoms=$(echo $PLATE_GEOMS)";
  echo "gcode_sha=$GCODE_SHA"; echo "inventory_sha=$INVENTORY_SHA";
  echo "physical_samples=$PHYSICAL_SAMPLES";
  echo "source_scope=part-and-dependencies";
  echo "qualification_manifest=$QUAL_MANIFEST";
  echo "qualification_manifest_sha=$QUAL_SHA";
  # Which parts the truth gates actually ran on — and, if the gate was bypassed, that it was.
  # A bypass has to survive into the artifact the human reads and send.sh consumes; a bypass
  # visible only in the shell that typed it is not a record of anything.
  while IFS= read -r _sp; do
      [ -n "$_sp" ] || continue
      echo "spec_part=$_sp"
      # The verdict travels into the artifact send.sh reads, for the same reason the NO_SPEC_OK
      # bypass does: a gate result visible only in the shell that ran it is not a record.
      _bv=$(stamp_get "$_sp/verify.stamp" verdict)
      echo "brep_verdict=${_bv:-(none — this part is not on the plate)}  $_sp"
  done <<EOF
$SPEC_PARTS
EOF
  if [ "$nospec" != 0 ]; then echo "no_spec_ok=1"; fi; } > "$OUT/handoff.txt"
echo
echo "=== HANDOFF COMPLETE ==="
echo "Present the paths above to the human. Nothing may be uploaded until they approve;"
echo "then send with:  APPROVED=1 send.sh [--start] $OUT/plate_1.gcode"
echo "After handoff, initialize the planned physical record (this creates NO verdict):"
echo "  qualification_check.py init --manifest $QUAL_MANIFEST --part <part_dir> \\\n    --id <YYYY-MM-DD-iN> --kind <coupon|full-part> --objective '<question>' \\\n    --output <part_dir>/qa/iterations/<YYYY-MM-DD-iN>.yaml"
