"""Group near-duplicate theme labels ("login fails", "can't log in") into canonical themes."""

from __future__ import annotations

from collections import Counter

from ..providers import LLMError, LLMProvider, Usage

MAX_LABELS = 300  # long-tail labels beyond this keep their own name
MAX_THEMES = 25

GROUP_SCHEMA = {
    "type": "object",
    "properties": {
        "themes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "members": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["name", "members"],
            },
        }
    },
    "required": ["themes"],
}

_SYSTEM = """You organise app review themes for a product design team.
Group the numbered labels into at most {max_themes} themes. Merge labels that describe the same
underlying problem or praise; keep genuinely different issues apart. Name each theme with a clear
2-5 word lowercase {language} label a designer would put on a sticky note. Every label number must
appear in exactly one theme."""


async def build_theme_map(
    provider: LLMProvider, label_counts: Counter, *, output_language: str = "English"
) -> tuple[dict[str, str], Usage, str | None]:
    """Return (raw label -> theme, usage, warning). Falls back to identity mapping if the model call fails."""
    identity = {label: label for label in label_counts}
    if len(label_counts) < 2:
        return identity, Usage(), None

    labels = [label for label, _ in label_counts.most_common(MAX_LABELS)]
    numbered = "\n".join(f"{i}. {label} ({label_counts[label]})" for i, label in enumerate(labels))
    system = _SYSTEM.format(max_themes=MAX_THEMES, language=output_language)
    try:
        data, usage = await provider.complete_json(
            system=system, prompt=f"Labels (with mention counts):\n{numbered}", schema=GROUP_SCHEMA
        )
    except LLMError as exc:
        if exc.fatal:
            raise
        return identity, Usage(), f"Theme grouping skipped: {exc}"

    mapping = dict(identity)
    for theme in data.get("themes") or []:
        if not isinstance(theme, dict):
            continue
        name = " ".join(str(theme.get("name") or "").lower().split())[:60]
        if not name:
            continue
        for member in theme.get("members") or []:
            try:
                index = int(member)
            except (TypeError, ValueError):
                continue
            if 0 <= index < len(labels):
                mapping[labels[index]] = name
    return mapping, usage, None
