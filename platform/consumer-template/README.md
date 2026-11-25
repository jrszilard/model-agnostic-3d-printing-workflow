# Consumer Template

Use `scripts/init-consumer.sh` from the workflow repository to wire any parts repository to
`model-agnostic-3d-printing-workflow` without copying or forking the pipeline scripts:

```bash
# Default: expects workflow cloned as a sibling at ../model-agnostic-3d-printing-workflow
../model-agnostic-3d-printing-workflow/scripts/init-consumer.sh .

# Or point at a submodule / custom path:
./vendor/workflow/scripts/init-consumer.sh . --platform-root vendor/workflow
```

What gets created in the consumer repo:
- `platform.consumer.yaml` — declares the workflow root, version handshake, and entry points
- `PLATFORM_VERSION` — pins the expected workflow `VERSION`
- `scripts/platform/env.sh` — resolves `PLATFORM_ROOT` and verifies `PLATFORM_VERSION`
- `scripts/platform/*.sh` — thin one-line executors for every pipeline stage (`prepare`, `build`,
  `render`, `verify`, `slice`, `verify-slice`, `handoff`, `qualification`, `next-action`,
  `plate-inventory`, `plate-scope`, `send`)

Keep all domain parts, `build/` outputs, printer credentials, and physical test records in the
consumer repository. Keep reusable pipeline fixes in `model-agnostic-3d-printing-workflow`.
See `docs/consumer-contract.md` for the full contract.
