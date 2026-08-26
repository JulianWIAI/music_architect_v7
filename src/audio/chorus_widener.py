"""
src/audio/chorus_widener.py
────────────────────────────
Chorus-based stereo widener: mono input → stereo (L, R) output.

Two LFO-modulated delay lines run 180° out of phase.  When the two
output channels are summed back to mono the LFO modulation cancels,
preserving mono compatibility with no comb-filter colouration in
summed playback.

Typical use: pad, texture, and lead tracks.
Avoid on kick and bass — low-frequency phase differences cause
cancellation on mono club systems.

Design notes
────────────
The anti-phase LFO pair ensures:
    lfo_L[t] + lfo_R[t] = depth  (constant)

so the delay sum is always the same. This makes the widener transparent
when both channels are played through the same speaker.

The depth and rate are intentionally kept modest (8 ms / 0.45 Hz) to
produce a spacious but natural image. Higher depth values add pitch
modulation character (classic chorus sound); higher rates add vibrato.
"""
from __future__ import annotations

import math

import numpy as np


class ChorusWidener:
    """
    Lightweight stereo widener driven by two anti-phase LFO delay lines.

    Parameters
    ----------
    sample_rate : int
        Audio sample rate (Hz).
    depth_ms : float
        Maximum modulation depth (ms).  7–10 ms gives natural width;
        higher values produce a more obvious chorus character.
    rate_hz : float
        LFO speed (Hz).  0.3–0.7 Hz is natural; > 1 Hz becomes obvious chorus.
    mix : float
        Wet/dry balance [0.0, 1.0].  0.45 gives good width without
        hollowing the centre image.
    """

    def __init__(
        self,
        sample_rate: int   = 44100,
        depth_ms:    float = 8.0,
        rate_hz:     float = 0.45,
        mix:         float = 0.45,
    ) -> None:
        self._sr    = int(sample_rate)
        self._depth = int(depth_ms / 1000.0 * self._sr)
        self._rate  = float(rate_hz)
        self._mix   = float(max(0.0, min(1.0, mix)))
        # Leading silence so delay indices never underrun into negative territory
        self._pad   = self._depth * 2 + 64

    def process(self, mono: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """
        Widen a mono signal to a stereo pair.

        Parameters
        ----------
        mono : np.ndarray, shape (N,)
            Mono input, any float dtype.

        Returns
        -------
        (L, R) : tuple of np.ndarray, each shape (N,), float32.
            L and R are distinct stereo channels.  When summed they
            reproduce the original mono signal without cancellation.
        """
        mono = np.asarray(mono, dtype=np.float64)
        n    = len(mono)
        pad  = self._pad

        # Zero-padded buffer so delay indexing stays in bounds
        buf      = np.zeros(pad + n, dtype=np.float64)
        buf[pad:] = mono

        t = np.arange(n, dtype=np.float64) / self._sr

        # LFO for L channel: depth * (1 + sin) / 2  →  oscillates 0 .. depth
        lfo_L = (self._depth * (1.0 + np.sin(2.0 * math.pi * self._rate * t)) * 0.5
                 ).astype(int)

        # LFO for R channel: exactly anti-phase so lfo_L + lfo_R = depth
        lfo_R = (self._depth - lfo_L).clip(0)

        # Gather delayed samples using integer indices
        idx_base = np.arange(n) + pad
        max_idx  = pad + n - 1
        chorus_L = buf[(idx_base - lfo_L).clip(0, max_idx)]
        chorus_R = buf[(idx_base - lfo_R).clip(0, max_idx)]

        dry = 1.0 - self._mix
        wet = self._mix

        L = (mono * dry + chorus_L * wet).astype(np.float32)
        R = (mono * dry + chorus_R * wet).astype(np.float32)
        return L, R
