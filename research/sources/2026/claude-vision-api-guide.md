---
url: https://docs.anthropic.com/en/docs/build-with-claude/vision
title: Vision - Build with Claude
publisher: Anthropic
accessed_date: '2026-04-25'
kind: documentation
summary: Comprehensive guide to Claude's vision capabilities for analyzing images,
  including usage methods, limits, best practices, code examples, and known limitations.
key_quotes:
- Claude's vision capabilities allow it to understand and analyze images, opening
  up exciting possibilities for multimodal interaction.
- An image uses approximately width * height / 750 tokens, where the width and height
  are expressed in pixels.
- Claude cannot be used to name people in images and refuses to do so.
- Multiple images can be included in a single request, which Claude will analyze jointly
  when formulating its response.
source_type: primary
---
This official API documentation covers Claude's multimodal vision capabilities, including supported formats (JPEG, PNG, GIF, WebP), token pricing calculations, image resolution limits (up to 8000x8000 px), and maximum images per request (20 on claude.ai, 100-600 via API). The guide provides practical code examples in multiple languages, prompt optimization tips, and details limitations including inability to identify people, spatial reasoning constraints, and inaccuracy with low-quality or tiny images.
