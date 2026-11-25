"""Pure validation for the optional ``fasteners:`` section in a part contract.

This checks that a design has declared the information needed to make an informed
fastener choice. It does *not* claim that CAD geometry or an as-printed joint is strong:
those are source assertions, a coupon, and a physical reality gate.

Shares `Context`/`Material` with the joint registry (`parts/_lib/process.py`). A receiver pocket
is a qualified physical fit exactly like a dovetail clearance: a side-entry captive-nut pocket
proven in PLA is not proven in PCTG, and no thread of any kind is proven in a material with no
filament profile. Declaring ``context:`` is optional (older specs predate it) but recommended —
without it the material advisories cannot fire.
"""
import os
import re
import sys

_LIB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", "..", "parts", "_lib"))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from process import context_from, material_advisories  # noqa: E402

# Methods that cut or form threads directly in the printed polymer, so the polymer's own
# behaviour governs the joint rather than a metal insert doing the work.
_POLYMER_THREADED = {"thread-forming-screw", "printed-thread"}

_METHODS = {
    "side-entry-captive-nut",
    "heat-set-insert",
    "external-through-nut",
    "threaded-substrate-compression-limiter",
    "thread-forming-screw",
    "printed-thread",
}


def _nominal_diameter(size):
    match = re.fullmatch(r"M(\d+(?:\.\d+)?)", str(size).upper())
    return float(match.group(1)) if match else None


def _row(fid, status, message):
    return {"id": fid, "status": status, "message": message}


def evaluate_fasteners(fasteners):
    """Validate declared fastener strategy; missing ``fasteners`` is intentionally PASS.

    Returns ``{passed, declared_count, rows}``. Any schema/geometry contradiction is FAIL;
    the caller still needs coupon and physical evidence for real joint strength.
    """
    if fasteners is None:
        return {"passed": True, "declared_count": 0, "rows": []}
    if not isinstance(fasteners, list):
        return {"passed": False, "declared_count": 0,
                "rows": [_row("fasteners", "FAIL", "must be a list")]}

    rows, seen, failed = [], set(), False
    for idx, f in enumerate(fasteners):
        fid = f.get("id", "fastener_%d" % (idx + 1)) if isinstance(f, dict) else "fastener_%d" % (idx + 1)
        if not isinstance(f, dict):
            rows.append(_row(fid, "FAIL", "entry must be a mapping")); failed = True; continue
        if fid in seen:
            rows.append(_row(fid, "FAIL", "duplicate fastener id")); failed = True; continue
        seen.add(fid)
        method, size, qty = f.get("method"), f.get("size"), f.get("quantity")
        if method not in _METHODS:
            rows.append(_row(fid, "FAIL", "unknown method %r" % method)); failed = True; continue
        if _nominal_diameter(size) is None:
            rows.append(_row(fid, "FAIL", "size must be metric form such as M3")); failed = True; continue
        if not isinstance(qty, int) or qty < 1:
            rows.append(_row(fid, "FAIL", "quantity must be a positive integer")); failed = True; continue
        evaluation = f.get("evaluation", {})
        if not isinstance(evaluation, dict) or not evaluation.get("physical_gate"):
            rows.append(_row(fid, "FAIL", "must name a physical_gate")); failed = True; continue

        # ── material/process context: the same dimension the joint registry uses ──────────
        if f.get("context") is not None:
            ctx, err = context_from(f["context"])
            if ctx is None:
                rows.append(_row(fid, "FAIL", err)); failed = True; continue
            sustained = bool(f.get("sustained_load"))
            blocked = False
            for severity, msg in material_advisories(ctx, sustained_load=sustained):
                rows.append(_row(fid, severity, msg))
                blocked = blocked or severity == "FAIL"
            if blocked:
                failed = True; continue
            if method in _POLYMER_THREADED and ctx.mat.id != "PLA":
                if not evaluation.get("coupon"):
                    rows.append(_row(fid, "FAIL",
                                     "%s cuts threads in the polymer itself and no %s coupon "
                                     "exists — pilot and holding are material-specific, so "
                                     "declare evaluation.coupon" % (method, ctx.mat.id)))
                    failed = True; continue
                rows.append(_row(fid, "WARN", "%s in %s is off the qualified material; coupon %r "
                                              "is authoritative"
                                 % (method, ctx.mat.id, evaluation["coupon"])))

        if method == "side-entry-captive-nut":
            receiver = f.get("receiver", {})
            nut = receiver.get("nut", {}) if isinstance(receiver, dict) else {}
            pocket = receiver.get("pocket", {}) if isinstance(receiver, dict) else {}
            required = (nut.get("across_flats"), nut.get("thickness"), pocket.get("across_flats"),
                        pocket.get("height"), pocket.get("roof"), receiver.get("entry_slit_width"),
                        receiver.get("bore_d"), evaluation.get("coupon"), evaluation.get("source_assertion"))
            if any(v is None for v in required):
                rows.append(_row(fid, "FAIL", "captive nut needs nut, pocket, bore, coupon, and source assertion")); failed = True; continue
            nominal = _nominal_diameter(size)
            if pocket["across_flats"] <= nut["across_flats"] or pocket["height"] <= nut["thickness"]:
                rows.append(_row(fid, "FAIL", "pocket must exceed nut across-flats and thickness")); failed = True; continue
            if receiver["entry_slit_width"] < nut["across_flats"]:
                rows.append(_row(fid, "FAIL", "entry slit is narrower than the nut")); failed = True; continue
            if receiver["bore_d"] <= nominal or pocket["roof"] <= 0:
                rows.append(_row(fid, "FAIL", "bore needs positive clearance and roof must be positive")); failed = True; continue
            rows.append(_row(fid, "PASS", "captive nut declaration complete; coupon remains authoritative"))
            continue

        if method == "heat-set-insert":
            receiver = f.get("receiver", {})
            if not (f.get("insert_vendor") and receiver.get("pilot_d") and receiver.get("boss_wall") and
                    evaluation.get("coupon")):
                rows.append(_row(fid, "FAIL", "heat-set insert needs vendor, pilot, boss wall, and coupon")); failed = True; continue
            rows.append(_row(fid, "PASS", "insert declaration complete; vendor-specific pilot is coupon-gated"))
            continue

        if method == "threaded-substrate-compression-limiter":
            substrate = f.get("substrate", {})
            limiter = f.get("limiter", {})
            stack = f.get("stack", {})
            if not isinstance(substrate, dict) or not isinstance(limiter, dict) or not isinstance(stack, dict):
                rows.append(_row(fid, "FAIL", "threaded substrate, limiter, and stack must be mappings")); failed = True; continue
            required = (substrate.get("material"), substrate.get("thread_size"), substrate.get("thread_pitch"),
                        substrate.get("tapped_depth"), limiter.get("od"), limiter.get("id"),
                        limiter.get("length"), limiter.get("undercut"), stack.get("under_head"),
                        f.get("clearance_bore_d"), f.get("assembly_access"), evaluation.get("coupon"),
                        evaluation.get("source_assertion"), evaluation.get("anti_bottom_out_assertion"))
            if any(v is None for v in required):
                rows.append(_row(fid, "FAIL", "threaded substrate limiter needs substrate thread/pitch/depth, "
                                 "limiter OD/ID/length/undercut, stack, clearance bore, access, coupon, "
                                 "and anti-bottom-out assertion")); failed = True; continue
            numeric = (substrate["thread_pitch"], substrate["tapped_depth"], limiter["od"], limiter["id"],
                       limiter["length"], limiter["undercut"], stack["under_head"], f["clearance_bore_d"])
            try:
                numeric = tuple(float(v) for v in numeric)
            except (TypeError, ValueError):
                rows.append(_row(fid, "FAIL", "threaded substrate limiter dimensions must be numeric")); failed = True; continue
            pitch, depth, od, inner, length, undercut, under_head, clearance = numeric
            if str(substrate["thread_size"]).upper() != str(size).upper():
                rows.append(_row(fid, "FAIL", "substrate thread_size must match fastener size")); failed = True; continue
            if min(pitch, depth, od, inner, length, under_head, clearance) <= 0 or undercut < 0:
                rows.append(_row(fid, "FAIL", "thread pitch/depth, limiter, stack, and bore must be positive; undercut non-negative")); failed = True; continue
            if inner >= od:
                rows.append(_row(fid, "FAIL", "limiter ID must be smaller than limiter OD")); failed = True; continue
            if clearance <= _nominal_diameter(size):
                rows.append(_row(fid, "FAIL", "clearance bore must exceed nominal fastener diameter")); failed = True; continue
            rows.append(_row(fid, "PASS", "threaded-substrate limiter declaration complete; stack/bottom-out coupon remains authoritative"))
            continue

        if method == "thread-forming-screw" and not (f.get("screw_vendor") and f.get("pilot_d") and evaluation.get("coupon")):
            rows.append(_row(fid, "FAIL", "thread-forming screw needs vendor, pilot, and coupon")); failed = True; continue
        if method == "printed-thread" and not evaluation.get("cycle_limit"):
            rows.append(_row(fid, "FAIL", "printed thread needs declared cycle_limit")); failed = True; continue
        if method == "external-through-nut" and not f.get("assembly_access"):
            rows.append(_row(fid, "FAIL", "through-nut needs declared assembly_access")); failed = True; continue
        rows.append(_row(fid, "PASS", "%s declaration complete" % method))
    return {"passed": not failed, "declared_count": len(fasteners), "rows": rows}
