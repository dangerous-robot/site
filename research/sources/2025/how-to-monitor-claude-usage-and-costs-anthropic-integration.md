---
url: https://grafana.com/blog/how-to-monitor-claude-usage-and-costs-introducing-the-anthropic-integration-for-grafana-cloud/
title: 'How to monitor Claude usage and costs: introducing the Anthropic integration
  for Grafana Cloud'
publisher: Grafana Labs
published_date: '2025-08-19'
accessed_date: '2026-04-26'
kind: blog
summary: Grafana Labs adds an Anthropic integration for Grafana Cloud that pulls Claude
  usage and cost data via Anthropic’s API, with pre‑built dashboards, token metrics,
  and alerts.
key_quotes:
- Introducing the Anthropic integration for Grafana Cloud, a new solution that lets
  you connect directly to the Anthropic Usage and Cost API from within Grafana Cloud.
- The integration provides real-time insights into both the costs and performance
  of your Claude LLMs, all within Grafana Cloud.
- The Anthropic integration for Grafana Cloud includes a pre‑built API usage dashboard
  that allows you to quickly and easily track token consumption and costs, model usage,
  and more.
- 'AnthropicDailyCostSpike: Triggers when the daily cost increases by more than 50%
  compared to the previous day.'
- 'AnthropicTokenRateAnomaly: Alerts when token processing rate exceeds 3x the 7‑day
  average.'
source_type: tertiary
---
The post explains how the collector‑less Grafana Cloud Metrics Endpoint fetches data from Anthropic's Usage and Cost API, converting it into Prometheus metrics for monitoring Claude LLMs. It also details setup steps, dashboard features, and ready‑made alerts.
