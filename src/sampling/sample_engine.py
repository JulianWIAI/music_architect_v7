"""
src/sampling/sample_engine.py
──────────────────────────────
Manages per-track SamplePlayer instances for sample-based synthesis.

Call load_from_assignments() before each render to pre-load every assigned
audio file.  Call synthesize() per MIDI event during the render loop.

The engine uses the C++ SamplePlayer (from synth_core) when it is available,
and falls back to a pure-Python pitch-shifting implementation otherwise.

Public API
----------
SampleEngine(sample_rate: int)
    load_from_assignments(assignments: dict[str, str]) -> None
    synthesize(comp_track_name: str, midi_note, start_time, duration, velocity)
        -> tuple[int, ndarray]
    is_loaded(comp_track_name: str) -> bool
    clear() -> None

Track-key mapping
-----------------
assignments dict uses builder keys (bass, melody, chords, pads, arp, stabs,
texture, fx).  Internally these are mapped to composition track names
(03_Bass, 04_Melody, …) so BuiltinSynthesizer can look them up by track name.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np

from src.sampling.sample_loader import load_audio_file

# Builder-key → composition track-name mapping.
# Must match the track names produced by CompositionEngine.
_BUILDER_TO_COMP: Dict[str, str] = {
    'bass':    '03_Bass',
    'melody':  '04_Melody',
    'chords':  '05_Chords',
    'pads':    '06_Pad',
    'arp':     '07_Arp',
    'stabs':   '08_Stabs',
    'texture': '09_Texture',
    'fx':      '10_FX',
}


class _PythonPlayer:
    """
    Pure-Python fallback player used when synth_core.SamplePlayer is not
    compiled.  Applies linear-interpolation pitch-shifting and a simple ADSR
    envelope.

    Performance note: this path is significantly slower than the C++ player;
    it is only used when the C++ extension has not been compiled.
    """

    def __init__(self, buffer: np.ndarray, source_sr: int, root_midi: int,
                 render_sr: int) -> None:
        self._buf       = buffer.astype(np.float32)
        self._source_sr = source_sr
        self._root      = root_midi
        self._rate      = render_sr

    def synthesize(
        self,
        midi_note: int,
        start_time: float,
        duration: float,
        velocity: float,
        attack: float  = 0.005,
        decay: float   = 0.10,
        sustain: float = 0.80,
        release: float = 0.30,
    ) -> Tuple[int, np.ndarray]:
        semitones  = midi_note - self._root
        pitch_ratio = 2.0 ** (semitones / 12.0)

        # Resample for pitch-shifting: play sample faster/slower.
        src_len = len(self._buf)
        # How many source samples we need to fill one render-rate second:
        #   render_sr samples at target pitch = source_sr / pitch_ratio samples of src
        src_per_render = self._source_sr / (pitch_ratio * self._rate)
        n_output = int((duration + release) * self._rate)
        if n_output <= 0 or src_len == 0:
            return int(start_time * self._rate), np.zeros(1, dtype=np.float32)

        # Build index array into source buffer (linear interpolation)
        idx  = np.arange(n_output, dtype=np.float64) * src_per_render
        idx  = np.clip(idx, 0, src_len - 1)
        i0   = idx.astype(np.int64)
        frac = (idx - i0).astype(np.float32)
        i1   = np.clip(i0 + 1, 0, src_len - 1)
        out  = self._buf[i0] + frac * (self._buf[i1] - self._buf[i0])

        # ADSR envelope
        env = _adsr_envelope(n_output, self._rate, attack, decay, sustain,
                             duration, release)
        out  = out * env * (velocity / 127.0)
        start_idx = int(start_time * self._rate)
        return start_idx, out.astype(np.float32)


def _adsr_envelope(
    n: int, rate: int,
    attack: float, decay: float, sustain: float,
    note_dur: float, release: float,
) -> np.ndarray:
    """Return a float32 ADSR envelope of length n."""
    env  = np.ones(n, dtype=np.float32)
    a_s  = int(attack  * rate)
    d_s  = int(decay   * rate)
    r_s  = int(release * rate)
    nd_s = int(note_dur * rate)

    for i in range(min(a_s, n)):
        env[i] = i / max(a_s, 1)
    for i in range(a_s, min(a_s + d_s, n)):
        t = (i - a_s) / max(d_s, 1)
        env[i] = 1.0 - t * (1.0 - sustain)
    for i in range(a_s + d_s, min(nd_s, n)):
        env[i] = sustain
    for i in range(nd_s, n):
        t = (i - nd_s) / max(r_s, 1)
        env[i] = sustain * max(0.0, 1.0 - t)
    return env


class SampleEngine:
    """
    Pre-loads one audio sample per track and provides sample-based synthesis
    compatible with BuiltinSynthesizer's mix loop.

    Parameters
    ----------
    sample_rate : int
        Output sample rate of the render (default 44100).
    """

    def __init__(self, sample_rate: int = 44100) -> None:
        self._rate    = sample_rate
        # comp_track_name → player object (C++ or Python)
        self._players: Dict[str, Any] = {}

        # Detect C++ availability once at construction time
        try:
            import synth_core as _sc
            self._cpp_cls = _sc.SamplePlayer if hasattr(_sc, 'SamplePlayer') else None
        except ImportError:
            self._cpp_cls = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def load_from_assignments(
        self,
        assignments: Dict[str, str],
    ) -> None:
        """
        Synchronously load all audio files in assignments.

        Call this from the render thread before starting the mix loop.
        GUI widgets must not be accessed from the render thread — pass
        the assignments dict (a plain Python dict) captured on the main thread.

        Parameters
        ----------
        assignments : dict[str, str]
            Builder-key → absolute file path.  Empty string values are ignored.
        """
        self._players.clear()
        for builder_key, path in assignments.items():
            if not path:
                continue
            comp_name = _BUILDER_TO_COMP.get(builder_key)
            if comp_name is None:
                continue
            try:
                buf, sr = load_audio_file(path)
                self._players[comp_name] = self._make_player(buf, sr, root_midi=60)
                print(f"[SampleEngine] Loaded '{path}' → {comp_name}")
            except Exception as exc:
                print(f"[SampleEngine] Failed to load '{path}' for '{builder_key}': {exc}")

    def is_loaded(self, comp_track_name: str) -> bool:
        """Return True when a sample is loaded for the given composition track."""
        return comp_track_name in self._players

    def synthesize(
        self,
        comp_track_name: str,
        midi_note: int,
        start_time: float,
        duration: float,
        velocity: float,
    ) -> Tuple[int, np.ndarray]:
        """
        Render one note event using the loaded sample for comp_track_name.

        Return contract mirrors SynthCore.synthesize_note():
            (start_sample_index: int, samples: ndarray[float32])
        """
        player = self._players.get(comp_track_name)
        if player is None:
            raise KeyError(f"No sample loaded for track '{comp_track_name}'")
        start_idx, arr = player.synthesize(midi_note, start_time, duration, velocity)
        return int(start_idx), np.asarray(arr, dtype=np.float32)

    def clear(self) -> None:
        """Unload all samples and release memory."""
        self._players.clear()

    # ── Private ────────────────────────────────────────────────────────────────

    def _make_player(
        self,
        buf: np.ndarray,
        source_sr: int,
        root_midi: int = 60,
    ) -> Any:
        """Create a C++ SamplePlayer or Python fallback, loading the buffer."""
        if self._cpp_cls is not None:
            player = self._cpp_cls(self._rate)
            player.load_sample(buf, source_sr, root_midi)
            return player
        # Python fallback
        return _PythonPlayer(buf, source_sr, root_midi, self._rate)
