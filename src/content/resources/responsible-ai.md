---
title: "Responsible AI Chatbots"
description: "Side-by-side comparison of responsible AI chatbots: GreenPT, Ecosia AI, Euria, and TreadLightlyAI on privacy, sustainability, and transparency."
pubDate: 2026-03-06
layout: matrix
wallpaper: responsible-ai
topics:
  - responsible-ai
  - consumer-guide
data:
  caption: "Data gathered from public sources as of April 2026. If something is wrong, let us know."
  groups:
    - key: environmental
      label: "Environmental"
    - key: models-safety
      label: "Models & AI safety"
    - key: privacy-data
      label: "Privacy & data"
    - key: business
      label: "Business & ownership"
    - key: product-access
      label: "Product & access"
  products:
    - key: greenpt
      name: GreenPT
      url: https://chat.greenpt.ai/
      status: active
      summary:
        ai_ethics: "Open-weight models only."
        financial_transparency: "GreenPT BV, Netherlands; no published financials."
        environmental: "Hosted at Scaleway data center in France (PUE 1.37), powered by 100% renewable energy."
        notes: "Smaller, more efficient models."
    - key: ecosia
      name: Ecosia AI
      url: https://blog.ecosia.org/ecosia-ai/
      status: active
      summary:
        ai_ethics: "Wraps OpenAI's GPT-4 mini; proprietary model."
        financial_transparency: "Non-profit under German [steward-ownership](https://blog.ecosia.org/ecosia-ai/); monthly financial reports published."
        environmental: "Conventional cloud hosting; tree counter is an engagement metric, not energy data."
        notes: "Free, ad-supported; revenue funds tree planting rather than greener inference."
    - key: euria
      name: Euria
      url: https://euria.ai/
      status: active
      summary:
        ai_ethics: "Open-weight models (DeepSeek, Qwen, Mistral, Llama); Chinese-origin models carry specific training biases."
        financial_transparency: "Infomaniak is a B Corp; no published financials."
        environmental: "Hosted on Infomaniak's Geneva data center (PUE 1.06, waste heat to district heating). Powered by 100% renewable energy."
        notes: "Bold [environmental committments](https://www.infomaniak.com/en/ecology/commitments). Certified by myClimate.org for 10 years."
    - key: treadlightly
      name: TreadLightlyAI
      url: https://treadlightly.ai/
      status: active
      summary:
        ai_ethics: "Mix of open-weight (Mistral, GPT-oss) and proprietary (Claude) models; publishes AI limitations."
        financial_transparency: "Sole proprietorship; no published financials."
        environmental: "Primary host is Infomaniak's Geneva data center (PUE 1.06, waste heat to district heating) which is powered by 100% renewable energy. Anthropic/AWS hosting for Claude. Energy estimates modeled, not metered."
        notes: "Beta product from same founder as Dangerous Robot."
    - key: viro
      name: Viro AI
      url: https://ai.viro.app/
      status: active
      initially_hidden: true
      summary:
        ai_ethics: "Thin wrapper over OpenAI, Anthropic, Google, and Meta APIs; no own inference."
        financial_transparency: "Solo-founder LLC; no public disclosure."
        environmental: "Conventional cloud hosting; offsets via [Terrapass](https://en.wikipedia.org/wiki/TerraPass) Green-e wind RECs after the fact."
        notes: "Launched October 2025; iOS and Android; partner Terrapass entered a [California DFPI consent order](https://dfpi.ca.gov/press_release/dfpi-secures-over-68500-in-consumer-refunds-from-carbon-credit-dealer/) in July 2025."
    - key: chatgptree
      name: ChatGPTree
      url: https://www.chatgptree.ai/
      status: active
      initially_hidden: true
      summary:
        ai_ethics: "OpenAI API wrapper (GPT-4 series); marketing not endorsed by OpenAI."
        financial_transparency: "No published financials."
        environmental: "Conventional cloud hosting; funds tree planting via Evertreen and Veritree."
        notes: "Launched June 2025; $11/mo plants one tree per month; Evertreen partner [flagged for non-transparent practices](https://redmonitor.substack.com/p/evertreen-non-transparent-tree-planting), Veritree is transparency-focused."
    - key: earthly-insight
      name: Earthly Insight
      url: https://www.earthlyinsight.com/
      status: active
      initially_hidden: true
      summary:
        ai_ethics: "Wraps OpenAI, Anthropic, and Google APIs (GPT-4.1, Gemini 2.5, Claude 3.5 Sonnet)."
        financial_transparency: "Bootstrapped LLC, no investors; donation flow not independently audited."
        environmental: "Conventional cloud hosting."
        notes: "Launched October 2025; donates [33% of premium revenue](https://globalrewilding.earth/earthly-insight-joins-our-global-rewilding-champions/) to Global Rewilding Alliance and partners; $20/mo premium tier."
  features:
    - key: renewable-hosting
      label: "Hosted on renewable energy"
      group: environmental
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "yes" }
        ecosia: { type: "no" }
        euria: { type: "yes" }
        treadlightly: { type: "partial", detail: "All but Anthropic" }
        viro: { type: "no", detail: "Post-hoc REC purchases" }
        chatgptree: { type: "no" }
        earthly-insight: { type: "no" }
    - key: real-time-energy-display
      label: "Real-time energy display"
      group: environmental
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "yes" }
        ecosia: { type: "no" }
        euria: { type: "no" }
        treadlightly: { type: "yes" }
        viro: { type: "yes", detail: "Per-query Wh from token counts" }
        chatgptree: { type: "no" }
        earthly-insight: { type: "no" }
    - key: no-image-generation
      label: "No image generation"
      group: environmental
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "yes" }
        ecosia: { type: "yes" }
        euria: { type: "yes" }
        treadlightly: { type: "yes" }
        viro: { type: "unknown" }
        chatgptree: { type: "unknown" }
        earthly-insight: { type: "unknown" }
    - key: financial-transparency
      label: "Published financials"
      group: business
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "partial", detail: "Employee-owned" }
        ecosia: { type: "yes", detail: "Non-profit" }
        euria: { type: "partial", detail: "B Corp" }
        treadlightly: { type: "partial", detail: "Pre-launch" }
        viro: { type: "no" }
        chatgptree: { type: "no" }
        earthly-insight: { type: "no", detail: "No audit or 990 located" }
    - key: models
      label: "Models"
      group: models-safety
      cells:
        greenpt: { type: "text", detail: "Mistral Small, GPT-OSS" }
        ecosia: { type: "text", detail: "GPT-4 mini" }
        euria: { type: "text", detail: "DeepSeek R1, Qwen 3, Mistral Nemo, Llama 3.3" }
        treadlightly: { type: "text", detail: "Mistral Ministral, Mistral Small, GPT-OSS, Claude Haiku, Claude Sonnet" }
        viro: { type: "text", detail: "GPT, Claude, Gemini, LLaMA" }
        chatgptree: { type: "text", detail: "GPT-4 series" }
        earthly-insight: { type: "text", detail: "GPT-4.1, Gemini 2.5, Claude 3.5 Sonnet" }
    - key: image-and-document-analysis
      label: "Image and document analysis"
      group: product-access
      cells:
        greenpt: { type: "yes" }
        ecosia: { type: "no" }
        euria: { type: "yes" }
        treadlightly: { type: "yes" }
        viro: { type: "unknown" }
        chatgptree: { type: "unknown" }
        earthly-insight: { type: "unknown" }
    - key: data-used-for-training
      label: "Data used for training"
      group: privacy-data
      ideal: { value: "no-good" }
      cells:
        greenpt: { type: "no-good" }
        ecosia: { type: "unknown" }
        euria: { type: "no-good" }
        treadlightly: { type: "no-good" }
        viro: { type: "unknown" }
        chatgptree: { type: "unknown" }
        earthly-insight: { type: "unknown" }
    - key: published-ai-limitations
      label: "Published AI limitations"
      group: models-safety
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "partial" }
        ecosia: { type: "partial" }
        euria: { type: "no" }
        treadlightly: { type: "yes" }
        viro: { type: "unknown" }
        chatgptree: { type: "unknown" }
        earthly-insight: { type: "unknown" }
    - key: corporate-structure
      label: "Ownership structure"
      group: business
      cells:
        greenpt: { type: "text", detail: "Employee-owned" }
        ecosia: { type: "text", detail: "Steward-ownership" }
        euria: { type: "text", detail: "Employee-controlled, B Corp" }
        treadlightly: { type: "text", detail: "Private" }
        viro: { type: "text", detail: "Solo-founder LLC" }
        chatgptree: { type: "text", detail: "Private" }
        earthly-insight: { type: "text", detail: "Bootstrapped LLC" }
    - key: free-tier
      label: "Free tier"
      group: product-access
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "yes" }
        ecosia: { type: "yes" }
        euria: { type: "yes" }
        treadlightly: { type: "yes" }
        viro: { type: "unknown" }
        chatgptree: { type: "unknown" }
        earthly-insight: { type: "unknown" }
    - key: accessibility
      label: "Accessibility"
      group: product-access
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "partial" }
        ecosia: { type: "partial" }
        euria: { type: "partial" }
        treadlightly: { type: "partial" }
        viro: { type: "unknown" }
        chatgptree: { type: "unknown" }
        earthly-insight: { type: "unknown" }
    - key: maturity
      label: "Maturity"
      group: product-access
      cells:
        greenpt: { type: "text", detail: "~2 years" }
        ecosia: { type: "text", detail: "~2 years (AI feature)" }
        euria: { type: "text", detail: "~4 months" }
        treadlightly: { type: "text", detail: "Pre-launch" }
        viro: { type: "text", detail: "~7 months" }
        chatgptree: { type: "text", detail: "~11 months" }
        earthly-insight: { type: "text", detail: "~7 months" }
    - key: web-search
      label: "Web search"
      group: product-access
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "unknown" }
        ecosia: { type: "yes", detail: "Bing" }
        euria: { type: "yes" }
        treadlightly: { type: "yes", detail: "Opt-in" }
        viro: { type: "unknown" }
        chatgptree: { type: "unknown" }
        earthly-insight: { type: "unknown" }
    - key: data-jurisdiction
      label: "Data jurisdiction"
      group: privacy-data
      cells:
        greenpt: { type: "text", detail: "Swiss (FADP + GDPR)" }
        ecosia: { type: "text", detail: "German (GDPR)" }
        euria: { type: "text", detail: "Swiss (FADP + GDPR)" }
        treadlightly: { type: "text", detail: "US state laws" }
        viro: { type: "unknown" }
        chatgptree: { type: "text", detail: "US state laws" }
        earthly-insight: { type: "unknown" }
    - key: pricing-paid-tier
      label: "Pricing (paid tier)"
      group: business
      cells:
        greenpt: { type: "text", detail: "CHF 15/mo (~$17)" }
        ecosia: { type: "text", detail: "Free (ad-supported)" }
        euria: { type: "text", detail: "Free" }
        treadlightly: { type: "text", detail: "$3/mo" }
        viro: { type: "unknown" }
        chatgptree: { type: "text", detail: "$11/mo" }
        earthly-insight: { type: "text", detail: "$20/mo" }
    - key: open-source-models-only
      label: "Open-source models only"
      group: models-safety
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "yes" }
        ecosia: { type: "no", detail: "GPT-4 mini is proprietary" }
        euria: { type: "yes" }
        treadlightly: { type: "no", detail: "Claude models are proprietary" }
        viro: { type: "no", detail: "OpenAI, Anthropic, Google are proprietary" }
        chatgptree: { type: "no", detail: "GPT-4 series is proprietary" }
        earthly-insight: { type: "no", detail: "OpenAI, Anthropic, Google are proprietary" }
  footnotes:
    - subject: "GreenPT renewable energy"
      text: "Operated by Infomaniak (Swiss). ISO 14001 and ISO 50001 certified, audited annually by SGS. Swiss hydroelectric power."
    - subject: "Euria renewable energy"
      text: "Owned and operated by Infomaniak at their Geneva data center. 100% waste heat recovery feeds Geneva district heating. PUE of 1.06 (European average ~1.8). No water cooling."
    - subject: "Ecosia financial transparency"
      text: "Publishes monthly financial reports. Structured as steward-ownership (German Verantwortungseigentum), legally cannot be sold or taken over, profits permanently committed to mission."
    - subject: "Ecosia energy display"
      text: "Shows a tree counter (how many trees your searches have funded) rather than per-query energy data. This is an engagement metric, not energy transparency."
    - subject: "Euria Chinese-origin models"
      text: "DeepSeek R1 and Qwen 3 have documented censorship of topics politically sensitive to the CCP. Running open-weight versions on Swiss infrastructure avoids sending data to China, but training biases are baked into the model weights."
    - subject: "GreenPT pricing"
      text: "CHF 15/month. No free tier. Price reflects Swiss hosting costs and employee-owned structure."
    - subject: "Euria pricing"
      text: "Free, subsidized by Infomaniak as a showcase for their AI infrastructure."
    - subject: "Open-source models"
      text: "GreenPT and Euria use exclusively open-weight models, meaning the weights are publicly available and the providers control the full inference stack. TreadLightlyAI and Ecosia use some proprietary models where inference runs on the provider's infrastructure."
    - subject: "TreadLightlyAI"
      text: "Pre-launch product. Uses a mix of green-hosted (Infomaniak) and conventional (Anthropic/AWS) infrastructure. Energy estimates are modeled, not metered."
    - subject: "GreenPT green claims"
      text: "Cover inference-time energy only. Mistral models were trained on conventional infrastructure. This tension between green hosting and non-green training applies across the industry."
---
