import hashlib
import json
import os
import subprocess
import tempfile
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
SEND = os.path.realpath(os.path.join(HERE, "..", "send", "send.sh"))


class SendIdentityGuardTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory(); self.addCleanup(self.td.cleanup)
        self.gcode = os.path.join(self.td.name, "plate.gcode")
        with open(self.gcode, "w") as stream:
            stream.write("G1 X1 Y1 E1\n")

    def run_send(self, approved="1"):
        env = os.environ.copy(); env["APPROVED"] = approved
        return subprocess.run([SEND, self.gcode], env=env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def write_complete_handoff(self, manifest_data=None):
        with open(self.gcode, "rb") as stream:
            digest = hashlib.sha256(stream.read()).hexdigest()
        manifest = os.path.join(self.td.name, "qualification_manifest.json")
        data = manifest_data or {"schema": 1, "human_evaluation": "not-evaluated",
                                 "plate": {"gcode": {"sha256": digest}}}
        with open(manifest, "w") as stream:
            json.dump(data, stream)
        with open(manifest, "rb") as stream:
            manifest_sha = hashlib.sha256(stream.read()).hexdigest()
        with open(os.path.join(self.td.name, "handoff.txt"), "w") as stream:
            stream.write("handoff presented\ngcode_sha=%s\n"
                         "qualification_manifest=%s\nqualification_manifest_sha=%s\n"
                         % (digest, manifest, manifest_sha))
        return manifest

    def test_changed_after_handoff_fails_before_network(self):
        with open(os.path.join(self.td.name, "handoff.txt"), "w") as stream:
            stream.write("handoff presented\ngcode_sha=" + "0" * 64 + "\n")
        result = self.run_send()
        self.assertEqual(result.returncode, 11, result.stdout)
        self.assertIn("changed after", result.stdout)

    def test_matching_hash_and_manifest_reach_human_approval_gate(self):
        self.write_complete_handoff()
        result = self.run_send(approved="0")
        self.assertEqual(result.returncode, 9, result.stdout)

    def test_legacy_handoff_without_qualification_manifest_is_not_upload_authority(self):
        with open(self.gcode, "rb") as stream:
            digest = hashlib.sha256(stream.read()).hexdigest()
        with open(os.path.join(self.td.name, "handoff.txt"), "w") as stream:
            stream.write("handoff presented\ngcode_sha=%s\n" % digest)
        result = self.run_send()
        self.assertEqual(result.returncode, 12, result.stdout)
        self.assertIn("archived handoffs are not upload authority", result.stdout)

    def test_manifest_mutation_fails_before_human_approval_or_network(self):
        manifest = self.write_complete_handoff()
        with open(manifest, "a") as stream:
            stream.write("changed")
        result = self.run_send()
        self.assertEqual(result.returncode, 12, result.stdout)
        self.assertIn("manifest changed after handoff", result.stdout)

    def test_manifest_for_other_gcode_fails(self):
        self.write_complete_handoff({"schema": 1, "human_evaluation": "not-evaluated",
                                     "plate": {"gcode": {"sha256": "f" * 64}}})
        result = self.run_send()
        self.assertEqual(result.returncode, 12, result.stdout)
        self.assertIn("different G-code bytes", result.stdout)

    def test_force_cannot_override_failed_deterministic_slice_gate(self):
        self.write_complete_handoff()
        with open(os.path.join(self.td.name, "verify_slice.txt"), "w") as stream:
            stream.write("FAIL\n")
        env = os.environ.copy(); env.update(APPROVED="1", FORCE="1")
        result = subprocess.run([SEND, self.gcode], env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(result.returncode, 7, result.stdout)
        self.assertIn("FORCE is not a bypass", result.stdout)

    def test_missing_verify_slice_is_also_a_hard_gate(self):
        self.write_complete_handoff()
        result = self.run_send()
        self.assertEqual(result.returncode, 7, result.stdout)
        self.assertIn("no verify_slice.txt", result.stdout)

    def test_missing_handoff_still_exits_eight(self):
        self.assertEqual(self.run_send().returncode, 8)


if __name__ == "__main__":
    unittest.main()
