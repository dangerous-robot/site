---
title: "Responsible AI Chatbots"
description: "Side-by-side comparison of AI chatbots that call themselves green or responsible: hosting, models, data use, ownership and cost, with the evidence behind each cell."
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
    - key: chatgptree
      name: ChatGPTree
      url: https://www.chatgptree.ai/
      entity: products/chatgptree
      status: active
      summary:
        ai_ethics: "Proprietary model (US), GPT-4"
        financial_transparency: "No published financials."
        environmental: "Conventional cloud hosting; funds tree planting via Evertreen and Veritree."
        notes:
          text: "REDD-Monitor called partner Evertreen's tree planting non-transparent (December 2025); Evertreen responded. Veritree is transparency-focused."
          sources: [/research/sources/2025/evertreen-non-transparent-tree-planting-and-dodgy-carbon-offs]
    - key: earthly-insight
      name: Earthly Insight
      url: https://www.earthlyinsight.com/
      entity: products/earthly-insight
      status: active
      summary:
        ai_ethics: "Proprietary models (US)."
        financial_transparency: "No published financials."
        environmental:
          text: "Conventional cloud hosting. 33% of revenue to Global Rewilding Alliance."
          sources: [/research/sources/2025/earthly-insight-joins-global-rewilding-champions]
        notes: "Launched October 2025."
    - key: ecosia
      name: Ecosia AI
      url: https://www.ecosia.org/ai-chat
      entity: products/ecosia-ai
      status: active
      summary:
        ai_ethics: "Proprietary model (US), GPT-4 mini."
        financial_transparency:
          text: "Non-profit steward-ownership; publishes financial reports."
          sources:
            - /research/sources/2025/ecosias-green-ai-alternative
            - /research/sources/2020/ecosia-financial-reports-and-tree-planting-receipts
        environmental: "Conventional cloud hosting; funds tree planting projects worldwide"
        notes: "Free, ad-supported."
    - key: euria
      name: Euria
      url: https://euria.infomaniak.com/
      entity: products/euria
      status: active
      summary:
        ai_ethics: "Open-weight models (US, EU, CN)."
        financial_transparency: "Infomaniak is a Swiss B Corp; no published financials."
        environmental:
          text: "Infomaniak data center (PUE 1.06, waste heat to district heating). 100% renewable energy."
          sources: [/research/sources/2026/infomaniaks-environmental-certificates-and-awards]
        notes:
          text: "Bold environmental commitments. Offsets 200% of its CO2 emissions through myclimate.org."
          sources:
            - /research/sources/2026/infomaniak-environmental-reducing-cloud-footprint
            - /research/sources/2026/infomaniaks-environmental-certificates-and-awards
    - key: greenpt
      name: GreenPT
      url: https://chat.greenpt.ai/
      entity: products/greenpt
      status: active
      summary:
        ai_ethics: "Open-weight models only."
        financial_transparency: "GreenPT BV, Netherlands; no published financials."
        environmental: "Hosted at Scaleway data center in France (PUE 1.37), powered by 100% renewable energy."
        notes: "Smaller, more efficient models."
    - key: treadlightly
      name: TreadLightlyAI
      url: https://treadlightly.ai/
      status: active
      # Q1: sources only; no claims are researched for the operator's own product.
      max_tier: source
      summary:
        ai_ethics: "Proprietary models (US) and open-weight models (US, FR)."
        financial_transparency: "Sole proprietorship; no published financials."
        environmental: "Infomaniak (PUE 1.06, waste heat to district heating) + Anthropic conventional cloud."
        notes: "Beta product from same founder as Dangerous Robot."
    - key: viro
      name: Viro AI
      url: https://ai.viro.app/
      entity: products/viro-ai
      status: active
      summary:
        ai_ethics: "Proprietary models (US) and open weight models (US, CN)."
        financial_transparency: "Solo-founder LLC; Viro Climate Action, Inc; no public disclosure."
        environmental:
          text: "Conventional cloud hosting; offsets via [Terrapass](https://en.wikipedia.org/wiki/TerraPass) RECs; methodology published."
          sources: [/research/sources/2026/viro-energy-and-impact-methodology]
        notes:
          text: "Partner Terrapass entered a California DFPI consent order in July 2025."
          sources: [/research/sources/2025/dfpi-secures-over-68500-in-consumer-refunds-from-carbon-credit-dealer]
  features:
    - key: renewable-hosting
      label: "Hosted on renewable energy"
      group: environmental
      criterion: renewable-energy-hosting
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "yes", sources: [/research/sources/2026/sustainability-renewable-ai-measured-impact-greenpt] }
        ecosia: { type: "no" }
        euria: { type: "yes", sources: [/research/sources/2025/euria-sovereign-ai-assistant-challenges-american-dominance] }
        treadlightly: { type: "partial", detail: "On Free, Starter and Builder plans", sources: [/research/sources/2026/treadlightlyai-think-for-yourself-prompt-light] }
        viro: { type: "no" }
        chatgptree: { type: "no" }
        earthly-insight: { type: "no" }
    - key: real-time-energy-display
      label: "Real-time energy display"
      group: environmental
      criterion: realtime-energy-display
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "yes", sources: [/research/sources/2026/how-energy-indicator-works] }
        ecosia: { type: "no" }
        euria: { type: "no" }
        treadlightly: { type: "yes", sources: [/research/sources/2026/treadlightlyai-think-for-yourself-prompt-light] }
        viro: { type: "yes" }
        chatgptree: { type: "no" }
        earthly-insight: { type: "no" }
    - key: no-image-generation
      label: "No image generation"
      group: environmental
      criterion: excludes-image-generation
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "yes" }
        ecosia: { type: "no", detail: "Generates images for logged-in users", sources: [/research/sources/2026/generative-ai-on-ecosia-search] }
        euria: { type: "yes" }
        treadlightly: { type: "yes", sources: [/research/sources/2026/treadlightlyai-think-for-yourself-prompt-light] }
        viro: { type: "no", sources: [/research/sources/2026/viro-eco-friendly-ai-app] }
        chatgptree: { type: "yes" }
        earthly-insight: { type: "yes" }
    - key: financial-transparency
      label: "Published financials"
      group: business
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "no" }
        ecosia: { type: "yes", sources: [/research/sources/2020/ecosia-financial-reports-and-tree-planting-receipts] }
        euria: { type: "no"}
        treadlightly: { type: "no" }
        viro: { type: "no" }
        chatgptree: { type: "no" }
        earthly-insight: { type: "no" }
    - key: models
      label: "Models"
      group: models-safety
      ideal:
        answer: "no large models"
        # Sorted under P5 and R2 (a model is large if it was its lab's most
        # capable tier when released). Each lab's model page is cited below;
        # GPT-OSS still has none, so the list carries no last_checked date.
        large_models:
          sources:
            - /research/sources/2026/gpt-4o-model-documentation
            - /research/sources/2026/gpt-5-6-terra-model-documentation
            - /research/sources/2026/anthropic-claude-models-overview
            - /research/sources/2026/google-gemini-api-models
            - /research/sources/2026/gemma-4-model-overview
            - /research/sources/2026/mistral-ai-models-overview
          large: [GPT-4o, Gemini Pro]
          not_large: [Mistral Small, GPT-OSS, Gemma 4, Claude Haiku, Claude Sonnet, Gemini Flash, GPT-5.6 Terra]
      cells:
        greenpt: { type: "text", detail: "Mistral Small, GPT-OSS, Gemma 4", models: [Mistral Small, GPT-OSS, Gemma 4], sources: [/research/sources/2026/greenpt-privacy-first-ai-with-measured-energy-and-carbon] }
        ecosia: { type: "text", detail: "Mistral", sources: [/research/sources/2026/generative-ai-on-ecosia-search] }
        euria: { type: "text", detail: "DeepSeek R1, Qwen 3, Mistral Nemo, Llama 3" }
        treadlightly: { type: "text", detail: "Gemma 4, GPT-OSS, Claude Haiku & Sonnet", models: [Gemma 4, GPT-OSS, Claude Haiku, Claude Sonnet], sources: [/research/sources/2026/about-treadlightly-ai] }
        viro: { type: "text", detail: "GPT, Claude, Gemini, LLaMA" }
        chatgptree: { type: "text", detail: "GPT-4o", models: [GPT-4o], sources: [/research/sources/2025/eco-friendly-chatgptree-sustainable-ai-chatbot] }
        earthly-insight: { type: "text", detail: "GPT-5.6 Terra, Claude Sonnet, Gemini Pro & Flash", models: [GPT-5.6 Terra, Claude Sonnet, Gemini Pro, Gemini Flash], sources: [/research/sources/2026/earthly-insight-app-ai] }
    - key: data-used-for-training
      label: "Data used for training"
      group: privacy-data
      criterion: no-training-on-user-data
      polarity: inverted
      ideal: { value: "no" }
      cells:
        greenpt: { type: "no", sources: [/research/sources/2026/privacy-policy-greenpt-eu-hosted-no-training-on-your-data] }
        ecosia: { type: "no" }
        euria: { type: "no", sources: [/research/sources/2025/euria-sovereign-ai-assistant-challenges-american-dominance] }
        treadlightly: { type: "no", sources: [/research/sources/2026/treadlightly-privacy-policy] }
        viro: { type: "no", detail: "Ads may be based on the current message", sources: [/research/sources/2025/viro-ai-privacy-policy-2025] }
        chatgptree: { type: "unknown" }
        earthly-insight: { type: "unknown" }
    - key: corporate-structure
      label: "Ownership structure"
      group: business
      criterion: corporate-structure
      ideal:
        answer: "non-profit or similar"
        terms:
          good: [non-profit, steward-ownership, cooperative, B-corp, employee-owned]
          mixed: [privately-held]
          bad: [publicly-traded]
      cells:
        greenpt: { type: "text", detail: "Private", term: privately-held, sources: [/research/sources/2026/greenpt-terms-of-service] }
        ecosia: { type: "text", detail: "Non-profit, Steward-ownership", term: steward-ownership, sources: [/research/sources/2018/ecosia-commits-to-trees-not-profits] }
        euria: { type: "text", detail: "B Corp", term: B-corp, sources: [/research/sources/2025/infomaniak-becomes-a-b-corp-certified-company] }
        treadlightly: { type: "text", detail: "Sole proprietorship", term: privately-held }
        viro: { type: "text", detail: "Solo-founder LLC", term: privately-held }
        chatgptree: { type: "text", detail: "Private", term: privately-held }
        earthly-insight: { type: "text", detail: "LLC", term: privately-held, sources: [/research/sources/2026/earthly-insight-app-ai] }
    - key: free-tier
      label: "Free tier"
      group: business
      cells:
        greenpt: { type: "yes" }
        ecosia: { type: "yes", detail: "Ad supported"}
        euria: { type: "yes", sources: [/research/sources/2025/euria-sovereign-ai-assistant-challenges-american-dominance] }
        treadlightly: { type: "yes", sources: [/research/sources/2026/treadlightly-ai-pricing] }
        viro: { type: "yes", detail: "Ad supported", sources: [/research/sources/2026/viro-eco-friendly-ai-app] }
        chatgptree: { type: "yes" }
        earthly-insight: { type: "yes", sources: [/research/sources/2026/earthly-insight-app-ai] }
    - key: pricing-paid-tier
      label: "Pricing"
      group: business
      cells:
        greenpt: { type: "text", detail: "€ 4.50 | 17.50 /mo", sources: [/research/sources/2026/greenpt-privacy-first-ai-with-measured-energy-and-carbon] }
        ecosia: { type: "text", detail: "n/a" }
        euria: { type: "text", detail: "€ 1.58 /mo includes [kSuite Pro](https://www.infomaniak.com/en/ksuite)" }
        treadlightly: { type: "text", detail: "$ 3 | 8 | 20 /mo", sources: [/research/sources/2026/treadlightly-ai-pricing] }
        viro: { type: "text", detail: "$ 1 | 10 /mo" }
        chatgptree: { type: "text", detail: "$ 11 /mo", sources: [/research/sources/2025/eco-friendly-chatgptree-sustainable-ai-chatbot] }
        earthly-insight: { type: "text", detail: "$ 23 /mo", sources: [/research/sources/2026/earthly-insight-app-ai] }
    - key: maturity
      label: "Maturity"
      group: business
      # Launch month and year, each from a source that states it; without
      # one the cell says so rather than guessing.
      cells:
        greenpt: { type: "text", detail: "Not yet sourced" }
        ecosia: { type: "text", detail: "Launched Oct 2023 (beta)", sources: [/research/sources/2023/new-ecosia-search-features] }
        euria: { type: "text", detail: "Launched Dec 2025", sources: [/research/sources/2025/euria-sovereign-ai-assistant-challenges-american-dominance] }
        treadlightly: { type: "text", detail: "Not yet sourced" }
        viro: { type: "text", detail: "Not yet sourced" }
        chatgptree: { type: "text", detail: "Not yet sourced" }
        earthly-insight: { type: "text", detail: "Not yet sourced" }
    - key: image-and-document-analysis
      label: "Image and document analysis"
      group: product-access
      cells:
        greenpt: { type: "yes", sources: [/research/sources/2026/greenpt-privacy-first-ai-with-measured-energy-and-carbon] }
        ecosia: { type: "yes", sources: [/research/sources/2026/generative-ai-on-ecosia-search] }
        euria: { type: "yes", sources: [/research/sources/2025/euria-sovereign-ai-assistant-challenges-american-dominance] }
        treadlightly: { type: "yes", sources: [/research/sources/2026/treadlightly-ai-pricing] }
        viro: { type: "yes", sources: [/research/sources/2026/viro-eco-friendly-ai-app] }
        chatgptree: { type: "no" }
        earthly-insight: { type: "yes", detail: "Images", sources: [/research/sources/2026/earthly-insight-app-ai] }
    - key: agent-web-search
      label: "Agent Web search"
      group: product-access
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
      answers: ["yes", partial, unknown]
      ideal: { value: "yes" }
      # No product publishes an accessibility statement (searched
      # 2026-10-10). Each cell is Partial because a Lighthouse 13.5.0
      # accessibility audit of the product's public page found failures
      # (P4, "barriers found by our check"); the pages and failures are
      # recorded in the plan's S10 result so the check can be repeated.
      cells:
        greenpt: { type: partial, detail: "Mixed support", last_checked: "2026-10-10" }
        ecosia: { type: partial, detail: "Mixed support", last_checked: "2026-10-10" }
        euria: { type: partial, detail: "Mixed support", last_checked: "2026-10-10" }
        treadlightly: { type: partial, detail: "Mixed support", last_checked: "2026-10-10" }
        viro: { type: partial, detail: "Mixed support", last_checked: "2026-10-10" }
        chatgptree: { type: partial, detail: "Mixed support", last_checked: "2026-10-10" }
        earthly-insight: { type: partial, detail: "Mixed support", last_checked: "2026-10-10" }
    - key: data-jurisdiction
      label: "Data jurisdiction"
      group: privacy-data
      cells:
        greenpt: { type: "text", detail: "EU (GDPR)", sources: [/research/sources/2026/privacy-policy-greenpt-eu-hosted-no-training-on-your-data] }
        ecosia: { type: "text", detail: "EU (GDPR)", sources: [/research/sources/2026/generative-ai-on-ecosia-search] }
        euria: { type: "text", detail: "Swiss (FADP + GDPR)", sources: [/research/sources/2026/euria-sovereign-ai-assistant-infomaniak] }
        treadlightly: { type: "text", detail: "US" }
        viro: { type: "text", detail: "US", sources: [/research/sources/2025/viro-ai-terms-conditions] }
        chatgptree: { type: "text", detail: "US", sources: [/research/sources/2020/terms-of-use-chatgptree] }
        earthly-insight: { type: text, detail: "US" }
    - key: open-source-models-only
      label: "Open-weight models"
      group: models-safety
      ideal: { value: "yes" }
      cells:
        greenpt: { type: "yes", sources: [/research/sources/2026/greenpt-privacy-first-ai-with-measured-energy-and-carbon] }
        ecosia: { type: "no" }
        euria: { type: "yes", sources: [/research/sources/2026/euria-sovereign-ai-assistant-infomaniak] }
        treadlightly: { type: "partial", detail: "Claude on Advanced", sources: [/research/sources/2026/about-treadlightly-ai] }
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

"Green AI" gets thrown around a lot. This page lays out what each product actually offers, side-by-side, so you can compare. If you spot an error or omission, [let us know](/corrections).

<p class="resource-matrix__disclosure">TreadLightlyAI is made by the same person who makes Dangerous Robot. It is listed under the same criteria and sources as every other product, and we publish no verdict on claims about it.</p>
