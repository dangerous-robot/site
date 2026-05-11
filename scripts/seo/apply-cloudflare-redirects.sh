#!/usr/bin/env bash
set -euo pipefail

: "${CF_API_TOKEN:?CF_API_TOKEN must be exported}"
: "${CF_ACCOUNT_ID:?CF_ACCOUNT_ID must be exported}"

AUTH="Authorization: Bearer $CF_API_TOKEN"
CT="Content-Type: application/json"
API="https://api.cloudflare.com/client/v4"
LIST_NAME="dr_redirects"
RULE_REF="dr_redirects_rule"

# Pre-flight: verify the token can read the account's rules/lists.
# (The /accounts/{id}/tokens/verify endpoint is not a real Cloudflare route.)
curl -sSf -H "$AUTH" "$API/user/tokens/verify" >/dev/null \
  || { echo "CF_API_TOKEN is not active"; exit 1; }
curl -sSf -H "$AUTH" "$API/accounts/$CF_ACCOUNT_ID/rules/lists" >/dev/null \
  || { echo "CF_API_TOKEN cannot access account $CF_ACCOUNT_ID rules/lists"; exit 1; }

# (a) Find or create the redirect list
LIST_ID=$(curl -sSf -H "$AUTH" "$API/accounts/$CF_ACCOUNT_ID/rules/lists" \
  | jq -r --arg n "$LIST_NAME" '.result[] | select(.name==$n and .kind=="redirect") | .id' | head -1)
if [ -z "$LIST_ID" ]; then
  LIST_ID=$(curl -sSf -X POST -H "$AUTH" -H "$CT" \
    "$API/accounts/$CF_ACCOUNT_ID/rules/lists" \
    -d '{"name":"'"$LIST_NAME"'","description":"dangerousrobot.org restructure 301s","kind":"redirect"}' \
    | jq -r .result.id)
fi
echo "LIST_ID=$LIST_ID"

# (b) Replace items in the list (PUT replaces; safe to rerun). Async op, poll with timeout + failure handling.
OP=$(curl -sSf -X PUT -H "$AUTH" -H "$CT" \
  "$API/accounts/$CF_ACCOUNT_ID/rules/lists/$LIST_ID/items" \
  --data @scripts/seo/redirects.json | jq -r .result.operation_id)
for _ in $(seq 1 60); do
  resp=$(curl -sSf -H "$AUTH" "$API/accounts/$CF_ACCOUNT_ID/rules/lists/bulk_operations/$OP")
  status=$(echo "$resp" | jq -r .result.status)
  case "$status" in
    completed) break ;;
    failed)    echo "$resp" | jq .result.error >&2; exit 1 ;;
    pending|running) sleep 2 ;;
    *) echo "unexpected bulk_op status: $status" >&2; exit 1 ;;
  esac
done
[ "$status" = "completed" ] || { echo "bulk_op timed out"; exit 1; }

# (c) Find or create the http_request_redirect entrypoint ruleset.
# Use -w with a newline so we can split body/status safely.
HTTP=$(curl -sS -o /tmp/rs.json -w '%{http_code}' -H "$AUTH" \
  "$API/accounts/$CF_ACCOUNT_ID/rulesets/phases/http_request_redirect/entrypoint")
if [ "$HTTP" = "200" ]; then
  RULESET_ID=$(jq -r .result.id < /tmp/rs.json)
elif [ "$HTTP" = "404" ]; then
  RULESET_ID=$(curl -sSf -X POST -H "$AUTH" -H "$CT" \
    "$API/accounts/$CF_ACCOUNT_ID/rulesets" \
    -d '{"name":"DR redirects entrypoint","kind":"root","phase":"http_request_redirect","rules":[]}' \
    | jq -r .result.id)
else
  echo "Unexpected status $HTTP from entrypoint GET" >&2; cat /tmp/rs.json >&2; exit 1
fi

# (d) Upsert the rule by ref. PUT the full rules array.
# Guard against null `rules` on a freshly-created ruleset.
EXISTING=$(curl -sSf -H "$AUTH" "$API/accounts/$CF_ACCOUNT_ID/rulesets/$RULESET_ID" \
  | jq --arg ref "$RULE_REF" '[(.result.rules // [])[] | select(.ref!=$ref)]')
NEW_RULE=$(jq -n --arg ref "$RULE_REF" --arg list "$LIST_NAME" '{
  ref: $ref,
  enabled: true,
  action: "redirect",
  description: "DR restructure 301s (list: \($list))",
  expression: "http.request.full_uri in $\($list)",
  action_parameters: { from_list: { name: $list, key: "http.request.full_uri" } }
}')
RULES=$(jq -n --argjson e "$EXISTING" --argjson r "$NEW_RULE" '$e + [$r]')
curl -sS -X PUT -H "$AUTH" -H "$CT" \
  "$API/accounts/$CF_ACCOUNT_ID/rulesets/$RULESET_ID" \
  -d "$(jq -n --argjson rules "$RULES" '{rules:$rules}')" > /dev/null
