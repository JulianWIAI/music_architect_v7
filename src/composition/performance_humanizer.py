"""
performance_humanizer.py — Commercial-grade MIDI performance humanization.

Three stateless utility classes, each with a single class-method entry point:

  PhraseVelocityMapper   velocity(step, energy, jitter=5) -> int
      Beat-position-aware velocity for melody, chords, and arpeggiator.
      Strong beats (1 & 3) hit harder; passing 16ths are softer.

  GateLengthHumanizer    apply(duration) -> float
      ±3% gate-time randomization so no two notes of the same nominal
      length are perfectly identical — mimics fingers leaving a keyboard.

  BassVelocityProfile    velocity(genre, step, energy, is_root=False) -> int
      Per-genre bass velocity weights. Trap 808 / House bass receive a
      boosted floor (108–120) to drive the low-end; a per-note ±4 jitter
      prevents the machine-gun effect on repeated root notes.
"""
from __future__ import annotations

import random
from typing import Dict, Tuple

# ── 16th-note step categories within a 4/4 bar (steps 0-15) ──────────────────
_STRONG_STEPS   = frozenset({0, 8})           # beat 1 (downbeat) and beat 3
_BACKBEAT_STEPS = frozenset({4, 12})          # beat 2 and beat 4 (snare zone)
_OFFBEAT_STEPS  = frozenset({2, 6, 10, 14})  # "and" of each quarter note


class PhraseVelocityMapper:
    """
    Maps a note's 16th-note step position to a commercially-graded velocity.

    Category   Steps         Vel range   Musical role
    ---------  -----------   ---------   ----------------------------------
    strong     0, 8          95-110      Beat 1 / beat 3 — tonic accent
    backbeat   4, 12         88-105      Beat 2 / beat 4 — backbeat drive
    offbeat    2,6,10,14     78-95       "And" subdivisions — rhythmic flow
    passing    1,3,5,7,...   68-88       Weak 16ths — melodic fill

    Energy scaling: energy_mult = 0.70 + 0.30 × energy
      verse (0.55) → 0.87×  chorus (0.85) → 0.96×  break (0.2) → 0.76×
    This preserves dynamic range across sections without crushing weak bars.

    An additional ±jitter micro-randomization is applied to every note.
    """

    _RANGES: Dict[str, Tuple[int, int]] = {
        'strong':   (95, 110),
        'backbeat': (88, 105),
        'offbeat':  (78,  95),
        'passing':  (68,  88),
    }

    @classmethod
    def _category(cls, step: int | float) -> str:
        s = int(round(step)) % 16
        if s in _STRONG_STEPS:
            return 'strong'
        if s in _BACKBEAT_STEPS:
            return 'backbeat'
        if s in _OFFBEAT_STEPS:
            return 'offbeat'
        return 'passing'

    @classmethod
    def velocity(cls, step: int | float, energy: float, jitter: int = 5) -> int:
        """
        Args:
            step   : 16th-note position within bar (0-15); floats are rounded.
                     Beat positions (0-4) can be passed as step*4.
            energy : section energy scalar 0.0-1.0 from _section_energy()
            jitter : micro-randomization half-range (default ±5)
        """
        lo, hi       = cls._RANGES[cls._category(step)]
        base         = random.randint(lo, hi)
        energy_mult  = 0.70 + 0.30 * max(0.0, min(1.0, energy))
        base         = int(base * energy_mult)
        base        += random.randint(-jitter, jitter)
        return max(20, min(127, base))


class GateLengthHumanizer:
    """
    Applies ±3% gate-time randomization to note durations.

    Usage:
        duration = GateLengthHumanizer.apply(raw_duration)

    At a gate of 1.0 beat, the result is uniformly distributed in
    [0.97, 1.03] — subtle enough not to affect MIDI grid snapping
    but sufficient to eliminate machine-perfect uniformity.
    """

    _VARIANCE: float = 0.03   # ±3% of nominal duration

    @classmethod
    def apply(cls, duration: float, variance: float = _VARIANCE) -> float:
        """Return `duration` scaled by 1.0 ± variance (minimum 0.05 beats)."""
        factor = 1.0 + random.uniform(-variance, variance)
        return max(0.05, duration * factor)


class BassVelocityProfile:
    """
    Per-genre velocity profiles calibrated for commercial bass weight.

    Trap 808 / Phonk / House targets 108-120 (floor stays high even in
    low-energy sections) so the sub-bass always drives the low-end mix.
    Lighter genres (classical, jpop) use a moderate 75-100 range.

    Energy scaling: energy_mult = 0.85 + 0.15 × energy
      verse (0.55) → 0.93×  chorus (0.85) → 0.98×  outro (0.25) → 0.89×
    This keeps bass weight consistent; breaks / outros still receive
    a gentle attenuation rather than collapsing to inaudible levels.

    Beat-1 / root-note accent: +8 velocity on the downbeat root hit.
    Machine-gun prevention: ±4 per-note jitter on every note.
    """

    _PROFILES: Dict[str, Tuple[int, int]] = {
        'trap':      (108, 120),   # 808 sub-bass — maximum weight
        'phonk':     (105, 118),   # Memphis 808
        'house':     (108, 118),   # four-on-the-floor low-end driver
        'edm':       (105, 118),   # festival unison bass
        'techno':    (102, 115),   # industrial low-end
        'hiphop':    ( 98, 112),   # boom-bap pocket
        'dnb':       ( 98, 112),   # Reese-bass punch
        'jpop':      ( 85, 100),   # melodic / lighter bass
        'classical': ( 75,  92),   # pizzicato / arco sub
    }
    _DEFAULT: Tuple[int, int]  = (90, 108)
    _ACCENT_BOOST: int         = 8     # beat-1 / root-note accent

    @classmethod
    def velocity(cls, genre: str, step: int, energy: float,
                 is_root: bool = False) -> int:
        """
        Args:
            genre   : composition genre string
            step    : 16th-note step within bar (0 = beat 1)
            energy  : section energy scalar 0.0-1.0
            is_root : True for root-note hits (adds accent boost)
        """
        lo, hi       = cls._PROFILES.get(genre, cls._DEFAULT)
        vel          = random.randint(lo, hi)
        energy_mult  = 0.85 + 0.15 * max(0.0, min(1.0, energy))
        vel          = int(vel * energy_mult)
        if step == 0 or is_root:
            vel = min(127, vel + cls._ACCENT_BOOST)
        vel         += random.randint(-4, 4)   # machine-gun prevention
        return max(30, min(127, vel))
