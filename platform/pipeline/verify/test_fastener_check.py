import unittest
from fastener_check import evaluate_fasteners


class FastenerCheck(unittest.TestCase):
    def captive(self):
        return {
            "id": "crown_to_frame", "method": "side-entry-captive-nut", "size": "M3", "quantity": 3,
            "receiver": {
                "nut": {"across_flats": 5.5, "thickness": 2.4},
                "pocket": {"across_flats": 5.8, "height": 2.7, "roof": 3.7},
                "entry_slit_width": 5.8, "bore_d": 3.4,
            },
            "evaluation": {"source_assertion": "generator assertion", "coupon": "clamp coupon",
                           "physical_gate": "install and hand clamp"},
        }

    def test_missing_section_is_optional(self):
        self.assertTrue(evaluate_fasteners(None)["passed"])

    def test_complete_captive_nut_passes(self):
        rep = evaluate_fasteners([self.captive()])
        self.assertTrue(rep["passed"])
        self.assertEqual(rep["rows"][0]["status"], "PASS")

    def test_captive_nut_rejects_tight_pocket(self):
        f = self.captive(); f["receiver"]["pocket"]["across_flats"] = 5.5
        rep = evaluate_fasteners([f])
        self.assertFalse(rep["passed"])
        self.assertIn("pocket", rep["rows"][0]["message"])

    def test_captive_nut_requires_coupon_and_source_assertion(self):
        f = self.captive(); del f["evaluation"]["coupon"]
        rep = evaluate_fasteners([f])
        self.assertFalse(rep["passed"])

    def test_heat_set_insert_requires_vendor_specific_pilot_coupon(self):
        f = {"id": "insert", "method": "heat-set-insert", "size": "M3", "quantity": 1,
             "receiver": {"pilot_d": 4.0, "boss_wall": 3.0},
             "evaluation": {"physical_gate": "install test"}}
        self.assertFalse(evaluate_fasteners([f])["passed"])
        f["insert_vendor"] = "vendor SKU"; f["evaluation"]["coupon"] = "three-pilot coupon"
        self.assertTrue(evaluate_fasteners([f])["passed"])

    def threaded_limiter(self):
        return {
            "id": "arm-clamp", "method": "threaded-substrate-compression-limiter",
            "size": "M4", "quantity": 2, "assembly_access": "glass side and bolt head accessible",
            "substrate": {"material": "steel arm", "thread_size": "M4", "thread_pitch": 0.7,
                          "tapped_depth": 8.0},
            "limiter": {"od": 7.0, "id": 4.3, "length": 10.75, "undercut": 0.3},
            "stack": {"under_head": 10.75}, "clearance_bore_d": 4.3,
            "evaluation": {"source_assertion": "limiter seats before screw bottoms",
                           "anti_bottom_out_assertion": "engagement remains after limiter seats",
                           "coupon": "actual arm-stack coupon",
                           "physical_gate": "torque, remove, and inspect clamp stack"},
        }

    def test_threaded_substrate_limiter_contract_is_complete(self):
        rep = evaluate_fasteners([self.threaded_limiter()])
        self.assertTrue(rep["passed"], rep["rows"])
        self.assertEqual(rep["rows"][-1]["status"], "PASS")

    def test_threaded_substrate_limiter_rejects_false_clearance_or_missing_bottom_out_proof(self):
        f = self.threaded_limiter(); f["clearance_bore_d"] = 4.0
        self.assertFalse(evaluate_fasteners([f])["passed"])
        f = self.threaded_limiter(); del f["evaluation"]["anti_bottom_out_assertion"]
        self.assertFalse(evaluate_fasteners([f])["passed"])

    def test_duplicate_ids_fail(self):
        f = self.captive()
        self.assertFalse(evaluate_fasteners([f, f.copy()])["passed"])


if __name__ == "__main__":
    unittest.main()


class MaterialContext(unittest.TestCase):
    """Fasteners share Context/Material with the joint registry: a pocket proven in PLA is not
    proven in PCTG, and nothing is proven in a material with no filament profile."""

    PLA = {"printer": "core-one", "material": "PLA", "nozzle": 0.4, "layer_h": 0.20}

    def f(self, **kw):
        base = {"id": "f1", "method": "thread-forming-screw", "size": "M3", "quantity": 2,
                "screw_vendor": "acme", "pilot_d": 2.5,
                "evaluation": {"physical_gate": "tighten, remove, retighten", "coupon": "tf-r1"}}
        base.update(kw)
        return [base]

    def statuses(self, rep):
        return [r["status"] for r in rep["rows"]]

    def test_legacy_spec_without_context_still_passes(self):
        self.assertTrue(evaluate_fasteners(self.f())["passed"])

    def test_qualified_material_passes_clean(self):
        rep = evaluate_fasteners(self.f(context=self.PLA))
        self.assertTrue(rep["passed"])
        self.assertEqual(self.statuses(rep), ["PASS"])

    def test_polymer_thread_off_material_without_coupon_fails(self):
        rep = evaluate_fasteners(self.f(context=dict(self.PLA, material="PCTG"),
                                        evaluation={"physical_gate": "g"}))
        self.assertFalse(rep["passed"])
        self.assertIn("PCTG", rep["rows"][-1]["message"])

    def test_polymer_thread_off_material_with_coupon_warns(self):
        rep = evaluate_fasteners(self.f(context=dict(self.PLA, material="PCTG")))
        self.assertTrue(rep["passed"], rep["rows"])
        self.assertIn("WARN", self.statuses(rep))

    def test_material_with_starter_profile_warns_until_couponed(self):
        rep = evaluate_fasteners(self.f(context=dict(self.PLA, material="SUNLU-TPU-95A")))
        self.assertTrue(rep["passed"])
        self.assertIn("WARN", self.statuses(rep))
        self.assertIn("off the qualified material", rep["rows"][0]["message"])

    def test_sustained_load_in_a_creeping_material_warns(self):
        rep = evaluate_fasteners(self.f(context=self.PLA, sustained_load=True))
        self.assertTrue(rep["passed"], rep["rows"])
        self.assertIn("creeps", rep["rows"][0]["message"])

    def test_unknown_material_fails(self):
        rep = evaluate_fasteners(self.f(context=dict(self.PLA, material="NYLON")))
        self.assertFalse(rep["passed"])

    def test_metal_insert_is_not_gated_on_polymer_thread_material(self):
        """A heat-set insert puts metal threads in; the polymer rule does not apply."""
        rep = evaluate_fasteners([{
            "id": "f1", "method": "heat-set-insert", "size": "M3", "quantity": 2,
            "insert_vendor": "acme", "receiver": {"pilot_d": 4.0, "boss_wall": 2.0},
            "context": dict(self.PLA, material="PCTG"),
            "evaluation": {"physical_gate": "install + pull", "coupon": "hs-r1"}}])
        self.assertTrue(rep["passed"], rep["rows"])
