"""Pure validation for the ``joints:`` section of a part contract.

The foreign-key check between a spec and `parts/_lib/joints.py`: every declared joint must name a
registry sample that EXISTS, is still USABLE, and was qualified in the context and print
orientation this part actually uses. It also enforces rule R1 (retention amplitude under the
captured clearance) and checks that an N-up layout physically fits the span it is declared in.

Like `fastener_check`, this validates a DECLARATION. It does not claim the joint fits: that is a
source assertion, a coupon, and a physical reality gate. What it does claim is that the part is
not silently reusing PLA numbers in PCTG, a superseded clearance, or a wave amplitude that
cannot assemble — the three ways a joint quietly becomes a different joint.

Severity follows the repo's gate philosophy: deterministic contradictions BLOCK; things that are
merely marginal or in-flight WARN.
"""
import os
import sys

_LIB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", "..", "parts", "_lib"))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from joints import (CONTEXTS, Context, SAMPLES, STUDIO_PITCH, UNKNOWN,  # noqa: E402
                    check_context, check_lever_scale, check_orientation,
                    check_retention, retention_location, span_required)
from rules import RULES  # noqa: E402

_ROLES = ("male", "female", "pair")
_RETENTION_PATTERNS = ("WAVE_TRAIN", "SHOULDER_RATCHET")
_LOCATIONS = ("captured", "shoulder")


def _row(jid, status, message, rule=None):
    """A finding. `rule` cites the learned rule behind it, so the gate teaches rather than
    merely refusing — the documented fix for lessons that go unapplied is delivering them at the
    point of decision, not filing them in a document nobody re-reads."""
    row = {"id": jid, "status": status, "message": message}
    if rule:
        row["rule"] = rule
        r = RULES.get(rule)
        if r and r.naive_fix:
            row["trap"] = r.naive_fix
    return row


def _context_from(decl):
    """Build a Context from a joint's declared context block, or None if unusable."""
    if not isinstance(decl, dict):
        return None, "context must be a mapping of printer/material/nozzle/layer_h"
    try:
        return Context(decl["printer"], decl["material"],
                       float(decl["nozzle"]), float(decl["layer_h"])), None
    except KeyError as exc:
        return None, "context missing %s" % exc
    except Exception as exc:                                    # unknown material, bad number
        return None, "context invalid: %s" % exc


def evaluate_joints(joints):
    """Validate declared joints against the registry.

    Returns ``{passed, declared_count, rows}``. A missing ``joints`` section is intentionally
    PASS — not every part has a joint. Declaring one and getting it wrong is a FAIL.
    """
    if joints is None:
        return {"passed": True, "declared_count": 0, "rows": []}
    if not isinstance(joints, list):
        return {"passed": False, "declared_count": 0,
                "rows": [_row("joints", "FAIL", "must be a list")]}

    rows, seen, failed = [], set(), False
    for idx, j in enumerate(joints):
        jid = j.get("id", "joint_%d" % (idx + 1)) if isinstance(j, dict) else "joint_%d" % (idx + 1)
        if not isinstance(j, dict):
            rows.append(_row(jid, "FAIL", "entry must be a mapping")); failed = True; continue
        if jid in seen:
            rows.append(_row(jid, "FAIL", "duplicate joint id")); failed = True; continue
        seen.add(jid)

        # ── foreign key: the sample must exist (rule R4) ──────────────────────────────────
        sid = j.get("sample")
        sample = SAMPLES.get(sid)
        if sample is None:
            rows.append(_row(jid, "FAIL",
                             "unknown sample %r — a joint without a registry entry is not "
                             "qualified; add it to parts/_lib/joints.py first" % (sid,),
                             rule="R4"))
            failed = True; continue
        if not sample.usable:
            hint = (" use %s instead" % sample.superseded_by) if sample.superseded_by else ""
            rows.append(_row(jid, "FAIL", "%s is %s and must not ship.%s"
                             % (sid, sample.status, hint)))
            failed = True; continue

        blank = sorted(k for k, v in sample.measures.items() if v is UNKNOWN)
        if blank:
            rows.append(_row(jid, "WARN",
                             "%s has unrecorded measures %s — the coupon had them, the log did "
                             "not capture them. Re-measure before relying on this fit."
                             % (sid, blank)))

        role = j.get("role", "pair")
        if role not in _ROLES:
            rows.append(_row(jid, "FAIL", "role must be one of %s" % (_ROLES,)))
            failed = True; continue

        evaluation = j.get("evaluation", {})
        if not isinstance(evaluation, dict) or not evaluation.get("physical_gate"):
            rows.append(_row(jid, "FAIL", "must name a physical_gate"))
            failed = True; continue

        # ── context: fits do not transfer across material/printer/process (R2/R3) ─────────
        ctx, err = _context_from(j.get("context"))
        if ctx is None:
            rows.append(_row(jid, "FAIL", err)); failed = True; continue
        ok, msg = check_context(sample, ctx)
        if not ok:
            if evaluation.get("coupon"):
                rows.append(_row(jid, "WARN", msg + " Coupon %r declared — the coupon, not the "
                                              "registry, is authoritative here."
                                 % evaluation["coupon"], rule="R3"))
            else:
                rows.append(_row(jid, "FAIL", msg + " Declare evaluation.coupon to proceed.",
                                 rule="R3"))
                failed = True; continue
        if CONTEXTS.get(ctx.id) and CONTEXTS[ctx.id].status == "retired":
            rows.append(_row(jid, "WARN", "context %s is retired hardware" % ctx.id))

        # ── orientation: an orientation change re-opens the coupon gate (R2) ──────────────
        orientation = j.get("orientation", sample.orientation)
        ok, msg = check_orientation(sample, orientation)
        if not ok:
            if evaluation.get("coupon"):
                rows.append(_row(jid, "WARN", msg, rule="R2"))
            else:
                rows.append(_row(jid, "FAIL", msg + " Declare evaluation.coupon to proceed.",
                                 rule="R2"))
                failed = True; continue

        # ── layout: count/pitch must physically fit the declared span ─────────────────────
        count, pitch = j.get("count", 1), float(j.get("pitch", STUDIO_PITCH))
        if not isinstance(count, int) or count < 1:
            rows.append(_row(jid, "FAIL", "count must be a positive integer"))
            failed = True; continue
        if count > 1 and pitch <= 0:
            rows.append(_row(jid, "FAIL", "pitch must be positive for a multi-feature joint"))
            failed = True; continue
        span = j.get("span")
        if span is not None:
            feature_w = _feature_width(sample)
            need = span_required(count, pitch, feature_w=feature_w)
            if need > float(span) + 1e-9:
                rows.append(_row(jid, "FAIL",
                                 "%d x %s at pitch %.2f needs %.2fmm but span is %.2fmm"
                                 % (count, sid, pitch, need, float(span))))
                failed = True; continue

        # ── infill: a per-object slicer setting that changes how much a part can deform ───
        declared_infill = j.get("infill")
        if declared_infill is not None and sample.infill is not None:
            if int(declared_infill) != int(sample.infill):
                rows.append(_row(jid, "WARN",
                                 "%s was qualified at %d%% infill but this part prints at %d%%. "
                                 "Infill changes how much a part deforms to let a tight mate "
                                 "pass — it silently flipped 100%%->15%% between VD R3 and R4 and "
                                 "confounded that whole result."
                                 % (sid, sample.infill, int(declared_infill)), rule="ONE-VARIABLE"))
        # An UNDECLARED infill is deliberately silent. Warning on every joint that omits it
        # would fire on nearly all of them and train people to skim past WARNs — which is how a
        # gate stops working. Only a declared MISMATCH is worth interrupting for.

        # ── LEVER-SCALE: a coupon does not prove a lever ──────────────────────────────────
        ok, msg = check_lever_scale(sample, j.get("engagement"), j.get("lever_length"),
                                    j.get("lever_evidence"))
        if not ok:
            rows.append(_row(jid, "WARN", msg, rule="LEVER-SCALE"))

        # ── rule R1: retention amplitude under the captured clearance ─────────────────────
        rid = j.get("retention")
        if rid:
            ret = SAMPLES.get(rid)
            if ret is None:
                rows.append(_row(jid, "FAIL", "unknown retention sample %r" % (rid,)))
                failed = True; continue
            if ret.pattern.id not in _RETENTION_PATTERNS:
                rows.append(_row(jid, "FAIL", "%s is a %s, not a retention pattern"
                                 % (rid, ret.pattern.id)))
                failed = True; continue
            if not ret.usable:
                rows.append(_row(jid, "FAIL", "retention %s is %s" % (rid, ret.status)))
                failed = True; continue
            where = j.get("retention_location")
            if where is not None and where not in _LOCATIONS:
                rows.append(_row(jid, "FAIL", "retention_location must be one of %s" % (_LOCATIONS,)))
                failed = True; continue
            ok, msg = check_retention(sample, ret, location=where, strict=True)
            if not ok:
                ok_loose, loose_msg = check_retention(sample, ret, location=where, strict=False)
                if ok_loose:
                    rows.append(_row(jid, "WARN", loose_msg, rule="R1"))
                else:
                    rows.append(_row(jid, "FAIL", msg, rule="R1")); failed = True; continue

        if not evaluation.get("source_assertion"):
            rows.append(_row(jid, "WARN",
                             "%s declared without a source_assertion — the generator should "
                             "assert containment/interference against the registry" % sid))
        if sample.status == "coupon-gate" and not evaluation.get("coupon"):
            rows.append(_row(jid, "FAIL", "%s is coupon-gate; name evaluation.coupon" % sid))
            failed = True; continue

        if not any(r["id"] == jid and r["status"] in ("FAIL", "WARN") for r in rows):
            ret_note = ""
            if rid:
                where = retention_location(SAMPLES[rid], j.get("retention_location"))
                ret_note = (" + %s (%s%s)"
                            % (rid, where,
                               ", outside the joint envelope so R1 does not bind"
                               if where == "shoulder" else ", R1 checked"))
            rows.append(_row(jid, "PASS",
                             "%s x%d @%.1f%s in %s; registry-backed, coupon remains authoritative"
                             % (sid, count, pitch, ret_note, ctx.id)))
    return {"passed": not failed, "declared_count": len(joints), "rows": rows}


def _feature_width(sample):
    """Transverse footprint of one feature, for the span check."""
    m = sample.measures
    for key in ("crest", "base_w", "mid_w", "peg_d"):
        if key in m:
            return float(m[key])
    return 0.0
