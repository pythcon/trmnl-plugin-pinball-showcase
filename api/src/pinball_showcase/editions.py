"""Edition naming: OPDB's terse suffixes, cleaned up.

OPDB labels editions with abbreviations ("Harry Potter (CE)", "Halloween (SE)",
"Elton John (PE)") whose meaning depends on the maker, and occasionally bakes one into
a game's own name ("The Texas Chainsaw Massacre (SE)"). Here they become:

- a long form for the website and the full-screen layout: "Collector's Edition";
- a short form for small layouts: "CE", "Blood Sucker" (trailing "Edition" dropped).

Abbreviations, as used across OPDB (checked against every suffix in the export):
CE = Collector's Edition (JJP, Spooky, American, Pinball Brothers, Multimorphic),
LE = Limited Edition, PE = Platinum Edition (JJP's Elton John), EM / SS = electro-mechanical /
solid-state variants, AAB = add-a-ball, 1P/2P/4P = player-count variants.

SE is ambiguous: Spooky's SE is its entry model (Standard Edition; OPDB flags every one
"Pro edition"), while Chicago Gaming's Pulp Fiction SE is its upgraded model (Special
Edition; flagged "Premium edition"). Real special editions are otherwise spelled out
("Sonic the Hedgehog (Special)"). Callers pass the machine's flags to decide.
"""

from __future__ import annotations

import re

STANDARD_LONG = "Standard Edition"
STANDARD_SHORT = "Standard"

_ABBREVIATIONS = [
    (re.compile(r"\bCE\b"), "Collector's Edition"),
    (re.compile(r"\bLE\b"), "Limited Edition"),
    (re.compile(r"\bPE\b"), "Platinum Edition"),
    (re.compile(r"\bEM\b"), "Electro-mechanical"),
    (re.compile(r"\bSS\b"), "Solid State"),
    (re.compile(r"\bAAB\b"), "Add-A-Ball"),
    (re.compile(r"\b(\d)P\b"), r"\1 Player"),
]
# Words that make a parenthesised suffix an edition rather than, say, a maker
# ("Centaur (Inder)" keeps its suffix).
_EDITION_WORDS = re.compile(
    r"\b(edition|pro|premium|limited|vault|home|remake|anniversary|signature|special"
    r"|collector'?s?|platinum|deluxe|classic)\b",
    re.IGNORECASE,
)


def expand(text: str, flags: tuple[str, ...] = ()) -> str:
    """Long form: "Premium/LE" -> "Premium / Limited Edition", "CE" -> "Collector's Edition".

    ``flags`` are the machine's OPDB edition flags, used to read "SE" (see above).
    """
    out = text.strip()
    se = "Special Edition" if "Premium edition" in flags else STANDARD_LONG
    out = re.sub(r"\bSE\b", se, out)
    for pattern, replacement in _ABBREVIATIONS:
        out = pattern.sub(replacement, out)
    return re.sub(r"\s*/\s*", " / ", out)


def shorten(text: str) -> str:
    """Short form: OPDB's own wording, minus a trailing "Edition" ("Blood Sucker")."""
    trimmed = re.sub(r"\s+edition$", "", text.strip(), flags=re.IGNORECASE)
    return trimmed or text.strip()


def is_edition_suffix(text: str) -> bool:
    """Whether "(text)" at the end of a name names an edition."""
    return expand(text) != text.strip() or bool(_EDITION_WORDS.search(text))
