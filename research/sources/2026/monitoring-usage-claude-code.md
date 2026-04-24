---
url: https://code.claude.com/docs/en/monitoring-usage
title: Monitoring
publisher: Anthropic
accessed_date: '2026-04-24'
kind: documentation
summary: Documentation for configuring OpenTelemetry monitoring in Claude Code to
  export metrics, events, and traces for usage tracking, cost monitoring, and tool
  activity.
key_quotes:
- Track Claude Code usage, costs, and tool activity across your organization by exporting
  telemetry data through OpenTelemetry (OTel).
- Telemetry is opt-in and requires explicit configuration
- Raw file contents and code snippets are not included in metrics or events.
source_type: primary
---
This documentation provides comprehensive guidance on setting up OpenTelemetry-based telemetry collection for Claude Code, including configuration of metrics exporters, logs/events exporters, and distributed traces. It details environment variable configuration, available metrics (session count, tokens, costs), event types (user prompts, tool results, API requests), and span hierarchies for distributed tracing. The guide emphasizes privacy controls—telemetry is opt-in and content logging (prompts, tool details, API bodies) can be disabled by default.
