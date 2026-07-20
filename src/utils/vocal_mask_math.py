"""
vocal_mask_math.py -- Strict vocal mask mathematics for stems 04, 05, 07.

Frequency / MIDI Context:
    Human vocal range (soprano through tenor) sits roughly in the 250 Hz -- 4 kHz
    band.  The MIDI note equivalents are:

        250 Hz  ≈ B3   (MIDI  59)  <-- vocal mask LOWER bound
        4000 Hz ≈ B7   (MIDI 107)  <-- vocal mask UPPER bound

    When a vocal track is present, any dense MIDI activity in this range on
    backing stems will clash with (mask) the vocal.  To create headroom:

    A. SUPPRESS   -- notes in [59, 107] are either dropped or transposed out.
    B. OPEN VOICINGS -- chord matrices avoid the 3rd (which sits in the lower
                        vocal midrange).  Use 5th + octave shell voicings instead.
    C. DENSITY THINNING -- at most one note per 8th-note slot in [59,107] range;
                           extra notes are silenced.

    Stems affected:
        04_Melody  (ch 1) -- main note stream; transpose down when clashing
        05_Chords  (ch 2) -- open voicing enforced
        07_Arp     (ch 4) -- transpose or silence notes in the exclusion zone

    Stems NOT affected:
        01_Kick / 02_Percussion -- drums, below range
        03_Bass    (ch 0)  -- sits below 250 Hz, unaffected
        06_Pad     (ch 3)  -- handled separately via Harmonic Supersymmetry
        08_Stabs   (ch 5)  -- short attacks, handled by density rule only
        09_Texture (ch 6)  -- counter-melody; same rules as 04_Melody
        10_FX      (ch 7)  -- sparse; no masking concern

Sections where vocal mask is active:
    'verse', 'hook', 'chorus', 'pre_chorus'
    (NOT 'intro', 'break', 'build', 'drop', 'outro' -- no vocal in these)
"""

from __future__ import annotations
import random
from typing import List, Optional, Tuple

Note = Tuple[float, float, int, int]   # (time, duration, midi_note, velocity)

# MIDI note range of the vocal exclusion zone
VOCAL_MASK_LOW  = 59    # B3 -- 250 Hz lower bound
VOCAL_MASK_HIGH = 108   # C8 -- 4 kHz upper bound (exclusive)

# Sections where the vocal mask is enforced
VOCAL_SECTIONS = frozenset({'verse', 'hook', 'chorus', 'pre_chorus'})

# MIDI note interval constants (semitones)
OCTAVE      = 12
FIFTH       = 7
MAJOR_THIRD = 4
MINOR_THIRD = 3


def in_vocal_zone(midi_note: int) -> bool:
    """Return True if the note falls within the vocal exclusion zone."""
    return VOCAL_MASK_LOW <= midi_note < VOCAL_MASK_HIGH


def transpose_below_vocal_zone(midi_note: int, min_note: int = 36) -> Optional[int]:
    """
    Shift a note down by octaves until it falls below the vocal zone.

    Returns None if the note would drop below min_note (C2), signalling
    that the note should be dropped entirely.
    """
    note = midi_note
    while in_vocal_zone(note):
        note -= OCTAVE
    if note < min_note:
        return None
    return note


def transpose_above_vocal_zone(midi_note: int, max_note: int = 108) -> Optional[int]:
    """
    Shift a note UP by octaves until it clears the vocal zone.

    Returns None if the note would exceed max_note (C8).
    """
    note = midi_note
    while in_vocal_zone(note):
        note += OCTAVE
    if note > max_note:
        return None
    return note


def mask_melody_note(midi_note: int,
                     section_type: str,
                     active: bool = True) -> Optional[int]:
    """
    Apply vocal mask logic to a melody note.

    Strategy: transpose DOWN below the vocal zone (keeps bass character).
    Returns None if note should be dropped.

    Parameters
    ----------
    midi_note    : MIDI pitch to evaluate
    section_type : current section name
    active       : if False, the vocal mask is disabled and note is returned unchanged
    """
    if not active or section_type not in VOCAL_SECTIONS:
        return midi_note
    if not in_vocal_zone(midi_note):
        return midi_note
    return transpose_below_vocal_zone(midi_note)


def mask_arp_note(midi_note: int,
                  section_type: str,
                  active: bool = True) -> Optional[int]:
    """
    Apply vocal mask logic to an arpeggiator note.

    Strategy: arp pitches are transposed DOWN to avoid the midrange clash.
    """
    return mask_melody_note(midi_note, section_type, active)


def open_chord_voicing(root_midi: int,
                       intervals: List[int],
                       section_type: str,
                       active: bool = True) -> List[int]:
    """
    Enforce open-voicing on a chord to create vocal headroom.

    "Open voicing" means:
        - Drop the 3rd (interval 3 or 4) from the voicing
        - Use root + 5th in the lower octave
        - Add the octave of the root for warmth

    This avoids the 3rd sitting in the lower vocal midrange (where masking
    is most damaging to intelligibility).

    Parameters
    ----------
    root_midi  : MIDI note of the chord root
    intervals  : semitone offsets from the root (e.g. [0, 4, 7] for major)
    section_type: current section name
    active     : if False, returns the original unmodified chord tones

    Returns
    -------
    List of MIDI notes for the open voicing.
    The voicing is shell: [root, fifth, root+octave] -- max 3 voices.
    """
    # Build full chord tones first
    full_chord = [root_midi + i for i in intervals]

    if not active or section_type not in VOCAL_SECTIONS:
        return full_chord

    # Separate interval classes: find root(0), 3rd(3or4), 5th(7)
    root_note  = root_midi
    fifth_note = root_midi + FIFTH
    oct_note   = root_midi + OCTAVE

    # All three comfortably below or above vocal zone
    # Place root below vocal zone
    while in_vocal_zone(root_note):
        root_note -= OCTAVE
    if root_note < 24:   # below C1 -- too low
        root_note += OCTAVE

    while in_vocal_zone(fifth_note):
        fifth_note -= OCTAVE
    if fifth_note < 24:
        fifth_note += OCTAVE

    # Octave note: place above vocal zone to add shimmer
    oct_note = root_midi + OCTAVE
    while in_vocal_zone(oct_note):
        oct_note += OCTAVE
    if oct_note > 108:
        oct_note -= OCTAVE

    return sorted(set([root_note, fifth_note, oct_note]))


def thin_density(notes: List[Note],
                 section_type: str,
                 slot_beats: float = 0.5,
                 active: bool = True) -> List[Note]:
    """
    Density thinning: in the vocal zone, allow at most one note per `slot_beats`
    per MIDI pitch class to prevent cluster buildup in the exclusion zone.

    Notes outside the vocal zone are passed through unchanged.

    Parameters
    ----------
    notes        : input note list
    section_type : current section
    slot_beats   : minimum beat spacing between notes in the vocal zone (0.5 = 8th-note)
    active       : if False, returns notes unchanged
    """
    if not active or section_type not in VOCAL_SECTIONS:
        return notes

    result: List[Note] = []
    # Track the last time each pitch class was used in the vocal zone
    last_hit: dict = {}

    for note in sorted(notes, key=lambda n: n[0]):
        t, dur, pitch, vel = note
        if not in_vocal_zone(pitch):
            result.append(note)
            continue
        pc = pitch % 12   # pitch class
        if pc not in last_hit or (t - last_hit[pc]) >= slot_beats:
            result.append(note)
            last_hit[pc] = t
        # else: note is too close to a previous same-class note -- drop it

    return result


def apply_vocal_mask_to_track(
    notes:        List[Note],
    track_name:   str,
    section_type: str,
    active:       bool = True,
    rng:          Optional[random.Random] = None,
) -> List[Note]:
    """
    High-level entry point: apply the full vocal mask pipeline to a named track.

    Track-specific behavior:
        '04_Melody'  -- transpose each note below vocal zone; drop if too low
        '07_Arp'     -- same as melody
        '05_Chords'  -- open voicing (handled separately in chords generator)
        '09_Texture' -- transpose below, same as melody
        all others   -- density thinning only

    Parameters
    ----------
    notes        : note list for this track
    track_name   : e.g. '04_Melody'
    section_type : e.g. 'verse'
    active       : if False, returns notes unchanged
    rng          : optional seeded RNG for probabilistic filtering

    Returns
    -------
    Filtered/transposed note list.
    """
    if not active or section_type not in VOCAL_SECTIONS:
        return notes

    # Melody and arp: transpose down
    if track_name in ('04_Melody', '07_Arp', '09_Texture'):
        result: List[Note] = []
        for t, dur, pitch, vel in notes:
            new_pitch = mask_melody_note(pitch, section_type, active)
            if new_pitch is not None:
                result.append((t, dur, new_pitch, vel))
        return result

    # All other stems: density thinning in the exclusion zone
    return thin_density(notes, section_type, active=active)
