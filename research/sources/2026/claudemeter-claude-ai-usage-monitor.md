---
url: https://marketplace.visualstudio.com/items?itemName=hypersec.claudemeter
title: Claudemeter - Claude AI Usage Monitor
publisher: HyperI (formerly HyperSec)
accessed_date: '2026-04-24'
kind: documentation
summary: VS Code extension that monitors Claude API usage in real-time, tracking session,
  weekly, and token limits across all Claude plans with automatic context window detection.
key_quotes:
- Tracks session, weekly, and token limits across all Claude plans.
- The extension verifies the browser account matches the CLI account, saves the session
  cookie locally, and closes the browser
- Claude.ai's usage API endpoints are undocumented and may change without notice
source_type: primary
---
Claudemeter is a VS Code extension developed by HyperI that provides real-time monitoring of Claude AI usage, including token consumption, session limits, weekly limits, and API service status. The extension automatically detects context window sizes and uses HTTP requests to fetch usage data from Claude.ai's API endpoints after an initial browser-based login. It is open source and available on GitHub, with comprehensive configuration options and built-in fallback mechanisms for API changes.
