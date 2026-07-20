"""
house_archetypes.py — House-specific IntroVarietyProtocol archetype generators.

Three archetypes, each returning (time_beats, dur_beats, midi_note, vel) tuples:

  lpf_bass_groove   — Root on beat 1 + full chord at beat 2.5 (off-beat).
                      Mimics a low-pass filter gradually opening; swung feel.
  percussive_build  — Off-beat staccato stabs that grow denser bar-by-bar.
                      Classic house groove build toward the first drop.
  chord_stab        — 2-4 "and"-beat stabs (0.5-beat offset grid) per bar.
                      Strong syncopation; consistent with house swing factor 0.56.
"""

from __future__ import annotations

import random
from typing import Callable, List, Tuple


def generate(
    archetype:    str,
    bar:          int,
    section_bars: int,
    chord_notes:  List[int],
    beat_pos:     float,
    bar_vel:      int,
    h_amt:        float,
    humanize_fn:  Callable[[float, float], float],
    gate_fn:      Callable[[float], float],
) -> List[Tuple[float, float, int, int]]:
    """Dispatch to the named House intro archetype."""
    if archetype == 'lpf_bass_groove':
        return _lpf_bass_groove(chord_notes, beat_pos, bar_vel, h_amt, humanize_fn, gate_fn)
    if archetype == 'percussive_build':
        return _percussive_build(bar, section_bars, chord_notes, beat_pos, bar_vel, h_amt, humanize_fn, gate_fn)
    if archetype == 'chord_stab':
        return _chord_stab(chord_notes, beat_pos, bar_vel, h_amt, humanize_fn, gate_fn)
    return []


def _lpf_bass_groove(
    chord_notes: List[int],
    beat_pos:    float,
    bar_vel:     int,
    h_amt:       float,
    humanize_fn, gate_fn,
) -> List[Tuple[float, float, int, int]]:
    """
    LPF Bass Groove — beat-1 root hit + off-beat chord at 2.5.
    Simulates a LPF-filtered bass/chord layer slowly opening up.
    """
    if not chord_notes:
        return []
    root   = min(chord_notes)
    events: List[Tuple[float, float, int, int]] = []
    # Beat 1: root note anchors the bar
    events.append((
        humanize_fn(beat_pos, 0.022 * h_amt),
        gate_fn(random.uniform(0.35, 0.55)),
        root, max(40, int(bar_vel * 0.90)),
    ))
    # Beat 2.5: full chord hit (off-beat, lighter)
    for note in chord_notes:
        events.append((
            humanize_fn(beat_pos + 2.5, 0.025 * h_amt),
            gate_fn(random.uniform(0.22, 0.38)),
            note, max(32, int(bar_vel * 0.68)),
        ))
    return events


def _percussive_build(
    bar:          int,
    section_bars: int,
    chord_notes:  List[int],
    beat_pos:     float,
    bar_vel:      int,
    h_amt:        float,
    humanize_fn, gate_fn,
) -> List[Tuple[float, float, int, int]]:
    """
    Percussive Build — staccato stabs on off-beats, density grows each bar.
    Sparse at start of intro; full 4-stab pattern by last bar.
    """
    build_frac = (bar + 1) / max(1, section_bars)
    if build_frac < 0.33:
        offsets = [2.0]
    elif build_frac < 0.67:
        offsets = [2.0, 3.5]
    else:
        offsets = [1.0, 2.0, 3.0, 3.5]

    events: List[Tuple[float, float, int, int]] = []
    for off in offsets:
        hit_vel = max(38, int(bar_vel * random.uniform(0.75, 1.0)))
        for note in chord_notes:
            events.append((
                humanize_fn(beat_pos + off, 0.025 * h_amt),
                gate_fn(random.uniform(0.18, 0.28)),
                note, hit_vel,
            ))
    return events


def _chord_stab(
    chord_notes: List[int],
    beat_pos:    float,
    bar_vel:     int,
    h_amt:       float,
    humanize_fn, gate_fn,
) -> List[Tuple[float, float, int, int]]:
    """
    Chord Stab — 2-4 stabs on "and" positions (0.5, 1.5, 2.5, 3.5).
    Classic house syncopation; consistent swing emphasis.
    """
    ands   = random.sample([0.5, 1.5, 2.5, 3.5], k=random.randint(2, 4))
    events: List[Tuple[float, float, int, int]] = []
    for off in ands:
        hit_vel = max(45, int(bar_vel * random.uniform(0.82, 1.0)))
        for note in chord_notes:
            events.append((
                humanize_fn(beat_pos + off, 0.020 * h_amt),
                gate_fn(random.uniform(0.18, 0.30)),
                note, hit_vel,
            ))
    return events
