"""
audio_writer.py — High-quality multi-format audio writer backed by libsndfile.

AudioWriter is the single public class for writing audio to disk.  It replaces
the old wav_writer.py (which only wrote 16-bit mono/stereo WAV using the stdlib
wave module) with a full-featured writer that supports:

  • Five container formats: WAV, AIFF, RF64 (>4 GB), CAF, W64
  • Four bit depths: 16-bit int, 24-bit int, 32-bit float, 64-bit float
  • TPDF dithering when reducing to integer bit depths
  • Optional metadata: string tags, loop points, MIDI instrument info (WAV only)

All heavy I/O is delegated to soundfile / libsndfile — a native C library
available as a pre-compiled binary on both Windows and macOS via pip.

Typical usage
-------------
    from src.audio_io.audio_writer import AudioWriter
    from src.audio_io.audio_format import OutputSpec, AudioFormat, BitDepth

    # Default: 24-bit WAV at 44.1 kHz with dithering
    writer = AudioWriter()
    writer.write('output.wav', samples, sample_rate=44100)

    # 32-bit float AIFF for DAW interchange
    spec = OutputSpec(format=AudioFormat.AIFF, bit_depth=BitDepth.FLOAT_32)
    writer.write('output.aiff', samples, spec=spec)

Fallback behaviour
------------------
If soundfile is not installed, write() raises ImportError with a clear
install instruction.  Callers that need a guaranteed fallback should catch
ImportError and call wav_writer.write_wav() (the legacy 16-bit path) instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

import numpy as np

from src.audio_io.audio_format import AudioFormat, BitDepth, OutputSpec
from src.audio_io.audio_metadata import AudioFileMetadata
from src.audio_io.dithering import TPDFDither
from src.audio_io.soundfile_backend import (
    FORMAT_MAP,
    SUBTYPE_MAP,
    assert_rf64_supported,
    get_soundfile,
)
from src.audio_io.wav_chunk_writer import WAVChunkWriter


class AudioWriter:
    """
    Write normalised float audio buffers to disk in multiple formats.

    Parameters
    ----------
    default_spec : OutputSpec, optional
        Default output specification used when write() is called without
        an explicit spec argument.  Defaults to 24-bit WAV at 44.1 kHz
        with TPDF dithering enabled.

    Thread safety
    -------------
    AudioWriter is stateless after construction (the default_spec is read-only
    during write calls).  Multiple threads may call write() concurrently as
    long as each call targets a different output file path.
    """

    def __init__(self, default_spec: Optional[OutputSpec] = None) -> None:
        # Store the default output specification
        self._default_spec = default_spec or OutputSpec()

        # Reusable ditherer — stateless, safe to share across write() calls
        self._dither = TPDFDither()

        # Reusable WAV chunk appender — stateless
        self._chunk_writer = WAVChunkWriter()

    # ── Primary write method ──────────────────────────────────────────────────

    def write(
        self,
        filepath: Union[str, Path],
        samples:  Union[List[float], np.ndarray],
        sample_rate: Optional[int]         = None,
        metadata:    Optional[AudioFileMetadata] = None,
        spec:        Optional[OutputSpec]  = None,
    ) -> None:
        """
        Write *samples* to *filepath* according to *spec*.

        Parameters
        ----------
        filepath : str or Path
            Destination file path.  The directory must already exist.
            The file extension does not affect the output format —
            the format is controlled exclusively by spec.format.
        samples : list of float, or numpy array (1-D or 2-D)
            Audio samples normalised to [−1.0, +1.0].
            1-D array  → mono output.
            2-D array  → shape must be (frames, channels); stereo = 2 channels.
            A Python list of floats is treated as mono.
        sample_rate : int, optional
            Output sample rate in Hz.  If provided, overrides spec.sample_rate.
            Defaults to spec.sample_rate (44 100 Hz unless spec is customised).
        metadata : AudioFileMetadata, optional
            String tags, loop points, and instrument info to embed in the file.
            Currently only written for WAV format (see wav_chunk_writer.py).
            Silently ignored for AIFF, RF64, CAF, and W64.
        spec : OutputSpec, optional
            Per-call output specification.  Overrides the default_spec set at
            construction time.  Useful when writing multiple formats from one
            AudioWriter instance.

        Raises
        ------
        ImportError  : soundfile is not installed (see soundfile_backend.py)
        RuntimeError : RF64 requested but soundfile version is too old
        ValueError   : format/subtype combination rejected by libsndfile
        OSError      : destination path not writable, disk full, etc.
        """
        resolved_spec = spec or self._default_spec
        resolved_sr   = sample_rate if sample_rate is not None else resolved_spec.sample_rate

        # Pre-flight check for RF64: requires soundfile ≥ 0.11.0
        if resolved_spec.format == AudioFormat.RF64:
            assert_rf64_supported()

        # Normalise samples to a float32 ndarray
        arr = self._to_float32(samples)

        # Infer channel count from data shape (never from OutputSpec)
        n_channels = arr.shape[1] if arr.ndim == 2 else 1

        # Apply TPDF dithering when writing to an integer bit depth.
        # Floating-point targets (FLOAT_32, FLOAT_64) need no dithering
        # because no bit-depth reduction occurs.
        if resolved_spec.apply_dither and self._is_integer_depth(resolved_spec.bit_depth):
            target_bits = self._bits_for_depth(resolved_spec.bit_depth)
            arr = self._dither.apply(arr, target_bits)

        # Look up the soundfile format and subtype strings from our mapping tables
        sf_format  = FORMAT_MAP[resolved_spec.format.value]
        sf_subtype = SUBTYPE_MAP[resolved_spec.bit_depth.value]

        filepath = Path(filepath)
        sf = get_soundfile()

        # ── Write the audio file via soundfile / libsndfile ──────────────────
        with sf.SoundFile(
            str(filepath),
            mode='w',
            samplerate=resolved_sr,
            channels=n_channels,
            format=sf_format,
            subtype=sf_subtype,
        ) as f:
            f.write(arr)
            # Write string tags (title/artist/comment) via libsndfile's
            # sf_set_string() if the format supports it.  Unsupported formats
            # raise no error — the tags are silently dropped by libsndfile.
            if metadata:
                self._apply_string_tags_via_ctypes(f, metadata)

        # ── Append WAV-specific binary chunks after soundfile closes the file ─
        # smpl (loop points) and inst (MIDI instrument info) chunks are not
        # exposed by soundfile's Python API; we append them manually.
        # String metadata for WAV is also handled here via LIST INFO chunks
        # if the ctypes path above did not succeed (soundfile version-dependent).
        if metadata and resolved_spec.format == AudioFormat.WAV:
            self._chunk_writer.append_metadata(filepath, metadata, resolved_sr)

    # ── Helper: normalise input to float32 ndarray ────────────────────────────

    @staticmethod
    def _to_float32(
        samples: Union[List[float], np.ndarray]
    ) -> np.ndarray:
        """
        Convert *samples* to a float32 numpy array.

        Lists are treated as mono (1-D).  Numpy arrays are cast to float32
        without copying if they are already the correct dtype.
        """
        if isinstance(samples, list):
            # Plain Python list → 1-D mono array
            return np.array(samples, dtype=np.float32)

        # Numpy array: cast dtype only if needed (avoids unnecessary copy)
        return np.asarray(samples, dtype=np.float32)

    # ── Helper: dithering decision ────────────────────────────────────────────

    @staticmethod
    def _is_integer_depth(depth: BitDepth) -> bool:
        """Return True if *depth* is an integer PCM format that benefits from dithering."""
        return depth in (BitDepth.INT_16, BitDepth.INT_24)

    @staticmethod
    def _bits_for_depth(depth: BitDepth) -> int:
        """Map a BitDepth enum value to the corresponding integer bit count."""
        return 16 if depth == BitDepth.INT_16 else 24

    # ── Helper: string tag writing via soundfile internal handle ──────────────

    @staticmethod
    def _apply_string_tags_via_ctypes(sf_file, metadata: AudioFileMetadata) -> None:
        """
        Write title / artist / comment tags into *sf_file* using libsndfile's
        sf_set_string() function accessed through soundfile's internal ctypes handle.

        soundfile does not expose sf_set_string() in its public Python API, so we
        reach into the private _handle attribute.  This is version-dependent:
        if the attribute is absent (future soundfile versions may rename it) the
        call is silently skipped and the WAVChunkWriter LIST INFO path handles
        string tags instead.

        Tag IDs (SF_STR_*)
        ------------------
        1  SF_STR_TITLE
        2  SF_STR_COPYRIGHT
        3  SF_STR_SOFTWARE
        4  SF_STR_ARTIST
        5  SF_STR_COMMENT
        6  SF_STR_DATE
        """
        try:
            import soundfile as sf_mod  # noqa: PLC0415

            # Access the internal ctypes handle (SoundFile._handle)
            handle = sf_file._handle

            # sf_set_string(sndfile*, sf_str_type int, const char* str) → int
            set_str = sf_mod._snd.sf_set_string

            if metadata.title:
                set_str(handle, 1, metadata.title.encode('utf-8'))  # SF_STR_TITLE
            if metadata.artist:
                set_str(handle, 4, metadata.artist.encode('utf-8'))  # SF_STR_ARTIST
            if metadata.comment:
                set_str(handle, 5, metadata.comment.encode('utf-8'))  # SF_STR_COMMENT

        except Exception:
            # Any failure here is non-fatal: WAVChunkWriter's LIST INFO chunk
            # will provide an alternative mechanism for WAV files.
            pass
