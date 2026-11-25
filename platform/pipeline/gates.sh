#!/usr/bin/env bash
# gates.sh — the shell half of the gates.txt registry. Sourced by handoff.sh / verify-slice.sh.
#
# WHY THIS IS NOT A PYTHON CALL
# The obvious implementation is `python3 gates.py allows ...` at each call site. handoff.sh consults
# four gates per part and verify-slice.sh four more, and validate/hooks/pre-commit already carries a
# written note that a second interpreter start was a third of that gate's whole runtime. So this
# parses gates.txt in bash — same file, no second copy of the rules, no fork per question.
#
# WHY NOT KEEP THE GREPS
# `grep -q 'TOKEN: PASS'` hardcodes the verdict set at the call site. When VERIFY_RESULT grew DEBT
# on 2026-09-06, every such line silently became "DEBT is a failure", and finding them meant hitting
# them one at a time — handoff.sh refused, was fixed, and qualification_check.py then refused for
# the same reason. Asking the registry means a new verdict is decided once, in gates.txt.
set -uo pipefail

GATES_REGISTRY="${GATES_REGISTRY:-$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/gates.txt}"

# gate_verdict <TOKEN> <text>  — print the verdict the report announced, or nothing.
# Nothing is NOT the same as a failure: it means the stage produced no verdict line at all, which
# is a toolchain fault rather than a bad part. Callers that conflate the two report "fix the part"
# over a crash, which verify.sh:28-31 exists to stop happening again.
gate_verdict() {
    printf '%s\n' "$2" | sed -n "s/^[[:space:]]*$1:[[:space:]]*\([^[:space:]]\{1,\}\).*/\1/p" | head -1
}

# _gate_row <TOKEN> — the registry row, comments and blanks stripped.
_gate_row() {
    sed 's/#.*//' "$GATES_REGISTRY" | grep -E "^[[:space:]]*$1[[:space:]]*\|" | head -1
}

# gate_allows <TOKEN> <text> [condition_met]
#   0 = this verdict may proceed, 1 = it blocks.
# `condition_met` is required to be passed explicitly by any caller of a gate that HAS a conditional
# verdict; defaulting it to true would hand every caller the prototype's latitude, which is exactly
# the leak the conditional exists to prevent. Unknown verdicts and unknown tokens block.
gate_allows() {
    local token="$1" text="$2" condition_met="${3:-0}" row v passing conditional
    row=$(_gate_row "$token")
    [ -n "$row" ] || return 1
    v=$(gate_verdict "$token" "$text")
    [ -n "$v" ] || return 1
    passing=$(printf '%s' "$row" | awk -F'|' '{gsub(/ /,"",$2); print $2}')
    conditional=$(printf '%s' "$row" | awk -F'|' '{gsub(/ /,"",$3); print $3}')
    local allowed=0
    case ",$passing," in *",$v,"*) allowed=1;; esac
    if [ "$allowed" = 0 ] && [ "$condition_met" = 1 ] && [ "$conditional" != "-" ]; then
        case ",$conditional," in *",$v,"*) allowed=1;; esac
    fi
    _gate_record "$token" "$v" "$allowed" "$condition_met" "$row"
    [ "$allowed" = 1 ]
}

# Structured trace, so an agent does not have to parse a 60-line human report to learn what a stage
# decided. One JSON object per line into $GATE_RESULTS when the caller sets it — JSONL because bash
# can append to it safely and nothing has to seek back to close an array if a stage dies mid-run.
# The human text above is untouched: prose for people, this for machines, neither degraded for the
# other. Fields are drawn from gates.txt, so the trace explains itself without a second lookup.
_gate_record() {
    [ -n "${GATE_RESULTS:-}" ] || return 0
    # Serialization only, not a second gate evaluator. MESH_ROT="..." in the REAL registry
    # made hand-built JSON invalid. Encode all strings, and append the entire row together.
    python3 - "$1" "$2" "$3" "$4" "$5" >> "$GATE_RESULTS" <<'PY'
import json, sys
gate, verdict, allowed, condition_met, row = sys.argv[1:]
fields = [v.strip() for v in row.split('|')]
print(json.dumps(dict(gate=gate, verdict=verdict, allowed=allowed == '1', blocking=allowed != '1',
                      condition=fields[3], condition_met=condition_met == '1',
                      exit_on_block=fields[4], enforced_as=fields[7]), separators=(',', ':')))
PY
}

# gate_explain <TOKEN> — one line an agent or a human can act on, for a refusal message.
gate_explain() {
    local row
    row=$(_gate_row "$1")
    if [ -z "$row" ]; then echo "$1: not in $GATES_REGISTRY"; return 0; fi
    printf '%s' "$row" | awk -F'|' '{gsub(/^ +| +$/,"",$2); gsub(/^ +| +$/,"",$3);
        gsub(/^ +| +$/,"",$4); gsub(/^ +| +$/,"",$5);
        printf "%s: passing=%s", $1, $2;
        if ($3 != "-") printf "; also %s if %s", $3, $4;
        if ($5 != "-") printf "; blocks with exit %s", $5;
        printf "\n"}' | sed 's/^ *//'
}
