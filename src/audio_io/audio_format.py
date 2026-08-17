"""
audio_format.py — Output format and bit-depth enumerations, plus OutputSpec.

OutputSpec is the single configuration object passed to AudioWriter. It
describes *how* a file should be written: which container format, which
integer or float bit depth, the sample rate, and whether TPDF dithering
should be applied when reducing to an integer depth.

Supported container formats
---------------------------
WAV   Standard RIFF WAV — universal compatibility.
AIFF  Apple Interchange File Format — common on macOS / Logic Pro.
RF64  BWF RF64 — identical to WAV but lifts the 4 GB file-size limit.
      Required for sessions longer than ~6.8 hours at 44.1 kHz / 24-bit.
CAF   Apple Core Audio Format — macOS only; no size limit; supports very
      large channel counts.
W64   Sony Wave64 — lifts the 4 GB limit on Windows without the RF64
      broadcasting metadata overhead.

Supported bit depths
--------------------
INT_16   16-bit signed integer PCM  — CD standard, smallest file.
INT_24   24-bit signed integer PCM  — mastering standard; best quality
         without floating-point overhead on older hardware.
FLOAT_32 32-bit IEEE-754 float      — production interchange format;
         preserves all headroom, no clipping risk.
FLOAT_64 64-bit IEEE-754 double     — archival / DSP analysis; rarely
         needed for listening.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AudioFormat(Enum):
    """Container/wrapper format for the output audio file."""

    WAV  = 'WAV'   # RIFF WAV — broadest compatibility
    AIFF = 'AIFF'  # Apple AIFF — macOS / Logic Pro native
    RF64 = 'RF64'  # BWF RF64 — WAV without the 4 GB limit
    CAF  = 'CAF'   # Apple Core Audio Format — macOS, no size limit
    W64  = 'W64'   # Sony Wave64 — Windows alternative to RF64


class BitDepth(Enum):
    """
    Sample encoding precision.

    The string values are the soundfile/libsndfile subtype identifiers
    used verbatim when opening a SoundFile for writing.
    """

    INT_16   = 'PCM_16'  # 16-bit integer — CD quality
    INT_24   = 'PCM_24'  # 24-bit integer — mastering standard
    FLOAT_32 = 'FLOAT'   # 32-bit float   — production interchange
    FLOAT_64 = 'DOUBLE'  # 64-bit float   — archival / DSP


@dataclass
class OutputSpec:
    """
    Complete specification for a single audio write operation.

    Parameters
    ----------
    format : AudioFormat
        Container format of the output file.  Default: WAV.
    bit_depth : BitDepth
        Sample encoding.  Default: 24-bit integer (mastering standard).
    sample_rate : int
        Output sample rate in Hz.  Default: 44 100 (CD / streaming).
    apply_dither : bool
        When True (default) and bit_depth is an integer type, TPDF
        dithering is applied *before* quantisation.  Has no effect
        for FLOAT_32 or FLOAT_64 because no bit reduction occurs.
    """

    format:       AudioFormat = AudioFormat.WAV
    bit_depth:    BitDepth    = BitDepth.INT_24
    sample_rate:  int         = 44_100
    apply_dither: bool        = True