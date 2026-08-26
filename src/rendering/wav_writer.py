"""
wav_writer.py — Compatibility shim over the new src.audio_io.AudioWriter.

All code that previously imported write_wav() or write_wav_stereo() from this
module continues to work without modification.  Internally both functions now
delegate to AudioWriter (backed by libsndfile) and write 24-bit WAV files
instead of the old 16-bit output.

Fallback behaviour
------------------
If soundfile is not installed the functions fall back to the original stdlib
wave / struct implementation (16-bit PCM) and print a one-time warning.  This
ensures the application keeps working even without soundfile, just at lower
bit depth.

Migration
---------
New code should import AudioWriter directly:

    from src.audio_io import AudioWriter, OutputSpec, AudioFormat, BitDepth

    writer = AudioWriter()
    writer.write(path, samples, sample_rate=44100)

The shim functions write_wav() and write_wav_stereo() are preserved only for
backwards compatibility with existing callers (wav_renderer.py etc.).
"""

from __future__ import annotations

import struct
import wave
from typing import List

import numpy as np


# ── Detect soundfile availability and set up the appropriate writer ───────────
# AudioWriter itself imports cleanly (no soundfile at import time), so we must
# explicitly probe for soundfile before deciding which path to use.

from src.audio_io.soundfile_backend import soundfile_available as _sf_available
from src.audio_io.audio_writer import AudioWriter
from src.audio_io.audio_format import OutputSpec, BitDepth, AudioFormat

if _sf_available():
    # soundfile is installed — use AudioWriter for 24-bit output with dithering
    _writer = AudioWriter(
        OutputSpec(
            format=AudioFormat.WAV,
            bit_depth=BitDepth.INT_24,
            apply_dither=True,
        )
    )
    _USE_SOUNDFILE = True
else:
    # soundfile not installed — fall back to legacy 16-bit stdlib path
    _USE_SOUNDFILE = False
    _writer = None
    import warnings as _warnings
    _warnings.warn(
        "soundfile is not installed — wav_writer is using legacy 16-bit PCM output.\n"
        "Install soundfile for 24-bit output:  pip install soundfile",
        stacklevel=1,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def write_wav(filepath: str, samples, sample_rate: int = 44100) -> None:
    """
    Write a mono or stereo float buffer to a WAV file.

    Accepts a mono list / 1-D array or a stereo np.ndarray of shape (N, 2).
    Stereo input is written as a 2-channel WAV automatically.

    With soundfile installed  : 24-bit PCM WAV with TPDF dithering.
    Without soundfile         : 16-bit PCM WAV (legacy stdlib path).

    Parameters
    ----------
    filepath    : destination file path (created or overwritten)
    samples     : mono float samples in [−1.0, +1.0], or (N, 2) stereo array
    sample_rate : output sample rate in Hz (default 44 100)
    """
    arr = np.asarray(samples, dtype=np.float32)
    if arr.ndim == 2:
        # Stereo (N, 2): AudioWriter accepts this shape directly
        if _USE_SOUNDFILE:
            _writer.write(filepath, arr, sample_rate=sample_rate)
        else:
            _legacy_write_wav_stereo(filepath, arr[:, 0].tolist(), arr[:, 1].tolist(), sample_rate)
    else:
        if _USE_SOUNDFILE:
            _writer.write(filepath, arr, sample_rate=sample_rate)
        else:
            _legacy_write_wav(filepath, arr.tolist(), sample_rate)


def write_wav_stereo(
    filepath:    str,
    left:        List[float],
    right:       List[float],
    sample_rate: int = 44100,
) -> None:
    """
    Write separate left and right float sample lists to a stereo WAV file.

    With soundfile installed  : 24-bit stereo PCM WAV with TPDF dithering.
    Without soundfile         : 16-bit stereo PCM WAV (legacy stdlib path).

    Parameters
    ----------
    filepath    : destination file path (created or overwritten)
    left        : left-channel float samples in [−1.0, +1.0]
    right       : right-channel float samples in [−1.0, +1.0]
    sample_rate : output sample rate in Hz (default 44 100)
    """
    if _USE_SOUNDFILE:
        # Interleave L/R into a (frames, 2) array and hand it to AudioWriter
        n = min(len(left), len(right))
        stereo = np.stack(
            [np.array(left[:n], dtype=np.float32),
             np.array(right[:n], dtype=np.float32)],
            axis=1,                  # shape: (n, 2) — frames × channels
        )
        _writer.write(filepath, stereo, sample_rate=sample_rate)
    else:
        _legacy_write_wav_stereo(filepath, left, right, sample_rate)


# ── Legacy fallback (16-bit, stdlib only) ─────────────────────────────────────
# These are the original implementations from before soundfile was introduced.
# They are called only when soundfile is not importable.

def _legacy_write_wav(
    filepath: str, samples: List[float], sample_rate: int
) -> None:
    """Write mono float samples to a 16-bit mono WAV using the stdlib wave module."""
    filepath = str(filepath)
    with wave.open(filepath, 'w') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)          # 2 bytes = 16 bits
        wav.setframerate(sample_rate)
        for s in samples:
            clamped = max(-1.0, min(1.0, s))
            wav.writeframes(struct.pack('<h', int(clamped * 32767)))


def _legacy_write_wav_stereo(
    filepath:    str,
    left:        List[float],
    right:       List[float],
    sample_rate: int,
) -> None:
    """Write L/R float sample lists to a 16-bit stereo WAV using the stdlib wave module."""
    filepath = str(filepath)
    n = min(len(left), len(right))
    with wave.open(filepath, 'w') as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)          # 2 bytes = 16 bits
        wav.setframerate(sample_rate)
        for i in range(n):
            l_s = max(-1.0, min(1.0, left[i]))
            r_s = max(-1.0, min(1.0, right[i]))
            wav.writeframes(struct.pack('<hh', int(l_s * 32767), int(r_s * 32767)))
