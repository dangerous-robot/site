#!/usr/bin/env bash
set -euo pipefail

: "${GSC_QUOTA_PROJECT:?GSC_QUOTA_PROJECT must be exported (e.g. dr-seo-496019)}"

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
DATE=$(date -u +%Y-%m-%d)
OUT_DIR="$REPO_ROOT/seo-runs/urlinspect-$DATE"
mkdir -p "$OUT_DIR"

URLS=(
  "https://dangerousrobot.org/"
  "https://dangerousrobot.org/research"
  "https://dangerousrobot.org/resources"
  "https://dangerousrobot.org/values"
  "https://dangerousrobot.org/credits"
  "https://dangerousrobot.org/resources/should-i"
  "https://dangerousrobot.org/resources/ai-safety"
  "https://dangerousrobot.org/resources/turn-off-ai"
  "https://dangerousrobot.org/resources/responsible-ai"
  "https://dangerousrobot.org/research/claims"
  "https://dangerousrobot.org/research/companies"
  "https://dangerousrobot.org/research/products"
  "https://dangerousrobot.org/research/subjects"
  "https://dangerousrobot.org/research/topics"
  "https://dangerousrobot.org/research/sources"
  "https://dangerousrobot.org/research/criteria"
  "https://dangerousrobot.org/claims"
  "https://dangerousrobot.org/companies"
)

inspect_one() {
  local url="$1" out="$2"
  local token
  token=$(gcloud auth application-default print-access-token)
  curl -sS -X POST \
    -H "Authorization: Bearer $token" \
    -H "x-goog-user-project: $GSC_QUOTA_PROJECT" \
    -H "Content-Type: application/json" \
    https://searchconsole.googleapis.com/v1/urlInspection/index:inspect \
    -d "{\"inspectionUrl\":\"$url\",\"siteUrl\":\"sc-domain:dangerousrobot.org\",\"languageCode\":\"en-US\"}" \
    -o "$out"
}

urlencode() {
  python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1],safe=""))' "$1"
}

for url in "${URLS[@]}"; do
  enc=$(urlencode "$url")
  out="$OUT_DIR/$enc.json"
  inspect_one "$url" "$out"
  sleep 0.15
done

echo
echo "Summary ($OUT_DIR):"
for url in "${URLS[@]}"; do
  enc=$(urlencode "$url")
  out="$OUT_DIR/$enc.json"
  summary=$(jq -r '.inspectionResult.indexStatusResult |
    "verdict=\(.verdict // "-") coverageState=\(.coverageState // "-") googleCanonical=\(.googleCanonical // "-") userCanonical=\(.userCanonical // "-")"' \
    "$out" 2>/dev/null || echo "parse-error")
  printf '%s  %s\n' "$url" "$summary"
done
