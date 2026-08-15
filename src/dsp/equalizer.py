"""
src.dsp.equalizer — Parametric EQ chain with genre-specific master curves.

Genre curves are defined as lists of (ftype, freq_hz, gain_db, q_or_slope) tuples.
Variant curves are additive adjustments applied on top of the genre base curve.

Build a ready-to-use ParametricEQ via:
    eq = build_genre_eq('trap', 'bright', sr=44100)
    processed = eq.apply(samples, sr)
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np
from scipy.signal import sosfilt

from src.dsp.biquad import high_shelf, highpass, low_shelf, lowpass, peaking_eq

# ── Type alias ─────────────────────────────────────────────────────────────────
# (ftype, freq_hz, gain_db, q_or_slope)
_Band = Tuple[str, float, float, float]


# ── Genre master EQ curves ─────────────────────────────────────────────────────
# ftype strings: 'peak', 'loshelf', 'hishelf', 'hp', 'lp'
# q_or_slope column: Q for peak/hp/lp; slope (0–1] for loshelf/hishelf

_GENRE_EQ: dict[str, List[_Band]] = {
    'trap': [
        # sub bass boost, bass warmth, mud cut, snap presence, air top-end
        ('loshelf', 60.0,   2.5, 1.0),
        ('peak',   180.0,   1.5, 1.2),
        ('peak',   350.0,  -2.0, 1.5),
        ('peak',  2500.0,   1.5, 1.5),
        ('hishelf', 10000.0, 1.0, 1.0),
    ],
    'hiphop': [
        ('loshelf',  80.0,  2.0, 1.0),
        ('peak',    200.0,  1.0, 1.2),
        ('peak',    400.0, -1.5, 1.5),
        ('peak',   3000.0,  1.5, 1.5),
        ('hishelf', 8000.0, 1.0, 1.0),
    ],
    'pop': [
        ('peak',    120.0,  1.0, 1.2),
        ('peak',    300.0, -1.0, 1.5),
        ('peak',   1500.0,  1.5, 1.5),
        ('peak',   4000.0,  1.0, 1.5),
        ('hishelf', 10000.0, 2.0, 1.0),
    ],
    'house': [
        ('loshelf',  70.0,  2.0, 1.0),
        ('peak',    160.0,  1.5, 1.2),
        ('peak',    350.0, -1.5, 1.5),
        ('peak',   1000.0,  1.0, 1.5),
        ('hishelf', 9000.0, 1.5, 1.0),
    ],
    'techno': [
        ('loshelf',  60.0,  1.5, 1.0),
        ('peak',    200.0, -1.0, 1.5),
        ('peak',    600.0,  1.0, 1.5),
        ('peak',   4000.0,  2.0, 1.5),
        ('hishelf', 12000.0, 1.0, 1.0),
    ],
    'dnb': [
        ('loshelf',  55.0,  2.0, 1.0),
        ('peak',    150.0,  1.5, 1.2),
        ('peak',    400.0, -2.0, 1.5),
        ('peak',   3000.0,  2.0, 1.5),
        ('hishelf', 10000.0, 1.5, 1.0),
    ],
    'phonk': [
        # heavy sub, bass density, mud cut, mid presence, dark top-end cut
        ('loshelf',  60.0,  3.0, 1.0),
        ('peak',    180.0,  2.0, 1.2),
        ('peak',    350.0, -2.0, 1.5),
        ('peak',   2500.0,  1.0, 1.5),
        ('hishelf', 8000.0, -1.0, 1.0),
    ],
    'edm': [
        ('loshelf',  80.0,  2.0, 1.0),
        ('peak',    200.0, -1.0, 1.5),
        ('peak',    700.0,  1.0, 1.5),
        ('peak',   5000.0,  2.0, 1.5),
        ('hishelf', 12000.0, 2.5, 1.0),
    ],
    'cinematic': [
        ('loshelf',  50.0,  1.0, 1.0),
        ('peak',    300.0, -0.5, 1.5),
        ('peak',   1500.0,  1.0, 1.5),
        ('peak',   4000.0,  1.0, 1.5),
        ('hishelf', 12000.0, 1.5, 1.0),
    ],
    'jpop': [
        ('peak',    120.0,  1.0, 1.2),
        ('peak',    350.0, -1.0, 1.5),
        ('peak',   2000.0,  2.0, 1.5),
        ('peak',   5000.0,  1.5, 1.5),
        ('hishelf', 12000.0, 2.0, 1.0),
    ],
}

# ── Variant adjustments (additive, applied after genre curve) ──────────────────
_VARIANT_EQ: dict[str, List[_Band]] = {
    'bright': [
        ('hishelf', 10000.0,  1.5, 1.0),
        ('peak',     300.0,  -1.0, 1.5),
    ],
    'neutral': [],
    'dark': [
        ('hishelf', 8000.0, -2.0, 1.0),
        ('loshelf', 100.0,   1.5, 1.0),
        ('peak',   4000.0,  -1.0, 1.5),
    ],
}


# ── Helper: build one SOS row from a band tuple ────────────────────────────────

def _band_to_sos(band: _Band, sr: int) -> np.ndarray:
    """Convert a (_Band) tuple to a single (6,) SOS row."""
    ftype, freq_hz, gain_db, q_or_slope = band
    if ftype == 'peak':
        return peaking_eq(freq_hz, gain_db, q_or_slope, sr)
    if ftype == 'loshelf':
        return low_shelf(freq_hz, gain_db, q_or_slope, sr)
    if ftype == 'hishelf':
        return high_shelf(freq_hz, gain_db, q_or_slope, sr)
    if ftype == 'hp':
        return highpass(freq_hz, q_or_slope, sr)
    if ftype == 'lp':
        return lowpass(freq_hz, q_or_slope, sr)
    raise ValueError(f"Unknown filter type: {ftype!r}")


# ── ParametricEQ class ─────────────────────────────────────────────────────────

class ParametricEQ:
    """
    Multi-band parametric EQ implemented as a cascade of biquad SOS sections.

    Usage:
        eq = ParametricEQ()
        eq.add_band(peaking_eq(1000, 3.0, 1.4, sr))
        out = eq.apply(samples_float32, sr)
    """

    def __init__(self) -> None:
        self._bands: List[np.ndarray] = []  # list of (6,) SOS rows

    def add_band(self, sos_row: np.ndarray) -> None:
        """Append one SOS row to the filter cascade."""
        self._bands.append(sos_row)

    def apply(self, samples: np.ndarray, sr: int) -> np.ndarray:
        """
        Apply all EQ bands sequentially to *samples* (float32).

        Handles both mono (N,) and stereo (N, 2) arrays.
        Returns float32 array of the same shape.
        """
        if not self._bands:
            return samples

        # Stack all bands into a (num_bands, 6) SOS matrix
        sos = np.stack(self._bands, axis=0)  # shape (K, 6)

        samples = samples.astype(np.float32)
        if samples.ndim == 1:
            # Mono — single sosfilt pass
            return sosfilt(sos, samples).astype(np.float32)

        # Stereo — process each channel independently
        out = np.empty_like(samples)
        for ch in range(samples.shape[1]):
            out[:, ch] = sosfilt(sos, samples[:, ch])
        return out.astype(np.float32)


# ── Public factory ─────────────────────────────────────────────────────────────

def build_genre_eq(genre: str, variant_id: str, sr: int) -> ParametricEQ:
    """
    Build a ParametricEQ from the genre master curve plus variant adjustments.

    Falls back to 'pop' if *genre* is unknown; 'neutral' if *variant_id* unknown.
    """
    genre_bands   = _GENRE_EQ.get(genre, _GENRE_EQ['pop'])
    variant_bands = _VARIANT_EQ.get(variant_id, [])

    eq = ParametricEQ()
    for band in genre_bands + variant_bands:
        eq.add_band(_band_to_sos(band, sr))
    return eq
