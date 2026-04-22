# Entity Onboarding Queue

One entry per line: `name|type`. Blank lines and `#` comments are ignored.

Process all entries:
```bash
while IFS='|' read -r name type; do
  [[ "$name" =~ ^# || -z "$name" ]] && continue
  dr onboard "$name" --type "$type"
done < research/ONBOARD_QUEUE.md
```

---

Anthropic|company
Ecosia|company
OpenAI|company
TreadLightlyAI|company
GreenPT|company
ChatGPT|product
Ecosia AI|product
Viro AI|product

# Needs manual review before re-onboarding:
# Earthly Insight|company  -- previously misresolved to an environmental NGO; verify entity before running
# ChatGPTRee|company        -- exists as both company and product; decide type first
# ChatGPTRee|product        -- see above
