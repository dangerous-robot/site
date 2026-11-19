---
title: Gemini does not use user data for training
statement: Gemini does not use user data for training
entity: products/gemini
topics: [data-privacy]
verdict: mixed
confidence: medium
verification_level: independently-verified
takeaway: Gemini trains on user chats by default outside the EU, requiring an opt‑out.
seo_title: Gemini does not use user data for training
criteria_slug: no-training-on-user-data
status: draft
as_of: '2026-11-09'
next_recheck_due: '2027-01-08'
sources:
- 2025/google-gemini-now-learns-from-your-chats-unless-you-turn-it-off
- 2026/ai-privacy
- 2026/data-governance
- 2024/genaiprivacygooglecloudpdf
- 2026/news-google-gemini-ai-training-publishers-lawsuit
tags: []
---
An independent article from PPC Land reports that, as of August 13 2025, Gemini’s **Personal Context** feature automatically uses user conversation data for model training by default, requiring users to manually opt out in the privacy settings. This policy applies globally except for users in the European Union, United Kingdom, and Switzerland, where the feature is disabled. In contrast, Google’s own documentation for Workspace and Cloud states that Gemini does **not** use prompts or responses to train its models and that data is not used for training without explicit permission. A Google Cloud whitepaper reinforces the claim that customer data is not used for model training without prior consent. An independent news article notes a lawsuit alleging that Google trained Gemini on copyrighted books, suggesting some form of data use, though it focuses on copyrighted content rather than everyday user chats. The conflicting statements indicate that the consumer default varies by region: outside the EU/UK/Switzerland, user chats are used for training unless the user opts out; within those regions, chats are not used by default. The opt‑out control is located in the privacy settings of the Gemini product.
