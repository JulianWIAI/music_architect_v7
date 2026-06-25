import json
import random
import os
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Tuple, Optional

try:
    from midiutil import MIDIFile
    MIDI_AVAILABLE = True
except ImportError:
    MIDI_AVAILABLE = False
    print("WARNING: midiutil not installed. Run: pip install midiutil")

try:
    from src.patterns.generators.rhythm_generator import LearnedPatternGenerator
    LEARNED_PATTERNS_AVAILABLE = True
except ImportError:
    LEARNED_PATTERNS_AVAILABLE = False

try:
    from src.arrangement.genre_fusion import GenreFusionEngine
    FUSION_AVAILABLE = True
except ImportError:
    FUSION_AVAILABLE = False

try:
    from src.arrangement.smart_arrangement import SmartArrangementEngine
    SMART_ARRANGEMENT_AVAILABLE = True
except ImportError:
    SMART_ARRANGEMENT_AVAILABLE = False

try:
    from src.patterns.rhythmic_decoupler import RhythmicDecoupler
    RHYTHMIC_DECOUPLER_AVAILABLE = True
except ImportError:
    RHYTHMIC_DECOUPLER_AVAILABLE = False

try:
    from src.generation.omni_layers import OmniLayerGenerator
    OMNI_LAYERS_AVAILABLE = True
except ImportError:
    OMNI_LAYERS_AVAILABLE = False

from src.composition.genre_constants import (
    NOTE_TO_MIDI, MIDI_TO_NOTE, CHORD_INTERVALS, SCALE_INTERVALS,
    KICK, SNARE, RIMSHOT, CLAP, HIHAT_CLOSED, HIHAT_OPEN, HIHAT_PEDAL, CRASH, RIDE,
    TOM_LOW, TOM_MID, TOM_HIGH,
    GENRE_DRUM_PATTERNS, GENRE_BPM, GENRE_SCALES, GENRE_INSTRUMENTS, STRUCTURE_TEMPLATES,
    note_name_to_midi, get_chord_midi_notes, parse_chord_string, get_scale_notes,
    weighted_choice, humanize, humanize_velocity,
)
from src.composition.composition_config import CompositionConfig


def _tension_skew_weights(followers: dict, tension_factor: float) -> dict:
    """
    Blend follower probability weights between normal and inverted distributions.

    At tension_factor=1.0 every high-probability chord is de-emphasised and
    low-probability (surprising/dissonant) chords are preferred — creating
    harmonic tension.  At tension_factor=0.0 weights are returned unchanged.
    """
    if not followers or tension_factor <= 0:
        return followers
    max_w = max(followers.values())
    eps = max_w * 0.05
    result = {}
    for chord, w in followers.items():
        inverted = max_w - w + eps
        blended = (1.0 - tension_factor) * w + tension_factor * inverted
        result[chord] = max(0.001, blended)
    return result


class CompositionEngine:
    """
    The heart of the system: generates complete multi-track songs
    from musical DNA seeds.
    """

    def __init__(self, seeds_dir: str = "seeds"):
        self.seeds_dir = Path(seeds_dir)
        self.seeds = []
        self.genre_seeds = defaultdict(list)
        self.genre_matrices = {}
        self.global_matrix = {}
        self._loaded = False
        self.pattern_generator = None
        self.fusion_engine = None
        self.arrangement_engine = None

    def load_seeds(self):
        """Load seed data from JSON files."""
        master_path = self.seeds_dir / "master_seeds.json"
        if master_path.exists():
            with open(master_path, 'r', encoding='utf-8') as f:
                self.seeds = json.load(f)
            for seed in self.seeds:
                self.genre_seeds[seed.get('genre', 'pop')].append(seed)
            print(f"LOADED {len(self.seeds)} seeds ({len(self.genre_seeds)} genres)")

        matrices_dir = self.seeds_dir / "matrices"
        if matrices_dir.exists():
            for f in matrices_dir.glob("matrix_*.json"):
                genre = f.stem.replace("matrix_", "")
                with open(f, 'r', encoding='utf-8') as fh:
                    self.genre_matrices[genre] = json.load(fh)
            if 'global' in self.genre_matrices:
                self.global_matrix = self.genre_matrices.pop('global')
            print(f"LOADED {len(self.genre_matrices)} genre matrices")

        if LEARNED_PATTERNS_AVAILABLE:
            try:
                self.pattern_generator = LearnedPatternGenerator()
                self.pattern_generator.load_from_seeds(self.seeds)
                total_patterns = sum(len(p) for p in self.pattern_generator.global_patterns.values())
                print(f"LOADED {total_patterns} rhythm patterns")
            except Exception as e:
                print(f"Rhythm patterns not available: {e}")
                self.pattern_generator = None

        self.bass_patterns = {'global': [], 'by_genre': {}}
        try:
            bass_count = 0
            for seed in self.seeds:
                genre = seed.get('genre', 'unknown')
                if genre not in self.bass_patterns['by_genre']:
                    self.bass_patterns['by_genre'][genre] = []

                inst_patterns = seed.get('instrument_patterns', {})
                if isinstance(inst_patterns, dict):
                    transitions = inst_patterns.get('pattern_transitions', {})
                    if isinstance(transitions, dict):
                        bass_trans = transitions.get('bass', {})
                        if isinstance(bass_trans, dict):
                            for pat_str in bass_trans.keys():
                                try:
                                    pattern = json.loads(pat_str)
                                    if isinstance(pattern, list) and len(pattern) == 16:
                                        self.bass_patterns['global'].append(pattern)
                                        self.bass_patterns['by_genre'][genre].append(pattern)
                                        bass_count += 1
                                except:
                                    pass

                    drum_pats = inst_patterns.get('drum_patterns', {})
                    if isinstance(drum_pats, dict):
                        bass_pats = drum_pats.get('bass', [])
                        if isinstance(bass_pats, list):
                            for p in bass_pats:
                                if isinstance(p, list) and len(p) == 16:
                                    self.bass_patterns['global'].append(p)
                                    self.bass_patterns['by_genre'][genre].append(p)
                                    bass_count += 1

            self.bass_patterns['global'] = [list(p) for p in set(tuple(p) for p in self.bass_patterns['global'])]
            for genre in self.bass_patterns['by_genre']:
                self.bass_patterns['by_genre'][genre] = [list(p) for p in set(tuple(p) for p in self.bass_patterns['by_genre'][genre])]

            total_bass = len(self.bass_patterns['global'])
            if total_bass > 0:
                print(f"LOADED {total_bass} bass patterns")
        except Exception as e:
            print(f"Bass patterns not available: {e}")

        self.lead_patterns = {'global': [], 'by_genre': {}}
        try:
            lead_count = 0
            for seed in self.seeds:
                genre = seed.get('genre', 'unknown')
                if genre not in self.lead_patterns['by_genre']:
                    self.lead_patterns['by_genre'][genre] = []

                inst_patterns = seed.get('instrument_patterns', {})
                if isinstance(inst_patterns, dict):
                    transitions = inst_patterns.get('pattern_transitions', {})
                    if isinstance(transitions, dict):
                        for key in ['synth', 'lead', 'pad']:
                            synth_trans = transitions.get(key, {})
                            if isinstance(synth_trans, dict):
                                for pat_str in synth_trans.keys():
                                    try:
                                        pattern = json.loads(pat_str)
                                        if isinstance(pattern, list) and len(pattern) == 16:
                                            self.lead_patterns['global'].append(pattern)
                                            self.lead_patterns['by_genre'][genre].append(pattern)
                                            lead_count += 1
                                    except:
                                        pass

                    drum_pats = inst_patterns.get('drum_patterns', {})
                    if isinstance(drum_pats, dict):
                        for key in ['synth', 'pad']:
                            synth_pats = drum_pats.get(key, [])
                            if isinstance(synth_pats, list):
                                for p in synth_pats:
                                    if isinstance(p, list) and len(p) == 16:
                                        self.lead_patterns['global'].append(p)
                                        self.lead_patterns['by_genre'][genre].append(p)
                                        lead_count += 1

            self.lead_patterns['global'] = [list(p) for p in set(tuple(p) for p in self.lead_patterns['global'])]
            for genre in self.lead_patterns['by_genre']:
                self.lead_patterns['by_genre'][genre] = [list(p) for p in set(tuple(p) for p in self.lead_patterns['by_genre'][genre])]

            total_lead = len(self.lead_patterns['global'])
            if total_lead > 0:
                print(f"LOADED {total_lead} lead patterns")
        except Exception as e:
            print(f"Lead patterns not available: {e}")

        if FUSION_AVAILABLE and self.pattern_generator:
            try:
                self.fusion_engine = GenreFusionEngine(self.pattern_generator)
                print("FUSION ENGINE READY")
            except Exception as e:
                print(f"Fusion engine not available: {e}")
                self.fusion_engine = None

        self.rhythmic_decoupler = RhythmicDecoupler() if RHYTHMIC_DECOUPLER_AVAILABLE else None
        self.omni_layer_gen     = OmniLayerGenerator() if OMNI_LAYERS_AVAILABLE else None

        if SMART_ARRANGEMENT_AVAILABLE:
            try:
                self.arrangement_engine = SmartArrangementEngine()
                self.arrangement_engine.load_from_seeds(self.seeds)
            except Exception as e:
                print(f"Smart arrangement not available: {e}")
                self.arrangement_engine = None

        self._loaded = True

    def _ensure_loaded(self):
        if not self._loaded:
            self.load_seeds()

    # ─────────────────────────────────────────────────────────────────
    #  CHORD PROGRESSION GENERATION (Markov Chain + Theory)
    # ─────────────────────────────────────────────────────────────────

    def generate_chord_progression(
        self,
        config: CompositionConfig,
        num_chords: int = 32,
        structure: Optional[List[Tuple[str, int]]] = None,
    ) -> List[str]:
        self._ensure_loaded()
        matrix = self.genre_matrices.get(config.genre, self.global_matrix)
        if not matrix: return self._theory_fallback_progression(config, num_chords)

        current = config.starting_chord or weighted_choice({k: sum(v.values()) for k, v in matrix.items()})
        progression = [current]
        exploration = config.complexity / 10.0

        key_parts = (config.key or "C major").split()
        root_note = key_parts[0]
        scale_mode = key_parts[1] if len(key_parts) > 1 else "major"
        key_notes = get_scale_notes(root_note, scale_mode)

        # Pre-compute section boundary bar indices for tension shaping
        tension_multiplier = getattr(config, 'tension_multiplier', 0.0)
        boundary_bars: set = set()
        if tension_multiplier > 0 and structure:
            cumulative = 0
            for _, bars in structure:
                cumulative += bars
                boundary_bars.add(cumulative)

        for chord_idx in range(num_chords - 1):
            followers = matrix.get(current, {})
            if not followers:
                current = random.choice(list(matrix.keys()))
                progression.append(current)
                continue

            # Key-complexity boosting (original logic)
            if config.complexity < 7:
                working: dict = {}
                for chord, prob in followers.items():
                    c_root, c_quality = parse_chord_string(chord)
                    chord_midi = [(note_name_to_midi(c_root, 4) + i) % 12 for i in
                                  CHORD_INTERVALS.get(c_quality, [0, 4, 7])]
                    match_score = sum(1 for n in chord_midi if n in key_notes)
                    working[chord] = prob * (1.0 + match_score * (1.0 - exploration))
            else:
                working = followers

            # Tension / resolution matrix skewing
            if tension_multiplier > 0 and boundary_bars:
                if chord_idx in boundary_bars:
                    # Downbeat of new section: resolve to highest-probability chord
                    current = max(working, key=lambda c: working[c])
                else:
                    next_boundary = min(
                        (b for b in boundary_bars if b > chord_idx), default=999
                    )
                    bars_to_boundary = next_boundary - chord_idx
                    if bars_to_boundary <= 2:
                        tf = tension_multiplier * (1.0 - (bars_to_boundary - 1) / 2.0)
                        current = weighted_choice(_tension_skew_weights(working, tf))
                    else:
                        current = weighted_choice(working)
            else:
                current = weighted_choice(working)

            progression.append(current)
        return progression

    def _theory_fallback_progression(self, config: CompositionConfig,
                                      num_chords: int) -> List[str]:
        key = config.key or 'C major'
        parts = key.split()
        root = parts[0] if parts else 'C'
        is_minor = 'minor' in key.lower()

        root_midi = NOTE_TO_MIDI.get(root, 0)

        if is_minor:
            degrees = [
                (0, 'min7'), (3, 'maj7'), (5, 'min7'), (7, 'min7'),
                (8, 'maj7'), (10, 'maj7'), (2, 'dim7'),
            ]
        else:
            degrees = [
                (0, 'maj7'), (2, 'min7'), (4, 'min7'), (5, 'maj7'),
                (7, '7'), (9, 'min7'), (11, 'dim7'),
            ]

        common = [
            [0, 3, 4, 0],
            [0, 5, 3, 4],
            [0, 3, 5, 4],
            [5, 3, 0, 4],
            [0, 4, 5, 3],
        ]

        prog_pattern = random.choice(common)
        progression = []

        for _ in range(num_chords // len(prog_pattern) + 1):
            for idx in prog_pattern:
                if idx < len(degrees):
                    semi, quality = degrees[idx]
                    note_midi = (root_midi + semi) % 12
                    note_name = MIDI_TO_NOTE.get(note_midi, 'C')
                    progression.append(f"{note_name}{quality}")

        return progression[:num_chords]

    # ─────────────────────────────────────────────────────────────────
    #  SONG STRUCTURE GENERATION
    # ─────────────────────────────────────────────────────────────────

    def generate_structure(self, config: CompositionConfig) -> List[Tuple[str, int]]:
        bpm = config.bpm or 120
        target_bars = int(180 * bpm / 240)

        template = STRUCTURE_TEMPLATES.get(config.genre, STRUCTURE_TEMPLATES['pop'])
        raw_result = []

        for s, b in template:
            if config.complexity < 8:
                quantized_bars = max(4, (b // 4) * 4) if b >= 4 else (2 if b >= 2 else b)
                raw_result.append((s, quantized_bars))
            else:
                raw_result.append((s, b))

        if not raw_result:
            raw_result = [('intro', 4), ('verse', 16), ('outro', 8)]

        return self._apply_structural_sanity(raw_result)

        return self._apply_structural_sanity(result)

    # ─────────────────────────────────────────────────────────────────
    #  V4 CINEMATIC DRUM TRACK GENERATION
    # ─────────────────────────────────────────────────────────────────

    def generate_drum_track(self, config, structure, total_bars, seed_patterns=None):
        """
        Cinematic Drum Engine: Focuses on heavy toms, impacts, tribal grooves,
        and loop-safe probabilistic fills for epic game audio.
        """
        has_seed = seed_patterns and 'drum_patterns' in seed_patterns
        pdmx_kick = seed_patterns['drum_patterns'].get('kick', []) if has_seed else []
        pdmx_snare = seed_patterns['drum_patterns'].get('snare', []) if has_seed else []
        use_pdmx = len(pdmx_kick) > 0 or len(pdmx_snare) > 0

        complexity = config.complexity
        mutation = getattr(config, 'mutation', 0.0)
        notes = []
        h_amt = config.humanize_amount

        bar_offset = 0
        section_index = 0
        verse_count = 0

        for section_type, section_bars in structure:
            energy = self._section_energy(section_type)
            is_last_section = (section_index == len(structure) - 1)

            if section_type == 'verse': verse_count += 1

            if section_type == 'intro':
                for bar in range(section_bars):
                    bo = (bar_offset + bar) * 4
                    fade = (bar + 1) / max(1, section_bars)

                    if complexity > 4:
                        for i in range(0, 16, 4):
                            if random.random() < fade * 0.8:
                                notes.append((humanize(bo + i / 4, 0.01 * h_amt), 0.25,
                                              TOM_LOW, humanize_velocity(int(60 * fade), 8)))

            elif section_type == 'outro':
                for bar in range(section_bars):
                    bo = (bar_offset + bar) * 4
                    fade = 1.0 - (bar / max(1, section_bars))
                    if fade > 0.2 and bar % 2 == 0:
                        notes.append((humanize(bo, 0.01 * h_amt), 0.5,
                                      KICK, humanize_velocity(int(100 * fade), 10)))

            elif section_type == 'break':
                for bar in range(section_bars):
                    bo = (bar_offset + bar) * 4
                    if complexity > 5 and random.random() < 0.5:
                        notes.append((humanize(bo + 2.0, 0.01 * h_amt), 0.1, HIHAT_CLOSED, 40))

            elif section_type == 'build':
                for bar in range(section_bars):
                    bo = (bar_offset + bar) * 4
                    build_pct = (bar + 1) / section_bars

                    step = max(1, int(4 / (build_pct * 4)))
                    for i in range(0, 16, step):
                        if random.random() < build_pct * 0.9:
                            drum_choice = random.choice([TOM_MID, TOM_LOW])
                            notes.append((humanize(bo + i / 4, 0.008 * h_amt), 0.25,
                                          drum_choice, humanize_velocity(int(90 * build_pct), 10)))

                    if bar == section_bars - 1 and random.random() < 0.8:
                        self._add_cinematic_fill(notes, bo, complexity, 1.0, h_amt)

            else:
                pattern_shift = 1 if (section_type == 'verse' and verse_count > 1) else 0

                for bar in range(section_bars):
                    bo = (bar_offset + bar) * 4
                    is_first_bar = (bar == 0)

                    if is_first_bar and section_type in ('chorus', 'drop', 'climax'):
                        if random.random() < 0.4:
                            notes.append((bo, 0.5, KICK, humanize_velocity(115, 8)))
                            notes.append((bo, 0.5, TOM_LOW, humanize_velocity(110, 8)))

                    if use_pdmx:
                        k_pat = pdmx_kick[bar % len(pdmx_kick)] if pdmx_kick else [0] * 16
                        s_pat = pdmx_snare[bar % len(pdmx_snare)] if pdmx_snare else [0] * 16

                        for step in range(16):
                            time = bo + (step * 0.25)
                            if k_pat[step] > 0 and energy > 0.2:
                                notes.append((humanize(time, 0.01 * h_amt), 0.25, KICK,
                                              humanize_velocity(int(100 * energy), 8)))
                            if s_pat[step] > 0 and energy > 0.3:
                                drum_type = TOM_MID if complexity > 4 else SNARE
                                notes.append((humanize(time, 0.01 * h_amt), 0.25, drum_type,
                                              humanize_velocity(int(90 * energy), 10)))
                    else:
                        if energy > 0.3:
                            notes.append(
                                (humanize(bo, 0.01 * h_amt), 0.25, KICK, humanize_velocity(int(115 * energy), 8)))
                            if random.random() < (mutation * 0.8):
                                notes.append((humanize(bo + 2.5, 0.01 * h_amt), 0.25, KICK,
                                              humanize_velocity(int(90 * energy), 8)))

                        if complexity > 3:
                            for step in range(16):
                                pos = step * 0.25
                                if step in [2, 6, 7, 10, 14, 15]:
                                    hit_chance = energy * (0.9 if step in [6, 14] else 0.5)
                                    if random.random() < hit_chance:
                                        drum_type = TOM_MID if step in [7, 15] else TOM_HIGH
                                        vel_mult = 1.0 if step in [7, 15] else 0.6
                                        notes.append((humanize(bo + pos, 0.005 * h_amt), 0.2,
                                                      drum_type, humanize_velocity(int(95 * energy * vel_mult), 10)))

                        if energy > 0.5:
                            notes.append((humanize(bo + 2.0, 0.01 * h_amt), 0.25,
                                          SNARE, humanize_velocity(int(110 * energy), 5)))

                    if bar == section_bars - 1 and complexity > 2:
                        fill_chance = 0.2 + (mutation * 0.3)
                        if random.random() < fill_chance:
                            self._add_cinematic_fill(notes, bo, complexity, energy, h_amt)

            bar_offset += section_bars
            section_index += 1

        return notes

    def _add_cinematic_fill(self, notes, beat_offset, complexity, energy, h_amt):
        """Heavy, rolling orchestral toms instead of a standard snare fill."""
        if complexity <= 4:
            for pos in [12, 14]:
                notes.append((humanize(beat_offset + pos / 4, 0.01 * h_amt), 0.25,
                              TOM_LOW, humanize_velocity(int(100 * energy), 8)))
        else:
            fill_notes = [(8, TOM_HIGH), (10, TOM_HIGH), (11, TOM_MID),
                          (12, TOM_MID), (13, TOM_LOW), (14, TOM_LOW), (15, KICK)]
            for pos, drum in fill_notes:
                vel = 70 + (pos - 8) * 3
                if random.random() < 0.9:
                    notes.append((humanize(beat_offset + pos / 4, 0.008 * h_amt), 0.2,
                                  drum, humanize_velocity(min(127, int(vel * energy)), 10)))

            if random.random() < 0.3:
                notes.append((beat_offset + 3.95, 0.1, CRASH, humanize_velocity(100, 8)))

    # ─────────────────────────────────────────────────────────────────
    #  BASS TRACK GENERATION
    # ─────────────────────────────────────────────────────────────────

    def generate_bass_track(self, config: CompositionConfig,
                            chord_progression: List[str],
                            structure: List[Tuple[str, int]]) -> List[Tuple[float, float, int, int]]:
        if hasattr(self, 'bass_patterns') and self.bass_patterns.get('global'):
            return self._generate_bass_from_learned(config, chord_progression, structure)
        return self._generate_bass_fallback(config, chord_progression, structure)

    def _generate_bass_from_learned(self, config: CompositionConfig,
                                    chord_progression: List[str],
                                    structure: List[Tuple[str, int]]) -> List[Tuple[float, float, int, int]]:
        notes = []
        volume = config.tracks.get('bass', {}).get('volume', 0.8)
        base_vel = int(90 * volume)
        h_amt = config.humanize_amount
        mutation = getattr(config, 'mutation', 0.0)

        genre = config.genre
        if genre in self.bass_patterns['by_genre'] and self.bass_patterns['by_genre'][genre]:
            patterns = self.bass_patterns['by_genre'][genre]
        else:
            patterns = self.bass_patterns['global']

        if not patterns:
            return self._generate_bass_fallback(config, chord_progression, structure)

        bar_idx = 0
        chord_idx = 0
        current_pattern = random.choice(patterns)

        for section_type, section_bars in structure:
            energy = self._section_energy(section_type)

            for local_bar in range(section_bars):
                if chord_idx >= len(chord_progression):
                    chord_idx = chord_idx % max(1, len(chord_progression))

                bar_time = bar_idx * 4

                root, quality = parse_chord_string(chord_progression[chord_idx])
                root_midi = note_name_to_midi(root, 2)
                fifth = root_midi + 7

                switch_chance = 0.2 + mutation * 0.3
                if random.random() < switch_chance:
                    current_pattern = random.choice(patterns)

                working_pattern = self._mutate_pattern(current_pattern, mutation)

                section_energy = energy
                if section_type == 'intro':
                    fade = (local_bar + 1) / max(1, section_bars)
                    section_energy *= fade
                elif section_type == 'outro':
                    fade = 1.0 - (local_bar / max(1, section_bars))
                    section_energy *= fade
                elif section_type == 'break':
                    section_energy *= 0.3

                for step in range(16):
                    if working_pattern[step] == 1:
                        step_time = bar_time + (step / 4)

                        if step == 0:
                            midi_note = root_midi
                        elif step == 8:
                            midi_note = random.choice([root_midi, fifth])
                        elif step in [4, 12]:
                            midi_note = random.choice([root_midi, fifth, root_midi + 3])
                        else:
                            midi_note = random.choice([root_midi, fifth])

                        if mutation > 0.5 and random.random() < mutation * 0.3:
                            scale_notes = get_scale_notes(root, 'minor' if 'min' in quality else 'major', 2)
                            if scale_notes:
                                midi_note = random.choice(scale_notes)

                        while midi_note > 60:
                            midi_note -= 12
                        while midi_note < 28:
                            midi_note += 12

                        next_hit = None
                        for future_step in range(step + 1, 16):
                            if working_pattern[future_step] == 1:
                                next_hit = future_step
                                break

                        if next_hit:
                            duration = (next_hit - step) / 4 - 0.05
                        else:
                            duration = (16 - step) / 4 - 0.1

                        duration = max(0.1, min(duration, 3.8))

                        h_offset = (random.random() - 0.5) * 0.02 * h_amt
                        vel_variation = random.randint(-8, 8) * h_amt

                        velocity = int(base_vel * section_energy + vel_variation)
                        velocity = max(40, min(127, velocity))

                        if step == 0:
                            velocity = min(127, velocity + 10)

                        notes.append((step_time + h_offset, duration, midi_note, velocity))

                bar_idx += 1
                chord_idx += 1

        return notes

    def _mutate_pattern(self, pattern: List[int], mutation_rate: float) -> List[int]:
        if mutation_rate <= 0:
            return pattern

        mutated = list(pattern)
        for i in range(len(mutated)):
            if random.random() < mutation_rate * 0.3:
                if mutated[i] == 0:
                    if random.random() < mutation_rate * 0.5:
                        mutated[i] = 1
                else:
                    if random.random() < mutation_rate * 0.3:
                        mutated[i] = 0
                    elif random.random() < mutation_rate * 0.4:
                        new_pos = i + random.choice([-1, 1])
                        if 0 <= new_pos < len(mutated):
                            mutated[i] = 0
                            mutated[new_pos] = 1
        return mutated

    def _generate_bass_fallback(self, config: CompositionConfig,
                                chord_progression: List[str],
                                structure: List[Tuple[str, int]]) -> List[Tuple[float, float, int, int]]:
        notes = []
        complexity = config.complexity
        volume = config.tracks.get('bass', {}).get('volume', 0.8)
        base_vel = int(90 * volume)

        beat_pos = 0
        chord_idx = 0
        bar_count = 0

        for section_type, section_bars in structure:
            energy = self._section_energy(section_type)

            for bar in range(section_bars):
                if chord_idx >= len(chord_progression):
                    chord_idx = chord_idx % max(1, len(chord_progression))

                root, quality = parse_chord_string(chord_progression[chord_idx])
                root_midi = note_name_to_midi(root, 2)

                if energy < 0.2:
                    notes.append((
                        humanize(beat_pos, 0.01 * config.humanize_amount),
                        3.5, root_midi, humanize_velocity(int(base_vel * energy * 1.5), 8)
                    ))
                elif complexity <= 3:
                    for beat in range(4):
                        notes.append((
                            humanize(beat_pos + beat, 0.01 * config.humanize_amount),
                            0.9, root_midi, humanize_velocity(base_vel, 8)
                        ))
                elif complexity <= 6:
                    fifth = root_midi + 7
                    pattern = [
                        (0, root_midi, 0.9), (1, root_midi, 0.5),
                        (2, fifth, 0.9), (2.5, root_midi, 0.4),
                        (3, root_midi, 0.8),
                    ]
                    for offset, note, dur in pattern:
                        notes.append((
                            humanize(beat_pos + offset, 0.01 * config.humanize_amount),
                            dur, note, humanize_velocity(int(base_vel * energy), 8)
                        ))
                else:
                    chord_notes = get_chord_midi_notes(root, quality, 2)
                    scale = get_scale_notes(root, 'minor' if 'min' in quality else 'major', 2)

                    positions = [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5]
                    for pos in positions:
                        if random.random() < 0.7 * energy:
                            if pos in (0, 2):
                                note = root_midi
                            elif pos in (1, 3):
                                note = random.choice(chord_notes) if chord_notes else root_midi
                            else:
                                note = random.choice(scale) if scale else root_midi
                            notes.append((
                                humanize(beat_pos + pos, 0.012 * config.humanize_amount),
                                0.4, note, humanize_velocity(int(base_vel * energy), 10)
                            ))

                beat_pos += 4
                chord_idx += 1
                bar_count += 1

        return notes

    # ─────────────────────────────────────────────────────────────────
    #  CHORD TRACK GENERATION
    # ─────────────────────────────────────────────────────────────────

    def generate_chord_track(self, config: CompositionConfig,
                             chord_progression: List[str],
                             structure: List[Tuple[str, int]]) -> List[Tuple[float, float, int, int]]:
        notes = []
        complexity = config.complexity
        volume = config.tracks.get('chords', {}).get('volume', 0.7)
        base_vel = int(80 * volume)

        beat_pos = 0
        chord_idx = 0
        prev_voicing = None

        for section_type, section_bars in structure:
            energy = self._section_energy(section_type)

            for bar in range(section_bars):
                if chord_idx >= len(chord_progression):
                    chord_idx = chord_idx % max(1, len(chord_progression))

                root, quality = parse_chord_string(chord_progression[chord_idx])
                chord_notes = get_chord_midi_notes(root, quality, 4)

                if prev_voicing and len(chord_notes) > 0:
                    chord_notes = self._voice_lead(prev_voicing, chord_notes)

                prev_voicing = chord_notes

                if energy < 0.15:
                    for note in chord_notes:
                        notes.append((
                            humanize(beat_pos, 0.01),
                            3.8, note, humanize_velocity(int(base_vel * 0.5), 6)
                        ))
                elif complexity <= 3:
                    for note in chord_notes:
                        notes.append((
                            beat_pos, 3.8, note,
                            humanize_velocity(int(base_vel * energy), 6)
                        ))
                elif complexity <= 6:
                    for beat_offset in [0, 2]:
                        for note in chord_notes:
                            notes.append((
                                humanize(beat_pos + beat_offset, 0.015 * config.humanize_amount),
                                1.5, note,
                                humanize_velocity(int(base_vel * energy), 8)
                            ))
                else:
                    rhythm = [0, 0.75, 1.5, 2, 2.75, 3.5]
                    for i, offset in enumerate(rhythm):
                        if random.random() < 0.8 * energy:
                            note = chord_notes[i % len(chord_notes)]
                            notes.append((
                                humanize(beat_pos + offset, 0.02 * config.humanize_amount),
                                0.6, note,
                                humanize_velocity(int(base_vel * energy), 10)
                            ))

                beat_pos += 4
                chord_idx += 1

        return notes

    # ─────────────────────────────────────────────────────────────────
    #  LEAD MELODY GENERATION
    # ─────────────────────────────────────────────────────────────────

    def generate_lead_track(self, config: CompositionConfig,
                            chord_progression: List[str],
                            structure: List[Tuple[str, int]]) -> List[Tuple[float, float, int, int]]:
        if hasattr(self, 'lead_patterns') and self.lead_patterns.get('global'):
            return self._generate_lead_from_learned(config, chord_progression, structure)
        return self._generate_lead_fallback(config, chord_progression, structure)

    def _generate_lead_from_learned(self, config: CompositionConfig,
                                    chord_progression: List[str],
                                    structure: List[Tuple[str, int]]) -> List[Tuple[float, float, int, int]]:
        notes = []
        volume = config.tracks.get('lead', {}).get('volume', 0.75)
        base_vel = int(85 * volume)
        h_amt = config.humanize_amount
        complexity = config.complexity

        genre = config.genre
        if genre in self.lead_patterns['by_genre'] and self.lead_patterns['by_genre'][genre]:
            patterns = self.lead_patterns['by_genre'][genre]
        else:
            patterns = self.lead_patterns['global']

        if not patterns:
            return self._generate_lead_fallback(config, chord_progression, structure)

        key = config.key or 'C major'
        parts = key.split()
        root = parts[0] if parts else 'C'
        is_minor = 'minor' in key.lower()

        scale_choices = GENRE_SCALES.get(config.genre, ['major'])
        scale_type = random.choice(scale_choices)
        scale = get_scale_notes(root, scale_type, 5)

        bar_idx = 0
        chord_idx = 0
        current_pattern = random.choice(patterns)
        prev_note = None

        for section_type, section_bars in structure:
            energy = self._section_energy(section_type)

            if section_type in ('intro', 'outro', 'break') and complexity < 7:
                if random.random() < 0.5:
                    bar_idx += section_bars
                    chord_idx += section_bars
                    continue

            for local_bar in range(section_bars):
                if chord_idx >= len(chord_progression):
                    chord_idx = chord_idx % max(1, len(chord_progression))

                bar_time = bar_idx * 4

                c_root, c_quality = parse_chord_string(chord_progression[chord_idx])
                chord_notes = get_chord_midi_notes(c_root, c_quality, 5)

                if random.random() < 0.25:
                    current_pattern = random.choice(patterns)

                section_energy = energy
                if section_type == 'break':
                    section_energy *= 0.4
                elif section_type in ('chorus', 'drop', 'climax'):
                    section_energy *= 1.1

                for step in range(16):
                    if current_pattern[step] == 1:
                        step_time = bar_time + (step / 4)

                        if prev_note is None:
                            midi_note = random.choice(chord_notes)
                        else:
                            candidates = [n for n in scale if abs(n - prev_note) <= 4]
                            if not candidates:
                                candidates = scale
                            midi_note = random.choice(candidates)

                        while midi_note > 84:
                            midi_note -= 12
                        while midi_note < 60:
                            midi_note += 12

                        next_hit = None
                        for future_step in range(step + 1, 16):
                            if current_pattern[future_step] == 1:
                                next_hit = future_step
                                break

                        if next_hit:
                            duration = (next_hit - step) / 4 - 0.05
                        else:
                            duration = (16 - step) / 4 - 0.1

                        duration = max(0.1, min(duration, 2.0))

                        h_offset = (random.random() - 0.5) * 0.025 * h_amt
                        vel_variation = random.randint(-10, 10) * h_amt

                        velocity = int(base_vel * section_energy + vel_variation)
                        velocity = max(40, min(127, velocity))

                        notes.append((step_time + h_offset, duration, midi_note, velocity))
                        prev_note = midi_note

                bar_idx += 1
                chord_idx += 1

        return notes

    def _generate_lead_fallback(self, config: CompositionConfig,
                                chord_progression: List[str],
                                structure: List[Tuple[str, int]]) -> List[Tuple[float, float, int, int]]:
        notes = []
        complexity = config.complexity
        volume = config.tracks.get('lead', {}).get('volume', 0.75)
        base_vel = int(85 * volume)

        key = config.key or 'C major'
        parts = key.split()
        root = parts[0] if parts else 'C'
        is_minor = 'minor' in key.lower()

        scale_choices = GENRE_SCALES.get(config.genre, ['major'])
        scale_type = random.choice(scale_choices)
        scale = get_scale_notes(root, scale_type, 5)

        beat_pos = 0
        chord_idx = 0
        prev_note = None
        phrase_counter = 0

        for section_type, section_bars in structure:
            energy = self._section_energy(section_type)

            if section_type in ('intro', 'outro', 'break') and complexity < 7:
                beat_pos += section_bars * 4
                chord_idx += section_bars
                continue

            for bar in range(section_bars):
                if chord_idx >= len(chord_progression):
                    chord_idx = chord_idx % max(1, len(chord_progression))

                c_root, c_quality = parse_chord_string(chord_progression[chord_idx])
                chord_notes = get_chord_midi_notes(c_root, c_quality, 5)

                if complexity <= 3:
                    positions = [0, 2]
                elif complexity <= 6:
                    positions = [0, 1, 2, 3]
                else:
                    positions = [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5]

                for pos in positions:
                    if random.random() < 0.6 * energy:
                        if random.random() < 0.6:
                            note = random.choice(chord_notes)
                        else:
                            note = random.choice(scale) if scale else random.choice(chord_notes)

                        if prev_note and abs(note - prev_note) > 7:
                            candidates = [n for n in scale + chord_notes if abs(n - prev_note) <= 5]
                            if candidates:
                                note = random.choice(candidates)

                        dur_options = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0]
                        dur = random.choice(dur_options[:2 + complexity // 2])

                        phrase_counter += 1
                        if phrase_counter > 4 + complexity and random.random() < 0.4:
                            phrase_counter = 0
                            continue

                        notes.append((
                            humanize(beat_pos + pos, 0.02 * config.humanize_amount),
                            dur, note,
                            humanize_velocity(int(base_vel * energy), 12)
                        ))
                        prev_note = note

                beat_pos += 4
                chord_idx += 1

        return notes

    # ─────────────────────────────────────────────────────────────────
    #  PAD TRACK GENERATION
    # ─────────────────────────────────────────────────────────────────

    def generate_pad_track(self, config: CompositionConfig,
                           chord_progression,
                           structure: List[Tuple[str, int]],
                           seed_patterns=None):
        notes = []
        volume = config.tracks.get('pad', {}).get('volume', 0.6)
        base_vel = int(65 * volume)
        mutation = getattr(config, 'mutation', 0.0)

        has_seed = seed_patterns and 'pad_patterns' in seed_patterns
        pdmx_pad = seed_patterns['pad_patterns'] if has_seed else []

        beat_pos = 0
        chord_idx = 0

        for section_type, section_bars in structure:
            energy = self._section_energy(section_type)
            pad_energy = min(1.0, energy * 0.9 + 0.1)

            for bar in range(section_bars):
                if chord_idx >= len(chord_progression):
                    chord_idx = 0

                chord_data = chord_progression[chord_idx]
                if isinstance(chord_data, tuple):
                    root, quality = chord_data[3], chord_data[4]
                else:
                    root, quality = parse_chord_string(chord_data)

                chord_notes = get_chord_midi_notes(root, quality, 3)
                if not chord_notes:
                    chord_notes = [note_name_to_midi(root, 3)]

                bo = beat_pos + (bar * 4)

                if has_seed and pdmx_pad:
                    pattern = pdmx_pad[bar % len(pdmx_pad)]
                    for step in range(16):
                        if pattern[step] > 0:
                            for note in chord_notes[:3]:
                                time = bo + (step * 0.25)
                                final_note = note + 12 if (mutation > 0.6 and random.random() < 0.2) else note
                                notes.append((humanize(time, 0.01), 0.25, final_note,
                                              humanize_velocity(int(base_vel * pad_energy * 1.2), 6)))
                else:
                    if config.complexity < 4 or energy < 0.4:
                        for note in chord_notes[:3]:
                            notes.append((bo, 3.8, note, humanize_velocity(int(base_vel * pad_energy), 6)))
                    else:
                        swell_pattern = [0.8, 0.9, 1.1, 1.2, 1.3, 1.1, 0.9, 0.8]

                        for step in range(8):
                            time = bo + (step * 0.5)
                            swell = swell_pattern[step] + (mutation * 0.1)

                            for i, note in enumerate(chord_notes[:3]):
                                offset = i * 0.015
                                vel = humanize_velocity(int(base_vel * pad_energy * swell), 8)
                                notes.append((time + offset, 0.45, note, vel))

                chord_idx += 1
            beat_pos += section_bars * 4

        return notes

    # ─────────────────────────────────────────────────────────────────
    #  ARPEGGIO TRACK GENERATION
    # ─────────────────────────────────────────────────────────────────

    def generate_arp_track(self, config: CompositionConfig,
                           chord_progression: List[str],
                           structure: List[Tuple[str, int]]) -> List[Tuple[float, float, int, int]]:
        notes = []
        complexity = config.complexity
        volume = config.tracks.get('arp', {}).get('volume', 0.5)
        base_vel = int(70 * volume)

        arp_patterns = [
            [0, 1, 2, 1],
            [0, 1, 2, 3],
            [3, 2, 1, 0],
            [0, 2, 1, 3],
            [0, 1, 2, 3, 2, 1],
            [0, 0, 1, 2, 2, 3],
        ]
        arp_pattern = random.choice(arp_patterns[:1 + complexity // 2])

        if complexity <= 3:
            step = 1.0
        elif complexity <= 6:
            step = 0.5
        else:
            step = 0.25

        beat_pos = 0
        chord_idx = 0

        for section_type, section_bars in structure:
            energy = self._section_energy(section_type)

            if section_type in ('intro', 'outro') and complexity < 5:
                beat_pos += section_bars * 4
                chord_idx += section_bars
                continue

            for bar in range(section_bars):
                if chord_idx >= len(chord_progression):
                    chord_idx = chord_idx % max(1, len(chord_progression))

                root, quality = parse_chord_string(chord_progression[chord_idx])
                chord_notes = get_chord_midi_notes(root, quality, 5)
                if not chord_notes:
                    chord_notes = [60, 64, 67]

                pos = 0
                arp_idx = 0
                while pos < 4.0:
                    if random.random() < 0.85 * energy:
                        note_idx = arp_pattern[arp_idx % len(arp_pattern)]
                        note = chord_notes[note_idx % len(chord_notes)]
                        notes.append((
                            humanize(beat_pos + pos, 0.008 * config.humanize_amount),
                            step * 0.8,
                            note,
                            humanize_velocity(int(base_vel * energy), 8)
                        ))
                    pos += step
                    arp_idx += 1

                beat_pos += 4
                chord_idx += 1

        return notes

    # ─────────────────────────────────────────────────────────────────
    #  VOICE LEADING
    # ─────────────────────────────────────────────────────────────────

    def _voice_lead(self, prev_notes: List[int], new_notes: List[int]) -> List[int]:
        if not prev_notes or not new_notes:
            return new_notes

        result = []
        used = set()
        for prev in prev_notes:
            best = None
            best_dist = float('inf')
            for n in new_notes:
                for octave_shift in [-12, 0, 12]:
                    candidate = n + octave_shift
                    dist = abs(candidate - prev)
                    if dist < best_dist and candidate not in used:
                        best_dist = dist
                        best = candidate
            if best is not None:
                result.append(best)
                used.add(best)

        for n in new_notes:
            if n not in used and len(result) < len(new_notes):
                result.append(n)

        return result if result else new_notes

    # ─────────────────────────────────────────────────────────────────
    #  SECTION ENERGY MAPPING
    # ─────────────────────────────────────────────────────────────────

    def _section_energy(self, section_type: str) -> float:
        energy_map = {
            'intro': 0.3, 'verse': 0.55, 'pre_chorus': 0.65,
            'chorus': 0.85, 'drop': 1.0, 'bridge': 0.5,
            'break': 0.2, 'build': 0.7, 'climax': 1.0,
            'tension': 0.75, 'resolution': 0.5, 'outro': 0.25,
            'exposition': 0.6, 'development': 0.75,
            'recapitulation': 0.7, 'coda': 0.4,
            'variation': 0.65,
        }
        return energy_map.get(section_type, 0.5)

    # ─────────────────────────────────────────────────────────────────
    #  FUSED DRUM GENERATION (Cross-Genre)
    # ─────────────────────────────────────────────────────────────────

    def _generate_fused_drums(self, fusion_config, structure, config):
        KICK, SNARE, HIHAT_CLOSED, HIHAT_OPEN, CRASH = 36, 38, 42, 46, 49
        notes = []
        total_bars = sum(bars for _, bars in structure)
        complexity_float = config.complexity / 10.0
        h_amt = config.humanize_amount

        kick_patterns = self.fusion_engine.get_fused_patterns(fusion_config, 'kick', total_bars, complexity_float)
        snare_patterns = self.fusion_engine.get_fused_patterns(fusion_config, 'snare', total_bars, complexity_float)
        hihat_patterns = self.fusion_engine.get_fused_patterns(fusion_config, 'hihat', total_bars, complexity_float)

        bar_idx = 0
        for section_type, section_bars in structure:
            energy = self._section_energy(section_type)
            for local_bar in range(section_bars):
                if bar_idx >= len(kick_patterns): break
                bar_time = bar_idx * 4
                k_pat, s_pat, h_pat = kick_patterns[bar_idx], snare_patterns[bar_idx], hihat_patterns[bar_idx]

                for step in range(16):
                    step_time = bar_time + (step / 4)
                    h_off = (random.random() - 0.5) * 0.02 * h_amt
                    if k_pat[step] > 0:
                        notes.append((step_time + h_off, 0.25, KICK, max(40, min(127, int(80 * energy)))))
                    if s_pat[step] > 0:
                        notes.append((step_time + h_off, 0.25, SNARE, max(40, min(127, int(90 * energy)))))
                    if h_pat[step] > 0:
                        hat = HIHAT_OPEN if random.random() < 0.08 else HIHAT_CLOSED
                        notes.append((step_time + h_off, 0.15, hat, max(30, min(127, int(70 * energy)))))
                bar_idx += 1
        return notes

    def _generate_fused_bass(self, fusion_config, chord_progression, structure, config):
        notes = []
        total_bars = sum(bars for _, bars in structure)
        complexity_float = config.complexity / 10.0
        base_vel = int(90 * config.tracks.get('bass', {}).get('volume', 0.8))
        bass_patterns = self.fusion_engine.get_fused_patterns(fusion_config, 'bass', total_bars, complexity_float)

        bar_idx = 0
        for section_type, section_bars in structure:
            energy = self._section_energy(section_type)
            for local_bar in range(section_bars):
                if bar_idx >= len(bass_patterns): break
                chord_str = chord_progression[bar_idx % len(chord_progression)]
                root, _ = parse_chord_string(chord_str)
                root_midi = note_name_to_midi(root, 2)
                rhythm = bass_patterns[bar_idx]
                for step in range(16):
                    if rhythm[step] == 1:
                        notes.append((bar_idx * 4 + step / 4, 0.4, root_midi, max(40, int(base_vel * energy))))
                bar_idx += 1
        return notes

    def _generate_fused_lead(self, fusion_config, chord_progression, structure, config):
        notes = []
        total_bars = sum(bars for _, bars in structure)
        complexity_float = config.complexity / 10.0
        base_vel = int(85 * config.tracks.get('lead', {}).get('volume', 0.75))
        lead_patterns = self.fusion_engine.get_fused_patterns(fusion_config, 'synth', total_bars, complexity_float)

        bar_idx = 0
        for section_type, section_bars in structure:
            energy = self._section_energy(section_type)
            for local_bar in range(section_bars):
                if bar_idx >= len(lead_patterns): break
                chord_str = chord_progression[bar_idx % len(chord_progression)]
                root, _ = parse_chord_string(chord_str)
                root_midi = note_name_to_midi(root, 5)
                rhythm = lead_patterns[bar_idx]
                for step in range(16):
                    if rhythm[step] == 1:
                        notes.append((bar_idx * 4 + step / 4, 0.3, root_midi, max(40, int(base_vel * energy))))
                bar_idx += 1
        return notes

    # ─────────────────────────────────────────────────────────────────
    #  DRUM SPLITTING (01_Kick / 02_Percussion)
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _split_drums(drum_notes):
        """Separate kick (MIDI 36) from all other percussion notes."""
        kick  = [n for n in drum_notes if n[2] == KICK]
        perc  = [n for n in drum_notes if n[2] != KICK]
        return kick, perc

    # ─────────────────────────────────────────────────────────────────
    #  MAIN COMPOSITION METHOD
    # ─────────────────────────────────────────────────────────────────

    def compose(self, config: CompositionConfig) -> dict:
        self._ensure_loaded()
        if config.seed_value is not None: random.seed(config.seed_value)

        if config.bpm is None: config.bpm = random.uniform(*GENRE_BPM.get(config.genre, (100, 130)))
        if config.key is None: config.key = f"{random.choice(['C', 'D', 'E', 'F', 'G', 'A', 'Bb'])} {random.choice(['major', 'minor'])}"

        structure = list(config.structure_override) if config.structure_override else self.generate_structure(config)
        total_bars = sum(b for _, b in structure)
        chord_progression = self.generate_chord_progression(config, total_bars + 4, structure=structure)

        fusion_config = getattr(config, 'fusion', None)
        using_fusion = fusion_config is not None and self.fusion_engine is not None

        inst_map = GENRE_INSTRUMENTS.get(config.genre, {})

        # ── Generate core tracks ──────────────────────────────────────
        def _gen(t_name, func_name):
            if not config.tracks.get(t_name, {}).get('enabled', False):
                return []
            gen_fn = getattr(self, func_name)
            if t_name == 'drums':
                if using_fusion:
                    return self._generate_fused_drums(fusion_config, structure, config)
                return gen_fn(config, structure, total_bars)
            if using_fusion and t_name in ('bass', 'lead'):
                return getattr(self, f"_generate_fused_{t_name}")(
                    fusion_config, chord_progression, structure, config)
            return gen_fn(config, chord_progression, structure)

        raw_drums  = _gen('drums', 'generate_drum_track')
        raw_bass   = _gen('bass',  'generate_bass_track')
        raw_chords = _gen('chords','generate_chord_track')
        raw_lead   = _gen('lead',  'generate_lead_track')
        raw_pad    = _gen('pad',   'generate_pad_track')

        # ── Rhythmic decoupling on the lead / melody track ───────────
        melody_notes = raw_lead
        if self.rhythmic_decoupler and melody_notes:
            melody_notes = self.rhythmic_decoupler.apply(
                seed_notes   = raw_lead,
                target_genre = config.genre,
                tpqn         = 480,
                total_beats  = float(total_bars * 4),
            )

        # ── Split drums into kick + percussion ───────────────────────
        kick_notes, perc_notes = self._split_drums(raw_drums)

        # ── Scale info for texture inversion ────────────────────────
        key_parts  = (config.key or "C major").split()
        root_note  = key_parts[0]
        scale_mode = key_parts[1] if len(key_parts) > 1 else "major"
        scale_choices = GENRE_SCALES.get(config.genre, ['major'])
        chosen_scale  = scale_choices[0] if scale_mode not in scale_choices else scale_mode
        scale_notes   = get_scale_notes(root_note, chosen_scale, 4)
        # Root MIDI pitch for texture anchor (one octave above bass)
        from src.composition.genre_constants import note_name_to_midi as _n2m
        anchor_pitch  = _n2m(root_note, 5)

        # ── Omni layers (07–10) ───────────────────────────────────────
        omni_tracks: dict = {}
        if self.omni_layer_gen:
            omni_tracks = self.omni_layer_gen.generate(
                melody_notes      = melody_notes,
                chord_progression = chord_progression,
                structure         = structure,
                scale_notes       = scale_notes,
                genre             = config.genre,
                chord_notes_fn    = get_chord_midi_notes,
                parse_chord_fn    = parse_chord_string,
                anchor_pitch      = anchor_pitch,
                arp_volume        = config.tracks.get('arp', {}).get('volume', 0.5),
                stab_volume       = 0.8,
                fx_volume         = 0.9,
            )

        # ── Assemble final 10-track output ───────────────────────────
        tracks = {
            '01_Kick':     kick_notes,
            '02_Percussion': perc_notes,
            '03_Bass':     raw_bass,
            '04_Melody':   melody_notes,
            '05_Chords':   raw_chords,
            '06_Pad':      raw_pad,
            '07_Arp':      omni_tracks.get('07_Arp',     []),
            '08_Stabs':    omni_tracks.get('08_Stabs',   []),
            '09_Texture':  omni_tracks.get('09_Texture', []),
            '10_FX':       omni_tracks.get('10_FX',      []),
        }

        track_info = {
            '01_Kick':       {'channel': 9, 'program': 0},
            '02_Percussion': {'channel': 9, 'program': 0},
            '03_Bass':       {'channel': 0, 'program': config.tracks.get('bass',   {}).get('instrument') or inst_map.get('bass',   33)},
            '04_Melody':     {'channel': 1, 'program': config.tracks.get('lead',   {}).get('instrument') or inst_map.get('lead',   80)},
            '05_Chords':     {'channel': 2, 'program': config.tracks.get('chords', {}).get('instrument') or inst_map.get('chords',  0)},
            '06_Pad':        {'channel': 3, 'program': config.tracks.get('pad',    {}).get('instrument') or inst_map.get('pad',    88)},
            '07_Arp':        {'channel': 4, 'program': inst_map.get('arp', 80)},
            '08_Stabs':      {'channel': 5, 'program': inst_map.get('chords', 0)},
            '09_Texture':    {'channel': 6, 'program': inst_map.get('pad',   88)},
            '10_FX':         {'channel': 7, 'program': 0},
        }

        return {
            'config': {'genre': config.genre, 'bpm': round(config.bpm, 1), 'key': config.key,
                       'complexity': config.complexity},
            'structure': structure,
            'chord_progression': chord_progression[:total_bars],
            'total_bars': total_bars,
            'duration_seconds': round(total_bars * 4 * 60 / config.bpm, 2),
            'tracks': tracks,
            'track_info': track_info
        }

    def generate_batch(self, count: int, genre: str, base_output_dir: str = "batch_output", active_tracks: dict = None):
        os.makedirs(base_output_dir, exist_ok=True)

        for i in range(count):
            comp_val = random.randint(4, 10)
            sync_val = random.randint(3, 10)
            mut_val = random.uniform(0.3, 0.8)

            config = CompositionConfig(
                genre=genre,
                bpm=random.uniform(80, 130),
                complexity=comp_val,
                mutation=mut_val,
                seed_value=random.randint(0, 999999)
            )
            setattr(config, 'syncopation', sync_val)

            if active_tracks is not None:
                config.tracks = active_tracks
            else:
                config.tracks['arp']['enabled'] = True

            composition = self.compose(config)

            key_str = composition['config']['key'].replace(' ', '')
            filename = f"V4_{genre}_{i + 1}_{key_str}_C{comp_val}_M{int(mut_val * 10)}.mid"

            self.export_midi(composition, os.path.join(base_output_dir, filename))
            print(f"V4 BATCH: {i + 1}/{count} | Key: {key_str} | Complexity: {comp_val}")

        print(f"V4 BATCH COMPLETE: {count} tracks exported")

    # ─────────────────────────────────────────────────────────────────
    #  MIDI EXPORT
    # ─────────────────────────────────────────────────────────────────

    def export_midi(self, composition: dict, filepath: str) -> str:
        if not MIDI_AVAILABLE: return ""
        midi = MIDIFile(len(composition['tracks']), file_format=1)

        current_bar = 0
        for section_type, section_bars in composition['structure']:
            marker_time = current_bar * 4
            midi.addText(0, marker_time, section_type.upper())
            current_bar += section_bars

        for i, (name, events) in enumerate(composition['tracks'].items()):
            info = composition['track_info'].get(name, {})
            midi.addTempo(i, 0, composition['config']['bpm'])

            events.sort(key=lambda x: x[0])

            channel = info.get('channel', 0)
            is_drum = (channel == 9)
            seen_notes: set = set()
            # Track when each pitch last had a note_off, to prevent midiutil
            # deInterleaveNotes from encountering orphaned note_off events.
            active_end: dict = {}   # pitch → current note_off time

            for idx, e in enumerate(events):
                time, duration, pitch, vel = e[0], e[1], e[2], e[3]

                if time < 0 or pitch < 0 or pitch > 127:
                    continue
                vel = max(1, min(127, int(vel)))

                # Clip duration against the next note with the same pitch
                for future_e in events[idx + 1:]:
                    if future_e[2] == pitch and future_e[0] < (time + duration):
                        duration = max(0.05, future_e[0] - time - 0.01)
                        break

                duration = max(0.05, duration)

                # For drums: prevent overlap with still-active same-pitch note
                if is_drum and active_end.get(pitch, -1.0) > time:
                    continue   # skip: previous hit hasn't ended yet

                # Dedup key: for drums snap to 16th-note grid (0.25 beats)
                if is_drum:
                    key_time = round(time / 0.25) * 0.25
                else:
                    key_time = round(time, 3)

                note_key = (key_time, pitch)
                if note_key not in seen_notes:
                    seen_notes.add(note_key)
                    active_end[pitch] = time + duration
                    midi.addNote(i, channel, pitch, time, duration, vel)

        with open(filepath, 'wb') as f:
            midi.writeFile(f)
        return filepath

    def _apply_structural_sanity(self, structure: List[Tuple[str, int]]) -> List[Tuple[str, int]]:
        if not structure:
            return [('intro', 4), ('verse', 16), ('outro', 8)]

        intros = [s for s in structure if s[0] == 'intro']
        outros = [s for s in structure if s[0] == 'outro']
        mains = [s for s in structure if s[0] not in ['intro', 'outro', 'build', 'break']]
        utilities = [s for s in structure if s[0] in ['build', 'break', 'bridge']]

        sanitized = []

        if intros:
            sanitized.append(intros[0])
        else:
            sanitized.append(('intro', 4))

        if not mains:
            sanitized.append(('verse', 16))
        else:
            for s in structure:
                if s[0] not in ['intro', 'outro']:
                    sanitized.append(s)

        if sanitized[-1][0] != 'outro':
            if outros:
                sanitized.append(outros[-1])
            else:
                sanitized.append(('outro', 8))

        return sanitized


def quick_compose(genre='pop', bpm=None, key=None, complexity=5,
                  starting_chord=None, output_path='generated_song.mid',
                  seeds_dir='seeds') -> str:
    engine = CompositionEngine(seeds_dir)

    config = CompositionConfig(
        genre=genre,
        bpm=bpm,
        key=key,
        complexity=complexity,
        starting_chord=starting_chord,
    )

    composition = engine.compose(config)
    return engine.export_midi(composition, output_path)


if __name__ == "__main__":
    quick_compose(genre='hiphop', complexity=4)
