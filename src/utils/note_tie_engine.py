"""
note_tie_engine.py -- Merges consecutive same-pitch notes into single held blocks.

Music Theory Context:
    In MIDI, a "tied note" is when two or more adjacent notes of the same pitch
    are played without a gap between them, creating one continuous tone.  For pad
    and chord layers, long tied notes create harmonic sustain that is critical for
    an evolving, breathing texture.  Without note-tying, MIDI pads sound choppy
    and robotic because each note re-triggers the attack transient.

Algorithm:
    1. Sort notes by (pitch, time) to group co-pitch runs together.
    2. Walk forward: if note[i+1] starts within TIE_TOLERANCE beats of note[i]
       ending, extend note[i]'s duration to cover both and discard note[i+1].
    3. Repeat until no more merges occur (or single pass if pattern is sorted).

Inputs/Outputs use the standard 4-tuple:
    Note = (time_beats: float, duration_beats: float, midi_note: int, velocity: int)
"""

from __future__ import annotations
from typing import List, Tuple

Note = Tuple[float, float, int, int]

# Maximum gap between end of one note and start of next to still count as tied.
# 0.05 beats = ~12ms at 120 BPM -- tolerates minor quantization drift.
TIE_TOLERANCE = 0.05


def tie_notes(notes: List[Note], tolerance: float = TIE_TOLERANCE) -> List[Note]:
    """
    Merge consecutive same-pitch notes that overlap or are separated by less
    than `tolerance` beats into single held notes.

    Parameters
    ----------
    notes     : list of (time, duration, midi_note, velocity) 4-tuples
    tolerance : maximum gap (in beats) still considered tied

    Returns
    -------
    New list of notes with consecutive same-pitch runs merged.
    The velocity of the merged note is taken from the FIRST note in the run
    (attack velocity governs the phrase), so the tied tail inherits the
    expressive intent of the initial attack.
    """
    if not notes:
        return []

    # Group by pitch, preserving time order within each pitch group.
    by_pitch: dict = {}
    for note in notes:
        pitch = note[2]
        if pitch not in by_pitch:
            by_pitch[pitch] = []
        by_pitch[pitch].append(note)

    merged: List[Note] = []
    for pitch, group in by_pitch.items():
        # Sort by time so consecutive notes are adjacent in the list
        group_sorted = sorted(group, key=lambda n: n[0])

        # Walk through and merge tied runs
        current_time = group_sorted[0][0]
        current_dur  = group_sorted[0][1]
        current_vel  = group_sorted[0][3]

        for i in range(1, len(group_sorted)):
            nxt_time = group_sorted[i][0]
            nxt_dur  = group_sorted[i][1]

            current_end = current_time + current_dur
            # If the next note starts within tolerance of this note's end, tie them
            if nxt_time <= current_end + tolerance:
                # Extend duration to cover the end of the next note
                new_end = max(current_end, nxt_time + nxt_dur)
                current_dur = new_end - current_time
            else:
                # Gap too large -- emit the current note and start a new one
                merged.append((current_time, current_dur, pitch, current_vel))
                current_time = nxt_time
                current_dur  = nxt_dur
                current_vel  = group_sorted[i][3]

        # Emit the final note in this pitch group
        merged.append((current_time, current_dur, pitch, current_vel))

    # Re-sort the merged list by time (mixing pitches back together)
    merged.sort(key=lambda n: n[0])
    return merged


def tie_pad_notes(notes: List[Note],
                  section_start: float,
                  section_end: float,
                  max_hold_beats: float = 8.0) -> List[Note]:
    """
    Pad-specific variant: ties notes within a section window AND caps any single
    tied block at max_hold_beats.  This prevents a pad note from sustaining
    silently past a section boundary where a new chord root would take over.

    Parameters
    ----------
    notes           : raw pad notes
    section_start   : beat position where this section begins
    section_end     : beat position where this section ends
    max_hold_beats  : maximum duration of any single tied block (default 8 beats = 2 bars)

    Returns
    -------
    Tied and capped pad notes.
    """
    # Filter to only notes within this section window
    section_notes = [n for n in notes if section_start <= n[0] < section_end]

    # Clip note durations so they don't extend past section boundary
    clipped: List[Note] = []
    for t, dur, pitch, vel in section_notes:
        clipped_dur = min(dur, section_end - t)
        clipped.append((t, clipped_dur, pitch, vel))

    # Apply note-tie merging
    tied = tie_notes(clipped)

    # Cap each tied block at max_hold_beats
    result: List[Note] = []
    for t, dur, pitch, vel in tied:
        result.append((t, min(dur, max_hold_beats), pitch, vel))

    return result


def split_long_notes(notes: List[Note],
                     max_duration: float,
                     gap: float = 0.0) -> List[Note]:
    """
    Split any note longer than max_duration into a chain of repeated notes.
    Used when an instrument model can't hold a note indefinitely and needs
    re-trigger events.

    Parameters
    ----------
    notes        : input note list
    max_duration : maximum duration per note event
    gap          : silence gap between split segments (default 0.0 = tied)

    Returns
    -------
    Note list with all long notes broken into max_duration chunks.
    """
    result: List[Note] = []
    for t, dur, pitch, vel in notes:
        if dur <= max_duration:
            result.append((t, dur, pitch, vel))
        else:
            # Break into chunks of max_duration
            remaining = dur
            cursor = t
            while remaining > 0.001:
                chunk = min(remaining, max_duration)
                result.append((cursor, chunk, pitch, vel))
                cursor   += chunk + gap
                remaining -= chunk + gap

    result.sort(key=lambda n: n[0])
    return result
