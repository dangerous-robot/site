# Plan: PDF attachment as alternate source content surface (core)

**Status**: ready
**Date**: 2026-04-23
**Scope**: ingestion + content model only. The site-publish half lives in `source-pdf-publish.md` (drafted separately).
**Related plans**: `ingestor-fail-fast-403.md`, `audit-trail.md`, `researcher-host-blocklist.md`, `dr-lint.md`

## Problem

The ingestor reaches an origin via `web_fetch` (`pipeline/ingestor/agent.py`). Per `ingestor-fail-fast-403.md`, terminal HTTP codes (401/402/403/451) short-circuit the run and the URL is recorded as a `StepError`. When the document is real — a paywalled paper, a government PDF on a 403-locked CDN, a policy served only to approved regions — the source is unreachable to the agent. Researchers frequently have the PDF in hand (library access, FOIA response, Wayback `application/pdf` snapshot, direct share) but the content model has no slot for it today. We need a durable content surface that lets a PDF stand in for a URL body, serving the ingestion agent's extraction pass and the audit trail that grounds claim verdicts.

This plan covers the ingestion and data-model halves. A companion plan (`source-pdf-publish.md`) handles the separate concern of republishing redistributable PDFs on the public site, which has its own licensing and rendering discussion.

## Design

### Principles

- **Markdown frontmatter + YAML stays authoritative.** No database; no parallel attachments store with its own index.
- **The `.md` file is the per-source anchor.** An attached PDF is described in frontmatter and located by convention next to the `.md`.
- **Default to "git-only, not republished."** A PDF committed to the public repo is already visible on GitHub; the `republish` flag governs only whether we *also* serve it from `dangerousrobot.org`. This honesty matters; see Licensing below.
- **Same agent shape for URL and PDF.** The ingestor selects one surface or the other at run time; the model sees one fetch tool, not both.
- **List-first cardinality.** `pdfs: [...]` from day one, with a v1 validator cap of one entry. v2 multi-PDF (addendum, appendix, FOIA rolls) does not require a YAML migration across every existing source.
- **Integrity is enforced, not advisory.** sha256 mismatch is a commit-time lint failure and a build failure, not a console warning.
- **Small diffs over new structures.** Extend existing Pydantic/Zod schemas; replace the glob loader only where necessary.

### Storage & path convention

Co-located sibling file, same stem as the Markdown, lowercase `.pdf`:

```
research/sources/2022/viro-privacy-policy-2022.md
research/sources/2022/viro-privacy-policy-2022.pdf       ← new sibling
```

- **Lowercase `.pdf` required.** macOS default filesystems are case-insensitive; Linux CI is not. A researcher who commits `Foo.PDF` locally will pass review and fail the build in GitHub Actions. The `dr attach-pdf` tool normalizes; the lint step enforces.
- **Reserved sibling descriptor namespace.** The repo's source convention is `<slug>.<descriptor>.<ext>`. Reserved descriptors today: `.md` (source prose), `.audit.yaml` (audit sidecar), `.pdf` (this plan). Reserved for future: `.extracted.txt`, `.ocr.txt`, `.screenshot.png`. Document in `AGENTS.md`.
- **Slug collisions are year-scoped.** `2022/x.pdf` and `2023/x.pdf` coexist; audit IDs (`<year>/<slug>`) disambiguate.
- **Future content-addressed dedup is compatible via symlinks.** A later `research/_attachments/sha256/ab/cd.../original.pdf` store with sibling symlinks works through git. Hardlinks do not survive `git clone` and are explicitly not a future option.

Considered and rejected:

| Option | Verdict | Reason |
|---|---|---|
| `research/sources/<year>/<slug>/source.pdf` + `index.md` | rejected | Forces existing sources into a directory migration; loader pattern changes; uglier `git log`. |
| Separate `research/attachments/` tree mirroring sources | rejected | Two places to rename on slug change; easier to orphan; breaks single-anchor rule. |
| Flat `pdf_url:` pointing at origin, no local file | rejected | If the origin were reachable, we would not need the fallback. |

### Size policy

GitHub soft-caps blobs at 100 MB and warns at 50 MB. Most source PDFs (policies, papers, reports) are 200 KB – 10 MB. We treat >25 MB as an exception that requires a reviewer note. Git LFS is **out of scope**; revisit if and when >25 MB attachments become routine. The pre-commit lint (see `dr-lint.md`) rejects uncommitted PDFs over the threshold.

### Attachment manifest (`_attachments.yaml`)

Adding a PDF attachment creates a chicken-and-egg for the ingestion loop: `_select_source_surface(url)` needs to decide "PDF or URL" *before* the agent runs, but the slug/year under which the PDF lives is derived *after* the agent has titled the source. Relying on the frontmatter `pdfs:` block to drive surface selection only works for already-ingested sources, not for bootstrapping.

Solution: a URL-keyed manifest at `research/sources/_attachments.yaml`.

```yaml
# Auto-maintained by `dr attach-pdf`. Hand-editing is supported but discouraged.
attachments:
  - url: https://www.viro.app/privacy-policy
    path: 2022/viro-privacy-policy-2022.pdf
    sha256: 6f4c...
  - url: https://journals.example.org/paywalled-article
    path: 2024/paywalled-article.pdf
    sha256: ab12...
```

- **`dr attach-pdf` upserts into this file on every attach/detach.**
- **Orchestrator resolves surface by URL lookup first**, no slug required.
- **Frontmatter `pdfs:` block remains authoritative for integrity** (it is the per-source, per-audit record), but the manifest is the only way to answer "does a PDF exist for URL X?" before the `.md` exists.
- **Per-year sharding** (e.g., `research/sources/2024/_attachments.yaml`) is out of scope for v1 — a single file scales linearly with attachments (hundreds, not thousands) and is machine-written, so diff churn is low.

### Frontmatter schema

New optional block on source frontmatter. All fields are opt-in; existing sources continue to validate unchanged.

```yaml
# existing
url: https://www.viro.app/privacy-policy
title: Privacy Policy 2022
publisher: Viro Climate Action, Inc
published_date: '2022-09-06'
accessed_date: '2026-04-22'
kind: documentation
summary: ...
key_quotes: [...]

# new — always a list, cap of 1 in v1
pdfs:
  - path: viro-privacy-policy-2022.pdf   # relative to the .md's directory
    role: primary                        # "primary" | "addendum" | "appendix" | "supplementary"
    source_url: https://www.viro.app/privacy-policy.pdf
    sha256: 6f4c...                      # 64 lowercase hex chars
    captured_date: '2026-04-22'
    page_count: 11
    republish: false                     # governs only dist/ and site rendering
    license_note: null                   # required when republish: true
```

**Field justifications.**

- `path` — relative (not absolute, not repo-rooted). Portable across repo moves and research-repo splits.
- `role` — `primary` in v1 (exactly one). Reserved slots prevent a v2 enum churn when addendum/appendix cases land.
- `source_url` — provenance. May be an `http(s)://`, `file://`, or a DOI (`10.NNNN/...`). Not required to equal `url`.
- `sha256` — integrity anchor. Computed at attach; verified at lint and build.
- `captured_date` — distinct from `accessed_date` (consultation) and `published_date` (origin publication). The date the snapshot was taken.
- `page_count` — tool-written, never hand-edited. Surfaces on the site as a reading hint.
- `republish` — licensing switch for the publication surface (see `source-pdf-publish.md`). Default `false`. Named `republish`, not `redistribute`, because the PDF is already in a public git repo; this flag governs only whether dangerousrobot.org additionally serves it.
- `license_note` — required when `republish: true`. Human-written reason: CC license, public domain, granted permission, US federal work, etc.

### Public-repo reality

Storing a third-party PDF in a public GitHub repository *is* a form of redistribution — `https://github.com/<owner>/<repo>/blob/main/research/sources/2022/x.pdf` is a public URL. The plan does not pretend otherwise.

Our posture:
- Storage alongside our commentary and quote extraction is a fair-use archival act consistent with a criticism/commentary research site.
- `republish: false` is the default. The site does not additionally serve, download-link, or index the PDF.
- A rights-holder objection is resolved by `git rm` + history rewrite if requested, plus `_attachments.yaml` cleanup and a site rebuild. The takedown policy is documented in the repo README.
- A future escape hatch (private repo or non-git content-addressed store for non-redistributable PDFs) is architecturally available via the manifest — a future `storage: "private-repo"` field on a manifest entry can point the loader elsewhere without touching the public schema.

### Pydantic model

In `pipeline/common/models.py`, add:

```python
class PdfAttachment(BaseModel):
    path: str
    role: Literal["primary", "addendum", "appendix", "supplementary"] = "primary"
    source_url: str | None = None
    sha256: str | None = None   # validated as 64 lowercase hex when present
    captured_date: datetime.date | None = None
    page_count: int | None = None
    republish: bool = False
    license_note: str | None = None

    @model_validator(mode="after")
    def _guard(self) -> Self:
        if os.path.isabs(self.path) or ".." in Path(self.path).parts:
            raise ValueError("path must be relative and contain no '..'")
        if self.sha256 is not None and not re.fullmatch(r"[a-f0-9]{64}", self.sha256):
            raise ValueError("sha256 must be 64 lowercase hex characters")
        if self.republish and not (self.license_note or "").strip():
            raise ValueError("license_note is required when republish is true")
        return self
```

In `pipeline/ingestor/models.py`, extend `SourceFrontmatter`:

```python
pdfs: list[PdfAttachment] = Field(default_factory=list)

@field_validator("pdfs")
@classmethod
def _cap_one(cls, v: list[PdfAttachment]) -> list[PdfAttachment]:
    if len(v) > 1:
        raise ValueError("v1 supports at most one attached PDF per source")
    if v and v[0].role != "primary":
        raise ValueError("the first (v1 only) PDF must have role=primary")
    return v
```

### Zod schema (site-side)

The plan's ingestion surface is Python, but the Astro site already parses source frontmatter via the Zod schema in `src/content.config.ts`. That schema must accept the new `pdfs` block so existing and new sources both validate. The site does not render the PDF in this plan — rendering is in the publish plan — but the schema must round-trip.

Hoist a named schema:

```typescript
import { createHash } from 'node:crypto';

const DOI_RE = /^10\.\d{4,9}\/\S+$/;

const pdfAttachmentSchema = z
  .object({
    path: z
      .string()
      .refine((p) => !nodePath.isAbsolute(p) && !p.split('/').includes('..'), {
        message: 'path must be relative and cannot contain ".."',
      }),
    role: z.enum(['primary', 'addendum', 'appendix', 'supplementary']).default('primary'),
    source_url: z
      .string()
      .refine(
        (s) =>
          (/^https?:\/\//i.test(s) && URL.canParse(s)) ||
          /^file:\/\//i.test(s) ||
          DOI_RE.test(s),
        { message: 'source_url must be http(s), file://, or a DOI (10.NNNN/...)' },
      )
      .optional(),
    sha256: z
      .string()
      .regex(/^[a-f0-9]{64}$/, 'sha256 must be 64 lowercase hex chars')
      .optional(),
    captured_date: z.coerce.date().optional(),
    page_count: z.number().int().positive().optional(),
    republish: z.boolean().default(false),
    license_note: z.string().nullable().default(null),
  })
  .strict()
  .superRefine((val, ctx) => {
    if (val.republish && !val.license_note?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['license_note'],
        message: 'license_note is required when republish is true',
      });
    }
  });

export type PdfAttachment = z.infer<typeof pdfAttachmentSchema>;
```

In the `sources` collection:

```typescript
pdfs: z.array(pdfAttachmentSchema).max(1).default([]),
```

`.strict()` is applied to the nested `pdf` object only (catches `license-note` vs `license_note` typos from hand-edited YAML); the outer sources schema stays permissive to avoid a behavior change for every existing source.

Audit sidecar (`auditSchema.sources_consulted[]`) gains two fields and a conditional refine:

```typescript
sources_consulted: z.array(
  z.object({
    id: z.string(),
    url: z.string().url(),
    title: z.string(),
    ingested: z.boolean(),
    surface: z.enum(['url', 'pdf']).default('url'),
    pdf_sha256: z.string().regex(/^[a-f0-9]{64}$/).optional(),
  }).superRefine((val, ctx) => {
    if (val.surface === 'pdf' && !val.pdf_sha256) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['pdf_sha256'],
        message: 'pdf_sha256 is required when surface is "pdf"' });
    }
    if (val.surface === 'url' && val.pdf_sha256) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['pdf_sha256'],
        message: 'pdf_sha256 must only be set when surface is "pdf"' });
    }
  }),
),
```

The enum is `'url' | 'pdf'` only. Wayback is an origin for the URL surface, not a third surface — if finer-grained provenance matters later, add a separate `archive` field. `.default('url')` keeps existing sidecars valid.

### Sources loader replacement

The sources collection today uses `glob({ pattern: '**/*.md', base: 'research/sources' })` — the built-in Astro loader. The built-in loader has no post-parse hook for filesystem sibling verification. This plan **replaces** it with a custom loader, mirroring the `claims-with-audit` pattern already in `content.config.ts`:

```typescript
const sources = defineCollection({
  loader: {
    name: 'sources-with-pdf',
    load: async ({ store, parseData, generateDigest, renderMarkdown }) => {
      store.clear();
      const base = nodePath.resolve('research/sources');
      const files = await walkMdFiles(base);

      for (const relPath of files) {
        const absPath = nodePath.join(base, relPath);
        const id = relPath.replace(/\.md$/, '').replace(/\\/g, '/');
        const content = await fs.readFile(absPath, 'utf-8');
        const { data: frontmatter, body } = parseMarkdownFrontmatter(content);
        const parsed = await parseData({ id, data: frontmatter });

        for (const pdf of parsed.pdfs ?? []) {
          const pdfAbs = nodePath.resolve(nodePath.dirname(absPath), pdf.path);
          if (!pdfAbs.startsWith(base + nodePath.sep)) {
            throw new Error(`[sources loader] pdf.path escapes research/sources: ${id}`);
          }
          let buf: Buffer;
          try {
            buf = await fs.readFile(pdfAbs);
          } catch (err: unknown) {
            if ((err as NodeJS.ErrnoException).code === 'ENOENT') {
              throw new Error(`[sources loader] pdf.path missing on disk: ${id} → ${pdf.path}`);
            }
            throw err;
          }
          if (pdf.sha256) {
            const actual = createHash('sha256').update(buf).digest('hex');
            if (actual !== pdf.sha256) {
              throw new Error(
                `[sources loader] sha256 mismatch for ${id}: expected ${pdf.sha256}, got ${actual}`,
              );
            }
          }
        }

        const digest = generateDigest(content);
        const rendered = await renderMarkdown(body);
        store.set({
          id, data: parsed, body,
          filePath: nodePath.join('research/sources', relPath),
          digest, rendered,
        });
      }
    },
  },
  schema: /* sources schema with pdfs */,
});
```

- Missing PDF on disk → **build fails**.
- sha256 mismatch → **build fails**.
- `path` escaping the sources root → **build fails** (belt-and-suspenders beside the Zod refine).
- Dev-server HMR trigger: editing the `.md` triggers reload; editing the PDF alone does not. Researchers re-run `dr attach-pdf` to refresh the hash, which edits the `.md`. Document this in `AGENTS.md`.

### Ingestor tool: `pdf_read`

New file: `pipeline/ingestor/tools/pdf_read.py`. A single tool, shape-compatible with `web_fetch` so the model's mental surface doesn't fork.

```python
async def pdf_read(ctx: RunContext[IngestorDeps], relative_path: str) -> dict:
    """Return extracted text + metadata from a locally attached PDF."""
```

Behavior:
- Resolve `relative_path` against `ctx.deps.repo_root` with a traversal guard (must live under `research/sources/`).
- If `ctx.deps.pdf_hint.sha256` is set, hash the file and raise `PdfIntegrityError` on mismatch. Do not silently extract from stale content.
- Extract title (PDF `/Title`, fallback to first non-empty line of page 1), publisher (from `/Author` or `/Producer`, else `None`), page-joined text, page count.
- Truncate returned text to the same order of magnitude as `web_fetch`'s HTML return.
- Return shape mirrors `web_fetch` so the instructions don't special-case PDF:

```python
{
    "text": "...",
    "title": "Privacy Policy",
    "publisher": "Viro ...",
    "page_count": 11,
    "truncated": False,
    "source_hint": {"type": "pdf", "path": "2022/viro-privacy-policy-2022.pdf"},
}
```

**Library choice.** `pypdf` — pure Python, MIT, no system deps. Reject `PyMuPDF` (AGPL) and `pdfplumber` (heavy, drags `pdfminer.six`). If `pypdf` returns no text, report and stop; OCR is a separate future plan.

### Orchestrator routing and agent variants

The chicken-and-egg resolves via the manifest (`_attachments.yaml`). `_select_source_surface` is URL-keyed:

```python
def _select_source_surface(url: str, manifest: AttachmentManifest) -> tuple[Literal["url","pdf"], PdfAttachment | None]:
    hit = manifest.lookup(url)
    if hit:
        return "pdf", hit.as_attachment()
    return "url", None
```

**Agent variants via conditional tool registration**, not via system-prompt guidance. The LLM cannot call a tool that is not registered, which is what we want.

```python
# pipeline/ingestor/agent.py
def build_ingestor_agent(surface: Literal["url", "pdf"]) -> Agent[IngestorDeps, IngestorOutput]:
    tools = [wayback_check] if surface == "url" else []
    tools.append(web_fetch if surface == "url" else pdf_read)
    return Agent(model, deps_type=IngestorDeps, output_type=IngestorOutput, tools=tools, ...)
```

The orchestrator calls `build_ingestor_agent("pdf")` when `_select_source_surface` returns `"pdf"`. `wayback_check` is intentionally not registered in PDF mode in v1 (the researcher who attached the PDF has already handled archival).

**Reactive fallback on `TerminalFetchError`.** When `web_fetch` raises terminal (401/402/403/451), the orchestrator checks `_attachments.yaml` before returning a `StepError`; if a manifest entry exists, it re-runs in PDF mode rather than surfacing the error. If no manifest entry exists, existing `StepError` behavior is unchanged.

### Audit trail integration

`_build_sources_consulted` in `pipeline/orchestrator/persistence.py` gains a `surface` parameter and emits `pdf_sha256` when `surface == "pdf"`:

```yaml
sources_consulted:
  - id: "2022/viro-privacy-policy-2022"
    url: "https://www.viro.app/privacy-policy"
    title: "Privacy Policy 2022"
    ingested: true
    surface: "pdf"
    pdf_sha256: "6f4c..."
```

This is the load-bearing line for verifier trust: a reader can see a claim was grounded in a PDF whose exact bytes are identified.

### Integrity enforcement — lint, not warning

sha256 mismatch has two enforcement points:

1. **`dr lint` (per `dr-lint.md`) walks every source with `pdfs:` and recomputes the hash.** Mismatch exits nonzero; the pre-commit hook blocks the commit. This is the primary gate — a researcher swapping a PDF on disk after attach cannot land the swap silently.
2. **The Astro build's custom loader re-verifies.** Mismatch fails the build. Deploy does not proceed.

This is stricter than the `audit-trail.md` precedent ("malformed sidecar → console.warn"). That precedent applies to *rendering* concerns, where a bad sidecar shouldn't block the rest of the site. This is an *integrity* concern where a bad hash invalidates the trust claim on the claim it supports. Different failure modes, different teeth.

### Human authoring flow

Canonical paths, in preference order:

1. **PDF-first bootstrap.** `dr attach-pdf ~/Downloads/foo.pdf --url https://foo.example/paper --slug foo-paper --year 2024`. The CLI:
   1. Copies (or moves with `--move`) the PDF to `research/sources/<year>/<slug>.pdf`.
   2. Computes sha256 and page_count.
   3. Upserts the manifest entry in `_attachments.yaml`.
   4. If no `.md` exists, invokes the ingestor in PDF-first mode and writes both the `.md` (with `pdfs:` block) and the manifest.
   5. If a stub `.md` exists, merges the `pdfs:` block into its frontmatter.

2. **Markdown-first retrofit.** An existing `.md` has a dead URL. Researcher drops the PDF and runs `dr attach-pdf --existing <slug> --year <year>`. The CLI computes hash/page_count, writes the `pdfs:` block, upserts the manifest; does not re-extract.

3. **Re-ingest.** `dr research --url <url>` as normal. The orchestrator sees the manifest entry and silently routes to PDF-first without the researcher having to know about the switch.

No path requires hand-editing frontmatter or the manifest. Hand-editing remains supported (all files are plain YAML) but is not the documented flow.

### Licensing / legal

- `research/` authored content (summaries, quote excerpts, prose) stays CC-BY-4.0 via `LICENSE-CONTENT`.
- Third-party PDFs retain the publisher's copyright.
- Storing a PDF in the public repo is already public (see "Public-repo reality" above). The research site's posture is fair-use archival coupled with criticism/commentary.
- `republish: false` (default) keeps the PDF out of `dist/` and off the site; it does *not* hide the file on GitHub.
- `republish: true` requires a human-written `license_note`. The companion publish plan handles the actual site exposure.
- **Takedown policy:** a rights-holder request is answered with `git rm` (plus history rewrite if requested), manifest entry removal, and a site rebuild. Documented in the repo README as part of this plan's rollout.

### Follow-ups outside this plan

- **Site republication surface** — `source-pdf-publish.md`. Handles the Astro page block, build-time asset copy, `_headers` `X-Robots-Tag: noindex` on PDFs, and the `republish: true` render path.
- **Triage tooling** — `dr list-attachment-candidates`, a small command that enumerates recent `StepError(error_type="http_4xx")` URLs from `checkpoints.json` and produces a worklist for researchers to attach PDFs against. Separate plan; depends on the `audit-trail.md` persistence contract.
- **OCR** — scanned PDFs return no text from `pypdf`. A future `.ocr.txt` sibling populated by a separate tool is the reserved namespace; implementation is out of scope.

## Implementation

1. **Pydantic.** Add `PdfAttachment` in `pipeline/common/models.py` with validators (relative path, sha256 regex, `republish → license_note`). Extend `SourceFrontmatter` in `pipeline/ingestor/models.py` with `pdfs: list[PdfAttachment]` and the v1 max-1 / `role=primary` validator. Add `pypdf` to `pipeline/pyproject.toml`.

2. **Manifest.** New module `pipeline/common/attachments.py`: `AttachmentManifest` loader/saver for `research/sources/_attachments.yaml`, with `lookup(url)` and `upsert(url, path, sha256)` / `remove(url)`.

3. **`pdf_read` tool.** New file `pipeline/ingestor/tools/pdf_read.py` with `PdfIntegrityError` exception. Hash verification happens inside the tool; traversal guard rejects any path not under `research/sources/`.

4. **Agent variants.** In `pipeline/ingestor/agent.py`, replace single-agent construction with `build_ingestor_agent(surface)`. `web_fetch` and `wayback_check` register only for `"url"`; `pdf_read` registers only for `"pdf"`. Drop any "call pdf_read first" guidance from `pipeline/ingestor/instructions.md` — structural separation makes it unnecessary.

5. **Orchestrator routing.** In `pipeline/orchestrator/pipeline.py`, add `_select_source_surface(url, manifest)`. Thread the result (and `PdfAttachment` hint if any) into `IngestorDeps`. Extend the `TerminalFetchError` branch to consult the manifest and re-run in PDF mode before returning `StepError`.

6. **Persistence.** In `pipeline/orchestrator/persistence.py`:
   - Serialize `pdfs:` round-trip (verify the Pydantic model serializes correctly).
   - `_build_sources_consulted` gains `surface` and emits `pdf_sha256` conditionally.
   - New helper `_attach_pdf(pdf_path, year, slug, republish, license_note) -> PdfAttachment` used by the CLI.

7. **CLI.** In `pipeline/orchestrator/cli.py`, add `dr attach-pdf`. Flags: `--url` (required for bootstrap), `--slug`, `--year`, `--existing`, `--move`, `--republish`, `--license`, `--dry-run`. All attach operations upsert the manifest.

8. **Zod + loader.** In `src/content.config.ts`:
   - Hoist `pdfAttachmentSchema` as a named const with the refines and `.strict()` + `superRefine` described above.
   - `export type PdfAttachment = z.infer<typeof pdfAttachmentSchema>;`.
   - Add `pdfs: z.array(pdfAttachmentSchema).max(1).default([])` to the sources schema.
   - Extend `auditSchema.sources_consulted[]` with `surface` + `pdf_sha256` and the conditional refine; drop any stray `'wayback'` enum value.
   - Replace the sources collection's `glob()` loader with the custom `sources-with-pdf` loader above. Import `createHash` from `node:crypto`.

9. **Integrity lint.** In `dr lint` (per `dr-lint.md`), walk all source `.md` files; for each `pdfs[].sha256`, recompute from the on-disk file; any mismatch or missing file exits nonzero. Also verify that every manifest entry points at an extant PDF and vice versa (manifest and frontmatter are consistent). Wire the lint into the pre-commit hook.

10. **Fixtures.** Add `pipeline/tests/fixtures/pdfs/`:
    - `minimal.pdf` — 1 page, synthetic, text "Hello world, this is a test PDF."
    - `multipage.pdf` — 3 pages, per-page known text.
    - `no-text.pdf` — image-only synthetic; `pypdf` returns empty text.
    - `corrupt.pdf` — truncated header bytes.
    - `sha256sums.txt` — checked-in hashes; fixture loader verifies on import so a fixture swap doesn't silently change test outcomes.
    A tiny `pipeline/tests/fixtures/_build_pdfs.py` regenerates the synthetic PDFs deterministically from source.

11. **Docs.** Update `AGENTS.md` with: the attach workflow, the reserved sibling-descriptor namespace, the lowercase-`.pdf` rule, and the HMR note. Add the takedown policy to the repo README.

## Test plan

Python (pytest):

- `test_pdf_attachment_model_validates`: valid + invalid `PdfAttachment` (absolute path rejected, `..` rejected, bad sha rejected, `republish=True` without `license_note` rejected).
- `test_sourcefrontmatter_pdfs_cap`: two-element `pdfs` rejected; single non-primary role rejected.
- `test_pdf_read_extracts_text_and_metadata`: on `minimal.pdf` fixture.
- `test_pdf_read_multipage_page_count`: on `multipage.pdf`.
- `test_pdf_read_no_text`: on `no-text.pdf`; assert empty-text signal, no crash.
- `test_pdf_read_corrupt_raises`: on `corrupt.pdf`.
- `test_pdf_read_integrity_mismatch_raises`: tamper hash, assert `PdfIntegrityError`.
- `test_pdf_read_traversal_rejected`: `../../etc/passwd`.
- `test_manifest_roundtrip`: upsert + save + load.
- `test_select_source_surface_pdf`: manifest hit → `"pdf"`.
- `test_select_source_surface_url`: no manifest entry → `"url"`.
- `test_agent_variant_url_lacks_pdf_read`: `build_ingestor_agent("url")` tool registry excludes `pdf_read`.
- `test_agent_variant_pdf_lacks_web_fetch`: inverse; structural proof, not behavioral.
- `test_orchestrator_falls_back_to_pdf_on_403`: mock 403 + manifest entry → agent rerun in PDF mode, no `StepError`.
- `test_orchestrator_stepErrors_on_403_without_manifest`: mock 403 + empty manifest → existing `StepError` behavior unchanged.
- `test_attach_pdf_bootstrap`: `.md`, PDF, and manifest all written; hashes match.
- `test_attach_pdf_existing_md_merge`: pre-existing `.md` preserved except for inserted `pdfs:` block.
- `test_audit_sidecar_records_pdf_surface`: `surface: pdf` + `pdf_sha256` present.
- `test_audit_sidecar_refuses_pdf_sha_on_url_surface`: Zod/Pydantic refusal.

Site (Astro / Vitest where applicable, otherwise manual build):

- Build with a fixture source carrying a `pdfs:` block and a matching on-disk PDF → build succeeds; `source.data.pdfs[0]` is populated.
- Build with `pdfs:` block but missing on-disk PDF → build **fails** with the expected error.
- Build with `pdfs:` block but corrupted on-disk bytes → build **fails** on sha mismatch.
- Build with a malformed `source_url` (not http/file/DOI) → build fails with the refine message.

Lint:

- `dr lint` on a repo with mismatched hash → nonzero exit, descriptive message.
- `dr lint` on an orphan manifest entry (manifest says attached, frontmatter does not) → nonzero exit.
- `dr lint` on an orphan frontmatter (frontmatter says attached, manifest does not) → nonzero exit.

Manual round-trip:

- `dr attach-pdf` against a real 403-blocked privacy-policy URL with a locally downloaded PDF. Verify: `.md` generated, quotes from the PDF, `_attachments.yaml` updated, `.audit.yaml` records `surface: pdf`, `dr lint` clean, build succeeds.

## Done when

1. `PdfAttachment` Pydantic model exists with all validators; existing sources without a `pdfs` block still validate.
2. `SourceFrontmatter.pdfs` is a length-≤1 list in v1.
3. `research/sources/_attachments.yaml` manifest is read/written by `AttachmentManifest` and kept in sync by `dr attach-pdf`.
4. `pdf_read` tool extracts title, text, and page_count from fixture PDFs; raises `PdfIntegrityError` on sha mismatch.
5. `build_ingestor_agent(surface)` registers `web_fetch`/`wayback_check` only for `"url"` and `pdf_read` only for `"pdf"`; no instruction-based steering.
6. Orchestrator uses the URL-keyed manifest to select surface; terminal HTTP codes fall back to PDF mode when a manifest entry exists.
7. `dr attach-pdf` bootstraps a new source from PDF+URL, retrofits a PDF onto an existing source, and keeps the manifest consistent.
8. Audit sidecar records `surface: "url" | "pdf"` and `pdf_sha256` when applicable; `wayback` is not a value in this enum.
9. `src/content.config.ts` accepts the new `pdfs` schema and extended `sources_consulted` schema; the sources collection uses the custom loader with sha verification.
10. `dr lint` fails on hash mismatch, missing PDF, or manifest/frontmatter inconsistency; the pre-commit hook invokes it.
11. Astro build fails (not warns) on hash mismatch, missing PDF, or path-traversal.
12. Fixture PDFs (minimal, multipage, no-text, corrupt) are checked in with a verified `sha256sums.txt`.
13. Docs updated: `AGENTS.md` attach workflow + sibling namespace; repo README takedown policy.

## Out of scope

- Site rendering of attached PDFs (download link, inline viewer, meta block) — `source-pdf-publish.md`.
- Build-time copy of `republish: true` PDFs to `dist/` and `_headers` `noindex` — `source-pdf-publish.md`.
- OCR of scanned / image-only PDFs.
- Multi-file attachments per source. Schema supports lists; CLI and validators cap at one in v1.
- Non-PDF attachments (images, video, audio, spreadsheets).
- Full-text search over attached PDFs.
- pdf.js inline viewer.
- Git LFS; >25 MB attachments remain exceptional.
- Triage tool (`dr list-attachment-candidates`) that enumerates `StepError`-flagged URLs — separate follow-up plan.
- Cross-source / cross-repo PDF deduplication. Co-location is compatible with future symlink-based dedup; hardlinks are not.
- Private-repo storage for non-redistributable PDFs. Architecturally reserved via a future manifest `storage:` field; not built in v1.

## Critical files

- `pipeline/common/models.py` — `PdfAttachment`.
- `pipeline/common/attachments.py` — manifest loader/saver (new).
- `pipeline/ingestor/models.py` — `SourceFrontmatter.pdfs` + cap validator.
- `pipeline/ingestor/tools/pdf_read.py` — new tool + `PdfIntegrityError`.
- `pipeline/ingestor/agent.py` — `build_ingestor_agent(surface)`.
- `pipeline/ingestor/instructions.md` — drop any stale "prefer pdf_read" guidance.
- `pipeline/orchestrator/pipeline.py` — `_select_source_surface`, manifest-driven fallback on `TerminalFetchError`.
- `pipeline/orchestrator/persistence.py` — `_attach_pdf`, `surface`/`pdf_sha256` in `_build_sources_consulted`.
- `pipeline/orchestrator/cli.py` — `dr attach-pdf` subcommand.
- `pipeline/pyproject.toml` — add `pypdf`.
- `src/content.config.ts` — hoist `pdfAttachmentSchema`, extend sources + audit schemas, replace `glob()` with custom `sources-with-pdf` loader.
- `research/sources/_attachments.yaml` — new manifest file (initially empty).
- `pipeline/tests/fixtures/pdfs/` — synthetic fixtures + `sha256sums.txt`.
- `AGENTS.md` — attach workflow + sibling descriptor namespace + lowercase `.pdf` rule.
- `README.md` — takedown policy.
