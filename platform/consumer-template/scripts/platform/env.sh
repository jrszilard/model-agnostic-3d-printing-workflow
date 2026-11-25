#!/usr/bin/env bash
# Resolve CONSUMER_ROOT and PLATFORM_ROOT for scripts/platform wrappers.
# Override PLATFORM_ROOT only for deliberate workflow-compatibility testing.

CONSUMER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEFAULT_PLATFORM_REL="__PLATFORM_ROOT__"

if [[ -z "${PLATFORM_ROOT:-}" ]]; then
  if [[ "$DEFAULT_PLATFORM_REL" = /* ]]; then
    PLATFORM_ROOT="$DEFAULT_PLATFORM_REL"
  else
    PLATFORM_ROOT="$CONSUMER_ROOT/$DEFAULT_PLATFORM_REL"
  fi
fi

if [[ ! -f "$PLATFORM_ROOT/platform/AGENTS.md" ]]; then
  echo "error: platform/AGENTS.md not found under PLATFORM_ROOT=$PLATFORM_ROOT" >&2
  echo "  Clone model-agnostic-3d-printing-workflow there, or set PLATFORM_ROOT=/path/to/workflow." >&2
  exit 2
fi

if [[ "${PLATFORM_VERSION_ALLOW_MISMATCH:-0}" != "1" ]] \
   && [[ -f "$CONSUMER_ROOT/PLATFORM_VERSION" ]] \
   && [[ -f "$PLATFORM_ROOT/VERSION" ]]; then
  _want="$(tr -d '[:space:]' < "$CONSUMER_ROOT/PLATFORM_VERSION")"
  _have="$(tr -d '[:space:]' < "$PLATFORM_ROOT/VERSION")"
  if [[ "$_want" != "$_have" ]]; then
    echo "error: workflow VERSION mismatch: consumer pins $_want (PLATFORM_VERSION), workflow is $_have ($PLATFORM_ROOT/VERSION)" >&2
    echo "  Update PLATFORM_VERSION after verifying compatibility, or set PLATFORM_VERSION_ALLOW_MISMATCH=1 to test." >&2
    exit 2
  fi
fi
