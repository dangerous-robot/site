#!/usr/bin/env python3
"""Word-frequency source data for the taxonomy analysis and word clouds.

Four corpora, each written to data/word-frequency/<name>.json:
  docs                - prose in docs/**/*.md + AGENTS.md + CLAUDE.md + README.md
  pipeline-identifiers - names (class/function/variable) in pipeline/**/*.py, snake_case split
  site-identifiers     - names in src/**/*.{ts,astro} frontmatter, camelCase split
  ui-copy              - visible text readers see in src templates (tags/expressions stripped)

Run from repo root: .venv/bin/python docs/reports/codebase-analysis-2026-07/scripts/word_frequency.py
"""

import ast
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()
OUT_DIR = ROOT / "docs/reports/codebase-analysis-2026-07/data/word-frequency"
EXCLUDE_PARTS = {".venv", "node_modules", "__pycache__", ".astro", "dist"}

STOPWORDS = set("""
a about above after again all also an and any are as at be because been before being below between both but by
can could did do does doing down during each few for from further had has have having he her here hers him his how
i if in into is it its itself just like me more most my no nor not now of off on once only or other our out over
own same she should so some such than that the their them then there these they this those through to too under
until up very was we were what when where which while who whom why will with would you your yours
md yaml json http https www com org github file files line lines new use used using see also may via eg ie etc
true false null none str int list dict bool default optional self cls return type value values name key
""".split())

# words too generic to be interesting in identifier clouds
IDENTIFIER_NOISE = {"get", "set", "add", "run", "main", "init", "test", "tests", "data", "item", "items",
                    "result", "results", "obj", "arg", "args", "kwargs", "params", "param", "props", "prop",
                    "index", "idx", "tmp", "temp", "util", "utils", "helper", "handler"}

WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z'-]{2,}")
CAMEL_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])")


def split_identifier(name):
    parts = []
    for chunk in name.split("_"):
        parts.extend(CAMEL_RE.findall(chunk))
    return [p.lower() for p in parts if len(p) > 2]


def strip_markdown(text):
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL)      # frontmatter
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)            # code blocks
    text = re.sub(r"`[^`]*`", " ", text)                               # inline code
    text = re.sub(r"https?://\S+", " ", text)                          # urls
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)               # links -> text
    return text


def docs_corpus():
    words, bigrams = Counter(), Counter()
    files = list((ROOT / "docs").rglob("*.md")) + [ROOT / n for n in ("AGENTS.md", "CLAUDE.md", "README.md")]
    n = 0
    for f in files:
        if not f.exists() or EXCLUDE_PARTS & set(f.parts):
            continue
        n += 1
        tokens = [w.lower() for w in WORD_RE.findall(strip_markdown(f.read_text(errors="replace")))]
        kept = [t for t in tokens if t not in STOPWORDS]
        words.update(kept)
        for a, b in zip(kept, kept[1:]):
            bigrams.update([f"{a} {b}"])
    return words, bigrams, n


def pipeline_identifiers():
    full, parts = Counter(), Counter()
    n = 0
    for f in (ROOT / "pipeline").rglob("*.py"):
        if EXCLUDE_PARTS & set(f.parts):
            continue
        try:
            tree = ast.parse(f.read_text(errors="replace"))
        except SyntaxError:
            continue
        n += 1
        for node in ast.walk(tree):
            names = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.append(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                names.append(node.id)
            for name in names:
                if name.startswith("__"):
                    continue
                full.update([name])
                parts.update(p for p in split_identifier(name)
                             if p not in STOPWORDS and p not in IDENTIFIER_NOISE)
    return full, parts, n


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
TS_NAME_RE = re.compile(r"\b(?:function|const|let|var|interface|type|class|enum)\s+([A-Za-z_]\w*)")


def site_identifiers():
    full, parts = Counter(), Counter()
    n = 0
    for f in (ROOT / "src").rglob("*"):
        if f.suffix not in (".ts", ".astro") or EXCLUDE_PARTS & set(f.parts):
            continue
        text = f.read_text(errors="replace")
        if f.suffix == ".astro":
            m = FRONTMATTER_RE.match(text)
            text = m.group(1) if m else ""
        n += 1
        for name in TS_NAME_RE.findall(text):
            full.update([name])
            parts.update(p for p in split_identifier(name)
                         if p not in STOPWORDS and p not in IDENTIFIER_NOISE)
    return full, parts, n


def ui_copy():
    """Visible template text: strip frontmatter, JSX-ish expressions, tags, styles/scripts."""
    words, phrases = Counter(), Counter()
    attr_re = re.compile(r"""(?:title|alt|aria-label|label|placeholder)\s*=\s*["']([^"'{}]{3,})["']""")
    n = 0
    for base in ("src/pages", "src/components", "src/layouts", "src/content"):
        for f in (ROOT / base).rglob("*"):
            if f.suffix not in (".astro", ".md") or EXCLUDE_PARTS & set(f.parts):
                continue
            n += 1
            text = f.read_text(errors="replace")
            if f.suffix == ".md":
                body = strip_markdown(text)
            else:
                body = FRONTMATTER_RE.sub("", text, count=1)
                for m in attr_re.finditer(body):
                    phrases.update([m.group(1).strip()])
                body = re.sub(r"<style[\s\S]*?</style>|<script[\s\S]*?</script>", " ", body)
                body = re.sub(r"\{[^{}]*\}", " ", body)   # expressions (one nesting level)
                body = re.sub(r"<[^>]+>", " ", body)      # tags
            tokens = [w.lower() for w in WORD_RE.findall(body)]
            words.update(t for t in tokens if t not in STOPWORDS)
    return words, phrases, n


def write(name, payload):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"{name}.json").write_text(json.dumps(payload, indent=1))


def main():
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    meta = {"commit": head, "generated_by": "word_frequency.py"}

    words, bigrams, n = docs_corpus()
    write("docs", {"meta": {**meta, "files": n, "corpus": "docs prose"},
                   "words": words.most_common(300), "bigrams": bigrams.most_common(150)})

    full, parts, n = pipeline_identifiers()
    write("pipeline-identifiers", {"meta": {**meta, "files": n, "corpus": "pipeline python identifiers"},
                                   "word_parts": parts.most_common(300), "identifiers": full.most_common(200)})

    full, parts, n = site_identifiers()
    write("site-identifiers", {"meta": {**meta, "files": n, "corpus": "src ts/astro identifiers"},
                               "word_parts": parts.most_common(300), "identifiers": full.most_common(200)})

    words, phrases, n = ui_copy()
    write("ui-copy", {"meta": {**meta, "files": n, "corpus": "reader-visible template text"},
                      "words": words.most_common(300), "labeled_phrases": phrases.most_common(150)})

    print("word-frequency: 4 corpora written")


if __name__ == "__main__":
    main()
