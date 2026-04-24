---
url: https://grafana.com/blog/how-to-monitor-claude-usage-and-costs-introducing-the-anthropic-integration-for-grafana-cloud/
title: 'How to monitor Claude usage and costs: introducing the Anthropic integration
  for Grafana Cloud'
publisher: Grafana Labs
published_date: '2025-08-19'
accessed_date: '2026-04-23'
kind: blog
summary: Grafana Cloud integration for monitoring Claude LLM usage and costs via the
  Anthropic Usage and Cost API. Provides real-time metrics, pre-built dashboards,
  and customizable alerts.
key_quotes:
- By leveraging usage data from Anthropic — the AI company who developed the Claude
  large language models (LLMs) — the integration provides real-time insights into
  both the costs and performance of your Claude LLMs, all within Grafana Cloud.
- This collector-less integration (built on the Grafana Cloud Metrics Endpoint feature)
  pulls usage data directly from the Usage and Cost API, converts it into Prometheus-format
  metrics, and stores it in Grafana Cloud.
- The integration also provides three ready-to-use, customizable alerts to stay ahead
  of unexpected usage and cost spikes
source_type: tertiary
---
The Anthropic integration for Grafana Cloud enables direct monitoring of Claude LLM usage and costs through a collector-less architecture that pulls data from the Anthropic Usage and Cost API. The integration automatically transforms this data into Prometheus-format metrics (gen_ai_cost and gen_ai_usage_tokens_total) and provides a pre-built dashboard with template variables for dynamic filtering by workspace, model, and job name. Three customizable alerts are included to monitor daily cost spikes (>50% increase), token rate anomalies (>3x 7-day average), and high daily costs (>$1000).
