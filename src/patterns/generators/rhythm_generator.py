"""
LearnedPatternGenerator

Loads drum/rhythm patterns from seed dicts and generates new bar sequences
using Markov-chain transitions. Also contains the high-level
generate_drums_from_learned_patterns() function used by the composition layer.
"""

import json
import random
from collections import defaultdict, Counter
from typing import List, Dict, Tuple


def _section_energy(section_type: str) -> float:
    """Energy coefficient for each structural section type (drums perspective)."""
    return {
        'intro': 0.5, 'verse': 0.7, 'pre_chorus': 0.8, 'chorus': 1.0,
        'drop': 1.0, 'bridge': 0.6, 'breakdown': 0.4, 'build': 0.8,
        'outro': 0.5, 'break': 0.2, 'climax': 1.0, 'pre-chorus': 0.8,
    }.get(section_type, 0.7)


class LearnedPatternGenerator:
    """
    Generates drum patterns from patterns learned across a seed collection.

    Patterns are indexed by genre and instrument. Markov-chain transition
    tables allow the generator to produce musically coherent bar sequences
    rather than purely random selections.
    """

    INSTRUMENTS = ['kick', 'snare', 'hihat', 'bass', 'synth', 'pad']

    def __init__(self):
        self.genre_patterns: Dict[str, Dict[str, List]] = {}
        self.genre_transitions: Dict[str, Dict] = {}
        self.global_patterns: Dict[str, List] = {inst: [] for inst in self.INSTRUMENTS}
        self.global_transitions: Dict = {}

    # ─── LOADING ──────────────────────────────────────────────────────────────

    def load_from_seeds(self, seeds: List[Dict]):
        for seed in seeds:
            genre = seed.get('genre', 'unknown')
            patterns = seed.get('instrument_patterns', {})
            if not patterns:
                continue

            if genre not in self.genre_patterns:
                self.genre_patterns[genre] = {inst: [] for inst in self.INSTRUMENTS}
                self.genre_transitions[genre] = {}

            drum_pats = patterns.get('drum_patterns', {})
            for inst in ['kick', 'snare', 'hihat', 'synth', 'pad']:
                for p in drum_pats.get(inst, []):
                    if isinstance(p, list) and len(p) == 16:
                        self.genre_patterns[genre][inst].append(p)
                        self.global_patterns[inst].append(p)

            for p in patterns.get('bass_patterns', []):
                if isinstance(p, list) and len(p) == 16:
                    self.genre_patterns[genre]['bass'].append(p)
                    self.global_patterns['bass'].append(p)

            for inst, inst_trans in patterns.get('pattern_transitions', {}).items():
                if not isinstance(inst_trans, dict):
                    continue
                if inst not in self.genre_transitions[genre]:
                    self.genre_transitions[genre][inst] = defaultdict(Counter)
                for pat_str, followers in inst_trans.items():
                    if isinstance(followers, dict):
                        for next_str, prob in followers.items():
                            self.genre_transitions[genre][inst][pat_str][next_str] += prob

        # Deduplicate
        for genre in self.genre_patterns:
            for inst in self.genre_patterns[genre]:
                unique = list(set(tuple(p) for p in self.genre_patterns[genre][inst] if p))
                self.genre_patterns[genre][inst] = [list(p) for p in unique]
        for inst in self.global_patterns:
            unique = list(set(tuple(p) for p in self.global_patterns[inst] if p))
            self.global_patterns[inst] = [list(p) for p in unique]

    # ─── PATTERN SELECTION ────────────────────────────────────────────────────

    def get_patterns_for_genre(self, genre: str, instrument: str) -> List[List[int]]:
        if genre in self.genre_patterns and self.genre_patterns[genre].get(instrument):
            return self.genre_patterns[genre][instrument]
        return self.global_patterns.get(instrument, [])

    def generate_pattern_sequence(
        self, genre: str, instrument: str, num_bars: int, complexity: float = 0.5
    ) -> List[List[int]]:
        """Generate a bar sequence using Markov transitions from learned patterns."""
        patterns = self.get_patterns_for_genre(genre, instrument)
        if not patterns:
            return [[0] * 16 for _ in range(num_bars)]

        transitions = {}
        if genre in self.genre_transitions and instrument in self.genre_transitions[genre]:
            transitions = self.genre_transitions[genre][instrument]

        sequence = []
        current = random.choice(patterns)
        sequence.append(current)

        for _ in range(num_bars - 1):
            current_str = str(current)
            if current_str in transitions and random.random() > complexity * 0.3:
                followers = transitions[current_str]
                total = sum(followers.values())
                r = random.uniform(0, total)
                cumulative = 0.0
                for next_str, prob in followers.items():
                    cumulative += prob
                    if r <= cumulative:
                        try:
                            current = json.loads(next_str)
                        except Exception:
                            current = random.choice(patterns)
                        break
                else:
                    current = random.choice(patterns)
            else:
                if random.random() < complexity * 0.4:
                    current = random.choice(patterns)
                else:
                    similar = [p for p in patterns if sum(p) == sum(current)]
                    current = random.choice(similar) if similar else random.choice(patterns)
            sequence.append(current)

        return sequence


# ─── HIGH-LEVEL GENERATOR ─────────────────────────────────────────────────────

def generate_drums_from_learned_patterns(
    pattern_generator: LearnedPatternGenerator,
    genre: str,
    structure: List[Tuple[str, int]],
    complexity: int,
    humanize_amount: float,
    bpm: float,
) -> List[Tuple[float, float, int, int]]:
    """
    Generate a full drum track as a list of (time, duration, pitch, velocity) tuples.

    Applies per-section pattern modifications (fade-ins, fade-outs, roll fills)
    and adds crash cymbals at section boundaries.
    """
    KICK, SNARE, HIHAT_CLOSED, HIHAT_OPEN, CRASH = 36, 38, 42, 46, 49

    notes = []
    total_bars = sum(bars for _, bars in structure)
    cf = complexity / 10.0

    kick_pats = pattern_generator.generate_pattern_sequence(genre, 'kick', total_bars, cf)
    snare_pats = pattern_generator.generate_pattern_sequence(genre, 'snare', total_bars, cf)
    hihat_pats = pattern_generator.generate_pattern_sequence(genre, 'hihat', total_bars, cf)

    bar_idx = 0
    for section_type, section_bars in structure:
        energy = _section_energy(section_type)
        for local_bar in range(section_bars):
            if bar_idx >= len(kick_pats):
                break

            bar_time = bar_idx * 4
            kick_pat = list(kick_pats[bar_idx]) if bar_idx < len(kick_pats) else [0] * 16
            snare_pat = list(snare_pats[bar_idx]) if bar_idx < len(snare_pats) else [0] * 16
            hihat_pat = list(hihat_pats[bar_idx]) if bar_idx < len(hihat_pats) else [0] * 16

            if section_type == 'intro':
                fade = (local_bar + 1) / max(1, section_bars)
                kick_pat = [int(v * fade) for v in kick_pat]
                snare_pat = [int(v * (fade * 0.5)) for v in snare_pat]
            elif section_type == 'outro':
                fade = 1.0 - (local_bar / max(1, section_bars))
                kick_pat = [int(v * fade) for v in kick_pat]
                snare_pat = [int(v * fade) for v in snare_pat]
                hihat_pat = [int(v * fade) for v in hihat_pat]
            elif section_type == 'break':
                kick_pat = [0] * 16
                snare_pat = [0] * 16
                hihat_pat = [v if i % 8 == 0 else 0 for i, v in enumerate(hihat_pat)]
            elif section_type == 'build':
                build_pct = (local_bar + 1) / section_bars
                if build_pct > 0.7:
                    for i in range(16):
                        if i % 2 == 0 and random.random() < build_pct * 0.5:
                            snare_pat[i] = 1

            for step in range(16):
                t = bar_time + (step / 4)
                h = (random.random() - 0.5) * 0.02 * humanize_amount
                if kick_pat[step] > 0:
                    vel = max(40, min(127, int((80 + random.randint(-8, 8) * humanize_amount) * energy)))
                    notes.append((t + h, 0.25, KICK, vel))
                if snare_pat[step] > 0:
                    vel = max(40, min(127, int((90 + random.randint(-10, 10) * humanize_amount) * energy)))
                    notes.append((t + h, 0.25, SNARE, vel))
                if hihat_pat[step] > 0:
                    vel = max(30, min(127, int((70 + random.randint(-6, 6) * humanize_amount) * energy)))
                    hat = HIHAT_OPEN if random.random() < 0.08 else HIHAT_CLOSED
                    dur = 0.4 if hat == HIHAT_OPEN else 0.15
                    notes.append((t + h, dur, hat, vel))

            if local_bar == 0 and section_type in ('chorus', 'drop', 'climax'):
                notes.append((bar_time, 1.0, CRASH, int(100 * energy)))

            bar_idx += 1

    return notes
