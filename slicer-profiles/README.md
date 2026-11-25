# Slicer profiles (versioned)

OrcaSlicer presets, split to mirror Orca's own schema so they import directly:
`OrcaSlicer/{machine,process,filament}/*.json`. Export from OrcaSlicer and commit
here so a slice is reproducible. Headless slice recipe: see platform/pipeline/README.md.

## PrusaSlicer (the Core One bench)

`PrusaSlicer/{filament,print}/*.ini`, each `inherits =` a stock preset and overrides only
what physical prints changed. Install by copying into `~/.config/PrusaSlicer/<kind>/` and
restarting, or by selecting the parent preset in the GUI and typing the values.

**A recipe is a PAIR.** PrusaSlicer keeps temperature/flow/retraction in the *filament*
preset and speeds in the *print* preset, so loading one of them silently gives you half
the recipe. The TPU bench recipe is:

| | preset |
|---|---|
| filament | `SUNLU_TPU_95A_COREONE.ini` (Generic FLEX @COREONE + 215/210 C, 60 C bed, 2.5 mm³/s, 0.4 retract) |
| print | `TPU_020_SLOW_COREONE.ini` (0.20mm SPEED @COREONE 0.4 + 15 mm/s first layer, 30 mm/s walls) |
| print, UNTESTED | `TPU_015_COREONE_UNTESTED.ini` — 0.15 mm starting point, no coupon behind it. Read its header. |
| printer | stock `Prusa CORE One 0.4 nozzle` — the *profile*, not the fitted nozzle (see below) |

> **The fitted nozzle is the HF0.4 and always has been** (Justin, 2026-09-21). This recipe names the
> standard-0.4 *machine profile*, which is why defect 2 below never bit: the plate is sliced against
> that profile and then printed on the HF nozzle, which the printer accepts. **TPU on HF is proven
> here** — ladder-i2 printed this way and gave P8. The 2.5 mm³/s cap binds long before the nozzle
> does, so there is little to gain from an HF TPU preset even if Prusa shipped one, and it does not.
> What this recipe cannot claim is that its speeds were *qualified* on an HF hotend; they were
> measured on plates that printed on one. `send.sh` reports the profile/nozzle mismatch and does not
> block it.

`slice.sh` applies the same values as an override .ini, so a GUI slice and a headless one
match. The one setting the GUI does not need is `binary_gcode = 0`: the verify/preview
chain here is a line parser, and the printer accepts ASCII gcode either way.

### The volumetric cap is per-NOZZLE, and it is the only lever that matters for bulky TPU

Found 2026-09-17 while sizing a Pixel 6 case. The cap lives in the *filament* preset and Prusa
ships a different one per nozzle preset:

| filament preset | cap | a ~36 cm³ part |
|---|---:|---:|
| `Generic FLEX @COREONE` (0.4) | 2.5 mm³/s | **4.0 h** |
| `Generic FLEX @COREONE 0.6` | 3.5 mm³/s | 2.9 h |
| `Generic FLEX @COREONE 0.8` | 7.5 mm³/s | **1.3 h** |

This bench already knew speeds are not the lever — the 25 h cloud ran 99% flow-limited at a
measured 2.506 mm³/s and doubling infill speed bought 13 minutes. The **nozzle** is. And layer
height is free: at a binding cap, time = volume ÷ Q regardless of layer height, because speed
scales as 1/h and layer count as 1/h and they cancel.

### Two defects in the pair above, found by reading the resolved profiles

1. **`TPU_020_SLOW_COREONE.ini` leaves `gap_fill_speed` at the parent's 120 mm/s** while its walls
   run 30. Gap fill is short high-frequency strokes, the feature most likely to blob in TPU, and it
   has run at 4× the wall speed through every plate on this bench including the 25 h one.
2. **Its parent is invalid on the nozzle currently installed.** `0.20mm SPEED @COREONE 0.4`
   inherits `*C1_04*`, which declares `! nozzle_high_flow[0]`, so it will not pair with
   `Prusa CORE One HF0.4 nozzle`. Presets meant to survive a nozzle swap should inherit a
   `*C1_Shared04*` profile (the STRUCTURAL ones) instead.

### Pressure advance is OFF for every flexible filament

`*FLEX*` ships `start_filament_gcode = "M900 K0"`. Nothing on this bench has ever tuned it, and
neither has the pressure equalizer (`max_volumetric_extrusion_rate_slope_*`, stock 0) — the field
built for exactly the case of soft filament with PA disabled. Both are open one-variable
experiments, recorded in `print/TPU_015_COREONE_UNTESTED.ini`.
