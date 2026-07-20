"""
quantizer.py -- Event time-quantization grid for all 10 track generators.

Why Quantization Matters:
    Raw floating-point beat values drift over long compositions due to floating-
    point rounding.  If a kick at bar 16 is placed at 64.000000001 beats instead
    of 64.0, the MIDI encoder may insert a spurious tick gap, breaking the groove.

    The quantizer snaps all event times to the nearest grid slot of a given
    resolution (default: 1/64th note = 0.0625 beats in 4/4) while preserving
    intentional swing and humanization offsets.

    Quantization is applied as a LAST PASS before notes are assembled into the
    final track dict, after humanization.  The order is:
        1. Generate notes on idealized grid
        2. Apply swing (genre-specific 8th-note offset)
        3. Apply micro-timing humanization (±Δt)
        4. Quantize to nearest 1/64th (removes floating-point noise, not feel)
        5. Clip/wrap for loop alignment

Resolution Reference (4/4 time, beats per bar = 4):
    Whole note     = 4.0   beats
    Half note      = 2.0
    Quarter note   = 1.0
    8th note       = 0.5
    16th note      = 0.25
    32nd note      = 0.125
    64th note      = 0.0625  <-- default quantization grid
"""

from __future__ import annotations
from typing import List, Tuple

Note = Tuple[float, float, int, int]   # (time, duration, midi_note, velocity)

# Default resolution: 1/64th note in 4/4
DEFAULT_RESOLUTION = 0.0625


def snap(value: float, resolution: float = DEFAULT_RESOLUTION) -> float:
    """
    Snap a beat value to the nearest multiple of resolution.

    snap(0.2510, 0.0625) = 0.25   (nearest 16th-note = 4 * 0.0625)
    snap(0.3124, 0.0625) = 0.3125 (nearest 64th-note)
    """
    return round(round(value / resolution) * resolution, 8)


def quantize_note(note: Note,
                  resolution: float = DEFAULT_RESOLUTION,
                  min_duration: float = 0.0625) -> Note:
    """
    Snap note-on time and duration to the nearest grid slot.

    Parameters
    ----------
    note         : (time, duration, midi_note, velocity)
    resolution   : grid slot size in beats
    min_duration : minimum output duration (prevents zero-length notes)

    Returns
    -------
    Quantized note 4-tuple.
    """
    t, dur, pitch, vel = note
    new_t   = snap(t,   resolution)
    new_dur = max(min_duration, snap(dur, resolution))
    # Ensure non-negative time
    new_t = max(0.0, new_t)
    return (new_t, new_dur, pitch, vel)


def quantize_notes(notes: List[Note],
                   resolution: float = DEFAULT_RESOLUTION,
                   min_duration: float = 0.0625) -> List[Note]:
    """
    Quantize an entire note list and return sorted by time.

    After quantization, two notes that snapped to the same time slot may now
    coincide.  This is expected for polyphonic chords.
    """
    if not notes:
        return []
    quantized = [quantize_note(n, resolution, min_duration) for n in notes]
    quantized.sort(key=lambda n: n[0])
    return quantized


def quantize_tracks(tracks: dict,
                    resolution: float = DEFAULT_RESOLUTION) -> dict:
    """
    Apply quantize_notes() to every track in a tracks dict.

    Parameters
    ----------
    tracks : {'01_Kick': [Note,...], '02_Percussion': [...], ...}

    Returns
    -------
    New dict with all note lists quantized.
    """
    return {name: quantize_notes(notes, resolution)
            for name, notes in tracks.items()}


def beats_per_subdivision(subdivision: str) -> float:
    """
    Convert a subdivision name to beats (for 4/4 with bar_beats=4).

    Examples:
        'whole'    → 4.0
        'half'     → 2.0
        'quarter'  → 1.0
        '8th'      → 0.5
        '16th'     → 0.25
        '32nd'     → 0.125
        '64th'     → 0.0625
        'triplet'  → 0.333...  (8th-note triplet)
    """
    MAP = {
        'whole':    4.0,
        'half':     2.0,
        'quarter':  1.0,
        '8th':      0.5,
        '16th':     0.25,
        '32nd':     0.125,
        '64th':     0.0625,
        'triplet':  4.0 / 12.0,   # 8th-note triplet
        'sextuplet':4.0 / 24.0,   # 16th-note triplet
    }
    return MAP.get(subdivision, 0.25)   # default: 16th note
