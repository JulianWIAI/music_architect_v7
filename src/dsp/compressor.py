"""
src.dsp.compressor — Feed-forward dynamics processing (Compressor + Limiter).

Block-based RMS envelope follower (256-sample blocks) avoids per-sample Python
iteration for the compressor, keeping performance acceptable at 44.1 kHz.

The Limiter uses a sample-level peak follower with instantaneous attack and
exponential release; a hard clip follows as a true-peak safety net.
"""
from __future__ import annotations

import numpy as np

# Block size for RMS envelope detection (power of 2 for cache efficiency)
_BLOCK = 256


class Compressor:
    """
    Feed-forward RMS compressor with soft-knee gain shaping.

    Parameters
    ----------
    threshold_db : float
        RMS level (dBFS) above which gain reduction begins.
    ratio : float
        Compression ratio (e.g. 4.0 → 4:1).
    attack_ms : float
        Attack time constant in milliseconds.
    release_ms : float
        Release time constant in milliseconds.
    knee_db : float
        Width of the soft-knee zone in dB (centred on threshold).
    makeup_db : float
        Fixed make-up gain applied after compression (dB).
    """

    def __init__(
        self,
        threshold_db: float = -18.0,
        ratio:        float =   4.0,
        attack_ms:    float =  10.0,
        release_ms:   float = 100.0,
        knee_db:      float =   3.0,
        makeup_db:    float =   0.0,
    ) -> None:
        self.threshold_db = threshold_db
        self.ratio        = ratio
        self.attack_ms    = attack_ms
        self.release_ms   = release_ms
        self.knee_db      = knee_db
        self.makeup_db    = makeup_db

    def process(self, samples: np.ndarray, sr: int) -> np.ndarray:
        """
        Apply compression to *samples* (float32, shape (N,) or (N, 2)).

        Returns float32 array of same shape.
        """
        samples = samples.astype(np.float32)
        mono    = samples.mean(axis=1) if samples.ndim == 2 else samples
        N       = len(mono)

        # ── Time constants ────────────────────────────────────────────────────
        # coeff = exp(-1 / (tc_samples)) for single-pole IIR
        a_coeff = float(np.exp(-1.0 / (self.attack_ms  * 0.001 * sr)))
        r_coeff = float(np.exp(-1.0 / (self.release_ms * 0.001 * sr)))

        thr   = self.threshold_db
        ratio = self.ratio
        half_knee = self.knee_db / 2.0

        # ── Block-RMS envelope follower ───────────────────────────────────────
        n_blocks  = (N + _BLOCK - 1) // _BLOCK
        block_env = np.zeros(n_blocks, dtype=np.float64)
        env_db    = thr  # initialise envelope at threshold

        for i in range(n_blocks):
            blk     = mono[i * _BLOCK : (i + 1) * _BLOCK].astype(np.float64)
            rms     = float(np.sqrt(np.mean(blk ** 2)) + 1e-30)
            rms_db  = 20.0 * np.log10(rms)
            # One-pole follower: attack when rising, release when falling
            coeff   = a_coeff if rms_db > env_db else r_coeff
            env_db  = coeff * env_db + (1.0 - coeff) * rms_db
            block_env[i] = env_db

        # ── Soft-knee gain computer ───────────────────────────────────────────
        block_gain_db = np.zeros(n_blocks, dtype=np.float64)
        for i in range(n_blocks):
            x = block_env[i]
            if x < thr - half_knee:
                # Below knee — unity gain
                gc = 0.0
            elif x > thr + half_knee:
                # Above knee — full ratio
                gc = (thr + (x - thr) / ratio) - x
            else:
                # Inside knee — parabolic interpolation
                dist = (x - thr + half_knee)
                gc   = (dist ** 2) / (2.0 * self.knee_db) * (1.0 / ratio - 1.0)
            block_gain_db[i] = gc

        # ── Upsample block gain to sample resolution ──────────────────────────
        # Map each block index to its centre sample, then interpolate
        block_centres = (np.arange(n_blocks) + 0.5) * _BLOCK
        sample_idx    = np.arange(N, dtype=np.float64)
        gain_db_fine  = np.interp(sample_idx, block_centres, block_gain_db)
        gain_db_fine += self.makeup_db
        gain_lin      = 10.0 ** (gain_db_fine / 20.0)

        # ── Apply gain ────────────────────────────────────────────────────────
        gain_lin = gain_lin.astype(np.float32)
        if samples.ndim == 2:
            return (samples * gain_lin[:, np.newaxis]).astype(np.float32)
        return (samples * gain_lin).astype(np.float32)


class Limiter:
    """
    True-peak limiter — instantaneous attack, exponential release, hard clip.

    Parameters
    ----------
    ceiling_db : float
        Output ceiling in dBFS (e.g. -1.0 → -1 dBTP).
    release_ms : float
        Release time constant in milliseconds.
    """

    def __init__(self, ceiling_db: float = -1.0, release_ms: float = 50.0) -> None:
        self.ceiling_db  = ceiling_db
        self.release_ms  = release_ms

    def process(self, samples: np.ndarray, sr: int) -> np.ndarray:
        """
        Apply limiting to *samples* (float32, shape (N,) or (N, 2)).

        Returns float32 array of same shape.
        """
        samples      = samples.astype(np.float32)
        ceiling_lin  = float(10.0 ** (self.ceiling_db / 20.0))
        r_coeff      = float(np.exp(-1.0 / (self.release_ms * 0.001 * sr)))

        # Peak signal level: max absolute value across channels per sample
        if samples.ndim == 2:
            peak = np.abs(samples).max(axis=1).astype(np.float64)
        else:
            peak = np.abs(samples).astype(np.float64)

        N = len(peak)

        # ── Per-sample peak follower (instantaneous attack, exp release) ──────
        # This sequential loop is required — each sample depends on the previous.
        env = np.zeros(N, dtype=np.float64)
        cur = 0.0
        for i in range(N):
            p = peak[i]
            if p > cur:
                cur = p        # instantaneous attack
            else:
                cur *= r_coeff  # exponential release
            env[i] = cur

        # ── Gain reduction + hard clip safety ─────────────────────────────────
        # gain = ceiling / env (only when env > ceiling, else unity)
        gain = np.where(env > ceiling_lin, ceiling_lin / (env + 1e-30), 1.0)
        gain = gain.astype(np.float32)

        if samples.ndim == 2:
            out = samples * gain[:, np.newaxis]
        else:
            out = samples * gain

        # Hard-clip as final true-peak safety net
        return np.clip(out, -ceiling_lin, ceiling_lin).astype(np.float32)
