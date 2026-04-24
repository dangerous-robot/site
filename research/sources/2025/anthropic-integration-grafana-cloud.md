---
url: https://grafana.com/blog/how-to-monitor-claude-usage-and-costs-introducing-the-anthropic-integration-for-grafana-cloud/
title: 'How to monitor Claude usage and costs: introducing the Anthropic integration
  for Grafana Cloud'
publisher: Grafana Labs
published_date: '2025-08-19'
accessed_date: '2026-04-24'
kind: blog
summary: Grafana Cloud now offers an Anthropic integration that monitors Claude LLM
  usage and costs via the Anthropic Usage and Cost API, providing real-time dashboards
  and alerts.
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
The integration works without requiring additional agents or exporters, pulling metrics directly from Anthropic's Usage and Cost API and converting them into Prometheus format. It provides a pre-built dashboard with interactive panels for tracking token consumption, costs, and model usage, plus three customizable alert rules for cost and token anomalies. The setup process requires an Anthropic Admin API key and takes approximately five minutes to configure within Grafana Cloud.
