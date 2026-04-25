---
url: https://grafana.com/blog/how-to-monitor-claude-usage-and-costs-introducing-the-anthropic-integration-for-grafana-cloud/
title: 'How to monitor Claude usage and costs: introducing the Anthropic integration
  for Grafana Cloud'
publisher: Grafana Labs
published_date: '2025-08-19'
accessed_date: '2026-04-24'
kind: blog
summary: Introduces the Anthropic integration for Grafana Cloud, enabling real-time
  monitoring of Claude LLM costs and usage through pre-built dashboards and alerts.
key_quotes:
- Generative AI is becoming a core part of modern applications, making it essential
  to monitor and manage how these services are used.
- By leveraging usage data from Anthropic — the AI company who developed the Claude
  large language models (LLMs) — the integration provides real-time insights into
  both the costs and performance of your Claude LLMs, all within Grafana Cloud.
- This collector-less integration (built on the Grafana Cloud Metrics Endpoint feature)
  pulls usage data directly from the Usage and Cost API, converts it into Prometheus-format
  metrics, and stores it in Grafana Cloud.
source_type: tertiary
---
The Anthropic integration for Grafana Cloud is a collector-less solution that connects directly to Anthropic's Usage and Cost API to provide real-time insights into Claude model performance and costs. The integration includes a pre-built dashboard with interactive panels for tracking token consumption, model usage distribution, and cost trends, along with three customizable alert rules for cost spikes and usage anomalies. Setup requires entering an Anthropic Admin API key and takes approximately one minute to enable automated metric collection every minute.
