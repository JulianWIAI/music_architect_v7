"""
edm_archetypes.py — EDM-specific IntroVarietyProtocol archetype generators.

Three archetypes, each returning (time_beats, dur_beats, midi_note, vel) tuples:

  filter_sweep  — Full-chord whole-bar sustain; velocity sweeps from 40% to 100%
                  across the intro section, simulating a supersaw filter opening.
  mono_pluck    — Root-only monophonic hits on a rigid 4-on-the-floor grid.
                  Hit count builds 1→3 as the section progresses.
  impact_drone  — Hard-impact on bar 0 followed by soft drone sustain for all
                  remaining bars.  Creates the classic EDM "boom then sustain" feel.
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
    """Dispatch to the named EDM intro archetype."""
    if archetype == 'filter_sweep':
        return _filter_sweep(bar, section_bars, chord_notes, beat_pos, bar_vel, h_amt, humanize_fn, gate_fn)
    if archetype == 'mono_pluck':
        return _mono_pluck(bar, section_bars, chord_notes, beat_pos, bar_vel, h_amt, humanize_fn, gate_fn)
    if archetype == 'impact_drone':
        return _impact_drone(bar, chord_notes, beat_pos, bar_vel, h_amt, humanize_fn, gate_fn)
    return []


def _filter_sweep(
    bar:          int,
    section_bars: int,
    chord_notes:  List[int],
    beat_pos:     float,
    bar_vel:      int,
    h_amt:        float,
    humanize_fn, gate_fn,
) -> List[Tuple[float, float, int, int]]:
    """
    Filter Sweep — sustained full-chord voicing; velocity climbs each bar.
    Mimics a supersaw cutoff filter opening over the intro.
    All chord tones included (wide voicing = supersaw character).
    """
    build_frac = (bar + 1) / max(1, section_bars)
    sweep_vel  = max(30, int(bar_vel * (0.40 + 0.60 * build_frac)))
    gate       = gate_fn(3.9)
    events: List[Tuple[float, float, int, int]] = []
    for note in chord_notes:
        events.append((
            humanize_fn(beat_pos, 0.010 * h_amt),
            gate, note, sweep_vel,
        ))
    return events


def _mono_pluck(
    bar:          int,
    section_bars: int,
    chord_notes:  List[int],
    beat_pos:     float,
    bar_vel:      int,
    h_amt:        float,
    humanize_fn, gate_fn,
) -> List[Tuple[float, float, int, int]]:
    """
    Monophonic Pluck — root note only; hit count grows 1→3 over the section.
    Rigid quantization (very small humanize factor) consistent with 4-on-the-floor.
    """
    root       = min(chord_notes) if chord_notes else 60
    build_frac = (bar + 1) / max(1, section_bars)
    if build_frac < 0.40:
        offsets = [0.0]
    elif build_frac < 0.75:
        offsets = [0.0, 2.0]
    else:
        offsets = [0.0, 1.5, 3.0]

    events: List[Tuple[float, float, int, int]] = []
    for off in offsets:
        events.append((
            humanize_fn(beat_pos + off, 0.008 * h_amt),   # rigid grid feel
            gate_fn(random.uniform(0.20, 0.35)),
            root, max(50, int(bar_vel * random.uniform(0.88, 1.0))),
        ))
    return events


def _impact_drone(
    bar:         int,
    chord_notes: List[int],
    beat_pos:    float,
    bar_vel:     int,
    h_amt:       float,
    humanize_fn, gate_fn,
) -> List[Tuple[float, float, int, int]]:
    """
    Impact & Drone — maximum-velocity crash on bar 0, then quiet drone sustain.
    Sets the key on first bar; remaining bars build harmonic tension quietly.
    """
    events: List[Tuple[float, float, int, int]] = []
    if bar == 0:
        for note in chord_notes:
            events.append((
                humanize_fn(beat_pos, 0.004 * h_amt),
                gate_fn(3.9),
                note, min(127, int(bar_vel * 1.30)),
            ))
    else:
        drone_vel = max(28, int(bar_vel * 0.58))
        gate      = gate_fn(random.uniform(3.5, 7.0))
        for note in chord_notes:
            events.append((
                humanize_fn(beat_pos, 0.008 * h_amt),
                gate, note, drone_vel,
            ))
    return events
