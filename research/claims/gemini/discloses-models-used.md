---
title: Gemini transparently discloses model details
entity: products/gemini
topics:
- ai-safety
verdict: 'true'
confidence: medium
verification_level: partially-verified
cap_rationale: Confidence is capped at medium due to reliance on Google's self-disclosed
  documentation (Sources 3, 7, 8). Though sourced from first-party pages, these are
  detailed, signed by Google's engineering and AI teams, exceeding typical promotional
  releases. However, gaps remain in critical transparency metrics like data ethics
  due to mentioned concerns about confidential or proprietary info (Source 2).
takeaway: Gemini offers partial model transparency but lacks granular details on training
  data, parameters, or ethical boundaries beyond its documentation.
seo_title: Gemini partially discloses model specifics
criteria_slug: discloses-models-used
status: published
as_of: '2026-05-07'
sources:
- 2024/googlegemini201020ultra20apihtml
- 2025/googlefinalreportfmti2025html
- 2024/design
- 2026/13594961
- 2026/access-transparency
- 2026/google-transparency-report
- 2026/models
- 2026/gemini-enterprise-agent-platform
source_overrides:
- source: Source 2
  independence: first-party
  reason: This source evaluates Google's own reporting on transparency, which is acknowledged
    as self-reported though detailed.
tags: []
---
Google publicly discloses some core details about the models used in Gemini. Source 1, the CRFM report, evaluated Google's transparency for Gemini 1.0 Ultra (see 'Gemini 1.0 API'), specifically details data sources, model architecture in the context of the AI's capability. Additionally, Source 7 lists and explains different model families (like Gemini 3.1 Pro, AI Agents, or Nebula dataset models) under 'Google AI models'. Source 3 provides guidance on model cards and transparent development practices for responsibility (see Google AI’s 'Design a responsible approach' documentation). The 'Models' source (Source 7) lists model types and versions, while Source 8 (Gemini Enterprise/platform) and 7 elaborate on capabilities and access. However, while Google documents model families and some development processes (synthetic data creation, architecture), these sources do not provide comprehensive granularity about training data composition, model parameters, or the security and ethical evaluations for all Tensorflow engine specifics in use. Google's documentation also emphasizes model cards but does not disclose dataset ownership, spent computational resources, or training data origins. Source 2's Report, for instance, scores Google's transparency but notes non-disclosure around specific data acquisition practices and compute allocation meant for security. Thus, while Gemini is partially disclosed, key details about raw model specifications, especially internal technical parameters or data sources, are not provided in publicly accessible documentation. Additionally, the reports from independent evaluators (Sources 1 and 2) give context rather than confirming every aspect of the claim, which applies more technically limited insights from Google's perspective. Given this, the claim that it 'discloses all models used' is true but notably insufficient in depth. Thus, the claim holds but with limitations outlined above.
