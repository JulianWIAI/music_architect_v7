"""
src/dsp/lfo_engine.py
──────────────────────
Aperiodic LFO engine for named DSP parameter targets.

``AperiodicLFOEngine`` generates smoothly varying modulation signals for the
targets listed in a ``GenreProfile``.  Unlike a conventional LFO it does NOT
use a fixed period.  Instead it operates as a **sample-and-hold system with
smooth interpolation**:

1. A hold value and hold duration are drawn at random within the profile's
   ``[lfo_rate_bars_min, lfo_rate_bars_max]`` range.
2. The output linearly (or sinusoidally, depending on waveform) interpolates
   from the current value toward the target hold value.
3. When the hold duration elapses a new target and duration are drawn.

This avoids the mechanical, predictable feel of a regular LFO while still
providing smooth parameter motion over musical time.

All output values are normalised to ``[0.0, 1.0]``.  The C++/Python DSP layer
is responsible for scaling to the actual parameter range.  The
``set_target_range()`` method allows overriding this range per-target so the
engine can also produce directly usable values when called from Python.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.midi.genre_profiles import GenreProfile


class AperiodicLFOEngine:
    """
    Aperiodic (variable-rate) LFO engine driven by a ``GenreProfile``.

    Each LFO *target* is independent: it maintains its own current value,
    target hold value, hold duration, and elapsed sample counter.

    Parameters
    ----------
    profile : GenreProfile
        Provides the list of targets, rate range, waveform type, and BPM
        context for computing hold times in samples.
    bpm : float
        Current tempo.  Used to convert bar durations to sample counts.
    sample_rate : int
        Audio sample rate (default 48 000 Hz).
    seed : int | None
        Random seed for reproducibility.
    """

    def __init__(
        self,
        profile: "GenreProfile",
        bpm: float,
        sample_rate: int = 48_000,
        seed: Optional[int] = None,
    ) -> None:
        self._profile = profile
        self._bpm = bpm
        self._sample_rate = sample_rate
        self._rng = random.Random(seed)

        # Per-target state dictionaries.
        # Keys are target name strings from profile.lfo_targets.
        self._current_value: Dict[str, float] = {}
        self._target_value:  Dict[str, float] = {}
        self._hold_samples:  Dict[str, int] = {}   # total samples for current hold
        self._elapsed:       Dict[str, int] = {}   # samples elapsed in current hold

        # Optional per-target output range (min, max).  Default: (0.0, 1.0).
        self._ranges: Dict[str, Tuple[float, float]] = {}

        # Phase accumulator for sine waveform (separate per target).
        self._sine_phase: Dict[str, float] = {}

        self._init_targets()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def next_block(self, block_size: int) -> Dict[str, List[float]]:
        """
        Generate *block_size* samples for each LFO target.

        Returns
        -------
        dict
            ``{target_name: [float, …]}`` where each list has length
            ``block_size`` and values are in the registered range
            (default 0.0–1.0).
        """
        result: Dict[str, List[float]] = {}
        waveform = self._profile.lfo_waveform

        for target in self._profile.lfo_targets:
            samples = self._generate_target_block(target, block_size, waveform)
            result[target] = samples

        return result

    def set_target_range(
        self, target: str, min_val: float, max_val: float
    ) -> None:
        """
        Override the output range for *target*.

        After this call, ``next_block()`` will return values in
        ``[min_val, max_val]`` for this target instead of ``[0.0, 1.0]``.
        """
        self._ranges[target] = (min_val, max_val)

    def reset(self) -> None:
        """
        Reset all LFO targets to their initial state.

        Call when the song restarts so the LFO starts from a clean slate
        rather than mid-modulation.
        """
        self._init_targets()

    def update_bpm(self, bpm: float) -> None:
        """
        Update the tempo and recalculate hold times for all active targets.

        The *current* hold phase is preserved (elapsed sample count does not
        change) but the total hold duration is recomputed at the new tempo so
        the remaining modulation time is correct.
        """
        self._bpm = bpm
        for target in self._profile.lfo_targets:
            # Keep elapsed samples unchanged; only rescale hold_samples.
            old_hold = self._hold_samples.get(target, 1)
            old_elapsed = self._elapsed.get(target, 0)
            progress = old_elapsed / max(1, old_hold)
            new_hold = self._draw_hold_samples()
            self._hold_samples[target] = new_hold
            # Preserve proportional progress to avoid sudden jumps.
            self._elapsed[target] = int(progress * new_hold)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_targets(self) -> None:
        """Initialise per-target state for all targets in the profile."""
        for target in self._profile.lfo_targets:
            start_val = self._rng.random()
            self._current_value[target] = start_val
            self._target_value[target]  = self._rng.random()
            self._hold_samples[target]  = self._draw_hold_samples()
            self._elapsed[target]       = 0
            self._sine_phase[target]    = self._rng.uniform(0.0, 2.0 * math.pi)

    def _draw_hold_samples(self) -> int:
        """
        Draw a random hold duration in samples within the profile's bar-rate range.

        hold_time_samples = hold_bars × beats_per_bar × beat_duration_s × sample_rate
        """
        lo = self._profile.lfo_rate_bars_min
        hi = self._profile.lfo_rate_bars_max
        if hi <= 0.0 or lo <= 0.0:
            # Waveform is "none" or rates are zero — return a large hold so
            # the output stays flat.
            return self._sample_rate * 4 * 64  # ~64 bars of silence
        hold_bars = self._rng.uniform(lo, hi)
        beat_s = 60.0 / max(self._bpm, 1.0)
        hold_s = hold_bars * 4.0 * beat_s   # 4 beats per bar
        return max(1, int(hold_s * self._sample_rate))

    def _scale(self, target: str, raw: float) -> float:
        """Map a normalised value in [0.0, 1.0] to the target's registered range."""
        lo, hi = self._ranges.get(target, (0.0, 1.0))
        return lo + raw * (hi - lo)

    def _generate_target_block(
        self, target: str, block_size: int, waveform: str
    ) -> List[float]:
        """
        Generate ``block_size`` samples for *target* using *waveform* mode.

        Handles the hold-point logic: when the current hold expires, new target
        value and hold duration are drawn.
        """
        output: List[float] = []

        for _ in range(block_size):
            sample = self._compute_sample(target, waveform)
            output.append(self._scale(target, sample))

            # Advance elapsed counter; refresh hold state when expired.
            self._elapsed[target] += 1
            if self._elapsed[target] >= self._hold_samples[target]:
                self._current_value[target] = self._target_value[target]
                self._target_value[target]  = self._rng.random()
                self._hold_samples[target]  = self._draw_hold_samples()
                self._elapsed[target]       = 0

        return output

    def _compute_sample(self, target: str, waveform: str) -> float:
        """
        Compute one normalised sample for *target* under the given *waveform*.

        Returns a value in [0.0, 1.0].
        """
        if waveform == "none":
            return 0.0

        elapsed = self._elapsed[target]
        hold    = self._hold_samples[target]
        current = self._current_value[target]
        tgt_val = self._target_value[target]

        if waveform == "sample_hold":
            # Flat hold — stay at current value until hold time expires.
            return current

        if waveform == "random_ramp":
            # Linear ramp from current to target over the hold period.
            if hold <= 0:
                return tgt_val
            t = elapsed / hold
            return current + (tgt_val - current) * t

        if waveform == "sine":
            # Sine wave at a period matching the hold duration.
            # Phase advances per sample so the period = hold_samples.
            if hold <= 0:
                return 0.5
            freq_hz = self._sample_rate / max(1, hold)
            phase = self._sine_phase[target] + 2.0 * math.pi * elapsed / hold
            raw = 0.5 + 0.5 * math.sin(phase)
            return raw

        if waveform == "square":
            # Alternates 0.0 and 1.0 at hold_samples rate.
            half = max(1, hold // 2)
            return 1.0 if (elapsed < half) else 0.0

        # Fallback: linear ramp (same as random_ramp).
        if hold <= 0:
            return tgt_val
        t = elapsed / hold
        return current + (tgt_val - current) * t
