#!/usr/bin/env bash
# Remove all research artifacts for OpenAI (company) and ChatGPT (product).
# Pair with scripts/onboard-openai.sh for iterate-and-clear development cycles.
#
# Usage:
#   bash scripts/clear-openai.sh           # live run
#   bash scripts/clear-openai.sh --dry-run # print what would be deleted

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DRY_RUN=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

remove() {
  local target="$1"
  if [ ! -e "$target" ]; then
    echo "  skip (not found): $target"
    return
  fi
  if $DRY_RUN; then
    echo "  would remove: $target"
  else
    rm -rf "$target"
    echo "  removed: $target"
  fi
}

$DRY_RUN && echo "=== DRY RUN — nothing will be deleted ==="

echo ""
echo "=== Entities ==="
remove "$REPO_ROOT/research/entities/companies/openai.md"
remove "$REPO_ROOT/research/entities/products/chatgpt.md"

echo ""
echo "=== Claims ==="
remove "$REPO_ROOT/research/claims/openai"
remove "$REPO_ROOT/research/claims/chatgpt"

echo ""
echo "=== Sources ==="
while IFS= read -r -d '' f; do
  remove "$f"
done < <(find "$REPO_ROOT/research/sources" -type f -name "openai-*.md" -print0 -o -type f -name "chatgpt-*.md" -print0)

echo ""
$DRY_RUN && echo "=== Dry run complete. Re-run without --dry-run to apply. ===" || echo "=== Done. ==="
