"""
corpus_matcher.py

Computes a corpus-match percentage: how well the current composition's
musical parameters align with the statistical distribution of real songs
in the seed database for its genre.

Scoring dimensions (each 0-100, then weighted average):

  BPM proximity    40 %  — Gaussian similarity: σ = half the genre's BPM range width.
                            Score 100 when BPM == genre median, 50 at ±σ.
  Scale family     30 %  — 100 if the key mode is one of the genre's valid scales, else 0.
  Chord quality    20 %  — fraction of the composition's chord qualities that appear
                            frequently in the genre's seed corpus.
  Syncopation      10 %  — 100 if syncopation level is within the genre's typical range,
                            partial credit for proximity.

Usage
-----
    from src.composition.corpus_matcher import CorpusMatcher
    cm = CorpusMatcher(seeds_dir='seeds')
    result = cm.match(genre='trap', bpm=145, key='A minor', chord_qualities=['min7'])
    # result: {'score': 87, 'bpm_match': 95, 'scale_match': 100, ...}
"""

import json
import math
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Genre BPM ranges for σ calculation (lo, hi).  Matches bpm_range in the JSON
# production guide; kept here so the matcher works without loading those files.
_GENRE_BPM_RANGE: Dict[str, Tuple[int, int]] = {
    'trap':      (130, 165),
    'hiphop':    (70,  100),
    'pop':       (90,  130),
    'edm':       (125, 150),
    'house':     (120, 130),
    'jpop':      (100, 140),
    'techno':    (130, 150),
    'dnb':       (160, 180),
    'phonk':     (130, 160),
    'cinematic': (60,  120),
    'classical': (40,  180),
}

# Genre valid scale families — mirrors genre JSON valid_scales fields.
_GENRE_SCALES: Dict[str, List[str]] = {
    'trap':      ['natural_minor', 'phrygian', 'pentatonic_minor', 'minor'],
    'hiphop':    ['natural_minor', 'pentatonic_minor', 'blues', 'minor'],
    'pop':       ['major', 'natural_minor', 'mixolydian', 'dorian'],
    'edm':       ['major', 'minor', 'natural_minor'],
    'house':     ['major', 'minor', 'mixolydian'],
    'jpop':      ['major', 'dorian', 'natural_minor'],
    'techno':    ['phrygian', 'natural_minor', 'minor'],
    'dnb':       ['natural_minor', 'phrygian', 'minor'],
    'phonk':     ['natural_minor', 'phrygian', 'minor'],
    'cinematic': ['natural_minor', 'major', 'dorian', 'phrygian'],
    'classical': ['major', 'natural_minor', 'dorian', 'minor'],
}

# Typical syncopation range [lo, hi] for each genre (from seed analysis).
_GENRE_SYNCOPATION: Dict[str, Tuple[float, float]] = {
    'trap':      (0.30, 0.65),
    'hiphop':    (0.25, 0.55),
    'pop':       (0.10, 0.35),
    'edm':       (0.05, 0.25),
    'house':     (0.05, 0.20),
    'jpop':      (0.10, 0.35),
    'techno':    (0.05, 0.20),
    'dnb':       (0.20, 0.50),
    'phonk':     (0.25, 0.55),
    'cinematic': (0.10, 0.40),
    'classical': (0.05, 0.30),
}

# Chord quality frequency tables built from seed corpus analysis.
# Keys are chord quality strings; values are relative frequency (0-1).
_GENRE_CHORD_FREQ: Dict[str, Dict[str, float]] = {
    'trap': {
        'min7': 0.42, 'maj7': 0.25, 'min': 0.12, 'dom7': 0.08,
        'sus2': 0.05, 'sus4': 0.04, 'dim': 0.03, 'aug': 0.01,
    },
    'hiphop': {
        'min7': 0.35, 'maj7': 0.22, 'dom7': 0.15, 'min': 0.12,
        'maj': 0.08, 'sus2': 0.05, 'dim': 0.02, 'aug': 0.01,
    },
    'pop': {
        'maj': 0.30, 'min': 0.25, 'maj7': 0.18, 'dom7': 0.12,
        'min7': 0.08, 'sus2': 0.04, 'sus4': 0.02, 'aug': 0.01,
    },
    'edm': {
        'maj': 0.32, 'min': 0.28, 'min7': 0.15, 'sus4': 0.10,
        'maj7': 0.08, 'dom7': 0.05, 'sus2': 0.02,
    },
    'house': {
        'maj': 0.30, 'min': 0.25, 'dom7': 0.18, 'maj7': 0.12,
        'min7': 0.10, 'sus4': 0.05,
    },
    'jpop': {
        'maj': 0.28, 'maj7': 0.22, 'min': 0.18, 'dom7': 0.12,
        'min7': 0.10, 'aug': 0.05, 'sus2': 0.03, 'sus4': 0.02,
    },
    'techno': {
        'min': 0.40, 'maj': 0.20, 'min7': 0.18, 'dom7': 0.12,
        'sus4': 0.06, 'dim': 0.04,
    },
    'dnb': {
        'min': 0.35, 'min7': 0.28, 'dom7': 0.15, 'dim': 0.10,
        'maj': 0.08, 'sus4': 0.04,
    },
    'phonk': {
        'min': 0.38, 'min7': 0.25, 'dom7': 0.15, 'dim': 0.12,
        'maj': 0.06, 'sus2': 0.04,
    },
    'cinematic': {
        'maj': 0.22, 'min': 0.20, 'maj7': 0.18, 'min7': 0.15,
        'dom7': 0.10, 'sus2': 0.06, 'aug': 0.05, 'dim': 0.04,
    },
    'classical': {
        'maj': 0.30, 'min': 0.25, 'dom7': 0.18, 'dim': 0.12,
        'aug': 0.06, 'maj7': 0.05, 'sus4': 0.04,
    },
}


class CorpusMatcher:
    """
    Scores a composition against the seed corpus for its genre.

    Seeds are loaded lazily on first match() call and cached in memory.
    If no seed file exists for the genre, the scorer uses only the
    statistical tables compiled from the full corpus.
    """

    def __init__(self, seeds_dir: Optional[str] = None) -> None:
        # Resolve seeds_dir relative to the project root when not supplied.
        if seeds_dir is None:
            seeds_dir = str(Path(__file__).parent.parent.parent / 'seeds')
        self._seeds_dir = seeds_dir
        self._cache: Dict[str, List[dict]] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def match(
        self,
        genre: str,
        bpm: float,
        key: str = '',
        chord_qualities: Optional[List[str]] = None,
        syncopation: Optional[float] = None,
    ) -> Dict[str, object]:
        """
        Compute corpus match for the given composition parameters.

        Returns a dict:
          {
            'score':        int,    # 0-100 overall corpus-match %
            'bpm_match':    int,    # 0-100 BPM proximity sub-score
            'scale_match':  int,    # 0 or 100 scale-family sub-score
            'chord_match':  int,    # 0-100 chord-quality sub-score
            'synco_match':  int,    # 0-100 syncopation sub-score
            'seed_count':   int,    # number of seeds available for genre
            'bpm_range':    tuple,  # (lo, hi) typical BPM for genre
          }
        """
        seeds = self._load_seeds(genre)
        seed_count = len(seeds)

        bpm_score    = self._score_bpm(genre, bpm, seeds)
        scale_score  = self._score_scale(genre, key)
        chord_score  = self._score_chords(genre, chord_qualities or [], seeds)
        synco_score  = self._score_syncopation(genre, syncopation, seeds)

        overall = int(round(
            bpm_score   * 0.40 +
            scale_score * 0.30 +
            chord_score * 0.20 +
            synco_score * 0.10
        ))

        return {
            'score':       overall,
            'bpm_match':   int(round(bpm_score)),
            'scale_match': int(round(scale_score)),
            'chord_match': int(round(chord_score)),
            'synco_match': int(round(synco_score)),
            'seed_count':  seed_count,
            'bpm_range':   _GENRE_BPM_RANGE.get(genre, (60, 200)),
        }

    # ── Seed Loading ──────────────────────────────────────────────────────────

    def _load_seeds(self, genre: str) -> List[dict]:
        if genre in self._cache:
            return self._cache[genre]
        path = os.path.join(self._seeds_dir, f'seeds_{genre}.json')
        if os.path.exists(path):
            try:
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
                self._cache[genre] = data if isinstance(data, list) else []
            except Exception:
                self._cache[genre] = []
        else:
            self._cache[genre] = []
        return self._cache[genre]

    # ── Scoring Dimensions ────────────────────────────────────────────────────

    def _score_bpm(self, genre: str, bpm: float, seeds: List[dict]) -> float:
        lo, hi = _GENRE_BPM_RANGE.get(genre, (60, 200))

        # Score against real seed distribution if seeds are available.
        if seeds:
            seed_bpms = [s.get('dna', {}).get('bpm', 0) for s in seeds
                         if s.get('dna', {}).get('bpm')]
            if seed_bpms:
                mean_bpm = sum(seed_bpms) / len(seed_bpms)
                variance = sum((b - mean_bpm) ** 2 for b in seed_bpms) / len(seed_bpms)
                sigma = math.sqrt(variance) if variance > 0 else (hi - lo) / 4
                score = 100 * math.exp(-0.5 * ((bpm - mean_bpm) / sigma) ** 2)
                return min(100.0, score)

        # Fallback: linear score based on the genre BPM range.
        mid = (lo + hi) / 2
        half_range = (hi - lo) / 2
        if half_range == 0:
            return 100.0
        dist = abs(bpm - mid) / half_range
        # Gaussian with σ = half the range → score = 100 at centre, ~61 at edge.
        return min(100.0, 100 * math.exp(-0.5 * dist ** 2))

    def _score_scale(self, genre: str, key: str) -> float:
        valid = _GENRE_SCALES.get(genre, [])
        if not valid or not key:
            return 50.0  # neutral when data is unavailable
        key_lower = key.lower()
        # Check if any valid scale name appears in the key string.
        # e.g. "A minor" → "minor" matches "natural_minor", "minor"
        for scale in valid:
            scale_parts = scale.replace('_', ' ').split()
            if any(p in key_lower for p in scale_parts):
                return 100.0
        return 0.0

    def _score_chords(
        self, genre: str, chord_qualities: List[str], seeds: List[dict]
    ) -> float:
        if not chord_qualities:
            return 50.0  # neutral
        freq_table = _GENRE_CHORD_FREQ.get(genre, {})
        if not freq_table:
            return 50.0

        # Build corpus frequency from seeds if available.
        if seeds:
            counts: Dict[str, int] = {}
            total = 0
            for s in seeds:
                for q in s.get('chord_qualities_used', []):
                    counts[q] = counts.get(q, 0) + 1
                    total += 1
            if total > 0:
                freq_table = {k: v / total for k, v in counts.items()}

        scores = []
        for q in chord_qualities:
            freq = freq_table.get(q, 0.0)
            # Scale 0-1 frequency to 0-100 with √ to reward any positive presence.
            scores.append(min(100.0, math.sqrt(freq) * 100 * 3.2))
        return sum(scores) / len(scores)

    def _score_syncopation(
        self, genre: str, syncopation: Optional[float], seeds: List[dict]
    ) -> float:
        if syncopation is None:
            return 50.0  # neutral when not provided
        lo, hi = _GENRE_SYNCOPATION.get(genre, (0.05, 0.50))
        if lo <= syncopation <= hi:
            return 100.0
        dist = min(abs(syncopation - lo), abs(syncopation - hi))
        range_width = hi - lo if hi > lo else 0.1
        # Decay score beyond the typical range.
        return max(0.0, 100.0 - (dist / range_width) * 100)
