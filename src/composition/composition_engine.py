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
    GENRE_DRUM_PATTERNS, GENRE_SWING, GENRE_BPM, GENRE_SCALES, GENRE_INSTRUMENTS, STRUCTURE_TEMPLATES,
    note_name_to_midi, get_chord_midi_notes, parse_chord_string, get_scale_notes,
    weighted_choice, humanize, humanize_velocity,
)
from src.composition.composition_config import CompositionConfig
from src.composition.performance_humanizer import (
    PhraseVelocityMapper, GateLengthHumanizer, BassVelocityProfile,
)
from src.composition.trap_cipher import (
    HiHatRatchetEngine, EightOhEightGlider, EightOhEightOctaveLeap,
    SilenceMatrix, AuxPercussionLayer,
)

try:
    from src.composition import intro_archetype_registry as _intro_registry
    _INTRO_REGISTRY_AVAILABLE = True
except ImportError:
    _intro_registry = None        # type: ignore
    _INTRO_REGISTRY_AVAILABLE = False
from src.composition.edm_cipher import (
    SidechainMatrix, StochasticBuildUp, PreDropVoid,
    AntiDropFakeOut, PolyrhythmicFilterSweep,
)


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


# ─── HARMONIC GOVERNOR ───────────────────────────────────────────────────────

_HG_NOTE_TO_PC: Dict[str, int] = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3,
    'E': 4, 'Fb': 4, 'F': 5, 'E#': 5, 'F#': 6, 'Gb': 6,
    'G': 7, 'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10,
    'B': 11, 'Cb': 11,
}

# ─── VOCAL SPACE MASK ────────────────────────────────────────────────────────
_VOCAL_MASK_LOW      = 60   # C4 (Middle C) — start of exclusion zone
_VOCAL_MASK_HIGH     = 84   # C6 — end of exclusion zone (exclusive)
_VOCAL_MASK_SECTIONS = frozenset({'verse', 'hook', 'chorus', 'pre_chorus'})


class HarmonicGovernor:
    """
    JSON-driven harmonic filter.

    Resolves dissonant MIDI notes to the nearest allowed pitch class as
    defined in harmonic_governor.json, with a passing-note exception for
    rhythmically weak 16th-note off-beats.

    Parameters
    ----------
    json_path : optional path override; defaults to harmonic_governor.json
                at the project root.
    """

    def __init__(self, json_path: Optional[str] = None):
        path = (
            Path(json_path)
            if json_path
            else Path(__file__).parent.parent.parent / 'config' / 'harmonic_governor.json'
        )
        with open(path, 'r', encoding='utf-8') as fh:
            self._data = json.load(fh)

    # ------------------------------------------------------------------
    def _get_allowed_pcs(self, chord_type: str, use_7th_chords: bool) -> set:
        """Return the set of allowed pitch classes for the given chord string."""
        ct = chord_type.strip()

        def _pcs(names):
            return {_HG_NOTE_TO_PC[n] for n in names if n in _HG_NOTE_TO_PC}

        # Explicit maj7
        if ct.endswith('maj7'):
            names = self._data['major_7th'].get(ct)
            if names:
                return _pcs(names)

        # Explicit minor 7th  (but not maj7)
        if ct.endswith('m7') and not ct.endswith('maj7'):
            names = self._data['minor_7th'].get(ct)
            if names:
                return _pcs(names)

        # Minor triad (ends with 'm', not 'm7'/'maj7')
        if ct.endswith('m') and not ct.endswith('m7') and not ct.endswith('maj7'):
            if use_7th_chords:
                names = self._data['minor_7th'].get(ct + '7')
                if names:
                    return _pcs(names)
            names = self._data['minor_triads'].get(ct)
            if names:
                return _pcs(names)

        # Major triad (plain root, e.g. 'C', 'F#')
        if use_7th_chords:
            names = self._data['major_7th'].get(ct + 'maj7')
            if names:
                return _pcs(names)
        names = self._data['major_triads'].get(ct)
        if names:
            return _pcs(names)

        return set()  # unknown chord — no filtering applied

    # ------------------------------------------------------------------
    @staticmethod
    def _is_weak_beat(beat_position: float) -> bool:
        """True for off-beat 16th-note positions (0.25, 0.75, 1.25 … ±0.05 tolerance)."""
        return abs((beat_position % 0.5) - 0.25) < 0.05

    # ------------------------------------------------------------------
    def resolve(
        self,
        note: int,
        chord_type: str,
        beat_position: float,
        use_7th_chords: bool = False,
    ) -> int:
        """
        Return note unchanged if consonant or on a passing-note beat.
        Otherwise transpose to the nearest semitone in the chord's allowed set.

        Parameters
        ----------
        note          : MIDI pitch to evaluate.
        chord_type    : chord string as it appears in the progression
                        (e.g. 'Am', 'Cmaj7', 'G', 'Dm7').
        beat_position : absolute beat position in the song (used for
                        the weak-beat passing-note exception).
        use_7th_chords: when True, plain triads are promoted to their
                        7th-chord allowed set (major→maj7, minor→m7).
        """
        allowed_pcs = self._get_allowed_pcs(chord_type, use_7th_chords)
        if not allowed_pcs or note % 12 in allowed_pcs:
            return note
        if self._is_weak_beat(beat_position):
            return note  # passing-note exception — let it through

        # Expand outward by semitone until we hit an allowed pitch class
        for delta in range(1, 13):
            lo, hi = note - delta, note + delta
            lo_ok = lo % 12 in allowed_pcs
            hi_ok = hi % 12 in allowed_pcs
            if lo_ok and hi_ok:
                return lo   # tie-break: prefer lower (voice-leading convention)
            if lo_ok:
                return lo
            if hi_ok:
                return hi
        return note  # fallback — no match within an octave


class CompositionEngine:
    """
    The heart of the system: generates complete multi-track songs
    from musical DNA seeds.
    """

    def __init__(self, seeds_dir: str = "seeds", vocal_mask: bool = False):
        self.seeds_dir = Path(seeds_dir)
        self.seeds = []
        self.genre_seeds = defaultdict(list)
        self.genre_matrices = {}
        self.global_matrix = {}
        self._loaded = False
        self.pattern_generator = None
        self.fusion_engine = None
        self.arrangement_engine = None
        self._hgov = None  # lazy-loaded HarmonicGovernor
        self.vocal_mask = vocal_mask

    def _get_hgov(self) -> Optional['HarmonicGovernor']:
        """Return the shared HarmonicGovernor, loading it once on first call."""
        if self._hgov is None:
            try:
                self._hgov = HarmonicGovernor()
            except Exception as e:
                print(f"HarmonicGovernor unavailable: {e}")
                self._hgov = False  # sentinel: load failed — don't retry
        return self._hgov if self._hgov else None

    def _apply_vocal_mask(
        self,
        note: int,
        section_type: str,
        config: 'CompositionConfig',
    ) -> Optional[int]:
        """
        Enforce the Vocal Space Mask for melody and arpeggiator tracks.

        When active, MIDI notes in the C4–C6 range (60–83) are forbidden
        during primary vocal sections ('verse', 'hook').  The note is first
        attempted one octave lower; if that would fall below C2 (MIDI 36)
        the note is dropped entirely (returns None).

        Bass and pad/chord generators must NOT call this method — they sit
        naturally below the exclusion zone and should remain untouched.
        """
        if not getattr(config, 'vocal_mask', False):
            return note
        if section_type not in _VOCAL_MASK_SECTIONS:
            return note
        if _VOCAL_MASK_LOW <= note < _VOCAL_MASK_HIGH:
            transposed = note
            while transposed >= _VOCAL_MASK_LOW:  # keep shifting until below C4
                transposed -= 12
            return transposed if transposed >= 36 else None  # drop below C2
        return note

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
                # ±4-bar jitter so tracks of the same genre have different lengths
                if quantized_bars >= 8:
                    quantized_bars = max(4, quantized_bars + random.choice([-4, 0, 0, 0, 4]))
                raw_result.append((s, quantized_bars))
            else:
                raw_result.append((s, b))

        if not raw_result:
            raw_result = [('intro', 4), ('verse', 16), ('outro', 8)]

        # Intro entropy injection: every 5th seed gets a non-template intro length.
        # Ensures 20 % of tracks open with a distinctly different bar count (4/8/12/16).
        seed_val = getattr(config, 'seed_value', 0) or 0
        if seed_val % 5 == 0:
            raw_result = [
                (s, random.choice([4, 8, 12, 16]) if s == 'intro' else b)
                for s, b in raw_result
            ]

        # Outro entropy injection: every 7th seed gets a non-template outro length.
        # Primes 5 and 7 are coprime so intro and outro mutations don't always coincide.
        if seed_val % 7 == 0:
            raw_result = [
                (s, random.choice([4, 8, 12]) if s == 'outro' else b)
                for s, b in raw_result
            ]

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
        mutation   = getattr(config, 'mutation', 0.0)
        tension    = getattr(config, 'tension_multiplier', 0.5)
        bpm        = config.bpm or 120.0
        notes      = []
        h_amt      = config.humanize_amount

        # Pick one base variant, then apply per-track groove morphing seeded by seed_value.
        # This gives every track a unique drum pattern while keeping the genre feel.
        g_pats = GENRE_DRUM_PATTERNS.get(config.genre, [{'kick': [], 'snare': [], 'hihat': []}])
        g_pat       = random.choice(g_pats)
        kick_steps, snare_steps, hihat_steps = self._apply_groove_variation(
            g_pat.get('kick',  []),
            g_pat.get('snare', []),
            g_pat.get('hihat', []),
            complexity, mutation, config.genre,
        )

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
                for bar in range(section_bars):
                    absolute_bar    = bar_offset + bar
                    bo              = absolute_bar * 4
                    is_first_bar    = (bar == 0)
                    is_phrase_accent = (absolute_bar % 4 == 0)   # accent every 4 bars
                    occupied_steps: set = set()                   # for ghost-note injection

                    # Section-opening crash+kick for chorus/drop/climax
                    if is_first_bar and section_type in ('chorus', 'drop', 'climax'):
                        if random.random() < 0.4:
                            notes.append((bo, 0.5, KICK,
                                          self._drum_velocity(115, energy, tension, accent=True)))
                            notes.append((bo, 0.5, TOM_LOW,
                                          self._drum_velocity(100, energy, tension)))

                    if use_pdmx:
                        k_pat = pdmx_kick[bar % len(pdmx_kick)] if pdmx_kick else [0] * 16
                        s_pat = pdmx_snare[bar % len(pdmx_snare)] if pdmx_snare else [0] * 16
                        for step in range(16):
                            beat_t = bo + step * 0.25
                            if k_pat[step] > 0 and energy > 0.2:
                                t   = self._micro_humanize(beat_t, bpm)
                                vel = self._drum_velocity(100, energy, tension,
                                                          accent=(is_phrase_accent and step == 0))
                                notes.append((t, 0.25, KICK, vel))
                                occupied_steps.add(step)
                            if s_pat[step] > 0 and energy > 0.3:
                                t   = self._micro_humanize(beat_t, bpm)
                                vel = self._drum_velocity(90, energy, tension)
                                drum_type = TOM_MID if complexity > 4 else SNARE
                                notes.append((t, 0.25, drum_type, vel))
                                occupied_steps.add(step)
                    else:
                        swing_pct = GENRE_SWING.get(config.genre, 0.50)
                        swing_off = (swing_pct - 0.5) * 0.5   # beat offset for odd 16th steps

                        # ── Kick ──────────────────────────────────────────────────
                        kick_hit_steps: set = set()
                        for step, base_vel in kick_steps:
                            if energy > 0.3 and random.random() > mutation * 0.15:
                                is_beat1   = (step == 0)
                                is_accent  = is_phrase_accent and is_beat1
                                if is_beat1:
                                    vel = random.randint(115, 127) if is_accent else random.randint(110, 122)
                                elif step % 4 == 0:
                                    vel = self._drum_velocity(base_vel, energy, tension,
                                                              jitter=10, accent=False)
                                else:
                                    vel = random.randint(85, 98)
                                t_raw = bo + step * 0.25
                                if step % 2 == 1:
                                    t_raw += swing_off
                                t = self._micro_humanize(t_raw, bpm)
                                notes.append((t, 0.25, KICK, vel))
                                occupied_steps.add(step)
                                kick_hit_steps.add(step)

                        # ── Snare (base pattern) ───────────────────────────────────
                        for step, base_vel in snare_steps:
                            if energy > 0.3:
                                vel   = self._drum_velocity(base_vel, energy, tension)
                                t_raw = bo + step * 0.25
                                if step % 2 == 1:
                                    t_raw += swing_off
                                t = self._micro_humanize(t_raw, bpm)
                                notes.append((t, 0.25, SNARE, vel))
                                occupied_steps.add(step)

                        # Per-bar ghost snare (25% chance, never on main beats)
                        if random.random() < 0.25:
                            ghost_cands = [s for s in range(16)
                                           if s not in occupied_steps
                                           and s not in (0, 4, 8, 12)]
                            if ghost_cands:
                                gs    = random.choice(ghost_cands)
                                t_raw = bo + gs * 0.25
                                if gs % 2 == 1:
                                    t_raw += swing_off
                                tg = self._micro_humanize(t_raw, bpm, max_seconds=0.004)
                                notes.append((tg, 0.08, SNARE, random.randint(25, 45)))

                        # Trap/Phonk: 32nd-note snare roll at phrase end
                        if (config.genre in ('trap', 'phonk')
                                and bar % 4 == 3 and random.random() < 0.30):
                            for sub in (14, 15):
                                if sub not in occupied_steps:
                                    tg = self._micro_humanize(
                                        bo + sub * 0.25, bpm, max_seconds=0.003)
                                    notes.append((tg, 0.06, SNARE,
                                                  random.randint(55, 75)))

                        # ── Hi-hat (choked on kick steps) ─────────────────────────
                        for step, base_vel in hihat_steps:
                            if int(step) in kick_hit_steps:
                                continue   # inter-layer choke
                            if energy > 0.2:
                                hh_type = (HIHAT_OPEN
                                           if complexity > 6 and step % 8 == 4
                                           and random.random() < 0.3
                                           else HIHAT_CLOSED)
                                vel   = self._drum_velocity(base_vel, energy, tension)
                                t_raw = bo + step * 0.25
                                if int(step) % 2 == 1:
                                    t_raw += swing_off
                                t = self._micro_humanize(t_raw, bpm, max_seconds=0.005)
                                notes.append((t, 0.15, hh_type, vel))

                        # ── Ghost note injection (fills acoustic pocket) ───────────
                        self._inject_ghost_notes(notes, occupied_steps, bo, bpm, energy)

                        # ── Hi-Hat Ratchet (Trap / Hip-Hop) ───────────────────────
                        if config.genre in ('trap', 'hiphop', 'phonk'):
                            ratchet = HiHatRatchetEngine.maybe_roll(absolute_bar, bo, bpm)
                            if ratchet:
                                # Replace hi-hats that fall inside the ratchet window
                                roll_start = ratchet[0][0]
                                notes = [n for n in notes
                                         if not (n[2] in (HIHAT_CLOSED, HIHAT_OPEN)
                                                 and roll_start <= n[0] < bo + 4.0)]
                                notes.extend(ratchet)

                        # ── Auxiliary Percussion (Trap / Hip-Hop) ─────────────────
                        if config.genre in ('trap', 'hiphop', 'phonk'):
                            aux = AuxPercussionLayer.generate(
                                bo,
                                {s for s, _ in kick_steps} | {s for s, _ in snare_steps},
                                bpm,
                            )
                            notes.extend(aux)

                    if bar == section_bars - 1 and complexity > 2:
                        fill_chance = 0.2 + (mutation * 0.3)
                        if random.random() < fill_chance:
                            self._add_cinematic_fill(notes, bo, complexity, energy, h_amt)

            bar_offset += section_bars
            section_index += 1

        # ── Silence Matrix — mute drums at 8-bar phrase drops ─────────────────
        if config.genre in ('trap', 'hiphop', 'phonk'):
            _drop_seed  = getattr(config, 'seed_value', None) or abs(hash(config.genre))
            _drop_zones = SilenceMatrix.compute_zones(total_bars, seed=_drop_seed)
            notes       = SilenceMatrix.apply(notes, _drop_zones)

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

    # ── Commercial-grade drum helpers ────────────────────────────────────────

    def _micro_humanize(self, beat_pos: float, bpm: float,
                        max_seconds: float = 0.005) -> float:
        """±max_seconds timing jitter converted to beat units (deterministic via seed)."""
        max_beats = max_seconds * (bpm / 60.0)
        return beat_pos + random.uniform(-max_beats, max_beats)

    def _drum_velocity(self, base: int, energy: float, tension: float,
                       jitter: int = 15, accent: bool = False) -> int:
        """
        Commercial-grade velocity: base ±15, energy-scaled, tension-boosted.
        Forced accent (115-125) on 4-bar phrase downbeats.
        Tension linkage: higher tension → higher average velocity for hihats/snares.
        """
        if accent:
            return random.randint(115, 125)
        vel  = base + random.randint(-jitter, jitter)   # base ±15
        vel  = int(vel * max(0.25, energy))             # energy scaling
        vel += int(tension * 12)                        # tension boost (0→0, 1.5→+18)
        return max(20, min(127, vel))

    def _inject_ghost_notes(self, notes: list, occupied_steps: set,
                            bo: float, bpm: float, energy: float,
                            probability: float = 0.15) -> None:
        """
        Ghost note injection: low-velocity rimshot fills (vel 30-50) in the
        rhythmic gaps between main kick and snare hits.
        Beat 1 (step 0) and snare anchors (steps 4, 12) are never ghosted.
        """
        if energy < 0.3:
            return
        for step in range(1, 16):
            if step in occupied_steps or step in (4, 12):
                continue
            if random.random() < probability:
                t   = self._micro_humanize(bo + step * 0.25, bpm, max_seconds=0.01)
                vel = random.randint(30, 50)
                notes.append((t, 0.08, RIMSHOT, vel))

    def _apply_groove_variation(self, kick_steps, snare_steps, hihat_steps,
                               complexity, mutation, genre: str = 'pop'):
        """
        Morphs a base drum pattern — enforces density limits and applies hi-hat choking.
        NEVER adds kick hits; density can only stay equal or decrease.

        Transformations:
          Kick  : prune to hard_max via _KICK_DENSITY; shift 1 secondary hit ±1 step
          Hihat : drop/add steps; choke any hihat that coincides with a kick step
          Snare : passed through unchanged (ghost notes injected per-bar in main loop)
        """
        _ANCHOR_KICKS  = frozenset({0})
        _ANCHOR_SNARES = frozenset({4, 8, 12})

        lo, hi = self._KICK_DENSITY.get(genre, self._KICK_DENSITY_DEFAULT)
        hard_max = random.randint(lo, hi)

        # ── Kick: enforce density limit first, then shift ─────────────────────
        kick = list(kick_steps)
        kick.sort(key=lambda x: x[0])

        if len(kick) > hard_max:
            anchors     = [(s, v) for s, v in kick if s in _ANCHOR_KICKS]
            non_anchors = [(s, v) for s, v in kick if s not in _ANCHOR_KICKS]
            allowed_non = max(0, hard_max - len(anchors))
            kick = anchors + non_anchors[:allowed_non]
            kick.sort(key=lambda x: x[0])

        kick_positions = {s for s, _ in kick}

        # Shift one non-anchor secondary kick ±1 step (count stays the same)
        secondary = [(i, s, v) for i, (s, v) in enumerate(kick)
                     if s not in _ANCHOR_KICKS and s not in (4, 8, 12)]
        if secondary and random.random() < 0.6:
            idx, old_step, vel = random.choice(secondary)
            new_step = old_step + random.choice([-1, 1])
            if (0 < new_step < 16
                    and new_step not in kick_positions
                    and new_step not in _ANCHOR_KICKS):
                kick[idx] = (new_step, vel)
                kick_positions = {s for s, _ in kick}

        kick.sort(key=lambda x: x[0])

        # ── Hi-hat: drop/add steps; choke on kick steps ───────────────────────
        hihat = list(hihat_steps)

        droppable = [(i, h) for i, h in enumerate(hihat)
                     if int(h[0]) not in (_ANCHOR_KICKS | _ANCHOR_SNARES)]

        if droppable and random.random() < 0.5:
            n_drop  = random.randint(1, min(3, max(1, len(droppable) // 2)))
            drop_set = {i for i, _ in random.sample(droppable, n_drop)}
            hihat   = [h for i, h in enumerate(hihat) if i not in drop_set]
        elif hihat and random.random() < 0.4:
            existing = {s for s, _ in hihat}
            cands    = [s for s in range(16) if s not in existing]
            if cands:
                n_add = random.randint(1, min(2, len(cands)))
                for s in random.sample(cands, n_add):
                    hihat.append((s, random.randint(40, 60)))
                hihat.sort(key=lambda x: x[0])

        # 32nd-note rolls at complexity ≥ 7
        if complexity >= 7 and hihat and random.random() < 0.4:
            even_steps     = {int(s) for s, _ in hihat if int(s) % 2 == 0}
            existing_floats = {s for s, _ in hihat}
            safe_halves    = [s + 0.5 for s in even_steps
                              if s + 0.5 < 16 and s + 0.5 not in existing_floats]
            if safe_halves:
                n_rolls = random.randint(1, min(3, len(safe_halves)))
                for pos in random.sample(safe_halves, n_rolls):
                    hihat.append((pos, random.randint(30, 50)))
                hihat.sort(key=lambda x: x[0])

        # Inter-layer choke: remove hihats that land on kick steps
        hihat = [(s, v) for s, v in hihat if int(s) not in kick_positions]

        return kick, list(snare_steps), hihat

    # ─────────────────────────────────────────────────────────────────
    #  DRUM & BASS CIPHER — dedicated breakbeat + Reese bass generators
    # ─────────────────────────────────────────────────────────────────

    # Max kick steps per 16-step bar per genre (lo, hi) — density governor.
    _KICK_DENSITY: Dict[str, Tuple[int, int]] = {
        'pop':       (4, 6),
        'hiphop':    (3, 5),
        'trap':      (4, 7),
        'phonk':     (4, 7),
        'edm':       (4, 8),
        'house':     (4, 8),
        'techno':    (4, 8),
        'cinematic': (3, 6),
        'dnb':       (3, 6),
        'jpop':      (4, 6),
        'classical': (2, 4),
    }
    _KICK_DENSITY_DEFAULT: Tuple[int, int] = (4, 6)

    # Ghost-kick candidates (bar-relative beat positions, 0-indexed).
    # Excludes main kick (0.0) and hard-locked snares (1.0, 3.0).
    _DNB_GHOST_KICK_POSITIONS: tuple = (
        0.25, 0.5, 0.75,          # "and" subdivisions of beat 1
        1.25, 1.5, 1.75,          # beat 2.25 / 2.5 / 2.75
        2.25, 2.5, 2.75,          # beat 3.25 / 3.5 (user-specified) / 3.75
        3.25, 3.5, 3.75,          # beat 4.25 / 4.5 / 4.75
    )

    def _generate_dnb_drums(
        self,
        config: 'CompositionConfig',
        structure: List[Tuple[str, int]],
        total_bars: int,
    ) -> List[Tuple[float, float, int, int]]:
        """
        Breakbeat cipher for DnB. Dynamically picks from all GENRE_DRUM_PATTERNS['dnb']
        variants (re-selected every 4 bars) and routes through _apply_groove_variation
        for density governance, swing, and inter-layer choking.
        """
        notes: List[Tuple[float, float, int, int]] = []
        complexity = config.complexity
        mutation   = getattr(config, 'mutation', 0.0)
        bpm        = config.bpm or 174.0

        dnb_pats = GENRE_DRUM_PATTERNS.get('dnb', [])
        if not dnb_pats:
            return notes

        kick_steps: list = []
        snare_steps: list = []
        hihat_steps: list = []
        beat_pos = 0.0
        bar_global = 0

        for section_type, section_bars in structure:
            energy   = self._section_energy(section_type)
            is_break = section_type == 'break'

            for bar in range(section_bars):
                bo = beat_pos

                # Re-pick pattern variant every 4 bars for breakbeat variety
                if bar_global % 4 == 0:
                    g_pat = random.choice(dnb_pats)
                    kick_steps, snare_steps, hihat_steps = self._apply_groove_variation(
                        g_pat.get('kick',  []),
                        g_pat.get('snare', []),
                        g_pat.get('hihat', []),
                        complexity, mutation, 'dnb',
                    )

                # ── Kick ──────────────────────────────────────────────────
                kick_hit_steps: set = set()
                for step, base_vel in kick_steps:
                    if is_break and step != 0:
                        continue   # breaks: keep only beat-1 anchor
                    vel = random.randint(110, 122) if step == 0 else random.randint(85, 98)
                    t   = self._micro_humanize(bo + step * 0.25, bpm)
                    notes.append((t, 0.22, KICK, min(127, int(vel * energy))))
                    kick_hit_steps.add(step)

                # ── Snare ─────────────────────────────────────────────────
                for step, base_vel in snare_steps:
                    vel = min(127, int(base_vel * energy))
                    t   = self._micro_humanize(bo + step * 0.25, bpm)
                    notes.append((t, 0.22, SNARE, vel))
                    # Ghost snare (35% per main snare hit)
                    if random.random() < 0.35:
                        ghost_step = step + random.choice([-1, 1])
                        if 0 <= ghost_step < 16 and ghost_step not in (0, 4, 8, 12):
                            tg = self._micro_humanize(
                                bo + ghost_step * 0.25, bpm, max_seconds=0.004)
                            notes.append((tg, 0.08, SNARE, random.randint(28, 48)))

                # ── Hi-hats (choked on kick steps) ────────────────────────
                for step, base_vel in hihat_steps:
                    if step in kick_hit_steps:
                        continue
                    vel = min(127, max(25, int(base_vel * energy)))
                    hat = HIHAT_OPEN if step % 8 == 4 else HIHAT_CLOSED
                    t   = self._micro_humanize(bo + step * 0.25, bpm, max_seconds=0.005)
                    notes.append((t, 0.20, hat, vel))

                beat_pos   += 4.0
                bar_global += 1

        return notes

    def _generate_dnb_bass(
        self,
        config: 'CompositionConfig',
        chord_progression: List[str],
        structure: List[Tuple[str, int]],
    ) -> List[Tuple[float, float, int, int]]:
        """
        Reese-bass generator for DnB.

        Produces long, sustained sub-bass notes that mimic a detuned
        oscillator stack.  All notes are forced to octave 2 (MIDI 36–47).
        Short staccato plucks are disabled — minimum note length is 1.9 beats.

        Pattern (per bar)
        -----------------
        70 % : single root note held for the full bar (3.9 beats).
        30 % : two-note movement — root for 2 beats, then root or perfect 5th
               for the remaining 2 beats (common Reese modulation gesture).
        """
        notes: List[Tuple[float, float, int, int]] = []
        beat_pos = 0.0
        chord_idx = 0

        volume   = config.tracks.get('bass', {}).get('volume', 0.8)
        base_vel = int(102 * volume)

        for section_type, section_bars in structure:
            energy = self._section_energy(section_type)

            for _ in range(section_bars):
                if chord_idx >= len(chord_progression):
                    chord_idx = chord_idx % max(1, len(chord_progression))

                root, quality = parse_chord_string(chord_progression[chord_idx])
                root_midi = note_name_to_midi(root, 2)   # sub-bass at octave 2
                vel = BassVelocityProfile.velocity('dnb', 0, energy, is_root=True)

                if random.random() < 0.70:
                    # Full-bar sustain — the canonical Reese character
                    notes.append((beat_pos, GateLengthHumanizer.apply(3.90), root_midi, vel))
                else:
                    # Two-note movement for harmonic variety
                    second  = root_midi + 7 if random.random() < 0.6 else root_midi
                    vel2    = BassVelocityProfile.velocity('dnb', 8, energy)
                    notes.append((beat_pos,       GateLengthHumanizer.apply(1.95), root_midi, vel))
                    notes.append((beat_pos + 2.0, GateLengthHumanizer.apply(1.85), second,    vel2))

                beat_pos  += 4.0
                chord_idx += 1

        return notes

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
        bpm = getattr(config, 'bpm', None) or 120.0

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
                        velocity = BassVelocityProfile.velocity(
                            genre, step, section_energy,
                            is_root=(step == 0 or midi_note == root_midi),
                        )
                        notes.append((
                            step_time + h_offset,
                            GateLengthHumanizer.apply(duration),
                            midi_note, velocity,
                        ))

                # ── 808 Octave Leap ───────────────────────────────────────
                if config.genre in ('trap', 'hiphop', 'phonk'):
                    leap = EightOhEightOctaveLeap.maybe_hit(root_midi, bar_time, bpm)
                    if leap:
                        notes.append(leap)

                bar_idx += 1
                chord_idx += 1

        # ── 808 Glide ────────────────────────────────────────────────────────
        if config.genre in ('trap', 'hiphop', 'phonk'):
            notes = EightOhEightGlider.apply(notes, bpm)

        # ── Silence Matrix ───────────────────────────────────────────────────
        if config.genre in ('trap', 'hiphop', 'phonk'):
            _total      = sum(b for _, b in structure)
            _drop_seed  = getattr(config, 'seed_value', None) or abs(hash(config.genre))
            notes       = SilenceMatrix.apply(notes, SilenceMatrix.compute_zones(_total, _drop_seed))

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
        bpm = getattr(config, 'bpm', None) or 120.0

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

                genre = config.genre
                if energy < 0.2:
                    vel = BassVelocityProfile.velocity(genre, 0, energy, is_root=True)
                    notes.append((
                        humanize(beat_pos, 0.01 * config.humanize_amount),
                        GateLengthHumanizer.apply(3.5), root_midi, vel,
                    ))
                elif complexity <= 3:
                    for beat in range(4):
                        s   = beat * 4   # step within bar: 0, 4, 8, 12
                        vel = BassVelocityProfile.velocity(genre, s, energy, is_root=True)
                        notes.append((
                            humanize(beat_pos + beat, 0.01 * config.humanize_amount),
                            GateLengthHumanizer.apply(0.9), root_midi, vel,
                        ))
                elif complexity <= 6:
                    fifth   = root_midi + 7
                    pattern = [
                        (0,   root_midi, 0.9),
                        (1,   root_midi, 0.5),
                        (2,   fifth,     0.9),
                        (2.5, root_midi, 0.4),
                        (3,   root_midi, 0.8),
                    ]
                    for offset, note, dur in pattern:
                        s   = int(offset * 4) % 16
                        vel = BassVelocityProfile.velocity(
                            genre, s, energy, is_root=(note == root_midi))
                        notes.append((
                            humanize(beat_pos + offset, 0.01 * config.humanize_amount),
                            GateLengthHumanizer.apply(dur), note, vel,
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
                            s   = int(pos * 4) % 16
                            vel = BassVelocityProfile.velocity(
                                genre, s, energy, is_root=(note == root_midi))
                            notes.append((
                                humanize(beat_pos + pos, 0.012 * config.humanize_amount),
                                GateLengthHumanizer.apply(0.4), note, vel,
                            ))

                # ── 808 Octave Leap ───────────────────────────────────────
                if config.genre in ('trap', 'hiphop', 'phonk'):
                    leap = EightOhEightOctaveLeap.maybe_hit(root_midi, beat_pos, bpm)
                    if leap:
                        notes.append(leap)

                beat_pos += 4
                chord_idx += 1
                bar_count += 1

        # ── 808 Glide ────────────────────────────────────────────────────────
        if config.genre in ('trap', 'hiphop', 'phonk'):
            notes = EightOhEightGlider.apply(notes, bpm)

        # ── Silence Matrix ───────────────────────────────────────────────────
        if config.genre in ('trap', 'hiphop', 'phonk'):
            _drop_seed = getattr(config, 'seed_value', None) or abs(hash(config.genre))
            notes      = SilenceMatrix.apply(notes, SilenceMatrix.compute_zones(bar_count, _drop_seed))

        return notes

    # ─────────────────────────────────────────────────────────────────
    #  CHORD TRACK GENERATION
    # ─────────────────────────────────────────────────────────────────

    # ── Intro / Outro archetype constants ─────────────────────────────────
    _INTRO_ARCHETYPES = ('staccato', 'atmospheric', 'arpeggio')
    _OUTRO_ARCHETYPES = ('fade_sustain', 'dissolve', 'descending_arp')

    # IntroVarietyProtocol — 80 % of tracks get one of the three randomised
    # archetypes; 20 % preserve the "Signature Intro" (single sustained chord
    # per bar) so the dataset retains a genre-representative anchor pattern.
    _INTRO_VARIETY_PCT  = 0.80   # probability of using a randomised archetype
    _INTRO_SIGNATURE    = 'signature'

    # Staccato hit grids used by intro Type A.
    # Randomly chosen per bar so consecutive bars never share the same grid.
    _STACCATO_GRIDS = [
        [0.0, 2.0],
        [0.0, 1.5, 3.0],
        [0.5, 2.5],
        [0.0, 2.5, 3.5],
        [1.0, 3.0],
        [0.0, 1.0, 2.5],
    ]

    def generate_chord_track(self, config: CompositionConfig,
                             chord_progression: List[str],
                             structure: List[Tuple[str, int]]) -> List[Tuple[float, float, int, int]]:
        notes = []
        complexity = config.complexity
        volume = config.tracks.get('chords', {}).get('volume', 0.7)
        base_vel = int(80 * volume)
        h_amt = config.humanize_amount

        # Parse key once for Billboard archetypes that build chords from root.
        _key_parts    = (config.key or 'C major').split()
        _key_root_str = _key_parts[0]
        _key_scale    = _key_parts[1] if len(_key_parts) > 1 else 'major'
        _key_root_midi: int = note_name_to_midi(_key_root_str, 4)

        beat_pos = 0
        chord_idx = 0
        prev_voicing = None

        # Per-section archetype state (reset on each intro/outro entry)
        _archetype: str = 'atmospheric'
        _quiet_bar: int = 0          # intro: one soft bar
        _silent_bar: int = -1        # outro: one completely silent bar (breath)
        _sig_mate_prog: list = []    # databank harmonic sequence for signature mating

        for section_type, section_bars in structure:
            energy = self._section_energy(section_type)

            # ── Select intro archetype once per intro section ──────────────
            # IntroVarietyProtocol: 80 % varied / 20 % signature.
            # Genre-specific archetypes (Pop/House/EDM) are fetched from the
            # intro_archetype_registry; all other genres use the built-in set.
            if section_type == 'intro':
                _genre_archetypes = (
                    _intro_registry.get_archetypes(config.genre)
                    if _INTRO_REGISTRY_AVAILABLE else None
                )
                _available_archetypes = _genre_archetypes or self._INTRO_ARCHETYPES
                if random.random() < self._INTRO_VARIETY_PCT:
                    _archetype     = random.choice(_available_archetypes)
                    _sig_mate_prog = []
                else:
                    _archetype = self._INTRO_SIGNATURE
                    # Mate the signature rhythm with a real seed's harmonic DNA.
                    # Pull a random seed from the genre pool (fall back to global).
                    _pool = self.genre_seeds.get(config.genre) or self.seeds
                    if _pool:
                        _mate = random.choice(_pool)
                        _sig_mate_prog = _mate.get('progression_sample', []) or []
                    else:
                        _sig_mate_prog = []
                _quiet_bar = random.randint(max(0, 1), max(1, section_bars - 1))

            # ── Select outro archetype once per outro section ──────────────
            elif section_type == 'outro':
                _archetype   = random.choice(self._OUTRO_ARCHETYPES)
                # 30 % chance of one completely silent "breath" bar mid-outro
                if section_bars >= 4 and random.random() < 0.30:
                    _silent_bar = random.randint(1, section_bars - 2)
                else:
                    _silent_bar = -1

            for bar in range(section_bars):
                if chord_idx >= len(chord_progression):
                    chord_idx = chord_idx % max(1, len(chord_progression))

                root, quality = parse_chord_string(chord_progression[chord_idx])
                chord_notes = get_chord_midi_notes(root, quality, 4)

                if prev_voicing and len(chord_notes) > 0:
                    chord_notes = self._voice_lead(prev_voicing, chord_notes)
                prev_voicing = chord_notes

                # ── Intro: genre-specific archetypes via registry, then built-ins ─
                if section_type == 'intro':
                    is_quiet = (bar == _quiet_bar)
                    vel_scale = 0.48 if is_quiet else random.uniform(0.72, 1.0)
                    bar_vel   = max(28, int(base_vel * vel_scale * (energy + 0.15)))

                    # Try genre-specific dispatch (Pop / House / EDM / Billboard)
                    if _INTRO_REGISTRY_AVAILABLE and _archetype != self._INTRO_SIGNATURE:
                        _genre_events = _intro_registry.generate_events(
                            genre         = config.genre,
                            archetype     = _archetype,
                            bar           = bar,
                            section_bars  = section_bars,
                            chord_notes   = chord_notes,
                            beat_pos      = beat_pos,
                            bar_vel       = bar_vel,
                            h_amt         = h_amt,
                            humanize_fn   = humanize,
                            gate_fn       = GateLengthHumanizer.apply,
                            key_root_midi = _key_root_midi,
                            key_scale     = _key_scale,
                        )
                        if _genre_events is not None:
                            notes.extend(_genre_events)
                            beat_pos  += 4
                            chord_idx += 1
                            continue

                    if _archetype == 'staccato':
                        # Type A — Rhythmic Staccato: short punchy hits, varied grid each bar
                        grid = random.choice(self._STACCATO_GRIDS)
                        for off in grid:
                            hit_vel = max(28, int(bar_vel * random.uniform(0.75, 1.0)))
                            for note in chord_notes:
                                notes.append((
                                    humanize(beat_pos + off, 0.02 * h_amt),
                                    GateLengthHumanizer.apply(random.uniform(0.22, 0.42)),
                                    note, hit_vel,
                                ))

                    elif _archetype == 'atmospheric':
                        # Type B — Sustained Atmospheric: one long chord, gate varies per bar
                        gate = GateLengthHumanizer.apply(random.uniform(3.2, 7.0))
                        for note in chord_notes:
                            notes.append((
                                humanize(beat_pos, 0.01 * h_amt),
                                gate, note, bar_vel,
                            ))

                    elif _archetype == 'arpeggio':
                        # Type C — Arpeggiated Tension: ascending 8th-note arpeggio.
                        # Note count builds bar-by-bar so tension accumulates.
                        sorted_notes = sorted(chord_notes)
                        build_frac   = (bar + 1) / max(1, section_bars)
                        n_notes      = max(2, round(len(sorted_notes) * build_frac))
                        for i, note in enumerate(sorted_notes[:n_notes]):
                            t = beat_pos + i * 0.5
                            if t < beat_pos + 3.9:
                                arp_vel = max(28, int(bar_vel * (0.60 + 0.40 * i / max(1, n_notes - 1))))
                                notes.append((
                                    humanize(t, 0.015 * h_amt),
                                    GateLengthHumanizer.apply(0.40),
                                    note, arp_vel,
                                ))

                    else:
                        # Signature Intro mated with seed-databank harmonics.
                        # Rhythm: one sustained chord per bar (the genre's brand sound).
                        # Voicing: cycles through a randomly-selected seed's
                        # progression_sample so each Signature Intro track carries
                        # real harmonic DNA from the training corpus.
                        if _sig_mate_prog:
                            mate_str = _sig_mate_prog[bar % len(_sig_mate_prog)]
                            try:
                                m_root, m_quality = parse_chord_string(mate_str)
                                src_notes = get_chord_midi_notes(m_root, m_quality, 4)
                            except Exception:
                                src_notes = chord_notes  # fallback on parse error
                        else:
                            src_notes = chord_notes
                        chord_vel = PhraseVelocityMapper.velocity(0, energy)
                        chord_dur = GateLengthHumanizer.apply(3.8)
                        for note in src_notes:
                            notes.append((beat_pos, chord_dur, note, chord_vel))

                # ── Outro: three distinct archetypes (mirror of intro, inverse motion) ──
                elif section_type == 'outro':
                    # Breath bar: deliberate silence
                    if bar == _silent_bar:
                        beat_pos  += 4
                        chord_idx += 1
                        continue

                    # Fade factor: 1.0 on bar 0, approaches 0.0 at last bar
                    fade = max(0.05, 1.0 - bar / max(1, section_bars - 1))

                    if _archetype == 'fade_sustain':
                        # Type A — Fade Sustain: long chord, velocity decays bar-by-bar
                        gate    = GateLengthHumanizer.apply(random.uniform(3.5, 6.5))
                        out_vel = max(18, int(base_vel * fade * (energy + 0.1)))
                        for note in chord_notes:
                            notes.append((
                                humanize(beat_pos, 0.01 * h_amt),
                                gate, note, out_vel,
                            ))

                    elif _archetype == 'dissolve':
                        # Type B — Dissolve: chord loses notes bar-by-bar (full → root only)
                        sorted_notes = sorted(chord_notes, reverse=True)  # top notes drop first
                        n_remaining  = max(1, len(sorted_notes) - int(bar * len(sorted_notes) / max(1, section_bars)))
                        out_vel      = max(18, int(base_vel * fade * (energy + 0.1)))
                        gate         = GateLengthHumanizer.apply(random.uniform(3.0, 5.5))
                        for note in sorted_notes[:n_remaining]:
                            notes.append((
                                humanize(beat_pos, 0.01 * h_amt),
                                gate, note, out_vel,
                            ))

                    else:
                        # Type C — Descending Arpeggio: falling 8th-notes, count shrinks per bar
                        sorted_notes = sorted(chord_notes, reverse=True)  # high → low
                        n_notes      = max(1, len(sorted_notes) - int(bar * len(sorted_notes) / max(1, section_bars)))
                        for i, note in enumerate(sorted_notes[:n_notes]):
                            t = beat_pos + i * 0.5
                            if t < beat_pos + 3.9:
                                arp_vel = max(18, int(base_vel * fade * (0.85 - 0.15 * i / max(1, n_notes - 1))))
                                notes.append((
                                    humanize(t, 0.015 * h_amt),
                                    GateLengthHumanizer.apply(0.40),
                                    note, arp_vel,
                                ))

                # ── Section-specific chord patterns (run before complexity fallback) ──

                elif section_type in ('drop', 'climax'):
                    # Dense 8th-note stabs — wall-of-sound effect
                    for i, offset in enumerate([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]):
                        if random.random() < 0.82 * energy:
                            note = chord_notes[i % len(chord_notes)]
                            notes.append((
                                humanize(beat_pos + offset, 0.015 * h_amt),
                                GateLengthHumanizer.apply(random.uniform(0.28, 0.46)),
                                note,
                                PhraseVelocityMapper.velocity(i * 2, energy),
                            ))

                elif section_type == 'chorus':
                    # Syncopated 4-hit grid — more punchy than verse, varied each bar
                    grid = random.choice([
                        [0.0, 0.75, 2.0, 2.75],   # off-beat syncopation
                        [0.0, 1.0,  2.0, 3.0],    # on-beat punch
                        [0.0, 0.5,  2.0, 3.5],    # hybrid push
                    ])
                    for i, offset in enumerate(grid):
                        chord_vel = PhraseVelocityMapper.velocity(int(offset * 4) % 16, energy)
                        for note in chord_notes:
                            notes.append((
                                humanize(beat_pos + offset, 0.015 * h_amt),
                                GateLengthHumanizer.apply(random.uniform(0.9, 1.6)),
                                note, chord_vel,
                            ))

                elif section_type == 'build':
                    # Escalating density: starts with 1 hit per bar, builds to 4
                    build_frac = (bar + 1) / max(1, section_bars)
                    n_hits     = max(1, round(4 * build_frac))
                    gate       = GateLengthHumanizer.apply(max(0.28, 3.5 - 3.0 * build_frac))
                    chord_vel  = PhraseVelocityMapper.velocity(0, energy * (0.5 + 0.5 * build_frac))
                    for offset in [0.0, 1.0, 2.0, 3.0][:n_hits]:
                        for note in chord_notes:
                            notes.append((
                                humanize(beat_pos + offset, 0.015 * h_amt),
                                gate, note, chord_vel,
                            ))

                elif section_type == 'break':
                    # Very sparse — 35 % chance of one long chord per bar
                    if random.random() < 0.35:
                        chord_vel = max(20, int(base_vel * 0.5 * energy))
                        for note in chord_notes:
                            notes.append((
                                humanize(beat_pos, 0.01 * h_amt),
                                GateLengthHumanizer.apply(3.8),
                                note, chord_vel,
                            ))

                # ── Remaining sections (verse, pre_chorus, bridge, tension,
                #    resolution, …): complexity-gated fallback ───────────────
                elif energy < 0.15:
                    chord_vel = PhraseVelocityMapper.velocity(0, energy * 0.5)
                    chord_dur = GateLengthHumanizer.apply(3.8)
                    for note in chord_notes:
                        notes.append((humanize(beat_pos, 0.01), chord_dur, note, chord_vel))
                elif complexity <= 3:
                    chord_vel = PhraseVelocityMapper.velocity(0, energy)
                    chord_dur = GateLengthHumanizer.apply(3.8)
                    for note in chord_notes:
                        notes.append((beat_pos, chord_dur, note, chord_vel))
                elif complexity <= 6:
                    for beat_offset in [0, 2]:
                        s         = int(beat_offset * 4)
                        chord_vel = PhraseVelocityMapper.velocity(s, energy)
                        chord_dur = GateLengthHumanizer.apply(1.5)
                        for note in chord_notes:
                            notes.append((
                                humanize(beat_pos + beat_offset, 0.015 * h_amt),
                                chord_dur, note, chord_vel,
                            ))
                else:
                    rhythm = [0, 0.75, 1.5, 2, 2.75, 3.5]
                    for i, offset in enumerate(rhythm):
                        if random.random() < 0.8 * energy:
                            s    = int(offset * 4) % 16
                            note = chord_notes[i % len(chord_notes)]
                            notes.append((
                                humanize(beat_pos + offset, 0.02 * h_amt),
                                GateLengthHumanizer.apply(0.6), note,
                                PhraseVelocityMapper.velocity(s, energy),
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

                        hgov = self._get_hgov()
                        if hgov:
                            midi_note = hgov.resolve(
                                midi_note, chord_progression[chord_idx],
                                step_time,
                                getattr(config, 'use_7th_chords', False),
                            )

                        while midi_note > 84:
                            midi_note -= 12
                        while midi_note < 60:
                            midi_note += 12

                        midi_note = self._apply_vocal_mask(midi_note, section_type, config)
                        if midi_note is None:
                            prev_note = None  # reset voice-leading on drop
                            continue

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
                        velocity = PhraseVelocityMapper.velocity(step, section_energy)
                        notes.append((
                            step_time + h_offset,
                            GateLengthHumanizer.apply(duration),
                            midi_note, velocity,
                        ))
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

                        hgov = self._get_hgov()
                        if hgov:
                            note = hgov.resolve(
                                note, chord_progression[chord_idx],
                                beat_pos + pos,
                                getattr(config, 'use_7th_chords', False),
                            )

                        note = self._apply_vocal_mask(note, section_type, config)
                        if note is None:
                            prev_note = None  # reset voice-leading on drop
                            continue

                        dur_options = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0]
                        dur = random.choice(dur_options[:2 + complexity // 2])

                        phrase_counter += 1
                        if phrase_counter > 4 + complexity and random.random() < 0.4:
                            phrase_counter = 0
                            continue

                        step_pos = int(pos * 4) % 16
                        notes.append((
                            humanize(beat_pos + pos, 0.02 * config.humanize_amount),
                            GateLengthHumanizer.apply(dur), note,
                            PhraseVelocityMapper.velocity(step_pos, energy),
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
                                notes.append((humanize(time, 0.01),
                                              GateLengthHumanizer.apply(0.25), final_note,
                                              humanize_velocity(int(base_vel * pad_energy * 1.2), 6)))
                else:
                    if config.complexity < 4 or energy < 0.4:
                        for note in chord_notes[:3]:
                            notes.append((bo, GateLengthHumanizer.apply(3.8), note,
                                          humanize_velocity(int(base_vel * pad_energy), 6)))
                    else:
                        swell_pattern = [0.8, 0.9, 1.1, 1.2, 1.3, 1.1, 0.9, 0.8]

                        for step in range(8):
                            time = bo + (step * 0.5)
                            swell = swell_pattern[step] + (mutation * 0.1)

                            for i, note in enumerate(chord_notes[:3]):
                                offset = i * 0.015
                                vel = humanize_velocity(int(base_vel * pad_energy * swell), 8)
                                notes.append((time + offset, GateLengthHumanizer.apply(0.45), note, vel))

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
                        hgov = self._get_hgov()
                        if hgov:
                            note = hgov.resolve(
                                note, chord_progression[chord_idx],
                                beat_pos + pos,
                                getattr(config, 'use_7th_chords', False),
                            )
                        note = self._apply_vocal_mask(note, section_type, config)
                        if note is not None:
                            step_pos = int(pos * 4) % 16
                            notes.append((
                                humanize(beat_pos + pos, 0.008 * config.humanize_amount),
                                GateLengthHumanizer.apply(step * 0.8),
                                note,
                                PhraseVelocityMapper.velocity(step_pos, energy),
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
    #  EDM BUILD-UP GENERATOR  (public wrapper for StochasticBuildUp)
    # ─────────────────────────────────────────────────────────────────

    def generate_edm_buildup(
        self,
        bar_offset: int,
        n_bars:     int,
        bpm:        float,
    ) -> dict:
        """
        Generate stochastic EDM build-up content for the n_bars bars that
        immediately precede a Drop section.

        Returns a dict with three keys:
          'kick'         : List[Note]        crash cymbal on bar downbeat
          'perc'         : List[Note]        accelerating snare roll (1/4→1/32)
          'pitch_events' : List[PitchEvent]  linear pitch-bend sweep 0→8191 + reset

        The returned notes replace the standard drum generator output for the
        matching bar range in compose().  Pitch events are stored separately
        and injected into the MIDI file via addPitchWheelEvent() in export_midi().
        """
        return StochasticBuildUp.generate(bar_offset, n_bars, bpm)

    # ─────────────────────────────────────────────────────────────────
    #  MAIN COMPOSITION METHOD
    # ─────────────────────────────────────────────────────────────────

    def compose(self, config: CompositionConfig) -> dict:
        self._ensure_loaded()
        if self.vocal_mask:
            config.vocal_mask = True   # engine-level flag overrides config
        if config.seed_value is not None: random.seed(config.seed_value)

        if config.bpm is None: config.bpm = random.uniform(*GENRE_BPM.get(config.genre, (100, 130)))
        if config.genre == 'dnb':
            config.bpm = random.uniform(170, 175)  # tempo lock — always forced
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

        # ── DnB cipher: replace standard drum + bass with breakbeat generators
        if config.genre == 'dnb':
            raw_drums = self._generate_dnb_drums(config, structure, total_bars)
            raw_bass  = self._generate_dnb_bass(config, chord_progression, structure)

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

        # ── Bass/Kick pocket constraint ───────────────────────────────
        # If a bass note lands within ±0.01 s of a kick, choke its sustain
        # to prevent low-end phase cancellation and muddiness.
        # DnB is exempt: Reese bass is intentionally layered over the kick.
        if kick_notes and raw_bass and config.genre != 'dnb':
            _bpm              = config.bpm or 120.0
            tolerance_beats   = 0.01 * (_bpm / 60.0)
            kick_times        = {n[0] for n in kick_notes}
            raw_bass = [
                (bp,
                 min(dur, 0.08) if any(abs(bp - k) <= tolerance_beats for k in kick_times)
                 else dur,
                 pitch, vel)
                for bp, dur, pitch, vel in raw_bass
            ]

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

        # ── Vocal mask post-pass on omni arp (07_Arp) ────────────────
        if getattr(config, 'vocal_mask', False):
            # Build beat ranges for sections that need to be cleared
            masked_ranges: list = []
            beat = 0.0
            for s_type, s_bars in structure:
                end = beat + s_bars * 4
                if s_type in _VOCAL_MASK_SECTIONS:
                    masked_ranges.append((beat, end))
                beat = end

            def _mask_note(n):
                time, dur, pitch, vel = n
                in_section = any(s <= time < e for s, e in masked_ranges)
                if not in_section or not (_VOCAL_MASK_LOW <= pitch < _VOCAL_MASK_HIGH):
                    return n
                p = pitch
                while p >= _VOCAL_MASK_LOW:
                    p -= 12
                return (time, dur, p, vel) if p >= 36 else None

            raw_arp = [r for r in map(_mask_note, omni_tracks.get('07_Arp', [])) if r is not None]
            omni_tracks['07_Arp'] = raw_arp

            melody_notes = [r for r in map(_mask_note, melody_notes) if r is not None]

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

        # ── EDM Ciphers  (edm / house genres) ────────────────────────────────
        cc_events:    list = []
        pitch_events: list = []

        if config.genre in ('edm', 'house'):
            _edm_bpm = config.bpm or 128.0
            _seed    = getattr(config, 'seed_value', None)

            # Cipher 1 — Sidechain CC11 pumping on bass / chords / pad
            _kick_times = [n[0] for n in tracks['01_Kick']]
            cc_events += SidechainMatrix.generate_cc(_kick_times, total_bars)

            # Cipher 5 — Polyrhythmic filter sweep CC74 on pad / arp
            cc_events += PolyrhythmicFilterSweep.generate_cc(total_bars)

            # Cipher 2 — Stochastic build-up for 'build' sections before 'drop' or 'chorus'
            _bar_cur = 0
            for _idx, (_stype, _sbars) in enumerate(structure):
                if (    _stype == 'build'
                        and _idx + 1 < len(structure)
                        and structure[_idx + 1][0] in ('drop', 'chorus')):
                    _bu    = StochasticBuildUp.generate(_bar_cur, _sbars, _edm_bpm)
                    _bu_s  = _bar_cur * 4.0
                    _bu_e  = (_bar_cur + _sbars) * 4.0
                    # Replace standard drum notes inside this build-up window
                    tracks['01_Kick']       = [n for n in tracks['01_Kick']       if not (_bu_s <= n[0] < _bu_e)]
                    tracks['02_Percussion'] = [n for n in tracks['02_Percussion'] if not (_bu_s <= n[0] < _bu_e)]
                    tracks['01_Kick']      += _bu['kick']
                    tracks['02_Percussion']+= _bu['perc']
                    pitch_events           += _bu['pitch_events']
                _bar_cur += _sbars

            # Cipher 3 — Pre-Drop Void: mute kick / bass / chords / pad 1-2 beats before drop
            tracks = PreDropVoid.apply(tracks, structure)

            # Cipher 4 — Anti-Drop Fake-Out: 20% chance of minimalist drop (4 bars)
            tracks = AntiDropFakeOut.apply(tracks, structure, seed=_seed)

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
            'tracks':       tracks,
            'track_info':   track_info,
            'cc_events':    cc_events,
            'pitch_events': pitch_events,
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
            midi.addTrackName(i, 0, name)

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

        # ── CC automation and pitch-bend events (EDM ciphers) ─────────────────
        _cc_evts    = composition.get('cc_events',    [])
        _pitch_evts = composition.get('pitch_events', [])

        if _cc_evts or _pitch_evts:
            # Build channel → track-index lookup from the ordered track_info dict
            _ch_to_track: dict = {}
            for _ti, _tname in enumerate(composition['tracks']):
                _ch = composition['track_info'].get(_tname, {}).get('channel', -1)
                if _ch >= 0 and _ch not in _ch_to_track:
                    _ch_to_track[_ch] = _ti

            for _t, _cc, _val, _ch in _cc_evts:
                _ti = _ch_to_track.get(_ch, 0)
                try:
                    midi.addControllerEvent(_ti, _ch, _t, _cc, _val)
                except Exception:
                    pass   # midiutil version may differ

            for _t, _pb, _ch in _pitch_evts:
                _ti = _ch_to_track.get(_ch, 0)
                try:
                    midi.addPitchWheelEvent(_ti, _ch, _t, _pb)
                except Exception:
                    pass

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


# ─────────────────────────────────────────────────────────────────────────────
#  Golden Matrix Injection — pool loader + mutated config builder
# ─────────────────────────────────────────────────────────────────────────────

_GOLDEN_ROOTS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def _jitter(val: float, lo: float, hi: float, factor: float) -> float:
    """Perturb *val* by ±(range_width × factor), clamped to [lo, hi]."""
    delta = (hi - lo) * factor
    return max(lo, min(hi, val + random.uniform(-delta, delta)))


class GoldenMatrixPool:
    """
    Weighted pool of top-scoring generation parameters loaded from a
    math_fitness_report.json produced by telemetry_grader_midi.

    Higher-scoring matrices are sampled more frequently so the next
    batch converges toward the winning parameter space while still
    exploring the neighbourhood through mutation.
    """

    def __init__(self, matrices: list, mutation_factor: float = 0.05):
        if not matrices:
            raise ValueError("GoldenMatrixPool requires at least one matrix.")
        self.matrices       = matrices
        self.mutation_factor = mutation_factor

        # Score-proportional weights (shift so minimum weight > 0)
        scores  = [float(m.get("score", 50.0)) for m in matrices]
        min_s   = min(scores)
        self.weights = [max(s - min_s + 1.0, 0.01) for s in scores]

    # ── Sampling ──────────────────────────────────────────────────────────────

    def sample(self) -> dict:
        """Weighted-random draw; returns the full golden matrix dict."""
        return random.choices(self.matrices, weights=self.weights, k=1)[0]

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_report(cls, report_path: str,
                    mutation_factor: float = 0.05) -> "GoldenMatrixPool":
        """Load *report_path* (math_fitness_report.json) and build a pool."""
        with open(report_path, "r", encoding="utf-8") as fh:
            report = json.load(fh)
        matrices = report.get("golden_matrices", [])
        if not matrices:
            raise ValueError(f"No 'golden_matrices' key in {report_path}")
        pool = cls(matrices, mutation_factor)
        print(
            f"[GoldenPool] Loaded {len(matrices)} matrices from "
            f"'{report_path}'  (genre={report.get('genre','?')}  "
            f"mutation_factor={mutation_factor})"
        )
        return pool

    # ── Info ──────────────────────────────────────────────────────────────────

    def summary(self) -> str:
        top = self.matrices[0]
        return (
            f"{len(self.matrices)} matrices  "
            f"top_score={top.get('score', '?'):.2f}  "
            f"mutation_factor={self.mutation_factor}"
        )


def config_from_golden(
    golden: dict,
    mutation_factor: float = 0.05,
) -> "CompositionConfig":
    """
    Build a mutated :class:`CompositionConfig` from a golden matrix entry.

    Continuous parameters (BPM, tension, humanize, mutation rate) are jittered
    by ±(range_width × mutation_factor).

    Root note diversity uses a fixed 50 % chance of shifting ±1-5 semitones,
    independent of mutation_factor, so tracks never all lock to the same key
    even at low mutation_factor values.

    seed_value is always regenerated to guarantee a unique composition.

    Parameters
    ----------
    golden          : one element of the golden_matrices array
    mutation_factor : controls BPM/tension/complexity spread
                      0.03 = very tight  |  0.10 = moderate  |  0.20 = broad
    """
    params = golden.get("generation_params", golden)
    genre  = params.get("genre", "pop")
    bpm_lo, bpm_hi = GENRE_BPM.get(genre, (100, 130))

    # ── BPM jitter — floor of ±5 BPM so tempo is always audibly varied ──────────
    bpm_delta = max((bpm_hi - bpm_lo) * mutation_factor, 5.0)
    base_bpm  = params.get("bpm", (bpm_lo + bpm_hi) / 2.0)
    new_bpm   = max(bpm_lo, min(bpm_hi, base_bpm + random.uniform(-bpm_delta, bpm_delta)))

    new_tension  = _jitter(params.get("tension_multiplier", 0.5),  0.0, 1.5, mutation_factor)
    new_humanize = _jitter(params.get("humanize_amount",    0.6),  0.2, 1.0, mutation_factor)
    new_mut_rate = _jitter(params.get("mutation",           0.3),  0.0, 1.0, mutation_factor)

    # Complexity: ±1 step minimum, scales up with mutation_factor
    base_complexity   = int(params.get("complexity", 5))
    complexity_radius = max(1, round(mutation_factor * 10))
    new_complexity    = max(1, min(10,
        base_complexity + random.randint(-complexity_radius, complexity_radius)
    ))

    # ── Root note — 50 % shift, min ±5 semitones range so key never clusters ────
    base_root  = params.get("root",  "C")
    base_scale = params.get("scale", "major")
    if random.random() < 0.50:
        idx       = _GOLDEN_ROOTS.index(base_root) if base_root in _GOLDEN_ROOTS else 0
        max_shift = max(5, round(mutation_factor * 24))   # min ±5 semitones always
        shift     = random.randint(1, max_shift) * random.choice([-1, 1])
        new_root  = _GOLDEN_ROOTS[(idx + shift) % 12]
    else:
        new_root = base_root

    # ── Scale mode mutation — 25 % chance to pick any valid scale for the genre ─
    genre_scales = GENRE_SCALES.get(genre, ["major", "minor"])
    if random.random() < 0.25 and len(genre_scales) > 1:
        new_scale = random.choice(genre_scales)
    else:
        new_scale = base_scale

    config = CompositionConfig(
        genre              = genre,
        bpm                = round(new_bpm, 2),
        key                = f"{new_root} {new_scale}",
        complexity         = new_complexity,
        tension_multiplier = round(new_tension,  3),
        mutation           = round(new_mut_rate, 3),
        humanize_amount    = round(new_humanize, 3),
        seed_value         = random.randint(0, 999_999),
    )
    config.tracks['arp']['enabled'] = True
    return config


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
