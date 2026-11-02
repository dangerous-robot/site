# Copy review config: Dangerous Robot

Read by the personal /copy-review skill (~/.claude/skills/copy-review/; format in its `config-template.md`).
Voice rules: `docs/mission-and-voice.md`; decided copy strings: `docs/decisions.md` ("Decided copy" entry; do not
reword them without a new entry there). Do not review `research/**`: the pipeline regenerates it. Applying edits
under `src/` needs an active release-gate work item (`release-triage` skill); `--review-only` needs none.

Reports: .claude/archive/copy-review/

## Registers
| Glob | Register |
|---|---|
| src/pages/**/*.astro, src/content/**/*.md | page |
| src/components/**, src/layouts/** | ui |
| docs/decisions.md, docs/mission-and-voice.md | page |
| docs/**, handoff/** | brandon |

The two `docs/` files are `page` so nothing auto-applies there: one holds the decided copy, the other quotes
off-voice lines on purpose.

## Documents
| Glob | Doc and sections | Use |
|---|---|---|
| src/**, public/** | docs/mission-and-voice.md § "Voice" (rules 1 to 9), § "Mechanics" | rules |
| src/pages/**, src/content/** | docs/decisions.md:49 (the "Decided copy" bullet and its table), src/pages/values.astro | facts |

## Extra tells
| ID | Tell | Severity | Source |
|---|---|---|---|
| DR1 | A forecast the site cannot evidence, or a generalization written as a finding ("The ones sharing the least usually have the most to hide"); a number with no source or as-of date | SEV-1 | mission-and-voice.md § Voice rule 2 |
| DR2 | A line that ranks one danger (individual or societal) above the other, or waves one off to make the other land | SEV-1 | mission-and-voice.md § Voice rule 5 |
| DR3 | Ultimatum or countdown form: "act now", "before it's too late", "while you still can" | SEV-2 | mission-and-voice.md § Voice rule 3 |
| DR4 | The reader written as a dupe or already beaten ("You've already handed over your life") | SEV-2 | mission-and-voice.md § Voice rule 4 |
| DR5 | Spelling out the consequence of the one-reviewer limit, or dressing it or the contradictions as a virtue or a brag | SEV-2 | mission-and-voice.md § Voice rule 8 |
| DR6 | Abstract where the drip should be listed: "every aspect of modern society", "our lives", "hard drives" | SEV-3 | mission-and-voice.md § Voice rule 7 |
| DR7 | The industry's words for itself or tribe words: "tech leaders", "innovators", "billionaires"; "arms race" on sourced pages; a weather verb that hides who decides ("is being shaped by", "is transforming"): name the actor, do not swap the verb | SEV-4 | mission-and-voice.md § Voice rule 6 |
| DR8 | Vendor diction: "powered by AI" (decided: "built with the help of AI"); "agency", "autonomy", "stakeholders" for plain words; "felony"; "TreadLightly AI" as two words | SEV-4 | mission-and-voice.md § Voice rule 1 |
| DR9 | Site word list: "crucial", "landscape", "navigate" (the rest of that list is AT6, AT7, AT18) | SEV-4 | mission-and-voice.md § Mechanics |
| DR10 | Internal vocabulary on the site: "operator" for the person who reviews (name the person), "crossroads" for a decision (say "decision" or name it), "GSI" (spell out "general superintelligence") | SEV-4 | mission-and-voice.md § Voice rule 1 (GSI), rule 8 (operator), § Mechanics (crossroads) |

## Overrides
| Glob | Tell | Change |
|---|---|---|
| ** | M1 (em dash) | never |
| src/pages/index.astro | AT19 (staccato fragments) | off: one sentence per line in the hero, by decision (mission-and-voice.md § Mechanics) |
| src/pages/privacy.astro | AT3 (list of what isn't) | off: legal lists are information |
