"""
src.dsp.parallel_compression — NY-style parallel (blend) compression.

The wet signal path is band-limited, heavily compressed, and mixed back with
the unprocessed dry signal.  This preserves transient punch while adding
density and glue.

Genre-specific parameters are loaded from the 'parallel_compression' key of
the genre JSON data dict (see data/production_guide/json/*.json).
"""
from __future__ import annotations

import re

import numpy as np
from scipy.signal import sosfilt

from src.dsp.biquad import highpass, lowpass
from src.dsp.compressor import Compressor

# ── Defaults ───────────────────────────────────────────────────────────────────
_DEF_WET_PCT    = 40.0
_DEF_RATIO      = 10.0
_DEF_THR_DB     = -30.0
_DEF_ATTACK_MS  =  2.0
_DEF_RELEASE_MS = 80.0
_DEF_MAKEUP_DB  =  6.0
_DEF_HPF_HZ     = 80.0
_DEF_LPF_HZ     = 14000.0


def _safe_float(value, default: float) -> float:
    """
    Safely convert *value* to float.

    Handles strings such as '40-60 (target 50)' by extracting the first
    numeric token; returns *default* on failure.
    """
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    # Extract the first number from strings like '10:1' → 10, '40-60 …' → 40
    m = re.search(r'[-+]?\d+(?:\.\d+)?', str(value))
    return float(m.group()) if m else default


class ParallelCompressor:
    """
    NY-style parallel compressor.

    Parameters
    ----------
    wet_pct : float
        Wet signal blend percentage (0–100).
    ratio, threshold_db, attack_ms, release_ms, makeup_db : float
        Inner compressor parameters.
    hpf_hz, lpf_hz : float
        Band-limit the wet path before compression (avoids pumping sub/air).
    """

    def __init__(
        self,
        wet_pct:      float = _DEF_WET_PCT,
        ratio:        float = _DEF_RATIO,
        threshold_db: float = _DEF_THR_DB,
        attack_ms:    float = _DEF_ATTACK_MS,
        release_ms:   float = _DEF_RELEASE_MS,
        makeup_db:    float = _DEF_MAKEUP_DB,
        hpf_hz:       float = _DEF_HPF_HZ,
        lpf_hz:       float = _DEF_LPF_HZ,
    ) -> None:
        self.wet_w        = wet_pct / 100.0
        self._hpf_hz      = hpf_hz
        self._lpf_hz      = lpf_hz
        self._compressor  = Compressor(
            threshold_db = threshold_db,
            ratio        = ratio,
            attack_ms    = attack_ms,
            release_ms   = release_ms,
            makeup_db    = makeup_db,
        )

    def process(self, samples: np.ndarray, sr: int) -> np.ndarray:
        """
        Apply parallel compression to *samples* (float32).

        Steps:
          1. Preserve dry copy.
          2. Band-limit wet path with HPF + LPF biquads.
          3. Heavily compress wet path.
          4. Blend: out = dry*(1-w) + wet*w
        """
        samples  = samples.astype(np.float32)
        dry      = samples.copy()
        wet      = samples.copy()

        # ── Band-limit wet path ───────────────────────────────────────────────
        sos_hp = highpass(self._hpf_hz, q=0.707, sr=sr).reshape(1, 6)
        sos_lp = lowpass(self._lpf_hz,  q=0.707, sr=sr).reshape(1, 6)

        if wet.ndim == 1:
            wet = sosfilt(sos_hp, wet).astype(np.float32)
            wet = sosfilt(sos_lp, wet).astype(np.float32)
        else:
            for ch in range(wet.shape[1]):
                wet[:, ch] = sosfilt(sos_hp, wet[:, ch])
                wet[:, ch] = sosfilt(sos_lp, wet[:, ch])
            wet = wet.astype(np.float32)

        # ── Compress the band-limited wet path ────────────────────────────────
        wet = self._compressor.process(wet, sr)

        # ── Blend dry + wet ───────────────────────────────────────────────────
        w   = float(self.wet_w)
        out = (dry * (1.0 - w) + wet * w).astype(np.float32)
        return out


def from_genre_data(genre_data: dict) -> ParallelCompressor:
    """
    Build a ParallelCompressor from the 'parallel_compression' key of genre_data.

    Handles the messy string values that appear in the genre JSON
    (e.g. '40-60 (target 50)', '10:1', '60-100 ms …').
    """
    pc = genre_data.get('parallel_compression', {}) if genre_data else {}

    wet_pct     = _safe_float(pc.get('wet_blend_pct'),     _DEF_WET_PCT)
    ratio       = _safe_float(pc.get('ratio'),              _DEF_RATIO)
    thr_db      = _safe_float(pc.get('threshold_dbfs'),     _DEF_THR_DB)
    attack_ms   = _safe_float(pc.get('attack_ms'),          _DEF_ATTACK_MS)
    release_ms  = _safe_float(pc.get('release_formula'),    _DEF_RELEASE_MS)
    makeup_db   = _safe_float(pc.get('net_level_rise_db'),  _DEF_MAKEUP_DB)
    hpf_hz      = _safe_float(pc.get('wet_path_hpf_hz'),   _DEF_HPF_HZ)
    lpf_hz      = _safe_float(pc.get('wet_path_lpf_hz'),   _DEF_LPF_HZ)

    # Clamp wet percentage to [0, 100]
    wet_pct = max(0.0, min(100.0, wet_pct))

    return ParallelCompressor(
        wet_pct      = wet_pct,
        ratio        = ratio,
        threshold_db = thr_db,
        attack_ms    = attack_ms,
        release_ms   = release_ms,
        makeup_db    = makeup_db,
        hpf_hz       = hpf_hz,
        lpf_hz       = lpf_hz,
    )
