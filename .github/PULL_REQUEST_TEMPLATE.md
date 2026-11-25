## Summary

- What does this PR change and why?

## Safety & scope checklist

- [ ] No approval or physical-attestation gates (`APPROVED=1`, `CONFIRMED=1`, `handoff.sh`, `send.sh`, `plate_scope.py`, `plate_inventory.py`) were weakened or bypassed
- [ ] `platform/pipeline/test.sh` passes
- [ ] `python3 scripts/check-public.py` passes
- [ ] New behavior includes offline unit tests (covering pass and fail paths)
- [ ] Docs updated where entry points or gate contracts changed
