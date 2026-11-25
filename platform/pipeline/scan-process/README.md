# Scan process — calibrated photographs → mesh → CAD

This is the reverse-engineering intake protocol. A ruler visible in one photo is not enough: the
scale target, camera path, lighting, and reconstruction validation must be recorded so a mesh has
traceable physical units.

## Capture target

Use `tools/photo-calibration-corner` (**photo-scale**) when an object can fit inside/along its
150 mm X/Y/Z rails. Its 10 mm checker pitch is the primary scale reference; metric/imperial ticks
are manual cross-checks. Print it in matte white with the final raised markings in matte black.

## Shoot setup

1. Put the object and target on one rigid board. If a turntable is used, rotate **both together**;
   a stationary target behind a rotating object is a moving-background failure for SfM.
2. Use diffuse, even illumination. Avoid glossy black target glare and hard shadows. Use a plain,
   non-repeating background outside the target.
3. Lock focal length/zoom, focus, exposure, and white balance. Do not mix portrait/landscape,
   zoom levels, or auto-HDR variants in one solve.
4. Place the corner so at least one known 10 mm checker and a second non-coplanar rail are visible
   in every reconstruction image. Do not cover the object’s important face with the target.
5. Capture two full elevation rings (low and high) with 60–80% adjacent-image overlap, then close
   views for occluded detail. Photograph any hidden cavity separately; stop and scan it rather than
   inventing freeform geometry.

## Folder contract

```
vendor/scans/<subject>/<YYYY-MM-DD>/
  raw/                 # untouched camera originals
  capture.yaml         # camera, lens/focal length, lighting, target, operator
  selected/            # chosen reconstruction frames, copied not renamed originals
  mesh/                # raw + cleaned mesh; never overwrite raw
  measurements.csv     # caliper anchors and 10mm target scale checks
  README.md            # what was visible, occlusions, reconstruction verdict
```

`capture.yaml` must name the photo-scale variant, its measured checker pitch, camera/app, image
count, turntable/co-motion choice, and any camera settings that were locked.

## Mesh acceptance before CAD

- Scale from the target, then independently measure at least two non-collinear known checker
  intervals and compare them to 10 mm pitch. Log error; do not just “eyeball” it.
- Check coverage: no unrecorded hole, floating island, mirrored orientation, or texture-only
  feature treated as geometry.
- Mesh is a capture of the real surface; CAD is the editable functional interpretation. Calipers
  verify critical dimensions and mates, but they do not replace the scan for worn/freeform form.
- For a fit-critical reverse-engineered part, create a mating coupon before a long/full print per
  `docs/workflow.md`.

## Scope

This records the capture discipline now. Mesh cleanup/surfacing automation remains a pipeline
stage to build; do not pretend the current repo automatically turns photos into a trusted mesh.
