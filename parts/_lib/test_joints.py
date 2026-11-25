"""Tests for the qualified joint registry (pure Python — no cadquery, no FreeCAD).
Run:  python3 -m unittest discover -s parts/_lib -p 'test_*.py'
"""
import os
import unittest

import joints as J
import render_registry

KB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "..", "..", "..", "..", "knowledge-base",
                                  "projects", "3d-printing", "decisions"))


class SchemaIsEnforcedAtLoad(unittest.TestCase):
    """The NOT-NULL / unknown-column discipline that replaces a database."""

    def test_missing_required_measure_raises(self):
        with self.assertRaises(J.RegistryError):
            J.Sample("XX", J.DOVETAIL, J.CORE_ONE_PLA, "qualified",
                     {"width_clearance": 0.2}, behaviour="snug")

    def test_unknown_measure_raises(self):
        with self.assertRaises(J.RegistryError):
            J.Sample("XX", J.DOVETAIL, J.CORE_ONE_PLA, "qualified",
                     {"width_clearance": 0.2, "depth_clearance": 0.1, "wibble": 1.0},
                     behaviour="snug")

    def test_unknown_material_raises(self):
        with self.assertRaises(J.RegistryError):
            J.Context("core-one", "UNOBTAINIUM", 0.4, 0.20)

    def test_unknown_status_raises(self):
        with self.assertRaises(J.RegistryError):
            J.Sample("XX", J.DOVETAIL, J.CORE_ONE_PLA, "probably-fine",
                     {"width_clearance": 0.2, "depth_clearance": 0.1}, behaviour="snug")


class RegistryIntegrity(unittest.TestCase):
    def test_every_sample_id_is_unique_and_self_named(self):
        for sid, s in J.SAMPLES.items():
            self.assertEqual(sid, s.id)

    def test_supersession_targets_resolve(self):
        for s in J.SAMPLES.values():
            if s.superseded_by:
                self.assertIn(s.superseded_by, J.SAMPLES, s.id)

    def test_nothing_is_superseded_by_a_dead_sample(self):
        for s in J.SAMPLES.values():
            if s.superseded_by:
                self.assertTrue(J.SAMPLES[s.superseded_by].usable,
                                "%s points at unusable %s" % (s.id, s.superseded_by))

    def test_qualified_samples_cite_evidence(self):
        for s in J.SAMPLES.values():
            if s.status == "qualified":
                self.assertTrue(s.evidence, "%s is qualified with no evidence" % s.id)

    @unittest.skipUnless(os.path.isdir(KB), "knowledge base not present")
    def test_evidence_files_exist_in_the_knowledge_base(self):
        for s in J.SAMPLES.values():
            for ev in s.evidence:
                self.assertTrue(os.path.exists(os.path.join(KB, ev)),
                                "%s cites missing KB decision %s" % (s.id, ev))

    def test_every_qualified_sample_names_when_to_use_it(self):
        for s in J.SAMPLES.values():
            if s.status == "qualified":
                self.assertTrue(s.use_when, "%s has no use_when" % s.id)


class MaterialAxis(unittest.TestCase):
    """A sample is (pattern x context); an unproven material must return NOTHING."""

    def test_pla_triangle_keys_are_qualified(self):
        ids = {s.id for s in J.qualified_in(J.TRIANGLE_KEY, J.CORE_ONE_PLA)}
        self.assertEqual(ids, {"TK10", "TK12"})

    def test_pctg_has_no_qualified_joint_of_any_pattern(self):
        for p in J.PATTERNS.values():
            self.assertEqual(J.qualified_in(p, J.CORE_ONE_PCTG), (),
                             "%s claims a PCTG qualification that was never couponed" % p.id)

    def test_tpu_has_no_qualified_joint(self):
        for p in J.PATTERNS.values():
            self.assertEqual(J.qualified_in(p, J.CORE_ONE_TPU95A), ())

    def test_context_mismatch_is_reported_not_silently_allowed(self):
        ok, msg = J.check_context(J.SAMPLES["TK10"], J.CORE_ONE_PCTG)
        self.assertFalse(ok)
        self.assertIn("do not transfer", msg)

    def test_every_sample_declares_a_real_context(self):
        for s in J.SAMPLES.values():
            self.assertIn(s.context.id, J.CONTEXTS)


class PetgRoadJoints(unittest.TestCase):
    """The first joints qualified in PETG (registered 2026-11-11): found by pattern and context, and
    never handed back for a material or a layer height they were not proven in (rule R3)."""

    def test_they_are_found_by_pattern_and_context(self):
        self.assertEqual([s.id for s in J.qualified_in(J.PUSH_TAB, J.CORE_ONE_PETG)], ["TR6-1"])
        self.assertEqual([s.id for s in J.qualified_in(J.RIBBED_SOCKET, J.CORE_ONE_PETG_015)], ["TR7-2"])
        self.assertEqual([s.id for s in J.qualified_in(J.SNAP_TAB_HOLDER, J.CORE_ONE_PETG)], ["TR8-3"])
        self.assertEqual(J.MATERIALS["PETG"].profile_status, "qualified")

    def test_nothing_comes_back_outside_the_context_proven(self):
        self.assertEqual(J.qualified_in(J.PUSH_TAB, J.CORE_ONE_PLA), ())
        self.assertEqual(J.qualified_in(J.RIBBED_SOCKET, J.CORE_ONE_PETG), ())      # proven at 0.15 layers only
        ok, msg = J.check_context(J.SAMPLES["TR6-1"], J.CORE_ONE_PLA)
        self.assertFalse(ok)
        self.assertIn("do not transfer", msg)

    def test_a_crush_rib_is_recorded_as_sliced_and_as_drawn(self):
        for key in ("TR6-1", "TR6-2", "TR7-2", "TR7-3"):
            m = J.SAMPLES[key].m
            self.assertLess(m["rib_past_sliced"], m["rib_past_drawn"], key)
            self.assertEqual(m["body_clear"], 0.25, key)       # PLA's 0.12 bound in PETG (tr6-i1)
        self.assertEqual(J.SAMPLES["TR6-2"].status, "reference")

    def test_the_click_tab_records_its_taper_and_preload(self):
        m = J.SAMPLES["TR8-3"].m
        self.assertGreater(m["tab_t_root"], m["tab_t_tip"])
        self.assertEqual((m["lip"], m["preload"], m["root_r_out"]), (1.0, 0.6, 4.0))


class Layout(unittest.TestCase):
    """double -> triple must be one integer, on the studio's +/-7 convention."""

    def test_two_up_is_the_studio_stations(self):
        self.assertEqual(J.stations(2), (-7.0, 7.0))

    def test_three_up_stays_symmetric_at_the_same_pitch(self):
        self.assertEqual(J.stations(3), (-14.0, 0.0, 14.0))

    def test_one_up_is_centred(self):
        self.assertEqual(J.stations(1), (0.0,))

    def test_pitch_is_preserved_between_neighbours(self):
        for n in range(2, 7):
            st = J.stations(n, pitch=14.0)
            gaps = [round(b - a, 6) for a, b in zip(st, st[1:])]
            self.assertEqual(set(gaps), {14.0})

    def test_layout_is_always_centred_on_its_center(self):
        for n in range(1, 7):
            st = J.stations(n, center=5.0)
            self.assertAlmostEqual((st[0] + st[-1]) / 2.0, 5.0)

    def test_zero_or_negative_count_raises(self):
        for bad in (0, -1, 2.5):
            with self.assertRaises(ValueError):
                J.stations(bad)

    def test_span_grows_with_count(self):
        self.assertLess(J.span_required(2, 14.0, feature_w=9.0),
                        J.span_required(3, 14.0, feature_w=9.0))


class RuleR1(unittest.TestCase):
    """Wave amplitude must stay under a captured joint's clearance."""

    def test_the_vd_r1_failure_is_caught(self):
        ok, msg = J.check_amplitude(0.30, 0.20)
        self.assertFalse(ok)
        self.assertIn("cam", msg)

    def test_compliant_amplitude_passes(self):
        self.assertTrue(J.check_amplitude(0.20, 0.25)[0])

    def test_equal_is_strict_fail_and_loose_pass(self):
        self.assertFalse(J.check_amplitude(0.20, 0.20, strict=True)[0])
        self.assertTrue(J.check_amplitude(0.20, 0.20, strict=False)[0])

    def test_open_joint_wave_is_labelled_open_only(self):
        self.assertIn("OPEN", J.SAMPLES["FXW"].use_when)

    def test_captured_wave_sample_clears_its_intended_female(self):
        amp = J.SAMPLES["VW20"].m["amp"]
        self.assertTrue(J.check_amplitude(amp, J.SAMPLES["VDF40"].m["depth_clearance"])[0])


class RetentionLocation(unittest.TestCase):
    """R1 binds on teeth INSIDE the joint envelope, not on shoulder teeth outside it."""

    def test_shoulder_ratchet_is_located_on_the_shoulder(self):
        self.assertEqual(J.SHOULDER_RATCHET.retention_location, "shoulder")

    def test_waves_default_to_captured(self):
        self.assertEqual(J.WAVE_TRAIN.retention_location, "captured")

    def test_qz_on_qh2_passes_despite_depth_exceeding_clearance(self):
        """The PASS_PERFECT corner: QZ depth 0.20 vs QH2 depth clearance 0.10."""
        ok, msg = J.check_retention(J.SAMPLES["QH2"], J.SAMPLES["QZ"])
        self.assertTrue(ok, msg)
        self.assertIn("outside", msg)

    def test_the_same_amplitude_captured_is_rejected(self):
        ok, _ = J.check_retention(J.SAMPLES["QH2"], J.SAMPLES["QZ"], location="captured")
        self.assertFalse(ok)

    def test_open_lap_override_rescues_the_qualified_fxw_application(self):
        self.assertFalse(J.check_retention(J.SAMPLES["VDF30"], J.SAMPLES["FXW"])[0])
        self.assertTrue(J.check_retention(J.SAMPLES["VDF30"], J.SAMPLES["FXW"],
                                          location="shoulder")[0])


class FaceInterference(unittest.TestCase):
    """R1 corrected by the VD R3 physical result (2026-07-24): the governing quantity is
    amp minus the MATING-FACE gap, not amp versus the joint's depth clearance."""

    def test_an_open_lap_wave_has_no_face_gap_so_captured_use_is_refused(self):
        ok, msg = J.check_retention(J.SAMPLES["VDF40"], J.SAMPLES["FXW"], location="captured")
        self.assertFalse(ok)
        self.assertIn("face_gap", msg)

    def test_the_r3_configuration_that_actually_jammed_is_now_rejected(self):
        """VW20 at face_gap 0.0 in VDF40: dc 0.25 looked generous under the OLD rule and passed
        it, yet the coupon stuck halfway. The corrected rule catches it."""
        ok, msg = J.check_retention(J.SAMPLES["VDF40"], J.SAMPLES["VW20"], location="captured")
        self.assertFalse(ok)
        self.assertIn("face interference", msg)

    def test_raising_depth_clearance_does_not_rescue_a_zero_face_gap(self):
        """The proof from the bench: VOZ30W (dc 0.20) and VOZ40W (dc 0.25) failed identically."""
        for female in ("VDF30", "VDF40", "VDF50"):
            ok, _ = J.check_retention(J.SAMPLES[female], J.SAMPLES["VW20"], location="captured")
            self.assertFalse(ok, "%s should still fail — dc is the wrong surface pair" % female)

    def test_a_real_face_gap_removes_the_interference(self):
        relieved = J.Sample("VWTEST", J.WAVE_TRAIN, J.CORE_ONE_PLA, "coupon-gate",
                            dict(amp=0.20, width=1.8, pitch=2.4, face_gap=0.20, stations=8),
                            behaviour="unknown")
        ok, msg = J.check_retention(J.SAMPLES["VDF30"], relieved, location="captured")
        self.assertTrue(ok, msg)
        self.assertIn("free travel", msg)

    def test_a_reduced_interference_is_unproven_not_qualified(self):
        light = J.Sample("VWLIGHT", J.WAVE_TRAIN, J.CORE_ONE_PLA, "coupon-gate",
                         dict(amp=0.20, width=1.8, pitch=2.4, face_gap=0.15, stations=8),
                         behaviour="unknown")
        self.assertFalse(J.check_retention(J.SAMPLES["VDF30"], light, location="captured",
                                           strict=True)[0])
        ok, msg = J.check_retention(J.SAMPLES["VDF30"], light, location="captured", strict=False)
        self.assertTrue(ok)
        self.assertIn("UNPROVEN", msg)


class ShortEndTrain(unittest.TestCase):
    """R4: the rule must separate 'proven to jam' from 'untested', or it blocks the coupon
    designed to tell R1 (interference) apart from R1b (simultaneous camming)."""

    def test_the_long_train_that_jammed_stays_blocked(self):
        ok, msg = J.check_retention(J.SAMPLES["VOZ30E"], J.SAMPLES["VW20"],
                                    location="captured", strict=False)
        self.assertFalse(ok)
        self.assertIn("8 stations", msg)

    def test_the_same_interference_over_two_stations_is_unproven_not_blocked(self):
        ok, msg = J.check_retention(J.SAMPLES["VOZ30E"], J.SAMPLES["VW20E"],
                                    location="captured", strict=False)
        self.assertTrue(ok, msg)
        self.assertIn("2 stations", msg)

    def test_r4_turned_the_unproven_branch_into_a_qualified_envelope(self):
        """2026-07-25: VOM4 x VOZ30E fit best, so the short end train is no longer merely
        unproven — it is the qualified captured retention."""
        ok, msg = J.check_retention(J.SAMPLES["VOZ30E"], J.SAMPLES["VW20E"],
                                    location="captured", strict=True)
        self.assertTrue(ok, msg)
        self.assertIn("qualified envelope", msg)

    def test_the_same_interference_over_a_long_train_is_still_blocked(self):
        """The single-variable pair: identical amp and face gap, 8 stations instead of 2."""
        ok, msg = J.check_retention(J.SAMPLES["VDF40"], J.SAMPLES["VW20"], location="captured")
        self.assertFalse(ok)
        self.assertIn("shorten the train", msg)

    def test_the_r4_arms_differ_only_in_amplitude(self):
        a, b = J.SAMPLES["VW20E"].m, J.SAMPLES["VW10E"].m
        differing = {k for k in a if a[k] != b[k]}
        self.assertEqual(differing, {"amp"}, "R4 fallback moved more than one variable")

    def test_vw20e_is_r3s_profile_with_only_the_station_count_changed(self):
        old, new = J.SAMPLES["VW20"].m, J.SAMPLES["VW20E"].m
        differing = {k for k in old if old[k] != new[k]}
        self.assertEqual(differing, {"stations"}, "R4 primary arm is not a single-variable test")

    def test_an_undeclared_station_count_is_treated_as_the_dangerous_case(self):
        vague = J.Sample("VWVAGUE", J.WAVE_TRAIN, J.CORE_ONE_PLA, "rejected",
                         dict(amp=0.20, width=1.8, pitch=2.4, face_gap=0.0, stations=None),
                         behaviour="unknown")
        self.assertFalse(J.check_retention(J.SAMPLES["VOZ30E"], vague, location="captured",
                                           strict=False)[0])

    def test_both_failed_coupons_are_recorded_with_their_evidence(self):
        for sid in ("VOZ30W", "VOZ40W", "VW20"):
            s = J.SAMPLES[sid]
            self.assertEqual(s.status, "rejected")
            self.assertEqual(s.behaviour, "too-tight")
            self.assertTrue(s.evidence)

    def test_the_one_qualified_captured_train_is_the_short_one(self):
        """R4 (2026-07-25) qualified exactly one captured wave train, and it is short."""
        captured = [s for s in J.SAMPLES.values()
                    if s.pattern.id == "WAVE_TRAIN" and s.status == "qualified"
                    and s.m.get("face_gap") is not None]
        self.assertEqual([s.id for s in captured], ["VW20E"])
        self.assertLessEqual(captured[0].m["stations"], J.QUALIFIED_STATIONS)

    def test_the_open_lap_train_still_declares_no_face_gap(self):
        self.assertIsNone(J.SAMPLES["FXW"].m.get("face_gap"))


class Lookup(unittest.TestCase):
    def test_resolve_unknown_cites_rule_r4(self):
        with self.assertRaises(KeyError) as cm:
            J.resolve("NOPE")
        self.assertIn("R4", str(cm.exception))

    def test_orientation_change_is_flagged(self):
        ok, msg = J.check_orientation(J.SAMPLES["TK10"], "vertical")
        self.assertFalse(ok)
        self.assertIn("R2", msg)


class DocMirrorsCode(unittest.TestCase):
    def test_joinery_doc_is_not_stale(self):
        with open(render_registry.DOC) as fh:
            current = fh.read()
        self.assertEqual(current, render_registry.splice(current, render_registry.render()),
                         "docs/joinery.md is stale — run: python3 parts/_lib/render_registry.py")


if __name__ == "__main__":
    unittest.main()


class Marking(unittest.TestCase):
    """Legibility is a qualified physical measure, not a style default."""

    def test_the_baseline_is_registered_with_its_evidence(self):
        ld6 = J.SAMPLES["LD6"]
        self.assertEqual(ld6.status, "qualified")
        self.assertEqual(ld6.m, {"size": 6.0, "effective_depth": 1.0, "weight": "bold"})
        self.assertTrue(ld6.evidence)

    def test_the_unreadable_measure_is_kept_as_counter_evidence(self):
        ld3 = J.SAMPLES["LD3"]
        self.assertEqual(ld3.status, "rejected")
        self.assertEqual(ld3.superseded_by, "LD6")

    def test_deboss_defaults_come_from_the_registry_not_the_function(self):
        """deboss.py imports cadquery, so assert on the source contract, not by importing it."""
        import pathlib
        src = pathlib.Path(__file__).with_name("deboss.py").read_text()
        self.assertIn('SAMPLES["LD6"]', src)
        sig = [ln for ln in src.splitlines() if "def legible_deboss" in ln][0]
        self.assertIn("size=None", sig, "legible_deboss still hardcodes its own size")


class SharedProcessDimension(unittest.TestCase):
    """Material/Context moved to process.py so fasteners and markings share them with joints."""

    def test_joints_still_re_exports_them(self):
        self.assertIs(J.CORE_ONE_PLA.mat, J.MATERIALS["PLA"])
        self.assertEqual(J.Context("core-one", "PLA", 0.4, 0.20), J.CORE_ONE_PLA)

    def test_a_material_with_only_a_starter_profile_is_printable_but_unqualified(self):
        self.assertTrue(J.MATERIALS["SUNLU-TPU-95A"].printable)
        self.assertTrue(J.MATERIALS["PLA"].printable)

    def test_advisories_warn_for_an_unqualified_starter_profile(self):
        adv = J.material_advisories(J.CORE_ONE_TPU95A)
        self.assertNotIn("FAIL", [sev for sev, _ in adv])
        self.assertIn("WARN", [sev for sev, _ in adv])

    def test_advisories_warn_on_creep_only_under_sustained_load(self):
        self.assertNotIn("creeps", " ".join(m for _, m in
                                            J.material_advisories(J.CORE_ONE_PLA)))
        self.assertIn("creeps", " ".join(m for _, m in
                                         J.material_advisories(J.CORE_ONE_PLA,
                                                               sustained_load=True)))

    def test_qualified_context_is_clean(self):
        self.assertEqual(J.material_advisories(J.CORE_ONE_PLA), [])


class EvidenceBasis(unittest.TestCase):
    """`status` says whether we CHOSE it; `basis` says how much evidence stands behind it.
    Aerospace allowables never quote a value without its basis; ours is cruder, so say so."""

    def test_basis_is_recorded_for_every_sample(self):
        for s in J.SAMPLES.values():
            self.assertIn(s.basis, J.BASES, s.id)

    def test_cycled_basis_must_state_the_cycle_count(self):
        with self.assertRaises(J.RegistryError):
            J.Sample("XX", J.DOVETAIL, J.CORE_ONE_PLA, "qualified",
                     {"width_clearance": 0.2, "depth_clearance": 0.1},
                     behaviour="snug", basis="cycled")

    def test_the_ten_cycle_ratchet_records_its_cycles(self):
        self.assertEqual(J.SAMPLES["QZ"].basis, "cycled")
        self.assertEqual(J.SAMPLES["QZ"].cycles, 10)

    def test_the_only_in_service_sample_is_the_one_gauged_on_a_real_part(self):
        self.assertEqual(J.SAMPLES["VC05"].basis, "in-service")

    def test_unknown_basis_raises(self):
        with self.assertRaises(J.RegistryError):
            J.Sample("XX", J.DOVETAIL, J.CORE_ONE_PLA, "qualified",
                     {"width_clearance": 0.2, "depth_clearance": 0.1},
                     behaviour="snug", basis="vibes")


class UnrecordedMeasures(unittest.TestCase):
    """UNKNOWN means 'the coupon had this and nobody wrote it down' — distinct from omitting
    the key, which means 'not applicable'. A known gap beats a silent one."""

    def test_unknown_is_falsey_and_prints_as_itself(self):
        self.assertFalse(J.UNKNOWN)
        self.assertEqual(repr(J.UNKNOWN), "UNKNOWN")

    def test_the_ladder_records_its_missing_depth_explicitly(self):
        for sid in ("QH4", "QV8", "QV6", "QV4"):
            self.assertIs(J.SAMPLES[sid].m["depth_clearance"], J.UNKNOWN, sid)

    def test_a_qualified_sample_may_not_carry_unrecorded_measures(self):
        with self.assertRaises(J.RegistryError):
            J.Sample("XX", J.DOVETAIL, J.CORE_ONE_PLA, "qualified",
                     {"width_clearance": 0.2, "depth_clearance": J.UNKNOWN}, behaviour="snug")

    def test_omitting_a_key_still_raises_for_a_gated_status(self):
        with self.assertRaises(J.RegistryError) as cm:
            J.Sample("XX", J.DOVETAIL, J.CORE_ONE_PLA, "reference",
                     {"width_clearance": 0.2}, behaviour="snug")
        self.assertIn("UNKNOWN", str(cm.exception))


class MatingPairs(unittest.TestCase):
    def test_mating_references_resolve(self):
        for s in J.SAMPLES.values():
            for m in s.mates_with:
                self.assertIn(m, J.SAMPLES, "%s mates with unknown %s" % (s.id, m))

    def test_mating_is_symmetric_where_declared(self):
        self.assertIn("TF", J.SAMPLES["TK10"].mates_with)
        self.assertIn("TK10", J.SAMPLES["TF"].mates_with)


class LeverScale(unittest.TestCase):
    """A coupon does not prove a lever. QV5 was coupon-SNUG and lever-LOOSE at 9x."""

    def test_no_lever_declared_is_clean(self):
        self.assertTrue(J.check_lever_scale(J.SAMPLES["VOZ30E"], None, None)[0])

    def test_a_short_arm_carries_from_the_coupon(self):
        self.assertTrue(J.check_lever_scale(J.SAMPLES["VOZ30E"], 20.0, 40.0)[0])

    def test_the_production_upright_is_flagged(self):
        """VOZ30E is cycled-basis on a 28mm stub but drives a 180mm upright on 20mm engagement."""
        ok, msg = J.check_lever_scale(J.SAMPLES["VOZ30E"], 20.0, 180.0)
        self.assertFalse(ok)
        self.assertIn("9.0x", msg)
        self.assertIn("QV5", msg)

    def test_cycling_does_not_substitute_for_scale(self):
        """Ten cycles on a coupon still says nothing about a 9x arm — different question."""
        self.assertEqual(J.SAMPLES["VOZ30E"].basis, "cycled")
        self.assertFalse(J.check_lever_scale(J.SAMPLES["VOZ30E"], 20.0, 180.0)[0])

    def test_only_in_service_clears_it(self):
        """VC05 exists BECAUSE of this failure, and was gauged on the real printed upright."""
        self.assertEqual(J.SAMPLES["VC05"].basis, "in-service")
        self.assertTrue(J.check_lever_scale(J.SAMPLES["VC05"], 20.0, 180.0)[0])


class LeverEvidenceDischarge(unittest.TestCase):
    """The first draft of check_lever_scale accepted ONLY an in-service basis, which is circular
    whenever the mating geometry just changed: it demanded a real printed part when printing one
    was the only way to make it. A gate must not block the work that would satisfy it."""

    def test_declared_evidence_discharges_the_lever(self):
        ok, msg = J.check_lever_scale(J.SAMPLES["VOZ30E"], 20.0, 180.0,
                                      lever_evidence="production-orientation coupon + twin fins")
        self.assertTrue(ok, msg)
        self.assertIn("discharged by", msg)

    def test_silence_still_warns(self):
        self.assertFalse(J.check_lever_scale(J.SAMPLES["VOZ30E"], 20.0, 180.0)[0])

    def test_the_warning_no_longer_demands_only_a_real_part(self):
        _, msg = J.check_lever_scale(J.SAMPLES["VOZ30E"], 20.0, 180.0)
        self.assertIn("or declare lever_evidence", msg)

    def test_in_service_still_clears_without_declaring_anything(self):
        self.assertTrue(J.check_lever_scale(J.SAMPLES["VC05"], 20.0, 180.0)[0])


class InfillIsPerSample(unittest.TestCase):
    """Infill is a PER-OBJECT slicer setting, so it lives on Sample, not in the shared Context:
    a joint's two halves routinely differ. Added 2026-07-25 after it changed silently across
    three VD rounds and confounded the R4 result."""

    def test_every_sample_records_the_infill_it_was_proven_at(self):
        for s in J.SAMPLES.values():
            self.assertIsNotNone(s.infill, "%s has no infill recorded" % s.id)

    def test_the_vd_confound_is_on_the_record(self):
        """R3 jammed at 100%, R4 fit at 15% — the pair is not single-variable."""
        self.assertEqual(J.SAMPLES["VW20"].infill, 100)
        self.assertEqual(J.SAMPLES["VW20E"].infill, 15)

    def test_a_joints_two_halves_may_differ(self):
        """TK10 keys were qualified at 100% against TF channels printed at 15%."""
        self.assertEqual(J.SAMPLES["TK10"].infill, 100)
        self.assertEqual(J.SAMPLES["TF"].infill, 15)
        self.assertIn("TF", J.SAMPLES["TK10"].mates_with)

    def test_infill_is_not_in_the_context_id(self):
        """Context stays the shared process dimension; infill would wrongly fragment it."""
        self.assertNotIn("infill", J.CORE_ONE_PLA.id)
