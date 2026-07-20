"""
macro_envelope.py -- Macro-Level Velocity Envelope ("Phrase Breathing").

Music Theory / Performance Context:
    A MIDI arrangement where every note plays at a fixed velocity sounds robotic
    and dead.  Real performers breathe with the music: phrases swell towards their
    emotional peak and then fade as the phrase resolves.  This phenomenon occurs
    at two timescales:

        MICRO (Δv per note): ±8 velocity jitter -- already implemented in humanizer.py
        MACRO (LFO per phrase): the ENTIRE phrase rises and falls over 16-32 bars

    This module implements the MACRO level using a mathematical sine-wave LFO
    (Low Frequency Oscillator) that spans the full phrase length.

LFO Formula:
    V_macro(t) = V_base + A · sin(2π · t / T + φ)

    Where:
        t : absolute beat position in the song
        T : phrase cycle length in beats (16 bars × 4 beats = 64 beats default)
        A : amplitude -- maximum velocity swing ±A (default ±22)
        φ : per-track phase offset -- staggers the peaks so tracks don't all
            swell simultaneously (which would be unnatural)

    Result:
        V_base - A  →  minimum (bottom of breath / decrescendo)
        V_base      →  midpoint (steady state)
        V_base + A  →  maximum (top of phrase / crescendo peak)

    At T=64 beats (16 bars at 4/4):
        beat 0   → V_base (neutral start)
        beat 16  → V_base + A (peak, bar 4)
        beat 32  → V_base (return to neutral, bar 8 -- phrase midpoint)
        beat 48  → V_base - A (trough, bar 12 -- breath before next phrase)
        beat 64  → V_base (repeat)

Phase Offsets Per Track (defaults):
    04_Melody  : φ = 0.0           -- peaks first (melody leads the phrase)
    05_Chords  : φ = π/4  (45°)    -- peaks slightly after melody
    06_Pad     : φ = π/2  (90°)    -- peaks at melody's halfway point (lagged)
    09_Texture : φ = -π/4 (-45°)   -- peaks slightly before melody (counter-motion)

    This staggered phasing creates the "breathing" effect where different stems
    swell at slightly different times, mimicking a real ensemble.

Layered LFOs (optional):
    A second LFO at a different frequency is superimposed for complex dynamics.
    e.g., a 32-bar "macro arch" + a 4-bar "micro swell":

        V(t) = V_base + A1·sin(2π·t/T1 + φ) + A2·sin(2π·t/T2 + φ2)

    A2 << A1 so the micro swell is subtle (±8) compared to macro (±22).
"""

from __future__ import annotations
import math
from typing import Optional


# Default LFO parameters
DEFAULT_PHRASE_BARS     = 16        # one complete LFO cycle (16 bars)
DEFAULT_BAR_BEATS       = 4.0       # 4/4 time
DEFAULT_AMPLITUDE       = 22        # ± 22 velocity units (peak swing)
DEFAULT_MICRO_AMPLITUDE = 8         # secondary LFO amplitude (subtle)
DEFAULT_MICRO_RATIO     = 4         # secondary LFO runs 4× faster than macro

# Per-track phase offsets (radians) -- stagger the breathing peaks
TRACK_PHASE_OFFSETS = {
    '04_Melody':  0.0,
    '05_Chords':  math.pi / 4,       #  45° lag behind melody
    '06_Pad':     math.pi / 2,       #  90° lag (peaks when melody is half-done)
    '09_Texture': -math.pi / 4,      # -45° (peaks just before melody)
}


class MacroVelocityEnvelope:
    """
    Applies a phrase-level sine-wave LFO to MIDI velocity values.

    Attach one instance per track generator.  Call .apply(base_vel, beat)
    for every note to get the dynamically shaped velocity.

    Parameters
    ----------
    track_name      : e.g. '04_Melody' -- used to look up phase offset
    phrase_bars     : LFO period in bars (default 16)
    bar_beats       : beats per bar (default 4.0)
    amplitude       : peak velocity swing ±A (default 22)
    song_start_beat : absolute beat where the song begins (always 0.0)
    seed            : optional int for deterministic phase randomization
    """

    def __init__(
        self,
        track_name:       str,
        phrase_bars:      int   = DEFAULT_PHRASE_BARS,
        bar_beats:        float = DEFAULT_BAR_BEATS,
        amplitude:        int   = DEFAULT_AMPLITUDE,
        song_start_beat:  float = 0.0,
        seed:             Optional[int] = None,
    ):
        self.track_name = track_name

        # LFO period in beats
        self._T = phrase_bars * bar_beats

        # Primary amplitude
        self._A = amplitude

        # Secondary (micro-swell) LFO
        self._A2 = DEFAULT_MICRO_AMPLITUDE
        self._T2 = self._T / DEFAULT_MICRO_RATIO   # faster cycle

        # Phase offset: look up by track name, then add small random jitter
        self._phi = TRACK_PHASE_OFFSETS.get(track_name, 0.0)
        if seed is not None:
            # Add ±0.2 radians of phase randomization per track instance
            import random
            rng = random.Random(seed + abs(hash(track_name)))
            self._phi += rng.uniform(-0.2, 0.2)

        # Secondary LFO phase (offset by π so the micro-swell is counter-phase
        # to the macro, creating a subtle waver rather than a simple addition)
        self._phi2 = self._phi + math.pi

        self._song_start = song_start_beat

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def apply(self, base_vel: int, beat: float) -> int:
        """
        Return the macro-envelope-modulated velocity for a note at `beat`.

        V(t) = base_vel + A·sin(2π·t/T + φ) + A2·sin(2π·t/T2 + φ2)

        Parameters
        ----------
        base_vel : the note's base MIDI velocity (before macro shaping)
        beat     : absolute beat position of the note in the song

        Returns
        -------
        int clamped to [1, 127]
        """
        t = beat - self._song_start

        # Primary LFO (16-bar slow breath)
        primary = self._A * math.sin(2.0 * math.pi * t / self._T + self._phi)

        # Secondary LFO (4-bar subtle micro-swell)
        secondary = self._A2 * math.sin(2.0 * math.pi * t / self._T2 + self._phi2)

        shaped = int(base_vel + primary + secondary)
        return max(1, min(127, shaped))

    def envelope_value(self, beat: float) -> float:
        """
        Return the raw LFO value at `beat` in the range [-1.0, +1.0].

        Useful for scaling other parameters (not just velocity) such as
        filter cutoff or reverb depth.
        """
        t = beat - self._song_start
        primary   = math.sin(2.0 * math.pi * t / self._T + self._phi)
        secondary = (self._A2 / self._A) * math.sin(
            2.0 * math.pi * t / self._T2 + self._phi2
        )
        # Blend: primary dominates (weight 0.85), secondary adds texture (0.15)
        return 0.85 * primary + 0.15 * secondary


# ---------------------------------------------------------------------------
# Convenience factory function
# ---------------------------------------------------------------------------

def make_envelope(track_name: str, total_bars: int,
                  bar_beats: float = 4.0,
                  seed: Optional[int] = None) -> MacroVelocityEnvelope:
    """
    Create a MacroVelocityEnvelope with automatically scaled phrase_bars.

    For short songs (< 32 bars): phrase_bars = total_bars / 2
    For medium songs (32-96 bars): phrase_bars = 16 (one full cycle per half-song)
    For long songs (> 96 bars): phrase_bars = 32 (slow, cinematic breathing)

    This ensures the LFO always completes at least 2 full cycles per song,
    giving a clear arc structure regardless of song length.
    """
    if total_bars < 32:
        phrase_bars = max(4, total_bars // 2)
    elif total_bars <= 96:
        phrase_bars = 16
    else:
        phrase_bars = 32

    return MacroVelocityEnvelope(
        track_name  = track_name,
        phrase_bars = phrase_bars,
        bar_beats   = bar_beats,
        seed        = seed,
    )
