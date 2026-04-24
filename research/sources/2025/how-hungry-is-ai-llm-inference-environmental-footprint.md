---
url: https://arxiv.org/html/2505.09598v1
title: How Hungry is AI? Benchmarking Energy, Water, and Carbon Footprint of LLM Inference
publisher: arXiv
published_date: '2025-05-09'
accessed_date: '2026-04-23'
kind: report
summary: Framework measuring energy, water, and carbon footprint of 30 LLM inference
  models in commercial data centers, finding o3 and DeepSeek-R1 consume 70× more than
  GPT-4.1 nano.
key_quotes:
- o3 and DeepSeek-R1 emerge as the most energy-intensive models, consuming over 33
  Wh per long prompt, more than 70 times the consumption of GPT-4.1 nano
- scaling this to 700 million queries/day results in substantial annual environmental
  impacts. These include electricity use comparable to 35,000 U.S. homes, freshwater
  evaporation matching the annual drinking needs of 1.2 million people, and carbon
  emissions requiring a Chicago-sized forest to offset
- 'a growing paradox: although individual queries are efficient, their global scale
  drives disproportionate resource consumption'
source_type: secondary
---
This paper presents an infrastructure-aware methodology for quantifying per-prompt environmental costs of LLM inference by combining API performance metrics with region-specific environmental multipliers (PUE, WUE, CIF) and statistical hardware estimation. The study benchmarks 30 state-of-the-art models including GPT-4o, Claude-3.7 Sonnet, DeepSeek-R1, and o3. A case study estimates GPT-4o's 2025 annual consumption at 391,509–463,269 MWh, equivalent to freshwater needs for 1.2 million people and carbon equivalent to a Chicago-sized forest.
