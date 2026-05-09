---
title: "Responsible AI Chatbots Compared"
description: "Side-by-side comparison of responsible AI chatbots: GreenPT, Ecosia AI, Euria, and TreadLightly AI on privacy, sustainability, and transparency."
pubDate: 2026-03-06
layout: matrix
wallpaper: responsible-ai
topics:
  - responsible-ai
  - consumer-guide
data:
  lede: "If you use AI, choose wisely."
  caption: "Data gathered from public sources as of April 2026. If something is wrong, let us know."
  products:
    - key: greenpt
      name: GreenPT
      url: https://greenpt.ai/
    - key: ecosia
      name: Ecosia AI
      url: https://blog.ecosia.org/ecosia-ai/
    - key: euria
      name: Euria
      url: https://euria.ai/
    - key: treadlightly
      name: TreadLightly AI
      url: https://treadlightly.ai/
  dimensions:
    - label: "Hosted on renewable energy"
      cells:
        greenpt: { type: "yes" }
        ecosia: { type: "no" }
        euria: { type: "yes" }
        treadlightly: { type: "partial", detail: "All but Anthropic" }
    - label: "Real-time energy display"
      cells:
        greenpt: { type: "yes" }
        ecosia: { type: "no" }
        euria: { type: "no" }
        treadlightly: { type: "yes" }
    - label: "No image generation"
      cells:
        greenpt: { type: "yes" }
        ecosia: { type: "yes" }
        euria: { type: "yes" }
        treadlightly: { type: "yes" }
    - label: "Financial transparency"
      cells:
        greenpt: { type: "partial", detail: "Employee-owned" }
        ecosia: { type: "yes", detail: "Non-profit" }
        euria: { type: "partial", detail: "B Corp" }
        treadlightly: { type: "partial", detail: "Pre-launch" }
    - label: "Models"
      cells:
        greenpt: { type: "text", detail: "Mistral Small, Mistral Large" }
        ecosia: { type: "text", detail: "GPT-4 mini" }
        euria: { type: "text", detail: "DeepSeek R1, Qwen 3, Mistral Nemo, Llama 3.3" }
        treadlightly: { type: "text", detail: "Mistral Ministral, Mistral Small, GPT-oss, Claude Haiku, Claude Sonnet" }
    - label: "Image and document analysis"
      cells:
        greenpt: { type: "yes" }
        ecosia: { type: "no" }
        euria: { type: "yes" }
        treadlightly: { type: "yes" }
    - label: "Data used for training"
      cells:
        greenpt: { type: "no-good" }
        ecosia: { type: "unknown" }
        euria: { type: "no-good" }
        treadlightly: { type: "no-good" }
    - label: "Published AI limitations"
      cells:
        greenpt: { type: "partial" }
        ecosia: { type: "partial" }
        euria: { type: "no" }
        treadlightly: { type: "yes" }
    - label: "Corporate structure"
      cells:
        greenpt: { type: "text", detail: "Employee-owned" }
        ecosia: { type: "text", detail: "Steward-ownership" }
        euria: { type: "text", detail: "Employee-controlled, B Corp" }
        treadlightly: { type: "text", detail: "Private" }
    - label: "Free tier"
      cells:
        greenpt: { type: "yes" }
        ecosia: { type: "yes" }
        euria: { type: "yes" }
        treadlightly: { type: "yes" }
    - label: "Accessibility"
      cells:
        greenpt: { type: "partial" }
        ecosia: { type: "partial" }
        euria: { type: "partial" }
        treadlightly: { type: "partial" }
    - label: "Maturity"
      cells:
        greenpt: { type: "text", detail: "~2 years" }
        ecosia: { type: "text", detail: "~2 years (AI feature)" }
        euria: { type: "text", detail: "~4 months" }
        treadlightly: { type: "text", detail: "Pre-launch" }
    - label: "Web search"
      cells:
        greenpt: { type: "unknown" }
        ecosia: { type: "yes", detail: "Bing" }
        euria: { type: "yes" }
        treadlightly: { type: "yes", detail: "Opt-in" }
    - label: "Data jurisdiction"
      cells:
        greenpt: { type: "text", detail: "Swiss (FADP + GDPR)" }
        ecosia: { type: "text", detail: "German (GDPR)" }
        euria: { type: "text", detail: "Swiss (FADP + GDPR)" }
        treadlightly: { type: "text", detail: "US state laws" }
    - label: "Pricing (paid tier)"
      cells:
        greenpt: { type: "text", detail: "CHF 15/mo (~$17)" }
        ecosia: { type: "text", detail: "Free (ad-supported)" }
        euria: { type: "text", detail: "Free" }
        treadlightly: { type: "text", detail: "$3/mo" }
    - label: "Open-source models only"
      cells:
        greenpt: { type: "yes" }
        ecosia: { type: "no", detail: "GPT-4 mini is proprietary" }
        euria: { type: "yes" }
        treadlightly: { type: "no", detail: "Claude models are proprietary" }
  excluded_products:
    - name: "Viro AI"
      reason: "Wraps OpenAI and Anthropic APIs. Green claim is purchasing renewable energy credits after the fact, not running on renewable infrastructure."
    - name: "ChatGPTree"
      reason: "OpenAI API wrapper. Green mechanism is tree planting through a partner flagged for non-transparent practices. No findable privacy policy."
    - name: "Earthly Insight"
      reason: "Wraps OpenAI, Anthropic, and Google APIs. No renewable energy claims. Donates a share of revenue, but the AI itself runs on conventional infrastructure."
  footnotes:
    - subject: "GreenPT renewable energy"
      text: "Operated by Infomaniak (Swiss). ISO 14001 and ISO 50001 certified, audited annually by SGS. Swiss hydroelectric power."
    - subject: "Euria renewable energy"
      text: "Infomaniak Geneva data center. 100% waste heat recovery feeds Geneva district heating. PUE of 1.06 (European average ~1.8). No water cooling."
    - subject: "Ecosia financial transparency"
      text: "Publishes monthly financial reports. Structured as steward-ownership (German Verantwortungseigentum), legally cannot be sold or taken over, profits permanently committed to mission."
    - subject: "Ecosia energy display"
      text: "Shows a tree counter (how many trees your searches have funded) rather than per-query energy data. This is an engagement metric, not energy transparency."
    - subject: "Euria Chinese-origin models"
      text: "DeepSeek R1 and Qwen 3 have documented censorship of topics politically sensitive to the CCP. Running open-weight versions on Swiss infrastructure avoids sending data to China, but training biases are baked into the model weights."
    - subject: "GreenPT pricing"
      text: "CHF 15/month. No free tier. Price reflects Swiss hosting costs and employee-owned structure."
    - subject: "Euria pricing"
      text: "Free, subsidized by Infomaniak as a showcase for their AI infrastructure. Sustainability depends on continued subsidy."
    - subject: "Open-source models"
      text: "GreenPT and Euria use exclusively open-weight models, meaning the weights are publicly available and the providers control the full inference stack. TreadLightly and Ecosia use some proprietary models where inference runs on the provider's infrastructure."
    - subject: "TreadLightly AI"
      text: "Pre-launch product. Uses a mix of green-hosted (Infomaniak) and conventional (Anthropic/AWS) infrastructure. Energy estimates are modeled, not metered."
    - subject: "GreenPT green claims"
      text: "Cover inference-time energy only. Mistral models were trained on conventional infrastructure. This tension between green hosting and non-green training applies across the industry."
---
