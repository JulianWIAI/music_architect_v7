"""
GenreFusionEngine

Blends musical DNA from multiple genres to create hybrid styles.

Provides fused pattern sequences, BPM values, and chord-transition matrices
by weighted-sampling from each contributing genre's learned patterns.
"""

import random
from collections import defaultdict
from typing import List, Dict, Tuple

from src.arrangement.fusion_config import FusionConfig
from src.arrangement.fusion_presets import FUSION_PRESETS


class GenreFusionEngine:
    """
    Blends patterns from multiple genres to produce hybrid arrangements.

    Requires a LearnedPatternGenerator for rhythm patterns, and optionally a
    LearnedBassGenerator and LearnedLeadGenerator for those instrument families.
    """

    def __init__(self, pattern_generator, bass_generator=None, lead_generator=None):
        self.pattern_generator = pattern_generator
        self.bass_generator = bass_generator
        self.lead_generator = lead_generator

    # ─── PATTERN FUSION ───────────────────────────────────────────────────────

    def get_fused_patterns(
        self,
        fusion_config: FusionConfig,
        instrument: str,
        num_bars: int,
        complexity: float = 0.5,
    ) -> List[List[int]]:
        """Return a bar sequence by weighted selection across contributing genres."""
        genres, weights = fusion_config.genres, fusion_config.weights
        genre_patterns = {
            g: self.pattern_generator.get_patterns_for_genre(g, instrument)
            for g in genres
        }
        genre_patterns = {g: p for g, p in genre_patterns.items() if p}

        if not genre_patterns:
            return [[0] * 16 for _ in range(num_bars)]

        sequence = []
        for _ in range(num_bars):
            r = random.random()
            cumulative = 0.0
            chosen_genre = genres[0]
            for genre, weight in zip(genres, weights):
                cumulative += weight
                if r <= cumulative:
                    chosen_genre = genre
                    break

            # Cross-pollinate when complexity is high
            if complexity > 0.5 and random.random() < complexity * 0.3:
                others = [g for g in genre_patterns if g != chosen_genre]
                if others:
                    chosen_genre = random.choice(others)

            patterns = genre_patterns.get(chosen_genre) or sum(genre_patterns.values(), [])
            sequence.append(random.choice(patterns))

        return sequence

    # ─── BPM FUSION ───────────────────────────────────────────────────────────

    def get_fused_bpm(
        self,
        fusion_config: FusionConfig,
        genre_bpm_ranges: Dict[str, Tuple[int, int]],
    ) -> float:
        """Calculate a BPM that blends the tempo ranges of the contributing genres."""
        genres, weights = fusion_config.genres, fusion_config.weights

        # Check for exact preset match to use its BPM range
        for preset in FUSION_PRESETS.values():
            if preset['genres'] == genres:
                return random.uniform(*preset.get('bpm_range', (100, 140)))

        total_bpm = total_weight = 0.0
        for genre, weight in zip(genres, weights):
            if genre in genre_bpm_ranges:
                lo, hi = genre_bpm_ranges[genre]
                total_bpm += (lo + hi) / 2 * weight
                total_weight += weight

        if total_weight > 0:
            return total_bpm / total_weight + random.uniform(-10, 10)
        return 120.0

    # ─── CHORD MATRIX FUSION ──────────────────────────────────────────────────

    def get_fused_chord_matrix(
        self,
        fusion_config: FusionConfig,
        genre_matrices: Dict[str, Dict],
    ) -> Dict:
        """Blend chord-transition matrices from multiple genres by weighted average."""
        fused: defaultdict = defaultdict(lambda: defaultdict(float))

        for genre, weight in zip(fusion_config.genres, fusion_config.weights):
            if genre not in genre_matrices:
                continue
            for chord, transitions in genre_matrices[genre].items():
                for next_chord, prob in transitions.items():
                    fused[chord][next_chord] += prob * weight

        result = {}
        for chord, transitions in fused.items():
            total = sum(transitions.values())
            if total > 0:
                result[chord] = {nc: p / total for nc, p in transitions.items()}
        return result
