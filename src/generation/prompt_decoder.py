"""
SemanticCipher — keyword-based natural language → CompositionConfig decoder.

V1: zero external dependencies, purely keyword/phrase driven.

Usage
-----
cipher = SemanticCipher()
params = cipher.decode_prompt("fast dark trap beat with a huge drop")
# DecodedParams(genre='trap', bpm=150.0, scale_hint='minor', tension_multiplier=1.5, ...)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
#  Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DecodedParams:
    """Parameters extracted from a natural-language prompt."""
    genre:              Optional[str]   = None   # canonical genre string
    bpm:                Optional[float] = None   # target BPM
    scale_hint:         Optional[str]   = None   # 'major', 'minor', 'phrygian', …
    tension_multiplier: Optional[float] = None   # 0.0 – 1.5+
    complexity:         Optional[int]   = None   # 1 – 10
    matched_keywords:   List[str]       = field(default_factory=list)

    def is_empty(self) -> bool:
        return all(v is None for v in (
            self.genre, self.bpm, self.scale_hint, self.tension_multiplier, self.complexity
        ))

    def summary(self) -> str:
        """One-liner for UI display."""
        parts = []
        if self.genre:
            parts.append(f"genre={self.genre}")
        if self.bpm is not None:
            parts.append(f"bpm={self.bpm:.0f}")
        if self.scale_hint:
            parts.append(f"scale={self.scale_hint}")
        if self.tension_multiplier is not None:
            parts.append(f"tension={self.tension_multiplier:.1f}")
        if self.complexity is not None:
            parts.append(f"complexity={self.complexity}")
        if not parts:
            return "No parameters detected"
        kws = f"  [{', '.join(self.matched_keywords[:6])}]" if self.matched_keywords else ""
        return "  |  ".join(parts) + kws


# ─────────────────────────────────────────────────────────────────────────────
#  Keyword / phrase tables
#  Longer phrases must appear BEFORE single-word equivalents so that
#  "hip hop" is matched as one entry, not as two unrelated words.
# ─────────────────────────────────────────────────────────────────────────────

_GENRE_PHRASES: List[Tuple[str, str]] = [
    # compound phrases first
    ("drum and bass",         "dnb"),     ("d&b",              "dnb"),
    ("dnb",                   "dnb"),
    ("hip hop",               "hiphop"),  ("hip-hop",          "hiphop"),
    ("deep house",            "house"),   ("tech house",       "house"),
    ("progressive house",     "house"),   ("future house",     "house"),
    ("tropical house",        "house"),   ("minimal house",    "house"),
    ("electronic dance music","edm"),     ("electronic dance", "edm"),
    ("film score",            "cinematic"),("film music",      "cinematic"),
    ("j-pop",                 "jpop"),    ("j pop",            "jpop"),
    ("lo-fi",                 "hiphop"),  ("lo fi",            "hiphop"),
    ("lofi",                  "hiphop"),  ("chill hop",        "hiphop"),
    ("chillhop",              "hiphop"),
    ("r&b",                   "hiphop"),  ("rnb",              "hiphop"),
    # single-word genres
    ("trap",      "trap"),    ("phonk",     "phonk"),
    ("hiphop",    "hiphop"),  ("rap",       "hiphop"),
    ("techno",    "techno"),  ("industrial","techno"),
    ("house",     "house"),
    ("edm",       "edm"),     ("electronic","edm"),
    ("pop",       "pop"),
    ("cinematic", "cinematic"),("orchestral","cinematic"),
    ("epic",      "cinematic"),("soundtrack","cinematic"),
    ("classical", "classical"),("baroque",  "classical"),
    ("symphonic", "classical"),
    ("jpop",      "jpop"),    ("anime",     "jpop"),
    ("ambient",   "cinematic"),
    ("jazz",      "classical"),("soul",     "hiphop"),
    ("funk",      "hiphop"),  ("drift",     "phonk"),
]

_BPM_PHRASES: List[Tuple[str, Tuple[int, int]]] = [
    # compound phrases
    ("very fast",       (160, 185)), ("super fast",   (170, 195)),
    ("extremely fast",  (175, 200)), ("very slow",    (50,  75)),
    ("super slow",      (45,  70)),  ("extremely slow",(40,  65)),
    ("mid tempo",       (105, 125)), ("mid-tempo",    (105, 125)),
    ("laid back",       (70,  90)),  ("full speed",   (160, 180)),
    # single words
    ("fast",      (135, 160)), ("rapid",     (140, 165)), ("quick",    (130, 150)),
    ("upbeat",    (120, 145)), ("energetic", (130, 155)), ("driving",  (130, 148)),
    ("hyper",     (165, 185)), ("frantic",   (160, 180)), ("rushing",  (150, 170)),
    ("pounding",  (135, 155)), ("pumping",   (128, 145)),
    ("slow",      (70,  95)),  ("chill",     (75,  100)), ("mellow",   (70,  95)),
    ("relaxed",   (70,  90)),  ("dreamy",    (65,  85)),  ("sleepy",   (55,  75)),
    ("smooth",    (85,  110)), ("moderate",  (100, 120)), ("medium",   (100, 120)),
    ("bouncy",    (115, 135)), ("groovy",    (100, 120)), ("funky",    (100, 115)),
    ("lively",    (120, 140)), ("heavy",     (128, 150)), ("hard",     (128, 145)),
]

_SCALE_PHRASES: List[Tuple[str, str]] = [
    # explicit scale names (multi-word first)
    ("harmonic minor",    "harmonic_minor"),
    ("melodic minor",     "melodic_minor"),
    ("pentatonic minor",  "pentatonic_minor"),
    ("pentatonic major",  "pentatonic_major"),
    ("natural minor",     "minor"),
    # mood phrases
    ("dark and mysterious","phrygian"),
    ("pitch black",        "phrygian"),
    ("evil sounding",      "phrygian"),
    # dark / tense
    ("dark",        "minor"),    ("sad",         "minor"),
    ("evil",        "phrygian"), ("ominous",      "phrygian"),
    ("haunting",    "minor"),    ("melancholic",  "minor"),
    ("mournful",    "minor"),    ("gloomy",       "minor"),
    ("somber",      "minor"),    ("bleak",        "minor"),
    ("sinister",    "phrygian"), ("spooky",       "phrygian"),
    ("mysterious",  "phrygian"), ("threatening",  "phrygian"),
    ("tense",       "minor"),    ("aggressive",   "minor"),
    ("intense",     "minor"),    ("brutal",       "phrygian"),
    ("ominous",     "phrygian"),
    # bright / happy
    ("happy",       "major"),    ("bright",       "major"),
    ("joyful",      "major"),    ("uplifting",    "major"),
    ("cheerful",    "major"),    ("positive",     "major"),
    ("euphoric",    "major"),    ("victorious",   "major"),
    ("triumphant",  "major"),    ("celebratory",  "major"),
    ("gleeful",     "major"),    ("optimistic",   "major"),
    # dorian
    ("funky",       "dorian"),   ("groovy",       "dorian"),
    ("jazzy",       "dorian"),   ("jazz",         "dorian"),
    ("soulful",     "dorian"),
    # lydian
    ("dreamy",      "lydian"),   ("ethereal",     "lydian"),
    ("magical",     "lydian"),   ("floating",     "lydian"),
    ("heavenly",    "lydian"),   ("surreal",      "lydian"),
    # special
    ("oriental",    "japanese"), ("asian",        "japanese"),
    ("bluesy",      "blues"),
    # explicit scale names
    ("minor",       "minor"),    ("major",        "major"),
    ("phrygian",    "phrygian"), ("dorian",       "dorian"),
    ("mixolydian",  "mixolydian"),("lydian",      "lydian"),
    ("pentatonic",  "pentatonic_minor"),
]

_TENSION_PHRASES: List[Tuple[str, float]] = [
    # high-tension phrases
    ("huge drop",      1.5), ("massive drop",   1.5), ("big drop",     1.4),
    ("heavy drop",     1.4), ("epic drop",      1.5),
    ("full send",      1.5), ("all out",        1.5),
    ("high tension",   1.5), ("maximum energy", 1.5), ("full energy",  1.5),
    # high-tension single words
    ("aggressive",   1.3), ("intense",      1.4), ("powerful",    1.3),
    ("epic",         1.2), ("heavy",        1.2), ("hard",        1.2),
    ("brutal",       1.5), ("extreme",      1.5), ("climactic",   1.4),
    ("explosive",    1.4), ("thundering",   1.3), ("crushing",    1.4),
    ("massive",      1.3), ("punishing",    1.4), ("banging",     1.3),
    # low-tension phrases
    ("laid back",    0.25),
    # low-tension single words
    ("smooth",       0.3), ("ambient",      0.2), ("relaxed",     0.3),
    ("chill",        0.3), ("peaceful",     0.2), ("soft",        0.25),
    ("gentle",       0.2), ("calm",         0.2), ("mellow",      0.3),
    ("dreamy",       0.3), ("floating",     0.2), ("sparse",      0.2),
    ("minimal",      0.25),("delicate",     0.2), ("subtle",      0.25),
    ("quiet",        0.2), ("soothing",     0.2),
]

_COMPLEXITY_PHRASES: List[Tuple[str, int]] = [
    ("very complex",    10), ("super complex",  10), ("extremely complex", 10),
    ("very simple",      1), ("super simple",    1),
    ("complex",          8), ("intricate",       9), ("sophisticated",     8),
    ("elaborate",        9), ("advanced",        8), ("detailed",          8),
    ("dense",            8), ("layered",         7), ("rich",              7),
    ("full",             6),
    ("simple",           3), ("minimal",         2), ("sparse",            2),
    ("basic",            3), ("clean",           3), ("stripped",          2),
    ("moderate",         5), ("balanced",        5), ("standard",          5),
]

# Explicit BPM pattern: "at 130 bpm", "130bpm", "bpm: 128"
_BPM_EXPLICIT_RE = re.compile(
    r'(?:at\s+)?(\d{2,3})\s*bpm|bpm\s*:?\s*(\d{2,3})', re.IGNORECASE
)


# ─────────────────────────────────────────────────────────────────────────────
#  Matching helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lowercase; replace punctuation (except hyphens and &) with spaces."""
    text = text.lower()
    text = re.sub(r"[^\w\s\-&]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract(norm: str, phrase_map: List[Tuple]) -> List[Tuple]:
    """
    Scan *norm* for all entries in *phrase_map*, checking word boundaries.
    Longer phrases are matched before shorter ones to prevent partial overlaps.
    Returns list of (phrase, value) in order of occurrence.
    """
    # Sort by phrase length descending
    sorted_map = sorted(phrase_map, key=lambda x: len(x[0]), reverse=True)
    consumed: List[Tuple[int, int]] = []
    matches:  List[Tuple] = []

    for phrase, value in sorted_map:
        idx = 0
        while True:
            pos = norm.find(phrase, idx)
            if pos == -1:
                break
            end = pos + len(phrase)
            # Word-boundary check
            before_ok = pos == 0 or not norm[pos - 1].isalnum()
            after_ok  = end == len(norm) or not norm[end].isalnum()
            if before_ok and after_ok:
                overlap = any(cs <= pos < ce or pos <= cs < end
                              for cs, ce in consumed)
                if not overlap:
                    matches.append((phrase, value, pos))
                    consumed.append((pos, end))
            idx = end

    # Return in text order
    matches.sort(key=lambda x: x[2])
    return [(p, v) for p, v, _ in matches]


# ─────────────────────────────────────────────────────────────────────────────
#  SemanticCipher
# ─────────────────────────────────────────────────────────────────────────────

class SemanticCipher:
    """
    Translates a free-text track description into CompositionConfig overrides.
    Stateless; safe to share across threads.
    """

    def decode_prompt(self, text_input: str) -> DecodedParams:
        """
        Parse *text_input* and return a DecodedParams with any detected
        configuration overrides.  Fields that were not mentioned stay None.

        Parameters
        ----------
        text_input : e.g. "fast dark trap beat with a huge drop"

        Returns
        -------
        DecodedParams
        """
        if not text_input or not text_input.strip():
            return DecodedParams()

        norm     = _normalize(text_input)
        params   = DecodedParams()
        keywords: List[str] = []

        # ── Genre ────────────────────────────────────────────────────────────
        genre_matches = _extract(norm, _GENRE_PHRASES)
        if genre_matches:
            params.genre = genre_matches[-1][1]   # last explicit mention wins
            keywords.extend(p for p, _ in genre_matches)

        # ── BPM: explicit numeric value takes priority ────────────────────────
        explicit = _BPM_EXPLICIT_RE.search(norm)
        if explicit:
            raw = float(explicit.group(1) or explicit.group(2))
            if 40 <= raw <= 220:
                params.bpm = raw
                keywords.append(f"{int(raw)} bpm")
        else:
            bpm_matches = _extract(norm, _BPM_PHRASES)
            if bpm_matches:
                midpoints = [(lo + hi) / 2.0 for _, (lo, hi) in bpm_matches]
                params.bpm = round(sum(midpoints) / len(midpoints), 1)
                keywords.extend(p for p, _ in bpm_matches)

        # ── Scale / mood ──────────────────────────────────────────────────────
        scale_matches = _extract(norm, _SCALE_PHRASES)
        if scale_matches:
            params.scale_hint = scale_matches[-1][1]   # last mood wins
            keywords.extend(p for p, _ in scale_matches)

        # ── Tension ───────────────────────────────────────────────────────────
        tension_matches = _extract(norm, _TENSION_PHRASES)
        if tension_matches:
            params.tension_multiplier = max(v for _, v in tension_matches)
            keywords.extend(p for p, _ in tension_matches)

        # ── Complexity ────────────────────────────────────────────────────────
        complexity_matches = _extract(norm, _COMPLEXITY_PHRASES)
        if complexity_matches:
            vals = [v for _, v in complexity_matches]
            params.complexity = int(round(sum(vals) / len(vals)))
            keywords.extend(p for p, _ in complexity_matches)

        # Deduplicate keywords while preserving order
        seen: set = set()
        params.matched_keywords = [
            kw for kw in keywords if not (kw in seen or seen.add(kw))
        ]
        return params
