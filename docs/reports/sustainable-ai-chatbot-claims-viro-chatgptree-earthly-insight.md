# Verification of Three "Sustainable AI" Chatbot Claims

> Transcribed from the source PDF `sustainable-ai-chatbot-claims-viro-chatgptree-earthly-insight.pdf` (image-based, 10 pages). This Markdown is the committed, diff-able record; the original PDF is not tracked in git.

## TL;DR

- **Claim 1 (Viro AI):** Substantively accurate — Viro is real, it does wrap OpenAI/Anthropic (and Google/Meta) APIs, and its "green" mechanism is buying Green-e wind Renewable Energy Certificates via Terrapass to *match* query energy after the fact, not running inference on renewable infrastructure. **High confidence.**
- **Claim 2 (ChatGPTree):** Mostly accurate but **the privacy-policy half is wrong** — ChatGPTree is a real OpenAI/GPT-4o wrapper that uses tree-planting (via Evertreen, which has been credibly flagged for non-transparency, plus Veritree, which has not). A privacy policy *is* findable at chatgptree.ai/legal/privacy (last updated Oct 2025), even though the secondary chatgptree.org site still says "coming soon." **High confidence overall, with the privacy claim contradicted.**
- **Claim 3 (Earthly Insight):** Accurate on every point — real product, wraps OpenAI/Anthropic/Google APIs, makes no renewable-energy claims, donates 33% of revenue (primarily to the Global Rewilding Alliance), and runs on conventional third-party cloud infrastructure. **High confidence.**

---

## Key Findings

1. All three products **exist as real, currently-listed chatbot offerings**, each with iOS/Android apps and active websites. None is fictitious.
2. All three are **thin wrappers over the same major frontier-model APIs** (OpenAI's GPT, Anthropic's Claude, Google's Gemini; Viro also adds Meta's LLaMA). None operates its own model or has its own inference infrastructure.
3. Their "green" differentiation strategies fall into three distinct categories:
   - **Viro AI** → after-the-fact REC/offset purchasing via Terrapass.
   - **ChatGPTree** → monthly tree planting via Evertreen + Veritree.
   - **Earthly Insight** → 33% revenue donation to rewilding NGOs (Global Rewilding Alliance, Rewilding America Now, Celtic Rewilding, 900M).
4. The **one factual error** in the three claims is the assertion that ChatGPTree has "no findable privacy policy" — a full policy exists at `chatgptree.ai/legal/privacy`.
5. The **non-transparency concern about Evertreen is well-sourced** (REDD-Monitor's March 2025 Substack investigation and Ground Truth Data's "Accountabilitree" review in March 2025 both document missing planting locations, species data, survival rates, and inconsistent pricing/CO₂ math). The user's claim about ChatGPTree's partner being "flagged for non-transparent practices" is therefore well-founded — but only for *Evertreen*, not for *Veritree*, which is itself a transparency-focused MRV platform.
6. **Terrapass — Viro's clean-energy partner — has its own transparency issue:** in July 2025 it entered a California DFPI consent order, refunding ~$68,500 to 621 California consumers and 9 businesses for failing to disclose ~40% markups on carbon credit sales. This is highly relevant context for Viro's REC-purchase mechanism. *(Wikipedia, CA)*

---

## Details

### CLAIM 1 — Viro AI

**Original claim:** *"Viro AI — Wraps OpenAI and Anthropic APIs. Green claim is purchasing renewable energy credits after the fact, not running on renewable infrastructure."*

**What was verifiable:**

| Sub-claim | Finding |
|-----------|---------|
| Viro AI exists | **Confirmed.** Website at viro.app and ai.viro.app; iOS app (id6747270877) and Android app (com.viro.ai); ~1,000+ users as of October 2025 per founder's Devpost updates. Solo founder "Nick A" (Nick Arbuckle). |
| Wraps OpenAI and Anthropic APIs | **Confirmed — and more.** The site explicitly states it lets users "Chat with ChatGPT, Claude, Gemini, and LLaMA - all in one app." Devpost project page lists "Supporting ChatGPT, Claude, Gemini, and LLaMA meant stitching together different APIs." So it wraps OpenAI + Anthropic + Google + Meta. |
| Specific environmental claim | Viro estimates each query's inference energy from token throughput (input + output tokens × per-token Wh from public research), then funds an equivalent quantity of clean-energy generation through Terrapass. Marketing language: "Every message powers clean energy." |
| Mechanism = RECs after the fact, not running on renewable infrastructure | **Confirmed.** Viro's own "Energy & Impact Methodology" page states the system boundary is "operational energy from inference" and that matching is "Wh-based, currently global-average, not yet region- or time-specific." Their partner Terrapass is a carbon-offset/REC broker — per Wikipedia and Terrapass's own materials, "TerraPass purchased Green-e-certified wind Renewable Energy Certificates (RECs) from wind farms and calculates the carbon reduction from these RECs based on the EPA eGRID methodology." Viro does **not** claim its inference runs on renewable-powered data centers (and cannot, because inference happens on OpenAI/Anthropic/Google/Meta infrastructure that Viro does not control). |
| Curious wording note | Viro is unusually careful in its methodology page: it explicitly says "We treat renewable procurement as structural fossil displacement, not carbon accounting" and "We avoid describing AI as 'eco-friendly.'" That nuance partly disarms the "greenwashing" critique — but the underlying mechanism is still REC-style after-the-fact procurement, exactly as the claim describes. |
| Additional risk | Terrapass entered a **July 2025 California DFPI consent order** for failing to disclose ~40% operating-cost markups on carbon credits sold to California consumers (621 consumers + 9 businesses refunded ~$68,500). This is directly relevant due-diligence context for Viro's choice of fulfillment partner, though it is not itself part of the user's claim. |

**Sources:**

- https://ai.viro.app/ (product page)
- https://www.viro.app/what-is-viro-ai (states ChatGPT, Claude, Gemini, LLaMA support)
- https://www.viro.app/energy-and-impact-methodology (full mechanism)
- https://www.viro.app/projects-we-support (lists Peñascal Wind, Wells Hydroelectric, FPL Solar, Prairie Winds Solar)
- https://devpost.com/software/viro-eco-friendly-ai (founder's own statement: "trusted partner (Terrapass)")
- https://en.wikipedia.org/wiki/TerraPass (Terrapass uses Green-e wind RECs)
- https://dfpi.ca.gov/press_release/dfpi-secures-over-68500-in-consumer-refunds-from-carbon-credit-dealer/ (July 2025 DFPI consent order against Terrapass)
- https://dfpi.ca.gov/wp-content/uploads/2025/07/Consent-Order-Restitution-Brands-LLC-dba-Terrapass.pdf

**Confidence: HIGH.** The claim's two factual components are both directly substantiated by Viro's own materials and the Wikipedia/Terrapass documentation. The framing "purchasing renewable energy credits after the fact" is an accurate plain-English characterization of what's happening, even though Viro's marketing prefers "matching" language and the methodology page resists "carbon accounting" framing. The only mild stretch is that the claim names only OpenAI and Anthropic — Viro actually integrates four model providers — but the named two are correct.

---

### CLAIM 2 — ChatGPTree

**Original claim:** *"ChatGPTree — OpenAI API wrapper. Green mechanism is tree planting through a partner flagged for non-transparent practices. No findable privacy policy."*

**What was verifiable:**

| Sub-claim | Finding |
|-----------|---------|
| ChatGPTree exists | **Confirmed.** Founded by John Vincent Lee (former founder/CEO of Seattle laundry startup Loopie), launched beta June 2025 per GeekWire. Two related domains: chatgptree.ai (main marketing site) and chatgptree.org (a related "Compassion Ventures"-powered site selling tree-planting bundles and a TreeMail newsletter). Apps: "GPTree Grove" on iOS (id6753215755) and "GPTree" / "ChatGPTree" on Android. Pricing $11/month for "Solo Sapling." |
| OpenAI API wrapper | **Confirmed.** Marketing copy says "Tap into GPT-4o," "powerful, GPT-4-level chat assistant," and the iOS listing now references "GPT-5 technology." It is a straightforward OpenAI API wrapper — no other model provider is mentioned. (Disclaimer on its own site: "ChatGPTree is not affiliated with or endorsed by OpenAI or ChatGPT.") |
| Tree planting mechanism | **Confirmed.** $11/mo plan = "1 tree planted every month." Trees are planted in Oregon (Douglas Fir / Western Hemlock) and Madagascar (Mangrove / Acacias). |
| Tree-planting partner(s) | ChatGPTree explicitly partners with **two** organizations: **Evertreen** (initially, per GeekWire June 2025) and **Veritree** (added later — Veritree photos and logo appear prominently on the current chatgptree.ai homepage). |
| Partner "flagged for non-transparent practices" | **Confirmed for Evertreen specifically; NOT for Veritree.** Evertreen has been the subject of two independent, credible transparency critiques in 2025: (1) Chris Harris / Ground Truth Data's "Accountabilitree" review (March 2025) flags that Evertreen does not publish species data, polygon-mapped planting areas, survival-rate monitoring, or identify the on-the-ground implementing organizations; (2) REDD-Monitor's Substack investigation ("Evertreen: Non-transparent tree planting and dodgy carbon offsets") catalogues vague project descriptions, missing project areas, irregular price/CO₂ math (£500 for 200 trees but £1,000 for 600 trees; ~1 ton CO₂ per tree with no published methodology), and that Evertreen's parent CG Green Solutions had only £2,135 in plant/machinery and 1 employee on its most recent financial statement despite claiming 3.1M trees planted. Veritree, by contrast, is a tentree-spun-out MRV platform specifically built *to address* the transparency problem in tree planting (Series A $9.1M CAD, blockchain-published ground-truth data, drone/satellite verification). So the user's claim is correct *with respect to Evertreen* and false *with respect to Veritree*. |
| "No findable privacy policy" | **FALSE.** A full, multi-section privacy policy exists at https://chatgptree.ai/legal/privacy, last updated October 29, 2025, covering: information collected, automatic data-collection technologies, disclosure of information, state privacy rights (CA, CO, CT, DE, FL, IN, IA, MT, OR, TN, TX, UT, VA), and data security. The iOS App Store ("GPTree Grove") links to this same URL. **What is true:** the *secondary* site chatgptree.org's `/privacy-policy` page just says "Privacy Policy coming soon" — so if someone only looked at chatgptree.org rather than the primary chatgptree.ai property, they would reasonably conclude no policy exists. The claim is partially explainable but ultimately incorrect about the product as a whole. |

**Sources:**

- https://www.chatgptree.ai/ (main marketing site — lists Evertreen + Veritree)
- https://chatgptree.org/ (related site — "Privacy Policy coming soon")
- https://www.geekwire.com/2025/rooted-in-founders-belief-that-tech-can-do-good-chatgptree-is-an-ai-tool-with-a-regenerative-focus/ (founder John Vincent Lee; initial Evertreen partnership; planting in Oregon and Madagascar; $11/mo)
- https://chatgptree.ai/legal/privacy (privacy policy — exists, dated Oct 29, 2025)
- https://apps.apple.com/us/app/gptree-grove/id6753215755 (App Store listing links to that privacy URL)
- https://reddmonitor.substack.com/p/evertreen-non-transparent-tree-planting (Evertreen non-transparency critique)
- https://groundtruth.app/accountabilitree-evertreen/ (Ground Truth Data's "Accountabilitree" framework applied to Evertreen)
- https://www.veritree.com/ and https://betakit.com/tentree-spinout-veritree-announces-9-1-million-cad-series-a-to-help-companies-manage-nature-restoration-projects/ (Veritree's transparency mission)

**Confidence: HIGH on each individually verifiable component.** The "OpenAI API wrapper" and "tree planting" descriptions are unambiguously correct. The "flagged partner" claim is correct for Evertreen (well-sourced by two independent reviewers) but does not apply to Veritree. The "no findable privacy policy" claim is **incorrect** — a current, detailed policy exists on the main domain.

---

### CLAIM 3 — Earthly Insight

**Original claim:** *"Earthly Insight — Wraps OpenAI, Anthropic, and Google APIs. No renewable energy claims. Donates a share of revenue, but the AI itself runs on conventional infrastructure."*

**What was verifiable:**

| Sub-claim | Finding |
|-----------|---------|
| Earthly Insight exists | **Confirmed.** Earthly Insight LLC. Co-founded by Matthew Plotkin ("Founding Member") with another principal named Avery quoted in press materials. iOS app id6746950997 ("Earthly Insight"), Android app com.earthlyinsight.app, web app at earthlyinsight.ai, marketing at earthlyinsight.com. Press release dated December 10, 2025; "Trusted by 5,000+ people" per homepage. |
| Wraps OpenAI, Anthropic, and Google APIs | **Confirmed explicitly and on the record.** From the Global Rewilding Alliance's partnership FAQ (the recipient of Earthly Insight's donations): *"We use a multi-model approach, integrating with leading LLMs like those from OpenAI, Anthropic, and Google."* App Store description: "leading AI models like GPT-4o, Claude 3.5 Sonnet, and Gemini." Webflow staging site lists "GPT-4.1, Gemini 2.5 and Claude 3.5 Sonnet." |
| No renewable energy claims | **Confirmed.** Earthly Insight's positioning is explicitly *reduction + restoration*, not renewable energy procurement. Per their press release: they "strip away high-resource features" (no image or video generation) and fund rewilding. They have not announced REC purchasing, green-energy matching, or renewable infrastructure. Roadmap items mention "the ability to track energy use, water consumption and carbon emissions" — but not provide renewable energy. |
| Donates share of revenue | **Confirmed: 33% of premium subscription revenue.** Primary recipient is the Global Rewilding Alliance, where Earthly Insight is the "first Private-sector Champion" (confirmed in a dedicated GRA blog post quoting Alister Scott, GRA Executive Director, and Matthew Plotkin). Other listed recipients include Rewilding America Now, Celtic Rewilding, and 900M. Premium subscription $20/month (some listings show $23). |
| AI itself runs on conventional infrastructure | **Confirmed by inference (and effectively conceded by EI itself).** Because Earthly Insight uses OpenAI, Anthropic, and Google APIs, inference physically runs on those providers' data-center infrastructure — Microsoft Azure (for OpenAI), AWS / Google Cloud (for Anthropic), and Google Cloud (for Gemini). The company makes no claim of running its own renewable-powered inference, and the GRA FAQ explicitly frames Earthly Insight's contribution as "reduction" of feature scope and "restoration" via funding — not infrastructure substitution. They are bootstrapped, not infrastructure operators. |

**Sources:**

- https://www.earthlyinsight.com/ (homepage)
- https://earthly-insight.webflow.io/ (older staging site listing GPT-4.1, Gemini 2.5, Claude 3.5 Sonnet)
- https://apps.apple.com/us/app/earthly-insight/id6746950997 (iOS listing, lists models)
- https://play.google.com/store/apps/details?id=com.earthlyinsight.app
- https://globalrewilding.earth/earthly-insight-joins-our-global-rewilding-champions/ (confirms 33% donation, GRA "first Private-Sector Champion," and the OpenAI/Anthropic/Google multi-model approach)
- https://www.morningstar.com/news/accesswire/1116190msn/introducing-earthly-insight-a-more-conscious-ai (Dec 10, 2025 press release)
- https://fintech.tv/eco-friendly-ai-how-earthly-insight-is-changing-tech/ (founder interview confirming bootstrapped/no investors, rewilding rationale)
- https://www.earthlyinsight.ai/privacy-policy (privacy policy exists, though the live page renders mostly JS-dependent)

**Confidence: HIGH.** Every component of the claim is directly substantiated, most notably by the partner organization (Global Rewilding Alliance), which has independent reason to accurately describe the relationship.

---

## Recommendations

1. **Use Claim 1 (Viro) and Claim 3 (Earthly Insight) confidently in competitive positioning** — both check out cleanly against primary sources and the products' own published methodologies. For Viro, you can strengthen the critique by adding the Terrapass DFPI consent order context (July 2025, 40% undisclosed markup, ~$68,500 in refunds), which materially weakens the "verified clean energy" framing.
2. **Correct Claim 2 (ChatGPTree) before using it externally.** The two corrections needed are:
   - Add **Veritree** alongside Evertreen as a current partner, and acknowledge that Veritree is *not* part of the transparency critique (it's actually a transparency-focused MRV platform). The flagged-partner critique is specifically about Evertreen, sourced to Ground Truth Data's "Accountabilitree" framework (March 2025) and REDD-Monitor's Substack investigation (March 2025). Cite those sources.
   - Drop or revise "no findable privacy policy." A full policy dated October 29, 2025 lives at `chatgptree.ai/legal/privacy` and is linked from the iOS App Store. If the original analyst was looking at chatgptree.org (which still says "Privacy Policy coming soon"), document that as a *secondary-property inconsistency* — that's a defensible critique of brand hygiene, but not the same as "no privacy policy exists."
3. **Threshold that would change these conclusions:**
   - If Viro publishes evidence of *direct renewable PPA matching* (time- and location-matched, not annual-Wh global-average via a broker) — re-evaluate. Their methodology page hints at moving in this direction but is not there yet.
   - If ChatGPTree drops Evertreen and uses only Veritree-verified planting — the "flagged partner" critique would no longer apply.
   - If Earthly Insight publishes audited financials showing the 33% donation is actually flowing as claimed — this would upgrade the donation claim from "stated" to "audited." Currently it's a stated commitment with no third-party financial verification beyond the GRA partnership announcement.
4. **For competitive landscape analysis, treat all three as belonging to the same architectural class:** API-wrapper chatbots that monetize a sustainability narrative attached to third-party-hosted inference. Their meaningful differentiation is the *funding mechanism* (RECs/offsets vs. trees vs. rewilding donations), not the AI itself. None of them runs on greener inference infrastructure than the underlying provider does.

---

## Caveats

- All three products are small, recently launched (most in 2025), and have minimal independent press coverage. Most descriptive information comes from the products' own marketing, app-store listings, and press releases, which should be read accordingly. The GeekWire piece on ChatGPTree and the Global Rewilding Alliance partnership page for Earthly Insight are the strongest *external* corroborations.
- Marketing/founder language is forward-looking in places ("Next in the product roadmap will be the ability to track energy use, water consumption and carbon emissions" — Earthly Insight; "Next, we're scaling Viro AI to fund millions of kWh" — Viro). I have flagged these as roadmap statements, not delivered features.
- Viro's wording explicitly avoids the term "carbon offsets" and uses "renewable energy matching" / "Wh-based matching," but the operational reality — payments to Terrapass, which procures Green-e wind RECs — *is* the standard REC/offset model. The user's plain-English characterization is fair; Viro's own marketing arguably softens what the mechanism actually is.
- The Evertreen critiques are from REDD-Monitor (an advocacy-oriented Substack run by Chris Lang, a longtime critic of REDD+ and offset markets) and Ground Truth Data (a Canadian forest-data company). Both are credible and methodical, but neither is a peer-reviewed source; readers should evaluate them on their cited evidence (which is detailed and specific) rather than on institutional authority.
- The single web fetch of `earthlyinsight.ai/privacy-policy` returned a near-empty body because the page is rendered via JavaScript; the policy is referenced from multiple legitimate properties (app stores, marketing site, GRA partnership page) so its existence is well-supported, though I was not able to read the full text.
- I was not able to independently verify the exact financial flow of Earthly Insight's "33% of revenue" donation beyond the company's own statements and the Global Rewilding Alliance's confirmation that they are a recipient. No audit, 990, or third-party financial verification was located.
