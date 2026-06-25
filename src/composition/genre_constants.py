import random
from typing import List, Dict, Tuple

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
    'japanese': [0, 1, 5, 7, 8],
    'chromatic': list(range(12)),
}

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
                 [(i + 0.5, 40) for i in range(0, 16, 2)],
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
        'kick':  [(i * 4, 110) for i in range(4)],
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
                 [(i + 0.33, 35) for i in range(0, 16, 3)],
    },
    'edm': {
        'kick':  [(i * 4, 112) for i in range(4)],
        'snare': [(4, 100), (12, 100)],
        'hihat': [(i, 70 + (10 if i % 4 == 0 else 0)) for i in range(16)],
    },
    'house': {
        'kick':  [(i * 4, 108) for i in range(4)],
        'snare': [(4, 95), (12, 95)],
        'hihat': [(i * 2, 75) for i in range(8)],
    },
}

GENRE_BPM = {
    'pop': (100, 130), 'hiphop': (70, 100), 'trap': (130, 165),
    'cinematic': (60, 100), 'classical': (70, 140), 'techno': (125, 150),
    'jpop': (110, 145), 'phonk': (130, 160),
    'edm': (128, 145), 'house': (120, 130),
}

GENRE_SCALES = {
    'pop': ['major', 'mixolydian'],
    'hiphop': ['minor', 'dorian', 'pentatonic_minor'],
    'trap': ['minor', 'phrygian', 'pentatonic_minor'],
    'cinematic': ['minor', 'harmonic_minor', 'lydian'],
    'classical': ['major', 'minor', 'dorian', 'lydian'],
    'techno': ['minor', 'dorian', 'pentatonic_minor'],
    'jpop': ['major', 'lydian', 'japanese', 'pentatonic_major'],
    'phonk': ['minor', 'phrygian', 'blues'],
    'edm': ['minor', 'phrygian', 'pentatonic_minor'],
    'house': ['minor', 'dorian', 'major'],
}

GENRE_INSTRUMENTS = {
    'pop': {'chords': 0, 'lead': 80, 'bass': 33, 'pad': 88, 'arp': 80},
    'hiphop': {'chords': 4, 'lead': 80, 'bass': 38, 'pad': 89, 'arp': 81},
    'trap': {'chords': 81, 'lead': 80, 'bass': 38, 'pad': 95, 'arp': 81},
    'cinematic': {'chords': 48, 'lead': 68, 'bass': 43, 'pad': 92, 'arp': 46},
    'classical': {'chords': 0, 'lead': 40, 'bass': 42, 'pad': 48, 'arp': 46},
    'techno': {'chords': 81, 'lead': 80, 'bass': 38, 'pad': 95, 'arp': 81},
    'jpop': {'chords': 0, 'lead': 80, 'bass': 33, 'pad': 89, 'arp': 11},
    'phonk': {'chords': 4, 'lead': 80, 'bass': 87, 'pad': 95, 'arp': 81},
    'edm':   {'chords': 81, 'lead': 80, 'bass': 87, 'pad': 95, 'arp': 38},
    'house': {'chords': 4,  'lead': 80, 'bass': 33, 'pad': 89, 'arp': 11},
}

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
    'edm': [
        ('intro', 16), ('build', 16), ('drop', 32), ('break', 8),
        ('build', 8), ('drop', 32), ('break', 4),
        ('build', 8), ('drop', 16), ('outro', 8),
    ],
    'house': [
        ('intro', 8), ('verse', 16), ('build', 8), ('chorus', 16),
        ('break', 8), ('build', 8), ('chorus', 16), ('outro', 8),
    ],
}


def note_name_to_midi(note: str, octave: int = 4) -> int:
    base = note[:2] if len(note) > 1 and note[1] in '#b' else note[0]
    return NOTE_TO_MIDI.get(base, 0) + (octave + 1) * 12


def get_chord_midi_notes(root: str, quality: str, octave: int = 4) -> List[int]:
    root_midi = note_name_to_midi(root, octave)
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
    if not chord_str:
        return ('C', 'major')
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
    root_midi = note_name_to_midi(root, octave)
    intervals = SCALE_INTERVALS.get(scale_type, SCALE_INTERVALS['major'])
    return [root_midi + i for i in intervals]


def weighted_choice(options: Dict[str, float]) -> str:
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
    return max(0, value + random.uniform(-amount, amount))


def humanize_velocity(vel: int, amount: int = 12) -> int:
    return max(1, min(127, vel + random.randint(-amount, amount)))
