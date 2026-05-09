---
title: Claude does not use user data for training
entity: products/claude
topics:
- data-privacy
verdict: 'false'
confidence: medium
verification_level: partially-verified
cap_rationale: Confidence is capped at low — while independent sources (like Source
  2, 4, 8) clarify that an opt-in is required and opt-out is possible, all sources
  rely on stated policy rather than independent confirmation of actual data use (or
  absence of use). The entity itself states non-use is only operating in opt-out mode;
  no source independently confirms zero data use in practice. This aligns with 'unexc
takeaway: ''
seo_title: Claude does not use user data for training
criteria_slug: no-training-on-user-data
status: published
as_of: '2026-05-07'
sources:
- 2025/claude-data-retention-policies-storage-rules-and-compliance-overview
- 2025/anthropic-using-claude-chats-for-training-how-to-opt-out
- 2026/7996885-how-do-you-use-personal-data-in-model-training
- 2025/claudeai-switches-to-opt-out-consent-model-for-personal-data-usage-in-ai-model-training
- 2025/claude-secure-usage-how-to-work-with-ai-without-sharing-sensitive-information
- 2026/anthropic-data-retention-policy
- 2026/claude-ai-privacy-policy
- 2025/claude-ai-will-start-training-on-your-data-soon-heres-how-to-opt-out-before-the-deadline
tags: []
---
Claude's official policy, as disclosed in its documentation (Source 3) and confirmed by independent sources like Anthropic Will Use Claude Chats for Training Data (Source 2) and other external coverage (Source 4, 8), states that user data may be used for training if users opt in. However, by default, Claude operates in a state where user data is *not* used for training unless users explicitly consent. Available sources reinforce this opt-in model rather than no-use-at-all. For instance, Source 5, Writer's Guide for Safe AI Usage (from Data Studios), notes that Claude does not use user inputs for model training unless opted into. However, Source 2 and related updates indicate that Claude launched an opt-out to user training data after September 2025. A user must actively opt out to prevent data use, not choose to opt-in. This falls short of an absolute 'does not use' claim; instead, the policy focuses on opt-in consent.
