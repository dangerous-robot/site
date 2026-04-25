---
url: https://code.claude.com/docs/en/monitoring-usage
title: Monitoring - Claude Code Docs
publisher: Anthropic
accessed_date: '2026-04-24'
kind: documentation
summary: Configuration and implementation guide for exporting Claude Code telemetry
  data via OpenTelemetry, including metrics, logs, events, and distributed traces.
key_quotes:
- Track Claude Code usage, costs, and tool activity across your organization by exporting
  telemetry data through OpenTelemetry (OTel).
- Telemetry is opt-in and requires explicit configuration
- Raw file contents and code snippets are not included in metrics or events.
source_type: primary
---
This documentation covers OpenTelemetry configuration for Claude Code, including environment variables, exporter types (OTLP, Prometheus, console), and managed settings for organizational control. It details available metrics (session count, lines of code, costs, tokens) and events (user prompts, API requests, tool results) with attributes for analysis and alerting. The guide emphasizes privacy and security controls through optional logging flags.
