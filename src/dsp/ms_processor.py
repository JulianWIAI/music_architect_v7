"""
src.dsp.ms_processor — Mid/Side stereo processing.

Mid/Side encoding:
    M = (L + R) / sqrt(2)     — correlated (mono-compatible) content
    S = (L - R) / sqrt(2)     — difference (width/stereo) content

Decoding:
    L = (M + S) / sqrt(2)
    R = (M - S) / sqrt(2)

The Side channel is high-passed (remove low-end smear) and shelf-boosted
(widen the top end).  The Mid channel can receive an independent shelf
adjustment (e.g. for mono LF focus).  On mono input the processor is a no-op.

Genre parameters are read from the 'ms_mastering' key of the genre JSON dict.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import sosfilt

from src.dsp.biquad import high_shelf, highpass

# sqrt(2) constant for encode/decode
_SQRT2 = float(np.sqrt(2.0))


class MSProcessor:
    """
    Mid/Side mastering processor for stereo signals.

    Parameters
    ----------
    side_hpf_hz : float
        High-pass cutoff (Hz) for the Side channel (removes muddy LF divergence).
    side_hpf_q : float
        Q factor of the Side channel HPF.
    side_shelf_db : float
        High-shelf gain (dB) applied to the Side channel to widen top-end.
    side_shelf_hz : float
        High-shelf transition frequency (Hz) for the Side channel.
    mid_shelf_db : float
        High-shelf gain (dB) for the Mid channel (0 = bypass).
    """

    def __init__(
        self,
        side_hpf_hz:   float = 200.0,
        side_hpf_q:    float = 0.707,
        side_shelf_db: float = 1.5,
        side_shelf_hz: float = 8000.0,
        mid_shelf_db:  float = 0.0,
    ) -> None:
        self.side_hpf_hz   = side_hpf_hz
        self.side_hpf_q    = side_hpf_q
        self.side_shelf_db = side_shelf_db
        self.side_shelf_hz = side_shelf_hz
        self.mid_shelf_db  = mid_shelf_db

    def process(self, samples: np.ndarray, sr: int) -> np.ndarray:
        """
        Apply M/S processing to *samples* (float32, shape (N,) or (N, 2)).

        Mono input is returned unchanged.
        """
        samples = samples.astype(np.float32)

        if samples.ndim == 1 or samples.shape[1] == 1:
            # Mono — M/S is meaningless; return as-is
            return samples

        L = samples[:, 0].astype(np.float64)
        R = samples[:, 1].astype(np.float64)

        # ── Encode to M/S ──────────────────────────────────────────────────────
        M = (L + R) / _SQRT2
        S = (L - R) / _SQRT2

        # ── Process Side channel ───────────────────────────────────────────────
        # 1. High-pass: remove low-frequency divergence from the side signal
        sos_hpf  = highpass(self.side_hpf_hz, self.side_hpf_q, sr).reshape(1, 6)
        S        = sosfilt(sos_hpf, S)

        # 2. High-shelf: add top-end width
        sos_side_shelf = high_shelf(self.side_shelf_hz, self.side_shelf_db,
                                    slope=1.0, sr=sr).reshape(1, 6)
        S = sosfilt(sos_side_shelf, S)

        # ── Process Mid channel (optional) ────────────────────────────────────
        if abs(self.mid_shelf_db) > 1e-6:
            sos_mid_shelf = high_shelf(self.side_shelf_hz, self.mid_shelf_db,
                                       slope=1.0, sr=sr).reshape(1, 6)
            M = sosfilt(sos_mid_shelf, M)

        # ── Decode back to L/R ─────────────────────────────────────────────────
        L_out = ((M + S) / _SQRT2).astype(np.float32)
        R_out = ((M - S) / _SQRT2).astype(np.float32)

        out = np.stack([L_out, R_out], axis=1)
        return out.astype(np.float32)


def _safe_float(value, default: float) -> float:
    """Parse a potentially mixed-type value to float, returning *default* on failure."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def from_genre_data(genre_data) -> MSProcessor:
    """
    Build an MSProcessor from the 'ms_mastering' key of *genre_data*.

    All fields use safe parsing — missing or invalid values fall back to defaults.
    """
    ms = {}
    if genre_data and isinstance(genre_data, dict):
        ms = genre_data.get('ms_mastering', {}) or {}

    return MSProcessor(
        side_hpf_hz   = _safe_float(ms.get('side_hpf_hz'),   200.0),
        side_hpf_q    = 0.707,   # 12 dB/oct Butterworth Q — not stored in JSON
        side_shelf_db = _safe_float(ms.get('side_shelf_db'),  1.5),
        side_shelf_hz = _safe_float(ms.get('side_shelf_hz'),  8000.0),
        mid_shelf_db  = _safe_float(ms.get('mid_shelf_db'),   0.0),
    )
