"""YAML frontmatter parse/strip/serialize utilities."""

from __future__ import annotations

import datetime
import enum
import re
from typing import Any

import yaml


# --- Custom YAML dumper ---

class _FrontmatterDumper(yaml.SafeDumper):
    """YAML dumper with custom representers for frontmatter output."""


def _represent_date(dumper: yaml.SafeDumper, data: datetime.date) -> yaml.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:str", data.isoformat())


def _represent_none(dumper: yaml.SafeDumper, _data: None) -> yaml.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:null", "")


def _represent_enum(dumper: yaml.SafeDumper, data: enum.Enum) -> yaml.ScalarNode:
    return dumper.represent_data(data.value)


_FrontmatterDumper.add_representer(datetime.date, _represent_date)
_FrontmatterDumper.add_representer(type(None), _represent_none)
_FrontmatterDumper.add_multi_representer(enum.Enum, _represent_enum)


# --- Frontmatter delimiter pattern ---

_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(.*?)^---[ \t]*\r?\n",
    re.MULTILINE | re.DOTALL,
)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a markdown file into (frontmatter dict, body string).

    Raises ValueError if no valid frontmatter delimiters are found.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("No YAML frontmatter found")
    raw_yaml = match.group(1)
    body = text[match.end():]
    data = yaml.safe_load(raw_yaml) or {}
    return data, body


def strip_frontmatter(text: str) -> str:
    """Return just the body, stripping frontmatter."""
    _, body = parse_frontmatter(text)
    return body


def _clean_for_serialize(obj: Any) -> Any:
    """Recursively remove keys with None values from dicts."""
    if isinstance(obj, dict):
        return {k: _clean_for_serialize(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_clean_for_serialize(item) for item in obj]
    return obj


def serialize_frontmatter(data: dict, body: str) -> str:
    """Serialize a dict + body back to frontmatter-delimited markdown."""
    cleaned = _clean_for_serialize(data)
    yaml_str = yaml.dump(
        cleaned,
        Dumper=_FrontmatterDumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    return f"---\n{yaml_str}---\n{body}"
