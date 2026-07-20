"""
loop_alignment.py -- Phase alignment protocol for seamless game loop boundaries.

Game Audio Context:
    In interactive game audio, music tracks loop continuously.  For the loop to
    be seamless, the last note event in a MIDI file must not have a tail that
    extends past the loop point (total_beats).  If it does:

    Option A -- CLIP:
        Set duration = total_beats - note_start - epsilon
        Note ends exactly at the loop point.  Safe but may sound abrupt for pads.

    Option B -- WRAP:
        Note tail wraps around to beat 0 of the next loop iteration.
        Sounds natural but requires the game engine to support split events
        (most do, via looping note-on state tracking).

    This module implements both options and provides a utility to scan a track
    for any out-of-bounds notes before export.

Vocabulary:
    loop_beats  -- total playback length of the loop in beats
    tail        -- portion of a note's duration that extends past loop_beats
    epsilon     -- small beat margin (0.01 beats ≈ 5ms at 120 BPM) used to
                   ensure notes actually end before the loop point, not at it
                   (some engines treat "at" as "past").
"""

from __future__ import annotations
from typing import List, Optional, Tuple

Note = Tuple[float, float, int, int]   # (time, duration, midi_note, velocity)

EPSILON = 0.01   # 10ms safety margin before the loop point


def clip_to_loop(notes: List[Note], loop_beats: float) -> List[Note]:
    """
    Clip all note durations so that no note tail extends past loop_beats.

    Notes that START at or past loop_beats are dropped entirely.

    Parameters
    ----------
    notes      : list of (time, duration, midi_note, velocity) tuples
    loop_beats : loop length in beats

    Returns
    -------
    New list with all notes clipped within [0, loop_beats).
    """
    result: List[Note] = []
    for t, dur, pitch, vel in notes:
        if t >= loop_beats:
            # Note starts after loop end -- discard
            continue
        max_dur = loop_beats - t - EPSILON
        if max_dur <= 0.0:
            continue
        clipped_dur = min(dur, max_dur)
        result.append((t, clipped_dur, pitch, vel))
    return result


def wrap_tail_to_start(notes: List[Note], loop_beats: float) -> List[Note]:
    """
    Wrap any note tail that extends past loop_beats back to beat 0.

    A note with tail T wraps into two events:
        1. Original note clipped at (loop_beats - epsilon)
        2. New note at time 0.0 with duration = T

    Notes that start at or past loop_beats are dropped.

    Parameters
    ----------
    notes      : input note list
    loop_beats : loop length in beats

    Returns
    -------
    Note list with tail-wrapped events, sorted by time.
    """
    result: List[Note] = []
    for t, dur, pitch, vel in notes:
        if t >= loop_beats:
            continue

        note_end = t + dur
        if note_end <= loop_beats - EPSILON:
            # Note fits entirely within the loop -- no wrapping needed
            result.append((t, dur, pitch, vel))
        else:
            # Clip this instance to the loop boundary
            clipped_dur = (loop_beats - EPSILON) - t
            if clipped_dur > 0.001:
                result.append((t, clipped_dur, pitch, vel))
            # Tail wraps to beginning
            tail_dur = note_end - loop_beats
            if tail_dur > 0.001:
                result.append((0.0, tail_dur, pitch, vel))

    result.sort(key=lambda n: n[0])
    return result


def scan_out_of_bounds(notes: List[Note],
                       loop_beats: float) -> List[Note]:
    """
    Return a list of notes whose tails extend past loop_beats.

    Used for diagnostic logging -- if this list is non-empty, the track
    needs phase alignment applied before export.
    """
    return [
        (t, dur, pitch, vel)
        for t, dur, pitch, vel in notes
        if t + dur > loop_beats + EPSILON
    ]


def align_all_tracks(
    tracks:    dict,
    loop_beats: float,
    mode:      str = 'clip',
) -> dict:
    """
    Apply phase alignment to every track in the tracks dict.

    Parameters
    ----------
    tracks     : {'01_Kick': [Note, ...], '02_Percussion': [...], ...}
    loop_beats : total loop length in beats
    mode       : 'clip' or 'wrap'

    Returns
    -------
    New dict with aligned note lists.
    """
    fn = clip_to_loop if mode == 'clip' else wrap_tail_to_start
    return {name: fn(notes, loop_beats) for name, notes in tracks.items()}
