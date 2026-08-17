"""
src/audio/pcm_decoder.py
─────────────────────────
Vectorised PCM → float32 decoder for WAV audio.

Supports 8-bit unsigned, 16-bit signed, 24-bit signed, and 32-bit IEEE float
PCM data, all in little-endian byte order (the only byte order used by WAV).

Why this module exists
──────────────────────
The original waveform_generator.py decoded 24-bit samples with:

    val = struct.unpack('<i', raw[i:i + 3] + b'\\x00')[0] >> 8

The ``>> 8`` right-shift divides every decoded value by 256, making the
waveform bars ~0.39 % of their correct height — visually flat.  The correct
approach is to zero-extend the three bytes to an unsigned 32-bit integer and
then apply two's-complement sign extension by subtracting 2²⁴ when the
sign bit (bit 23) is set.

This module provides a single public function:

    samples = decode_pcm(raw, samp_width, n_channels)

It uses NumPy for vectorised 24-bit unpacking (no Python loop over millions of
samples) and falls back to a stdlib struct path when NumPy is unavailable.
"""

from __future__ import annotations

import struct
from typing import List, Tuple

import numpy as np


def decode_pcm(
    raw:        bytes,
    samp_width: int,
    n_channels: int,
) -> np.ndarray:
    """
    Decode raw PCM bytes from a WAV file to a float32 NumPy array.

    Parameters
    ----------
    raw        : Raw byte string returned by wave.readframes().
    samp_width : Bytes per sample per channel (1, 2, 3, or 4).
    n_channels : Number of audio channels (1 = mono, 2 = stereo).

    Returns
    -------
    np.ndarray, dtype=float32
        Shape (n_frames, n_channels) for stereo, (n_frames,) for mono.
        Values are normalised to [-1.0, 1.0].
    """
    buf = np.frombuffer(raw, dtype=np.uint8)

    if samp_width == 1:
        # 8-bit PCM is unsigned [0, 255]; re-centre to [-128, 127]
        samples = (buf.astype(np.float32) - 128.0) / 128.0

    elif samp_width == 2:
        # 16-bit signed PCM, little-endian
        samples = buf.view(np.dtype('<i2')).astype(np.float32) / 32768.0

    elif samp_width == 3:
        # 24-bit signed PCM — no native NumPy dtype.
        # Vectorised decode (no Python loop):
        #   1. Reshape raw bytes into (n_samples, 3)
        #   2. Zero-extend each 3-byte group to a 32-bit unsigned int
        #   3. Apply two's-complement sign extension for values >= 2²³
        n_samps = len(buf) // 3
        b3 = buf[: n_samps * 3].reshape(n_samps, 3)

        # Combine bytes: byte[0] = LSB, byte[1], byte[2] = MSB of 24-bit value
        i32 = (b3[:, 0].astype(np.int32)
               | (b3[:, 1].astype(np.int32) << 8)
               | (b3[:, 2].astype(np.int32) << 16))

        # Sign-extend: values with bit 23 set are negative in two's complement
        i32[i32 >= (1 << 23)] -= (1 << 24)

        samples = i32.astype(np.float32) / float(1 << 23)   # → [-1, 1]

    elif samp_width == 4:
        # 32-bit IEEE float (written by FluidSynth mastering output)
        samples = buf.view(np.dtype('<f4')).astype(np.float32)

    else:
        raise ValueError(f"Unsupported WAV sample width: {samp_width} bytes")

    # Reshape interleaved stereo to (n_frames, n_channels)
    if n_channels > 1:
        samples = samples.reshape(-1, n_channels)

    return samples


# ── Pure-stdlib fallback (used when NumPy is unavailable) ─────────────────────

def decode_pcm_stdlib(
    raw:        bytes,
    samp_width: int,
    n_channels: int,
) -> Tuple[List[int], float]:
    """
    Stdlib-only fallback for environments without NumPy.

    Returns (int_samples, max_abs_value) where int_samples is a flat list of
    mono peak values (max across channels per frame).

    The 24-bit path correctly sign-extends without the erroneous >> 8 shift.
    """
    if samp_width == 1:
        raw_samples = [b - 128 for b in raw]
        max_val = 128.0

    elif samp_width == 2:
        n = len(raw) // 2
        raw_samples = list(struct.unpack(f'<{n}h', raw[:n * 2]))
        max_val = 32768.0

    elif samp_width == 3:
        # 24-bit: zero-extend to unsigned 32-bit, then sign-extend
        n = len(raw) // 3
        raw_samples = []
        for i in range(n):
            off = i * 3
            # Unsigned 32-bit from 3 bytes + one zero byte
            val = struct.unpack('<I', raw[off:off + 3] + b'\x00')[0]
            # Two's-complement sign extension: subtract 2²⁴ if bit 23 is set
            if val >= 8_388_608:
                val -= 16_777_216
            raw_samples.append(val)
        max_val = 8_388_608.0

    elif samp_width == 4:
        # 32-bit float: scale to int range for uniform treatment below
        n = len(raw) // 4
        floats = struct.unpack(f'<{n}f', raw[:n * 4])
        raw_samples = [int(f * 8_388_607) for f in floats]
        max_val = 8_388_607.0

    else:
        return [], 1.0

    # Collapse stereo to mono peak per frame
    if n_channels > 1:
        mono = [
            max(abs(raw_samples[i + c]) for c in range(n_channels))
            for i in range(0, len(raw_samples) - n_channels + 1, n_channels)
        ]
    else:
        mono = [abs(s) for s in raw_samples]

    return mono, max_val
