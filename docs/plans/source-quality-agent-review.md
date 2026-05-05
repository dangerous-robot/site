# Source quality roadmap: agent review

**Date**: 2026-05-05  
**Reviewed**: [`source-quality-roadmap.md`](source-quality-roadmap.md)  
**Reviewers**: Product advisor, research director, newspaper editor (separate agents, no coordination)  
**Purpose**: Strategic critique before implementation — identify weaknesses and major gaps at the plan level, not the implementation level.

The central question each agent addressed: *Does this work move the site closer to providing defensible verdicts on claims and presenting them logically to users?*

---

## Product advisor critique

**Verification scale measures source-type diversity, not claim validity.** The five-point scale (claimed → multiply-verified) is derived mechanically from source characteristics (independence + kind), not from whether those sources actually prove the claim. A "multiply-verified" verdict can mean five articles that all restate the same company disclosure. The scale tells you how many outside-origin sources exist, not whether any of them corroborate the claim.

**The confidence cap is pragmatic risk reduction, not a quality signal.** Capping confidence at "low" for self-reported claims is sensible as a floor rule. But the plan treats all self-reports equally. A company that publishes detailed methodology documentation, makes it auditable, and has no contradicting external evidence is treated identically to a company that posts a marketing claim on a blog. The cap prevents overclaiming but cannot distinguish weak evidence from strong-but-uncorroborated evidence.

**12 of 13 implementation items are backend-only.** Item 12 (display) adds one label and a source count — no explanation of what either means, no guidance on what a reader should do. The roadmap assumes users will infer quality from the label, without support. The infrastructure work doesn't generate user-facing value until the display layer is built out.

**The plan solves an internal governance problem, not a user problem.** The real driver is: "stop analysts from claiming high confidence on thin sources." That's a valid goal. But users don't ask for governance. They ask "is this claim true?" and "why should I believe it?" The roadmap doesn't answer either. Verification level doesn't explain why the sources chosen prove or disprove the claim — only the narrative does, and narrative quality isn't addressed.

**Defensibility requires argumentation, not metadata.** A claim is defensible when the analyst can explain why specific sources justify a specific verdict and a skeptic can point to which sources are weak or misread. The verification scale adds source-type labels but doesn't require showing the work when verdict and sources diverge, or when sources conflict. That's risk management, not defensibility.

---

## Research director critique

**The `source_type → independence` proxy breaks on the most common real case.** The plan maps `source_type: secondary → independence: independent`. But secondary sources most often cite primary sources — a journalist restating a company's press release is classified as "independent" but adds zero epistemic weight. "Originated outside the company" is not the same as "independently confirmed the claim." The scale will show "independently-verified" for a claim supported only by secondary sources that all trace to the same company document.

**The confidence cap is epistemically inconsistent.** Consider: a company reports zero data breaches in 2025, and no contradicting evidence exists (no breach disclosures, no lawsuits, no regulatory findings). Under this plan, confidence is capped at "low" because the claim is self-reported. But absence of contradicting evidence is meaningful data. Either the plan can't assess absence-of-evidence claims (fine — say so explicitly) or it's applying a source-type penalty independent of actual evidence quality. The cap needs an honest rationale, not just a rule.

**"Independently verified" is undefined for claims that require access to internal systems.** Many high-stakes claims (energy contracts, training data practices, safety protocols) are inherently unverifiable without insider access. Secondary sources citing these claims are often restating the company's own numbers. The plan will classify such claims as "independently verified" or "multiply-verified" when independent sources are found — even if every independent source is just citing the company's report. The scale doesn't distinguish between independent corroboration and independent repetition.

**Deferring COI, author authority, and document_type will silently degrade verdict quality.** Without COI detection, the analyst can't flag when an "independent" source is a publication funded by a competitor, or when an author has a financial relationship with the entity. Without document_type, a company's SEC filing and its marketing blog are both "first-party" with no differentiation. The confidence cap becomes the only lever, and it's too blunt for cases where evidence volume is high but epistemic quality is low.

**The system incentivizes quantity over quality.** High-profile claims attract more secondary sources → more `independence: independent` labels → higher verification level → verdict looks more authoritative. Low-profile claims backed by one quality primary source grade lower. You've created an incentive structure that rewards media coverage volume, and the verification scale masks that problem rather than surfacing it.

---

## Newspaper editor critique

**Item 12 displays a label and source count with no reader communication.** "Self-reported" and "2 sources (1 company-published, 1 independent)" appear on the claim page. But the plan never addresses: What does "low confidence" mean to this reader? Is this the confidence the analyst has in the verdict, or something else? A reader cannot determine from the display whether they should change their mind, demand more evidence, or trust the verdict. Display that doesn't answer "what should I do with this?" has failed its purpose.

**The label vocabulary is internal jargon.** "Self-reported" has no clear reader meaning. Does it mean: the company made an unverified claim? The company provided documents we reviewed but couldn't independently test? The company made a claim and published supporting evidence we found credible? All three feel like "self-reported" but require different reader responses. "Claimed" is worse — it sounds pejorative without a definition. These labels are derived from mechanical rules (source_type + kind) but never tested against reader comprehension.

**The plan has no editorial policy for when publishing low-confidence verdicts is harmful.** Decision 1 says: publish claims with self-reported sources. Decision 2 caps confidence at "low." But what happens when a company has published comprehensive, auditable documentation and no contradicting evidence exists? Publishing "low confidence" on a well-documented claim can amplify doubt about something true. The plan enforces a cap but provides no editorial stance on when that cap serves readers and when it confuses them.

**Claim stakes are absent.** Source quality on a trivial claim doesn't transfer to a safety-critical one. A claim about a company's blog publication frequency might have perfect independent verification. A claim about data retention practices might have only self-reported evidence. The plan treats both identically. A reader deciding "should I change my behavior based on this?" needs to understand not just source quality but claim importance — and the plan provides no mechanism for expressing that.

**The logical chain has a gap readers can't cross.** A reader sees "Independently verified — low confidence." The confidence is capped by verification level, but the display shows neither the cap rationale nor the reasoning from sources to conclusion. The reader cannot reconstruct why the analyst reached this verdict from this evidence. A claims site where readers can't follow the reasoning is asking for trust it hasn't earned.

**No transparency into analyst discretion.** Item 9 explicitly defers the "article: claimed or self-reported?" boundary to "case-by-case judgment at implementation." Readers see labels with no visibility into where that judgment was applied or how consistently. This is the core trust problem: the labels look rule-based and objective, but they rest on undisclosed analyst discretion.

---

## Where the agents agree

All three agents independently converged on the same three structural problems:

### 1. Verification scale measures source-type diversity, not claim validity

The mechanical derivation from `independence + kind` cannot distinguish five articles that independently investigate a claim from five articles that all cite the same company report. This is the most serious structural gap. The plan does not acknowledge this limitation, and presenting the scale as a quality signal to readers without that caveat risks active harm to reader trust if the limitation is ever surfaced.

### 2. Confidence cap is blunt risk reduction, not epistemic judgment

The cap stops analysts from overclaiming on thin sources — that's valuable. But it treats self-reported claims uniformly regardless of evidence quality, and displaying the result to users implies more analytical rigor than is present. The plan provides no mechanism for expressing "this is self-reported but the documentation is comprehensive and consistent with external signals."

### 3. Display layer (item 12) is vastly underdeveloped for the backend investment

12 items of infrastructure produce one line of display output with no explanation of labels, no reader guidance, and no cap rationale. The pattern is: build rigorous internal taxonomy, show users a label derived from that taxonomy, assume users will trust the label. This is confidence theater — the display looks authoritative but rests on heuristics readers can't evaluate.

---

## Recommended additions

These recommendations emerged from the agent critiques and are not in the original plan:

**A. Bound what the scale actually measures.** The architecture doc and analyst instructions should explicitly state: the verification scale measures source-type diversity, not claim corroboration. "Independently verified" means independent-origin sources exist, not that independent analysis confirmed the underlying claim. Without this caveat, the scale overpromises.

**B. Require cap reasoning in narrative and display.** When the confidence cap fires, the analyst must write why: "Confidence is capped at low — all sources originate from entity documentation; no independent source was found that conducts original analysis of this claim." This rationale should appear in the claim display, not just in internal pipeline logs.

**C. Define "original reporting" as a classification threshold.** Analyst instructions should distinguish: does this source conduct original analysis of the claim, or does it restate a published number? This doesn't require a new schema field in v1, but it needs to be in the instructions so the analyst applies the independence proxy correctly.

**D. Expand item 12 into a user communication task.** The display should answer three questions: What is the claim? What evidence exists? Why does the verdict say what it says? At minimum: plain-language explanation per verification level; cap rationale visible when it fires.

**E. Add editorial policy for publishing low-confidence verdicts.** When does a low-confidence verdict serve the reader (makes uncertainty visible) vs. harm the reader (amplifies doubt about something true)? The plan needs a decision, even if it's just a principle in the analyst instructions.
