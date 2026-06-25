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


# Touch-typing finger assignment (QWERTY). Same-finger digraphs are slow; an
# alternating-hand digraph is fast. Keyed by lowercase character.
FINGER: dict[str, str] = {}
for _finger, _keys in {
    "L_pinky": "qaz1", "L_ring": "wsx2", "L_mid": "edc3", "L_index": "rfvtgb45",
    "R_index": "yhnujm67", "R_mid": "ik8", "R_ring": "ol9", "R_pinky": "p0",
}.items():
    for _k in _keys:
        FINGER[_k] = _finger

# Symbols that require the Shift key on a US layout (uppercase letters too).
SHIFTED_SYMBOLS = frozenset('~!@#$%^&*()_+{}|:"<>?')


def needs_shift(ch: str) -> bool:
    """True if producing ``ch`` requires holding Shift (US QWERTY)."""
    return ch.isupper() or ch in SHIFTED_SYMBOLS


def _hand(ch: str) -> str | None:
    f = FINGER.get(ch.lower())
    return f[0] if f else None  # "L" or "R"


def same_finger(a: str, b: str) -> bool:
    fa, fb = FINGER.get(a.lower()), FINGER.get(b.lower())
    return fa is not None and fa == fb


def alternating_hands(a: str, b: str) -> bool:
    ha, hb = _hand(a), _hand(b)
    return ha is not None and hb is not None and ha != hb
