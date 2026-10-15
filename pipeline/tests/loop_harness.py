"""Scripted agents and fixtures for driving ``loop.run`` through its public entry.

Every test that uses this module reaches the loop the way a command does:
``loop.run(ClaimSpec, VerifyConfig)`` or the ``dr`` CLI, with the four agents
(planner, scorer, ingestor, analyst, Evaluator) on scripted models and
``researcher.decomposed.execute_searches`` patched. Nothing here patches a
private name under ``pipeline/loop/``.

The ingest model fetches the requested URL (served from the search result's
``raw_content``, so no HTTP call is made) and then returns a source for it,
so ``fetch_failure_reason`` is None without patching it.
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from pathlib import Path
from unittest.mock import patch

from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

ENTITY_REF = "subjects/probe-subject"
ENTITY_NAME = "Probe Subject"
SENTENCE = "Probe Subject data centers used more than 4% of US electricity in 2024"

# Four candidate pages, enough to pass the four-source threshold.
URLS = [
    "https://example.org/report",
    "https://example.org/second-report",
    "https://example.org/third-report",
    "https://example.org/fourth-report",
]
# Each page names every harness sub-question's terms, so the post-ingest text
# check (RE-BA, Source pool rules) confirms the scorer's tags on every page.
PAGE_TEXT = {
    u: (
        f"Page {i + 1}. Probe Subject data centers used more than 4% of US electricity in 2024. "
        "Third parties confirm the energy data it publishes; some evidence shows a lower share."
    )
    for i, u in enumerate(URLS)
}
# One counter-evidence sub-question (RE-BA, Source pool rules): the planner must
# emit one, with at least one query, so the harness plan carries it too.
COUNTER_SUB_QUESTION = {
    "id": "sq3",
    "question": "What evidence shows the share of electricity was below 4%?",
    "rationale": "what would falsify the claim",
    "kind": "counter-evidence",
}
SUB_QUESTIONS = [
    {"id": "sq1", "question": "Does the subject publish energy data?", "rationale": "first-party axis"},
    {"id": "sq2", "question": "Do third parties confirm it?", "rationale": "independent axis"},
    COUNTER_SUB_QUESTION,
]
URL_ADDRESSES = {URLS[0]: ["sq1"], URLS[1]: ["sq1", "sq2"], URLS[2]: ["sq2"], URLS[3]: ["sq1"]}


def planner_args(queries: list[str] | None = None) -> dict:
    """The harness plan: two coverage sub-questions and the counter-evidence one.

    ``queries`` are the coverage queries (the first for sq1, the rest for sq2);
    the counter-evidence sub-question always gets its own query.
    """
    queries = queries or ["probe subject energy report", "probe subject energy independent"]
    return {
        "sub_questions": list(SUB_QUESTIONS),
        "queries": [
            {"text": q, "sub_question_id": "sq1" if i == 0 else "sq2"} for i, q in enumerate(queries)
        ] + [{"text": "probe subject electricity share disputed", "sub_question_id": "sq3"}],
        "rationale": "two axes and a counter-evidence check",
    }


def scorer_args(urls: list[str] | None = None, *, kept: bool = True) -> dict:
    urls = urls if urls is not None else URLS
    if not kept:
        return {"kept": [], "dropped": list(urls), "rationale": "nothing relevant"}
    return {
        "kept": [{"url": u, "addresses": URL_ADDRESSES.get(u, ["sq1"]), "score": 4.0} for u in urls],
        "dropped": [],
        "rationale": "all relevant",
    }


def analyst_args(
    *,
    title: str = "Probe Subject used over four percent of US electricity",
    verdict: str = "mixed",
    confidence: str = "medium",
    level: str = "partially-verified",
    cited_sources: list[str] | None = None,
    narrative: str = "The evidence is mixed.",
    cap_rationale: str | None = None,
) -> dict:
    out = {
        "title": title,
        "topics": ["environmental-impact"],
        "verdict": verdict,
        "confidence": confidence,
        "narrative": narrative,
        "verification_level": level,
        "seo_title": "Probe Subject electricity share",
    }
    if cited_sources is not None:
        out["cited_sources"] = list(cited_sources)
    if cap_rationale is not None:
        out["cap_rationale"] = cap_rationale
    return out


def auditor_args(
    *, verdict: str = "mixed", confidence: str = "medium", evidence_gaps: list[str] | None = None
) -> dict:
    return {
        "verdict": verdict,
        "confidence": confidence,
        "reasoning": "Independent assessment.",
        "evidence_gaps": list(evidence_gaps or []),
    }


def fake_execute_searches(urls: list[str] | None = None, page_text: dict[str, str] | None = None):
    """A stand-in for ``researcher.decomposed.execute_searches`` returning scripted candidates."""
    from researcher.scorer import SearchCandidate

    urls = urls if urls is not None else URLS
    text = page_text if page_text is not None else PAGE_TEXT

    async def _run(queries, client, **_kwargs):
        return [
            SearchCandidate(
                url=u, title=f"Report {i + 1}", snippet="snippet", from_query=queries[0],
                raw_content=text.get(u),
            )
            for i, u in enumerate(urls)
        ]

    return _run


def ingest_model(
    *, key_quotes: dict[str, list[str]] | None = None, publisher: str = "Example Publisher",
) -> FunctionModel:
    """An ingest model that fetches the requested URL, then returns a source for it."""
    quotes = key_quotes or {}

    async def _fn(messages, info: AgentInfo) -> ModelResponse:
        parts = [p for m in messages for p in getattr(m, "parts", [])]
        prompt = next(p.content for p in parts if isinstance(p, UserPromptPart))
        url = prompt.split("URL: ", 1)[1].split("\n", 1)[0]
        called = [p.tool_name for p in parts if isinstance(p, ToolCallPart)]
        if not called:
            return ModelResponse(parts=[ToolCallPart(tool_name="web_fetch", args={"url": url})])
        frontmatter = {
            "url": url,
            "title": f"Report at {url.rsplit('/', 1)[-1]}",
            "publisher": publisher,
            "accessed_date": "2026-10-14",
            "kind": "article",
            "summary": "A factual summary of the report.",
        }
        if url in quotes:
            frontmatter["key_quotes"] = list(quotes[url])
        source = {"frontmatter": frontmatter, "body": "Body of the report.", "slug": "page", "year": 2026}
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=source)])

    return FunctionModel(_fn)


def capturing_model(captured: list[str], args: dict, *, calls: list[str] | None = None, name: str = "") -> FunctionModel:
    """A model that records its user prompt (and a call tally) and returns scripted output."""

    async def _fn(messages, info: AgentInfo) -> ModelResponse:
        for message in messages:
            for part in getattr(message, "parts", []):
                if isinstance(part, UserPromptPart):
                    captured.append(str(part.content))
        if calls is not None:
            calls.append(name)
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])

    return FunctionModel(_fn)


def failing_model(exc: Exception | None = None, *, calls: list | None = None) -> FunctionModel:
    """A model whose every run raises, so the agent step fails after its retries.

    ``calls`` (a list) gains one entry per model run, so a test can count the
    attempts a retry rule made.
    """

    async def _fn(messages, info: AgentInfo) -> ModelResponse:
        if calls is not None:
            calls.append("run")
        raise exc or RuntimeError("scripted model failure")

    return FunctionModel(_fn)


def flaky_model(args: dict, *, fail_times: int = 1, exc: Exception | None = None, calls: list | None = None) -> FunctionModel:
    """A model that raises on its first ``fail_times`` runs, then returns ``args``.

    For the recovered-retry cases: the first attempt fails, the retry succeeds.
    """
    seen: list[str] = []

    async def _fn(messages, info: AgentInfo) -> ModelResponse:
        seen.append("run")
        if calls is not None:
            calls.append("run")
        if len(seen) <= fail_times:
            raise exc or RuntimeError("scripted transient failure")
        return ModelResponse(parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)])

    return FunctionModel(_fn)


def counting_search(urls: list[str] | None = None, *, calls: list):
    """``fake_execute_searches`` that also counts how many times research ran."""
    inner = fake_execute_searches(urls)

    async def _run(queries, client, **kwargs):
        calls.append("search")
        return await inner(queries, client, **kwargs)

    return _run


def counting_ingest_model(calls: list, *, fail: Exception | None = None) -> FunctionModel:
    """An ingest model that counts each URL it is asked for (first turn only).

    With ``fail`` set, every run raises it instead, so each URL's ingest fails
    the same way (a transport failure on every page, say).
    """
    inner = ingest_model()

    async def _fn(messages, info: AgentInfo) -> ModelResponse:
        parts = [p for m in messages for p in getattr(m, "parts", [])]
        called = [p.tool_name for p in parts if isinstance(p, ToolCallPart)]
        if not called:
            calls.append("ingest")
        if fail is not None:
            raise fail
        return await inner.function(messages, info)

    return FunctionModel(_fn)


@contextmanager
def scripted_agents(
    *,
    planner: dict | None = None,
    scorer: dict | None = None,
    analyst: dict | None = None,
    auditor: dict | None = None,
    analyst_model=None,
    auditor_model=None,
    ingestor=None,
    search=None,
    tiebreaker: dict | None = None,
    tiebreaker_model=None,
):
    """Put every agent on a scripted model and patch the search executor.

    ``analyst_model`` and ``auditor_model`` take a ready model (for capturing
    or failing runs); ``analyst`` and ``auditor`` take ``custom_output_args``
    for a ``TestModel``. ``tiebreaker`` and ``tiebreaker_model`` do the same
    for the tie-breaker (RE-AT, Rules, findings file, tie-breaker); with
    neither, the tie-breaker answers ``mixed`` at medium confidence, so a
    scripted disagreement still settles. The loop's own ``Agent.override``
    calls are made no-ops so the scripted models survive them.
    """
    from analyst.agent import analyst_agent, verdict_only_agent
    from auditor.agent import auditor_agent
    from ingestor.agent import ingestor_agent
    from researcher.planner import research_planner_agent
    from researcher.scorer import url_scorer_agent

    analyst_m = analyst_model or TestModel(custom_output_args=analyst or analyst_args())
    auditor_m = auditor_model or TestModel(custom_output_args=auditor or auditor_args())
    tiebreaker_m = tiebreaker_model or TestModel(custom_output_args=tiebreaker or auditor_args())
    # The package lands with RE-AT; until then the override is skipped so the
    # harness still imports at the base commit.
    try:
        from loop.tiebreaker.agent import tiebreaker_agent
    except ImportError:
        tiebreaker_agent = None
    tiebreaker_override = (
        tiebreaker_agent.override(model=tiebreaker_m) if tiebreaker_agent is not None else nullcontext()
    )
    with (
        research_planner_agent.override(model=TestModel(custom_output_args=planner or planner_args())),
        url_scorer_agent.override(model=TestModel(custom_output_args=scorer or scorer_args())),
        ingestor_agent.override(model=ingestor or ingest_model()),
        verdict_only_agent.override(model=analyst_m),
        analyst_agent.override(model=analyst_m),
        auditor_agent.override(model=auditor_m),
        tiebreaker_override,
        patch("researcher.decomposed.execute_searches", side_effect=search or fake_execute_searches()),
        patch.object(Agent, "override", side_effect=lambda **kw: nullcontext()),
    ):
        yield


def write_entity(repo_root: Path, ref: str = ENTITY_REF, name: str = ENTITY_NAME) -> str:
    """Write a minimal entity file for ``ref`` and return the ref."""
    type_dir, slug = ref.split("/", 1)
    entity_type = {"subjects": "subject", "products": "product", "companies": "company"}[type_dir]
    path = repo_root / "research" / "entities" / type_dir / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {name}\ntype: {entity_type}\ndescription: A test entity.\n---\n",
        encoding="utf-8",
    )
    return ref


def claim_spec(repo_root: Path, sentence: str = SENTENCE, ref: str = ENTITY_REF, **kwargs):
    """Build the loop's ``ClaimSpec`` for an entity file on disk."""
    from loop import ClaimSpec
    from orchestrator.entity_resolution import parse_entity_ref

    return ClaimSpec(statement=sentence, entity=parse_entity_ref(ref, repo_root), **kwargs)


def loop_config(repo_root: Path, **overrides):
    from loop import VerifyConfig

    kwargs = {"model": "test", "max_sources": 4, "skip_wayback": True, "repo_root": str(repo_root)}
    kwargs.update(overrides)
    return VerifyConfig(**kwargs)


def claim_dir(repo_root: Path, ref: str = ENTITY_REF) -> Path:
    return repo_root / "research" / "claims" / ref


def written_claims(repo_root: Path, ref: str = ENTITY_REF) -> list[Path]:
    d = claim_dir(repo_root, ref)
    return sorted(p for p in d.glob("*.md")) if d.exists() else []


def written_sources(repo_root: Path) -> list[Path]:
    d = repo_root / "research" / "sources"
    return sorted(d.rglob("*.md")) if d.exists() else []
