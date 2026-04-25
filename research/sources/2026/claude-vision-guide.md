---
url: https://docs.anthropic.com/en/docs/build-with-claude/vision
title: Vision
publisher: Anthropic
accessed_date: '2026-04-24'
kind: documentation
summary: Guide to Claude's vision capabilities for analyzing images via API, including
  usage limits, image costs, quality considerations, code examples, and limitations.
key_quotes:
- Claude's vision capabilities allow it to understand and analyze images, opening
  up exciting possibilities for multimodal interaction.
- An image uses approximately width * height / 750 tokens, where the width and height
  are expressed in pixels.
- Claude cannot be used to name people in images and refuses to do so.
- Claude does not know if an image is AI-generated and may be incorrect if asked.
source_type: primary
---
This is the official Anthropic documentation for using Claude's vision capabilities through the API. It covers practical implementation details including image format requirements, token consumption calculations, API request examples in multiple programming languages, and important limitations to consider for production use cases. The guide emphasizes that images should be provided before text in prompts and includes specific guidance on high-resolution support in Claude Opus 4.7.
