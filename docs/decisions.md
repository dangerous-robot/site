# Decisions

Settled product decisions for dangerousrobot.org, newest first. Plans in `docs/plans/` implement them and quote the wording they need. This repo is public: keep money, people and other private matters out of this file.

Decisions made before 2026-10-04 (mission, audience, positioning, trust model, content model, messaging, early roadmap) are in the private Drive discovery records and their Decisions Log, frozen on 2026-10-04 as history. The last Drive entries cover the version reset and the About and Values revision.

## 2026-10-04

- **Planning lives in the repo.** New product decisions are recorded here; plans and the roadmap stay in `docs/`. The Drive discovery records and Decisions Log are frozen as history and no longer edited. The discovery handoff in the claude.ai project is retired. *(Final)*
- **Pledge signatures are collected on the site.** A Cloudflare Worker and D1 database (the stack `docs/plans/public-feedback.md` chose) take name and email, confirm by email, and show a signer's name publicly only if they opt in. Only Brandon receives the signer list. No hosted form in the meantime: the pledge post and its homepage menu entry wait for the Worker, and beta.4 waits with them. Design draft: `docs/plans/drafts/petition-signatures-architecture.md`. *(Final)*
- **beta.4 scope.** Companies and Products list only entities with at least one published claim (detail pages stay); Values stays in the footer and homepage menu, not the top nav; `research/v1-launch-set.md` is deleted. Details in `docs/plans/refocus-foundation.md`. *(Final)*
