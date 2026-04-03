"""
═══════════════════════════════════════════════════════════════════════
  COMPOSITION ENGINE — AI-Powered Song Generator
  Uses musical DNA seeds to compose unique multi-track songs.
  
  Features:
  - Markov chain chord progression generation
  - Genre-aware instrument pattern synthesis
  - Intelligent song structure generation (intro/verse/chorus/drop/outro)
  - Multi-track MIDI output (drums, bass, chords, lead, pad, arp)
  - Complexity control (0-10)
  - Humanization and groove
  - Music theory-compliant voice leading
═══════════════════════════════════════════════════════════════════════
"""

import json
import random
import math
import os
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field

try:
    from midiutil import MIDIFile
    MIDI_AVAILABLE = True
except ImportError:
    MIDI_AVAILABLE = False
    print("WARNING: midiutil not installed. Run: pip install midiutil")

# Import pattern learning systems
try:
    from rhythm_pattern_extractor import LearnedPatternGenerator, generate_drums_from_learned_patterns
    LEARNED_PATTERNS_AVAILABLE = True
except ImportError:
    LEARNED_PATTERNS_AVAILABLE = False

try:
    from genre_fusion import GenreFusionEngine, FusionConfig, FUSION_PRESETS
    FUSION_AVAILABLE = True
except ImportError:
    FUSION_AVAILABLE = False

try:
    from smart_arrangement import SmartArrangementEngine
    SMART_ARRANGEMENT_AVAILABLE = True
except ImportError:
    SMART_ARRANGEMENT_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════════

NOTE_TO_MIDI = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3,
    'E': 4, 'Fb': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7,
    'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11, 'Cb': 11,
}

MIDI_TO_NOTE = {v: k for k, v in NOTE_TO_MIDI.items() if '#' not in k and 'b' not in k}
MIDI_TO_NOTE.update({1: 'C#', 3: 'D#', 6: 'F#', 8: 'G#', 10: 'A#'})

CHORD_INTERVALS = {
    'major': [0, 4, 7], 'minor': [0, 3, 7], 'dim': [0, 3, 6],
    'aug': [0, 4, 8], 'sus4': [0, 5, 7], 'sus2': [0, 2, 7],
    '7': [0, 4, 7, 10], 'maj7': [0, 4, 7, 11], 'min7': [0, 3, 7, 10],
    'dim7': [0, 3, 6, 9], 'min': [0, 3, 7], 'maj': [0, 4, 7],
    '9': [0, 4, 7, 10, 14], 'add9': [0, 4, 7, 14],
    'min9': [0, 3, 7, 10, 14], 'maj9': [0, 4, 7, 11, 14],
    '11': [0, 4, 7, 10, 14, 17], '13': [0, 4, 7, 10, 14, 21],
    '6': [0, 4, 7, 9], 'min6': [0, 3, 7, 9],
}

# Scale intervals for melody generation
SCALE_INTERVALS = {
    'major': [0, 2, 4, 5, 7, 9, 11],
    'minor': [0, 2, 3, 5, 7, 8, 10],
    'dorian': [0, 2, 3, 5, 7, 9, 10],
    'mixolydian': [0, 2, 4, 5, 7, 9, 10],
    'pentatonic_major': [0, 2, 4, 7, 9],
    'pentatonic_minor': [0, 3, 5, 7, 10],
    'harmonic_minor': [0, 2, 3, 5, 7, 8, 11],
    'melodic_minor': [0, 2, 3, 5, 7, 9, 11],
    'phrygian': [0, 1, 3, 5, 7, 8, 10],
    'lydian': [0, 2, 4, 6, 7, 9, 11],
    'blues': [0, 3, 5, 6, 7, 10],
    'japanese': [0, 1, 5, 7, 8],  # For jpop/cinematic
    'chromatic': list(range(12)),
}

# GM Drum Map
KICK = 36
SNARE = 38
RIMSHOT = 37
CLAP = 39
HIHAT_CLOSED = 42
HIHAT_OPEN = 46
HIHAT_PEDAL = 44
CRASH = 49
RIDE = 51
TOM_LOW = 45
TOM_MID = 47
TOM_HIGH = 50

# Genre-specific drum patterns (positions in 16th notes within 1 bar of 4/4)
GENRE_DRUM_PATTERNS = {
    'pop': {
        'kick':  [(0, 100), (4, 80), (8, 90), (10, 60)],
        'snare': [(4, 100), (12, 100)],
        'hihat': [(i, 70 + (i % 2) * 15) for i in range(0, 16, 2)],
    },
    'hiphop': {
        'kick':  [(0, 110), (5, 70), (8, 90), (13, 60)],
        'snare': [(4, 100), (12, 95)],
        'hihat': [(i, 60 + random.randint(0, 20)) for i in range(16)],
    },
    'trap': {
        'kick':  [(0, 120), (3, 60), (6, 50), (10, 100), (14, 50)],
        'snare': [(4, 110), (12, 110)],
        'hihat': [(i, 50 + (30 if i % 3 == 0 else 0)) for i in range(16)] +
                 [(i + 0.5, 40) for i in range(0, 16, 2)],  # Triplet hats
    },
    'cinematic': {
        'kick':  [(0, 100), (8, 80)],
        'snare': [(8, 70)],
        'hihat': [],
    },
    'classical': {
        'kick': [], 'snare': [], 'hihat': [],
    },
    'techno': {
        'kick':  [(i * 4, 110) for i in range(4)],  # 4-on-the-floor
        'snare': [(4, 90), (12, 90)],
        'hihat': [(i, 80 if i % 2 == 0 else 60) for i in range(16)],
    },
    'jpop': {
        'kick':  [(0, 95), (6, 70), (8, 90), (14, 50)],
        'snare': [(4, 95), (12, 100)],
        'hihat': [(i, 65 + (i % 2) * 20) for i in range(0, 16, 2)],
    },
    'phonk': {
        'kick':  [(0, 120), (4, 60), (8, 110), (11, 70), (14, 50)],
        'snare': [(4, 115), (12, 115)],
        'hihat': [(i, 55 + (25 if i % 2 == 0 else 0)) for i in range(16)] +
                 [(i + 0.33, 35) for i in range(0, 16, 3)],  # Triplet rolls
    },
}

# Genre-specific BPM ranges
GENRE_BPM = {
    'pop': (100, 130), 'hiphop': (70, 100), 'trap': (130, 165),
    'cinematic': (60, 100), 'classical': (70, 140), 'techno': (125, 150),
    'jpop': (110, 145), 'phonk': (130, 160),
}

# Genre-specific scale preferences
GENRE_SCALES = {
    'pop': ['major', 'mixolydian'],
    'hiphop': ['minor', 'dorian', 'pentatonic_minor'],
    'trap': ['minor', 'phrygian', 'pentatonic_minor'],
    'cinematic': ['minor', 'harmonic_minor', 'lydian'],
    'classical': ['major', 'minor', 'dorian', 'lydian'],
    'techno': ['minor', 'dorian', 'pentatonic_minor'],
    'jpop': ['major', 'lydian', 'japanese', 'pentatonic_major'],
    'phonk': ['minor', 'phrygian', 'blues'],
}

# GM instrument numbers for each track type
GENRE_INSTRUMENTS = {
    'pop': {'chords': 0, 'lead': 80, 'bass': 33, 'pad': 88, 'arp': 80},
    'hiphop': {'chords': 4, 'lead': 80, 'bass': 38, 'pad': 89, 'arp': 81},
    'trap': {'chords': 81, 'lead': 80, 'bass': 38, 'pad': 95, 'arp': 81},
    'cinematic': {'chords': 48, 'lead': 68, 'bass': 43, 'pad': 92, 'arp': 46},
    'classical': {'chords': 0, 'lead': 40, 'bass': 42, 'pad': 48, 'arp': 46},
    'techno': {'chords': 81, 'lead': 80, 'bass': 38, 'pad': 95, 'arp': 81},
    'jpop': {'chords': 0, 'lead': 80, 'bass': 33, 'pad': 89, 'arp': 11},
    'phonk': {'chords': 4, 'lead': 80, 'bass': 87, 'pad': 95, 'arp': 81},
}

# ═══════════════════════════════════════════════════════════════════════
#  REFACTORED SONG STRUCTURE TEMPLATES (Pro Phrasing Edition)
# ═══════════════════════════════════════════════════════════════════════

STRUCTURE_TEMPLATES = {
    'pop': [
        ('intro', 8), ('verse', 16), ('pre_chorus', 8), ('chorus', 16),
        ('verse', 16), ('pre_chorus', 8), ('chorus', 16),
        ('bridge', 8), ('chorus', 16), ('outro', 8),
    ],
    'hiphop': [
        ('intro', 8), ('verse', 16), ('chorus', 8), ('verse', 16),
        ('chorus', 8), ('verse', 16), ('chorus', 16), ('outro', 8),
    ],
    'trap': [
        ('intro', 8), ('build', 8), ('drop', 16), ('verse', 16),
        ('build', 8), ('drop', 16), ('break', 4),
        ('verse', 16), ('drop', 16), ('outro', 8),
    ],
    'cinematic': [
        ('intro', 16), ('build', 16), ('climax', 16), ('break', 8),
        ('tension', 16), ('build', 8), ('climax', 16),
        ('resolution', 16), ('outro', 16),
    ],
    'classical': [
        ('exposition', 32), ('bridge', 8), ('development', 32),
        ('break', 4), ('recapitulation', 32), ('coda', 16),
    ],
    'techno': [
        ('intro', 16), ('build', 16), ('drop', 32), ('break', 8),
        ('build', 8), ('drop', 32), ('outro', 16),
    ],
    'jpop': [
        ('intro', 8), ('verse', 16), ('pre_chorus', 8), ('chorus', 16),
        ('verse', 16), ('pre_chorus', 8), ('chorus', 16),
        ('bridge', 12), ('chorus', 16), ('outro', 8),
    ],
    'phonk': [
        ('intro', 8), ('build', 8), ('drop', 16), ('verse', 16),
        ('break', 4), ('drop', 16), ('bridge', 8), ('drop', 16), ('outro', 8),
    ],
}


# ═══════════════════════════════════════════════════════════════════════
#  HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

def note_name_to_midi(note: str, octave: int = 4) -> int:
    """Convert note name to MIDI number."""
    base = note[:2] if len(note) > 1 and note[1] in '#b' else note[0]
    return NOTE_TO_MIDI.get(base, 0) + (octave + 1) * 12


def get_chord_midi_notes(root: str, quality: str, octave: int = 4) -> List[int]:
    """Get MIDI notes for a chord."""
    root_midi = note_name_to_midi(root, octave)
    # Normalize quality
    q = quality.lower().strip()
    intervals = CHORD_INTERVALS.get(q)
    if not intervals:
        if 'min' in q and '7' in q:
            intervals = CHORD_INTERVALS['min7']
        elif 'maj' in q and '7' in q:
            intervals = CHORD_INTERVALS['maj7']
        elif 'dim' in q:
            intervals = CHORD_INTERVALS['dim']
        elif 'aug' in q:
            intervals = CHORD_INTERVALS['aug']
        elif 'sus4' in q:
            intervals = CHORD_INTERVALS['sus4']
        elif 'sus2' in q:
            intervals = CHORD_INTERVALS['sus2']
        elif '7' in q:
            intervals = CHORD_INTERVALS['7']
        elif 'min' in q:
            intervals = CHORD_INTERVALS['minor']
        else:
            intervals = CHORD_INTERVALS['major']
    return [root_midi + i for i in intervals]


def parse_chord_string(chord_str: str) -> Tuple[str, str]:
    """Parse 'Amin7' → ('A', 'min7'), 'F#maj7' → ('F#', 'maj7')."""
    if not chord_str:
        return ('C', 'major')

    # Handle sharps/flats
    if len(chord_str) > 1 and chord_str[1] in '#b':
        root = chord_str[:2]
        quality = chord_str[2:] if len(chord_str) > 2 else 'major'
    else:
        root = chord_str[0]
        quality = chord_str[1:] if len(chord_str) > 1 else 'major'

    if not quality:
        quality = 'major'

    return root, quality


def get_scale_notes(root: str, scale_type: str, octave: int = 4) -> List[int]:
    """Get MIDI notes for a scale."""
    root_midi = note_name_to_midi(root, octave)
    intervals = SCALE_INTERVALS.get(scale_type, SCALE_INTERVALS['major'])
    return [root_midi + i for i in intervals]


def weighted_choice(options: Dict[str, float]) -> str:
    """Choose from weighted options."""
    if not options:
        return 'Cmaj7'
    items = list(options.items())
    weights = [w for _, w in items]
    total = sum(weights)
    if total == 0:
        return random.choice([k for k, _ in items])
    r = random.uniform(0, total)
    cumulative = 0
    for item, weight in items:
        cumulative += weight
        if r <= cumulative:
            return item
    return items[-1][0]


def humanize(value: float, amount: float = 0.015) -> float:
    """Add small random variation for human feel."""
    return max(0, value + random.uniform(-amount, amount))


def humanize_velocity(vel: int, amount: int = 12) -> int:
    """Humanize MIDI velocity."""
    return max(1, min(127, vel + random.randint(-amount, amount)))


# ═══════════════════════════════════════════════════════════════════════
#  COMPOSITION CONFIG
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class CompositionConfig:
    """User-configurable composition parameters."""
    genre: str = 'pop'
    bpm: Optional[float] = None          # None = auto from seeds
    starting_chord: Optional[str] = None  # None = auto from seeds
    key: Optional[str] = None            # None = auto from seeds
    complexity: int = 5                   # 0-10
    duration_bars: int = 0               # 0 = auto from structure template
    fusion: Optional[Any] = None         # FusionConfig for cross-genre fusion
    mutation: float = 0.0                # 0-1, how much to mutate/randomize patterns

    # Track enables and volumes (0.0 - 1.0)
    tracks: Dict[str, dict] = field(default_factory=lambda: {
        'drums': {'enabled': True, 'volume': 0.85, 'instrument': None},
        'bass': {'enabled': True, 'volume': 0.8, 'instrument': None},
        'chords': {'enabled': True, 'volume': 0.7, 'instrument': None},
        'lead': {'enabled': True, 'volume': 0.75, 'instrument': None},
        'pad': {'enabled': True, 'volume': 0.6, 'instrument': None},
        'arp': {'enabled': False, 'volume': 0.5, 'instrument': None},
    })

    humanize_amount: float = 0.6  # 0-1, how much humanization
    swing: float = 0.0            # 0-1, swing amount
    seed_value: Optional[int] = None  # Random seed for reproducibility


# ═══════════════════════════════════════════════════════════════════════
#  COMPOSITION ENGINE
# ═══════════════════════════════════════════════════════════════════════

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
        # Pattern learning systems
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
            print(f"◢ LOADED {len(self.seeds)} seeds ({len(self.genre_seeds)} genres) ◣")

        # Load genre matrices
        matrices_dir = self.seeds_dir / "matrices"
        if matrices_dir.exists():
            for f in matrices_dir.glob("matrix_*.json"):
                genre = f.stem.replace("matrix_", "")
                with open(f, 'r', encoding='utf-8') as fh:
                    self.genre_matrices[genre] = json.load(fh)
            if 'global' in self.genre_matrices:
                self.global_matrix = self.genre_matrices.pop('global')
            print(f"◢ LOADED {len(self.genre_matrices)} genre matrices ◣")

        # Load learned rhythm patterns
        if LEARNED_PATTERNS_AVAILABLE:
            try:
                self.pattern_generator = LearnedPatternGenerator()
                self.pattern_generator.load_from_seeds(self.seeds)
                total_patterns = sum(len(p) for p in self.pattern_generator.global_patterns.values())
                print(f"◢ LOADED {total_patterns} rhythm patterns ◣")
            except Exception as e:
                print(f"◢ Rhythm patterns not available: {e} ◣")
                self.pattern_generator = None

        # Load learned bass patterns
        self.bass_patterns = {'global': [], 'by_genre': {}}
        try:
            bass_count = 0
            for seed in self.seeds:
                genre = seed.get('genre', 'unknown')
                if genre not in self.bass_patterns['by_genre']:
                    self.bass_patterns['by_genre'][genre] = []

                # Get bass patterns from instrument_patterns.pattern_transitions.bass
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

                    # Also check drum_patterns.bass
                    drum_pats = inst_patterns.get('drum_patterns', {})
                    if isinstance(drum_pats, dict):
                        bass_pats = drum_pats.get('bass', [])
                        if isinstance(bass_pats, list):
                            for p in bass_pats:
                                if isinstance(p, list) and len(p) == 16:
                                    self.bass_patterns['global'].append(p)
                                    self.bass_patterns['by_genre'][genre].append(p)
                                    bass_count += 1

            # Deduplicate
            self.bass_patterns['global'] = [list(p) for p in set(tuple(p) for p in self.bass_patterns['global'])]
            for genre in self.bass_patterns['by_genre']:
                self.bass_patterns['by_genre'][genre] = [list(p) for p in set(tuple(p) for p in self.bass_patterns['by_genre'][genre])]

            total_bass = len(self.bass_patterns['global'])
            if total_bass > 0:
                print(f"◢ LOADED {total_bass} bass patterns ◣")
        except Exception as e:
            print(f"◢ Bass patterns not available: {e} ◣")

        # Load learned lead/synth patterns
        self.lead_patterns = {'global': [], 'by_genre': {}}
        try:
            lead_count = 0
            for seed in self.seeds:
                genre = seed.get('genre', 'unknown')
                if genre not in self.lead_patterns['by_genre']:
                    self.lead_patterns['by_genre'][genre] = []

                inst_patterns = seed.get('instrument_patterns', {})
                if isinstance(inst_patterns, dict):
                    # Check pattern_transitions for synth
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

                    # Also check drum_patterns for synth/pad
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

            # Deduplicate
            self.lead_patterns['global'] = [list(p) for p in set(tuple(p) for p in self.lead_patterns['global'])]
            for genre in self.lead_patterns['by_genre']:
                self.lead_patterns['by_genre'][genre] = [list(p) for p in set(tuple(p) for p in self.lead_patterns['by_genre'][genre])]

            total_lead = len(self.lead_patterns['global'])
            if total_lead > 0:
                print(f"◢ LOADED {total_lead} lead patterns ◣")
        except Exception as e:
            print(f"◢ Lead patterns not available: {e} ◣")

        # Initialize fusion engine
        if FUSION_AVAILABLE and self.pattern_generator:
            try:
                self.fusion_engine = GenreFusionEngine(self.pattern_generator)
                print(f"◢ FUSION ENGINE READY ◣")
            except Exception as e:
                print(f"◢ Fusion engine not available: {e} ◣")
                self.fusion_engine = None

        # Initialize smart arrangement engine
        if SMART_ARRANGEMENT_AVAILABLE:
            try:
                self.arrangement_engine = SmartArrangementEngine()
                self.arrangement_engine.load_from_seeds(self.seeds)
            except Exception as e:
                print(f"◢ Smart arrangement not available: {e} ◣")
                self.arrangement_engine = None

        self._loaded = True

    def _ensure_loaded(self):
        if not self._loaded:
            self.load_seeds()

    # ─────────────────────────────────────────────────────────────────
    #  CHORD PROGRESSION GENERATION (Markov Chain + Theory)
    # ─────────────────────────────────────────────────────────────────

    def generate_chord_progression(self, config: CompositionConfig, num_chords: int = 32) -> List[str]:
        self._ensure_loaded()
        matrix = self.genre_matrices.get(config.genre, self.global_matrix)
        if not matrix: return self._theory_fallback_progression(config, num_chords)

        current = config.starting_chord or weighted_choice({k: sum(v.values()) for k, v in matrix.items()})
        progression = [current]
        exploration = config.complexity / 10.0

        # Get key notes once for matching
        key_parts = (config.key or "C major").split()
        root_note = key_parts[0]
        scale_mode = key_parts[1] if len(key_parts) > 1 else "major"
        key_notes = get_scale_notes(root_note, scale_mode)

        for _ in range(num_chords - 1):
            followers = matrix.get(current, {})
            if not followers:
                current = random.choice(list(matrix.keys()))
                progression.append(current)
                continue

            # Apply Key Gravity for lower complexity (prevents chaotic dissonance)
            if config.complexity < 7:
                boosted_followers = {}
                for chord, prob in followers.items():
                    c_root, c_quality = parse_chord_string(chord)
                    # Convert chord notes to pitch classes (0-11)
                    chord_midi = [(note_name_to_midi(c_root, 4) + i) % 12 for i in
                                  CHORD_INTERVALS.get(c_quality, [0, 4, 7])]
                    # Scale matching: 1.0 multiplier per note in key
                    match_score = sum(1 for n in chord_midi if n in key_notes)
                    boosted_followers[chord] = prob * (1.0 + match_score * (1.0 - exploration))
                current = weighted_choice(boosted_followers)
            else:
                # High complexity = full Markov randomness
                current = weighted_choice(followers)

            progression.append(current)
        return progression

    def _theory_fallback_progression(self, config: CompositionConfig,
                                      num_chords: int) -> List[str]:
        """Fallback progression using pure music theory when no seeds exist."""
        key = config.key or 'C major'
        parts = key.split()
        root = parts[0] if parts else 'C'
        is_minor = 'minor' in key.lower()

        root_midi = NOTE_TO_MIDI.get(root, 0)

        if is_minor:
            # Natural minor scale degrees: i, bIII, iv, v, bVI, bVII
            degrees = [
                (0, 'min7'), (3, 'maj7'), (5, 'min7'), (7, 'min7'),
                (8, 'maj7'), (10, 'maj7'), (2, 'dim7'),
            ]
        else:
            # Major scale degrees: I, ii, iii, IV, V, vi, vii°
            degrees = [
                (0, 'maj7'), (2, 'min7'), (4, 'min7'), (5, 'maj7'),
                (7, '7'), (9, 'min7'), (11, 'dim7'),
            ]

        # Common progressions
        common = [
            [0, 3, 4, 0],  # I-IV-V-I
            [0, 5, 3, 4],  # I-vi-IV-V
            [0, 3, 5, 4],  # I-IV-vi-V
            [5, 3, 0, 4],  # vi-IV-I-V
            [0, 4, 5, 3],  # I-V-vi-IV
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
        """Generate song structure with total crash protection."""
        bpm = config.bpm or 120
        target_bars = int(180 * bpm / 240)

        # 1. Get raw structure from template or arrangement engine
        template = STRUCTURE_TEMPLATES.get(config.genre, STRUCTURE_TEMPLATES['pop'])
        raw_result = []

        for s, b in template:
            # Symmetry Fix: Force even phrasing for lower complexity
            if config.complexity < 8:
                quantized_bars = max(4, (b // 4) * 4) if b >= 4 else (2 if b >= 2 else b)
                raw_result.append((s, quantized_bars))
            else:
                raw_result.append((s, b))

        # 2. Safety Check: If for some reason the list is empty, provide a fallback
        if not raw_result:
            raw_result = [('intro', 4), ('verse', 16), ('outro', 8)]

        # 3. Apply Sanity Check (This replaces the old .pop() logic)
        return self._apply_structural_sanity(raw_result)

        return self._apply_structural_sanity(result)

    # ─────────────────────────────────────────────────────────────────
    #  DRUM TRACK GENERATION
    # ─────────────────────────────────────────────────────────────────

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

            # ── SECTION: INTRO — Rhythmic Rumbles ──
            if section_type == 'intro':
                for bar in range(section_bars):
                    bo = (bar_offset + bar) * 4
                    fade = (bar + 1) / max(1, section_bars)

                    # Cinematic deep rumble instead of hi-hats
                    if complexity > 4:
                        for i in range(0, 16, 4):
                            if random.random() < fade * 0.8:
                                notes.append((humanize(bo + i / 4, 0.01 * h_amt), 0.25,
                                              TOM_LOW, humanize_velocity(int(60 * fade), 8)))

            # ── SECTION: OUTRO — Decaying Impacts ──
            elif section_type == 'outro':
                for bar in range(section_bars):
                    bo = (bar_offset + bar) * 4
                    fade = 1.0 - (bar / max(1, section_bars))
                    if fade > 0.2 and bar % 2 == 0:
                        # Sparse, heavy concluding kicks
                        notes.append((humanize(bo, 0.01 * h_amt), 0.5,
                                      KICK, humanize_velocity(int(100 * fade), 10)))

            # ── SECTION: BREAK — Tense Silence ──
            elif section_type == 'break':
                for bar in range(section_bars):
                    bo = (bar_offset + bar) * 4
                    # Subtle cinematic clock-tick effect
                    if complexity > 5 and random.random() < 0.5:
                        notes.append((humanize(bo + 2.0, 0.01 * h_amt), 0.1, HIHAT_CLOSED, 40))

            # ── SECTION: BUILD — Orchestral March ──
            elif section_type == 'build':
                for bar in range(section_bars):
                    bo = (bar_offset + bar) * 4
                    build_pct = (bar + 1) / section_bars

                    # Accelerating Heavy Toms (The "March")
                    step = max(1, int(4 / (build_pct * 4)))
                    for i in range(0, 16, step):
                        if random.random() < build_pct * 0.9:
                            drum_choice = random.choice([TOM_MID, TOM_LOW])
                            notes.append((humanize(bo + i / 4, 0.008 * h_amt), 0.25,
                                          drum_choice, humanize_velocity(int(90 * build_pct), 10)))

                    # Probabilistic massive fill at the end of the build
                    if bar == section_bars - 1 and random.random() < 0.8:
                        self._add_cinematic_fill(notes, bo, complexity, 1.0, h_amt)

            # ── NORMAL SECTIONS (Cinematic Grooves) ──
            else:
                pattern_shift = 1 if (section_type == 'verse' and verse_count > 1) else 0

                for bar in range(section_bars):
                    bo = (bar_offset + bar) * 4
                    is_first_bar = (bar == 0)

                    # LOOP-SAFE CINEMATIC IMPACT: Kick + Low Tom on downbeat (probabilistic)
                    if is_first_bar and section_type in ('chorus', 'drop', 'climax'):
                        if random.random() < 0.4:  # 40% chance so it loops well
                            notes.append((bo, 0.5, KICK, humanize_velocity(115, 8)))
                            notes.append((bo, 0.5, TOM_LOW, humanize_velocity(110, 8)))

                    if use_pdmx:
                        # ── SEED LEARNING LOGIC (Cinematic Mapping) ──
                        k_pat = pdmx_kick[bar % len(pdmx_kick)] if pdmx_kick else [0] * 16
                        s_pat = pdmx_snare[bar % len(pdmx_snare)] if pdmx_snare else [0] * 16

                        for step in range(16):
                            time = bo + (step * 0.25)
                            # Play learned kick
                            if k_pat[step] > 0 and energy > 0.2:
                                notes.append((humanize(time, 0.01 * h_amt), 0.25, KICK,
                                              humanize_velocity(int(100 * energy), 8)))
                            # Play learned snare (mapped to Heavy Toms for cinematic feel)
                            if s_pat[step] > 0 and energy > 0.3:
                                drum_type = TOM_MID if complexity > 4 else SNARE
                                notes.append((humanize(time, 0.01 * h_amt), 0.25, drum_type,
                                              humanize_velocity(int(90 * energy), 10)))
                    else:
                        # ── ALGORITHMIC CINEMATIC GROOVE GENERATOR ──
                        # Generates unique, galloping orchestral rhythms dynamically

                        # 1. Pounding Downbeats (Kicks)
                        if energy > 0.3:
                            notes.append(
                                (humanize(bo, 0.01 * h_amt), 0.25, KICK, humanize_velocity(int(115 * energy), 8)))
                            if random.random() < (mutation * 0.8):  # Wildcard kick
                                notes.append((humanize(bo + 2.5, 0.01 * h_amt), 0.25, KICK,
                                              humanize_velocity(int(90 * energy), 8)))

                        # 2. The "Gallop" Engine (Mid & High Toms)
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

                        # 3. Massive Orchestral Snare/Anvil on the 3
                        if energy > 0.5:
                            notes.append((humanize(bo + 2.0, 0.01 * h_amt), 0.25,
                                          SNARE, humanize_velocity(int(110 * energy), 5)))

                    # ── LOOP-SAFE PROBABILISTIC FILL ──
                    if bar == section_bars - 1 and complexity > 2:
                        # Higher mutation = more frequent fills, but never 100%
                        fill_chance = 0.2 + (mutation * 0.3)
                        if random.random() < fill_chance:
                            self._add_cinematic_fill(notes, bo, complexity, energy, h_amt)

            bar_offset += section_bars
            section_index += 1

        return notes

    def _add_cinematic_fill(self, notes, beat_offset, complexity, energy, h_amt):
        """Heavy, rolling orchestral toms instead of a standard snare fill."""
        if complexity <= 4:
            # Pounding low toms
            for pos in [12, 14]:
                notes.append((humanize(beat_offset + pos / 4, 0.01 * h_amt), 0.25,
                              TOM_LOW, humanize_velocity(int(100 * energy), 8)))
        else:
            # Rolling toms (High to Low)
            fill_notes = [(8, TOM_HIGH), (10, TOM_HIGH), (11, TOM_MID),
                          (12, TOM_MID), (13, TOM_LOW), (14, TOM_LOW), (15, KICK)]
            for pos, drum in fill_notes:
                vel = 70 + (pos - 8) * 3
                if random.random() < 0.9:
                    notes.append((humanize(beat_offset + pos / 4, 0.008 * h_amt), 0.2,
                                  drum, humanize_velocity(min(127, int(vel * energy)), 10)))

            # Probabilistic crash to protect the infinite loop
            if random.random() < 0.3:
                notes.append((beat_offset + 3.95, 0.1, CRASH, humanize_velocity(100, 8)))


    #def _add_drum_roll(self, notes, beat_offset, complexity, h_amt):
        """Add a snare/tom roll (e.g., after a break to re-enter)."""
        # Accelerating roll: starts slow, gets faster
        #positions = []
        #if complexity <= 4:
            # Quarter note roll
            #positions = [0, 1, 2, 2.5, 3, 3.25, 3.5, 3.75]
        #else:
            # 16th note accelerating roll
            #t = 0
            #interval = 0.5
            #while t < 4.0:
                #positions.append(t)
                #t += interval
                #interval = max(0.125, interval * 0.8)  # Accelerate

        #for i, pos in enumerate(positions):
            #vel = 50 + int(60 * (i / max(1, len(positions) - 1)))
            #drum = SNARE if i % 3 != 2 else TOM_MID
            #notes.append((humanize(beat_offset + pos, 0.006*h_amt), 0.12,
                          #drum, humanize_velocity(min(120, vel), 6)))


    # ─────────────────────────────────────────────────────────────────
    #  BASS TRACK GENERATION
    # ─────────────────────────────────────────────────────────────────

    def generate_bass_track(self, config: CompositionConfig,
                            chord_progression: List[str],
                            structure: List[Tuple[str, int]]) -> List[Tuple[float, float, int, int]]:
        """Generate bass line following chord roots with rhythmic patterns."""
        # Check if we have learned bass patterns
        if hasattr(self, 'bass_patterns') and self.bass_patterns.get('global'):
            return self._generate_bass_from_learned(config, chord_progression, structure)

        # Fallback to original generation
        return self._generate_bass_fallback(config, chord_progression, structure)

    def _generate_bass_from_learned(self, config: CompositionConfig,
                                    chord_progression: List[str],
                                    structure: List[Tuple[str, int]]) -> List[Tuple[float, float, int, int]]:
        """Generate bass using learned patterns."""
        notes = []
        volume = config.tracks.get('bass', {}).get('volume', 0.8)
        base_vel = int(90 * volume)
        h_amt = config.humanize_amount
        mutation = getattr(config, 'mutation', 0.0)

        # Get patterns for this genre or global
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
                root_midi = note_name_to_midi(root, 2)  # Bass octave
                fifth = root_midi + 7

                # Switch patterns occasionally (more often with higher mutation)
                switch_chance = 0.2 + mutation * 0.3
                if random.random() < switch_chance:
                    current_pattern = random.choice(patterns)

                # Apply mutation to pattern
                working_pattern = self._mutate_pattern(current_pattern, mutation)

                # Section energy adjustments
                section_energy = energy
                if section_type == 'intro':
                    fade = (local_bar + 1) / max(1, section_bars)
                    section_energy *= fade
                elif section_type == 'outro':
                    fade = 1.0 - (local_bar / max(1, section_bars))
                    section_energy *= fade
                elif section_type == 'break':
                    section_energy *= 0.3

                # Convert pattern to MIDI
                for step in range(16):
                    if working_pattern[step] == 1:
                        step_time = bar_time + (step / 4)

                        # Choose note based on position (with mutation adding randomness)
                        if step == 0:
                            midi_note = root_midi
                        elif step == 8:
                            midi_note = random.choice([root_midi, fifth])
                        elif step in [4, 12]:
                            midi_note = random.choice([root_midi, fifth, root_midi + 3])
                        else:
                            midi_note = random.choice([root_midi, fifth])

                    # Mutation can add more note variety
                        # SAFE MUTATION: Keep it in the scale
                        if mutation > 0.5 and random.random() < mutation * 0.3:
                            scale_notes = get_scale_notes(root, 'minor' if 'min' in quality else 'major', 2)
                            if scale_notes:
                                midi_note = random.choice(scale_notes)

                        # Keep in bass range
                        while midi_note > 60:
                            midi_note -= 12
                        while midi_note < 28:
                            midi_note += 12

                        # Duration until next hit
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

                        # Humanize
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
        """Apply mutation to a pattern. Higher mutation = more changes."""
        if mutation_rate <= 0:
            return pattern

        mutated = list(pattern)
        for i in range(len(mutated)):
            if random.random() < mutation_rate * 0.3:
                if mutated[i] == 0:
                    # Maybe add a hit
                    if random.random() < mutation_rate * 0.5:
                        mutated[i] = 1
                else:
                    # Maybe remove or shift a hit
                    if random.random() < mutation_rate * 0.3:
                        mutated[i] = 0
                    elif random.random() < mutation_rate * 0.4:
                        # Shift the hit
                        new_pos = i + random.choice([-1, 1])
                        if 0 <= new_pos < len(mutated):
                            mutated[i] = 0
                            mutated[new_pos] = 1
        return mutated

    def _generate_bass_fallback(self, config: CompositionConfig,
                                chord_progression: List[str],
                                structure: List[Tuple[str, int]]) -> List[Tuple[float, float, int, int]]:
        """Original bass generation fallback."""
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
                root_midi = note_name_to_midi(root, 2)  # Bass octave

                # Bass pattern depends on complexity and energy
                if energy < 0.2:
                    # Sparse: whole notes
                    notes.append((
                        humanize(beat_pos, 0.01 * config.humanize_amount),
                        3.5, root_midi, humanize_velocity(int(base_vel * energy * 1.5), 8)
                    ))
                elif complexity <= 3:
                    # Simple: quarter notes on root
                    for beat in range(4):
                        notes.append((
                            humanize(beat_pos + beat, 0.01 * config.humanize_amount),
                            0.9, root_midi, humanize_velocity(base_vel, 8)
                        ))
                elif complexity <= 6:
                    # Medium: root + fifth with eighth notes
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
                    # Complex: walking bass / melodic bass
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
        """Generate chord voicings with voice leading."""
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

                # Voice leading: minimize movement from previous chord
                if prev_voicing and len(chord_notes) > 0:
                    chord_notes = self._voice_lead(prev_voicing, chord_notes)

                prev_voicing = chord_notes

                # Rhythm depends on section and complexity
                if energy < 0.15:
                    # Sparse: whole chord
                    for note in chord_notes:
                        notes.append((
                            humanize(beat_pos, 0.01),
                            3.8, note, humanize_velocity(int(base_vel * 0.5), 6)
                        ))
                elif complexity <= 3:
                    # Simple: whole notes
                    for note in chord_notes:
                        notes.append((
                            beat_pos, 3.8, note,
                            humanize_velocity(int(base_vel * energy), 6)
                        ))
                elif complexity <= 6:
                    # Rhythmic: stabs on beats 1 and 3
                    for beat_offset in [0, 2]:
                        for note in chord_notes:
                            notes.append((
                                humanize(beat_pos + beat_offset, 0.015 * config.humanize_amount),
                                1.5, note,
                                humanize_velocity(int(base_vel * energy), 8)
                            ))
                else:
                    # Complex: arpeggiated / syncopated
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
        """Generate a lead melody that follows the chords and scale."""
        # Check if we have learned lead patterns
        if hasattr(self, 'lead_patterns') and self.lead_patterns.get('global'):
            return self._generate_lead_from_learned(config, chord_progression, structure)

        # Fallback to original generation
        return self._generate_lead_fallback(config, chord_progression, structure)

    def _generate_lead_from_learned(self, config: CompositionConfig,
                                    chord_progression: List[str],
                                    structure: List[Tuple[str, int]]) -> List[Tuple[float, float, int, int]]:
        """Generate lead using learned patterns."""
        notes = []
        volume = config.tracks.get('lead', {}).get('volume', 0.75)
        base_vel = int(85 * volume)
        h_amt = config.humanize_amount
        complexity = config.complexity

        # Get patterns for this genre or global
        genre = config.genre
        if genre in self.lead_patterns['by_genre'] and self.lead_patterns['by_genre'][genre]:
            patterns = self.lead_patterns['by_genre'][genre]
        else:
            patterns = self.lead_patterns['global']

        if not patterns:
            return self._generate_lead_fallback(config, chord_progression, structure)

        # Determine scale
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

            # Lead plays less in intro/outro
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

                # Switch patterns occasionally
                if random.random() < 0.25:
                    current_pattern = random.choice(patterns)

                section_energy = energy
                if section_type == 'break':
                    section_energy *= 0.4
                elif section_type in ('chorus', 'drop', 'climax'):
                    section_energy *= 1.1

                # Convert pattern to MIDI
                for step in range(16):
                    if current_pattern[step] == 1:
                        step_time = bar_time + (step / 4)

                        # Choose note with melodic motion
                        if prev_note is None:
                            midi_note = random.choice(chord_notes)
                        else:
                            # Prefer stepwise motion
                            candidates = [n for n in scale if abs(n - prev_note) <= 4]
                            if not candidates:
                                candidates = scale
                            midi_note = random.choice(candidates)

                        # Keep in playable range
                        while midi_note > 84:
                            midi_note -= 12
                        while midi_note < 60:
                            midi_note += 12

                        # Duration
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

                        # Humanize
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
        """Original lead generation fallback."""
        notes = []
        complexity = config.complexity
        volume = config.tracks.get('lead', {}).get('volume', 0.75)
        base_vel = int(85 * volume)

        # Determine scale
        key = config.key or 'C major'
        parts = key.split()
        root = parts[0] if parts else 'C'
        is_minor = 'minor' in key.lower()

        scale_choices = GENRE_SCALES.get(config.genre, ['major'])
        scale_type = random.choice(scale_choices)
        scale = get_scale_notes(root, scale_type, 5)  # Lead in octave 5

        beat_pos = 0
        chord_idx = 0
        prev_note = None
        phrase_counter = 0

        for section_type, section_bars in structure:
            energy = self._section_energy(section_type)

            # Lead only plays in certain sections
            if section_type in ('intro', 'outro', 'break') and complexity < 7:
                beat_pos += section_bars * 4
                chord_idx += section_bars
                continue

            for bar in range(section_bars):
                if chord_idx >= len(chord_progression):
                    chord_idx = chord_idx % max(1, len(chord_progression))

                c_root, c_quality = parse_chord_string(chord_progression[chord_idx])
                chord_notes = get_chord_midi_notes(c_root, c_quality, 5)

                # Phrase density based on complexity
                if complexity <= 3:
                    positions = [0, 2]
                elif complexity <= 6:
                    positions = [0, 1, 2, 3]
                else:
                    positions = [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5]

                for pos in positions:
                    if random.random() < 0.6 * energy:
                        # Choose note: prefer chord tones, add scale passing tones
                        if random.random() < 0.6:
                            note = random.choice(chord_notes)
                        else:
                            note = random.choice(scale) if scale else random.choice(chord_notes)

                        # Stepwise motion: prefer small intervals from prev note
                        if prev_note and abs(note - prev_note) > 7:
                            # Try to find a closer note
                            candidates = [n for n in scale + chord_notes if abs(n - prev_note) <= 5]
                            if candidates:
                                note = random.choice(candidates)

                        # Duration variety
                        dur_options = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0]
                        dur = random.choice(dur_options[:2 + complexity // 2])

                        # Rests for musicality
                        phrase_counter += 1
                        if phrase_counter > 4 + complexity and random.random() < 0.4:
                            phrase_counter = 0
                            continue  # Rest

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
        """Generates a dynamic cinematic pad that learns from seeds or pulses with energy."""
        notes = []
        volume = config.tracks.get('pad', {}).get('volume', 0.6)
        base_vel = int(65 * volume)
        mutation = getattr(config, 'mutation', 0.0)

        # Check for seed DNA
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

                # Safely extract the root and quality regardless of format
                chord_data = chord_progression[chord_idx]
                if isinstance(chord_data, tuple):
                    root, quality = chord_data[3], chord_data[4]
                else:
                    root, quality = parse_chord_string(chord_data)

                chord_notes = get_chord_midi_notes(root, quality, 3)  # Register 3 for warmth
                if not chord_notes:
                    chord_notes = [note_name_to_midi(root, 3)]

                bo = beat_pos + (bar * 4)

                if has_seed and pdmx_pad:
                    # ── LEARNED FROM SEED ──
                    pattern = pdmx_pad[bar % len(pdmx_pad)]
                    for step in range(16):
                        if pattern[step] > 0:
                            for note in chord_notes[:3]:
                                time = bo + (step * 0.25)
                                # Add a little octave variation based on mutation
                                final_note = note + 12 if (mutation > 0.6 and random.random() < 0.2) else note
                                notes.append((humanize(time, 0.01), 0.25, final_note,
                                              humanize_velocity(int(base_vel * pad_energy * 1.2), 6)))
                else:
                    # ── CREATIVE CINEMATIC PULSE ──
                    if config.complexity < 4 or energy < 0.4:
                        # Calm sections: Standard sustained pad
                        for note in chord_notes[:3]:
                            notes.append((bo, 3.8, note, humanize_velocity(int(base_vel * pad_energy), 6)))
                    else:
                        # High-tension sections: 8th-note Tremolo Pulse
                        swell_pattern = [0.8, 0.9, 1.1, 1.2, 1.3, 1.1, 0.9, 0.8]

                        for step in range(8):
                            time = bo + (step * 0.5)
                            # Create a swelling volume effect
                            swell = swell_pattern[step] + (mutation * 0.1)

                            for i, note in enumerate(chord_notes[:3]):
                                # Offset the chord notes microscopically for a massive stereo width feel
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
        """Generate arpeggiated patterns."""
        notes = []
        complexity = config.complexity
        volume = config.tracks.get('arp', {}).get('volume', 0.5)
        base_vel = int(70 * volume)

        # Arp patterns (note index offsets within chord)
        arp_patterns = [
            [0, 1, 2, 1],           # Up-down
            [0, 1, 2, 3],           # Up
            [3, 2, 1, 0],           # Down
            [0, 2, 1, 3],           # Skip
            [0, 1, 2, 3, 2, 1],    # Wave
            [0, 0, 1, 2, 2, 3],    # Double-hit
        ]
        arp_pattern = random.choice(arp_patterns[:1 + complexity // 2])

        # Arp speed (in 16th notes)
        if complexity <= 3:
            step = 1.0  # Quarter notes
        elif complexity <= 6:
            step = 0.5  # Eighth notes
        else:
            step = 0.25  # Sixteenth notes

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
        """Minimize voice movement between chords."""
        if not prev_notes or not new_notes:
            return new_notes

        result = []
        used = set()
        for prev in prev_notes:
            best = None
            best_dist = float('inf')
            for n in new_notes:
                # Try note in different octaves
                for octave_shift in [-12, 0, 12]:
                    candidate = n + octave_shift
                    dist = abs(candidate - prev)
                    if dist < best_dist and candidate not in used:
                        best_dist = dist
                        best = candidate
            if best is not None:
                result.append(best)
                used.add(best)

        # Add remaining new notes
        for n in new_notes:
            if n not in used and len(result) < len(new_notes):
                result.append(n)

        return result if result else new_notes

    # ─────────────────────────────────────────────────────────────────
    #  SECTION ENERGY MAPPING
    # ─────────────────────────────────────────────────────────────────

    def _section_energy(self, section_type: str) -> float:
        """Map section type to energy level (0-1)."""
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
        """Generate drums using fused patterns from multiple genres."""
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
        """Generate bass using fused patterns from multiple genres."""
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
        """Generate lead using fused patterns from multiple genres."""
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
    #  MAIN COMPOSITION METHOD
    # ─────────────────────────────────────────────────────────────────

    def compose(self, config: CompositionConfig) -> dict:
        self._ensure_loaded()
        if config.seed_value is not None: random.seed(config.seed_value)

        # Standardizing BPM & Key
        if config.bpm is None: config.bpm = random.uniform(*GENRE_BPM.get(config.genre, (100, 130)))
        if config.key is None: config.key = f"{random.choice(['C', 'D', 'E', 'F', 'G', 'A', 'Bb'])} {random.choice(['major', 'minor'])}"

        structure = self.generate_structure(config)
        total_bars = sum(b for _, b in structure)
        chord_progression = self.generate_chord_progression(config, total_bars + 4)

        fusion_config = getattr(config, 'fusion', None)
        using_fusion = fusion_config is not None and self.fusion_engine is not None

        # Generate all tracks
        tracks, track_info = {}, {}

        # Define the mapping for track names to their generator functions
        track_map = {
            'drums': 'generate_drum_track',  # Fixes the plural/singular mismatch
            'bass': 'generate_bass_track',
            'chords': 'generate_chord_track',
            'lead': 'generate_lead_track',
            'pad': 'generate_pad_track',
            'arp': 'generate_arp_track'
        }

        for t_name, func_name in track_map.items():
            if config.tracks.get(t_name, {}).get('enabled', False):
                # Safely get the generator function
                gen_fn = getattr(self, func_name)

                if t_name == 'drums':
                    # Check for fusion mode first
                    if using_fusion:
                        tracks[t_name] = self._generate_fused_drums(fusion_config, structure, config)
                    else:
                        tracks[t_name] = gen_fn(config, structure, total_bars)
                else:
                    # Check for fusion for bass/lead if you implemented them
                    if using_fusion and t_name in ['bass', 'lead']:
                        fused_fn = getattr(self, f"_generate_fused_{t_name}")
                        tracks[t_name] = fused_fn(fusion_config, chord_progression, structure, config)
                    else:
                        tracks[t_name] = gen_fn(config, chord_progression, structure)

                # Assign MIDI channel and program
                inst = config.tracks[t_name].get('instrument') or \
                       GENRE_INSTRUMENTS.get(config.genre, {}).get(t_name, 0)

                # Channel 9 is reserved for drums in MIDI
                channel = 9 if t_name == 'drums' else list(track_map.keys()).index(t_name)
                track_info[t_name] = {'channel': channel, 'program': inst}
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
        """Generates multiple unique cinematic songs with distinct DNA."""
        os.makedirs(base_output_dir, exist_ok=True)

        for i in range(count):
            comp_val = random.randint(4, 10)  # Cinematic tracks usually need higher complexity
            sync_val = random.randint(3, 10)
            mut_val = random.uniform(0.3, 0.8)

            config = CompositionConfig(
                genre=genre,
                bpm=random.uniform(80, 130),  # Good range for epic scores
                complexity=comp_val,
                mutation=mut_val,
                seed_value=random.randint(0, 999999)
            )
            setattr(config, 'syncopation', sync_val)

            # Ensure Arp/Texture tracks are enabled for full orchestral/cinematic feel
            if active_tracks is not None:
                config.tracks = active_tracks
            else:
                config.tracks['arp']['enabled'] = True

            composition = self.compose(config)

            key_str = composition['config']['key'].replace(' ', '')
            filename = f"V4_{genre}_{i + 1}_{key_str}_C{comp_val}_M{int(mut_val * 10)}.mid"

            self.export_midi(composition, os.path.join(base_output_dir, filename))
            print(f"◢ V4 BATCH: {i + 1}/{count} | Key: {key_str} | Complexity: {comp_val}")

        print(f"◢ V4 BATCH COMPLETE: {count} epic tracks exported ◣")

    # ─────────────────────────────────────────────────────────────────
    #  MIDI EXPORT
    # ─────────────────────────────────────────────────────────────────

    def export_midi(self, composition: dict, filepath: str) -> str:
        if not MIDI_AVAILABLE: return ""
        midi = MIDIFile(len(composition['tracks']), file_format=1)

        # 1. ADD HORIZONTAL MARKERS (For Adaptive Game Audio)
        current_bar = 0
        for section_type, section_bars in composition['structure']:
            marker_time = current_bar * 4
            midi.addText(0, marker_time, section_type.upper())
            current_bar += section_bars

        # 2. PROCESS TRACKS
        for i, (name, events) in enumerate(composition['tracks'].items()):
            info = composition['track_info'].get(name, {})
            midi.addTempo(i, 0, composition['config']['bpm'])

            # Sort for the Overlap Killer
            events.sort(key=lambda x: x[0])

            seen_notes = set()
            for idx, e in enumerate(events):
                time, duration, pitch, vel = e[0], e[1], e[2], e[3]

                # --- OVERLAP KILLER ---
                for future_e in events[idx + 1:]:
                    if future_e[2] == pitch and future_e[0] < (time + duration):
                        duration = max(0.05, future_e[0] - time - 0.01)
                        break

                note_key = (round(time, 3), pitch)
                if note_key not in seen_notes and duration > 0:
                    seen_notes.add(note_key)
                    midi.addNote(i, info.get('channel', 0), pitch, time, duration, vel)

        with open(filepath, 'wb') as f:
            midi.writeFile(f)
        return filepath

    def _apply_structural_sanity(self, structure: List[Tuple[str, int]]) -> List[Tuple[str, int]]:
        """A robust re-organizer that ensures a logical flow without crashing."""
        if not structure:
            return [('intro', 4), ('verse', 16), ('outro', 8)]

        # Separate sections into buckets
        intros = [s for s in structure if s[0] == 'intro']
        outros = [s for s in structure if s[0] == 'outro']
        mains = [s for s in structure if s[0] not in ['intro', 'outro', 'build', 'break']]
        utilities = [s for s in structure if s[0] in ['build', 'break', 'bridge']]

        sanitized = []

        # Narrative Rule 1: Always start with an Intro
        if intros:
            sanitized.append(intros[0])
        else:
            sanitized.append(('intro', 4))

        # Narrative Rule 2: Ensure there is at least one Main section (Verse/Chorus)
        if not mains:
            sanitized.append(('verse', 16))
        else:
            # Add all main and utility sections in their original relative order
            for s in structure:
                if s[0] not in ['intro', 'outro']:
                    sanitized.append(s)

        # Narrative Rule 3: Always end with an Outro
        # Check if the last section added is already an outro to avoid duplicates
        if sanitized[-1][0] != 'outro':
            if outros:
                sanitized.append(outros[-1])
            else:
                sanitized.append(('outro', 8))

        return sanitized



# ═══════════════════════════════════════════════════════════════════════
#  CONVENIENCE FUNCTION
# ═══════════════════════════════════════════════════════════════════════

def quick_compose(genre='pop', bpm=None, key=None, complexity=5,
                  starting_chord=None, output_path='generated_song.mid',
                  seeds_dir='seeds') -> str:
    """Quick composition with sensible defaults."""
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
