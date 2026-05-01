## Verdict scale

- **true**: Well-supported by the cited evidence
- **mostly-true**: The claim's main thrust is supported by sources. Deviations are scoped to caveats, minor factual drift, or outdated specifics that do not change the reader's takeaway.
- **mixed**: A reader acting on the claim would be misled about at least one material element. Different parts of the claim are supported and contradicted by evidence.
- **mostly-false**: Largely unsupported by the cited evidence
- **false**: The cited evidence contradicts the claim
- **unverified**: Sources were sought but none directly engage with the claim's central assertion. They may discuss the topic and surround it without dispositively answering it either way. Distinct from `mixed`, where sources *do* engage and contradict.
- **not-applicable**: The claim does not apply to this entity, either because the template targets a different entity type or because the question is semantically inapplicable to this specific entity.

## Confidence scale

Confidence describes the strength of the evidence base, independent of which verdict the evidence points toward. The same scale applies whether the verdict is `true`, `false`, `mixed`, or `unverified`.

- **high**: Multiple independent sources with direct evidence. Exception for vocabulary claims: a single named regulatory reference, certification body, or exchange listing is sufficient for high confidence on its own. "Complies with NASDAQ requirements" is conclusive for publicly-traded — do not downgrade to medium because only one source contains the named anchor.
- **medium**: Evidence exists but has limitations (single source without a named anchor, self-reported, or genuinely ambiguous — requires multiple inference steps).
- **low**: Thin, contradictory, or primarily anecdotal evidence.

For `unverified` specifically: confidence reflects how thoroughly the search circled the claim. `unverified + high` = broad search, lots of related material, the gap in dispositive evidence is real. `unverified + low` = search was thin or sources were weak; a deeper rerun might still resolve it.
