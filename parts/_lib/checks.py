#!/usr/bin/env python3
"""Run a generator's check sections side by side, and report them as if they had run one after another.

Why: a slow generator is slow in its checks, not its geometry. The touge road's body builds in 14 s and its checks
take 137 to 310 s a module, one after another on a 16-core machine (measured 2026-11-11).

    from checks import run
    lines = run([("S", checks, ("S", bodies["S"])),
                 ("BO", checks, ("BO", bodies["BO"]))])

Each section is (name, function, args): a MODULE-LEVEL function of the generator and arguments that pickle (CadQuery
shapes do, plain values do, a lambda does not). Each runs in its own fresh Python process, which imports the generator
file again and is handed the arguments.

Why fresh processes and not forks: the CAD kernel starts a pool of threads the first time it needs one, and a forked
child inherits the locks but not the threads. Forked after the road's three bodies were built, all three children sat
at 0 % CPU for ever (2026-11-11). A fresh process cannot inherit that.

What this must not change, and how it is kept:

- THE REPORT. Lines come back in the order the sections were given, whatever order they finished in.
- THE FAILURE. A section that raises fails the run with its own message. When several fail, the first in the given
  order is the one raised, as it would be serially. A worker that dies or runs over `CHECK_TIMEOUT` seconds (default
  3600) is a failure that names the section; it is never read as a pass.
- THE CODE UNDER TEST. A worker runs the generator AS IT IS ON DISK. A negative control runs a generator mutated in
  memory, so there every section runs in this process (`NEGATIVE_CASE` in the environment, or `__negative_case__` in
  the module). As a second guard the worker compares the generator's plain module-level constants with the caller's
  and refuses when they differ, so a caller patched in memory can never be answered by unpatched code.
- THE BUILD'S VIEW OF WHAT WAS READ. The declared build (`generate/build_provenance.py`) watches every file the
  generator process opens, to refuse an undeclared dependency. A worker's reads would be invisible to it, so each
  worker reports the files it opened and this process opens them again, where the watcher sees them.

`CHECK_JOBS=1` runs every section in this process, in order: use it under a profiler or a debugger.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import os
import pickle
import subprocess
import sys
import threading
import traceback
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

WORKER_MODULE = "check_section_generator"


class CheckFailed(RuntimeError):
    """A section's own failure, with its message unchanged. `.section` names it; `.detail` is its traceback."""

    def __init__(self, message, section=None, detail=""):
        super().__init__(message)
        self.section = section
        self.detail = detail


def default_jobs(count):
    env = os.environ.get("CHECK_JOBS")
    if env:
        return max(1, int(env))
    return max(1, min(count, (os.cpu_count() or 2) - 2))


def _plain(value):
    if isinstance(value, (bool, int, float, str, bytes, type(None))):
        return True
    return isinstance(value, (tuple, frozenset)) and all(_plain(v) for v in value)


def constants_digest(namespace):
    """A digest of a module's plain constants (numbers, strings, tuples of them), by name."""
    rows = [(name, repr(value)) for name, value in sorted(namespace.items())
            if not name.startswith("__") and _plain(value)]
    return hashlib.sha256(repr(rows).encode()).hexdigest()


def _lines(result):
    return [] if result is None else ([result] if isinstance(result, str) else list(result))


def _normalise(sections):
    rows = []
    for section in sections:
        name, fn = section[0], section[1]
        args = tuple(section[2]) if len(section) > 2 else ()
        rows.append((name, fn, args))
    names = [name for name, _, _ in rows]
    if len(set(names)) != len(names):
        raise ValueError("check sections need distinct names: %r" % names)
    return rows


def _request(fn, args):
    namespace = fn.__globals__
    path = namespace.get("__file__")
    if not path or fn.__qualname__ != fn.__name__ or namespace.get(fn.__name__) is not fn:
        raise ValueError("a check section must be a module-level function of the generator, with its values passed "
                         "as arguments: %r is not" % getattr(fn, "__qualname__", fn))
    return pickle.dumps({"path": str(Path(path).resolve()), "module_name": fn.__module__, "function": fn.__name__,
                         "args": pickle.dumps(args), "constants": constants_digest(namespace)})


def _replay_reads(paths):
    """Open again, in this process, what a worker opened: the build's watcher only sees this process."""
    for path in paths:
        try:
            if os.path.isfile(path):
                with open(path, "rb"):
                    pass
        except OSError:
            pass


def run(sections, jobs=None):
    """Run `sections`, each (name, function, args), and return their lines in the given order.

    A function returns a list of lines, one line, or None. The first failing section, in the given order, raises
    CheckFailed with that section's own message."""
    sections = _normalise(sections)
    jobs = default_jobs(len(sections)) if jobs is None else max(1, int(jobs))
    mutated = bool(os.environ.get("NEGATIVE_CASE")) or any(fn.__globals__.get("__negative_case__")
                                                           for _, fn, _ in sections)
    if jobs == 1 or len(sections) <= 1 or mutated:
        out = []
        for _, fn, args in sections:
            out += _lines(fn(*args))
        return out

    requests = [_request(fn, args) for _, fn, args in sections]
    limit = float(os.environ.get("CHECK_TIMEOUT", "3600"))
    env = dict(os.environ, CHECK_JOBS="1", PYTHONDONTWRITEBYTECODE="1")
    results = {}
    live = {}
    lock = threading.Lock()
    stopping = threading.Event()

    def one(index):
        name = sections[index][0]
        if stopping.is_set():
            return index, ("died", "%s: not run: an earlier section had already failed" % name, "", [])
        read_fd, write_fd = os.pipe()
        proc = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()), "--worker", str(write_fd)],
                                stdin=subprocess.PIPE, pass_fds=[write_fd], env=env)
        os.close(write_fd)
        with lock:
            live[index] = proc
        chunks = []

        def drain():
            with os.fdopen(read_fd, "rb") as pipe:
                chunks.append(pipe.read())

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        timed_out = False
        try:
            proc.stdin.write(requests[index])
            proc.stdin.close()
        except BrokenPipeError:
            pass
        try:
            proc.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            proc.wait()
        reader.join()
        with lock:
            live.pop(index, None)
        data = b"".join(chunks)
        if timed_out:
            return index, ("died", "%s: the check section ran over CHECK_TIMEOUT (%.0f s) and was stopped"
                           % (name, limit), "", [])
        if not data:
            code = proc.returncode
            how = "was killed by signal %d" % -code if code < 0 else "exited %d" % code
            if stopping.is_set():
                how = "was stopped: an earlier section had already failed"
            return index, ("died", "%s: the check section %s without answering" % (name, how), "", [])
        answer, printed, reads = pickle.loads(data)
        return index, (answer[0], answer[1], printed, reads)

    def first_failure_is_known():
        for index in range(len(sections)):
            if index not in results:
                return False
            if results[index][0] != "ok":
                return True
        return False

    with ThreadPoolExecutor(jobs) as pool:
        pending = {pool.submit(one, index) for index in range(len(sections))}
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                index, result = future.result()
                results[index] = result
            if first_failure_is_known() and not stopping.is_set():
                # The section that would have failed first, serially, has failed: the rest cannot change the outcome.
                stopping.set()
                with lock:
                    for proc in live.values():
                        proc.kill()

    out = []
    for index, (name, _, _) in enumerate(sections):
        kind, payload, printed, reads = results[index]
        _replay_reads(reads)
        if printed:
            sys.stdout.write(printed)
        if kind == "ok":
            out += payload
        elif kind == "died":
            raise CheckFailed(payload, section=name)
        else:
            _, message, detail = payload
            raise CheckFailed(message, section=name, detail=detail)
    return out


def _worker(result_fd):
    """One section in this fresh process: import the generator from disk, check it is the caller's, run, answer."""
    sys.dont_write_bytecode = True
    reads = []

    def audit(event, args):
        if event == "open":
            name, mode, flags = args
            if isinstance(mode, str) and ("w" in mode or "a" in mode or "+" in mode):
                return
            if isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                return
            if isinstance(name, (str, bytes, os.PathLike)):
                reads.append(os.fsdecode(name))

    sys.addaudithook(audit)
    request = pickle.load(sys.stdin.buffer)
    captured = io.StringIO()
    real_stdout = sys.stdout
    sys.stdout = captured
    try:
        path = Path(request["path"])
        sys.path.insert(0, str(path.parent))
        spec = importlib.util.spec_from_file_location(WORKER_MODULE, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[WORKER_MODULE] = module
        spec.loader.exec_module(module)
        # Arguments may hold instances of classes the generator defines; they were pickled under the caller's name
        # for that module ("__main__" when the generator was run as a script), so answer to that name too.
        sys.modules[request["module_name"]] = module
        if constants_digest(vars(module)) != request["constants"]:
            raise RuntimeError("the generator on disk (%s) does not have the constants of the code that asked for "
                               "this check: run the sections in one process (CHECK_JOBS=1)" % path.name)
        fn = getattr(module, request["function"])
        answer = ("ok", _lines(fn(*pickle.loads(request["args"]))))
    except BaseException as exc:                      # a SystemExit from a check is a refusal too
        answer = ("failed", (type(exc).__name__, str(exc), traceback.format_exc()))
    finally:
        sys.stdout = real_stdout
    for module in list(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if path:
            reads.append(path)
    with os.fdopen(result_fd, "wb") as pipe:
        pipe.write(pickle.dumps((answer, captured.getvalue(), sorted(set(reads)))))
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        _worker(int(sys.argv[2]))
    raise SystemExit("checks.py is a library; its only command is the worker it starts for itself")
