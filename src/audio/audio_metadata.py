"""
audio_metadata.py

Reads technical properties from WAV files (duration, sample rate, bitrate)
using the stdlib `wave` module — zero external dependencies.

Also assembles human-readable metadata (title, artist, album, genre, year)
from the composition config dict that Music Architect produces after generation.

The combined AudioMetadata object is consumed by TrackMetadataPanel for display.
"""

import wave
import os
import time as _time
from dataclasses import dataclass
from typing import Optional


@dataclass
class AudioMetadata:
    """All displayable metadata fields for one generated audio track."""

    title:         str   = "Unknown Title"
    artist:        str   = "Unknown Artist"
    album:         str   = "Unknown Album"
    genre:         str   = "Unknown Genre"
    year:          str   = "—"
    duration_sec:  float = 0.0
    bitrate_kbps:  int   = 0
    sample_rate_hz:int   = 0
    channels:      int   = 1
    bit_depth:     int   = 16

    # ── Formatted display helpers ─────────────────────────────────────────────

    @property
    def duration_str(self) -> str:
        """Return duration formatted as MM:SS."""
        total = int(self.duration_sec)
        return f"{total // 60:02d}:{total % 60:02d}"

    @property
    def bitrate_str(self) -> str:
        return f"{self.bitrate_kbps} kbps" if self.bitrate_kbps else "—"

    @property
    def sample_rate_str(self) -> str:
        return f"{self.sample_rate_hz:,} Hz" if self.sample_rate_hz else "—"


def read_wav_properties(wav_path: str) -> Optional[AudioMetadata]:
    """
    Read technical audio properties from *wav_path*'s RIFF header.

    Returns an AudioMetadata with only the technical fields filled in
    (title / artist / album / genre remain at defaults).
    Returns None when the file is missing or unreadable.
    """
    if not wav_path or not os.path.exists(wav_path):
        return None
    try:
        with wave.open(wav_path, 'rb') as wf:
            channels    = wf.getnchannels()
            sample_rate = wf.getframerate()
            # getsampwidth() returns bytes per sample; multiply by 8 for bit depth
            bit_depth   = wf.getsampwidth() * 8
            n_frames    = wf.getnframes()
            duration    = n_frames / float(sample_rate) if sample_rate else 0.0
            # Uncompressed PCM bitrate: sample_rate × bit_depth × channels
            bitrate_kbps = (sample_rate * bit_depth * channels) // 1000

        return AudioMetadata(
            duration_sec   = duration,
            bitrate_kbps   = bitrate_kbps,
            sample_rate_hz = sample_rate,
            channels       = channels,
            bit_depth      = bit_depth,
        )
    except Exception as exc:
        print(f"[AudioMetadata] Cannot read {wav_path}: {exc}")
        return None


def metadata_from_composition(
    comp:              dict,
    wav_path:          Optional[str] = None,
    generation_number: int           = 1,
) -> AudioMetadata:
    """
    Build a complete AudioMetadata from a Music Architect composition dict.

    Technical fields (duration, bitrate, sample_rate) are pulled from the WAV
    file header when *wav_path* is provided.  Descriptive fields (title, artist,
    album, genre, year) are derived from *comp['config']*.

    Parameters
    ----------
    comp              : Composition dict produced by CompositionEngine.compose().
    wav_path          : Optional path to the rendered WAV file for technical data.
    generation_number : Counter used to make the title unique per session.
    """
    cfg   = comp.get('config', {})
    genre = cfg.get('genre', 'unknown')
    bpm   = cfg.get('bpm', 0)
    key   = cfg.get('key', '')
    dur   = comp.get('duration_seconds', 0.0)

    title = (
        f"{genre.capitalize()} Song #{generation_number}"
        f"  —  {bpm} BPM  {key}"
    )

    meta = AudioMetadata(
        title  = title,
        artist = "Seed Composer AI",
        album  = f"{genre.capitalize()} Sessions",
        genre  = genre.capitalize(),
        year   = str(_time.localtime().tm_year),
        # Technical defaults — overridden below if WAV is available
        duration_sec = dur,
    )

    # Overwrite with precise values from the actual WAV header.
    wav_meta = read_wav_properties(wav_path) if wav_path else None
    if wav_meta:
        meta.duration_sec   = wav_meta.duration_sec
        meta.bitrate_kbps   = wav_meta.bitrate_kbps
        meta.sample_rate_hz = wav_meta.sample_rate_hz
        meta.channels       = wav_meta.channels
        meta.bit_depth      = wav_meta.bit_depth

    return meta
