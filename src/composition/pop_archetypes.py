"""
pop_archetypes.py — Pop-specific IntroVarietyProtocol archetype generators.

Three archetypes, each returning a list of (time_beats, dur_beats, midi_note, vel) tuples:

  piano_staccato  — Precise 8th-note chord hits; max 4 notes (triad + extension) to
                    preserve vocal-mask headroom. Very tight timing (near-zero jitter).
  pluck_arpeggio  — Ascending single-note arpeggio with pluck envelope. Note count
                    grows bar-by-bar for pre-chorus tension build.
  atmospheric_pad — Soft, long-sustain pad chord. Low velocity; gives room for vocal.
"""

from __future__ import annotations

import random
from typing import Callable, List, Tuple

# ── Staccato hit grids — clean 8th-note positions, no swing ──────────────────

_POP_STACCATO_GRIDS: List[List[float]] = [
    [0.0, 2.0],
    [0.0, 1.0, 2.0, 3.0],
    [0.0, 2.5],
    [0.5, 2.0, 3.5],
    [0.0, 1.0, 3.0],
    [0.0, 1.5, 3.0],
]


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
    """Dispatch to the named Pop intro archetype."""
    if archetype == 'piano_staccato':
        return _piano_staccato(chord_notes, beat_pos, bar_vel, h_amt, humanize_fn, gate_fn)
    if archetype == 'pluck_arpeggio':
        return _pluck_arpeggio(bar, section_bars, chord_notes, beat_pos, bar_vel, h_amt, humanize_fn, gate_fn)
    if archetype == 'atmospheric_pad':
        return _atmospheric_pad(chord_notes, beat_pos, bar_vel, h_amt, humanize_fn, gate_fn)
    return []


def _piano_staccato(
    chord_notes: List[int],
    beat_pos:    float,
    bar_vel:     int,
    h_amt:       float,
    humanize_fn, gate_fn,
) -> List[Tuple[float, float, int, int]]:
    """
    Piano Staccato — short chord hits on varied 8th-note grids.
    Hard ceiling of 4 notes per hit: leaves C4-C6 clear for vocal mask.
    """
    grid   = random.choice(_POP_STACCATO_GRIDS)
    voiced = sorted(chord_notes)[:4]    # triad / tetrad ceiling
    events: List[Tuple[float, float, int, int]] = []
    for off in grid:
        hit_vel = max(40, int(bar_vel * random.uniform(0.82, 1.0)))
        for note in voiced:
            events.append((
                humanize_fn(beat_pos + off, 0.004 * h_amt),  # very tight
                gate_fn(random.uniform(0.15, 0.28)),
                note, hit_vel,
            ))
    return events


def _pluck_arpeggio(
    bar:          int,
    section_bars: int,
    chord_notes:  List[int],
    beat_pos:     float,
    bar_vel:      int,
    h_amt:        float,
    humanize_fn, gate_fn,
) -> List[Tuple[float, float, int, int]]:
    """
    Pluck Arpeggio — ascending single-note arp on 8th-note steps.
    Builds note count bar-by-bar so tension accumulates over the intro section.
    """
    voiced     = sorted(chord_notes)[:4]
    build_frac = (bar + 1) / max(1, section_bars)
    n_notes    = max(2, round(len(voiced) * build_frac))
    events: List[Tuple[float, float, int, int]] = []
    for i, note in enumerate(voiced[:n_notes]):
        t = beat_pos + i * 0.5
        if t >= beat_pos + 3.9:
            break
        vel = max(35, int(bar_vel * (0.62 + 0.25 * i / max(1, n_notes - 1))))
        events.append((
            humanize_fn(t, 0.006 * h_amt),
            gate_fn(0.30),
            note, vel,
        ))
    return events


def _atmospheric_pad(
    chord_notes: List[int],
    beat_pos:    float,
    bar_vel:     int,
    h_amt:       float,
    humanize_fn, gate_fn,
) -> List[Tuple[float, float, int, int]]:
    """
    Atmospheric Pad — one soft sustained chord per bar.
    Low velocity keeps vocal space open. Max 4 notes (triad/tetrad).
    """
    gate    = gate_fn(random.uniform(3.5, 7.0))
    pad_vel = max(22, int(bar_vel * 0.60))
    events: List[Tuple[float, float, int, int]] = []
    for note in sorted(chord_notes)[:4]:
        events.append((
            humanize_fn(beat_pos, 0.004 * h_amt),
            gate, note, pad_vel,
        ))
    return events
