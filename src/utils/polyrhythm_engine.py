"""
polyrhythm_engine.py -- Prime-Number Euclidean Interference (Polyrhythms).

Mathematical Context:
    A polyrhythm occurs when two or more rhythmic cycles of different lengths
    are superimposed simultaneously.  The resulting pattern has a combined period
    equal to the LCM (Least Common Multiple) of the individual cycle lengths.

    When cycle lengths are PRIME NUMBERS, their LCM = their product:
        LCM(p1, p2) = p1 × p2   (since primes share no common factors)

    This is the KEY property that makes prime-length Euclidean sequences ideal
    for polyrhythm generation:

        E(k1, p1=7) -- 7-step cycle, never aligns with E(k2, p2=5)
        Combined period = 35 steps = 8.75 beats (at 16th-note resolution)

    With 16th-note steps (0.25 beats each):
        E(3, 7): 3 onsets across 7 steps = 1.75 beat period
        E(2, 5): 2 onsets across 5 steps = 1.25 beat period
        Combined: resets only every 8.75 beats -- crosses a bar boundary

    The cross-bar periodicity means the pattern never sounds the same twice
    within a standard 4 or 8 bar loop, creating the "evolving, hypnotic"
    quality of great polyrhythmic music (West African, Afrobeat, DnB, techno).

Available Prime Pairs (n values):
    Small primes: 2, 3, 5, 7, 11, 13
    Recommended pairs for music (avoiding very dense or very sparse):
        (5, 7)   → 35-step combined period   (medium density)
        (5, 11)  → 55-step combined period   (more evolving)
        (7, 11)  → 77-step combined period   (very long evolution)
        (7, 13)  → 91-step combined period   (near-infinite feel)
        (3, 11)  → 33-step combined period   (sparse, spaced out)

Merge Strategy:
    OR-merge: a step is active if EITHER pattern fires at that step.
        Density = d1 + d2 - (d1 × d2)    where d = k/n (individual density)
        E.g., E(3,7) density=3/7≈0.43 + E(2,5) density=2/5=0.40 → merged≈0.66

    XOR-merge: a step is active if EXACTLY ONE pattern fires (not both).
        Creates sparser, less predictable output.
        Useful for texture generator where over-density would mask the melody.

    WEIGHTED-merge: notes from pattern 1 are louder than pattern 2.
        Accent pattern 1 by velocity multiplier (e.g., 1.0) and pattern 2 (0.65).
        Creates polyrhythmic hierarchy rather than equal-weight interference.

Implementation:
    PrimeEuclideanPolyrhythm.generate():
        1. Build E(k1, p1) and E(k2, p2) patterns as binary lists
        2. Tile each to length LCM(p1, p2) = p1 * p2
        3. Merge with chosen strategy
        4. Convert active steps to beat-offset + velocity pairs
        5. Supports absolute positioning by bar_offset for multi-bar patterns
"""

from __future__ import annotations
from typing import List, Optional, Tuple

from src.utils.math_tools import euclidean_rhythm

# Curated prime pairs for music -- each pair is (k1, p1, k2, p2)
# k = number of onsets, p = number of steps (prime)
_PRIME_PAIR_PRESETS = {
    'light':    (2, 5,  1, 7),    # low density, widely spaced
    'groove':   (3, 7,  2, 5),    # medium density, syncopated
    'driving':  (4, 7,  3, 5),    # higher density, forward motion
    'complex':  (3, 7,  4, 11),   # wide period, evolving
    'dense':    (4, 11, 5, 7),    # dense and hypnotic
    'synth':    (5, 11, 3, 7),    # wide interference arc
    'tribal':   (4, 7,  5, 13),   # very long non-repeat period
}

# Named merge strategies
_MERGE_OR  = 'or'    # active if EITHER pattern fires
_MERGE_XOR = 'xor'  # active if EXACTLY ONE fires (sparser)
_MERGE_AND = 'and'  # active only if BOTH fire (very sparse, accent points)


class PrimeEuclideanPolyrhythm:
    """
    Generates polyrhythmic note grids by superimposing two Euclidean rhythms
    with prime step counts.

    Parameters
    ----------
    preset     : named preset key from _PRIME_PAIR_PRESETS, or None to specify
                 k1, p1, k2, p2 directly
    k1, p1     : onsets and steps for pattern 1 (p1 must be prime)
    k2, p2     : onsets and steps for pattern 2 (p2 must be prime, p2 != p1)
    merge      : 'or' | 'xor' | 'and'
    step_beats : beat duration of one grid step (0.25 = 16th note, default)
    """

    def __init__(
        self,
        preset:     Optional[str] = 'groove',
        k1:         int = 3,
        p1:         int = 7,
        k2:         int = 2,
        p2:         int = 5,
        merge:      str = _MERGE_OR,
        step_beats: float = 0.25,   # 16th-note resolution
    ):
        # Override with preset if specified
        if preset and preset in _PRIME_PAIR_PRESETS:
            k1, p1, k2, p2 = _PRIME_PAIR_PRESETS[preset]

        self.k1 = k1
        self.p1 = p1
        self.k2 = k2
        self.p2 = p2
        self.merge = merge
        self.step_beats = step_beats

        # Full combined period in steps (LCM of two primes = their product)
        self.period_steps = p1 * p2

        # Build the merged binary pattern once (it's invariant per instance)
        self._pattern = self._build_pattern()
        self._pat1    = self._build_pat1()

    # ------------------------------------------------------------------
    # Pattern construction
    # ------------------------------------------------------------------

    def _build_pattern(self) -> List[int]:
        """
        Build the merged binary pattern of length p1 * p2.

        Each element is 0 (silent) or 1 (active onset).
        """
        lcm = self.p1 * self.p2   # = LCM for prime pair

        # Build pattern 1: tile E(k1, p1) to cover lcm steps
        pat1_base = euclidean_rhythm(self.k1, self.p1)
        # Tile by repeating the base pattern enough times
        repeats1 = lcm // self.p1   # exact division since p1 divides lcm
        pat1 = (pat1_base * repeats1)[:lcm]

        # Build pattern 2: tile E(k2, p2) to cover lcm steps
        pat2_base = euclidean_rhythm(self.k2, self.p2)
        repeats2 = lcm // self.p2
        pat2 = (pat2_base * repeats2)[:lcm]

        # Apply merge strategy
        if self.merge == _MERGE_OR:
            return [1 if pat1[i] or pat2[i] else 0 for i in range(lcm)]
        elif self.merge == _MERGE_XOR:
            return [1 if bool(pat1[i]) != bool(pat2[i]) else 0 for i in range(lcm)]
        elif self.merge == _MERGE_AND:
            return [1 if pat1[i] and pat2[i] else 0 for i in range(lcm)]
        else:
            raise ValueError(f"Unknown merge strategy: '{self.merge}'. Use 'or', 'xor', or 'and'.")

    def _build_pat1(self) -> List[int]:
        lcm = self.p1 * self.p2
        pat1_base = euclidean_rhythm(self.k1, self.p1)
        return (pat1_base * (lcm // self.p1))[:lcm]

    def get_pattern_1(self) -> List[int]:
        """Return the tiled pattern for E(k1, p1) alone (for accent weighting)."""
        return self._pat1

    # ------------------------------------------------------------------
    # Note generation
    # ------------------------------------------------------------------

    def generate_offsets(
        self,
        start_beat:  float,
        total_beats: float,
        rotation:    int = 0,
    ) -> List[Tuple[float, float]]:
        """
        Generate (beat_position, velocity_weight) pairs for all active steps
        within the range [start_beat, start_beat + total_beats).

        The pattern cycles at period = p1 * p2 steps.  Notes at steps where
        ONLY pattern 1 fires get weight 1.0 (accented); steps where only
        pattern 2 fires get weight 0.65 (softer); steps where BOTH fire
        get weight 1.2 (double accent).

        Parameters
        ----------
        start_beat  : absolute beat position where the range begins
        total_beats : how many beats to fill (typically 4 per bar)
        rotation    : rotate the start phase of the combined pattern by
                      this many steps (use bar_offset for phase continuity)

        Returns
        -------
        List of (beat_position, velocity_weight) 2-tuples.
        velocity_weight is a float in ~[0.6, 1.2] -- multiply by base_vel.
        """
        period  = self.period_steps
        pattern = self._pattern
        pat1    = self.get_pattern_1()

        results: List[Tuple[float, float]] = []

        # Determine how many steps span total_beats
        n_steps = int(total_beats / self.step_beats)

        for step_offset in range(n_steps):
            # Map step to cyclic position with rotation
            cycle_pos = (rotation + step_offset) % period

            if not pattern[cycle_pos]:
                continue

            beat = start_beat + step_offset * self.step_beats

            # Determine velocity weight by which sub-pattern(s) fired
            p1_active = pat1[cycle_pos]
            # p2_active can be inferred from the merge
            if self.merge == _MERGE_OR:
                p2_derived_active = pattern[cycle_pos] and not p1_active
            elif self.merge == _MERGE_XOR:
                p2_derived_active = not p1_active
            else:
                p2_derived_active = p1_active  # AND merge: both active

            if p1_active and p2_derived_active:
                vel_weight = 1.20   # coincidence accent (both patterns hit simultaneously)
            elif p1_active:
                vel_weight = 1.00   # primary pattern accent
            else:
                vel_weight = 0.65   # secondary pattern (softer cross-rhythm)

            results.append((beat, vel_weight))

        return results

    def generate_notes(
        self,
        start_beat:   float,
        total_beats:  float,
        pitch_pool:   List[int],
        base_vel:     int = 72,
        gate:         float = 0.20,
        rotation:     int = 0,
        rng=None,
    ) -> List[Tuple[float, float, int, int]]:
        """
        Full note generation: map active steps to MIDI notes from pitch_pool.

        Parameters
        ----------
        start_beat  : absolute song beat position
        total_beats : duration to fill (e.g., 4.0 for one bar)
        pitch_pool  : list of MIDI notes to draw from (cycling)
        base_vel    : base MIDI velocity before weight scaling
        gate        : note duration in beats (staccato texture default 0.20)
        rotation    : pattern phase rotation (use bar_offset % period_steps)
        rng         : optional seeded random.Random for pitch selection

        Returns
        -------
        List of (time, duration, midi_note, velocity) 4-tuples.
        """
        if not pitch_pool:
            return []

        offsets = self.generate_offsets(start_beat, total_beats, rotation)
        notes: List[Tuple[float, float, int, int]] = []

        for i, (beat, vel_weight) in enumerate(offsets):
            # Cycle through pitch_pool in order (arpeggiated) or random
            if rng is not None:
                pitch = rng.choice(pitch_pool)
            else:
                pitch = pitch_pool[i % len(pitch_pool)]

            vel = max(1, min(127, int(base_vel * vel_weight)))
            notes.append((beat, gate, pitch, vel))

        return notes


# ---------------------------------------------------------------------------
# Convenience: get preset names
# ---------------------------------------------------------------------------

def list_presets() -> List[str]:
    """Return all available prime-pair preset names."""
    return list(_PRIME_PAIR_PRESETS.keys())


def describe_preset(preset: str) -> str:
    """Return a human-readable description of a preset's mathematical properties."""
    if preset not in _PRIME_PAIR_PRESETS:
        return f"Unknown preset: {preset}"
    k1, p1, k2, p2 = _PRIME_PAIR_PRESETS[preset]
    lcm = p1 * p2
    return (
        f"Preset '{preset}': E({k1},{p1}) × E({k2},{p2})\n"
        f"  Combined period = {lcm} steps = {lcm * 0.25:.2f} beats (16th-note grid)\n"
        f"  Density ≈ {k1/p1 + k2/p2 - (k1/p1)*(k2/p2):.2f} (fraction of steps active)\n"
        f"  Pattern repeats every {lcm * 0.25:.2f} beats "
        f"({lcm * 0.25 / 4:.2f} bars at 4/4)"
    )
