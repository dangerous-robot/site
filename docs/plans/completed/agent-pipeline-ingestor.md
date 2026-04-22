# Phase 4.1: Ingestor Agent -- Implementation Plan

**Phase**: 4.1
**Status**: done
**Depends on**: Phase 2 (schemas and content exist)
**Parent plan**: [agent-pipeline.md](agent-pipeline.md)

## Goal

Build a PydanticAI-based Ingestor agent that takes a URL and produces a valid source file (`research/sources/{yyyy}/{slug}.md`).

---

## 1. Python Project Structure

The `pipeline/` directory lives at the repo root, sibling to `src/`, `research/`, `scripts/`, and `docs/`. It is an independent Python package managed by `uv`. Flat layout (no `src/` intermediary) -- simpler for a CLI tool in a monorepo.

```
pipeline/
  pyproject.toml
  README.md
  common/
    __init__.py
    frontmatter.py       # YAML parse/strip/serialize utilities (shared with 4.2)
    content_loader.py    # Load source/claim/entity files by slug (shared with 4.2)
    models.py            # Shared enums: Verdict, Confidence, Category, SourceKind
  ingestor/
    __init__.py
    agent.py             # PydanticAI agent definition + system prompt
    cli.py               # CLI entry point (click)
    models.py            # Pydantic models matching Zod source schema
    tools/
      __init__.py
      web_fetch.py       # Fetch page content + extract metadata
      wayback.py         # Wayback Machine availability + save API
    validation.py        # Post-generation semantic validation
  tests/
    __init__.py
    conftest.py          # Shared fixtures, mock LLM setup
    test_agent.py        # Agent integration tests (mocked LLM)
    test_models.py       # Pydantic model validation tests
    test_tools.py        # Unit tests for each tool
    test_cli.py          # CLI invocation tests
    test_frontmatter.py  # Shared frontmatter read/write tests
    fixtures/
      sample_page.html   # Captured HTML for testing web_fetch
      sample_source.md   # Expected output for comparison
```

Notes:
- `common/` holds shared infrastructure used by both 4.1 and 4.2. File writing (previously `tools/file_writer.py`) moves here as `frontmatter.py` since both runners need frontmatter parsing.
- `ingestor/models.py` imports shared enums from `common/models.py` and defines source-specific models (`SourceFrontmatter`, `SourceFile`).

### pyproject.toml

```toml
[project]
name = "dangerous-robot-pipeline"
version = "0.1.0"
description = "PydanticAI runners for dangerousrobot.org research automation"
requires-python = ">=3.12"
dependencies = [
    "pydantic-ai>=0.1.0,<1.0",
    "pydantic>=2.0",
    "httpx>=0.27",
    "beautifulsoup4>=4.12",
    "pyyaml>=6.0",
    "click>=8.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "respx>=0.22",
]

[project.scripts]
ingest = "ingestor.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["common", "ingestor"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Note**: Verify `pydantic-ai` version pin at implementation time. The API uses `result_type` / `.data` -- if a newer version renames these, update the pin and agent definitions accordingly.

`.gitignore` additions: `pipeline/.venv/`, `pipeline/__pycache__/`.

---

## 2. Pydantic Models

Must match the Zod schema in `src/content.config.ts` exactly.

```python
# pipeline/ingestor/models.py

from __future__ import annotations
import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator


class SourceKind(str, Enum):
    REPORT = "report"
    ARTICLE = "article"
    DOCUMENTATION = "documentation"
    DATASET = "dataset"
    BLOG = "blog"
    VIDEO = "video"
    INDEX = "index"


class SourceFrontmatter(BaseModel):
    """Mirrors the Zod source schema in content.config.ts."""
    url: HttpUrl
    archived_url: Optional[HttpUrl] = None
    title: str
    publisher: str
    published_date: Optional[datetime.date] = None
    accessed_date: datetime.date
    kind: SourceKind
    summary: str = Field(max_length=200)
    key_quotes: Optional[list[str]] = None

    @field_validator("summary")
    @classmethod
    def summary_word_count(cls, v: str) -> str:
        """AGENTS.md content rule: summaries must not paraphrase beyond 30 words."""
        word_count = len(v.split())
        if word_count > 30:
            raise ValueError(
                f"Summary has {word_count} words; AGENTS.md limits summaries to 30 words"
            )
        return v


class SourceFile(BaseModel):
    """Complete source file: frontmatter + Markdown body."""
    frontmatter: SourceFrontmatter
    body: str = Field(description="Markdown body with additional context about the source")
    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", description="Kebab-case filename slug")
    year: int = Field(description="Publication or access year, for directory placement")
```

Key schema fidelity notes:
- `url`/`archived_url` use `HttpUrl`, matching Zod's `z.string().url()`
- `summary` has `max_length=200` matching `z.string().max(200)`
- 30-word content rule from AGENTS.md enforced via custom validator (stricter than schema)
- `kind` enum values identical to Zod enum array

**HttpUrl serialization**: Pydantic v2's `HttpUrl` is a rich type that serializes as `Url('https://...')`, not a plain string. The `frontmatter.py` YAML serializer must register a custom representer that calls `str()` on `HttpUrl` values. Alternatively, use a plain `str` field with a `@field_validator` that calls `HttpUrl(v)` for validation only. Either approach works -- the key constraint is that YAML output must contain plain URL strings to match what Zod expects.

---

## 3. Ingestor Agent Design

### Agent definition

```python
# pipeline/ingestor/agent.py

from dataclasses import dataclass
from pydantic_ai import Agent, RunContext

@dataclass
class IngestorDeps:
    """Dependencies injected into the agent -- swappable for testing."""
    http_client: httpx.AsyncClient
    repo_root: str
    today: datetime.date = datetime.date.today()

ingestor_agent = Agent(
    model="anthropic:claude-sonnet-4-20250514",
    result_type=SourceFile,
    deps_type=IngestorDeps,
    system_prompt=SYSTEM_PROMPT,
    retries=2,
)
```

**Agent-level timeout**: Wrap `ingestor_agent.run()` in `asyncio.wait_for(timeout=120)` in the CLI to prevent runaway tool-call loops. The 30s timeout on `web_fetch` covers HTTP calls, but the overall agent run (including LLM reasoning + retries) needs its own cap.

### System prompt

```
You are the Ingestor agent for dangerousrobot.org. Your job is to read a web page
and produce a structured source file for the research archive.

## Output format

You must return a SourceFile with these fields:

### frontmatter (all required unless noted):
- url: the original URL provided by the user (do NOT change it)
- archived_url: Wayback Machine URL if available (optional)
- title: the page's title, cleaned of site-name suffixes
- publisher: the organization that published the content
- published_date: date originally published (optional, omit if unknown)
- accessed_date: today's date (provided in context)
- kind: one of: report, article, documentation, dataset, blog, video, index
- summary: factual summary, MAX 30 words and MAX 200 characters.
  Do NOT editorialize. State what the source contains, not what you think of it.
- key_quotes: 0-5 notable direct quotes from the source (optional)

### body:
- 1-3 sentences of additional context. Factual, not evaluative.

### slug:
- Lowercase kebab-case. Derived from the title or topic.

### year:
- Publication year if published_date is known, otherwise access year.

## Content rules (from AGENTS.md):
1. Summaries must NOT paraphrase beyond 30 words.
2. Every source SHOULD have an archived_url when possible.
3. Key quotes must be EXACT text from the source -- never fabricate quotes.

## What NOT to do:
- Do not make claims or verdicts about the source content.
- Do not invent quotes. If you cannot find notable quotes, omit key_quotes.
- Do not include the site name in the title.
```

### Agent tools

#### web_fetch (`tools/web_fetch.py`)

Registered as `@ingestor_agent.tool`. Uses `ctx.deps.http_client` (httpx) with 30s timeout. Parses HTML with BeautifulSoup4 to extract `<title>`, meta description, `article:published_time`, author, Open Graph tags. Strips nav/footer/script/style, extracts text content. Truncates to ~50k chars for context limits.

Returns: `{ raw_html, title, meta_description, meta_author, meta_date, text_content }`

#### wayback (`tools/wayback.py`)

Two functions:
- `check_wayback`: Calls `https://archive.org/wayback/available?url={url}`. Returns `{ available, archived_url, timestamp }`.
- `save_to_wayback`: POSTs to `https://web.archive.org/save/{url}`. Best-effort -- logs warning on failure and continues without archived URL.

#### file_writer (`common/frontmatter.py`)

NOT an agent tool -- runs after the agent returns. Serializes `SourceFile` to YAML-frontmattered Markdown. Uses `pyyaml` with custom representers for dates (YYYY-MM-DD) and URLs (plain strings). Creates year directory if needed. Refuses to overwrite existing files. Lives in `common/` because 4.2 also needs frontmatter parsing.

---

## 4. CLI Interface

```python
# pipeline/ingestor/cli.py

@click.command()
@click.argument("url")
@click.option("--repo-root", default=None, help="Path to site repo root. Auto-detects via git.")
@click.option("--dry-run", is_flag=True, help="Print output to stdout instead of writing.")
@click.option("--model", default="anthropic:claude-sonnet-4-20250514")
@click.option("--skip-wayback", is_flag=True, help="Skip Wayback Machine check/save.")
def main(url, repo_root, dry_run, model, skip_wayback):
    """Ingest a URL and produce a source file for dangerousrobot.org research."""
```

Usage examples:

```bash
uv run ingest https://futureoflife.org/ai-safety-index-winter-2025/
uv run ingest --dry-run https://example.com/report
uv run ingest --model anthropic:claude-haiku-3 https://example.com/report
uv run ingest --skip-wayback https://example.com/report
```

CLI flow:
1. Resolve `repo_root` via `git rev-parse --show-toplevel` or provided path
2. Validate URL
3. Create `IngestorDeps` with httpx client
4. Run agent: `result = await ingestor_agent.run(url, deps=deps)`
5. Run semantic validation
6. `--dry-run`: print to stdout. Otherwise: write file.
7. Print path and success message.

---

## 5. Validation

Three levels:

**Level 1 -- Pydantic (automatic)**: Field types, constraints, 30-word validator. PydanticAI retries on validation failure.

**Level 2 -- Semantic (`validation.py`)**: Post-generation checks:
- File conflict (target path already exists)
- URL match (output URL matches input URL)
- Summary length double-check
- Slug format (lowercase kebab-case regex)
- Year plausibility (2000 to current year)
- `archived_url` domain check (must be `web.archive.org`)
- Key-quote verification: check that each `key_quote` is a substring of the fetched page content (catches hallucinated quotes automatically rather than relying solely on `--dry-run` human review)

**Level 3 -- Astro build**: The written file is validated by Zod schemas on `npm run build`. This is the ultimate source of truth.

---

## 6. Testing Strategy

### Unit tests (`test_models.py`)
- Valid/invalid SourceFrontmatter permutations
- 200-char limit, 30-word limit, invalid kind, invalid URL, slug format
- Optional fields can be omitted

### Tool tests (`test_tools.py`)
- Uses `respx` to mock httpx responses
- `fetch_page` title extraction, timeout handling
- `check_wayback` available/not available
- `save_to_wayback` success/rate-limited
- `write_source_file` correct path, frontmatter format, overwrite refusal, date formatting

### Agent tests (`test_agent.py`)
- PydanticAI `TestModel` for mocked LLM
- Verify agent produces valid `SourceFile`
- Verify URL passthrough
- Verify agent handles tool errors gracefully (e.g., `check_wayback` returns error -> `SourceFile` has `archived_url = None`)

### CLI tests (`test_cli.py`)
- `click.testing.CliRunner`
- `--dry-run` prints without writing
- Invalid URL errors gracefully
- Missing URL shows help

### Integration tests
- **Read direction**: Parse existing `research/sources/2025/fli-safety-index.md` with `SourceFrontmatter` model. Confirms Pydantic model stays in sync with actual files.
- **Write direction (round-trip)**: Create a `SourceFile` instance, serialize through `frontmatter.py`, parse the output YAML back, and compare field values. Catches serialization bugs (e.g., `HttpUrl` printing as `Url(...)`, dates with timestamps, enum values as uppercase Python names) before they hit the Astro build.

---

## 7. Error Handling

| Failure mode | Behavior |
|---|---|
| URL unreachable | Tool returns error dict. CLI exits code 1 with message. |
| Non-HTML content (PDF) | Attempt basic extraction or error with "unsupported content type". |
| Wayback API fails | Warning logged. Agent proceeds without `archived_url`. |
| LLM output fails validation | PydanticAI retries (2 retries). Final failure exits code 1. |
| Summary > 30 words | Treated as validation error. PydanticAI retries. |
| Hallucinated quotes | Semantic validation checks key_quotes against fetched page content (substring match). Remaining false positives caught via `--dry-run` human review. |
| Agent run timeout | `asyncio.wait_for(timeout=120)` kills runaway agent. CLI exits code 1. |
| File already exists | CLI exits code 1 with path message. |
| No API key | CLI exits code 2: "Set ANTHROPIC_API_KEY environment variable." |

Exit codes: `0` success, `1` recoverable error, `2` configuration error.

---

## 8. Open Decisions

| # | Decision | Options | Recommendation | Rationale |
|---|---|---|---|---|
| ~~1~~ | ~~Python tooling~~ | | `uv` | **Decided.** Already installed. Faster, single tool. |
| 2 | Default LLM model | Sonnet vs Haiku | Sonnet default, Haiku via `--model` | Summarization quality matters. Cost per invocation is low. |
| 3 | CLI framework | `click` vs `argparse` | `click` | Cleaner API, testable via `CliRunner`. |
| 4 | HTML parsing | `beautifulsoup4` vs `trafilatura` | `beautifulsoup4` | Widely used, fewer transitive deps. |
| ~~5~~ | ~~`pipeline/` location~~ | | Repo root, flat layout | **Decided.** Polyglot repo accepted. Flat layout (no `src/` intermediary) for simplicity. |
| 6 | Wayback save behavior | Always vs save-if-missing vs opt-in | Save-if-missing, `--skip-wayback` to disable | Respects rate limits. |
| 7 | Retry count | 1 vs 2 vs 3 | 2 retries | Two chances to fix validation errors. |
| 8 | API key source | Env var vs `.env` vs CLI flag | `ANTHROPIC_API_KEY` env var | PydanticAI reads this by default. |

---

## Implementation Sequence

| Step | Task | Estimate |
|---|---|---|
| 1 | Scaffold `pipeline/` with `pyproject.toml`, `.gitignore`, `uv sync` | 30 min |
| 2 | Implement + test `models.py` | 30 min |
| 3 | Implement + test `tools/` (web_fetch, wayback, file_writer) | 1-2 hours |
| 4 | Implement + test `agent.py` with system prompt | 1 hour |
| 5 | Implement + test `cli.py` | 30 min |
| 6 | Implement `validation.py`, wire into CLI | 30 min |
| 7 | Integration test against existing source files | 30 min |
| 8 | `pipeline/README.md`, update `docs/architecture/research-workflow.md` | 15 min |

---

## Critical Files

- `src/content.config.ts` -- Zod schemas (source of truth for Pydantic models)
- `research/sources/2025/fli-safety-index.md` -- Reference for output format
- `AGENTS.md` -- Content rules encoded in system prompt and validators
- `docs/plans/completed/agent-pipeline.md` -- Parent plan to update as work progresses

## Review history

| Date | Reviewer | Scope | Changes |
|---|---|---|---|
| 2026-04-22 | agent (cursory review) | completed-check | Added review history section; no unfinished work found |
