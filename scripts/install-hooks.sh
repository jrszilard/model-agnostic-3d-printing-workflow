#!/usr/bin/env bash
# Install the local pre-push hook that runs scripts/check-public.py before any push.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="$ROOT/.git/hooks/pre-push"

if [ ! -d "$ROOT/.git/hooks" ]; then
    echo "error: $ROOT/.git/hooks not found" >&2
    exit 2
fi

cat > "$HOOK" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
echo "Running public workflow guard (scripts/check-public.py)..."
python3 "$ROOT/scripts/check-public.py"
EOF
chmod +x "$HOOK"
echo "Installed pre-push hook at $HOOK"
