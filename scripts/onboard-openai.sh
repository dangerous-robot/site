#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Onboarding OpenAI (company) ==="
uv run dr onboard "OpenAI" https://openai.com --type company --repo-root "$REPO_ROOT"

echo "=== Onboarding ChatGPT (product) ==="
uv run dr onboard "ChatGPT" https://chatgpt.com --type product --repo-root "$REPO_ROOT"
