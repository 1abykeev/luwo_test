"""A safety net for one known model habit: with thinking switched off, the model sometimes writes a
short English "thinking aloud" paragraph in front of a correct answer in the user's language.
The prompt forbids it; this removes it when it still happens."""

import re

_CYRILLIC = re.compile(r"[А-Яа-яЁёӨөҮүҢң]")  # Russian and the extra Kyrgyz letters
_LATIN_WORD = re.compile(r"\b[A-Za-z]{3,}\b")
_CYRILLIC_WORD = re.compile(r"[А-Яа-яЁёӨөҮүҢң]{2,}")


def has_cyrillic(text: str) -> bool:
    return bool(_CYRILLIC.search(text))


def _is_foreign(paragraph: str) -> bool:
    """Looks like a sentence in English. A name or a class in Cyrillic inside it ("two students named
    Амир in 4А") must not save it, so we compare how many words of each script there are."""
    latin = len(_LATIN_WORD.findall(paragraph))
    cyrillic = len(_CYRILLIC_WORD.findall(paragraph))
    return latin >= 3 and latin > 2 * cyrillic


def drop_foreign_preamble(reply: str, user_text: str | None) -> str:
    """If the user wrote in Cyrillic, drop leading English-only paragraphs, but only when a paragraph
    in their language follows. A reply that is English from start to end is left alone: removing
    everything would leave the user with nothing."""
    if not user_text or not has_cyrillic(user_text):
        return reply
    paragraphs = [p for p in re.split(r"\n\s*\n", reply.strip()) if p.strip()]
    first_good = next((i for i, p in enumerate(paragraphs) if not _is_foreign(p)), None)
    if first_good is None or first_good == 0:
        return reply
    return "\n\n".join(paragraphs[first_good:])
