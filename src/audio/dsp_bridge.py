"""
src/audio/dsp_bridge.py
────────────────────────
Python bridge to the C++ synth_core DSP extension module.

This module owns the import and graceful fallback for the compiled
``synth_core`` pybind11 extension.  It re-exports two facades:

``SaturationBridge``
    Wraps ``synth_core.SaturationProcessor`` for block-level saturation of
    numpy float32 audio buffers.  Falls back to a pure-Python soft-clipper
    when the C++ extension is not built yet.

``DspSession``
    Convenience class that combines a ``SaturationBridge``, the Python-side
    ``AperiodicLFOEngine``, and ``ParameterSmoother`` for a single render
    session.  Callers drive the session one audio block at a time.

Cross-platform path resolution
───────────────────────────────
The compiled extension lands next to the project root as either::

    synth_core.cpython-3XX-win_amd64.pyd      (Windows)
    synth_core.cpython-3XX-darwin.so           (macOS)

``pathlib.Path`` is used to resolve this location at runtime so no
OS-specific path separators are hard-coded.

Buffer contract
───────────────
All audio buffers exchanged with C++ are ``numpy.ndarray[float32, ndim=1]``
(C-contiguous).  Never pass Python lists — this avoids a full memory copy
on every block boundary and satisfies the numpy.ctypeslib design constraint
recorded in the project's architecture notes.

Usage::

    from src.audio.dsp_bridge import DspSession
    from src.midi.genre_profiles import GenreProfileLibrary

    lib     = GenreProfileLibrary()
    profile = lib.get("trap", 138.0)
    session = DspSession(profile, bpm=138.0, sample_rate=48000, seed=42)

    audio_block = np.zeros(512, dtype=np.float32)   # replace with real audio
    result      = session.process_block(audio_block)
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from src.midi.genre_profiles import GenreProfile

# ── Optional imports from sibling modules ────────────────────────────────────
from src.dsp.lfo_engine import AperiodicLFOEngine
from src.dsp.parameter_smoother import ParameterSmoother


# ── Resolve the compiled C++ extension path ───────────────────────────────────
# The extension is placed in the project root by CMake's install rule.
# pathlib handles both Windows (\) and macOS (/) separators automatically.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

def _import_synth_core():
    """
    Attempt to import the compiled synth_core pybind11 extension.

    Adds the project root to sys.path so Python can locate the .pyd/.so file
    regardless of the current working directory.  Returns the module on
    success, None on ImportError (extension not built yet).
    """
    root_str = str(_PROJECT_ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    try:
        import synth_core as _sc   # noqa: PLC0415 (import inside function — intentional)
        return _sc
    except ImportError:
        return None

_synth_core = _import_synth_core()
_CPP_AVAILABLE = _synth_core is not None

if not _CPP_AVAILABLE:
    warnings.warn(
        "[DspBridge] synth_core C++ extension not found — "
        "using pure-Python fallback saturation.  "
        "Build with: cmake --build build --config Release",
        RuntimeWarning,
        stacklevel=2,
    )


# ── Pure-Python fallback saturation ──────────────────────────────────────────

def _python_tape_soft(buf: np.ndarray, drive_pct: float) -> np.ndarray:
    """
    Minimal pure-Python tape-soft saturation fallback.

    Only used when synth_core.so/.pyd is not available.  Quality is lower
    than the C++ implementation (no per-sample drive smoothing) but the
    output is musically acceptable for offline rendering.
    """
    if drive_pct < 0.01:
        return buf.copy()
    drive_norm = np.clip(drive_pct / 100.0, 0.0, 1.0)
    pre        = 1.0 + drive_norm * 4.0
    driven     = buf * pre + 0.1 * drive_norm * buf * np.abs(buf)
    # Normalise output to the range of the input.
    return np.tanh(driven) / np.tanh(pre)


# ── SaturationBridge ──────────────────────────────────────────────────────────

class SaturationBridge:
    """
    Block-level saturation bridge over ``synth_core.SaturationProcessor``.

    Delegates to C++ when the extension is available; silently falls back
    to a pure-Python implementation otherwise so downstream code is not
    gated on a successful build.

    Parameters
    ----------
    saturation_type : str
        Algorithm name: 'none','tape_soft','tube_tanh','hard_clip',
        'asymmetric_soft','vinyl_tape','waveshaper'.
    drive_pct_initial : float
        Initial drive level 0.0–100.0 %.
    sample_rate : int
        Audio sample rate in Hz.
    smoothing_ms : float
        De-clicking window in ms (passed to C++ constructor; no effect in
        the Python fallback because it applies a whole-block transform).
    """

    def __init__(
        self,
        saturation_type:   str   = "none",
        drive_pct_initial: float = 0.0,
        sample_rate:       int   = 48_000,
        smoothing_ms:      float = 5.0,
    ) -> None:
        self._type        = saturation_type
        self._drive_pct   = drive_pct_initial
        self._sample_rate = sample_rate
        self._cpp: Optional[object] = None  # synth_core.SaturationProcessor instance

        if _CPP_AVAILABLE:
            self._cpp = _synth_core.SaturationProcessor(
                sample_rate  = sample_rate,
                smoothing_ms = smoothing_ms,
            )
            self._cpp.set_type_from_string(saturation_type)
            self._cpp.set_drive(drive_pct_initial)

    def set_drive(self, drive_pct: float) -> None:
        """
        Update the drive target.

        In C++ mode the change is smoothed over smoothing_ms; in fallback
        mode it takes effect on the next process() call immediately.
        """
        self._drive_pct = drive_pct
        if self._cpp is not None:
            self._cpp.set_drive(drive_pct)

    def set_type(self, saturation_type: str) -> None:
        """Switch saturation algorithm by name string."""
        self._type = saturation_type
        if self._cpp is not None:
            self._cpp.set_type_from_string(saturation_type)

    def process(self, audio_block: np.ndarray) -> np.ndarray:
        """
        Apply saturation to *audio_block* and return the processed buffer.

        Parameters
        ----------
        audio_block : numpy.ndarray[float32, ndim=1]
            Input audio samples.  Must be C-contiguous float32.

        Returns
        -------
        numpy.ndarray[float32, ndim=1] — processed block, same length as input.
        """
        # Ensure the buffer is C-contiguous float32 before passing to C++.
        # np.ascontiguousarray is a no-op if the array already satisfies the
        # layout requirements, so there is no unnecessary copy in the common case.
        buf = np.ascontiguousarray(audio_block, dtype=np.float32)

        if self._cpp is not None:
            # Zero-copy handoff: pybind11 reads directly from the numpy buffer.
            return np.asarray(self._cpp.process(buf), dtype=np.float32)
        else:
            # Pure-Python fallback.
            return _python_tape_soft(buf, self._drive_pct).astype(np.float32)


# ── DspSession ────────────────────────────────────────────────────────────────

class DspSession:
    """
    Per-render DSP session: saturation + LFO + parameter smoothing.

    Combines ``SaturationBridge``, ``AperiodicLFOEngine``, and
    ``ParameterSmoother`` into a single block-processing interface.

    Call ``process_block()`` once per audio block; the LFO, smoother, and
    saturation all advance together so automation is sample-accurate.

    Parameters
    ----------
    profile : GenreProfile
        Drives saturation type/drive range, LFO targets, and waveform mode.
    bpm : float
        Current tempo in BPM.
    sample_rate : int
        Audio sample rate in Hz.
    seed : int | None
        Random seed for reproducible LFO behaviour.
    smoothing_ms : float
        De-clicking window forwarded to both the C++ processor and the Python
        ``ParameterSmoother``.
    """

    def __init__(
        self,
        profile:      "GenreProfile",
        bpm:          float,
        sample_rate:  int   = 48_000,
        seed:         Optional[int] = None,
        smoothing_ms: float = 5.0,
    ) -> None:
        self._profile      = profile
        self._bpm          = bpm
        self._sample_rate  = sample_rate
        self._smoothing_ms = smoothing_ms

        # Saturation bridge — initial drive set to mid-point of profile range.
        init_drive = (profile.drive_pct_min + profile.drive_pct_max) / 2.0
        self._saturator = SaturationBridge(
            saturation_type   = profile.saturation_type,
            drive_pct_initial = init_drive,
            sample_rate       = sample_rate,
            smoothing_ms      = smoothing_ms,
        )

        # Aperiodic LFO engine (Python side — generates normalised curves).
        self._lfo = AperiodicLFOEngine(
            profile     = profile,
            bpm         = bpm,
            sample_rate = sample_rate,
            seed        = seed,
        )

        # Parameter smoother (Python side — de-clicking before C++ bridge).
        self._smoother = ParameterSmoother(
            smoothing_ms = smoothing_ms,
            sample_rate  = sample_rate,
        )
        # Register drive as a smoothable parameter.
        self._smoother.register("drive", initial_value=init_drive)
        self._smoother.set_range(
            "drive",
            profile.drive_pct_min,
            profile.drive_pct_max,
        )

    def process_block(self, audio_block: np.ndarray) -> np.ndarray:
        """
        Process one block of audio through the full DSP session.

        Steps (in order):
          1. Advance the LFO by block_size samples.
          2. Feed LFO output into the parameter smoother to update drive target.
          3. Read the smoothed drive value and forward to the saturation bridge.
          4. Process the audio block through saturation.

        Parameters
        ----------
        audio_block : numpy.ndarray[float32, ndim=1]

        Returns
        -------
        numpy.ndarray[float32, ndim=1] — processed audio.
        """
        block_size = len(audio_block)

        # 1. Advance LFO — produces normalised [0, 1] values per target.
        lfo_out = self._lfo.next_block(block_size)

        # 2. Push LFO output through the parameter smoother.
        #    The smoother scales each target to its physical range and smooths
        #    transitions to prevent zipper noise in the Python parameter layer.
        self._smoother.apply_lfo_block(lfo_out)

        # 3. Update saturation drive from the smoothed parameter value.
        smoothed_drive = self._smoother.get_current("drive")
        self._saturator.set_drive(smoothed_drive)

        # 4. Saturate the audio block.
        #    The C++ SaturationProcessor applies its OWN per-sample smoother
        #    for the final de-clicking on top of the Python-level smoothing.
        return self._saturator.process(audio_block)

    def update_bpm(self, bpm: float) -> None:
        """Notify the session of a tempo change (recalculates LFO hold times)."""
        self._bpm = bpm
        self._lfo.update_bpm(bpm)

    def update_profile(self, profile: "GenreProfile") -> None:
        """
        Switch to a new genre profile mid-session.

        Updates the saturation type, drive range, and LFO targets.
        Any in-progress LFO ramp completes before the new parameters take effect.
        """
        self._profile = profile
        self._saturator.set_type(profile.saturation_type)
        new_drive = (profile.drive_pct_min + profile.drive_pct_max) / 2.0
        self._saturator.set_drive(new_drive)
        self._smoother.set_range("drive", profile.drive_pct_min, profile.drive_pct_max)

    # ── Accessors ─────────────────────────────────────────────────────────────

    @property
    def cpp_available(self) -> bool:
        """True when the C++ synth_core extension is loaded and in use."""
        return _CPP_AVAILABLE

    @property
    def saturator(self) -> SaturationBridge:
        """Direct access to the SaturationBridge for manual drive control."""
        return self._saturator

    @property
    def smoother(self) -> ParameterSmoother:
        """Direct access to the ParameterSmoother for additional parameters."""
        return self._smoother
