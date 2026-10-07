# Mission and voice

What Dangerous Robot is for, how the site works on that, and how to write for it. For anyone writing copy, guides, posts or claims for the site, coding agents included.

The decided wording lives in `docs/decisions.md` (the "Decided copy" entry, 2026-10-06, and later entries). This document explains the thinking behind that wording and quotes it. Where the two disagree, `docs/decisions.md` wins.

## Why the site exists

AI is a dangerous tool, and we keep using it because it grants wishes. If it were only dangerous we would walk away. Instead it is in our phones and our operating systems, in HR departments and insurance companies, and it got there faster than any tool before it.

The thesis (the post "Why Dangerous Robot exists", `src/content/writing/why-dangerous-robot-exists.md`) splits the danger in two.

- The familiar kind. A chainsaw is dangerous too, but much less so once you learn how it works and practice using it. Most of what AI can do to your privacy, your money, your attention or your judgment can be handled the same way, with knowledge and good habits. The trouble is that the tools arrived before the lessons.
- The second kind. The people building these systems say, on the record, that AI will become more capable than we are and that they do not yet know how to control it. You cannot train your way out of that.

Both kinds come down to trust. Every time you use AI, and every time it is used on you, someone decides how much to trust it with your data, your money, your security and your freedom to decide for yourself. The biggest of those decisions are being made by a few people, without you.

The mechanism is not force. Convenience runs on reliance and pays out in compliance. Nobody hands their life to a machine. They hand over the directions, then the inbox, then the money, then the wheel, then the diagnosis, each one sensible on its own, and nobody walks one back. The site exists to reach people at the moments where a choice is still being made.

What the site asks of a reader: choose better where you have a choice, and push harder where you do not. Choices add up to market pressure. Voices add up to policy.

### Who it is for

A concerned person at a decision point, uneasy but undecided: about to trust an AI product with something that matters, or wondering what the people building it admit they cannot control. Journalists, researchers and policy staff are welcome and are not the first reader. Sources are global. The United States is the primary frame, with Washington State as the worked local example when one is needed.

### What it is, and what it is not

Dangerous Robot is a guide to AI's dangers, with evidence you can check. It is not a research hub, a watchdog or a fact-checker. It does not compete with established organizations on thought leadership; it cites them and points to them. It publishes no composite score or ranking for any product. It covers risks to the person using AI and risks AI imposes on everyone, and does not rank one above the other. The research record is a cornerstone of the site and no longer defines it; the thesis does.

## How the site works on that

- Guides are the primary content. A guide cites claims where claims exist and sources otherwise, and it says what you can do.
- Every claim shows its sources, a verdict and a confidence level. The verdict vocabulary is True, Mostly true, Mixed, Mostly false, False, Unverified and N/A. Confidence is High, Medium or Low. No new labels. A verdict is our reading of the public record as of the date shown. Every source links to an archived copy where one exists.
- AI assisted, human accountable. Agents search, fetch and draft. A person reviews and approves every claim before it is published. Each published claim carries the reviewer's handle, linked to a profile page with their full name and the claims they reviewed. Copy about who reviews says a person reviews, without naming one. Posts carry a byline that says whether AI drafted the text. The signal of human involvement is accountability and authorship, never a claim that AI was not used.
- The site takes a side and says so. The Values page states four positions, uncited and signed. Research pages (guides, claims, sources) are sourced; writing and petitions argue from the Values positions and say so. On existential risk the site holds that AI carries some such risk, because the people building these systems say so on the record; how large, how likely and when, it does not state as settled, and research pages carry no opinion on it.
- Conflicts are disclosed in one sentence wherever TreadLightlyAI appears in a list or comparison, and the site publishes no verdict on claims about it.
- Corrections are public. A correction note stays on the claim, and the prior verdict stays visible.
- Action is content. Petitions are a content type, and the first is the pledge to support laws that stop AI systems from improving their own capabilities without human control.
- The contradictions are owned. The site runs on AI to investigate AI and burns electricity doing it. Small decisions go to small models.

## Voice

The voice is one person talking plainly about something that worries him, to someone who has not made up their mind. Nine rules, each with lines from the site that hit it and lines that miss it.

### 1. Plain words

Use the words the reader already owns. "Judgment" over "agency", "the wheel" over "autonomy", "a few people" over "stakeholders". Spell out "general superintelligence"; never "GSI". Say "unauthorized access", never "felony". Write "TreadLightlyAI" as one word. US spelling ("judgment", not "judgement"). "The robot" is the site's word for AI systems in editorial copy; the name does some of the work.

On voice: "You cannot train your way out of that." (thesis)

Off voice: "Open, accountable research on AI and the industries building it: built by people, powered by AI." (`src/pages/research/index.astro`, the hub heading). "Powered by AI" is vendor diction. The decided phrase is "built with the help of AI".

### 2. Evidence you can check, and judgment stated as judgment

Sourced pages state what the record shows. Editorial pages may take a side, and say that they are doing so. Never write a forecast the site cannot evidence, and never write a generalization as if it were a finding. Every number gets a source and an as-of date, on the page or one link away.

On voice: "Dangerous Robot treats every vendor safety claim as a claim, not a fact." (Values) "A company's safety page is marketing until someone else verifies it." (`ai-safety.md`): a stance, stated as one.

Off voice: "The ones sharing the least usually have the most to hide." (`src/content/resources/ai-safety.md`). No source says that, and it reads as a finding. "A quick text query uses roughly 0.03g CO2." (`should-i.md`): a number with no source and no date.

From the copy sessions: "Seat belt laws came sixty years after the car" survives a pedant (Model T, 1908; the federal rule, 1968). "We don't have sixty years" is a prophecy the site cannot back.

### 3. Urgent without alarm

Urgency comes from the mechanism and from what is on the record. It does not come from a threat or a countdown. State what the builders say ("its makers say they can't yet control it"), not what will happen.

On voice: "One you can learn to handle. The other, its makers say they can't yet control. We hand it our lives anyway: it grants wishes." (homepage)

Off voice: "Act now or lose everything." The ultimatum form ("while you still can", "before it's too late") reads as a threat. "Act while the choice is still yours" is as far as the north star goes, and it sits beside a sentence that names who is deciding.

### 4. The reader has agency

Convenience is a spell, and the reader can break it. Never write the reader as a dupe or as already beaten. Name the trade, then hand back the choice.

On voice: "With that in hand you can choose better where you have a choice, and push harder where you do not." (thesis)

Off voice: "You've already handed over your life and didn't notice." It stings, and it leaves the reader nothing to do.

### 5. Both dangers, no ranking

Individual risk (what AI does to you) and societal risk (what it does to everyone, and what nobody can control) stand on equal footing. Do not write a line that waves one off to make the other land.

On voice: "The robot is dangerous. So is needing it." (bench)

Off voice: "Don't fear the robot, fear reliance on the robot." A good line that ranks the two dangers, and the site's name sits on the one it dismisses.

### 6. Name who decides

Say who. "A few people", "a handful of companies, and the people who run them". Avoid the industry's words for itself ("tech leaders", "innovators"). Avoid class words that sort the reader into a tribe before they have checked a claim ("billionaires"). "Unelected" is accurate and allowed. On sourced pages prefer "the race to build it" to "arms race", which readers hear as weapons; the Values page may say what it likes.

On voice: "A handful of companies, and the people who run them, decide what gets built, how fast it ships, and which risks are acceptable." (Values)

Off voice: "Our future is being shaped by a select few tech leaders." "Shaped" is weather, "tech leaders" is their word, and nothing says you were left out.

### 7. Concrete over abstract

When the point is the drip, list the things, in rising order, ending on the body: the directions, the inbox, the money, the wheel, the diagnosis. Not "our lives", and not "hard drives" (nobody hands over a drive; they hand over the photos).

On voice: "It is in our phones and our operating systems, in HR departments and insurance companies." (thesis)

Off voice: "AI is infiltrating every aspect of modern society."

### 8. Own the limits, with no apology and no brag

Say the single-reviewer fact plainly and stop. Do not spell out the consequence, and do not dress it as a virtue. The same goes for the contradictions.

On voice: "One person reviews everything today. If we are wrong, tell us here." (verdict statement) "The contradictions are real, and we won't dress them up." (Values)

Off voice: "No one checks his work before it is published." (announces a travesty) "A fiercely independent one-man newsroom." (brag) "An operator reviews the draft via the dr CLI." (`src/pages/research/index.astro`): "the operator" is pipeline vocabulary. On the site, name the person.

### 9. "We" is the project

"We" and "us" are fine anywhere and mean Dangerous Robot. They do not imply a staff. Signed pages (Values) may use "I". The one-reviewer statement stays as written beside either.

### Mechanics

- No em dashes. Commas, colons, parentheses.
- No stacked fragments ("Fast. Cheap. Dangerous."). One sentence per line in the hero is the exception, by decision.
- Cut the closer that points back at the previous sentence and labels it without adding a fact ("That is one person, and it is a limit."). Test: delete it; if the reader loses no fact, it goes.
- "X, not Y" only when both halves carry a fact. "A claim, not a fact" does. "A guide, not a lecture" does not.
- No "crucial", "robust", "delve", "landscape", "leverage", "navigate", "empower". No "Here's the thing" or "The real story is" openers.
- A heading can be a sentence when it carries the finding ("The best overall grade is a C+.").
- "Crossroads" is an internal term. On the site say "decision" or name the decision.
- Homepage slot sizes at phone width: the hero holds about 15 characters per line, the tagline about 32 per line over two lines. Count before proposing.

### Lines now on the site or in the repo that miss the voice

| Where | Line | Rule |
|---|---|---|
| `README.md` | "Dangerous Robot is a structured research project that evaluates claims made by and about AI companies and AI products" | Old positioning (research hub). It contradicts the decided project description in the paragraph above it. |
| `AGENTS.md`, Purpose | "the research hub behind dangerousrobot.org, backing claims made on the TreadLightly AI site" | Old positioning, old sponsor spelling. |
| `src/pages/research/index.astro` | "Dangerous Robot tracks claims about AI companies and products" | Old positioning. |
| `src/pages/research/index.astro` | "Open, accountable research on AI and the industries building it: built by people, powered by AI." | Rule 1. |
| `src/pages/research/index.astro` | "An operator reviews the draft via the dr CLI" | Rule 8. |
| `src/content/resources/ai-safety.md` | "The ones sharing the least usually have the most to hide." | Rule 2. |
| `src/content/resources/ai-safety.md` | "Awareness is the first step toward accountability." | Mechanics: a closer with no fact in it. |
| `src/content/resources/should-i.md` | "A quick text query uses roughly 0.03g CO2." | Rule 2: no source, no date. |
| `src/content/actions/prohibit-ai-self-improvement.md` | description: "Show your support for AI Safety." | Rule 7, and stray capitals. |

## Settled copy

Quoted from `docs/decisions.md` (the "Decided copy" entry and later entries). That file is the record. If this list drifts from it, it wins.

| Slot | Text |
|---|---|
| Tagline (under the wordmark) | Convenience runs on reliance and pays out in compliance. |
| Hero (one sentence per line) | The algorithm got your attention. The robot wants the wheel. |
| North star (closes the homepage trust section) | The biggest decisions about AI are being made by a few people, without you. Act while the choice is still yours. |
| Homepage, two kinds of danger | One you can learn to handle. The other, its makers say they can't yet control. We hand it our lives anyway: it grants wishes. |
| Title tag | Dangerous Robot - A guide to AI's dangers, with evidence you can check |
| Meta description | A guide to AI's dangers, with evidence you can check: what AI does to you and to everyone, what its makers say they cannot control, and what you can do about it. |
| Project description | A guide to AI's dangers for people deciding whether to trust AI with something that matters. Evidence you can check, a named person behind every claim, and what you can do about it. |
| Positioning statement | For people deciding whether to trust AI with something that matters, Dangerous Robot is a guide to the danger, with evidence you can check. It shows the source and the person behind every claim, and says what you can do about it. |
| Footer maker line | A community project from the maker of TreadLightlyAI. |
| Disclosure sentence | TreadLightlyAI is made by the same person who makes Dangerous Robot. It is listed under the same criteria and sources as every other product, and we publish no verdict on claims about it. |
| Verdict statement | A verdict is our reading of the public record as of the date shown. AI agents draft it; the person named on the claim approves it. Every source is listed, and you can check them. One person reviews everything today. If we are wrong, tell us here. |
| Reviewer line | Reviewed and approved by brandon-f |
| Bylines | Written by Brandon Faloona, with AI assistance / Written by Brandon Faloona |
| The four positions (About, Values) | AI safety is unsolved. AI is fueling environmental destruction. AI outcomes are being decided by a small group of people. Staying human and connected to each other will be essential. |

## The bench

Working lines from the October 2026 copy sessions. None is in use. They are kept so the thinking is not lost and so a future slot (a guide intro, the pledge page, a 404, a social card) can draw on them. Anything promoted from here gets an entry in `docs/decisions.md`.

Thesis-shaped

- The biggest decisions about AI are being made by a few people, without you. Convenience is how they keep it that way.
- A few unelected leaders are playing with our future. Don't let convenience blind you.
- The robot is dangerous. So is needing it.
- AI is dangerous, and it grants wishes. That's why nobody puts it down.
- The robot is dangerous, and the race to build it is why the seat belts aren't in yet. We hand it things anyway: first the directions, then the inbox, then the money, then the wheel, then the diagnosis, each one sensible on its own, and nobody walks one back. That's the spell. Not that it's useful. That every step makes sense.

Hero-shaped

- The algorithm got your attention. The robot wants your judgment.
- The algorithm got your attention. The robot wants your choices.
- Seat belt laws came sixty years after the car, and only because people demanded them.
- The dangerous part shipped first.
- Everyone got the machine. Nobody wrote the manual.
- The robots are here. The rulebook isn't.
- Welcome to the machine. (A song title, which is fine to use. Wry register: a pledge-page opener or a 404 line, not a hero beside evidence.)

Tagline-shaped

- Silence is the price of convenience. Don't pay it.
- Don't let convenience buy your silence.
- Don't let convenience decide for you.
- Keep the choice ours.
- Make it your call. Keep it our call.
- Convenience is quiet. Don't be.
- Choose well. Speak up.

Rejected, with the reason

- "Don't fear the robot, fear reliance on the robot": ranks the two dangers (rule 5).
- "The algorithm no longer wants your attention. It wants your identity.": "no longer" is a falsifiable claim that is probably false, and "identity" splits readers between identity theft and sense of self (rule 2).
- "The robot wants your agency": the right concept in a seminar word; most readers hear an organization first (rule 1). Use "agency" on pages that explain, not in the hero.
- "The tools arrived before the lessons" (the former hero): "tools" is neutral and "lessons" is soft. The thesis keeps the sentence, where the paragraph around it does the work.
- "Seat belts came sixty years after the car. We don't have sixty years.": seat belts were sold from 1949 and the federal rule came in 1968, so say "seat belt laws"; and drop the forecast (rule 2).