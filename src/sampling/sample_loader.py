"""
src/sampling/sample_loader.py
─────────────────────────────
Cross-platform audio file loader.

Tries soundfile first (handles WAV / FLAC / OGG / AIFF / MP3 via libsndfile).
Falls back to the stdlib wave module for plain WAV files when soundfile is not
installed.  Both paths return a mono float32 numpy array and the source sample
rate.

Public API
----------
load_audio_file(path: str) -> tuple[np.ndarray, int]
    Synchronous load — call from a render thread, never from the GUI thread.

SUPPORTED_EXTENSIONS : frozenset[str]
    File extensions the loader accepts (lower-case, with leading dot).
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Tuple

import numpy as np

# Extensions that soundfile can read; wave fallback covers .wav only.
SUPPORTED_EXTENSIONS: frozenset = frozenset(
    {'.wav', '.aiff', '.aif', '.flac', '.ogg', '.mp3'}
)


def load_audio_file(path: str) -> Tuple[np.ndarray, int]:
    """
    Load an audio file and return a mono float32 buffer.

    Parameters
    ----------
    path : str
        Absolute path to the audio file.

    Returns
    -------
    (samples, sample_rate) where samples is a 1-D float32 ndarray normalised
    to ±1.0 and sample_rate is the file's native sample rate in Hz.

    Raises
    ------
    ValueError
        When the file cannot be read or the format is unsupported.
    """
    p = Path(path)
    if not p.exists():
        raise ValueError(f"Audio file not found: {path}")

    # ── Preferred path: soundfile (handles WAV, FLAC, OGG, AIFF, MP3 via plugins)
    try:
        import soundfile as sf  # type: ignore
        data, sr = sf.read(str(path), dtype='float32', always_2d=True)
        mono = data.mean(axis=1).astype(np.float32)
        return mono, int(sr)
    except ImportError:
        pass
    except Exception as exc:
        raise ValueError(f"soundfile could not read '{path}': {exc}") from exc

    # ── Fallback: stdlib wave module (WAV only, no compression)
    ext = p.suffix.lower()
    if ext != '.wav':
        raise ValueError(
            f"soundfile is not installed; only .wav files can be loaded as "
            f"fallback.  Install soundfile to support '{ext}'."
        )

    return _load_wav_stdlib(str(path))


def _load_wav_stdlib(path: str) -> Tuple[np.ndarray, int]:
    """Load a PCM WAV file using the stdlib wave module."""
    import wave

    with wave.open(path, 'rb') as wf:
        nchannels  = wf.getnchannels()
        sampwidth  = wf.getsampwidth()
        framerate  = wf.getframerate()
        nframes    = wf.getnframes()
        raw        = wf.readframes(nframes)

    total_samples = nframes * nchannels

    if sampwidth == 1:
        # 8-bit WAV is unsigned (0–255)
        arr = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        arr = (arr - 128.0) / 128.0
    elif sampwidth == 2:
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 3:
        arr = _decode_24bit(raw, total_samples)
    elif sampwidth == 4:
        arr = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2_147_483_648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sampwidth} bytes")

    if nchannels > 1:
        arr = arr.reshape(-1, nchannels).mean(axis=1)

    return arr.astype(np.float32), int(framerate)


def _decode_24bit(raw: bytes, total_samples: int) -> np.ndarray:
    """Decode a raw byte string of 24-bit signed PCM samples."""
    out = np.empty(total_samples, dtype=np.float32)
    for i in range(total_samples):
        b = raw[i * 3: i * 3 + 3]
        # Little-endian 24-bit signed integer
        val = struct.unpack('<i', b + (b'\xff' if b[2] & 0x80 else b'\x00'))[0]
        out[i] = val / 8_388_608.0
    return out
