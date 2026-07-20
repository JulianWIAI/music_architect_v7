"""
humanizer.py -- Global micro-timing and velocity humanization for all backing stems.

Music Theory / DSP Context:
    Human musicians do NOT play perfectly on the grid.  Their note-on events
    arrive slightly early or late (micro-timing) and with natural velocity
    variation (touch dynamics).  Emulating this "human feel" is essential for
    MIDI that sounds like a real performance rather than a sequenced robot.

    We model two independent jitter sources:
    1. Micro-timing delta Δt:
           t_human = t_grid + Δt
           Δt ~ Uniform(-max_ms, +max_ms) converted to beats
       Applied to all backing stems (tracks 1,3,5,6,7,8) but NOT drums
       (drums use a separate groove-quantize engine in composition_engine.py).

    2. Velocity jitter Δv:
           Vout = clamp(Vbase + Δv, 1, 127)
           Δv   ~ Uniform(-range_v, +range_v) scaled by intensity
       Applied to all non-drum MIDI channels.

Deterministic seeding:
    Both jitter sources are driven by a seeded random.Random() instance so that
    every run with the same seed_value produces identical micro-timing.  This is
    critical for reproducibility in the evolutionary fitness loop.

Stem index map (which tracks get humanized):
    01_Kick       -- drums, NOT humanized here (handled by drum engine)
    02_Percussion -- drums, NOT humanized here
    03_Bass       -- YES (timing tightens groove feel)
    04_Melody     -- YES
    05_Chords     -- YES
    06_Pad        -- YES (tiny drift on pad creates warmth)
    07_Arp        -- YES
    08_Stabs      -- YES
    09_Texture    -- YES
    10_FX         -- NO  (sparse events, placed precisely)
"""

from __future__ import annotations
import random
from typing import List, Tuple, Optional

Note = Tuple[float, float, int, int]   # (time, duration, midi_note, velocity)

# Default humanization constants
DEFAULT_MAX_TIMING_MS  = 12.0   # ±12 ms at BPM reference -- subtle but audible
DEFAULT_VELOCITY_RANGE = 8      # ±8 MIDI velocity units per stem note


class MicroTimingHumanizer:
    """
    Applies deterministic micro-timing and velocity jitter to a list of notes.

    Parameters
    ----------
    bpm         : tempo (beats per minute) -- needed to convert ms ↔ beats
    seed        : deterministic seed (use track seed_value for reproducibility)
    max_ms      : maximum ±timing offset in milliseconds
    vel_range   : maximum ±velocity offset in MIDI units (0-127)
    intensity   : overall humanization strength 0.0 (none) to 1.0 (full)
    """

    def __init__(
        self,
        bpm:       float = 120.0,
        seed:      Optional[int] = None,
        max_ms:    float = DEFAULT_MAX_TIMING_MS,
        vel_range: int   = DEFAULT_VELOCITY_RANGE,
        intensity: float = 0.6,
    ):
        self.bpm       = bpm
        self.max_ms    = max_ms * intensity
        self.vel_range = int(vel_range * intensity)
        # Seeded RNG -- identical seeds produce identical feel
        self._rng = random.Random(seed if seed is not None else 0)

    # ------------------------------------------------------------------
    # Beat ↔ millisecond conversion
    # ------------------------------------------------------------------

    def _ms_to_beats(self, ms: float) -> float:
        """Convert milliseconds to beat units at the current BPM."""
        beats_per_second = self.bpm / 60.0
        return (ms / 1000.0) * beats_per_second

    # ------------------------------------------------------------------
    # Single-note humanization
    # ------------------------------------------------------------------

    def humanize_note(self, note: Note) -> Note:
        """
        Apply Δt timing jitter and Δv velocity jitter to a single note.

        Δt is applied to note-on time only (duration is unchanged).
        Δv is clamped to MIDI range [1, 127].
        """
        t, dur, pitch, vel = note

        # Timing jitter: Δt in beats
        dt_beats = self._ms_to_beats(
            self._rng.uniform(-self.max_ms, self.max_ms)
        )
        # Prevent notes from going negative in time
        new_t = max(0.0, t + dt_beats)

        # Velocity jitter: Δv
        dv = self._rng.randint(-self.vel_range, self.vel_range)
        new_vel = max(1, min(127, vel + dv))

        return (new_t, dur, pitch, new_vel)

    # ------------------------------------------------------------------
    # Batch humanization
    # ------------------------------------------------------------------

    def humanize(self, notes: List[Note]) -> List[Note]:
        """
        Humanize a full list of notes and return a new list sorted by time.

        Notes are re-sorted after humanization because timing jitter can
        cause minor reorderings.
        """
        result = [self.humanize_note(n) for n in notes]
        result.sort(key=lambda n: n[0])
        return result

    def humanize_track(self, notes: List[Note],
                       track_name: str) -> List[Note]:
        """
        Humanize a named track.  Drum tracks ('01_Kick', '02_Percussion') are
        returned unchanged; all other tracks receive full humanization.
        """
        skip = {'01_Kick', '02_Percussion', '10_FX'}
        if track_name in skip:
            return notes
        return self.humanize(notes)


# ---------------------------------------------------------------------------
# Standalone helper functions (used by individual generators)
# ---------------------------------------------------------------------------

def apply_timing_jitter(t: float, bpm: float, max_ms: float,
                        rng: random.Random) -> float:
    """
    Return a humanized beat position for a single note-on event.

    Parameters
    ----------
    t      : original grid-quantized beat position
    bpm    : tempo in BPM
    max_ms : maximum ±offset in milliseconds
    rng    : caller-supplied random.Random for deterministic reproducibility

    Returns
    -------
    float -- humanized beat position, clamped to >= 0.0
    """
    beats_per_second = bpm / 60.0
    dt = (rng.uniform(-max_ms, max_ms) / 1000.0) * beats_per_second
    return max(0.0, t + dt)


def apply_velocity_jitter(vel: int, range_v: int, rng: random.Random) -> int:
    """
    Return a humanized velocity value.

    Parameters
    ----------
    vel     : base MIDI velocity
    range_v : maximum ±velocity jitter
    rng     : caller-supplied random.Random

    Returns
    -------
    int in [1, 127]
    """
    dv = rng.randint(-range_v, range_v)
    return max(1, min(127, vel + dv))


def humanize_notes_batch(
    notes:    List[Note],
    bpm:      float,
    max_ms:   float = DEFAULT_MAX_TIMING_MS,
    vel_range: int  = DEFAULT_VELOCITY_RANGE,
    seed:     Optional[int] = None,
    intensity: float = 0.6,
) -> List[Note]:
    """
    Convenience wrapper: humanize a list of notes in one call.

    Returns the humanized list sorted by time.
    """
    h = MicroTimingHumanizer(
        bpm=bpm, seed=seed, max_ms=max_ms, vel_range=vel_range, intensity=intensity
    )
    return h.humanize(notes)
