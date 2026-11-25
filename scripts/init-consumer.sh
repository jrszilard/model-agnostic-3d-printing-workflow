#!/usr/bin/env bash
# Scaffold a consumer repository to use model-agnostic-3d-printing-workflow without copying scripts.
# Usage: scripts/init-consumer.sh [--platform-root <path>] [--force] <target_dir>
set -euo pipefail

WORKFLOW_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE_DIR="$WORKFLOW_ROOT/platform/consumer-template"
PLATFORM_ROOT_REL="../model-agnostic-3d-printing-workflow"
FORCE=0
TARGET=""

while [ $# -gt 0 ]; do
    case "$1" in
        --platform-root)
            shift
            [ $# -gt 0 ] || { echo "error: --platform-root requires a value" >&2; exit 2; }
            PLATFORM_ROOT_REL="$1"
            ;;
        --force)
            FORCE=1
            ;;
        -h|--help)
            echo "Usage: scripts/init-consumer.sh [--platform-root <path>] [--force] <target_dir>"
            exit 0
            ;;
        -*)
            echo "error: unknown option: $1" >&2
            exit 2
            ;;
        *)
            [ -z "$TARGET" ] || { echo "error: unexpected extra argument: $1" >&2; exit 2; }
            TARGET="$1"
            ;;
    esac
    shift
done

if [ -z "$TARGET" ]; then
    echo "Usage: scripts/init-consumer.sh [--platform-root <path>] [--force] <target_dir>" >&2
    exit 2
fi

mkdir -p "$TARGET/scripts/platform" "$TARGET/parts" "$TARGET/build"

write_if_allowed() {
    local dst="$1"
    local mode="${2:-0644}"
    if [ -e "$dst" ] && [ "$FORCE" != "1" ]; then
        cat > /dev/null
        echo "  skip (exists): $dst"
        return 0
    fi
    cat > "$dst"
    chmod "$mode" "$dst"
    echo "  write: $dst"
}

echo "Initializing consumer at $TARGET (platform.root=$PLATFORM_ROOT_REL)"

sed "s|__PLATFORM_ROOT__|$PLATFORM_ROOT_REL|g" "$TEMPLATE_DIR/platform.consumer.yaml" \
    | write_if_allowed "$TARGET/platform.consumer.yaml" 0644

cat "$WORKFLOW_ROOT/VERSION" | write_if_allowed "$TARGET/PLATFORM_VERSION" 0644

sed "s|__PLATFORM_ROOT__|$PLATFORM_ROOT_REL|g" "$TEMPLATE_DIR/scripts/platform/env.sh" \
    | write_if_allowed "$TARGET/scripts/platform/env.sh" 0755

cat <<'EOF' | write_if_allowed "$TARGET/scripts/platform/prepare.sh" 0755
#!/usr/bin/env bash
# Consumer fixes ownership before the shared coordinator runs.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/env.sh"
exec "$PLATFORM_ROOT/platform/pipeline/prepare/prepare.sh" "$@" --root "$CONSUMER_ROOT"
EOF

write_exec_wrapper() {
    local name="$1"
    local rel="$2"
    local runner="${3:-}"
    if [ -n "$runner" ]; then
        cat <<EOF | write_if_allowed "$TARGET/scripts/platform/$name" 0755
#!/usr/bin/env bash
set -euo pipefail
source "\$(dirname "\${BASH_SOURCE[0]}")/env.sh"
exec $runner "\$PLATFORM_ROOT/$rel" "\$@"
EOF
    else
        cat <<EOF | write_if_allowed "$TARGET/scripts/platform/$name" 0755
#!/usr/bin/env bash
set -euo pipefail
source "\$(dirname "\${BASH_SOURCE[0]}")/env.sh"
exec "\$PLATFORM_ROOT/$rel" "\$@"
EOF
    fi
}

write_exec_wrapper "build.sh"           "platform/pipeline/generate/build.sh"
write_exec_wrapper "producer.sh"        "platform/pipeline/generate/build_provenance.py" "python3"
write_exec_wrapper "render.sh"          "platform/pipeline/preview/render.sh"
write_exec_wrapper "verify.sh"          "platform/pipeline/verify/verify.sh"
write_exec_wrapper "verify-slice.sh"    "platform/pipeline/verify/verify-slice.sh"
write_exec_wrapper "slice.sh"           "platform/pipeline/slice/slice.sh"
write_exec_wrapper "handoff.sh"         "platform/pipeline/handoff/handoff.sh"
write_exec_wrapper "qualification.sh"   "platform/pipeline/verify/qualification_check.py" "python3"
write_exec_wrapper "next-action.sh"     "platform/pipeline/next_action.py" "python3"
write_exec_wrapper "plate-inventory.sh" "platform/pipeline/plate_inventory.py" "python3"
write_exec_wrapper "plate-scope.sh"     "platform/pipeline/plate_scope.py" "python3"
write_exec_wrapper "send.sh"            "platform/pipeline/send/send.sh"

echo "Done. Test with: $TARGET/scripts/platform/next-action.sh --help"
