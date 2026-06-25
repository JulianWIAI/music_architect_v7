"""
LearnedLeadGenerator

Generates lead melody lines from patterns learned across a seed collection.

Combines rhythm sequences, chord-relative interval sequences, and melodic
contour chains to produce musically coherent single-voice melodies.
"""

import json
import random
from collections import defaultdict, Counter
from typing import List, Dict, Tuple

from src.utils.midi_utils import note_name_to_midi, parse_chord_string, get_scale_notes
from src.patterns.extractors.lead_extractor import (
    CONTOUR_UP, CONTOUR_DOWN, CONTOUR_STAY, CONTOUR_JUMP_UP, CONTOUR_JUMP_DOWN,
)


def _section_energy(section_type: str) -> float:
    """Energy coefficient for each structural section type (lead perspective)."""
    return {
        'intro': 0.4, 'verse': 0.6, 'pre_chorus': 0.7, 'chorus': 0.9,
        'drop': 1.0, 'bridge': 0.55, 'breakdown': 0.4, 'build': 0.75,
        'outro': 0.35, 'break': 0.25, 'climax': 1.0, 'tension': 0.7,
        'resolution': 0.5, 'exposition': 0.6, 'development': 0.75,
        'recapitulation': 0.85, 'coda': 0.45,
    }.get(section_type, 0.6)


class LearnedLeadGenerator:
    """
    Generates lead melodies using rhythm patterns, contours, intervals, and
    phrase structures learned from a corpus of seeds.
    """

    def __init__(self):
        self.genre_patterns: Dict[str, Dict] = {}
        self.genre_transitions: Dict[str, defaultdict] = {}
        self.genre_phrases: Dict[str, defaultdict] = {}
        self.genre_contour_trans: Dict[str, defaultdict] = {}
        self.global_patterns: Dict[str, List] = {
            'rhythms': [], 'velocities': [], 'contours': [], 'intervals': []
        }

    # ─── LOADING ──────────────────────────────────────────────────────────────

    def load_from_seeds(self, seeds: List[Dict]):
        for seed in seeds:
            genre = seed.get('genre', 'unknown')
            if genre not in self.genre_patterns:
                self.genre_patterns[genre] = {
                    'rhythms': [], 'velocities': [], 'contours': [], 'intervals': []
                }
                self.genre_transitions[genre] = defaultdict(Counter)
                self.genre_phrases[genre] = defaultdict(int)
                self.genre_contour_trans[genre] = defaultdict(Counter)

            lead_data = seed.get('lead_patterns', {})
            if isinstance(lead_data, dict) and lead_data.get('rhythm_patterns'):
                self._load_from_lead_data(genre, lead_data)
                continue

            inst_patterns = seed.get('instrument_patterns', {})
            if not isinstance(inst_patterns, dict):
                continue

            transitions = inst_patterns.get('pattern_transitions', {})
            synth_trans = (
                transitions.get('synth', {}) or transitions.get('lead', {})
                if isinstance(transitions, dict) else {}
            )
            if isinstance(synth_trans, dict):
                for pat_str, followers in synth_trans.items():
                    try:
                        pattern = json.loads(pat_str)
                        if isinstance(pattern, list) and len(pattern) == 16:
                            self.genre_patterns[genre]['rhythms'].append(pattern)
                            self.global_patterns['rhythms'].append(pattern)
                        if isinstance(followers, dict):
                            for ns, prob in followers.items():
                                self.genre_transitions[genre][pat_str][ns] += prob
                    except (json.JSONDecodeError, ValueError, TypeError):
                        continue

            drum_patterns = inst_patterns.get('drum_patterns', {})
            if isinstance(drum_patterns, dict):
                for inst in ('synth', 'pad'):
                    for pat in drum_patterns.get(inst, []):
                        if isinstance(pat, list) and len(pat) == 16:
                            self.genre_patterns[genre]['rhythms'].append(pat)
                            self.global_patterns['rhythms'].append(pat)

            synth_info = inst_patterns.get('synth', {})
            if isinstance(synth_info, dict):
                density = synth_info.get('density', 0)
                if density > 0:
                    if density < 0.1:
                        self.genre_phrases[genre]['sustained'] += 1
                    elif density < 0.3:
                        self.genre_phrases[genre]['sparse'] += 1
                    elif density < 0.5:
                        self.genre_phrases[genre]['rhythmic'] += 1
                    else:
                        self.genre_phrases[genre]['flowing'] += 1

        self._deduplicate()
        total = len(self.global_patterns.get('rhythms', []))
        genres = len([g for g in self.genre_patterns if self.genre_patterns[g].get('rhythms')])
        print(f'  Lead patterns loaded: {total} rhythms across {genres} genres')

    def _load_from_lead_data(self, genre: str, lead_data: Dict):
        for r in lead_data.get('rhythm_patterns', []):
            if isinstance(r, list) and len(r) == 16:
                self.genre_patterns[genre]['rhythms'].append(r)
                self.global_patterns['rhythms'].append(r)
        for v in lead_data.get('velocity_patterns', []):
            if isinstance(v, list) and len(v) == 16:
                self.genre_patterns[genre]['velocities'].append(v)
                self.global_patterns['velocities'].append(v)
        for c in lead_data.get('contour_patterns', []):
            if isinstance(c, list):
                self.genre_patterns[genre]['contours'].append(c)
                self.global_patterns['contours'].append(c)
        for iv in lead_data.get('interval_patterns', []):
            if isinstance(iv, list):
                self.genre_patterns[genre]['intervals'].append(iv)
                self.global_patterns['intervals'].append(iv)
        for pt, count in lead_data.get('phrase_distribution', {}).items():
            self.genre_phrases[genre][pt] += count
        for pat_str, followers in lead_data.get('pattern_transitions', {}).items():
            if isinstance(followers, dict):
                for ns, prob in followers.items():
                    self.genre_transitions[genre][pat_str][ns] += prob
        for cont, followers in lead_data.get('contour_transitions', {}).items():
            if isinstance(followers, dict):
                for nc, prob in followers.items():
                    self.genre_contour_trans[genre][cont][nc] += prob

    def _deduplicate(self):
        for genre in self.genre_patterns:
            for pt in ['rhythms', 'velocities', 'contours', 'intervals']:
                pats = self.genre_patterns[genre].get(pt, [])
                unique = list(set(tuple(p) if isinstance(p, list) else p for p in pats))
                self.genre_patterns[genre][pt] = [
                    list(p) if isinstance(p, tuple) else p for p in unique
                ]
        for pt in ['rhythms', 'velocities', 'contours', 'intervals']:
            pats = self.global_patterns.get(pt, [])
            unique = list(set(tuple(p) if isinstance(p, list) else p for p in pats))
            self.global_patterns[pt] = [list(p) if isinstance(p, tuple) else p for p in unique]

    # ─── SELECTION ────────────────────────────────────────────────────────────

    def get_patterns_for_genre(self, genre: str, pattern_type: str) -> List:
        if genre in self.genre_patterns:
            pats = self.genre_patterns[genre].get(pattern_type, [])
            if pats:
                return pats
        return self.global_patterns.get(pattern_type, [])

    def pick_phrase_type(self, genre: str) -> str:
        if genre in self.genre_phrases and self.genre_phrases[genre]:
            phrases = self.genre_phrases[genre]
            total = sum(phrases.values())
            if total > 0:
                r = random.uniform(0, total)
                cumulative = 0.0
                for phrase, count in phrases.items():
                    cumulative += count
                    if r <= cumulative:
                        return phrase
        return random.choice(['sustained', 'flowing', 'rhythmic', 'sparse', 'staccato'])

    def generate_rhythm_sequence(
        self, genre: str, num_bars: int, complexity: float = 0.5, section_type: str = 'verse'
    ) -> List[List[int]]:
        patterns = self.get_patterns_for_genre(genre, 'rhythms')
        if not patterns:
            return [self._fallback_rhythm(complexity, section_type) for _ in range(num_bars)]

        transitions = self.genre_transitions.get(genre, {})
        if section_type in ('intro', 'outro', 'break'):
            sparse = [p for p in patterns if sum(p) <= 4]
            current = random.choice(sparse) if sparse else random.choice(patterns)
        elif section_type in ('chorus', 'drop', 'climax'):
            dense = [p for p in patterns if sum(p) >= 4]
            current = random.choice(dense) if dense else random.choice(patterns)
        else:
            current = random.choice(patterns)

        sequence = [current]
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

    def generate_contour_sequence(self, num_notes: int, genre: str) -> List[str]:
        contour_trans = self.genre_contour_trans.get(genre, {})
        sequence = []
        current = random.choice([CONTOUR_STAY, CONTOUR_UP, CONTOUR_DOWN])
        for _ in range(num_notes):
            sequence.append(current)
            if current in contour_trans and contour_trans[current]:
                followers = contour_trans[current]
                total = sum(followers.values())
                r = random.uniform(0, total)
                cumulative = 0.0
                for nc, prob in followers.items():
                    cumulative += prob
                    if r <= cumulative:
                        current = nc
                        break
            else:
                weights = {
                    CONTOUR_STAY: 0.2, CONTOUR_UP: 0.3, CONTOUR_DOWN: 0.3,
                    CONTOUR_JUMP_UP: 0.1, CONTOUR_JUMP_DOWN: 0.1,
                }
                current = random.choices(list(weights.keys()), list(weights.values()))[0]
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
            quality = 'maj'
            if bar_idx < len(chord_progression):
                chord_str = chord_progression[bar_idx]
                quality = chord_str[1:] if len(chord_str) > 1 else 'maj'
            chord_tones = [0, 3, 7, 10] if 'min' in quality.lower() else [0, 4, 7, 11]
            scale_tones = [0, 2, 3, 5, 7, 8, 10] if 'min' in quality.lower() else [0, 2, 4, 5, 7, 9, 11]
            matching = [p for p in interval_patterns if len(p) == num_hits]
            if matching:
                sequence.append(list(random.choice(matching)))
            else:
                ivs = []
                prev = 0
                for pos in (i for i, v in enumerate(rhythm) if v == 1):
                    if pos == 0:
                        iv = random.choice(chord_tones)
                    elif pos % 4 == 0:
                        iv = random.choice(chord_tones)
                    else:
                        step = random.choice([-2, -1, 1, 2])
                        iv = prev + step
                        if iv not in scale_tones:
                            iv = min(scale_tones, key=lambda x: abs(x - iv))
                    ivs.append(iv % 12)
                    prev = iv
                sequence.append(ivs)
        return sequence

    def _fallback_rhythm(self, complexity: float, section_type: str) -> List[int]:
        pattern = [0] * 16
        if section_type in ('intro', 'outro', 'break'):
            positions = [0, 8] if complexity < 0.5 else [0, 4, 8, 12]
        elif section_type in ('chorus', 'drop'):
            positions = [0, 2, 4, 6, 8, 10, 12, 14][:int(4 + complexity * 4)]
        else:
            positions = [0, 4, 8, 12][:int(2 + complexity * 2)]
        for pos in positions:
            if random.random() < 0.8:
                pattern[pos] = 1
        return pattern


# ─── HIGH-LEVEL GENERATOR ─────────────────────────────────────────────────────

def generate_lead_from_learned_patterns(
    lead_generator: LearnedLeadGenerator,
    genre: str,
    chord_progression: List[str],
    structure: List[Tuple[str, int]],
    complexity: int,
    humanize_amount: float,
    bpm: float,
    volume: float = 0.75,
    key: str = 'C major',
) -> List[Tuple[float, float, int, int]]:
    """
    Generate a full lead-melody track as a list of (time, duration, pitch, velocity) tuples.

    Applies contour-guided pitch selection, phrase-type duration shaping,
    and section-based energy scaling.
    """
    notes = []
    cf = complexity / 10.0
    base_velocity = int(85 * volume)

    key_parts = key.split()
    bar_idx = 0
    chord_idx = 0
    prev_note = None

    for section_type, section_bars in structure:
        energy = _section_energy(section_type)
        if section_type in ('intro', 'outro') and complexity < 7:
            if random.random() < 0.3:
                bar_idx += section_bars
                chord_idx += section_bars
                continue

        rhythm_sequence = lead_generator.generate_rhythm_sequence(
            genre, section_bars, cf, section_type
        )
        section_chords = chord_progression[chord_idx:chord_idx + section_bars]
        interval_sequence = lead_generator.generate_interval_sequence(
            genre, rhythm_sequence, section_chords
        )
        total_notes = sum(sum(r) for r in rhythm_sequence)
        contour_sequence = lead_generator.generate_contour_sequence(total_notes, genre)
        contour_idx = 0

        for local_bar in range(section_bars):
            if local_bar >= len(rhythm_sequence):
                break

            bar_time = bar_idx * 4
            chord_str = (
                chord_progression[chord_idx]
                if chord_idx < len(chord_progression)
                else chord_progression[chord_idx % len(chord_progression)] if chord_progression else 'Cmaj7'
            )
            root, quality = parse_chord_string(chord_str)
            scale = get_scale_notes(root, quality, 5)
            root_midi = note_name_to_midi(root, 5)

            rhythm = rhythm_sequence[local_bar]
            intervals = interval_sequence[local_bar] if local_bar < len(interval_sequence) else []
            section_vel = base_velocity * energy * (1.1 if section_type in ('chorus', 'drop', 'climax') else 0.5 if section_type == 'break' else 1.0)

            interval_idx = 0
            for step in range(16):
                if not rhythm[step]:
                    continue
                step_time = bar_time + (step / 4)
                interval = intervals[interval_idx] if interval_idx < len(intervals) else 0
                interval_idx += 1

                midi_note = root_midi + interval

                if contour_idx < len(contour_sequence) and prev_note is not None:
                    contour = contour_sequence[contour_idx]
                    contour_idx += 1
                    if contour == CONTOUR_UP:
                        cands = [n for n in scale if prev_note < n <= prev_note + 4]
                        if cands:
                            midi_note = min(cands)
                    elif contour == CONTOUR_DOWN:
                        cands = [n for n in scale if prev_note - 4 <= n < prev_note]
                        if cands:
                            midi_note = max(cands)
                    elif contour == CONTOUR_JUMP_UP:
                        midi_note = prev_note + random.choice([5, 7, 8])
                    elif contour == CONTOUR_JUMP_DOWN:
                        midi_note = prev_note - random.choice([5, 7, 8])
                    elif contour == CONTOUR_STAY:
                        midi_note = prev_note

                while midi_note > 84:
                    midi_note -= 12
                while midi_note < 60:
                    midi_note += 12

                next_hit = next((s for s in range(step + 1, 16) if rhythm[s]), None)
                duration = (next_hit - step) / 4 - 0.05 if next_hit else (16 - step) / 4 - 0.1
                phrase = lead_generator.pick_phrase_type(genre)
                if phrase == 'staccato':
                    duration = min(duration, 0.25)
                elif phrase == 'sustained':
                    duration = min(duration * 1.5, 2.0)
                duration = max(0.1, duration)

                h_offset = (random.random() - 0.5) * 0.025 * humanize_amount
                velocity = max(40, min(127, int(section_vel + random.randint(-10, 10) * humanize_amount)))
                if step == 0:
                    velocity = min(127, velocity + 8)
                elif step == 8:
                    velocity = min(127, velocity + 4)

                notes.append((step_time + h_offset, duration, midi_note, velocity))
                prev_note = midi_note

            bar_idx += 1
            chord_idx += 1

    return notes
