"""QWERTY adjacency + common-word/bigram tables for the typing model."""

from __future__ import annotations

# Physically adjacent keys on a QWERTY layout (used for realistic typos).
QWERTY_NEIGHBORS: dict[str, str] = {
    "q": "wa", "w": "qeas", "e": "wrsd", "r": "etdf", "t": "ryfg",
    "y": "tugh", "u": "yihj", "i": "uojk", "o": "ipkl", "p": "ol",
    "a": "qwsz", "s": "weadzx", "d": "ersfcx", "f": "rtdgvc", "g": "tyfhbv",
    "h": "yugjnb", "j": "uihknm", "k": "iojlm", "l": "opk",
    "z": "asx", "x": "zsdc", "c": "xdfv", "v": "cfgb", "b": "vghn",
    "n": "bhjm", "m": "njk",
}

COMMON_WORDS = frozenset({
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i", "it", "for",
    "not", "on", "with", "he", "as", "you", "do", "at", "this", "but", "his",
    "by", "from", "they", "we", "say", "her", "she", "or", "an", "will", "my",
    "one", "all", "would", "there", "their", "what", "so", "is", "are", "was",
    "if", "out", "up", "about", "who", "get", "which", "go", "me", "when",
})

COMMON_BIGRAMS = frozenset({
    "th", "he", "in", "er", "an", "re", "on", "at", "en", "nd", "ti", "es",
    "or", "te", "of", "ed", "is", "it", "al", "ar", "st", "to", "nt", "ng",
    "se", "ha", "as", "ou", "io", "le", "ve", "co", "me", "de", "hi", "ri",
    "ro", "ic", "ne", "ea", "ra", "ce", "li", "ch", "ll", "be", "ma", "si",
})


def neighbor(ch: str, rng) -> str:
    """A physically adjacent key to ``ch``, preserving case. Falls back to ``ch``."""
    options = QWERTY_NEIGHBORS.get(ch.lower())
    if not options:
        return ch
    pick = rng.choice(options)
    return pick.upper() if ch.isupper() else pick
