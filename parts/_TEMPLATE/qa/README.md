# QA — measured vs. spec (physical)

After handoff, initialize one structured record per attempted coupon/full print:

```bash
python3 platform/pipeline/verify/qualification_check.py init \
  --manifest build/<plate>/qualification_manifest.json --part parts/<category>/<part> \
  --id YYYY-MM-DD-i1 --kind coupon --objective "question this print answers" \
  --output parts/<category>/<part>/qa/iterations/YYYY-MM-DD-i1.yaml
```

The command copies exact geometry, G-code, source, and slicer/profile identity and leaves every
physical field **NOT EVALUATED**. An agent may prepare that record; only the human who handled the
print may add execution facts, readings, observations, verdict, and `physical-observation`
attestation. Keep failed attempts—their `failure_class` and `next_change` close the design loop.
[`iteration.yaml`](iteration.yaml) documents the complete shape; [`reality-gate.md`](reality-gate.md)
is the human-readable worksheet, not the machine authority.

- keep raw repeated readings, instrument ID/resolution, and uncertainty basis in the iteration;
- record the actual printer, spool/lot/dry state, plate, nozzle/layer, ambient temperature/RH, and
  any process deviation after printing—named profiles are intent, not proof of what was loaded;
- add `measurements.csv` rows when a dimensional result also belongs in the shared research table;
- record every `spec.acceptance.printed` criterion, including failed attempts;
- retain evidence refs/photos of the identified artifact in situ;
- after a human pass, set `qualification.current` in `spec.yaml` and commit the record; the human
  then runs `CONFIRMED=1 bench.sh passed "<note>" <qa-record>`. Only after that immutable path/hash
  link exists may the part claim `dim-verified` or `released`.

A CAD bbox or STEP probe is not a physical measurement. `qualification_check.py` recomputes each
measurement against nominal ± tolerance including recorded uncertainty, checks current model bytes,
and refuses a non-draft status without matching evidence; accepted statuses also require the
matching human `passed/*` tag whose commit contains those record bytes. Never backfill an instrument, repeat
count, reading, operator, uncertainty, or verdict that was not actually recorded.
