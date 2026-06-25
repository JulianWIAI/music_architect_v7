"""
WAV file writer utilities.

Thin wrappers around the standard-library `wave` module that accept lists of
normalised float samples (range [-1.0, 1.0]) and write them as 16-bit PCM WAV.
"""

import struct
import wave
from typing import List


def write_wav(filepath: str, samples: List[float], sample_rate: int = 44100):
    """Write mono float samples to a 16-bit mono WAV file."""
    filepath = str(filepath)
    with wave.open(filepath, 'w') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for s in samples:
            clamped = max(-1.0, min(1.0, s))
            wav.writeframes(struct.pack('<h', int(clamped * 32767)))


def write_wav_stereo(
    filepath: str, left: List[float], right: List[float], sample_rate: int = 44100
):
    """Write left/right float sample lists to a 16-bit stereo WAV file."""
    filepath = str(filepath)
    n = min(len(left), len(right))
    with wave.open(filepath, 'w') as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for i in range(n):
            l = max(-1.0, min(1.0, left[i]))
            r = max(-1.0, min(1.0, right[i]))
            wav.writeframes(struct.pack('<hh', int(l * 32767), int(r * 32767)))
