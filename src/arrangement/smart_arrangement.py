"""
SmartArrangementEngine

Learns song-structure patterns from seed data using Markov chains over section
types, then generates realistic arrangements for any target genre and duration.
"""

import random
from collections import defaultdict, Counter
from typing import List, Dict, Tuple, Optional

from src.arrangement.section_constants import DEFAULT_TRANSITIONS, SECTION_BAR_RANGES


class SmartArrangementEngine:
    """
    Learns and generates intelligent song structures from genre patterns.

    When seed data is available the engine learns transition probabilities and
    typical section lengths from real songs. When no seeds are loaded the engine
    falls back to the hard-coded DEFAULT_TRANSITIONS tables.
    """

    def __init__(self):
        self.genre_transitions: Dict[str, Dict] = {}
        self.genre_section_lengths: Dict[str, Dict] = {}
        self.genre_energy_profiles: Dict[str, List] = {}
        self._loaded = False

    # ─── LEARNING ─────────────────────────────────────────────────────────────

    def load_from_seeds(self, seeds: List[Dict]):
        """Learn arrangement patterns from seed data."""
        for seed in seeds:
            genre = seed.get('genre', 'pop')
            structure = seed.get('structure', [])
            if not structure:
                continue

            if genre not in self.genre_transitions:
                self.genre_transitions[genre] = defaultdict(Counter)
                self.genre_section_lengths[genre] = defaultdict(list)
                self.genre_energy_profiles[genre] = []

            sections = []
            for section in structure:
                if isinstance(section, dict):
                    sec_type = section.get('type', 'verse')
                    start = section.get('start', 0)
                    end = section.get('end', start + 16)
                    energy = section.get('energy', 0.5)
                    sections.append((sec_type, end - start, energy))
                elif isinstance(section, tuple):
                    sec_type, bars = section[:2]
                    sections.append((sec_type, bars * 4, 0.5))

            for i in range(len(sections) - 1):
                self.genre_transitions[genre][sections[i][0]][sections[i + 1][0]] += 1

            for sec_type, duration, energy in sections:
                bars = max(2, int(duration / 2))
                self.genre_section_lengths[genre][sec_type].append(bars)

            self.genre_energy_profiles[genre].append([s[2] for s in sections])

        # Normalise to probabilities
        for genre in self.genre_transitions:
            for section, followers in self.genre_transitions[genre].items():
                total = sum(followers.values())
                if total > 0:
                    for ns in followers:
                        followers[ns] = followers[ns] / total

        self._loaded = True
        total_patterns = sum(
            sum(len(fol) for fol in trans.values())
            for trans in self.genre_transitions.values()
        )
        print(f'Smart Arrangement: Learned {total_patterns} transition patterns')

    # ─── GENERATION ───────────────────────────────────────────────────────────

    def get_transition_matrix(self, genre: str) -> Dict[str, Dict[str, float]]:
        if genre in self.genre_transitions and self.genre_transitions[genre]:
            return dict(self.genre_transitions[genre])
        return DEFAULT_TRANSITIONS.get(genre, DEFAULT_TRANSITIONS['pop'])

    def get_section_length(self, genre: str, section_type: str, complexity: int = 5) -> int:
        if genre in self.genre_section_lengths:
            lengths = self.genre_section_lengths[genre].get(section_type, [])
            if lengths:
                base = random.choice(lengths)
                if complexity >= 7:
                    base = int(base * 1.2)
                elif complexity <= 3:
                    base = int(base * 0.8)
                return max(2, min(24, base))

        min_bars, max_bars = SECTION_BAR_RANGES.get(section_type, (4, 8))
        if complexity >= 7:
            max_bars = int(max_bars * 1.3)
        elif complexity <= 3:
            max_bars = int(max_bars * 0.7)
            min_bars = max(2, int(min_bars * 0.7))
        return random.randint(min_bars, max_bars)

    def generate_structure(
        self,
        genre: str,
        target_duration_bars: int = 64,
        complexity: int = 5,
        mutation: float = 0.0,
    ) -> List[Tuple[str, int]]:
        """
        Generate a song structure using learned or default patterns.

        Returns a list of (section_type, num_bars) tuples that sum to
        approximately target_duration_bars.
        """
        matrix = self.get_transition_matrix(genre)
        structure = []
        current_bars = 0
        current_section = 'intro'

        intro_bars = self.get_section_length(genre, 'intro', complexity)
        structure.append(('intro', intro_bars))
        current_bars += intro_bars

        section_counts = Counter({'intro': 1})
        max_repeats = 3 if complexity >= 7 else 2
        iteration = 0

        while current_bars < target_duration_bars - 8 and iteration < 30:
            iteration += 1
            transitions = matrix.get(current_section, {})

            if not transitions:
                next_section = random.choice(['verse', 'chorus', 'bridge', 'drop', 'build'])
            elif mutation > 0 and random.random() < mutation * 0.4:
                all_sections = list(
                    set(list(transitions.keys()) + ['verse', 'chorus', 'drop', 'bridge', 'build', 'break'])
                )
                next_section = random.choice(all_sections)
            else:
                next_section = self._weighted_choice(transitions)

            if section_counts[next_section] >= max_repeats:
                alts = [s for s in transitions if section_counts[s] < max_repeats]
                if alts:
                    next_section = random.choice(alts)
                elif current_bars > target_duration_bars * 0.7:
                    break

            section_bars = self.get_section_length(genre, next_section, complexity)
            if mutation > 0 and random.random() < mutation * 0.3:
                section_bars = max(2, int(section_bars * (1.0 + (random.random() - 0.5) * mutation)))
            if current_bars + section_bars > target_duration_bars + 8:
                section_bars = max(2, target_duration_bars - current_bars - 4)

            structure.append((next_section, section_bars))
            current_bars += section_bars
            section_counts[next_section] += 1
            current_section = next_section

        outro_bars = self.get_section_length(genre, 'outro', complexity)
        structure.append(('outro', outro_bars))
        return structure

    def analyze_energy_flow(self, structure: List[Tuple[str, int]]) -> List[float]:
        """Return per-section energy values for a generated structure."""
        energy_map = {
            'intro': 0.3, 'verse': 0.55, 'pre_chorus': 0.65, 'chorus': 0.85,
            'drop': 1.0, 'bridge': 0.5, 'break': 0.2, 'build': 0.7,
            'climax': 1.0, 'tension': 0.75, 'resolution': 0.5, 'outro': 0.25,
            'exposition': 0.6, 'development': 0.75, 'recapitulation': 0.7,
            'coda': 0.4, 'variation': 0.65,
        }
        return [energy_map.get(sec_type, 0.5) for sec_type, _ in structure]

    # ─── HELPERS ──────────────────────────────────────────────────────────────

    def _weighted_choice(self, options: Dict[str, float]) -> str:
        if not options:
            return 'verse'
        items = list(options.items())
        total = sum(w for _, w in items)
        if total == 0:
            return random.choice([k for k, _ in items])
        r = random.uniform(0, total)
        cumulative = 0.0
        for item, weight in items:
            cumulative += weight
            if r <= cumulative:
                return item
        return items[-1][0]


def create_smart_arrangement_engine(seeds: List[Dict]) -> SmartArrangementEngine:
    """Create and initialise a SmartArrangementEngine from a seed list."""
    engine = SmartArrangementEngine()
    engine.load_from_seeds(seeds)
    return engine
