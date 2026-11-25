import contextlib
import io
import os
import signal
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checks
from checks import CheckFailed, run

SETTING = 1                      # a plain module-level constant: the worker compares these with the caller's


class Carrier:
    """A class the "generator" (this file) defines, passed to a section as an argument."""

    def __init__(self, value):
        self.value = value


def lines_after(seconds, lines):
    time.sleep(seconds)
    return lines


def refuse(message, kind="RuntimeError", after=0.0):
    time.sleep(after)
    raise {"RuntimeError": RuntimeError, "SystemExit": SystemExit, "ValueError": ValueError}[kind](message)


def crash():
    os.kill(os.getpid(), signal.SIGSEGV)


def big():
    return ["x" * 1000] * 3000                                     # about 3 MB pickled


def talk(word, wait):
    time.sleep(wait)
    print(word)
    return [word.upper()]


def read_some(path):
    with open(path) as stream:
        return [stream.read()[:13]]


def whoami():
    return [os.getpid()]


def setting():
    return [SETTING]


def unwrap(carrier):
    return [carrier.value * 2]


class CheckRunnerTests(unittest.TestCase):
    def test_lines_come_back_in_the_given_order_not_the_finishing_order(self):
        got = run([("a", lines_after, (0.5, ["a1", "a2"])), ("b", lines_after, (0.0, "b1")),
                   ("c", lines_after, (0.2, None)), ("d", lines_after, (0.1, ["d1"]))], jobs=4)
        self.assertEqual(got, ["a1", "a2", "b1", "d1"])

    def test_sections_run_at_the_same_time_each_in_its_own_process(self):
        started = time.monotonic()
        pids = run([(str(i), whoami) for i in range(4)] + [("slow %d" % i, lines_after, (1.0, [])) for i in range(6)],
                   jobs=10)
        self.assertLess(time.monotonic() - started, 4.0)           # the six sleeps alone are 6 s one after another
        self.assertEqual(len(set(pids)), 4)
        self.assertNotIn(os.getpid(), pids)

    def test_a_failure_keeps_its_own_message_and_names_its_section(self):
        with self.assertRaises(CheckFailed) as caught:
            run([("fits", lines_after, (0.0, ["ok"])), ("tabs", refuse, ("S: a tab strains 1.70 % at its root",))],
                jobs=2)
        self.assertEqual(str(caught.exception), "S: a tab strains 1.70 % at its root")
        self.assertEqual(caught.exception.section, "tabs")
        self.assertIn("RuntimeError", caught.exception.detail)
        self.assertIsInstance(caught.exception, RuntimeError)      # callers that catch RuntimeError still do

    def test_the_first_failure_in_the_given_order_wins_whichever_finished_first(self):
        with self.assertRaises(CheckFailed) as caught:
            run([("ok", lines_after, (0.0, [])), ("slow failure", refuse, ("first in order", "RuntimeError", 0.6)),
                 ("fast failure", refuse, ("first in time",))], jobs=3)
        self.assertEqual(str(caught.exception), "first in order")

    def test_later_sections_are_stopped_once_the_first_failure_is_known(self):
        started = time.monotonic()
        with self.assertRaises(CheckFailed) as caught:
            run([("fails at once", refuse, ("refused",)), ("would take a minute", lines_after, (60.0, ["late"]))],
                jobs=2)
        self.assertEqual(str(caught.exception), "refused")
        self.assertLess(time.monotonic() - started, 15.0)

    def test_a_systemexit_from_a_check_is_a_failure_not_a_pass(self):
        with self.assertRaises(CheckFailed) as caught:
            run([("a", lines_after, (0.0, [])), ("probes", refuse, ("spec.yaml probes are stale", "SystemExit"))],
                jobs=2)
        self.assertIn("stale", str(caught.exception))

    def test_a_worker_that_dies_without_answering_fails_and_is_named(self):
        with self.assertRaises(CheckFailed) as caught:
            run([("a", lines_after, (0.0, ["fine"])), ("kernel", crash)], jobs=2)
        self.assertIn("kernel", str(caught.exception))
        self.assertIn("without answering", str(caught.exception))

    def test_an_answer_larger_than_a_pipe_does_not_hang(self):
        got = run([("big", big), ("small", lines_after, (0.0, ["s"]))], jobs=2)
        self.assertEqual(len(got), 3001)

    def test_what_a_section_prints_is_replayed_in_order(self):
        seen = io.StringIO()
        with contextlib.redirect_stdout(seen):
            got = run([("one", talk, ("one", 0.4)), ("two", talk, ("two", 0.0))], jobs=2)
        self.assertEqual(seen.getvalue(), "one\ntwo\n")
        self.assertEqual(got, ["ONE", "TWO"])

    def test_a_file_only_a_worker_read_is_read_again_by_this_process(self):
        with tempfile.NamedTemporaryFile("w", suffix=".dat", delete=False) as handle:
            handle.write("a measurement a check depends on")
            path = handle.name
        seen = []
        sys.addaudithook(lambda event, args: seen.append(args[0]) if event == "open" else None)
        try:
            before = seen.count(path)
            self.assertEqual(run([("data", read_some, (path,)), ("other", lines_after, (0.0, []))], jobs=2),
                             ["a measurement"])
            self.assertEqual(seen.count(path), before + 1)           # this process's own watcher saw it
            self.assertGreaterEqual(seen.count(os.path.abspath(__file__)), 1)   # and the generator the worker imported
        finally:
            os.unlink(path)

    def test_a_section_over_its_time_limit_is_stopped_and_named(self):
        os.environ["CHECK_TIMEOUT"] = "1"
        try:
            with self.assertRaises(CheckFailed) as caught:
                run([("quick", lines_after, (0.0, [])), ("stuck", lines_after, (30.0, []))], jobs=2)
        finally:
            del os.environ["CHECK_TIMEOUT"]
        self.assertIn("stuck", str(caught.exception))
        self.assertIn("CHECK_TIMEOUT", str(caught.exception))

    def test_arguments_of_a_class_the_generator_defines_arrive_intact(self):
        self.assertEqual(run([("a", unwrap, (Carrier(21),)), ("b", unwrap, (Carrier("ab"),))], jobs=2), [42, "abab"])

    def test_a_caller_patched_in_memory_is_never_answered_by_the_code_on_disk(self):
        global SETTING
        SETTING = 2                                                  # what a careless negative control would do
        try:
            with self.assertRaises(CheckFailed) as caught:
                run([("a", setting), ("b", setting)], jobs=2)
            self.assertIn("does not have the constants", str(caught.exception))
            self.assertEqual(run([("a", setting), ("b", setting)], jobs=1), [2, 2])     # in one process it is right
        finally:
            SETTING = 1
        self.assertEqual(run([("a", setting), ("b", setting)], jobs=2), [1, 1])

    def test_a_negative_control_always_runs_in_this_process(self):
        os.environ["NEGATIVE_CASE"] = "1"
        try:
            self.assertEqual(run([("a", whoami), ("b", whoami)], jobs=4), [os.getpid(), os.getpid()])
        finally:
            del os.environ["NEGATIVE_CASE"]
        globals()["__negative_case__"] = True
        try:
            self.assertEqual(run([("a", whoami), ("b", whoami)], jobs=4), [os.getpid(), os.getpid()])
        finally:
            del globals()["__negative_case__"]

    def test_one_job_runs_in_this_process_and_raises_the_original_error(self):
        self.assertEqual(run([("a", whoami), ("b", lines_after, (0.0, ["b"]))], jobs=1), [os.getpid(), "b"])
        with self.assertRaises(ValueError):
            run([("a", refuse, ("plain", "ValueError")), ("b", whoami)], jobs=1)

    def test_only_module_level_functions_with_distinct_names_are_sections(self):
        with self.assertRaises(ValueError):
            run([("a", lambda: []), ("b", whoami)], jobs=2)
        def nested():
            return []
        with self.assertRaises(ValueError):
            run([("a", nested), ("b", whoami)], jobs=2)
        with self.assertRaises(ValueError):
            run([("same", whoami), ("same", whoami)])

    def test_check_jobs_env(self):
        os.environ["CHECK_JOBS"] = "1"
        try:
            self.assertEqual(checks.default_jobs(8), 1)
        finally:
            del os.environ["CHECK_JOBS"]
        self.assertGreaterEqual(checks.default_jobs(3), 1)


if __name__ == "__main__":
    unittest.main()
