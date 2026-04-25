---
url: https://arxiv.org/html/2505.09598v1
title: How Hungry is AI? Benchmarking Energy, Water, and Carbon Footprint of LLM Inference
publisher: arXiv
published_date: '2025-05-09'
accessed_date: '2026-04-24'
kind: report
summary: Framework for quantifying environmental footprint of LLM inference across
  30 models. Finds o3 and DeepSeek-R1 most energy-intensive; GPT-4o annually consumes
  electricity of 35,000 U.S. homes.
key_quotes:
- inference can account for up to 90% of a model's total lifecycle energy use
- a single short GPT-4o query consumes 0.43 Wh, scaling this to 700 million queries/day
  results in substantial annual environmental impacts
- although individual queries are efficient, their global scale drives disproportionate
  resource consumption
- DeepSeek-R1 consistently emits over 14 grams of carbon dioxide and consumes more
  than 150 milliliters of water per query
source_type: secondary
---
This research introduces an infrastructure-aware benchmarking framework combining API performance metrics with environmental multipliers (PUE, WUE, CIF) to estimate per-prompt energy, water, and carbon costs across 30 commercial LLM models. The study applies Data Envelopment Analysis to rank models by eco-efficiency and examines GPT-4o's projected annual environmental footprint at scale, illustrating the Jevons Paradox wherein efficiency gains lead to increased overall consumption.
