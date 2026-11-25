#!/usr/bin/env bash
# send.sh — upload a gcode to the Prusa Core One (PrusaLink) and optionally start it, SAFELY.
# Usage: send.sh [--host h] [--name f.gcode] [--storage usb|local] [--start] [--no-idle-check] <gcode>
#   default host = coreone.lan (or $PRUSALINK).  Without --start it only uploads (stages).
#   --start refuses unless the printer is IDLE — never clobbers a running job.
#
# Credentials (PrusaLink, Buddy firmware). Put them in ~/.config/3d-printing-workflow/prusalink.env
# (or point PRUSALINK_ENV at your own file outside the repo):
#     PRUSALINK=coreone.lan
#     PRUSALINK_USER=maker             # printer: Settings > Network > PrusaLink (user + password)
#     PRUSALINK_PASSWORD=<password>    # HTTP digest auth
#   (PRUSALINK_KEY=<API key> also works on older firmware that issues one)
set -uo pipefail
HOST=""; NAME=""; START=0; IDLECHECK=1; GCODE=""; STORAGE=""
while [ $# -gt 0 ]; do case "$1" in
  --host) shift; HOST="$1";; --name) shift; NAME="$1";; --storage) shift; STORAGE="$1";;
  --start) START=1;; --no-idle-check) IDLECHECK=0;;
  -*) echo "unknown option: $1" >&2; exit 2;; *) GCODE="$1";;
esac; shift; done
[ -n "$GCODE" ] && [ -f "$GCODE" ] || { echo "usage: send.sh [opts] <gcode>" >&2; exit 2; }

# A green job can still be the wrong job. This refusal also applies to upload-only,
# before sourcing printer credentials or contacting a device. No approval flag clears a hold.
python3 "$(dirname "$(readlink -f "$0")")/../plate_scope.py" check "$(dirname "$GCODE")" || exit 18

# --- handoff gate (HARD) -------------------------------------------------------------------
# Blocks the UPLOAD, not just --start. Staging is not a safe half-step: a staged plate is one tap
# on the printer's screen from running, so the human must have seen the geometry before it gets
# there. Requires BOTH the handoff artifacts (handoff.sh) and an explicit APPROVED=1 from a human.
# Overriding this means typing APPROVED=1 yourself — which is the point: it cannot be inferred.
_hd="$(dirname "$GCODE")/handoff.txt"
if [ ! -f "$_hd" ]; then
    echo "REFUSING: no handoff.txt beside this gcode — the review step has not been run." >&2
    echo "  run:  platform/pipeline/handoff/handoff.sh $(dirname "$GCODE") [<part_dir>]" >&2
    echo "  then present those paths to the human and get approval." >&2
    exit 8
fi
_hsha=$(grep -m1 '^gcode_sha=' "$_hd" 2>/dev/null | cut -d= -f2-)
_now=$(sha256sum "$GCODE" | awk '{print $1}')
if [ -n "$_hsha" ]; then
    if [ "$_now" != "$_hsha" ]; then
        echo "REFUSING: gcode changed after the human handoff." >&2
        echo "  reviewed ${_hsha:0:12}, on disk now ${_now:0:12}; rerun verify-slice + handoff." >&2
        exit 11
    fi
else
    echo "NOTE: legacy handoff has no gcode sha; rerun handoff.sh to bind final bytes." >&2
fi

# The handoff manifest is the machine-known half of the future physical record. Requiring it on
# every future upload prevents a human result from later becoming an unbound prose claim. It is
# explicitly NOT an approval or a physical verdict; those remain human-only after the print.
_qpath=$(grep -m1 '^qualification_manifest=' "$_hd" 2>/dev/null | cut -d= -f2-)
_qsha=$(grep -m1 '^qualification_manifest_sha=' "$_hd" 2>/dev/null | cut -d= -f2-)
_expected_q=$(readlink -f "$(dirname "$GCODE")/qualification_manifest.json" 2>/dev/null)
_actual_q=$(readlink -f "$_qpath" 2>/dev/null)
if [ -z "$_qpath" ] || [ -z "$_qsha" ] || [ -z "$_actual_q" ] \
        || [ "$_actual_q" != "$_expected_q" ] || [ ! -f "$_actual_q" ]; then
    echo "REFUSING: handoff has no exact qualification_manifest.json beside this G-code." >&2
    echo "  rerun verify-slice + handoff; archived handoffs are not upload authority." >&2
    exit 12
fi
_qnow=$(sha256sum "$_actual_q" | awk '{print $1}')
if [ "$_qnow" != "$_qsha" ]; then
    echo "REFUSING: qualification manifest changed after handoff." >&2
    echo "  reviewed ${_qsha:0:12}, on disk now ${_qnow:0:12}; rerun handoff." >&2
    exit 12
fi
if ! python3 - "$_actual_q" "$_now" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as stream:
        data = json.load(stream)
    ok = (data.get("schema") == 1 and data.get("human_evaluation") == "not-evaluated"
          and data.get("plate", {}).get("gcode", {}).get("sha256") == sys.argv[2])
except (OSError, ValueError):
    ok = False
raise SystemExit(0 if ok else 1)
PY
then
    echo "REFUSING: qualification manifest is malformed or names different G-code bytes." >&2
    exit 12
fi
if [ "${APPROVED:-0}" != 1 ]; then
    echo "REFUSING: handoff was presented but not approved (APPROVED=1 not set)." >&2
    echo "  a human must review the artifacts in $(dirname "$GCODE") and approve." >&2
    echo "  then:  APPROVED=1 $0 $([ "$START" = 1 ] && echo '--start ')<gcode>" >&2
    exit 9
fi

_vs="$(dirname "$GCODE")/verify_slice.txt"
if [ ! -f "$_vs" ]; then
    echo "REFUSING: no verify_slice.txt beside this G-code — run verify-slice.sh first." >&2
    exit 7
fi
if [ "$(cat "$_vs")" != "PASS" ]; then
    echo "REFUSING: verify-slice = $(cat "$_vs") for this plate." >&2
    echo "  Deterministic slice failures are hard gates; fix and re-slice. FORCE is not a bypass." >&2
    exit 7
fi
# Upload must be the same per-ID request + comparison and the same 3MF/G-code the human saw.
# An old green slice is not proof; no legacy override. Run before credentials or any network access.
python3 "$(dirname "$(readlink -f "$0")")/../plate_inventory.py" bound "$(dirname "$GCODE")" --gcode "$GCODE" || exit 19
CONF="${PRUSALINK_ENV:-$HOME/.config/3d-printing-workflow/prusalink.env}"
# shellcheck disable=SC1090
[ -f "$CONF" ] && . "$CONF"
HOST="${HOST:-${PRUSALINK:-coreone.lan}}"; STORAGE="${STORAGE:-${PRUSALINK_STORAGE:-usb}}"

# --- nozzle mismatch NOTICE (reports, does not block) -----------------------------------------
# The plate's profile stack assumes a nozzle, and says so in `M862.1 ... F<0|1>`. The fitted nozzle
# is a recorded bench fact (PRUSALINK_NOZZLE in $CONF, `0.4` or `HF0.4`) because PrusaLink reports
# nozzle DIAMETER and never high-flow.
#
# THIS DOES NOT BLOCK, and the reason is evidence. On 2026-09-21 it was written as a hard refusal
# on the theory that the printer stops at the start of the print when the flag disagrees. This
# bench disproves that: the HF0.4 nozzle has been fitted throughout, and ladder-i1, ladder-i2,
# f1-i1 and f2-i1 all declare F0, all printed, and all gave usable physical results. A hard gate
# would have refused four good plates. What the mismatch really means is milder and still worth
# saying out loud: the plate was sliced with a recipe tuned for the other nozzle -- for the
# gutter-backstop PETG plates, 240 C and a 12 mm3/s cap against the HF preset's 250 and 21.
_plate_hf=$(grep -m1 -aoE 'M862\.1 [^;]*F[01]' "$GCODE" | grep -oE 'F[01]$' | tr -d 'F')
if [ -n "$_plate_hf" ]; then
    _pn=$([ "$_plate_hf" = 1 ] && echo "HF0.4 (high flow)" || echo "0.4 (standard)")
    if [ -z "${PRUSALINK_NOZZLE:-}" ]; then
        echo "NOTE: this plate's profiles assume a $_pn nozzle; the bench records no fitted nozzle." >&2
        echo "      Set PRUSALINK_NOZZLE=0.4 or HF0.4 in $CONF to have this compared." >&2
    else
        case "$PRUSALINK_NOZZLE" in HF0.4|HF*) _want=1;; *) _want=0;; esac
        if [ "$_plate_hf" != "$_want" ]; then
            echo "NOTE: PROFILE/NOZZLE MISMATCH. This plate's profiles assume a $_pn nozzle; the" >&2
            echo "      bench records PRUSALINK_NOZZLE=$PRUSALINK_NOZZLE. It will still print." >&2
            echo "      Its speeds, flow cap and temperatures are the other nozzle's recipe --" >&2
            echo "      check that is what you want before spending the print. See docs/workflow.md." >&2
        fi
    fi
fi

[ -z "$NAME" ] && NAME=$(basename "$GCODE")
API="http://$HOST"

# Current Buddy firmware shows a USERNAME + PASSWORD on the printer (digest auth) rather than an
# API key; the key path is kept for older firmware that still issues one.
AUTH=()
if [ -n "${PRUSALINK_PASSWORD:-}" ]; then AUTH=(--digest -u "${PRUSALINK_USER:-maker}:$PRUSALINK_PASSWORD")
elif [ -n "${PRUSALINK_KEY:-}" ]; then    AUTH=(-H "X-Api-Key: $PRUSALINK_KEY")
else
    echo "no credentials: set PRUSALINK_USER + PRUSALINK_PASSWORD (in $CONF)." >&2
    echo "  get them on the printer: Settings > Network > PrusaLink (shows user + password)" >&2
    exit 2
fi
req(){ curl -s -m "${3:-15}" "${AUTH[@]}" -X "${2:-GET}" "$API$1"; }

st=$(req /api/v1/status)
echo "$st" | grep -q '"printer"' || { echo "PrusaLink not reachable/authorized at $HOST: ${st:-no response}" >&2; exit 3; }
state=$(echo "$st" | tr ',{}' '\n\n\n' | grep -o '"state" *: *"[A-Za-z]*"' | head -1 | cut -d'"' -f4)
echo "printer state: ${state:-unknown}"

if [ "$START" = 1 ] && [ "$IDLECHECK" = 1 ]; then
  case "$state" in
    IDLE|FINISHED|STOPPED|READY|"") : ;;
    *) echo "REFUSING to start: printer state='$state' (busy). Nothing uploaded." >&2; exit 5;;
  esac
fi

# --- active-job guard (HARD) ---------------------------------------------------------------
# The plain upload carries `Overwrite: ?1`, so it replaces a file WHOLESALE — including the one
# the printer is currently reading its job out of. The --start path has refused a busy printer
# since day one, but a bare upload checked nothing, on the reasoning that staging is a safe
# half-step. Staging OVER the running file is not staging; it is editing the job in flight.
#
# 2026-08-05: six plates were uploaded as a batch while rt1base was 27 minutes into printing.
# The job went PAUSED and the printer to ATTENTION. The gate that existed guarded the wrong verb.
job=$(req /api/v1/job)
job_file=$(echo "$job" | grep -o '"display_name" *: *"[^"]*"' | head -1 | cut -d'"' -f4)
job_short=$(echo "$job" | grep -o '"name" *: *"[^"]*"' | head -1 | cut -d'"' -f4)
job_state=$(echo "$job" | grep -o '"state" *: *"[A-Za-z]*"' | head -1 | cut -d'"' -f4)
if [ -n "$job_state" ]; then
  case "$job_state" in
    PRINTING|PAUSED|ATTENTION|BUSY)
      if [ "$job_file" = "$NAME" ] || [ "$job_short" = "$NAME" ]; then
        echo "REFUSING: '$NAME' IS the current job's file (job state=$job_state)." >&2
        echo "  Uploading would overwrite the gcode the printer is reading, mid-job." >&2
        echo "  Cancel or finish the job first, or stage under a different --name." >&2
        [ "${FORCE:-0}" = 1 ] || exit 6
        echo "  FORCE=1 — proceeding anyway. This can corrupt the running print." >&2
      else
        echo "NOTE: a job is $job_state ('${job_file:-$job_short}'). Uploading a DIFFERENT file is" >&2
        echo "      safe, but it competes for the printer's link — expect a slow transfer." >&2
      fi;;
  esac
fi

# PrusaLink v1 upload is a PUT of the raw file to its destination path.
# Print-After-Upload starts the job in the same request (?1 = true) — there is no separate
# "start file X" call in the v1 API, so --start must be decided before the upload.
#
# Retry: digest auth makes curl send the body, take a 401, then send it AGAIN with credentials.
# On a multi-MB plate that doubles the transfer and the printer intermittently gives up with
# HTTP 408 (an 8 MB plate takes ~23 s on a good run). The upload is idempotent — Overwrite is
# set and a partial file is replaced wholesale — so retrying is safe.
HDRS=(-H "Content-Type: application/octet-stream")
if [ "$START" = 1 ]; then
    # `Overwrite: ?1` together with `Print-After-Upload: ?1` onto an EXISTING filename makes the
    # firmware answer 500 on every attempt (observed 2026-07-20; the same body uploaded fine to an
    # unused name). Delete first, then upload clean, rather than overwrite-and-print.
    HDRS+=(-H "Print-After-Upload: ?1")
    curl -s -m 30 "${AUTH[@]}" -X DELETE "$API/api/v1/files/$STORAGE/$NAME" >/dev/null 2>&1 || true
else
    HDRS+=(-H "Overwrite: ?1")
fi
code=""; body=""
for attempt in 1 2 3; do
  code=$(curl -s -m 600 -o /tmp/.prusalink_up.$$ -w '%{http_code}' "${AUTH[@]}" "${HDRS[@]}" \
          --upload-file "$GCODE" "$API/api/v1/files/$STORAGE/$NAME")
  body=$(tr -d '\0' < /tmp/.prusalink_up.$$ 2>/dev/null); rm -f /tmp/.prusalink_up.$$
  case "$code" in
    20*|409) break;;
    408|000|5*) echo "upload attempt $attempt failed (HTTP $code) — retrying" >&2; sleep 3;;
    *) break;;
  esac
done
case "$code" in
  20*|409) echo "uploaded: $NAME -> $STORAGE  (from $(basename "$GCODE"))";;
  *) echo "upload failed: HTTP $code ${body:-}" >&2; exit 4;;
esac

# --- the local record of the send ------------------------------------------------------------
# Until now this left NO trace beside the plate, so nothing in the tree could tell an approved,
# uploaded plate from one still waiting to be presented — next_action.py read handoff.txt, saw a
# presented handoff, and reported AWAITING HUMAN APPROVAL forever after. An agent acting on that
# would re-present, or worse re-send, a plate already on the printer.
#
# What it records is only what this script actually did. Approval itself is NOT recorded as a
# fact about a person: APPROVED=1 is an assertion made to this script, and writing "the human
# approved" from it would manufacture the human evidence the handoff gate exists to require. So
# the field is named for what it is.
_sent="$(dirname "$GCODE")/sent.json"
printf '{"sent_at":"%s","gcode":"%s","gcode_sha256":"%s","name":"%s","host":"%s","storage":"%s",' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(basename "$GCODE")" "$_now" "$NAME" "$HOST" "$STORAGE" \
    > "$_sent" 2>/dev/null || _sent=""
[ -n "$_sent" ] && printf '"started":%s,"approved_env_was_set":true}\n' \
    "$([ "$START" = 1 ] && echo true || echo false)" >> "$_sent"

if [ "$START" = 1 ]; then
  sleep 3; echo "print started; state=$(req /api/v1/status | tr ',{}' '\n\n\n' | grep -o '"state" *: *"[A-Za-z]*"' | head -1 | cut -d'"' -f4)"
else
  echo "staged only (no --start) — start it on the printer's screen, in PrusaLink (http://$HOST), or re-run with --start."
fi
[ -n "$_sent" ] && echo "recorded: $_sent"
