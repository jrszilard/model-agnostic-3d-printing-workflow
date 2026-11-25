# FDM Joinery — qualified patterns

## QUALIFIED JOINT REGISTRY

> **`parts/_lib/joints.py` is authoritative.** This table is generated from it. Never re-type a
> measure into a generator — `from joints import SAMPLES` and read it, so "add a double dovetail
> with the waves" resolves to a lookup instead of a reconstruction from this prose.
>
> - **Build geometry** with `parts/_lib/joint_builders.py` (count-parameterised, retention
>   attached by construction, rule R1 enforced at build time).
> - **Declare it** in `spec.yaml` under `joints:`; `platform/pipeline/verify/joint_check.py`
>   checks the sample exists, is still usable, and matches your material/printer/orientation.
> - **Regenerate this table** with `python3 parts/_lib/render_registry.py`.
>
> "Sample" = the physical coupon part number debossed on the evidence part. A sample is a
> *(pattern × context)* qualification — the numbers are only valid in the context column.

<!-- BEGIN GENERATED REGISTRY — edit parts/_lib/joints.py, then run render_registry.py -->

> Generated from `parts/_lib/joints.py` — **do not hand-edit this block.**
> A sample is a *(pattern × context)* qualification: the numbers below are only
> valid in the context column. `qualified_in(PATTERN, CONTEXT)` returns nothing
> for an unproven material rather than handing back these values.

**Materials on record**

| Material | Class | Creep | Friction on glass | Profile |
|---|---|---|---|---|
| **PLA** | rigid | yes-under-sustained-load | low | qualified |
| **PCTG** | rigid | less-than-PLA | low | available-no-joint-coupon |
| **PETG** | rigid | less-than-PLA | low | qualified |
| **TPU-95A** | compliant | high-in-free-flexure | high | starter-no-joint-coupon |
| **SUNLU-TPU-95A** | compliant | high-in-free-flexure | high | starter-no-joint-coupon |

**QUALIFIED**

| Sample | Pattern | Context | Infill | Key measures | Behaviour | Basis | Print | Use when |
|---|---|---|---|---|---|---|---|---|
| **RK3A** | BANDED_TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | apex_flat 0.6 · band_len 3 · band_n 3 · band_pitch 12 · edge_chamfer 0.5 · interference 0 · key_len 36 · mid_w 5.6 · ramp_len 2 · tight_zone 9 · tip_w 5.3 | tight-hand-removable | bracketed | flat | THE PRODUCTION RIM KEY. One key tying three stacked members (rod-rim-rod), against females printed at 230C. |
| **TLRG** | BAYONET_LOCK | core-one/PLA/0.4/0.20 | 15% | bore_d 15.7 · lug_arc 34 · lug_cham 1.6 · lug_h 3.2 · lug_r 1.9 · run_h 3.3 · seat_h 2.7 · socket_h 10.8 · spig_d 15.4 · spig_h 11 · turn_deg 62 | tight-hand-removable | bracketed | vertical | THE LED COLUMN MOUNT. A slender column into a base, where a central key would be too small to carry a wire channel. |
| **RCW95** | CLEAT | core-one/PLA/0.4/0.20 | 15% | bar_d 8 · bar_len 48 · gap 9.5 | pass-perfect | single-coupon | standing | Rope tie-off on a tower post, 8mm sisal. |
| **QH2** | DOVETAIL | core-one/PLA/0.4/0.20 | 15% | width_clearance 0.2 · depth_clearance 0.1 | pass-perfect | bracketed | flat | Horizontal dovetail slides. The studio baseline cross-section. |
| **VC05** | DOVETAIL | core-one/PLA/0.4/0.20 | 100% | width_clearance 0.05 · depth_clearance 0.05 | snug | in-service | standing | Long-lever vertical joints (holds a 180mm lever square). |
| **LD6** | MARKING | core-one/PLA/0.4/0.20 | 15% | effective_depth 1 · size 6 · weight bold | pass-perfect | single-coupon | flat | THE BASELINE for every printed part ID where the face permits it. |
| **TR6-1** | PUSH_TAB | core-one/PETG/0.4/0.20 | 15% | body_clear 0.25 · end_margin 4 · groove_clear 0.15 · pitch_max 16 · rib_base 0.8 · rib_past_drawn 0.14 · rib_past_sliced 0.05 · slack 0.5 · strip_t 0.8 · strip_w 2.344 · tab_d 3 · tab_l 4 · tab_w 1.34 | snug | single-coupon | face-down | Every touge road line in PETG, and any flush strip pressed into a face-down PETG part. |
| **TR7-2** | RIBBED_SOCKET | core-one/PETG/0.4/0.15 | 15% | body_clear 0.25 · peg_d 4 · rib_base 0.8 · rib_past_drawn 0.14 · rib_past_sliced 0.05 · rib_ramp 0.8 · rib_sink 0.15 · rib_start 0.3 · ribs 4 | snug | bracketed | face-down | Each guardrail post socket on the touge road; a post or peg in a blind vertical PETG socket that must stay put and still go in by hand. |
| **RHG84** | ROPE_HOLE | core-one/PLA/0.4/0.20 | 15% | hole_d 8.4 · min_wall 1.8 · rope_nom 8 · section_t 12 | pass-perfect | single-coupon | flat | Every rope hole in a 12mm rim section. |
| **QZ** | SHOULDER_RATCHET | core-one/PLA/0.4/0.20 | 15% | pitch 2.4 · groove_w 1.8 · land 0.6 · depth 0.2 · phase 1.2 | pass-perfect | cycled(10) | flat | Retention on dovetail slides that HAVE compression shoulders (style A). |
| **TR8-3** | SNAP_TAB_HOLDER | core-one/PETG/0.4/0.20 | 15% | body_clear 0.25 · lip 1 · preload 0.6 · root_r_in 1 · root_r_out 4 · side_rib_past_sliced 0.15 · tab_clear 0.5 · tab_l 27 · tab_t_root 2.8 · tab_t_tip 1.6 · tab_w 12 | tight-hand-removable | single-coupon | face-down | The touge road's 2 x AA box (68.54 x 34.56 x 18.9) hung cover-down under the road; the starting point for any bought box clicked in under a face-down PETG part. |
| **PG51** | SPIRAL_DOWEL | core-one/PLA/0.4/0.20 | 15% | peg_d 5.1 · bore_d 5 · interference 0.1 · length 22 · groove_depth 0.45 | snug | bracketed | vertical | Legacy v1-compatible parts with existing round bores (PCC2ER). Superseded by TK10/TK12 for NEW extensions, 2026-07-24. |
| **TF** | TRIANGLE_CHANNEL | core-one/PLA/0.4/0.20 | 15% | base_w 5.6 · height 4.85 · depth 12 · skin 1.575 · section_t 8 | pass-perfect | bracketed | flat | Every triangle-key rail end. THE universal extension interface. |
| **TFB** | TRIANGLE_CHANNEL | core-one/PLA/0.4/0.20 | 15% | base_w 5.912 · height 5.12 · depth 11 · skin 3.04 · section_t 12 | tight-hand-removable | bracketed | vertical | A BLIND vertical socket — the plinth. One rung above TFV, and the rung is bought by the BLINDNESS, not by the surround. |
| **TFH** | TRIANGLE_CHANNEL | core-one/PLA/0.4/0.20 | 15% | base_w 5.704 · height 4.94 · depth 12 · skin 4.53 · section_t 14 | tight-hand-removable | bracketed | flat | A BLIND horizontal channel — a rod end, a socket you must pull back out of. Not for a through channel: that is plain TF. |
| **TFV** | TRIANGLE_CHANNEL | core-one/PLA/0.4/0.20 | 15% | base_w 5.808 · height 5.03 · depth 12 · skin 3.1 · section_t 12 | tight-hand-removable | bracketed | vertical | A VERTICAL socket in RIM-WEIGHT stock. Corner-fill closes a vertical triangle and there is no bridging sag to reopen it. |
| **TK10** | TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | mid_w 5.7 · tip_w 5.3 · interference 0.1 · key_len 22 · taper_len 6 · tight_zone 10 | tight-hand-removable | bracketed | flat | THE DEFAULT. Serviceable / disassemblable joints. |
| **TK12** | TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | mid_w 5.72 · tip_w 5.3 · interference 0.12 · key_len 22 · taper_len 6 · tight_zone 10 | tight-pliers | bracketed | flat | Semi-permanent joints. |
| **VOZ30E** | TWIN_DOVETAIL | core-one/PLA/0.4/0.20 | 15% | neck 6 · crest 9 · proud 3 · width_clearance 0.3 · depth_clearance 0.2 | pass-perfect | cycled(10) | flat | THE corner<->upright vertical joint (v2). Twin fins at +/-7, 0.30 width / 0.20 depth clearance, with the VW20E two-station end detent. |
| **TR3-1** | T_SLOT | core-one/PLA/0.4/0.20 | 15% | channel_h 1.4 · channel_w 9.14 · gap 0.1 · line_w 2.344 · lip 0.8 | snug | bracketed | face-down | Every touge road line, straight or curved, with a TR3S-8 strip. |
| **TR3S-8** | T_STRIP | core-one/SUNLU-TPU-95A/0.4/0.10 | 100% | flange_t 0.8 · flange_w 7.14 · foot_chamfer 0.2 · height 2.2 · line_w 2.344 | snug | bracketed | flange-down | The line strip for every TR3-1 slot, straight and curved (Justin, 2026-10-08: "let's do the straight lines in TPU to keep the look consistent"). |
| **FXW** | WAVE_TRAIN | core-one/PLA/0.4/0.20 | 15% | amp 0.3 · width 1.8 · pitch 2.4 | pass-perfect | single-coupon | flat | OPEN lap / corner joints ONLY, where the parts lift apart perpendicular to travel so the ridges can cam. NOT valid inside a captured joint at any amplitude yet. |
| **VW20E** | WAVE_TRAIN | core-one/PLA/0.4/0.20 | 15% | amp 0.2 · width 1.8 · pitch 2.4 | pass-perfect | cycled(10) | flat | THE captured-joint retention. Free travel, then interlock in the last 3.6mm of insertion. Two stations at the male's TRAILING end. |

**COUPON-GATE**

| Sample | Pattern | Context | Infill | Key measures | Behaviour | Basis | Print | Use when |
|---|---|---|---|---|---|---|---|---|
| **TR20** | TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | mid_w 5.6 · tip_w 5.3 · interference 0.2 · key_len 22 · taper_len 6 · tight_zone 10 | unknown | unproven | flat | Ribbed alternate: line-to-line body + raised face beads. Wider forgiveness band than the rigid ladder if it proves out. |
| **TR30** | TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | mid_w 5.6 · tip_w 5.3 · interference 0.3 · key_len 22 · taper_len 6 · tight_zone 10 | unknown | unproven | flat | Ribbed alternate: line-to-line body + raised face beads. Wider forgiveness band than the rigid ladder if it proves out. |

**REFERENCE**

| Sample | Pattern | Context | Infill | Key measures | Behaviour | Basis | Print | Use when |
|---|---|---|---|---|---|---|---|---|
| **RK3B** | BANDED_TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | apex_flat 0.6 · band_len 3 · band_n 3 · band_pitch 12 · edge_chamfer 0.5 · interference -0.1 · key_len 36 · mid_w 5.5 · ramp_len 2 · tight_zone 9 · tip_w 5.3 | loose | single-coupon | flat | Loose-end boundary of the RKL bracket. Not selected. |
| **TLRE** | BAYONET_LOCK | core-one/PLA/0.4/0.20 | 15% | bore_d 15.7 · lug_arc 34 · lug_cham 1.6 · lug_h 3.2 · lug_r 1.9 · run_h 3.3 · seat_h 2.9 · socket_h 10.8 · spig_d 15.4 · spig_h 11 · turn_deg 62 | loose | single-coupon | vertical | → TLRG |
| **TLRF** | BAYONET_LOCK | core-one/PLA/0.4/0.20 | 15% | bore_d 15.7 · lug_arc 34 · lug_cham 1.6 · lug_h 3.2 · lug_r 1.9 · run_h 3.3 · seat_h 2.8 · socket_h 10.8 · spig_d 15.4 · spig_h 11 · turn_deg 62 | loose | single-coupon | vertical | → TLRG |
| **TR6-2** | PUSH_TAB | core-one/PETG/0.4/0.20 | 15% | body_clear 0.25 · end_margin 4 · groove_clear 0.15 · pitch_max 16 · rib_base 0.8 · rib_past_drawn 0.22 · rib_past_sliced 0.1 · slack 0.5 · strip_t 0.8 · strip_w 2.344 · tab_d 3 · tab_l 4 · tab_w 1.34 | unknown | single-coupon | face-down | — |
| **TR7-3** | RIBBED_SOCKET | core-one/PETG/0.4/0.15 | 15% | body_clear 0.25 · peg_d 4 · rib_base 0.8 · rib_past_drawn 0.22 · rib_past_sliced 0.1 · rib_ramp 0.8 · rib_sink 0.15 · rib_start 0.3 · ribs 4 | unknown | single-coupon | face-down | — |
| **RHG87** | ROPE_HOLE | core-one/PLA/0.4/0.20 | 15% | hole_d 8.7 · min_wall 1.65 · rope_nom 8 · section_t 12 | loose | single-coupon | flat | → RHG84 |
| **PG49** | SPIRAL_DOWEL | core-one/PLA/0.4/0.20 | 15% | peg_d 4.9 · bore_d 5 · interference -0.1 · length 22 · groove_depth 0.45 | loose | single-coupon | vertical | → PG51 |
| **PG50** | SPIRAL_DOWEL | core-one/PLA/0.4/0.20 | 15% | peg_d 5 · bore_d 5 · interference 0 · length 22 · groove_depth 0.45 | loose | single-coupon | vertical | → PG51 |
| **PG52** | SPIRAL_DOWEL | core-one/PLA/0.4/0.20 | 15% | peg_d 5.2 · bore_d 5 · interference 0.2 · length 22 · groove_depth 0.45 | unknown | single-coupon | vertical | → PG51 |
| **PR51** | SPIRAL_DOWEL | core-one/PLA/0.4/0.20 | 15% | peg_d 5.1 · bore_d 5 · interference 0.1 · length 22 · groove_depth 0.45 | unknown | single-coupon | vertical | → PG51 |
| **PR53** | SPIRAL_DOWEL | core-one/PLA/0.4/0.20 | 15% | peg_d 5.3 · bore_d 5 · interference 0.3 · length 22 · groove_depth 0.45 | snug | single-coupon | vertical | → PG51 |
| **PR55** | SPIRAL_DOWEL | core-one/PLA/0.4/0.20 | 15% | peg_d 5.5 · bore_d 5 · interference 0.5 · length 22 · groove_depth 0.45 | unknown | single-coupon | vertical | → PG51 |
| **TK05** | TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | mid_w 5.65 · tip_w 5.3 · interference 0.05 · key_len 22 · taper_len 6 · tight_zone 10 | loose | single-coupon | flat | Loose-end boundary of the R3 bracket. Not selected. |
| **TK15** | TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | mid_w 5.75 · tip_w 5.3 · interference 0.15 · key_len 22 · taper_len 6 · tight_zone 10 | too-tight | single-coupon | flat | TIGHT-END BOUNDARY REFERENCE — keep, do not ship. |
| **VDF50** | TWIN_DOVETAIL | core-one/PLA/0.4/0.20 | 100% | neck 6 · crest 9 · proud 3 · width_clearance 0.5 · depth_clearance 0.3 | loose | single-coupon | flat | Corner<->upright vertical joint v2 (supersedes VC05). |
| **VOZ40E** | TWIN_DOVETAIL | core-one/PLA/0.4/0.20 | 15% | neck 6 · crest 9 · proud 3 · width_clearance 0.4 · depth_clearance 0.25 | loose | single-coupon | flat | Loose-end boundary of the R4 clearance bracket. Not selected. |
| **TR3S-7** | T_STRIP | core-one/SUNLU-TPU-95A/0.4/0.10 | 100% | flange_t 0.7 · flange_w 7.14 · foot_chamfer 0.2 · height 2.2 · line_w 2.344 | loose | single-coupon | flange-down | — |
| **VW10E** | WAVE_TRAIN | core-one/PLA/0.4/0.20 | 15% | amp 0.1 · width 1.8 · pitch 2.4 | loose | single-coupon | flat | Loose-end boundary of the R4 amplitude bracket. Not selected — VOM5 lost to VOM4, so 0.20 over two stations was not too stiff and 0.10 gave up grip for nothing. |

**SUPERSEDED**

| Sample | Pattern | Context | Infill | Key measures | Behaviour | Basis | Print | Use when |
|---|---|---|---|---|---|---|---|---|
| **RK3** | BANDED_TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | apex_flat 0.6 · band_len 3 · band_n 3 · band_pitch 12 · edge_chamfer 0.5 · interference 0.1 · key_len 36 · mid_w 5.7 · ramp_len 2 · tight_zone 9 · tip_w 5.3 | tight-hand-removable | bracketed | flat | → RK3A |
| **IX35** | DOVETAIL | core-one/PLA/0.4/0.20 | 15% | width_clearance 0.35 · depth_clearance 0.45 | snug | single-coupon | vertical | Legacy: the buried tongue-and-groove extension (retention style B). |
| **QH3** | DOVETAIL | core-one/PLA/0.4/0.20 | 15% | width_clearance 0.3 · depth_clearance 0.15 | snug | single-coupon | flat | → QH2 |
| **QH4** | DOVETAIL | core-one/PLA/0.4/0.20 | 15% | width_clearance 0.4 · depth_clearance *not recorded* | loose | single-coupon | flat | → QH2 |
| **QV5** | DOVETAIL | core-one/PLA/0.4/0.20 | 15% | width_clearance 0.5 · depth_clearance 0.3 | loose | single-coupon | standing | → VC05 |
| **QV6** | DOVETAIL | core-one/PLA/0.4/0.20 | 15% | width_clearance 0.6 · depth_clearance *not recorded* | loose | single-coupon | standing | → VC05 |
| **QV8** | DOVETAIL | core-one/PLA/0.4/0.20 | 15% | width_clearance 0.8 · depth_clearance *not recorded* | loose | single-coupon | standing | → VC05 |
| **VC10** | DOVETAIL | core-one/PLA/0.4/0.20 | 100% | width_clearance 0.1 · depth_clearance 0.1 | loose | single-coupon | standing | → VC05 |
| **VC15** | DOVETAIL | core-one/PLA/0.4/0.20 | 100% | width_clearance 0.15 · depth_clearance 0.15 | loose | single-coupon | standing | → VC05 |
| **VC25** | DOVETAIL | core-one/PLA/0.4/0.20 | 100% | width_clearance 0.25 · depth_clearance 0.2 | loose | single-coupon | standing | → VC05 |
| **VC35** | DOVETAIL | core-one/PLA/0.4/0.20 | 100% | width_clearance 0.35 · depth_clearance 0.3 | loose | single-coupon | standing | → VC05 |
| **PF** | TRIANGLE_CHANNEL | core-one/PLA/0.4/0.20 | 15% | base_w 5 · height 5 · depth 12 · skin 1.5 · section_t 8 | pass-perfect | single-coupon | flat | Legacy round-bore rail ends (PCC2ER v1 compatibility). |
| **TK00** | TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 15% | mid_w 5.6 · tip_w 5.3 · interference 0 · key_len 22 · taper_len 6 · tight_zone 10 | loose | single-coupon | flat | → TK10 |
| **TKN05** | TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | mid_w 5.55 · tip_w 5.3 · interference -0.05 · key_len 22 · taper_len 6 · tight_zone 10 | loose | bracketed | flat | → TK10 |
| **TKN10** | TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | mid_w 5.5 · tip_w 5.3 · interference -0.1 · key_len 22 · taper_len 6 · tight_zone 10 | tight-hand-removable | bracketed | flat | → TK10 |
| **TKN15** | TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | mid_w 5.45 · tip_w 5.3 · interference -0.15 · key_len 22 · taper_len 6 · tight_zone 10 | loose | bracketed | flat | → TK10 |
| **VDF30** | TWIN_DOVETAIL | core-one/PLA/0.4/0.20 | 100% | neck 6 · crest 9 · proud 3 · width_clearance 0.3 · depth_clearance 0.2 | unknown | single-coupon | flat | Corner<->upright vertical joint v2 (supersedes VC05). |
| **VDF40** | TWIN_DOVETAIL | core-one/PLA/0.4/0.20 | 100% | neck 6 · crest 9 · proud 3 · width_clearance 0.4 · depth_clearance 0.25 | unknown | single-coupon | flat | Corner<->upright vertical joint v2 (supersedes VC05). |

**REJECTED**

| Sample | Pattern | Context | Infill | Key measures | Behaviour | Basis | Print | Use when |
|---|---|---|---|---|---|---|---|---|
| **RK2** | BANDED_TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | apex_flat 0.6 · band_len 6 · band_n 2 · band_pitch 12 · edge_chamfer 0.5 · interference 0.1 · key_len 36 · mid_w 5.7 · ramp_len 2 · tight_zone 12 · tip_w 5.3 | too-tight | single-coupon | flat | → RK3A |
| **RK4** | BANDED_TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | apex_flat 0.6 · band_len 4 · band_n 3 · band_pitch 12 · edge_chamfer 0.5 · interference 0.1 · key_len 36 · mid_w 5.7 · ramp_len 2 · tight_zone 12 · tip_w 5.3 | too-tight | single-coupon | flat | → RK3A |
| **RK6** | BANDED_TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | apex_flat 0.6 · band_len 6 · band_n 3 · band_pitch 12 · edge_chamfer 0.5 · interference 0.1 · key_len 36 · mid_w 5.7 · ramp_len 2 · tight_zone 18 · tip_w 5.3 | too-tight | single-coupon | flat | → RK3A |
| **RKF** | BANDED_TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | apex_flat 0.6 · band_len 24 · band_n 1 · band_pitch 12 · edge_chamfer 0.5 · interference 0.1 · key_len 36 · mid_w 5.7 · ramp_len 6 · tight_zone 24 · tip_w 5.3 | too-tight | single-coupon | flat | → RK3A |
| **TLRB** | BAYONET_LOCK | core-one/PLA/0.4/0.20 | 15% | bore_d 15.7 · lug_arc 34 · lug_cham 1.6 · lug_h 3.2 · lug_r 1.9 · run_h 3.3 · seat_h 2.4 · socket_h 10.8 · spig_d 15.4 · spig_h 11 · turn_deg 62 | unknown | single-coupon | vertical | → TLRG |
| **TLRC** | BAYONET_LOCK | core-one/PLA/0.4/0.20 | 15% | bore_d 15.7 · lug_arc 34 · lug_cham 1.6 · lug_h 3.2 · lug_r 1.9 · run_h 3.3 · seat_h 2 · socket_h 10.8 · spig_d 15.4 · spig_h 11 · turn_deg 62 | unknown | single-coupon | vertical | → TLRG |
| **TLRH** | BAYONET_LOCK | core-one/PLA/0.4/0.20 | 15% | bore_d 15.7 · lug_arc 34 · lug_cham 1.6 · lug_h 3.2 · lug_r 1.9 · run_h 3.3 · seat_h 2.8 · socket_h 10.8 · spig_d 15.4 · spig_h 11 · turn_deg 62 | unknown | single-coupon | vertical | → TLRG |
| **LBK** | DOVETAIL | core-one/PLA/0.4/0.20 | 15% | width_clearance -0.1 · depth_clearance 0.1 | too-tight | single-coupon | flat | Butterfly (bowtie) closure keys tying two flat-printed plates together ACROSS their bond plane, where a direct snap cannot print (both bond faces are bed faces). Presses in snap-tight; the flares block plate separation. First use: the leaf cartridge halves whose female dovetail must grip the LSR rail. |
| **LSR** | DOVETAIL | core-one/PLA/0.4/0.20 | 15% | width_clearance 0.2 · depth_clearance 0.1 | loose | single-coupon | flat | Leaf-scale spine rail: a full-height sliding dovetail joining a 5mm bonded two-skin stack to its 9mm spine bar, both members printed flat. Replaces a glue-only butt joint (social-media-sign middle leaf). |
| **QR** | DOVETAIL | core-one/PLA/0.4/0.20 | 15% | width_clearance 0.2 · depth_clearance 0.1 | unknown | single-coupon | flat | → QZ |
| **QV4** | DOVETAIL | core-one/PLA/0.4/0.20 | 15% | width_clearance 0.4 · depth_clearance *not recorded* | too-tight | single-coupon | standing | → VC05 |
| **LD3** | MARKING | core-one/PLA/0.4/0.20 | 15% | effective_depth 0.4 · size 3 · weight regular | too-tight | single-coupon | flat | → LD6 |
| **RHG80** | ROPE_HOLE | core-one/PLA/0.4/0.20 | 15% | hole_d 8 · min_wall 2 · rope_nom 8 · section_t 12 | too-tight | single-coupon | flat | → RHG84 |
| **RHG82** | ROPE_HOLE | core-one/PLA/0.4/0.20 | 15% | hole_d 8.2 · min_wall 1.9 · rope_nom 8 · section_t 12 | too-tight | single-coupon | flat | → RHG84 |
| **PG46** | SPIRAL_DOWEL | core-one/PLA/0.4/0.20 | 15% | peg_d 4.6 · bore_d 5 · interference -0.4 · length 22 · groove_depth 0.45 | loose | single-coupon | vertical | → PG51 |
| **PG48** | SPIRAL_DOWEL | core-one/PLA/0.4/0.20 | 15% | peg_d 4.8 · bore_d 5 · interference -0.2 · length 22 · groove_depth 0.45 | loose | single-coupon | vertical | → PG51 |
| **TFX6** | TRIANGLE_CHANNEL | core-one/PLA/0.4/0.20 | 15% | base_w 5.6 · height 4.85 · depth 12 · skin 1.575 · section_t 8 | unknown | single-coupon | flat | → TFH |
| **TFX8** | TRIANGLE_CHANNEL | core-one/PLA/0.4/0.20 | 15% | base_w 5.6 · height 4.85 · depth 12 · skin 1.575 · section_t 8 | unknown | single-coupon | flat | → TFH |
| **TK30** | TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | mid_w 5.9 · tip_w 5.3 · interference 0.3 · key_len 22 · taper_len 6 · tight_zone 10 | too-tight | single-coupon | flat | → TK10 |
| **TK45** | TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | mid_w 6.05 · tip_w 5.3 · interference 0.45 · key_len 22 · taper_len 6 · tight_zone 10 | too-tight | single-coupon | flat | → TK10 |
| **TK60** | TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | mid_w 6.2 · tip_w 5.3 · interference 0.6 · key_len 22 · taper_len 6 · tight_zone 10 | too-tight | single-coupon | flat | → TK10 |
| **TS45** | TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | mid_w 6.05 · tip_w 5.3 · interference 0.45 · key_len 22 · taper_len 6 · tight_zone 10 | too-tight | single-coupon | flat | → TK10 |
| **TS70** | TRIANGLE_KEY | core-one/PLA/0.4/0.20 | 100% | mid_w 6.3 · tip_w 5.3 · interference 0.7 · key_len 22 · taper_len 6 · tight_zone 10 | too-tight | single-coupon | flat | → TK10 |
| **VDF10** | TWIN_DOVETAIL | core-one/PLA/0.4/0.20 | 100% | neck 6 · crest 9 · proud 3 · width_clearance 0.1 · depth_clearance 0.1 | too-tight | single-coupon | flat | Corner<->upright vertical joint v2 (supersedes VC05). |
| **VDF20** | TWIN_DOVETAIL | core-one/PLA/0.4/0.20 | 100% | neck 6 · crest 9 · proud 3 · width_clearance 0.2 · depth_clearance 0.15 | too-tight | single-coupon | flat | Corner<->upright vertical joint v2 (supersedes VC05). |
| **VOZ30W** | TWIN_DOVETAIL | core-one/PLA/0.4/0.20 | 100% | neck 6 · crest 9 · proud 3 · width_clearance 0.3 · depth_clearance 0.2 | too-tight | single-coupon | flat | → VOZ30E |
| **VOZ40W** | TWIN_DOVETAIL | core-one/PLA/0.4/0.20 | 100% | neck 6 · crest 9 · proud 3 · width_clearance 0.4 · depth_clearance 0.25 | too-tight | single-coupon | flat | → VOZ30E |
| **VW20** | WAVE_TRAIN | core-one/PLA/0.4/0.20 | 100% | amp 0.2 · width 1.8 · pitch 2.4 | too-tight | single-coupon | flat | — |

**Learned rules** — full structure in `parts/_lib/rules.py`. The `naive fix`
column is the trap: what you would otherwise reach for, and why it fails.

| Rule | Scope | Gated | What actually governs it | The naive fix that fails |
|---|---|---|---|---|
| **R1** Captured retention is governed by FACE interference, not depth clearance | joinery | yes (`joints.check_retention`) | ridge amplitude MINUS the nominal gap between the mating flat faces — but see R1b: this sets the PER-STATION force, and station count multiplies it | Compare the ridge amplitude against the joint's depth clearance and call it compliant if it is smaller. Those are DIFFERENT SURFACE PAIRS: on the VD twin dovetail the depth clearance is fin-crest-to-groove-roof slack, while the flat faces carrying the wave train meet at a ZERO gap. Raising depth clearance 0.20->0.25 changed nothing, which is the proof. |
| **R1b** Station count probably governs a captured train, not amplitude — CONFOUNDED | joinery | yes (`joints.check_retention`) | stations engaged simultaneously x per-station interference; with pitch-matched trains every station cams at once, so force scales with N | Reduce the ridge amplitude when a detented joint will not go together. That trades away the grip you wanted and does not address the cause. VD R4 ran the SAME amp 0.20 against the SAME zero face gap and it fit BEST — the only change was 8 stations over 18mm becoming 2 over 3.6mm. The halved-amplitude arm (0.10) LOST: it gave up grip for nothing. |
| **R2** Fits do NOT transfer across print orientations | joinery | yes (`joints.check_orientation`) | the print orientation of each mating surface | Reuse a clearance that passed on a coupon after reorienting the part. Standing walls print true plus elephant foot; flat-printed overhung flanks sag UNDERSIZE; bed-face voids squish narrow at the mouth; horizontal bore roofs sag. Same numbers, different orientation, different joint. |
| **R3** Fits do NOT transfer across materials or printers | joinery | yes (`joints.check_context`) | the (printer, material, nozzle, layer height) the measure was proven on | Carry a PLA clearance into PCTG because 'both are rigid'. A sample is (pattern x context); outside its context it is unproven, not merely riskier. |
| **R4** Refer to qualified joints by SAMPLE NUMBER | joinery | yes (`joint_check.evaluate_joints`) | whether the geometry is read from the registry or reconstructed | Describe a joint in prose ('the double dovetail with the waves') and rebuild the geometry from that description. It comes out different every time. |
| **R5** Dovetail floors and sloped walls stay SMOOTH; teeth are transverse only | joinery | advisory | whether a feature is parallel or transverse to the slide axis | Add longitudinal ribs along the dovetail to increase friction. They run parallel to the slide, so they bind it, and they mark a mating face. |
| **R6** Flat-printed insert keys beat vertical pins under bending | joinery | advisory | the angle between the layer planes and the tension plane of the load | Print a round pin vertically so it comes out truly round. It does — and its layer planes end up perpendicular to the axis, so bending loads the layers in tension, FDM's weakest direction. |
| **R7** Entry and mouth chamfers are free | joinery | advisory | geometry at the first millimetre of engagement, not the running clearance | Open up the clearance when a part will not start. That loosens the whole fit to solve a problem that lives only at the entry. |
| **R8** Identifiers never on a mating surface, and CENTRED on their face | joinery | yes (`deboss.legible_deboss`) | text center position, and whether the face is longer than the label | Shrink the text until it fits, or tuck it near an edge. `legible_deboss` y is the text CENTER, so edge-adjacent placement clips it — three coupons running. |
| **LEVER-SCALE** A clearance qualified on a coupon is not qualified for a long lever | measurement | yes (`joints.check_lever_scale`) | slack multiplied by the engagement-to-length ratio | Promote a coupon-snug clearance straight into production. QV5 was PASS_SNUG on a short coupon and showed ~0.6mm of slack on the real 180mm upright — pressed to one side, all the slack appears opposite. |
| **SCALE-CONTINUITY** An extension continues ONE parent scale, at that scale's datum | measurement | advisory | the parent's scale value at the MATING FACE, and that scale's units | Copy the parent's graphics onto the extension. The assembled ruler then reads 0..180 and restarts at 50 — useless for the one thing it exists to do. And the PCC2 base is not even one ruler: +X is metric, +Y is IMPERIAL, the upright is metric measured up from the floor. A generic metric extension is wrong on two of the three. |
| **SPAN-MEASUREMENT** Measure a repeating pitch over a SPAN, never a single gap | measurement | advisory | per-feature error divided across n gaps, versus the total play budget | Caliper one gap and use it. A single reading gave 24.63mm; a 6-hole span gave 126.44/5 = 25.288mm — a 1 inch board. The error was 3x the ENTIRE fit budget (peg play is 0.216mm), so a four-peg part built to it could not have entered. |
| **ASSEMBLY-FRAME** Verify in the frame the part is USED in, not the one it is authored in | method | yes (`pcc2e.assert_extension`) | the composition of the authored geometry with the actual mating transform | Open the part and check it looks right. It does — in the authored frame. If the mating transform rotates or mirrors the piece, everything reads correctly on screen and wrongly on the bench. The PCC2 upright's extension mates channel-to-channel, so it is rotated 180deg in use: its checker rows, its colour phase and its DIGITS all turn over — three separate corrections, each invisible until the part was held against its mate. |
| **CONFOUNDED-PAIR** Never gauge a new part against a part that was itself modified | method | advisory | whether the reference side is in its as-printed state | Test a new male against the female you already have on the bench. QV4 'fit only after filing' — and the mating QVM had ALSO been filed, so the datum described neither part. The ladder had to restart on fresh parts. |
| **COUPON-FIRST** Fit-critical or long? Coupon the mating ends before the full part | method | advisory | cost of the print versus cost of a coupon that answers the same question | Print the whole part to find out whether the fit is right. A multi-hour print is an expensive way to learn a 0.1mm mistake. |
| **ONE-VARIABLE** One variable per coupon round, and always ship a control | method | advisory | whether exactly one thing differs between the arms, and whether a control exists to read them against | Trim a plate to save print time by dropping the 'boring' plain part. VD R3 shipped three pieces and ALL of them carried waves, so when both females jammed the dovetail clearance could not be exonerated or convicted — the round produced an unattributable failure. |
| **FOOTPRINT-NOT-ADHESION** A lost print on a small base is leverage, not weak adhesion | orientation | advisory | the moment applied to the bed contact, not the contact's bond strength | Add brim and glue after a tall part comes off the bed. It kept SOME adhesion — it did not simply fail to stick. Mass built above a small footprint plus wide toolhead moves created a rocking moment that worked the contact loose. More brim would not have fixed it. |
| **FAIL-CLOSED** An unrecognised failure must BLOCK, not shrug | process | yes (`orca_exit.classify_exit`) | whether a gate's default branch is permissive or restrictive | Classify an unmapped error code as 'unknown' and let it through, on the grounds that you cannot say what went wrong. verify-slice did exactly that: its exit table held OrcaSlicer's negative codes, the bench moved to PrusaSlicer (which returns a plain 1), and every PrusaSlicer failure since PASSED the gate — over the STALE gcode left by the previous run. |
| **NO-HABIT-BRIM** Do not add a brim by habit | process | advisory | footprint size and tippiness, not caution | Add a brim for safety. On broad flat parts it is needless edge cleanup, and a brim added for one tall coupon left an elephant-foot skirt on every flat part on the plate. |
| **STALE-ARTIFACT** A build artifact outlives the design it came from | process | advisory | whether a stale output can still satisfy the gate that guards it | Leave a superseded plate in build/ — it is only a file, and the source is clearly marked. But a sliced plate keeps its handoff.txt and its PASS verdict, so send.sh accepts it: the gate cannot tell that the DESIGN behind it was retired. RL1 v3 sat sliced and sendable for two days after its rope dimensions were superseded, and verify-slice separately passed a FAILED slice over the previous run's leftover gcode. |
| **PERPENDICULAR-RETENTION** Retain soft filament perpendicular, never through gates | retention | advisory | the assembly MOTION — a soft filament buckles when pushed lengthwise | Chase the passage clearance when a soft strip will not feed through. Four iterations went 1.82 -> 1.92 -> 2.09 -> 2.28mm against a 1.65 strip and it still would not pass: 'like pushing on rope.' No clearance value fixes buckling, and a passage wider than the filament kills the channel's own grip. |
| **LAYER-PLANE-FEATURES** Anchor discrete features into the layer plane | structure | advisory | whether the feature's strength lives in-layer or across layers | Point a small feature upward because that is the direction it works in. Upward lips are vertical wisps of stacked layers — the weakest possible orientation, and the first thing to fail on a shaking substrate. |
| **LEVERAGE** For a cantilevered mount add leverage, not grip | structure | advisory | the moment couple from the top row to the lowest bearing point | Make the hooks longer or grippier when a loaded mount rocks off. Engagement is CAPPED by the hole: a rectangular peg in a round hole is limited by its rounded corner, not its width, and narrowing the arm to buy height costs bending section and makes the flex worse. |
| **PRINT-LOAD** Rigidity in use is not rigidity during printing | structure | advisory | nozzle contact force on a growing cantilever — the lever arm grows with Z and every layer lands on a moving target | Analyse self-weight in service, find sag of 0.01-0.03mm, and conclude no support structure is needed. The print failed at 60% Z anyway. |

<!-- END GENERATED REGISTRY -->

Labeling rule (2026-07-24, twice burned): `legible_deboss` y is the TEXT CENTER — **place part
IDs centred on their face**, never near an edge.

Reusable physical-fit evidence. Do not generalize dimensions across printers/materials without a
coupon, but preserve the architecture and test method — that split is why the registry separates
`Pattern` (portable architecture) from `Sample` (context-bound numbers).

## Trapezoidal sliding-dovetail lock (the core primitive)

> **Trapezoidal sliding-dovetail lock** — a trapezoidal cross-section (a dovetail, wider at one
> face than the other) that **slides along its length** and, through the overhanging wider base,
> **captures the mating part against both directions perpendicular to the slide** (no lift, no
> spread). The slide axis is the ONLY free direction. Hold along that axis is added *separately* by
> shallow transverse zip teeth — placed by one of the two **retention styles** below. The dovetail's
> **sloped walls always stay smooth** so fit stays predictable; teeth never go on the sloped walls,
> and never run *longitudinally* (along the slide — that binds the slide and was rejected).

This is the studio's standard removable FDM joint. Qualified cross-section (Core One / Prusament
PLA / 0.4 / 0.20mm) is **PCC2 QH2: 0.2mm total width clearance, 0.10mm depth clearance**, smooth,
CAD interference 0.0mm³.

### Retention style A — compression-shoulder teeth (grooves OFF the dovetail)

Default, and the qualified one. Cut the transverse zip teeth into **broad flat compression
shoulders outside the dovetail** (see "QZ compression-shoulder ratchet" below). Requires the part
to *have* those shoulders — a thick part, or a perpendicular join whose overlapping body supplies
them. This is what the PCC2 corner (PASS_PERFECT) and the FX "laps over" extension use.

### Retention style B — tongue-and-groove (grooves ON the tongue), for THIN parts (coupon-gate)

> **Trapezoidal tongue-and-groove lock** — the variation for **thin parts inserted edge-on**, whose
> cross-section has no room for separate compression shoulders (the dovetail already fills most of
> it). The half-pitch transverse zip teeth are cut into the **tongue's own flat top face** (and the
> socket roof) instead of a shoulder. Still transverse (they zip, they do not bind), still off the
> sloped walls — only the *host surface* moves onto the tongue because there is nowhere else.

Use when a flat part must accept a sliding dovetail through its thin edge and is too thin for style
A — e.g. the photo-calibration rails (6–8mm). The tongue is **centered in the thickness** (roof +
floor) for a two-sided clamp. Status: **coupon-gate** — being validated by the IX coupon in the
extension A/B below; not yet physically qualified.

### Extension application — SPIRAL DOWEL PEGS (QUALIFIED 2026-07-24)

The FX/IX dovetail A/B for collinear rail-to-rail extension was superseded by Justin's separate-peg
redesign (support-free everywhere), then qualified through two physical rounds (jobs 32 + 33):

**Female (each rail end):** two **Ø5.0 × 12.0mm blind bores**, axis along the rail, at
**mid-thickness of an 8mm rail** (1.5mm skins above/below — the qualified context; do NOT re-use
this fit at other thicknesses without a coupon), spaced **14mm apart** (centerline ±7mm on a 28mm
rail). Small horizontal bores self-bridge — no support.

**Male (loose, reprintable):** **PG51 — Ø5.1 × 22mm** dowel, **+0.1mm diametral interference**
on full-Ø lands; **2-start helical ball-grooves** (ball R0.45, cut 0.45 deep, 9.5mm/turn pitch
over a 19mm span, 1.5mm clear of each end), ends chamfered 0.8mm. Printed **VERTICALLY** (truly
round XY cross-section) on a **Ø12 × 0.2 twist-off pad foot** (modeled per-part brim). Sliced
**SOLID (100% infill)** — sparse-infill cores snap. The grooves are the woodworking-spiral-dowel
escape path that lets an over-size pin press into the bore.

Physical bracket results: PG46/PG48 (0.4/0.2 clearance) too loose; **PG51 (+0.1 interference)
BEST**; raised-crush-rib runner-up **PR53** (body Ø4.4 + 0.45 ribs → envelope Ø5.3) works but
second — rigid lands at fine interference beat compliant ribs. Retention knobs if a future
material/profile shifts the fit: groove depth (grooved family), rib height (raised family).

**Gotcha — trapezoid inversion under a 180° flip:** a male dovetail authored in print orientation
and flipped for assembly inverts top-for-bottom. Build the print-orientation foot **wide-at-top**
so that after the flip it is wide-at-bottom and enters a wide-at-bottom socket. Verify by running
the ACTUAL built foot through the assembly transform in the assert — checking a separately-built
"correct" foot masks the bug.

## QZ compression-shoulder ratchet (PASS_PERFECT)

Qualified on Prusa Core One, Prusament PLA, 0.4mm nozzle, 0.20mm SPEED profile.

### Architecture

Keep the load-bearing sliding dovetail smooth. Put shallow alternating teeth on the **broad flat
compression shoulders outside the dovetail opening**—never on the dovetail floor or sloped walls.
The dovetail supplies alignment and normal force; the shoulder teeth supply retention.

Qualified geometry:

- Smooth dovetail baseline: 0.2mm total width clearance, 0.10mm depth clearance (PCC2 QH2).
- Transverse tooth pitch: 2.4mm.
- Asymmetric groove width: 1.8mm, leaving a 0.6mm rib/land.
- Tooth depth: 0.20mm (one layer in the qualified process).
- Opposing patterns offset 1.2mm (half pitch).
- Opposing ramps mirrored, producing zip-tie-like engagement.
- Two shoulder bands immediately outside the dovetail opening.
- CAD smooth-dovetail interference: 0.0mm³.

### Why this works

The smooth dovetail remains predictable and removable. Its seating force presses the half-pitch
shoulder patterns together, localizing friction into shallow teeth rather than over-constraining the
precision sliding faces. A failed interpretation put longitudinal ribs directly on the dovetail;
that was rejected before printing.

### Identification

Never deboss text onto a mating surface. Put the required large mirrored identifier on the bed face
of an external tab. QZTF/QZTM used 6mm bold, 1mm-deep bed-only labels.

### Coupon gate

1. First qualify the plain dovetail.
2. Print the matching toothed pair flat, all-white, without support or unnecessary brim.
3. Test unsanded: full insertion, retention, hand removal, whitening/splitting, tooth shear/debris.
4. Cycle ten times and reject consequential loosening.
5. Do not commit teeth to production until the matching coupon passes physically.

### Evidence

- QH2 plain dovetail: `PASS_PERFECT`.
- QZTF + QZTM compression teeth: `PASS_PERFECT`.
- Source: `parts/tools/photo-calibration-corner/src/photo-calibration-corner-pcc2-compression-ratchet-coupons.py`.
- Contract: `parts/tools/photo-calibration-corner/pcc2-compression-ratchet-coupons.yaml`.
- Decision: KB `2026-07-23-pcc2-compression-shoulder-zip-teeth`.
