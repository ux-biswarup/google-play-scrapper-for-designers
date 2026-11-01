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
        },
        "discard": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["themes", "discard"],
}

_SYSTEM = """You organise app review themes for a product design team.
Group the numbered labels into at most {max_themes} themes. Merge labels about the same part of the
product; keep genuinely different subjects apart. Name each theme with a clear 2-5 word lowercase
{language} label naming the subject (e.g. "account bans", "ads frequency", "login after update"), never
a feeling: the same theme can be praised by some reviews and criticised by others.
Put labels that only express a feeling or are too vague to act on ("bad experience", "negative reviews",
"positive experience", "good game", "app quality") in "discard" instead of a theme.
Every label number must appear exactly once: in one theme or in discard."""


_CATCH_ALL = {"discard", "discarded", "other", "others", "misc", "miscellaneous", "general", "vague", "none"}


async def build_theme_map(
    provider: LLMProvider, label_counts: Counter, *, output_language: str = "English"
) -> tuple[dict[str, str], Usage, str | None]:
    """Return (raw label -> theme, usage, warning). An empty theme means the label was discarded as too vague.
    Falls back to the identity mapping if the model call fails."""
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
    for member in data.get("discard") or []:
        try:
            index = int(member)
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(labels):
            mapping[labels[index]] = ""  # too vague to act on: hidden from themes
    for theme in data.get("themes") or []:
        if not isinstance(theme, dict):
            continue
        name = " ".join(str(theme.get("name") or "").lower().split())[:60]
        if not name:
            continue
        if name in _CATCH_ALL:  # models sometimes put vague labels in a theme called "discard" or "other"
            name = ""
        for member in theme.get("members") or []:
            try:
                index = int(member)
            except (TypeError, ValueError):
                continue
            if 0 <= index < len(labels):
                mapping[labels[index]] = name
    return mapping, usage, None
