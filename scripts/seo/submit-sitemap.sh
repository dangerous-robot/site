#!/usr/bin/env bash
set -euo pipefail

: "${GSC_QUOTA_PROJECT:?GSC_QUOTA_PROJECT must be exported (e.g. dr-seo-496019)}"

SITE=$(python3 -c 'import urllib.parse;print(urllib.parse.quote("sc-domain:dangerousrobot.org",safe=""))')
FEED=$(python3 -c 'import urllib.parse;print(urllib.parse.quote("https://dangerousrobot.org/sitemap-index.xml",safe=""))')

submit() {
  local token
  token=$(gcloud auth application-default print-access-token)
  curl -sS -o /dev/null -w '%{http_code}' -X PUT \
    -H "Authorization: Bearer $token" \
    -H "x-goog-user-project: $GSC_QUOTA_PROJECT" \
    "https://www.googleapis.com/webmasters/v3/sites/$SITE/sitemaps/$FEED"
}

fetch() {
  local token
  token=$(gcloud auth application-default print-access-token)
  curl -sSf \
    -H "Authorization: Bearer $token" \
    -H "x-goog-user-project: $GSC_QUOTA_PROJECT" \
    "https://www.googleapis.com/webmasters/v3/sites/$SITE/sitemaps/$FEED"
}

HTTP=$(submit)
case "$HTTP" in
  2*) echo "sitemap submit: HTTP $HTTP" ;;
  *)  echo "sitemap submit failed: HTTP $HTTP" >&2; exit 1 ;;
esac

fetch | jq '{isPending, lastSubmitted}'
