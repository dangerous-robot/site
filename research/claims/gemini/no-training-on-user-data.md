---
title: Gemini does not use user data for training
statement: Gemini does not use user data for training
entity: products/gemini
topics: [data-privacy]
verdict: mixed
confidence: medium
verification_level: independently-verified
takeaway: ''
seo_title: Gemini does not use user data for training
criteria_slug: no-training-on-user-data
status: draft
as_of: '2026-11-08'
next_recheck_due: '2027-01-07'
sources:
- 2025/google-gemini-now-learns-from-your-chats-unless-you-turn-it-off
- 2026/ai-privacy
- 2026/data-governance
- 2024/genaiprivacygooglecloudpdf
- 2026/news-google-gemini-ai-training-publishers-lawsuit
tags: []
---
Google’s own privacy documentation says Gemini does not train on user prompts or data without explicit permission, emphasizing that content remains within the organization and is not shared for model training (*Secure AI and Privacy in Google Workspace with Gemini*; *Data Governance for Gemini Products in Google Cloud*; *Generative AI, Privacy, and Google Cloud*). However, an independent report notes that the consumer “Personal Context” feature automatically feeds chat content into model training by default, requiring users to manually turn the setting off, and that this behavior is blocked for users in the EU, UK and Switzerland (*Google Gemini Now Learns From Your Chats Unless You Turn It Off*). No third‑party audits or ESG reports were found that independently evaluate Gemini’s data‑use practices. Google publicly pledges not to use customer data for training without permission in its product announcements and whitepapers (*Generative AI, Privacy, and Google Cloud*). A lawsuit alleging that Google used copyrighted books to train Gemini shows ongoing controversy over the sources of training data (*Publishers and Author Sue Google Over Copyright Violations in Gemini AI Training*). The mixed evidence—enterprise documentation asserting no training use versus consumer‑facing defaults that do train—means the claim is mixed.
