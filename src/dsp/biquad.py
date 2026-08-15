"""
src.dsp.biquad — Biquad filter factories (Audio EQ Cookbook, R. Bristow-Johnson).

Each factory returns a numpy array of shape (6,) representing one SOS row
compatible with scipy.signal.sosfilt:
    [b0/a0, b1/a0, b2/a0, 1.0, a1/a0, a2/a0]

All coefficient formulas follow the Audio EQ Cookbook notation exactly.
"""
from __future__ import annotations

import math

import numpy as np


# ── Internal helper ────────────────────────────────────────────────────────────

def _sos_row(b0: float, b1: float, b2: float,
             a0: float, a1: float, a2: float) -> np.ndarray:
    """Normalise by a0 and pack into a single SOS row (shape (6,))."""
    return np.array([b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0],
                    dtype=np.float64)


# ── Filter factories ───────────────────────────────────────────────────────────

def peaking_eq(freq_hz: float, gain_db: float, q: float, sr: int) -> np.ndarray:
    """
    Peaking (bell) EQ filter.

    A  = 10^(gain_db/40)          — amplitude (not dB)
    w0 = 2*pi*f/sr                — normalised angular frequency
    alpha = sin(w0) / (2*Q)       — EQ Cookbook bandwidth term
    """
    A     = 10.0 ** (gain_db / 40.0)
    w0    = 2.0 * math.pi * freq_hz / sr
    cos_w = math.cos(w0)
    sin_w = math.sin(w0)
    alpha = sin_w / (2.0 * q)

    b0 =  1.0 + alpha * A
    b1 = -2.0 * cos_w
    b2 =  1.0 - alpha * A
    a0 =  1.0 + alpha / A
    a1 = -2.0 * cos_w
    a2 =  1.0 - alpha / A

    return _sos_row(b0, b1, b2, a0, a1, a2)


def high_shelf(freq_hz: float, gain_db: float, slope: float, sr: int) -> np.ndarray:
    """
    High-shelf filter.

    slope ∈ (0, 1] — 1.0 is maximally steep (6 dB/oct per unit of slope).
    A     = 10^(gain_db/40)
    alpha = sin(w0)/2 * sqrt((A + 1/A)*(1/slope - 1) + 2)
    """
    A     = 10.0 ** (gain_db / 40.0)
    w0    = 2.0 * math.pi * freq_hz / sr
    cos_w = math.cos(w0)
    sin_w = math.sin(w0)
    alpha = (sin_w / 2.0) * math.sqrt((A + 1.0 / A) * (1.0 / slope - 1.0) + 2.0)
    sq    = 2.0 * math.sqrt(A) * alpha   # convenience term: 2*sqrt(A)*alpha

    b0 =        A * ((A + 1.0) + (A - 1.0) * cos_w + sq)
    b1 = -2.0 * A * ((A - 1.0) + (A + 1.0) * cos_w)
    b2 =        A * ((A + 1.0) + (A - 1.0) * cos_w - sq)
    a0 =             (A + 1.0) - (A - 1.0) * cos_w + sq
    a1 =  2.0 *      ((A - 1.0) - (A + 1.0) * cos_w)
    a2 =             (A + 1.0) - (A - 1.0) * cos_w - sq

    return _sos_row(b0, b1, b2, a0, a1, a2)


def low_shelf(freq_hz: float, gain_db: float, slope: float, sr: int) -> np.ndarray:
    """
    Low-shelf filter.

    slope ∈ (0, 1] — 1.0 is maximally steep.
    Same alpha calculation as high_shelf; different sign conventions in b/a.
    """
    A     = 10.0 ** (gain_db / 40.0)
    w0    = 2.0 * math.pi * freq_hz / sr
    cos_w = math.cos(w0)
    sin_w = math.sin(w0)
    alpha = (sin_w / 2.0) * math.sqrt((A + 1.0 / A) * (1.0 / slope - 1.0) + 2.0)
    sq    = 2.0 * math.sqrt(A) * alpha

    b0 =        A * ((A + 1.0) - (A - 1.0) * cos_w + sq)
    b1 =  2.0 * A * ((A - 1.0) - (A + 1.0) * cos_w)
    b2 =        A * ((A + 1.0) - (A - 1.0) * cos_w - sq)
    a0 =             (A + 1.0) + (A - 1.0) * cos_w + sq
    a1 = -2.0 *      ((A - 1.0) + (A + 1.0) * cos_w)
    a2 =             (A + 1.0) + (A - 1.0) * cos_w - sq

    return _sos_row(b0, b1, b2, a0, a1, a2)


def highpass(freq_hz: float, q: float, sr: int) -> np.ndarray:
    """
    2nd-order Butterworth-style high-pass filter.

    b0 = (1 + cos(w0)) / 2
    b1 = -(1 + cos(w0))
    b2 = (1 + cos(w0)) / 2
    a0 = 1 + alpha,  a1 = -2*cos(w0),  a2 = 1 - alpha
    """
    w0    = 2.0 * math.pi * freq_hz / sr
    cos_w = math.cos(w0)
    sin_w = math.sin(w0)
    alpha = sin_w / (2.0 * q)

    b0 =  (1.0 + cos_w) / 2.0
    b1 = -(1.0 + cos_w)
    b2 =  (1.0 + cos_w) / 2.0
    a0 =  1.0 + alpha
    a1 = -2.0 * cos_w
    a2 =  1.0 - alpha

    return _sos_row(b0, b1, b2, a0, a1, a2)


def lowpass(freq_hz: float, q: float, sr: int) -> np.ndarray:
    """
    2nd-order Butterworth-style low-pass filter.

    b0 = (1 - cos(w0)) / 2
    b1 = 1 - cos(w0)
    b2 = (1 - cos(w0)) / 2
    a0 = 1 + alpha,  a1 = -2*cos(w0),  a2 = 1 - alpha
    """
    w0    = 2.0 * math.pi * freq_hz / sr
    cos_w = math.cos(w0)
    sin_w = math.sin(w0)
    alpha = sin_w / (2.0 * q)

    b0 = (1.0 - cos_w) / 2.0
    b1 =  1.0 - cos_w
    b2 = (1.0 - cos_w) / 2.0
    a0 =  1.0 + alpha
    a1 = -2.0 * cos_w
    a2 =  1.0 - alpha

    return _sos_row(b0, b1, b2, a0, a1, a2)
