"""
Shared MIDI utility constants and functions used across pattern extractors and generators.
"""

from typing import Tuple

NOTE_TO_MIDI = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3,
    'E': 4, 'Fb': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7,
    'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11, 'Cb': 11,
}

MIDI_TO_NOTE = {
    0: 'C', 1: 'C#', 2: 'D', 3: 'D#', 4: 'E', 5: 'F',
    6: 'F#', 7: 'G', 8: 'G#', 9: 'A', 10: 'A#', 11: 'B',
}

CHORD_INTERVALS = {
    'major': [0, 4, 7], 'minor': [0, 3, 7], 'maj7': [0, 4, 7, 11],
    'min7': [0, 3, 7, 10], '7': [0, 4, 7, 10], 'dim': [0, 3, 6],
    'dim7': [0, 3, 6, 9], 'aug': [0, 4, 8], 'sus4': [0, 5, 7],
    'sus2': [0, 2, 7], 'min': [0, 3, 7], 'maj': [0, 4, 7],
}


def note_name_to_midi(note: str, octave: int = 4) -> int:
    """Convert a note name and octave to a MIDI note number."""
    base = note[:2] if len(note) > 1 and note[1] in '#b' else note[0]
    return NOTE_TO_MIDI.get(base, 0) + (octave + 1) * 12


def parse_chord_string(chord_str: str) -> Tuple[str, str]:
    """Parse a chord string like 'Amin7' into ('A', 'min7')."""
    if not chord_str:
        return ('C', 'major')
    if len(chord_str) > 1 and chord_str[1] in '#b':
        root = chord_str[:2]
        quality = chord_str[2:] if len(chord_str) > 2 else 'major'
    else:
        root = chord_str[0]
        quality = chord_str[1:] if len(chord_str) > 1 else 'major'
    return root, quality or 'major'


def get_scale_notes(root: str, quality: str, octave: int = 5) -> list:
    """Return a list of MIDI pitches for the scale implied by a chord quality."""
    root_midi = note_name_to_midi(root, octave)
    intervals = [0, 2, 3, 5, 7, 8, 10] if 'min' in quality.lower() else [0, 2, 4, 5, 7, 9, 11]
    return [root_midi + i for i in intervals]
