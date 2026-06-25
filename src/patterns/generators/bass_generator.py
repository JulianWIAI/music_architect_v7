"""
LearnedBassGenerator

Generates bass lines from patterns learned across a seed collection.

Uses Markov-chain rhythm transitions and chord-relative interval sequences
to produce bass MIDI events. Supports groove-type weighting so that genres
with different characteristic bass feels (sustained 808, walking, etc.)
produce appropriately shaped output.
"""

import json
import random
from collections import defaultdict, Counter
from typing import List, Dict, Tuple

from src.utils.midi_utils import note_name_to_midi, parse_chord_string


def _section_energy(section_type: str) -> float:
    """Energy coefficient for each structural section type (bass perspective)."""
    return {
        'intro': 0.5, 'verse': 0.7, 'pre_chorus': 0.8, 'chorus': 1.0,
        'drop': 1.0, 'bridge': 0.6, 'breakdown': 0.4, 'build': 0.8,
        'outro': 0.5, 'break': 0.3, 'climax': 1.0, 'tension': 0.75,
        'resolution': 0.6, 'exposition': 0.7, 'development': 0.8,
        'recapitulation': 0.9, 'coda': 0.5,
    }.get(section_type, 0.7)


class LearnedBassGenerator:
    """
    Generates bass lines using rhythm patterns, intervals, and groove
    characteristics learned from a corpus of seeds.
    """

    def __init__(self):
        self.genre_patterns: Dict[str, Dict] = {}
        self.genre_transitions: Dict[str, defaultdict] = {}
        self.genre_grooves: Dict[str, defaultdict] = {}
        self.global_patterns: Dict[str, List] = {'rhythms': [], 'velocities': [], 'intervals': []}
        self.global_transitions: Dict = {}

    # ─── LOADING ──────────────────────────────────────────────────────────────

    def load_from_seeds(self, seeds: List[Dict]):
        for seed in seeds:
            genre = seed.get('genre', 'unknown')
            if genre not in self.genre_patterns:
                self.genre_patterns[genre] = {'rhythms': [], 'velocities': [], 'intervals': []}
                self.genre_transitions[genre] = defaultdict(Counter)
                self.genre_grooves[genre] = defaultdict(int)

            # Prefer dedicated bass_patterns field (new seed format)
            bass_data = seed.get('bass_patterns', {})
            if isinstance(bass_data, dict) and bass_data.get('rhythm_patterns'):
                self._load_from_bass_data(genre, bass_data)
                continue

            # Fallback: extract from instrument_patterns
            inst_patterns = seed.get('instrument_patterns', {})
            if not isinstance(inst_patterns, dict):
                continue

            trans = inst_patterns.get('pattern_transitions', {})
            bass_trans = trans.get('bass', {}) if isinstance(trans, dict) else {}
            if isinstance(bass_trans, dict):
                for pat_str, followers in bass_trans.items():
                    try:
                        pattern = json.loads(pat_str)
                        if isinstance(pattern, list) and len(pattern) == 16:
                            self.genre_patterns[genre]['rhythms'].append(pattern)
                            self.global_patterns['rhythms'].append(pattern)
                        if isinstance(followers, dict):
                            for ns, prob in followers.items():
                                self.genre_transitions[genre][pat_str][ns] += prob
                    except (json.JSONDecodeError, ValueError):
                        continue

            bass_info = inst_patterns.get('bass', {})
            if isinstance(bass_info, dict):
                density = bass_info.get('density', 0)
                if density < 0.1:
                    self.genre_grooves[genre]['sustained'] += 1
                elif density < 0.3:
                    self.genre_grooves[genre]['sparse'] += 1
                elif density < 0.5:
                    self.genre_grooves[genre]['rhythmic'] += 1
                else:
                    self.genre_grooves[genre]['melodic'] += 1

        self._deduplicate()
        total = len(self.global_patterns.get('rhythms', []))
        genres = len([g for g in self.genre_patterns if self.genre_patterns[g].get('rhythms')])
        print(f'  Bass patterns loaded: {total} rhythms across {genres} genres')

    def _load_from_bass_data(self, genre: str, bass_data: Dict):
        for r in bass_data.get('rhythm_patterns', []):
            if isinstance(r, list) and len(r) == 16:
                self.genre_patterns[genre]['rhythms'].append(r)
                self.global_patterns['rhythms'].append(r)
        for v in bass_data.get('velocity_patterns', []):
            if isinstance(v, list) and len(v) == 16:
                self.genre_patterns[genre]['velocities'].append(v)
                self.global_patterns['velocities'].append(v)
        for iv in bass_data.get('interval_patterns', []):
            if isinstance(iv, list):
                self.genre_patterns[genre]['intervals'].append(iv)
                self.global_patterns['intervals'].append(iv)
        for groove_type, count in bass_data.get('groove_distribution', {}).items():
            self.genre_grooves[genre][groove_type] += count
        for pat_str, followers in bass_data.get('pattern_transitions', {}).items():
            if isinstance(followers, dict):
                for ns, prob in followers.items():
                    self.genre_transitions[genre][pat_str][ns] += prob

    def _deduplicate(self):
        for genre in self.genre_patterns:
            for pt in ['rhythms', 'velocities', 'intervals']:
                unique = list(set(tuple(p) for p in self.genre_patterns[genre].get(pt, [])))
                self.genre_patterns[genre][pt] = [list(p) for p in unique]
        for pt in ['rhythms', 'velocities', 'intervals']:
            unique = list(set(tuple(p) for p in self.global_patterns.get(pt, [])))
            self.global_patterns[pt] = [list(p) for p in unique]

    # ─── SELECTION ────────────────────────────────────────────────────────────

    def get_patterns_for_genre(self, genre: str, pattern_type: str) -> List:
        if genre in self.genre_patterns:
            pats = self.genre_patterns[genre].get(pattern_type, [])
            if pats:
                return pats
        return self.global_patterns.get(pattern_type, [])

    def pick_groove_type(self, genre: str) -> str:
        if genre in self.genre_grooves and self.genre_grooves[genre]:
            grooves = self.genre_grooves[genre]
            total = sum(grooves.values())
            r = random.uniform(0, total)
            cumulative = 0.0
            for groove, count in grooves.items():
                cumulative += count
                if r <= cumulative:
                    return groove
        return random.choice(['sustained', 'rhythmic', 'melodic', 'syncopated', 'sparse'])

    def generate_rhythm_sequence(
        self, genre: str, num_bars: int, complexity: float = 0.5
    ) -> List[List[int]]:
        patterns = self.get_patterns_for_genre(genre, 'rhythms')
        if not patterns:
            return [self._fallback_rhythm(complexity) for _ in range(num_bars)]

        transitions = self.genre_transitions.get(genre, {})
        sequence = []
        current = random.choice(patterns)
        sequence.append(current)

        for _ in range(num_bars - 1):
            current_str = str(current)
            if current_str in transitions and random.random() > complexity * 0.4:
                followers = transitions[current_str]
                total = sum(followers.values())
                r = random.uniform(0, total)
                cumulative = 0.0
                chosen = None
                for ns, prob in followers.items():
                    cumulative += prob
                    if r <= cumulative:
                        try:
                            chosen = json.loads(ns)
                        except Exception:
                            pass
                        break
                current = chosen if chosen else random.choice(patterns)
            else:
                if random.random() < complexity * 0.3:
                    current = random.choice(patterns)
                else:
                    similar = [p for p in patterns if abs(sum(p) - sum(current)) <= 2]
                    current = random.choice(similar) if similar else random.choice(patterns)
            sequence.append(current)

        return sequence

    def generate_interval_sequence(
        self, genre: str, rhythm_sequence: List[List[int]], chord_progression: List[str]
    ) -> List[List[int]]:
        interval_patterns = self.get_patterns_for_genre(genre, 'intervals')
        sequence = []
        for bar_idx, rhythm in enumerate(rhythm_sequence):
            num_hits = sum(rhythm)
            if num_hits == 0:
                sequence.append([])
                continue
            matching = [p for p in interval_patterns if len(p) == num_hits]
            if matching:
                sequence.append(list(random.choice(matching)))
            else:
                ivs = []
                for pos in (i for i, v in enumerate(rhythm) if v == 1):
                    if pos == 0:
                        ivs.append(0)
                    elif pos == 8:
                        ivs.append(random.choice([0, 7]))
                    elif pos in [4, 12]:
                        ivs.append(random.choice([0, 4, 7]))
                    else:
                        ivs.append(random.choice([0, 2, 3, 4, 5, 7, 10]))
                sequence.append(ivs)
        return sequence

    def _fallback_rhythm(self, complexity: float) -> List[int]:
        pattern = [0] * 16
        pattern[0] = 1
        if complexity > 0.3:
            pattern[8] = 1
        if complexity > 0.5:
            pattern[4] = pattern[12] = 1
        if complexity > 0.7:
            for i in [2, 6, 10, 14]:
                if random.random() < complexity * 0.4:
                    pattern[i] = 1
        return pattern

    def mutate_pattern(self, pattern: List[int], rate: float = 0.1) -> List[int]:
        mutated = pattern.copy()
        for i in range(len(mutated)):
            if random.random() < rate:
                mutated[i] = 1 - mutated[i]
        if sum(mutated) == 0:
            mutated[0] = 1
        return mutated


# ─── HIGH-LEVEL GENERATOR ─────────────────────────────────────────────────────

def generate_bass_from_learned_patterns(
    bass_generator: LearnedBassGenerator,
    genre: str,
    chord_progression: List[str],
    structure: List[Tuple[str, int]],
    complexity: int,
    humanize_amount: float,
    bpm: float,
    volume: float = 0.8,
) -> List[Tuple[float, float, int, int]]:
    """
    Generate a full bass track as a list of (time, duration, pitch, velocity) tuples.

    Applies groove-type shaping, chord-root tracking, and section-based
    energy scaling.
    """
    notes = []
    total_bars = sum(bars for _, bars in structure)
    cf = complexity / 10.0
    base_velocity = int(90 * volume)

    rhythm_sequence = bass_generator.generate_rhythm_sequence(genre, total_bars, cf)
    interval_sequence = bass_generator.generate_interval_sequence(genre, rhythm_sequence, chord_progression)

    bar_idx = 0
    chord_idx = 0

    for section_type, section_bars in structure:
        energy = _section_energy(section_type)

        for local_bar in range(section_bars):
            if bar_idx >= len(rhythm_sequence):
                break

            bar_time = bar_idx * 4
            chord_str = (
                chord_progression[chord_idx]
                if chord_idx < len(chord_progression)
                else chord_progression[chord_idx % len(chord_progression)] if chord_progression else 'Cmaj7'
            )
            root, quality = parse_chord_string(chord_str)
            root_midi = note_name_to_midi(root, 2)

            rhythm = rhythm_sequence[bar_idx] if bar_idx < len(rhythm_sequence) else [1] + [0] * 15
            intervals = interval_sequence[bar_idx] if bar_idx < len(interval_sequence) else [0]

            # Section shaping
            if section_type == 'intro':
                energy *= (local_bar + 1) / max(1, section_bars)
            elif section_type == 'outro':
                energy *= 1.0 - (local_bar / max(1, section_bars))
            elif section_type == 'break':
                energy *= 0.3
            elif section_type == 'build':
                energy *= 0.5 + ((local_bar + 1) / section_bars) * 0.5

            interval_idx = 0
            for step in range(16):
                if not rhythm[step]:
                    continue
                step_time = bar_time + (step / 4)
                interval = intervals[interval_idx] if interval_idx < len(intervals) else 0
                interval_idx += 1

                midi_note = root_midi + interval
                while midi_note > 60:
                    midi_note -= 12
                while midi_note < 28:
                    midi_note += 12

                # Duration: hold until next hit
                next_hit = next((s for s in range(step + 1, 16) if rhythm[s]), None)
                duration = (next_hit - step) / 4 - 0.05 if next_hit else (16 - step) / 4 - 0.1
                groove = bass_generator.pick_groove_type(genre)
                if groove == 'sustained' and sum(rhythm) <= 2:
                    duration = min(duration * 1.5, 3.8)
                duration = max(0.1, duration)

                h_offset = (random.random() - 0.5) * 0.02 * humanize_amount
                velocity = max(40, min(127, int(base_velocity * energy + random.randint(-8, 8) * humanize_amount)))
                if step == 0:
                    velocity = min(127, velocity + 10)

                notes.append((step_time + h_offset, duration, midi_note, velocity))

            bar_idx += 1
            chord_idx += 1

    return notes
