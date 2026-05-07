---
title: Brave Leo does not use user data for training
entity: products/brave-leo
topics:
- data-privacy
verdict: 'true'
confidence: medium
verification_level: partially-verified
takeaway: Brave Leo does not train on user data.
seo_title: Brave Leo does not train on user data
criteria_slug: no-training-on-user-data
status: published
as_of: '2026-05-06'
sources:
- 2026/browser-privacy-policy
- 2024/leo-android
- 2025/automatic-mode-leo
- 2026/brave-leo-ai
- 2026/brave-ai
- 2024/rtx-ai-brave-browser
- 2024/byom-nightly
- 2025/leo-roadmap-2025-update
- 2025/browser-ai-tee
source_overrides:
- source: 2026/brave-ai
  independence: first-party
  reason: Although listed as independent, the index merely restates Brave’s own privacy
    statements without original measurement.
tags:
- highlight
---
Brave’s own documentation for Leo states that the assistant “doesn’t retain or share chats, or use them for additional model training” and that “your conversations are not persisted for model training”【2026/brave-leo-ai】. The Brave browser privacy policy reinforces this stance, asserting that the company does not collect or retain browsing history and that it has no access to information that could identify or profile users【2026/browser-privacy-policy】. Additional blog posts describe a privacy‑first architecture where requests are proxied through anonymization servers, BYOM bypasses Brave entirely, and local‑only inference is encouraged, all of which prevent Brave from seeing user prompts that could be used for training【2024/leo-android】【2024/byom-nightly】【2024/rtx-ai-brave-browser】. An independent index overview of Brave AI also repeats the claim that Leo “doesn’t retain or share chats, or use them for model training”【2026/brave-ai】. Together, these sources consistently indicate that Leo does not use user data to train its models.
