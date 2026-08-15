"""
audio_converter.py

Converts a source WAV file to the target format / quality specified by an
ExportPreset, using ffmpeg as the universal backend.

ffmpeg is required for all conversions except WAV→WAV with identical
parameters (in which case the file is simply copied).  When ffmpeg is absent
the caller is returned a clear error message rather than a silent failure.

Dependency check
----------------
    from src.export.audio_converter import ffmpeg_available
    if not ffmpeg_available():
        print("Install ffmpeg for MP3/FLAC/OGG export")

Conversion
----------
    ok, message = convert(src_wav='output.wav', dst_path='export/song.mp3', preset=preset)
"""

import os
import shutil
import subprocess
import wave
from typing import Callable, Optional, Tuple

from src.export.export_config import AudioFormat, ExportPreset


# ── ffmpeg detection ──────────────────────────────────────────────────────────

def ffmpeg_available() -> bool:
    """Return True when ffmpeg is found on PATH and responds to --version."""
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ── Public conversion entry-point ─────────────────────────────────────────────

def convert(
    src_wav:     str,
    dst_path:    str,
    preset:      ExportPreset,
    on_progress: Optional[Callable[[float], None]] = None,
) -> Tuple[bool, str]:
    """
    Convert *src_wav* to *dst_path* using the settings from *preset*.

    Parameters
    ----------
    src_wav     : Path to the source WAV file produced by FluidSynth.
    dst_path    : Desired output path (directory created if needed).
    preset      : ExportPreset describing target format and quality.
    on_progress : Optional callback(fraction: float) called during conversion.
                  Not currently used but reserved for future streaming progress.

    Returns
    -------
    (success: bool, message: str)
        success = True and message = human-readable summary on success.
        success = False and message = error description on failure.
    """
    if not os.path.exists(src_wav):
        return False, f"Source WAV not found:\n{src_wav}"

    # Ensure the output directory exists
    dst_dir = os.path.dirname(dst_path)
    if dst_dir:
        os.makedirs(dst_dir, exist_ok=True)

    has_ffmpeg = ffmpeg_available()

    try:
        if preset.fmt == AudioFormat.WAV:
            return _export_wav(src_wav, dst_path, preset, has_ffmpeg)
        else:
            # All non-WAV formats require ffmpeg
            if not has_ffmpeg:
                fmt = preset.fmt.value.upper()
                return False, (
                    f"ffmpeg is required for {fmt} export but was not found on PATH.\n\n"
                    "Install ffmpeg (https://ffmpeg.org/download.html) "
                    "and make sure it is accessible from the terminal."
                )
            return _run_ffmpeg(src_wav, dst_path, preset)
    except Exception as exc:
        return False, f"Unexpected export error: {exc}"


# ── WAV export (copy or ffmpeg resample) ─────────────────────────────────────

def _export_wav(
    src: str,
    dst: str,
    preset: ExportPreset,
    has_ffmpeg: bool,
) -> Tuple[bool, str]:
    """
    Export to WAV.  If the source already matches the target spec the file is
    copied directly; otherwise ffmpeg is used to resample / change bit depth.
    """
    try:
        with wave.open(src, 'rb') as wf:
            src_rate  = wf.getframerate()
            src_depth = wf.getsampwidth() * 8
            src_ch    = wf.getnchannels()
    except Exception:
        src_rate = src_depth = src_ch = 0

    needs_convert = (
        src_rate  != preset.sample_rate or
        src_ch    != preset.channels    or
        src_depth != preset.bit_depth   or
        preset.bit_depth == 32           # 32-bit float requires ffmpeg encoding
    )

    if not needs_convert:
        # Identical specs — plain file copy is fastest and lossless
        shutil.copy2(src, dst)
        size = os.path.getsize(dst)
        return True, f"WAV saved ({_fmt_size(size)}) — no re-encoding needed."

    if not has_ffmpeg:
        # Fall back to copying with the original format
        shutil.copy2(src, dst)
        size = os.path.getsize(dst)
        return True, (
            f"WAV saved ({_fmt_size(size)}).  "
            "Note: ffmpeg unavailable — original bit depth / sample rate kept."
        )

    return _run_ffmpeg(src, dst, preset)


# ── ffmpeg runner ─────────────────────────────────────────────────────────────

def _run_ffmpeg(
    src: str,
    dst: str,
    preset: ExportPreset,
) -> Tuple[bool, str]:
    """
    Build and execute an ffmpeg command for the given preset.

    The command always uses:
      -y         overwrite output without prompting
      -i <src>   input file
      <codec flags> derived from preset.fmt
      <dst>      output path (ffmpeg infers format from extension)
    """
    cmd = ['ffmpeg', '-y', '-i', src]

    if preset.fmt == AudioFormat.WAV:
        # PCM codec selected by bit depth
        codec = {32: 'pcm_f32le', 24: 'pcm_s24le'}.get(preset.bit_depth, 'pcm_s16le')
        cmd += [
            '-c:a', codec,
            '-ar', str(preset.sample_rate),
            '-ac', str(preset.channels),
        ]

    elif preset.fmt == AudioFormat.MP3:
        cmd += [
            '-c:a',  'libmp3lame',
            '-b:a',  f'{preset.bitrate_kbps}k',
            '-ar',   str(preset.sample_rate),
            '-ac',   str(preset.channels),
            # ID3 quality metadata
            '-id3v2_version', '3',
        ]

    elif preset.fmt == AudioFormat.FLAC:
        cmd += [
            '-c:a', 'flac',
            '-compression_level', '8',    # 0 (fastest) … 12 (smallest)
            '-ar', str(preset.sample_rate),
            '-ac', str(preset.channels),
        ]

    elif preset.fmt == AudioFormat.OGG:
        cmd += [
            '-c:a', 'libvorbis',
            '-b:a', f'{preset.bitrate_kbps}k',
            '-ar',  str(preset.sample_rate),
            '-ac',  str(preset.channels),
        ]

    cmd.append(dst)

    try:
        proc = subprocess.run(
            cmd,
            capture_output = True,
            timeout        = 300,   # 5-minute safety limit
        )
        if proc.returncode == 0 and os.path.exists(dst):
            size = os.path.getsize(dst)
            return True, f"Exported successfully  ({_fmt_size(size)})"
        else:
            # Surface the last 400 chars of stderr for diagnostics
            stderr = proc.stderr.decode(errors='replace')[-400:].strip()
            return False, f"ffmpeg returned error code {proc.returncode}:\n\n{stderr}"

    except subprocess.TimeoutExpired:
        return False, "Export timed out (exceeded 5 minutes)."
    except FileNotFoundError:
        return False, "ffmpeg executable not found on PATH."


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_size(n_bytes: int) -> str:
    if n_bytes < 1_048_576:
        return f"{n_bytes / 1024:.1f} KB"
    return f"{n_bytes / 1_048_576:.1f} MB"


def read_wav_duration(wav_path: str) -> float:
    """Return duration in seconds of a WAV file, or 0.0 on error."""
    try:
        with wave.open(wav_path, 'rb') as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 0.0
