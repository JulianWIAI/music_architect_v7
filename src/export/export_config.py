"""
export_config.py

Data classes and default presets for the multi-format audio export dialog.

An ExportPreset captures every parameter that the ffmpeg/wave conversion
pipeline needs: container format, codec, sample rate, bit depth and bitrate.
The DEFAULT_PRESETS list is the source of truth for what appears in the dialog.

To add a new preset: append an ExportPreset to DEFAULT_PRESETS.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List


class AudioFormat(Enum):
    """Supported output container / codec families."""
    WAV  = 'wav'
    MP3  = 'mp3'
    FLAC = 'flac'
    OGG  = 'ogg'


@dataclass
class ExportPreset:
    """
    One named export configuration.

    Fields
    ------
    name         : Human-readable preset name shown in the dialog list.
    description  : One-line hint about intended use.
    fmt          : Target AudioFormat.
    sample_rate  : Output sample rate in Hz (44100, 48000 …).
    bit_depth    : PCM bit depth (16, 24, 32).  Ignored for MP3/OGG.
    channels     : 1 = mono, 2 = stereo.
    bitrate_kbps : Target bitrate for lossy formats (MP3, OGG).  0 for lossless.
    quality_tag  : Short badge label shown in the preset row (e.g. 'Studio').
    quality_color: Background colour of the quality badge.
    fmt_color    : Background colour of the format badge (WAV/MP3 pill).
    """
    name:          str
    description:   str
    fmt:           AudioFormat
    sample_rate:   int  = 44100
    bit_depth:     int  = 16
    channels:      int  = 2
    bitrate_kbps:  int  = 0
    quality_tag:   str  = ''
    quality_color: str  = '#00ff88'
    fmt_color:     str  = '#223355'


# ── Built-in preset library ───────────────────────────────────────────────────
# Ordered from highest quality / largest file to lowest quality / smallest file.

DEFAULT_PRESETS: List[ExportPreset] = [
    # ── WAV — lossless PCM ────────────────────────────────────────────────────
    ExportPreset(
        name         = 'WAV — Mastering',
        description  = 'Lossless, 32-bit float.  Best for further mixing in a DAW.',
        fmt          = AudioFormat.WAV,
        sample_rate  = 44100,
        bit_depth    = 32,
        channels     = 2,
        quality_tag  = 'Studio',
        quality_color= '#00e5ff',
        fmt_color    = '#1a3a5c',
    ),
    ExportPreset(
        name         = 'WAV — CD Quality',
        description  = 'Lossless, 16-bit 44.1 kHz.  Standard for distribution.',
        fmt          = AudioFormat.WAV,
        sample_rate  = 44100,
        bit_depth    = 16,
        channels     = 2,
        quality_tag  = 'No compression',
        quality_color= '#00ff88',
        fmt_color    = '#1a3a5c',
    ),
    ExportPreset(
        name         = 'WAV — 48 kHz Broadcast',
        description  = 'Lossless, 16-bit 48 kHz.  Required for video / broadcast.',
        fmt          = AudioFormat.WAV,
        sample_rate  = 48000,
        bit_depth    = 16,
        channels     = 2,
        quality_tag  = 'Video',
        quality_color= '#4488ff',
        fmt_color    = '#1a3a5c',
    ),
    # ── FLAC — lossless compressed ────────────────────────────────────────────
    ExportPreset(
        name         = 'FLAC — Lossless',
        description  = 'Compressed lossless.  ~50 % of WAV size, zero quality loss.',
        fmt          = AudioFormat.FLAC,
        sample_rate  = 44100,
        bit_depth    = 16,
        channels     = 2,
        quality_tag  = 'Lossless',
        quality_color= '#a855f7',
        fmt_color    = '#2a1a5c',
    ),
    # ── MP3 — lossy compressed ────────────────────────────────────────────────
    ExportPreset(
        name         = 'MP3 — Highest (320 kbps)',
        description  = 'Great sound, while still lightweight.',
        fmt          = AudioFormat.MP3,
        sample_rate  = 44100,
        bitrate_kbps = 320,
        quality_tag  = 'Highest',
        quality_color= '#00ff88',
        fmt_color    = '#3a1a1a',
    ),
    ExportPreset(
        name         = 'MP3 — High (192 kbps)',
        description  = 'Lightweight, good quality.  Optimised for streaming.',
        fmt          = AudioFormat.MP3,
        sample_rate  = 44100,
        bitrate_kbps = 192,
        quality_tag  = 'High',
        quality_color= '#ffd500',
        fmt_color    = '#3a1a1a',
    ),
    ExportPreset(
        name         = 'MP3 — Medium (128 kbps)',
        description  = 'Lightweight, heavily compressed.  Great for sharing.',
        fmt          = AudioFormat.MP3,
        sample_rate  = 44100,
        bitrate_kbps = 128,
        quality_tag  = 'Medium',
        quality_color= '#ff6b00',
        fmt_color    = '#3a1a1a',
    ),
    ExportPreset(
        name         = 'MP3 — Lo-Fi (96 kbps)',
        description  = 'Minimum size.  Suitable for voice memos or preview.',
        fmt          = AudioFormat.MP3,
        sample_rate  = 44100,
        bitrate_kbps = 96,
        quality_tag  = 'Low',
        quality_color= '#ff2040',
        fmt_color    = '#3a1a1a',
    ),
    # ── OGG — open lossy format ───────────────────────────────────────────────
    ExportPreset(
        name         = 'OGG — 192 kbps',
        description  = 'Open format, excellent quality-per-byte ratio.',
        fmt          = AudioFormat.OGG,
        sample_rate  = 44100,
        bitrate_kbps = 192,
        quality_tag  = 'OGG',
        quality_color= '#ff0080',
        fmt_color    = '#2a1a3a',
    ),
]


def estimate_size_bytes(preset: ExportPreset, duration_sec: float) -> int:
    """
    Estimate the output file size in bytes for *duration_sec* of audio.

    WAV/FLAC sizes are calculated exactly from bit math; FLAC applies a 55 %
    compression factor derived from typical music corpus averages.  Lossy
    formats (MP3, OGG) use the target bitrate directly.
    """
    if duration_sec <= 0:
        return 0
    if preset.fmt == AudioFormat.WAV:
        return int(duration_sec * preset.sample_rate * (preset.bit_depth // 8) * preset.channels)
    elif preset.fmt == AudioFormat.FLAC:
        # FLAC typically achieves 50-60 % of the equivalent PCM size
        wav_bytes = duration_sec * preset.sample_rate * (preset.bit_depth // 8) * preset.channels
        return int(wav_bytes * 0.55)
    elif preset.fmt in (AudioFormat.MP3, AudioFormat.OGG):
        return int(duration_sec * preset.bitrate_kbps * 1000 / 8)
    return 0


def format_size(n_bytes: int) -> str:
    """Format a byte count as a human-readable string (KB or MB)."""
    if n_bytes <= 0:
        return '—'
    if n_bytes < 1_048_576:
        return f"{n_bytes / 1024:.1f} KB"
    return f"{n_bytes / 1_048_576:.1f} MB"
