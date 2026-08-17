"""
dithering.py — TPDF (Triangular Probability Density Function) dithering.

Why dither?
-----------
When reducing bit depth — e.g. from 32-bit float to 24-bit integer — each
sample is rounded to the nearest representable integer value.  This rounding
introduces a *quantisation error* that is mathematically correlated with the
original signal.  At low amplitudes (fades, reverb tails) this correlation
becomes audible as harmonic distortion or "graininess".

Dithering adds a tiny amount of shaped noise *before* quantisation.  The
noise decorrelates the rounding error, converting it from correlated distortion
into a low-level, spectrally flat hiss that sits well below the noise floor of
the target bit depth and is inaudible at normal listening levels.

TPDF is the industry-standard reference algorithm: two independent uniform
random values are summed to produce a triangular distribution.  This achieves
complete decorrelation with a noise variance of exactly 1/6 LSB² — one third
less power than rectangular dither, with no spectral colouration.

For 24-bit output (mastering standard) the dither level is at approximately
−144 dBFS — far below audible range.  For 16-bit output it sits at ≈ −93 dBFS,
still below the noise floor of most analog playback chains.

Reference
---------
Wannamaker, R. A., Lipshitz, S. P., Vanderkooy, J. & Wright, J. N. (2000).
"A Theory of Nonsubtractive Dither." IEEE Transactions on Signal Processing.
"""

from __future__ import annotations

import numpy as np


class TPDFDither:
    """
    Applies Triangular Probability Density Function dithering to a float array.

    Usage
    -----
        dither = TPDFDither()
        dithered = dither.apply(float32_array, bit_depth=24)
        # pass dithered directly to integer quantisation

    The class is stateless; a single instance can be reused across many calls.
    """

    def apply(self, samples: np.ndarray, bit_depth: int) -> np.ndarray:
        """
        Add TPDF dither noise to *samples* in preparation for quantisation
        to *bit_depth* integer bits.

        Parameters
        ----------
        samples : np.ndarray, dtype float32 or float64
            Audio samples normalised to the range [−1.0, +1.0].
            May be 1-D (mono) or 2-D (frames × channels).
        bit_depth : int
            Target integer bit depth after quantisation (typically 16 or 24).
            This determines the amplitude of one LSB in the float domain.

        Returns
        -------
        np.ndarray, dtype float32
            Dithered samples in the same shape as *samples*, still in the
            [−1.0, +1.0] float range — ready for integer conversion by the
            caller.  Samples are NOT clipped here; clipping is left to the
            quantiser so that the dither noise itself is never hard-clipped.

        Notes
        -----
        One LSB in float notation = 1 / 2^(bit_depth − 1).
        The triangular distribution is formed by summing two independent
        uniform U[−0.5, +0.5] variables — each scaled to one LSB — giving
        a triangular PDF over [−1, +1] LSB with zero mean.
        """
        # One least-significant bit expressed as a fraction of full scale
        lsb = 1.0 / (2 ** (bit_depth - 1))

        # Two independent rectangular distributions summed → triangular PDF.
        # Each is scaled to ±0.5 LSB so their sum spans ±1 LSB.
        noise = (
            np.random.uniform(-0.5, 0.5, samples.shape) +
            np.random.uniform(-0.5, 0.5, samples.shape)
        ) * lsb

        # Add noise and return as float32; precision beyond float32 is not
        # needed since the target is integer PCM
        return (samples + noise).astype(np.float32)
