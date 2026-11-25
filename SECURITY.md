# Security & Printer Safety Policy

## Hardware safety invariants

3D printers are physical machines with heaters and moving axes. This workflow enforces strict software boundaries:

- **Upload counts as send:** `platform/pipeline/send/send.sh` refuses to upload or start a plate without an exact, verified `handoff.txt`, `qualification_manifest.json`, matching G-code/3MF SHA-256 hashes, matching per-ID plate inventory, no active `scope-hold.json`, and explicit human `APPROVED=1`.
- **No silent credential storage:** Printer credentials belong outside git (default `~/.config/3d-printing-workflow/prusalink.env` or `$PRUSALINK_ENV`).
- **Fail-closed defaults:** Unknown gate verdicts, missing manifests, or unreadable scope holds always block rather than pass.

## Reporting a vulnerability or safety bypass

If you find a way for an agent or script to bypass the handoff/approval/inventory/scope guards, or spot an accidental credential leak:

1. Please open a private security advisory on GitHub (Security → Advisories → Report a vulnerability) rather than posting an exploit in a public issue.
2. Include the minimal reproduction steps and the affected script path.
