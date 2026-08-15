"""
src.dsp.loudness — K-weighted LUFS measurement and normalisation (ITU-R BS.1770-4).

The K-weighting filter is a two-stage biquad cascade:
  Stage 1: Pre-filter — high-shelf at ~1682 Hz boosting high-frequency content
           (accounts for the acoustic effect of the head)
  Stage 2: RLB (Revised Low-frequency B-curve) — 2nd-order high-pass at ~38 Hz
           (removes low-frequency content which does not contribute to loudness)

Gating follows BS.1770-4 §2.7:
  - Absolute gate: blocks below -70 LKFS are excluded
  - Relative gate: blocks 10 dB below the ungated mean are excluded
  - Final LUFS = -0.691 + 10*log10(mean of gated blocks)

All intermediate calculations use float64 for accuracy.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.signal import sosfilt

# ── K-weighting constants (ITU-R BS.1770-4 Annex 1) ──────────────────────────
_PRE_FILTER_HZ = 1681.974450955533    # pre-filter shelf frequency
_RLB_FILTER_HZ =   38.13547087602444  # RLB high-pass frequency
_RLB_Q         =    0.5003270373238773 # RLB Q factor
_PRE_VH        = 10 ** (3.999843853973347 / 20.0)   # Vh = 10^(3.9998/20)
_PRE_VB_EXP    = 0.4996667741545416   # exponent for Vb = Vh^0.4997

# BS.1770-4 gate thresholds
_ABS_GATE_POW  = 10.0 ** ((-70.0 + 0.691) / 10.0)  # -70 LKFS absolute gate
_REL_GATE_OFF  = 10.0 ** (-10.0 / 10.0)             # -10 dB relative gate offset
_LUFS_OFFSET   = -0.691                              # BS.1770-4 calibration constant

# Gating block/hop sizes in seconds (BS.1770-4 §2.7)
_GATE_BLOCK_S  = 0.400   # 400 ms blocks
_GATE_HOP_S    = 0.100   # 100 ms hop (75% overlap)


# ── K-weighting filter ────────────────────────────────────────────────────────

def _kweight_sos(sr: int) -> np.ndarray:
    """
    Build the ITU-R BS.1770-4 K-weighting SOS filter, shape (2, 6).

    Row 0 — Pre-filter (high-shelf ~+4 dB at 1682 Hz):
        Uses the bilinear-transform shelf design with analytically derived
        coefficients (Annex 1 of BS.1770-4 / implementations by Itu-R).
    Row 1 — RLB high-pass at 38.14 Hz, Q=0.5003 (2nd-order Butterworth-like).
    """
    # ── Stage 0: Pre-filter (high-shelf) ──────────────────────────────────────
    Kf  = math.tan(math.pi * _PRE_FILTER_HZ / sr)
    Vh  = _PRE_VH
    Vb  = Vh ** _PRE_VB_EXP
    Kf2 = Kf * Kf
    sq2 = math.sqrt(2.0)

    denom = 1.0 + sq2 * Kf + Kf2
    b0_s0 = (Vh  + Vb * sq2 * Kf + Kf2) / denom
    b1_s0 = (2.0 * (Kf2 - Vh))           / denom
    b2_s0 = (Vh  - Vb * sq2 * Kf + Kf2) / denom
    a1_s0 = (2.0 * (Kf2 - 1.0))          / denom
    a2_s0 = (1.0 - sq2 * Kf + Kf2)       / denom
    row0  = np.array([b0_s0, b1_s0, b2_s0, 1.0, a1_s0, a2_s0], dtype=np.float64)

    # ── Stage 1: RLB high-pass ─────────────────────────────────────────────────
    w0    = 2.0 * math.pi * _RLB_FILTER_HZ / sr
    cos_w = math.cos(w0)
    sin_w = math.sin(w0)
    alpha = sin_w / (2.0 * _RLB_Q)

    b0_s1 =  (1.0 + cos_w) / 2.0
    b1_s1 = -(1.0 + cos_w)
    b2_s1 =  (1.0 + cos_w) / 2.0
    a0_s1 =   1.0 + alpha
    a1_s1 =  -2.0 * cos_w
    a2_s1 =   1.0 - alpha
    row1  = np.array([b0_s1 / a0_s1, b1_s1 / a0_s1, b2_s1 / a0_s1,
                      1.0, a1_s1 / a0_s1, a2_s1 / a0_s1], dtype=np.float64)

    return np.stack([row0, row1], axis=0)  # (2, 6)


# ── LUFS measurement ───────────────────────────────────────────────────────────

def measure_lufs(samples: np.ndarray, sr: int) -> float:
    """
    Measure integrated loudness in LUFS (ITU-R BS.1770-4).

    Parameters
    ----------
    samples : np.ndarray
        Float32 audio, shape (N,) mono or (N, 2) stereo.
    sr : int
        Sample rate in Hz.

    Returns
    -------
    float
        Integrated loudness in LUFS, or float('-inf') if the signal is silent.
    """
    # Work in float64 for numerical precision
    sig = samples.astype(np.float64)

    # ── Mix to mono for single-channel measurement ─────────────────────────────
    if sig.ndim == 2:
        mono = sig.mean(axis=1)
    else:
        mono = sig

    if len(mono) == 0:
        return float('-inf')

    # ── Apply K-weighting filter ───────────────────────────────────────────────
    sos   = _kweight_sos(sr)
    kw    = sosfilt(sos, mono)

    # ── Gating ────────────────────────────────────────────────────────────────
    block_len = int(_GATE_BLOCK_S * sr)
    hop_len   = int(_GATE_HOP_S   * sr)

    if block_len < 1:
        return float('-inf')

    # Compute mean-square power of each overlapping block
    starts      = range(0, len(kw) - block_len + 1, hop_len)
    mean_sq     = np.array([
        float(np.mean(kw[s: s + block_len] ** 2))
        for s in starts
    ], dtype=np.float64)

    if len(mean_sq) == 0:
        return float('-inf')

    # ── Absolute gate (BS.1770-4 §2.7 step 1) ─────────────────────────────────
    above_abs   = mean_sq[mean_sq >= _ABS_GATE_POW]
    if len(above_abs) == 0:
        return float('-inf')

    # ── Relative gate (BS.1770-4 §2.7 step 2) ─────────────────────────────────
    ungated_mean = float(above_abs.mean())
    rel_thresh   = ungated_mean * _REL_GATE_OFF
    gated        = above_abs[above_abs >= rel_thresh]

    if len(gated) == 0:
        return float('-inf')

    # ── Integrated loudness ────────────────────────────────────────────────────
    lufs = _LUFS_OFFSET + 10.0 * math.log10(float(gated.mean()))
    return lufs


# ── Normalisation helpers ──────────────────────────────────────────────────────

def gain_for_target(current_lufs: float, target_lufs: float) -> float:
    """
    Compute the linear gain needed to move *current_lufs* to *target_lufs*.

    Returns 1.0 if *current_lufs* is -inf (silent signal).
    Clamps the dB adjustment to [-40, +20] dB to prevent extreme gains.
    """
    if math.isinf(current_lufs):
        return 1.0
    db_diff = target_lufs - current_lufs
    db_diff = max(-40.0, min(20.0, db_diff))
    return 10.0 ** (db_diff / 20.0)


def normalize_to_lufs(
    samples: np.ndarray,
    sr: int,
    target_lufs: float,
) -> np.ndarray:
    """
    Measure loudness of *samples*, apply gain to reach *target_lufs*.

    Returns float32 array of same shape as *samples*.
    """
    current = measure_lufs(samples, sr)
    gain    = gain_for_target(current, target_lufs)
    return (samples.astype(np.float32) * np.float32(gain))
