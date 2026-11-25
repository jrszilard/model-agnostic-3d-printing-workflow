"""One-shot manual repair reservation; never renew a deadline or clear prior costs."""
import json
import math
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from staging import digest, read_regular, require


def window(deadline, now=None):
    now = time.time() if now is None else now
    require(type(deadline) in (int, float) and math.isfinite(deadline), "invalid deadline")
    remaining = math.floor(deadline - now)
    require(10 < remaining <= 900, "original window unavailable; repair not run")
    return remaining - 4, remaining - 2   # include stop/outer kill margin inside original window


def claim_once(budget_path, expected_sha256, destination, *, now=None):
    """Generic exclusive claim of an independently pinned fresh budget; not approval.

    Caller policy fixes ONE destination for its approved attempt, independent of
    output paths. Any created/partial claim consumes the attempt, even on failure.
    """
    now = time.time() if now is None else now
    raw = read_regular(budget_path, maximum=1024*1024)
    require(digest(raw) == expected_sha256, 'budget identity mismatch')
    budget = json.loads(raw)
    require(type(budget['started_epoch']) in (int,float) and
            budget['started_epoch'] <= now < budget['deadline_epoch'] and
            0 < budget['deadline_epoch']-budget['started_epoch'] <= 900 and
            type(budget['maximum_launches_including_supervisor']) is int and
            1 <= budget['maximum_launches_including_supervisor'] <= 32, 'invalid fresh budget')
    window(budget['deadline_epoch'], now)
    value = {'kind':'one-shot-evaluation-claim','budget_record':str(Path(budget_path).absolute()),
             'budget_sha256':expected_sha256,'deadline_epoch':budget['deadline_epoch'],
             'claimed_epoch':now,'supervisor_reserved':True}
    fd = os.open(destination, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump(value,stream,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    parent = os.open(Path(destination).parent, os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(parent)
    finally: os.close(parent)
    return value


def reserve(budget_path, closed_path, *, now=None):
    now = time.time() if now is None else now
    raw_budget, raw_closed = read_regular(budget_path, maximum=1024*1024), read_regular(closed_path, maximum=1024*1024)
    budget, closed = json.loads(raw_budget), json.loads(raw_closed)
    deadline = budget["deadline_epoch"]
    window(deadline, now)
    prior = closed["launches_including_supervisor"]
    require(budget["maximum_launches_including_supervisor"] == 32
            and closed["batch_deadline_epoch"] == deadline
            and closed["batch_closed"] is True and closed["status"] == "incomplete"
            and type(prior) is int and prior == len(closed["records"]) + 1
            and prior + 13 <= 32 and budget["started_epoch"] <= closed["batch_finished_epoch"] <= now,
            "inconsistent prior budget/closed attempt")
    require(closed.get("controls_passed_before_cad") is True and not closed["cases"]
            and closed["records"][-1].get("label") == "runtime-freecad"
            and closed["records"][-1].get("status") == "rejected", "not the bounded HOME repair")
    reservation = Path(closed_path).parent / "repair-reservation.json"
    value = {"kind": "one-shot-freecad-identity-repair", "deadline_epoch": deadline,
             "carried_launches": prior, "launch_limit": prior + 13, "reserved_supervisor": True,
             "closed_record": str(Path(closed_path).absolute()), "closed_sha256": digest(raw_closed),
             "budget_record": str(Path(budget_path).absolute()), "budget_sha256": digest(raw_budget),
             "reserved_epoch": now}
    # Before supervisor creation. Retained even when startup fails; no retries/refund.
    fd = os.open(reservation, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return value, reservation


if __name__ == "__main__":
    if sys.argv[1] == "repair":
        value, path = reserve(sys.argv[2], sys.argv[3])
        runtime, outer = window(value["deadline_epoch"])
        print(runtime, outer, value["deadline_epoch"], path)
    else:
        runtime, outer = window(float(sys.argv[1]))
        print(runtime, outer)
