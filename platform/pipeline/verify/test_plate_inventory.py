"""Regression controls: expected quantities, mesh identity, real model deposition and review bindings."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import plate_inventory as inv
from inventory_fixture import package, restamp


class InventoryTests(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.p = Path(td.name)

    def result(self, want):
        r = inv.compare(self.p)
        self.assertEqual(r["verdict"], want, r)
        return r

    def test_instances_not_resources_or_files_and_disabled_items_do_not_count(self):
        package(
            self.p, {"clip": 2}, [("clip", 10, 10, True), ("clip", 30, 10, True), ("foot", 50, 10, False)]
        )
        r = self.result("PASS")
        self.assertEqual(r["sliced"], {"clip": 2})
        self.assertEqual(len(r["instances"]), 2)

    def test_same_total_wrong_type_and_extra_duplicate(self):
        package(self.p, {"foot": 1, "clip": 1}, [("clip", 10, 10, True), ("clip", 30, 10, True)])
        r = self.result("MISMATCH")
        self.assertEqual(r["missing"], {"foot": 1})
        self.assertEqual(r["extra"], {"clip": 1})

    def test_missing_instance_not_inferred_from_same_mesh_name(self):
        package(self.p, {"clip": 2})
        r = self.result("MISMATCH")
        self.assertEqual(r["missing"], {"clip": 1})

    def test_support_only_brim_purge_and_travel_do_not_count(self):
        rows = [("clip", 10, 10, True), ("foot", 30, 10, True)]
        for role in ("Support material", "Skirt/Brim", "Custom", "Purge tower"):
            with self.subTest(role=role):
                package(self.p, {"clip": 1, "foot": 1}, rows, [(10, 10, "Perimeter"), (30, 10, role)])
                r = self.result("UNPROVEN")
                self.assertEqual(r["project_counts"], {"clip": 1, "foot": 1})
                self.assertEqual(r["sliced"], {"clip": 1})
        package(self.p, {"clip": 1, "foot": 1}, rows)
        p = self.p / inv.GCODE
        p.write_text(p.read_text().replace("X32 Y11 E0.03", "X32 Y11 E-0.03\nG1 E0.03"))
        restamp(self.p)
        self.assertEqual(self.result("UNPROVEN")["sliced"], {"clip": 1})

    def test_missing_layer_or_extra_model_path_outside_the_project(self):
        package(self.p)
        p = self.p / inv.GCODE
        s = p.read_text()
        start = s.index(";Z:0.4")
        end = s.index(";Z:0.6")
        p.write_text(s[:start] + s[start:end].replace("E0.03", "E0") + s[end:])
        restamp(self.p)
        self.result("UNPROVEN")
        package(self.p, paths=[(10, 10, "Perimeter"), (59, 53, "External perimeter")])
        r = self.result("UNPROVEN")
        self.assertGreater(r["deposition"]["unassigned_model_moves"], 0)

    def test_ambiguous_identity_or_overlaid_copies_cannot_satisfy_inventory(self):
        package(self.p)
        p = self.p / inv.CATALOG
        cat = json.loads(p.read_text())
        cat["models"]["foot"] = cat["models"]["clip"]
        p.write_text(json.dumps(cat))
        self.assertIn("ambiguous IDs", " ".join(self.result("UNPROVEN")["problems"]))
        package(self.p, {"clip": 2}, [("clip", 10, 10, True)] * 2)
        self.assertGreater(self.result("UNPROVEN")["deposition"]["ambiguous_model_moves"], 0)

    def test_uncatalogued_substitution_same_extents_not_mistaken_for_a_known_mesh(self):
        package(self.p)
        p = self.p / inv.PROJECT
        with ZipFile(p) as z:
            m = z.read("3D/3dmodel.model")
        self.assertIn(b'<vertex x="4" y="4" z="0.6"', m)
        m = m.replace(b'<vertex x="4" y="4" z="0.6"', b'<vertex x="3.7" y="4" z="0.6"', 1)
        with ZipFile(p, "w") as z:
            z.writestr("3D/3dmodel.model", m)
        restamp(self.p)
        self.assertIn("uncatalogued geometry", " ".join(self.result("UNPROVEN")["problems"]))

    def test_malformed_or_missing_request_is_not_an_empty_order(self):
        for bad in (
            None,
            "{}",
            '{"schema":1,"requested":{}}',
            '{"schema":1,"requested":{"clip":true}}',
            '{"schema":1,"requested":{"clip":1,"clip":2}}',
            '{"schema":1,"requested":{"clip":-1}}',
        ):
            with self.subTest(bad=bad):
                package(self.p)
                p = self.p / inv.REQUEST
                if bad is None:
                    p.unlink()
                else:
                    p.write_text(bad)
                self.result("UNPROVEN")

    def test_retract_then_combined_xy_unretract_is_not_model_deposition(self):
        package(self.p)
        p = self.p / inv.GCODE
        s = p.read_text().replace("G1 X12 Y11 E0.03", "G1 E-1\nG1 X12 Y11 E1")
        p.write_text(s)
        restamp(self.p)
        self.assertFalse(self.result("UNPROVEN")["read_paths"])

    def test_actual_last_layer_must_not_be_entirely_missing(self):
        package(self.p)
        p = self.p / inv.GCODE
        s = p.read_text()
        i = s.index(";Z:0.6")
        p.write_text(s[:i] + s[i:].replace("E0.03", "E0"))
        restamp(self.p)
        self.assertFalse(self.result("UNPROVEN")["instances"][0]["through_height"])

    def test_absolute_e_reset_and_arc_are_supported_not_counted_as_header_declarations(self):
        package(self.p)
        p = self.p / inv.GCODE
        s = (
            p.read_text()
            .replace("M83", "M82")
            .replace("G1 X12 Y11 E0.03", "G92 E0\nG3 X12 Y11 I0.5 J0 E0.03")
        )
        p.write_text(s)
        restamp(self.p)
        self.assertEqual(self.result("PASS")["instances"][0]["exclusive_moves"], 3)

    def test_independent_upload_path_must_contain_reviewed_job_bytes(self):
        package(self.p)
        inv.record(self.p, self.result("PASS"))
        fields = {"inventory_sha": [inv.sha(self.p / inv.REPORT)]}
        other = self.p / "different.gcode"
        other.write_text("; another job")
        with self.assertRaisesRegex(ValueError, "selected for upload"):
            inv.bound(self.p, fields, gcode=other)

    def test_modifier_unsupported_record_and_stale_slice_stop(self):
        package(self.p)
        p = self.p / inv.PROJECT
        with ZipFile(p, "a") as z:
            z.writestr(
                "Metadata/Slic3r_PE_model.config",
                '<config><metadata key="volume_type" value="NegativeVolume"/></config>',
            )
        self.assertIn("bind", " ".join(self.result("UNPROVEN")["problems"]))
        restamp(self.p)
        self.assertIn("modifier", " ".join(self.result("UNPROVEN")["problems"]))

    def test_quarter_turn_and_component_build_tree_not_all_resource_definitions(self):
        package(self.p, {"foot": 1}, [("foot", 30, 10, True)], [(24, 12, "Perimeter")])
        p = self.p / inv.PROJECT
        with ZipFile(p) as z:
            m = z.read("3D/3dmodel.model")
        m = m.replace(
            b"</resources>",
            b'<object id="3" type="model"><components><component objectid="2" transform="0 1 0 -1 0 0 0 0 1 0 0 0"/></components></object></resources>',
        ).replace(b'<item objectid="2"', b'<item objectid="3"')
        with ZipFile(p, "w") as z:
            z.writestr("3D/3dmodel.model", m)
        restamp(self.p)
        self.result("PASS")

    def test_bound_rejects_changed_inputs_report_or_missing_handoff_binding(self):
        for name in (
            inv.REQUEST,
            inv.CATALOG,
            inv.REPORT,
            inv.META,
            inv.GCODE,
            inv.PROJECT,
            "source",
            "handoff",
        ):
            with self.subTest(name=name):
                package(self.p)
                inv.record(self.p, self.result("PASS"))
                fields = {"inventory_sha": [inv.sha(self.p / inv.REPORT)]}
                self.assertEqual(inv.bound(self.p, fields), {"clip": 1})
                if name == "handoff":
                    fields = {}
                else:
                    p = next((self.p / inv.REFS).glob("*")) if name == "source" else self.p / name
                    with p.open("ab") as f:
                        f.write(b" ")
                with self.assertRaises(ValueError):
                    inv.bound(self.p, fields)

    def test_pre_slice_declaration_is_exclusive_and_separate_from_catalog(self):
        from inventory_fixture import SIZES, mesh_bytes

        d = self.p / "new"
        mesh = self.p / "clip.stl"
        mesh.write_bytes(mesh_bytes(SIZES["clip"]))
        inv.capture(d, "request", ["clip=2"], None)
        inv.capture(d, "catalog", [f"clip={mesh}"], "as-saved")
        self.assertEqual(inv.inputs(d)[0], {"clip": 2})
        self.assertFalse((d / inv.REPORT).exists())
        with self.assertRaises(ValueError):
            inv.capture(d, "request", ["clip=1"], None)
        (self.p / inv.GCODE).write_text("; test")
        with self.assertRaises(ValueError):
            inv.capture(self.p, "request", ["clip=1"], None)

    def test_send_refuses_stale_inventory_before_credentials_and_network(self):
        package(self.p)
        r = self.result("PASS")
        inv.record(self.p, r)
        h = self.p / "handoff.txt"
        qm = self.p / "qualification_manifest.json"
        gsha = inv.sha(self.p / inv.GCODE)
        qm.write_text(
            json.dumps(
                {"schema": 1, "human_evaluation": "not-evaluated", "plate": {"gcode": {"sha256": gsha}}}
            )
        )
        (self.p / "verify_slice.txt").write_text("PASS")
        h.write_text(
            f"gcode_sha={gsha}\nqualification_manifest={qm}\nqualification_manifest_sha={inv.sha(qm)}\ninventory_sha={inv.sha(self.p / inv.REPORT)}\n"
        )
        (self.p / inv.REQUEST).write_text('{"schema":1,"requested":{"clip":2}}')
        spy = self.p / "device-access"
        conf = self.p / "test.env"
        conf.write_text(f'touch "{spy}"\n')
        fake = self.p / "curl"
        fake.write_text(f'#!/bin/sh\ntouch "{spy}"\nexit 97\n')
        fake.chmod(0o755)
        env = dict(
            os.environ,
            PATH=str(self.p) + ":" + os.environ["PATH"],
            PRUSALINK_ENV=str(conf),
            APPROVED="1",
            FORCE="1",
        )  # isolated synthetic guard fixture only
        for opts in ([], ["--start"]):
            r = subprocess.run(
                [HERE.parent / "send/send.sh", *opts, self.p / inv.GCODE],
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=8,
            )
            self.assertEqual(r.returncode, 19, r.stdout + r.stderr)
            self.assertFalse(spy.exists())
            self.assertFalse((self.p / "sent.json").exists())


if __name__ == "__main__":
    unittest.main()
