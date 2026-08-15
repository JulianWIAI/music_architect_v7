"""
waveform_generator.py

Reads raw PCM data from a WAV file and downsamples it into a compact list of
normalised peak amplitudes suitable for canvas bar-chart rendering.

Pure stdlib — no numpy, no scipy, no external dependencies.
Works with 8-bit, 16-bit, and 24-bit mono or stereo WAV files.

Usage
-----
    bars, duration = compute_waveform('output.wav', num_bars=300)
    # bars   : list of floats in [0.0, 1.0], len == num_bars
    # duration : total duration in seconds
"""

import wave
import struct
from typing import List, Tuple


def compute_waveform(
    wav_path: str,
    num_bars: int = 300,
) -> Tuple[List[float], float]:
    """
    Compute a downsampled peak-amplitude envelope from *wav_path*.

    Parameters
    ----------
    wav_path : Path to the WAV file.
    num_bars : Number of amplitude bars in the output.  Should roughly match
               the canvas pixel width divided by bar+gap width.

    Returns
    -------
    (amplitudes, duration_sec)
        amplitudes   : list of *num_bars* floats in [0.0, 1.0].
                       Empty list on any read error.
        duration_sec : total file duration in seconds. 0.0 on error.
    """
    try:
        with wave.open(wav_path, 'rb') as wf:
            n_channels  = wf.getnchannels()
            sample_rate = wf.getframerate()
            samp_width  = wf.getsampwidth()    # bytes per sample per channel
            n_frames    = wf.getnframes()
            raw         = wf.readframes(n_frames)

        if sample_rate == 0 or n_frames == 0:
            return [], 0.0

        duration = n_frames / float(sample_rate)

        # ── Decode PCM bytes to signed integer samples ────────────────────────
        if samp_width == 1:
            # 8-bit WAV is unsigned; shift to signed by centring at 128
            samples = [b - 128 for b in raw]
            max_val = 128.0
        elif samp_width == 2:
            n_samps = len(raw) // 2
            samples = list(struct.unpack(f'<{n_samps}h', raw[:n_samps * 2]))
            max_val = 32768.0
        elif samp_width == 3:
            # 24-bit packed: read 3 bytes at a time, sign-extend to 32 bits
            samples = []
            for i in range(0, len(raw) - 2, 3):
                # Pad to 4 bytes (little-endian) then right-shift to get 24-bit value
                val = struct.unpack('<i', raw[i:i + 3] + b'\x00')[0] >> 8
                samples.append(val)
            max_val = 8_388_608.0
        else:
            # 32-bit or unsupported width — skip
            return [], duration

        # ── Collapse stereo to mono peaks ─────────────────────────────────────
        if n_channels > 1:
            # For each frame, take the max absolute value across all channels
            samples = [
                max(abs(samples[i + c]) for c in range(n_channels))
                for i in range(0, len(samples) - n_channels + 1, n_channels)
            ]
        else:
            samples = [abs(s) for s in samples]

        if not samples:
            return [], duration

        # ── Downsample to num_bars peak values ────────────────────────────────
        total    = len(samples)
        bar_size = max(1, total // num_bars)
        bars: List[float] = []

        for i in range(num_bars):
            start = i * bar_size
            end   = min(start + bar_size, total)
            if start >= total:
                bars.append(0.0)
                continue
            chunk = samples[start:end]
            peak  = max(chunk) / max_val if chunk else 0.0
            bars.append(min(1.0, peak))

        return bars, duration

    except Exception as exc:
        print(f"[WaveformGenerator] Error reading {wav_path}: {exc}")
        return [], 0.0
