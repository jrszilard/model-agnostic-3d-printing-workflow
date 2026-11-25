import json
import os
import stat
import subprocess
import tempfile
import unittest


ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
TOOLCHAIN = os.path.join(ROOT, "platform", "pipeline", "toolchain.sh")


class ToolchainTest(unittest.TestCase):
    def _script(self, path, body):
        with open(path, "w", encoding="utf-8") as stream:
            stream.write("#!/bin/sh\n" + body)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)

    def _run(self, include_ocp=True, fake_ocp="7.9.3.1", extra_key=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        lock = os.path.join(temp.name, "toolchain.lock")
        lines = ["cadquery = 2.8.0"]
        if include_ocp:
            lines.append("ocp = 7.9.3.1")
        lines += ["python = 3.14.7", "openscad = 2021.01", "prusaslicer = 2.9.6",
                  "cadquery_venv = ~/ignored"]
        if extra_key:
            lines.append("%s = 1.2.3" % extra_key)
        with open(lock, "w", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")

        fake_python = os.path.join(temp.name, "python")
        self._script(fake_python, """
case "$*" in
  *"import cadquery"*) echo "${FAKE_CQ:-2.8.0}" ;;
  *"import OCP"*) echo "${FAKE_OCP:-7.9.3.1}" ;;
  *--version*) echo "Python ${FAKE_PYTHON:-3.14.7}" ;;
  *) exit 2 ;;
esac
""")
        self._script(os.path.join(temp.name, "openscad"),
                     'echo "OpenSCAD version ${FAKE_OPENSCAD:-2021.01}" >&2\n')
        self._script(os.path.join(temp.name, "prusa-slicer"),
                     'echo "PrusaSlicer-${FAKE_PRUSA:-2.9.6}+test based on Slic3r"\n')
        env = os.environ.copy()
        env.update({"TOOLCHAIN_LOCK": lock, "CADQUERY_PY": fake_python,
                    "PATH": temp.name + os.pathsep + env["PATH"], "FAKE_OCP": fake_ocp})
        return subprocess.run([TOOLCHAIN], env=env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def test_checks_every_declared_version(self):
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("ocp           7.9.3.1", result.stdout)
        self.assertIn("prusaslicer   2.9.6", result.stdout)
        self.assertIn("ALL DECLARED VERSION ENTRIES MATCH (5 checked", result.stdout)
        self.assertIn("coverage/build provenance not attested", result.stdout)

    def test_ocp_drift_is_not_a_false_match(self):
        result = self._run(fake_ocp="7.9.4")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("[want 7.9.3.1]", result.stdout)
        self.assertIn("TOOLCHAIN DRIFT", result.stdout)

    def test_missing_ocp_pin_is_not_a_false_match(self):
        result = self._run(include_ocp=False)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("ocp           7.9.3.1           [UNPINNED]", result.stdout)

    def test_new_lock_key_requires_a_checker(self):
        result = self._run(extra_key="freecad")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("freecad          [NO CHECK IMPLEMENTED]", result.stdout)

    def test_provenance_templates_do_not_attest_to_copied_tool_versions(self):
        paths = (os.path.join(ROOT, "parts", "_TEMPLATE", "provenance.json"),
                 os.path.join(ROOT, "platform", "schemas", "provenance.template.json"))
        for path in paths:
            with self.subTest(path=path), open(path, encoding="utf-8") as stream:
                data = json.load(stream)
                self.assertEqual(data["schema"], 2)
                self.assertEqual(data["toolchain"]["lock_path"], "platform/toolchain.lock")
                for key in ("lock_sha256", "python", "cadquery", "ocp", "openscad",
                            "prusaslicer"):
                    self.assertIsNone(data["toolchain"][key])


if __name__ == "__main__":
    unittest.main()
