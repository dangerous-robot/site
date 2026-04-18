# Work Item: Content Seeding

**Phase**: 2 (Schemas, Content & Site -- MVP)
**Status**: not started
**Depends on**: Zod schemas defined (research-schemas.md), Astro pages exist (astro-site.md)
**Co-authored with**: research-schemas.md and astro-site.md (tightly coupled)

## Goal

Create real research content that proves the architecture works end-to-end: schema validates, Astro renders, site deploys. Start with claims TreadLightly already makes on its existing pages -- structuring these has immediate practical value.

## Seed Data Sources

Files in `/Users/brandon/dev/ai/parallax-ai/`:

| Source | What it contains | Research category |
|--------|-----------------|-------------------|
| `frontend/src/app/robot/responsible-ai/page.tsx` | Chatbot comparison table data | Product Comparisons |
| `frontend/src/app/robot/ai-safety/page.tsx` | FLI Safety Index scorecard + commentary | AI Safety Assessments |
| `frontend/src/app/transparency/page.tsx` | AI Product Card data (models, hosts, grades) | Environmental Impact |
| `docs/dangerous-robot/links-to-add.txt` | 12 URLs: AI safety resources, GreenPT, sustainability | AI Safety, Environmental |
| `docs/reports/ENERGY_ESTIMATION_REVIEW.md` | Energy estimation pipeline review | Environmental Impact |
| `docs/plans/ENVIRONMENTAL_TRANSPARENCY_ROADMAP.md` | Competitive analysis (Ecosia, GreenPT) | Environmental Impact |

### PDFs Not Yet Read (needs `brew install poppler`)

- `docs/brand/ai_transparency_card_structure.pdf`
- `docs/plans/future/Proposal- AI Model Efficiency Benchmarking Tool.pdf`
- `docs/research/Grading Generative AI Image Services on Safety, Ethics, and Quality.pdf`
- `docs/dangerous-robot/Ranking AI Models by Energy Consumption: From Frugal to Frontier.pdf`

## Proof-of-Concept Content Set

### Entities (3)
- `entities/companies/anthropic.md`
- `entities/companies/greenpt.md`
- `entities/companies/ecosia.md`

### Sources (4-5)
- FLI AI Safety Index Winter 2025
- GreenPT energy methodology blog post
- "The True Price of Every ChatGPT Prompt" (Earth Day)
- Infomaniak data center sustainability info
- Dr Camilla Pang GreenPT review

### Claims (3)
From the responsible-ai comparison table -- claims TL already makes publicly:
- "GreenPT is hosted on renewable energy" (entity: greenpt, category: environmental-impact, verdict: true)
- "Ecosia AI Chat is hosted on renewable energy" (entity: ecosia, category: environmental-impact, verdict: false)
- "No AI company scored above D on existential safety" (entity: n/a or topic, category: ai-safety-assessments, verdict: true)

## Tasks

- [ ] Create 3 entity files
- [ ] Create 4-5 source files from seed URLs (include Wayback Machine archiving)
- [ ] Create 3 claim files referencing entities and sources
- [ ] Verify `npm run build` passes (Zod validation)
- [ ] Verify pages render correctly on dev server
- [ ] Deploy and confirm on GitHub Pages

## Design Decisions

**Manual first**: Converting sources by hand reveals friction points that inform the PydanticAI ingestor (Phase 4).

**Start with existing claims**: The chatbot comparison table and AI safety page contain claims displayed to users today. Structuring these proves the architecture while producing immediately useful output.

## Estimated Scope

Medium. ~10 files to create. Each source requires reading the material and writing structured frontmatter.
