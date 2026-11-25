import json
import os
import subprocess
import tempfile
import unittest


HERE = os.path.realpath(os.path.dirname(__file__))
RENDER = os.path.join(HERE, "render.sh")


class RenderProfileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stl = os.path.join(self.tmp.name, "part.stl")
        with open(self.stl, "wb") as stream:
            stream.write(b"solid fixture\nendsolid fixture\n")
        self.fake = os.path.join(self.tmp.name, "fake-openscad")
        with open(self.fake, "w", encoding="utf-8") as stream:
            stream.write("""#!/bin/sh
set -eu
out=
while [ $# -gt 0 ]; do
  if [ "$1" = -o ]; then out=$2; shift 2; else shift; fi
done
[ -n "$out" ]
printf 'fake-png' > "$out"
""")
        os.chmod(self.fake, 0o755)
        self.env = dict(os.environ, OPENSCAD=self.fake, FREECADCMD="missing-freecad-for-test")

    def test_zero_to_cad_profile_writes_eight_views_and_manifest(self):
        out = os.path.join(self.tmp.name, "eight")
        proc = subprocess.run([RENDER, "--profile", "zero-to-cad-8", self.stl, out],
                              env=self.env, text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        paths = [os.path.join(out, "part_image_%d.png" % index) for index in range(8)]
        self.assertTrue(all(os.path.getsize(path) > 0 for path in paths))
        with open(os.path.join(out, "part.zero-to-cad-8.json"), encoding="utf-8") as stream:
            manifest = json.load(stream)
        self.assertEqual(manifest["profile"], "zero-to-cad-8-v1")
        self.assertEqual(manifest["image_size"], [256, 256])
        self.assertEqual(len(manifest["views"]), 8)
        self.assertEqual([row["camera"]["rotation_z_deg"] for row in manifest["views"][:4]],
                         [45, 135, 225, 315])
        self.assertFalse(manifest["compatibility"]["exact_upstream_camera_matrices_published"])
        self.assertFalse(os.path.exists(os.path.join(out, "part.stamp")))

    def test_default_review_profile_remains_five_stamped_views(self):
        out = os.path.join(self.tmp.name, "review")
        proc = subprocess.run([RENDER, self.stl, out], env=self.env, text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        for name in ("iso", "iso_back", "top", "front", "back"):
            self.assertTrue(os.path.isfile(os.path.join(out, "part_%s.png" % name)))
        self.assertTrue(os.path.isfile(os.path.join(out, "part.stamp")))

    def test_unknown_profile_fails_closed(self):
        proc = subprocess.run([RENDER, "--profile", "pretty", self.stl, self.tmp.name],
                              env=self.env, text=True, capture_output=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unknown render profile", proc.stderr)


if __name__ == "__main__":
    unittest.main()
