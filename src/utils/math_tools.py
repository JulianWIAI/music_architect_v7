"""
math_tools.py -- Euclidean rhythm generator and density scoring utilities.

Euclidean Rhythm E(k, n):
    Distributes k pulses as evenly as possible across n steps using
    Bjorklund's algorithm.  This is the mathematical foundation for
    organic-sounding percussion patterns used in world music and EDM.

Density Score:
    Ratio of active note-on events to total 16th-note grid steps in a
    section.  Used by Harmonic Supersymmetry to inversely scale pad/chord
    gate lengths when melody is dense.

Reference:
    Toussaint, G. (2005). "The Euclidean algorithm generates traditional
    musical rhythms." Proceedings of BRIDGES.
"""

from __future__ import annotations
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Euclidean Rhythm
# ---------------------------------------------------------------------------

def euclidean_rhythm(k: int, n: int) -> List[int]:
    """
    Return a binary list of length n with k ones distributed as evenly as
    possible (Bjorklund / Euclidean algorithm).

    E(k=3, n=8)  → [1, 0, 0, 1, 0, 0, 1, 0]  (clave-like pattern)
    E(k=5, n=8)  → [1, 0, 1, 1, 0, 1, 1, 0]  (bossa nova clave)
    E(k=7, n=16) → [1,0,1,0,1,0,1,0,0,1,0,1,0,1,0,0]

    Parameters
    ----------
    k : number of active pulses (onsets)
    n : total number of steps

    Returns
    -------
    List[int] — length n, values 0 or 1
    """
    if k <= 0:
        return [0] * n
    if k >= n:
        return [1] * n

    # Bjorklund's algorithm: at each step, the smaller group is distributed
    # into the larger group.  We track main_groups (the majority type at this
    # step) and rem_groups (the remainder type), swapping roles each time the
    # remainder becomes larger than the main.  This mirrors the Euclidean GCD
    # algorithm and terminates in O(log n) steps.
    main_groups: List[List[int]] = [[1]] * k
    rem_groups:  List[List[int]] = [[0]] * (n - k)

    while len(rem_groups) > 1:
        count = min(len(main_groups), len(rem_groups))
        new_groups = [main_groups[i] + rem_groups[i] for i in range(count)]

        if len(main_groups) > len(rem_groups):
            # main had more: leftover main becomes the new remainder
            rem_groups  = main_groups[count:]
            main_groups = new_groups
        elif len(main_groups) < len(rem_groups):
            # rem had more: leftover rem stays as remainder
            rem_groups  = rem_groups[count:]
            main_groups = new_groups
        else:
            # equal counts: no remainder, finished
            main_groups = new_groups
            rem_groups  = []

    pattern: List[int] = []
    for g in main_groups + rem_groups:
        pattern.extend(g)
    return pattern


def euclidean_offsets(k: int, n: int, rotation: int = 0) -> List[float]:
    """
    Return a list of beat offsets (in units of 1/n-th of a bar of 4 beats)
    for each active pulse in the Euclidean rhythm.

    Parameters
    ----------
    k        : number of pulses
    n        : total steps (16 = 16th-note grid)
    rotation : number of steps to rotate the pattern (shifts the downbeat)

    Returns
    -------
    List[float] — beat positions within a single bar (0.0 to < 4.0)
    """
    pattern = euclidean_rhythm(k, n)
    step_dur = 4.0 / n  # duration of one step in beats

    # Rotate the pattern to shift the phase
    if rotation:
        r = rotation % n
        pattern = pattern[r:] + pattern[:r]

    return [i * step_dur for i, hit in enumerate(pattern) if hit]


# ---------------------------------------------------------------------------
# Density Scoring
# ---------------------------------------------------------------------------

def melody_density(notes: list, section_start_beat: float,
                   section_bars: int, bar_beats: float = 4.0) -> float:
    """
    Compute the fraction of 16th-note grid slots occupied by at least one
    note-on event within the given section window.

    Parameters
    ----------
    notes             : list of (time_beats, duration, midi_note, velocity) tuples
    section_start_beat: beat position where the section begins
    section_bars      : number of bars in this section
    bar_beats         : beats per bar (default 4 for 4/4)

    Returns
    -------
    float in [0.0, 1.0] — 0.0 = completely silent, 1.0 = every 16th-note hit
    """
    total_beats = section_bars * bar_beats
    section_end = section_start_beat + total_beats
    slot_dur = bar_beats / 16.0          # 16th-note grid slot size
    total_slots = int(total_beats / slot_dur)

    if total_slots == 0:
        return 0.0

    occupied: set = set()
    for note in notes:
        t = note[0]
        if section_start_beat <= t < section_end:
            slot = int((t - section_start_beat) / slot_dur)
            occupied.add(slot)

    return len(occupied) / total_slots


def harmonic_supersymmetry_gate_mult(density: float,
                                     density_threshold: float = 0.6) -> Tuple[float, float]:
    """
    Harmonic Supersymmetry: when melody is dense, pad holds longer and
    chords thin out to avoid frequency masking.

    Rule:
        if density > threshold:
            pad_gate_mult  = 2.0   (pad notes held twice as long)
            chord_density  = 0.5   (50% of chord events are suppressed)
        else:
            pad_gate_mult  = 1.0
            chord_density  = 1.0

    Parameters
    ----------
    density           : melody density score from melody_density()
    density_threshold : activation threshold (default 0.6)

    Returns
    -------
    Tuple[float, float] — (pad_gate_multiplier, chord_density_factor)
    """
    if density > density_threshold:
        return 2.0, 0.5
    return 1.0, 1.0


# ---------------------------------------------------------------------------
# Velocity Curve
# ---------------------------------------------------------------------------

def velocity_curve(step: int, total_steps: int,
                   base_vel: int = 90, peak_vel: int = 127,
                   curve: str = 'linear') -> int:
    """
    Generate a velocity value at a given step along a named curve.

    Curves:
        'linear'   -- steady ramp from base_vel to peak_vel
        'exp'      -- exponential growth (slow then fast) -- good for build-ups
        'log'      -- logarithmic (fast then slow) -- good for decay tails
        'triangle' -- ramps up then back down (good for fills)

    Parameters
    ----------
    step        : current step index (0-based)
    total_steps : total number of steps in the ramp
    base_vel    : velocity at step 0
    peak_vel    : velocity at the peak
    curve       : curve shape name

    Returns
    -------
    int clamped to [0, 127]
    """
    if total_steps <= 1:
        return int(peak_vel)

    t = step / (total_steps - 1)   # normalized 0.0 to 1.0

    if curve == 'exp':
        t = t ** 2
    elif curve == 'log':
        import math
        t = math.log1p(t * (math.e - 1))  # log(1 + t*(e-1)) maps [0,1]->[0,1]
    elif curve == 'triangle':
        t = 1.0 - abs(t * 2.0 - 1.0)     # ramp up to midpoint then back down

    val = base_vel + (peak_vel - base_vel) * t
    return max(0, min(127, int(val)))
