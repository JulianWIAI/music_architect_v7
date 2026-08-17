"""
soundfile_backend.py — Cross-platform soundfile availability detection
and format / subtype mapping tables.

soundfile is a Python binding to libsndfile (Erik de Castro Lopo, 2002–).
On Windows and macOS the pip wheel bundles a pre-compiled libsndfile binary,
so no system-level library installation is required — `pip install soundfile`
is sufficient on both platforms.

Format and subtype strings
--------------------------
AudioFormat and BitDepth enum values are mapped to the string identifiers
that libsndfile / soundfile expect.  These are the exact strings accepted by
soundfile.SoundFile(format=..., subtype=...).

RF64 support requires soundfile ≥ 0.11.0 (released January 2022) because
earlier versions did not expose the RF64 format string.  The version is
checked at import time and a clear error is raised if RF64 is requested on
an older installation.
"""

from __future__ import annotations

import importlib.util
from typing import Optional


# ── Format string mapping ─────────────────────────────────────────────────────
# Maps AudioFormat.value → soundfile format string
FORMAT_MAP: dict[str, str] = {
    'WAV':  'WAV',    # Standard RIFF WAV
    'AIFF': 'AIFF',   # Apple AIFF / AIFC
    'RF64': 'RF64',   # Broadcast Wave RF64 (≥ 4 GB)
    'CAF':  'CAF',    # Apple Core Audio Format
    'W64':  'W64',    # Sony / Microsoft Wave64
}

# ── Subtype string mapping ────────────────────────────────────────────────────
# Maps BitDepth.value → soundfile subtype string
SUBTYPE_MAP: dict[str, str] = {
    'PCM_16': 'PCM_16',  # 16-bit signed integer
    'PCM_24': 'PCM_24',  # 24-bit signed integer
    'FLOAT':  'FLOAT',   # 32-bit IEEE-754 float
    'DOUBLE': 'DOUBLE',  # 64-bit IEEE-754 double
}


def soundfile_available() -> bool:
    """
    Return True if the soundfile package is importable on this machine.

    Does NOT attempt to import soundfile (which loads libsndfile), so it
    is safe to call at startup without triggering a slow native library load.
    """
    return importlib.util.find_spec('soundfile') is not None


def get_soundfile():
    """
    Import and return the soundfile module.

    Raises ImportError with a cross-platform install hint if soundfile is
    not installed.  The error message is shown directly to the user when the
    fallback wav_writer shim catches it.
    """
    try:
        import soundfile as sf  # noqa: PLC0415 — intentional lazy import
        return sf
    except ImportError as exc:
        raise ImportError(
            "The 'soundfile' package is required for high-quality audio output.\n\n"
            "Install it with:\n"
            "    pip install soundfile\n\n"
            "soundfile bundles libsndfile as a pre-compiled binary — no separate\n"
            "system library installation is needed on Windows or macOS."
        ) from exc


def check_format_subtype(sf_format: str, sf_subtype: str) -> bool:
    """
    Return True if soundfile / libsndfile accepts this format+subtype pair.

    Use this to validate an OutputSpec before starting a long render, rather
    than discovering an unsupported combination only when writing the file.

    Parameters
    ----------
    sf_format  : soundfile format string, e.g. 'WAV', 'AIFF', 'RF64'
    sf_subtype : soundfile subtype string, e.g. 'PCM_24', 'FLOAT'
    """
    sf = get_soundfile()
    return sf.check_format(sf_format, sf_subtype)


def assert_rf64_supported() -> None:
    """
    Raise RuntimeError if soundfile is too old to support RF64.

    Called by AudioWriter when the requested format is RF64, so the user
    gets a clear version-specific message instead of a cryptic libsndfile error.
    """
    sf = get_soundfile()
    # RF64 was added to soundfile in 0.11.0
    from packaging.version import Version  # noqa: PLC0415
    try:
        if Version(sf.__version__) < Version('0.11.0'):
            raise RuntimeError(
                f"RF64 output requires soundfile ≥ 0.11.0 "
                f"(installed: {sf.__version__}).\n"
                "Upgrade with:  pip install --upgrade soundfile"
            )
    except Exception:
        # packaging not installed — skip the version check and let soundfile
        # raise its own error if RF64 is actually unsupported
        pass
