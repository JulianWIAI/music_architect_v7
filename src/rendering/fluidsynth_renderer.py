"""
FluidSynthRenderer

Renders MIDI files to WAV using the FluidSynth command-line tool.
Requires: fluidsynth installed on PATH and at least one .sf2 SoundFont file.

SF2 selection is delegated to SoundFontLibrary, which routes each genre to the
most appropriate installed font:
  - GeneralUser GS  → pop, j-pop, edm, house, classical  (bright, melodic)
  - Fluid R3 GM     → trap, hip-hop, cinematic, phonk, techno, dnb  (punchy, dark)
"""

import os
import subprocess
from typing import Optional

from src.rendering.soundfont_library import SoundFontLibrary


class FluidSynthRenderer:
    """
    High-quality MIDI-to-WAV renderer via FluidSynth.

    Falls back gracefully when FluidSynth or a SoundFont is unavailable —
    callers should check is_available() before invoking render().

    SF2 is chosen per render() call based on the genre argument, so a batch
    of songs with different genres each gets the most appropriate timbre.
    """

    def __init__(self, soundfont_path: Optional[str] = None) -> None:
        # Optional explicit override — bypasses the library's genre routing
        self._override: Optional[str] = (
            soundfont_path if soundfont_path and os.path.exists(soundfont_path)
            else None
        )
        self._library = SoundFontLibrary()

    # ── Availability ──────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Return True if FluidSynth is on PATH and at least one SF2 was found."""
        try:
            result = subprocess.run(
                ['fluidsynth', '--version'],
                capture_output=True, timeout=5,
            )
            has_sf2 = self._override is not None or self._library.any_available
            return result.returncode == 0 and has_sf2
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def soundfont_summary(self) -> str:
        """Human-readable summary of discovered SF2 files, for the log panel."""
        if self._override:
            return f'Using override SF2: {self._override}'
        return self._library.summary()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def render(
        self,
        midi_path:   str,
        wav_path:    str,
        sample_rate: int = 44100,
        genre:       str = '',
    ) -> bool:
        """
        Render *midi_path* to *wav_path* using FluidSynth.

        Parameters
        ----------
        midi_path   : Input MIDI file path.
        wav_path    : Output WAV file path.
        sample_rate : Sample rate in Hz (default 44100).
        genre       : Genre string used to select the best SF2 (e.g. 'trap').
                      Ignored when an explicit soundfont_path was passed to __init__.

        Returns
        -------
        True on success, False if FluidSynth is unavailable or rendering fails.
        """
        if not self.is_available():
            return False

        sf2 = self._override or self._library.select(genre)
        if not sf2:
            return False

        try:
            cmd = [
                'fluidsynth', '-ni',
                sf2, midi_path,
                '-F', wav_path,
                '-r', str(sample_rate),
                '-g', '0.8',
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=120)
            return result.returncode == 0 and os.path.exists(wav_path)
        except Exception as e:
            print(f'FluidSynth render error: {e}')
            return False
