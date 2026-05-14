---
title: "Responsible AI Chatbots"
description: "Side-by-side comparison of responsible AI chatbots: GreenPT, Ecosia AI, Euria, and TreadLightlyAI on privacy, sustainability, and transparency."
pubDate: 2026-03-06
layout: matrix
wallpaper: none
topics:
  - responsible-ai
  - consumer-guide
data:
  caption: "Data gathered from public sources and direct research. If something is wrong, let us know."
  groups:
    - key: environmental
      label: "Environmental"
    - key: models-safety
      label: "Models & AI safety"
    - key: product-access
      label: "Product Features"
    - key: privacy-data
      label: "Privacy & data"
    - key: business
      label: "Business & cost"
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
    - key: euria
      name: Euria
      url: https://euria.infomaniak.com/
      status: active
      summary:
        ai_ethics: "Open-weight models (US, EU, CN)."
        financial_transparency: "Infomaniak is a Swiss B Corp; no published financials."
        environmental: "Infomaniak data center (PUE 1.06, waste heat to district heating). 100% renewable energy.
        [Receipts](https://www.infomaniak.com/en/ecology/certificates-rewards)"
        notes: "Bold [environmental committments](https://www.infomaniak.com/en/ecology/commitments). Certified by myClimate.org."
    - key: ecosia
      name: Ecosia AI
      url: https://www.ecosia.org/ai-chat
      status: active
      summary:
        ai_ethics: "Proprietary model (US), GPT-4 mini."
        financial_transparency: "Non-profit [steward-ownership](https://blog.ecosia.org/ecosia-ai/); publishes [financial reports](https://blog.ecosia.org/ecosia-financial-reports-tree-planting-receipts/)."
        environmental: "Conventional cloud hosting; funds tree planting projects worldwide"
        notes: "Free, ad-supported."
    - key: treadlightly
      name: TreadLightlyAI
      url: https://treadlightly.ai/
      status: active
      summary:
        ai_ethics: "Proprietary models (US) and open-weight models (US, FR)."
        financial_transparency: "Sole proprietorship; no published financials."
        environmental: "Infomaniak (PUE 1.06, waste heat to district heating) + Anthropic conventional cloud."
        notes: "Beta product from same founder as Dangerous Robot."
    - key: chatgptree
      name: ChatGPTree
      url: https://www.chatgptree.ai/
      status: active
      summary:
        ai_ethics: "Proprietary model (US), GPT-4"
        financial_transparency: "No published financials."
        environmental: "Conventional cloud hosting; funds tree planting via Evertreen and Veritree."
        notes: "Evertreen partner [flagged for non-transparent practices](https://redmonitor.substack.com/p/evertreen-non-transparent-tree-planting), Veritree is transparency-focused."
    - key: earthly-insight
      name: Earthly Insight
      url: https://www.earthlyinsight.com/
      status: active
      summary:
        ai_ethics: "Proprietary models (US)."
        financial_transparency: "No published financials."
        environmental: "Conventional cloud hosting. 33% of revenue to [Global Rewilding Alliance](https://globalrewilding.earth/earthly-insight-joins-our-global-rewilding-champions/)"
        notes: "Launched October 2025."
    - key: viro
      name: Viro AI
      url: https://ai.viro.app/
      status: active
      summary:
        ai_ethics: "Proprietary models (US) and open weight models (US, CN)."
        financial_transparency: "Solo-founder LLC; Viro Climate Action, Inc; no public disclosure."
        environmental: "Conventional cloud hosting; offsets via [Terrapass](https://en.wikipedia.org/wiki/TerraPass) RECs; methodology [published](https://www.viro.app/energy-and-impact-methodology)."
        notes: "Partner Terrapass entered a [California DFPI consent order](https://dfpi.ca.gov/press_release/dfpi-secures-over-68500-in-consumer-refunds-from-carbon-credit-dealer/) in July 2025."
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
        viro: { type: "no" }
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
        viro: { type: "yes" }
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
        viro: { type: "no" }
        chatgptree: { type: "yes" }
        earthly-insight: { type: "yes" }
    - key: financial-transparency
      label: "Published financials"
      group: business
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "no" }
        ecosia: { type: "yes"}
        euria: { type: "no"}
        treadlightly: { type: "no" }
        viro: { type: "no" }
        chatgptree: { type: "no" }
        earthly-insight: { type: "no" }
    - key: models
      label: "Models"
      group: models-safety
      cells:
        greenpt: { type: "text", detail: "Mistral Small, GPT-OSS" }
        ecosia: { type: "text", detail: "GPT mini" }
        euria: { type: "text", detail: "DeepSeek R1, Qwen 3, Mistral Nemo, Llama 3" }
        treadlightly: { type: "text", detail: "Mistral Ministral & Small, GPT-OSS, Claude Haiku & Sonnet" }
        viro: { type: "text", detail: "GPT, Claude, Gemini, LLaMA" }
        chatgptree: { type: "text", detail: "GPT" }
        earthly-insight: { type: "text", detail: "GPT, Gemini Flash & Pro, Claude Sonnet" }
    - key: data-used-for-training
      label: "Data used for training"
      group: privacy-data
      ideal: { value: "no-good" }
      cells:
        greenpt: { type: "no-good" }
        ecosia: { type: "no-good" }
        euria: { type: "no-good" }
        treadlightly: { type: "no-good" }
        viro: { type: "no-good", detail: "Ads based on chat content"  }
        chatgptree: { type: "unknown", detail: "[probably?](https://www.chatgptree.ai/legal/privacy#how-we-use-info)" }
        earthly-insight: { type: "unknown", detail: "[probably not?](https://www.earthlyinsight.ai/privacy-policy)" }
    - key: corporate-structure
      label: "Ownership structure"
      group: business
      cells:
        greenpt: { type: "text", detail: "Private" }
        ecosia: { type: "text", detail: "Non-profit, Steward-ownership" }
        euria: { type: "text", detail: "B Corp" }
        treadlightly: { type: "text", detail: "Sole proprietorship" }
        viro: { type: "text", detail: "Solo-founder LLC" }
        chatgptree: { type: "text", detail: "Private" }
        earthly-insight: { type: "text", detail: "Bootstrapped LLC" }
    - key: free-tier
      label: "Free tier"
      group: business
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "yes" }
        ecosia: { type: "yes", detail: "Ad supported"}
        euria: { type: "yes", detail: "includes [kSuite](https://www.infomaniak.com/en/ksuite)" }
        treadlightly: { type: "yes" }
        viro: { type: "yes", detail: "Ad supported" }
        chatgptree: { type: "yes" }
        earthly-insight: { type: "yes" }
    - key: pricing-paid-tier
      label: "Pricing"
      group: business
      cells:
        greenpt: { type: "text", detail: "€ 4.50 | 17.50 /mo" }
        ecosia: { type: "text", detail: "n/a" }
        euria: { type: "text", detail: "€ 1.58 /mo includes [kSuite Pro](https://www.infomaniak.com/en/ksuite)" }
        treadlightly: { type: "text", detail: "$ 3 | 8 | 20 /mo" }
        viro: { type: "text", detail: "$ 1 | 10 /mo" }
        chatgptree: { type: "text", detail: "$ 11 /mo" }
        earthly-insight: { type: "text", detail: "$ 20 /mo" }
    - key: maturity
      label: "Maturity"
      group: business
      cells:
        greenpt: { type: "text", detail: "2 years" }
        ecosia: { type: "text", detail: "2 years (AI feature)" }
        euria: { type: "text", detail: "6 months" }
        treadlightly: { type: "text", detail: "2 months (Beta)" }
        viro: { type: "text", detail: "9 months" }
        chatgptree: { type: "text", detail: "1 year" }
        earthly-insight: { type: "text", detail: "9 months" }
    - key: image-and-document-analysis
      label: "Image and document analysis"
      group: product-access
      cells:
        greenpt: { type: "yes" }
        ecosia: { type: "no" }
        euria: { type: "yes" }
        treadlightly: { type: "yes" }
        viro: { type: "yes" }
        chatgptree: { type: "no" }
        earthly-insight: { type: "yes" }
    - key: agent-web-search
      label: "Agent Web search"
      group: product-access
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "yes" }
        ecosia: { type: "yes" }
        euria: { type: "yes" }
        treadlightly: { type: "yes" }
        viro: { type: "no" }
        chatgptree: { type: "no" }
        earthly-insight: { type: "no" }
    - key: web-search
      label: "Normal Web search"
      group: product-access
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "no" }
        ecosia: { type: "yes" }
        euria: { type: "no" }
        treadlightly: { type: "yes" }
        viro: { type: "yes" }
        chatgptree: { type: "no" }
        earthly-insight: { type: "no" }
    - key: accessibility
      label: "Accessibility"
      group: product-access
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "yes", detail: "Level A" }
        ecosia: { type: "yes", detail: "Level AA+" }
        euria: { type: "partial" }
        treadlightly: { type: "yes", detail: "Level AA+" }
        viro: { type: "partial" }
        chatgptree: { type: "partial" }
        earthly-insight: { type: "yes", detail: "Level A" }
    - key: data-jurisdiction
      label: "Data jurisdiction"
      group: privacy-data
      cells:
        greenpt: { type: "text", detail: "Swiss (FADP + GDPR)" }
        ecosia: { type: "text", detail: "German (GDPR)" }
        euria: { type: "text", detail: "Swiss (FADP + GDPR)" }
        treadlightly: { type: "text", detail: "US" }
        viro: { type: "text", detail: "US" }
        chatgptree: { type: "text", detail: "US" }
        earthly-insight: { type: text, detail: "US" }
    - key: open-source-models-only
      label: "Open-source models"
      group: models-safety
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "yes" }
        ecosia: { type: "no" }
        euria: { type: "yes" }
        treadlightly: { type: "partial", detail: "Claude is proprietary" }
        viro: { type: "partial" }
        chatgptree: { type: "no" }
        earthly-insight: { type: "no" }
  footnotes:
    - subject: "Ecosia energy display"
      text: "Shows a tree counter (how many trees your searches have funded) rather than per-query energy data. This is an engagement metric, not energy transparency."
    - subject: "Euria Chinese-origin models"
      text: "DeepSeek R1 and Qwen 3 have documented censorship of topics politically sensitive to the CCP. Running open-weight versions on Swiss infrastructure avoids sending data to China, but training biases are baked into the model weights."
    - subject: "GreenPT green claims"
      text: "Cover inference-time energy only. Mistral models were trained on conventional infrastructure. This tension between green hosting and non-green training applies across the industry."
---

"Green AI" gets thrown around a lot. This page lays out what each product actually offers, side-by-side, so you can compare. If you spot an error or omission, [let us know](mailto:info@dangerousrobot.org).

<p class="resource-matrix__disclosure">FULL DISCLOSURE: Dangerous Robot is sponsored by TreadLightlyAI.</p>
