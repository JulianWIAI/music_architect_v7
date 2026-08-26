"""Transient shaper: boosts attack transients and optionally cuts sustain body."""

import math
import numpy as np


class TransientShaper:
    """
    Transient shaper using dual-envelope detection.

    Two 1-pole IIR envelope followers with different time constants track
    the input signal simultaneously.  The difference between a fast envelope
    (which captures transients) and a slow envelope (which tracks the sustain
    body) produces a transient mask.  Gain is modulated per-sample to boost
    or attenuate transients and sustained portions independently.

    Parameters
    ----------
    sample_rate : int
        Audio sample rate in Hz.
    attack_boost_db : float
        Gain applied to detected transient portions (positive = boost).
    sustain_cut_db : float
        Gain applied to the sustained portion.  Use negative values to cut
        sustain (e.g. -3.0) or 0.0 to leave it unchanged.
    """

    def __init__(
        self,
        sample_rate: int,
        attack_boost_db: float = 3.0,
        sustain_cut_db: float = 0.0,
    ) -> None:
        self._sample_rate = int(sample_rate)

        # Pre-compute linear gain multipliers from dB values
        self._attack_gain = 10.0 ** (attack_boost_db / 20.0)
        # sustain_cut_db is typically <= 0; negative values reduce sustain gain
        self._sustain_gain = 10.0 ** (sustain_cut_db / 20.0)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _envelope(
        self,
        audio: np.ndarray,
        attack_ms: float,
        release_ms: float,
    ) -> np.ndarray:
        """
        1-pole IIR envelope follower.

        Uses separate attack and release smoothing coefficients so the
        envelope rises quickly on transients (small attack_ms) and falls
        slowly on sustain (larger release_ms).

        Parameters
        ----------
        audio : np.ndarray
            Input signal (float64).
        attack_ms : float
            Attack time constant in milliseconds.
        release_ms : float
            Release time constant in milliseconds.

        Returns
        -------
        np.ndarray
            Smoothed amplitude envelope (float64), same length as audio.
        """
        sr = self._sample_rate

        # IIR smoothing coefficients: a = exp(-1 / (time_s * sr))
        a_att = math.exp(-1.0 / (attack_ms / 1000.0 * sr))
        a_rel = math.exp(-1.0 / (release_ms / 1000.0 * sr))

        env = np.empty(len(audio), dtype=np.float64)
        state = 0.0

        for i in range(len(audio)):
            abs_s = abs(audio[i])
            # Attack coefficient when signal is rising, release when falling
            coef = a_att if abs_s > state else a_rel
            state = coef * state + (1.0 - coef) * abs_s
            env[i] = state

        return env

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, audio: np.ndarray) -> np.ndarray:
        """
        Apply transient shaping to an audio buffer.

        Workflow:
          1. Fast envelope  (attack=0.1 ms, release=50 ms)  detects transients.
          2. Slow envelope  (attack=20 ms,  release=200 ms) tracks sustain.
          3. transient_mask = clip(fast - slow, 0, 1)
          4. sustain_mask   = clip(slow / (fast + epsilon), 0, 1)
          5. Per-sample gain = 1 + transient_mask*(attack_gain-1)
                                 + sustain_mask*(sustain_gain-1)
          6. Output is hard-clipped to [-1, 1] to prevent clipping artefacts.

        Parameters
        ----------
        audio : np.ndarray
            Input audio as float32 (mono).

        Returns
        -------
        np.ndarray
            Transient-shaped output as float32, clipped to [-1, 1].
        """
        audio = np.asarray(audio, dtype=np.float32)
        x = audio.astype(np.float64)

        # Dual-envelope detection
        fast_env = self._envelope(x, attack_ms=0.1, release_ms=50.0)
        slow_env = self._envelope(x, attack_ms=20.0, release_ms=200.0)

        # Transient mask: regions where the fast envelope overshoots the slow one
        transient_mask = np.clip(fast_env - slow_env, 0.0, 1.0)

        # Sustain mask: regions where the signal is mostly sustained (no transient)
        sustain_mask = np.clip(slow_env / (fast_env + 1e-9), 0.0, 1.0)

        # Build per-sample gain envelope
        gain = (
            1.0
            + transient_mask * (self._attack_gain - 1.0)
            + sustain_mask * (self._sustain_gain - 1.0)
        )

        # Apply gain and hard-clip
        out = np.clip(x * gain, -1.0, 1.0)
        return out.astype(np.float32)
