"""
waveform_generator.py

Reads raw PCM data from a WAV file and downsamples it into a compact list of
normalised peak amplitudes suitable for canvas bar-chart rendering.

Supports 8-bit, 16-bit, 24-bit, and 32-bit IEEE-float mono or stereo WAV files.

Decoding is delegated to src.audio.pcm_decoder which provides:
  • A fast NumPy vectorised path (preferred) — handles all four bit depths
    correctly, including 24-bit sign extension without the erroneous >> 8 shift
    that caused the flat-waveform bug.
  • A pure-stdlib fallback path used when NumPy is unavailable.

Usage
-----
    bars, duration = compute_waveform('output.wav', num_bars=300)
    # bars     : list of floats in [0.0, 1.0], len == num_bars
    # duration : total duration in seconds
"""

import wave
from typing import List, Tuple

import numpy as np

# Fast vectorised decoder — correct 24-bit sign extension, 32-bit float support.
from src.audio.pcm_decoder import decode_pcm, decode_pcm_stdlib


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
               the canvas pixel width divided by (bar_width + gap_width).

    Returns
    -------
    (amplitudes, duration_sec)
        amplitudes   : list of *num_bars* floats in [0.0, 1.0].
                       Empty list on any read error.
        duration_sec : total file duration in seconds.  0.0 on error.
    """
    try:
        with wave.open(wav_path, 'rb') as wf:
            n_channels  = wf.getnchannels()
            sample_rate = wf.getframerate()
            samp_width  = wf.getsampwidth()   # bytes per sample per channel
            n_frames    = wf.getnframes()
            raw         = wf.readframes(n_frames)

        if sample_rate == 0 or n_frames == 0:
            return [], 0.0

        duration = n_frames / float(sample_rate)

        # ── Decode PCM → float32 via the vectorised numpy path ────────────────
        # decode_pcm returns shape (n_frames,) for mono or (n_frames, n_ch) for
        # stereo, values normalised to [-1.0, 1.0].
        samples_f32 = decode_pcm(raw, samp_width, n_channels)

        # ── Collapse multi-channel to mono peak per frame ──────────────────────
        if samples_f32.ndim == 2:
            # Take the max absolute value across channels for each frame
            mono = np.max(np.abs(samples_f32), axis=1)
        else:
            mono = np.abs(samples_f32)

        if mono.size == 0:
            return [], duration

        # ── Downsample to num_bars peak values ────────────────────────────────
        total    = len(mono)
        bar_size = max(1, total // num_bars)
        bars: List[float] = []

        for i in range(num_bars):
            start = i * bar_size
            end   = min(start + bar_size, total)
            if start >= total:
                bars.append(0.0)
                continue
            chunk = mono[start:end]
            # Blend peak (transient detail) and RMS (perceived loudness) then
            # apply a perceptual gamma so mastered/compressed audio shows visible
            # dynamics instead of a uniform wall of bars.
            peak = float(np.max(chunk))
            rms  = float(np.sqrt(np.mean(chunk ** 2)))
            raw  = 0.65 * peak + 0.35 * rms
            # gamma = 0.55 — quiet passages become visible beside loud ones.
            bars.append(min(1.0, raw ** 0.55))

        return bars, duration

    except Exception as exc:
        print(f"[WaveformGenerator] Error reading {wav_path}: {exc}")
        return [], 0.0


def compute_waveform_stdlib(
    wav_path: str,
    num_bars: int = 300,
) -> Tuple[List[float], float]:
    """
    Pure-stdlib fallback for environments where NumPy is unavailable.

    Identical contract to compute_waveform() but uses decode_pcm_stdlib()
    internally.  Slower on large files (Python loop for 24-bit).
    """
    try:
        with wave.open(wav_path, 'rb') as wf:
            n_channels  = wf.getnchannels()
            sample_rate = wf.getframerate()
            samp_width  = wf.getsampwidth()
            n_frames    = wf.getnframes()
            raw         = wf.readframes(n_frames)

        if sample_rate == 0 or n_frames == 0:
            return [], 0.0

        duration = n_frames / float(sample_rate)

        # decode_pcm_stdlib returns (mono_peak_list, max_abs_value)
        mono_ints, max_val = decode_pcm_stdlib(raw, samp_width, n_channels)

        if not mono_ints:
            return [], duration

        total    = len(mono_ints)
        bar_size = max(1, total // num_bars)
        bars: List[float] = []

        for i in range(num_bars):
            start = i * bar_size
            end   = min(start + bar_size, total)
            if start >= total:
                bars.append(0.0)
                continue
            chunk = mono_ints[start:end]
            peak  = max(chunk) / max_val if chunk else 0.0
            bars.append(min(1.0, peak))

        return bars, duration

    except Exception as exc:
        print(f"[WaveformGenerator] Error reading {wav_path}: {exc}")
        return [], 0.0
