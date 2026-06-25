"""
Scores and ranks seeds against an incoming AnalysisJSON document.

Scoring weights (standard genres):
  BPM proximity   35 %
  Rhythm match    40 %
  Harmonic match  25 %

EDM / HOUSE additionally blend in a 4-on-the-floor kick alignment score
(30 % of the final composite) to surface seeds whose kick DNA matches the
4-on-the-floor template.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from src.ingestion.analysis_schema import AnalysisJSON

SCORE_WEIGHTS = {"bpm": 0.35, "rhythm": 0.40, "harmonic": 0.25}

# Genres handled natively by the composition engine
_SUPPORTED_GENRES = {
    "pop", "hiphop", "trap", "cinematic", "classical",
    "techno", "jpop", "phonk", "edm", "house",
}

# Human / DAW tag → canonical genre
_GENRE_ALIASES: Dict[str, str] = {
    "hip-hop": "hiphop",
    "hip hop": "hiphop",
    "r&b": "hiphop",
    "rnb": "hiphop",
    "electronic": "edm",
    "electronic dance music": "edm",
    "progressive": "edm",
    "electro": "edm",
    "drum and bass": "techno",
    "dnb": "techno",
    "jazz": "classical",
    "orchestral": "cinematic",
    "ambient": "cinematic",
    "lofi": "hiphop",
    "lo-fi": "hiphop",
    "j-pop": "jpop",
    "deep house": "house",
    "tech house": "house",
    "progressive house": "house",
    "tropical house": "house",
    "future house": "house",
    "minimal house": "house",
}

# When a genre has no matching seeds in the library, fall back to this label
# for the seed-filter step.  Scoring still uses the original genre's 4-on-floor
# bonus where applicable.
_GENRE_SEED_FALLBACK: Dict[str, str] = {
    "edm":   "techno",
    "house": "techno",
}

# Genres that receive a 4-on-the-floor kick alignment bonus
_FOUR_ON_FLOOR_GENRES = frozenset({"edm", "house"})
_FOUR_ON_FLOOR_PATTERN = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0,
                           1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
# Weight of the 4-on-floor bonus blended into the composite score
_FOUR_ON_FLOOR_BLEND = 0.30


def resolve_genre(analysis: AnalysisJSON) -> str:
    """
    Return the canonical genre string to use for seed filtering.

    Priority: user_genre_override > assigned_genre_cluster > alias map > 'pop'.
    EDM and HOUSE are now resolved as first-class genres instead of being
    collapsed into 'techno'.
    """
    raw = (
        analysis.genre_metadata.user_genre_override
        or analysis.genre_metadata.assigned_genre_cluster
    ).lower().strip()
    if raw in _SUPPORTED_GENRES:
        return raw
    aliased = _GENRE_ALIASES.get(raw)
    if aliased:
        return aliased
    return "pop"


def _pattern_density(patterns: List[List[int]]) -> List[float]:
    """
    Average a list of 16-step binary patterns into a single density vector.
    Seeds store multiple patterns per instrument; we reduce to one vector.
    """
    if not patterns:
        return [0.0] * 16
    length = max(len(p) for p in patterns)
    totals = [0.0] * length
    for pat in patterns:
        for i, v in enumerate(pat):
            if i < length:
                totals[i] += v
    n = len(patterns)
    return [t / n for t in totals]


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity in [0, 1]; returns 0 for zero vectors."""
    length = min(len(a), len(b))
    if length == 0:
        return 0.0
    dot = sum(a[i] * b[i] for i in range(length))
    mag_a = math.sqrt(sum(x * x for x in a[:length]))
    mag_b = math.sqrt(sum(x * x for x in b[:length]))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def score_bpm(seed: Dict[str, Any], target_bpm: float) -> float:
    """Gaussian decay: score 1.0 at 0 BPM difference, ~0.37 at 20 BPM off."""
    seed_bpm = float(
        seed.get("instrument_patterns", {}).get("bpm")
        or seed.get("dna", {}).get("bpm", 120)
    )
    diff = abs(seed_bpm - target_bpm)
    return math.exp(-(diff ** 2) / (2 * 20 ** 2))


def score_rhythm(seed: Dict[str, Any], analysis: AnalysisJSON) -> float:
    """
    Weighted cosine similarity of kick (40%), snare (35%), hi-hat (25%)
    patterns between seed and incoming analysis.
    """
    inst_patterns = seed.get("instrument_patterns", {}).get("drum_patterns", {})
    rh = analysis.rhythm

    pairs = [
        (_pattern_density(inst_patterns.get("kick",  [])), list(map(float, rh.kick_pattern))),
        (_pattern_density(inst_patterns.get("snare", [])), list(map(float, rh.snare_pattern))),
        (_pattern_density(inst_patterns.get("hihat", [])), list(map(float, rh.hihat_pattern))),
    ]
    weights = [0.40, 0.35, 0.25]
    return sum(w * _cosine_similarity(a, b) for w, (a, b) in zip(weights, pairs))


def score_harmonic(seed: Dict[str, Any], analysis: AnalysisJSON) -> float:
    """
    Blend of scale-type match (30%), root-note match (20%), and
    chord-quality Jaccard coefficient (50%).
    """
    ha = analysis.harmony
    seed_key: str = seed.get("dna", {}).get("key", "") or ""
    parts = seed_key.lower().split()
    seed_root  = parts[0] if parts else ""
    seed_scale = parts[1] if len(parts) > 1 else ""

    scale_match = 1.0 if seed_scale == ha.scale_type.lower() else 0.0
    root_match  = 1.0 if seed_root  == ha.root_note.lower()  else 0.0

    seed_qualities: set = set(seed.get("chord_qualities_used", []))
    analysis_qualities: set = {_quality_from_chord(c) for c in ha.chord_sequence}
    if seed_qualities or analysis_qualities:
        jaccard = len(seed_qualities & analysis_qualities) / len(seed_qualities | analysis_qualities)
    else:
        jaccard = 0.0

    return 0.3 * scale_match + 0.2 * root_match + 0.5 * jaccard


def _quality_from_chord(chord: str) -> str:
    """Extract the quality suffix from a chord string like 'Amin7' → 'min7'."""
    if not chord:
        return ""
    i = 1
    if len(chord) > 1 and chord[1] in "#b":
        i = 2
    return chord[i:].lower() or "major"


def _four_on_floor_score(seed: Dict[str, Any]) -> float:
    """
    Cosine similarity of the seed's averaged kick pattern against the
    ideal 4-on-the-floor template [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0].

    Returns 1.0 for a perfect 4-on-the-floor kick, 0.0 for silence.
    """
    kick_patterns = (
        seed.get("instrument_patterns", {})
            .get("drum_patterns", {})
            .get("kick", [])
    )
    density = _pattern_density(kick_patterns)
    return _cosine_similarity(density, _FOUR_ON_FLOOR_PATTERN)


def score_seed(
    seed: Dict[str, Any],
    analysis: AnalysisJSON,
    genre: str = "",
) -> float:
    """
    Composite score in [0, 1].

    For EDM and HOUSE an additional 4-on-the-floor kick alignment term is
    blended in, replacing 30 % of the base score with the kick-pattern score.
    This surfaces seeds whose rhythmic DNA already reflects the high-BPM,
    every-quarter-note kick characteristic of those genres.
    """
    w = SCORE_WEIGHTS
    base = (
        w["bpm"]     * score_bpm(seed, analysis.rhythm.bpm)
        + w["rhythm"]   * score_rhythm(seed, analysis)
        + w["harmonic"] * score_harmonic(seed, analysis)
    )
    if genre in _FOUR_ON_FLOOR_GENRES:
        fof = _four_on_floor_score(seed)
        return (1.0 - _FOUR_ON_FLOOR_BLEND) * base + _FOUR_ON_FLOOR_BLEND * fof
    return base


def select_top_seeds(
    seeds: List[Dict[str, Any]],
    analysis: AnalysisJSON,
    genre: str,
    top_n: int = 20,
) -> List[Dict[str, Any]]:
    """
    Filter seeds to *genre* (using _GENRE_SEED_FALLBACK when the library
    has no seeds labelled with that genre), score each against *analysis*,
    and return the top *top_n* by descending composite score.

    For EDM and HOUSE, the composite score includes the 4-on-the-floor bonus
    so that seeds with matching kick DNA rank highest.
    """
    seed_label = _GENRE_SEED_FALLBACK.get(genre, genre)
    genre_seeds = [s for s in seeds if s.get("genre", "").lower() == seed_label]
    if not genre_seeds:
        genre_seeds = seeds

    scored = [(score_seed(s, analysis, genre=genre), s) for s in genre_seeds]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:top_n]]
