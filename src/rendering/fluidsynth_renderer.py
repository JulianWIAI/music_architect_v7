"""
FluidSynthRenderer

Renders MIDI files to WAV using the FluidSynth command-line tool.
Requires: fluidsynth installed on PATH and at least one .sf2 SoundFont file.

SF2 selection is delegated to SoundFontLibrary, which routes each genre to the
most appropriate installed font:
  - GeneralUser GS  → pop, j-pop, edm, house, classical  (bright, melodic)
  - Fluid R3 GM     → trap, hip-hop, cinematic, phonk, techno, dnb  (punchy, dark)
  - Arachno SF v1.0 → cinematic, classical  (rich orchestral)

The `-a null` audio driver flag is critical: without it FluidSynth opens the
system audio device and renders in real-time (3 min song = 3 min wait + audio
playing through speakers).  With `-a null` it writes the WAV at CPU speed
(~15-20 s for a 3-minute song) and produces no speaker output.
"""

import os
import subprocess
import threading
from typing import Optional

from src.rendering.soundfont_library import SoundFontLibrary
from src.rendering.fluidsynth_variant_params import build_fluidsynth_args


class FluidSynthRenderer:
    """
    High-quality MIDI-to-WAV renderer via FluidSynth.

    Falls back gracefully when FluidSynth or a SoundFont is unavailable —
    callers should check is_available() before invoking render().

    SF2 is chosen per render() call based on the genre argument, so a batch
    of songs with different genres each gets the most appropriate timbre.

    The active subprocess is stored so cancel() can kill it mid-render when
    the user clicks Stop during generation.
    """

    def __init__(self, soundfont_path: Optional[str] = None) -> None:
        # Optional explicit override — bypasses the library's genre routing
        self._override: Optional[str] = (
            soundfont_path if soundfont_path and os.path.exists(soundfont_path)
            else None
        )
        self._variant: str = 'neutral'
        self._library = SoundFontLibrary()
        self._current_proc: Optional[subprocess.Popen] = None
        self._proc_lock = threading.Lock()

    # ── Availability ──────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Return True if FluidSynth is on PATH and at least one SF2 is accessible."""
        try:
            result = subprocess.run(
                ['fluidsynth', '--version'],
                capture_output=True, timeout=5,
            )
            # Count an override as available even before the path is existence-
            # checked — render() will fall back to the library if the file is
            # missing.  This keeps is_available() consistent with set_override()
            # which now stores the path unconditionally.
            has_sf2 = self._override is not None or self._library.any_available
            return result.returncode == 0 and has_sf2
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def soundfont_summary(self) -> str:
        """Human-readable summary of discovered SF2 files, for the log panel."""
        if self._override:
            return f'Using override SF2: {self._override}'
        return self._library.summary()

    def set_variant(self, variant_id: str) -> None:
        """Store the timbral variant used for the next render ('bright'/'neutral'/'dark')."""
        self._variant = variant_id if variant_id in ('bright', 'neutral', 'dark') else 'neutral'

    def set_override(self, path: Optional[str]) -> None:
        """
        Change the SF2 override at runtime without recreating the renderer.

        Pass a valid .sf2 path to force every render to use that font.
        Pass None to revert to the SoundFontLibrary's genre-routing logic.

        The existence check is intentionally omitted here: Tkinter's
        filedialog returns forward-slash paths on Windows which os.path.exists
        may evaluate inconsistently across threads.  The path is validated
        inside render() immediately before the FluidSynth subprocess is built.
        """
        self._override = path if path else None

    def active_sf2(self, genre: str = '') -> Optional[str]:
        """
        Return the SF2 path that render() would use for *genre*.

        Used by the log panel to show which font is active without
        starting a render.  Returns None if no SF2 is available at all.
        """
        sf2 = os.path.normpath(self._override) if self._override else self._library.select(genre)
        return sf2 if sf2 and os.path.exists(sf2) else self._library.select(genre)

    def cancel(self) -> None:
        """Kill any in-progress render subprocess immediately."""
        with self._proc_lock:
            if self._current_proc and self._current_proc.poll() is None:
                self._current_proc.kill()
                self._current_proc = None

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
        True on success, False if FluidSynth is unavailable, cancelled, or failing.
        """
        if not self.is_available():
            return False

        # Resolve SF2: override takes priority over genre routing.
        # Normalize the path before the existence check: Tkinter's filedialog
        # on Windows returns forward-slash paths (C:/Users/…) that os.path.exists
        # can mishandle on some configurations.  normpath converts them to the
        # OS-native separator (C:\Users\…) so the check and the subprocess both
        # receive a consistent path.
        sf2 = os.path.normpath(self._override) if self._override else None
        if sf2 and not os.path.exists(sf2):
            print(f'[FluidSynthRenderer] Override SF2 not found: {sf2} — falling back to genre routing')
            sf2 = None
        if sf2 is None:
            sf2 = self._library.select(genre)
        if not sf2:
            return False

        # FluidSynth requires ALL option flags before positional arguments.
        # Placing -F / -r / -g after sf2 / midi_path causes FluidSynth to
        # ignore those flags, produce no WAV output, and exit non-zero —
        # which silently triggers the MIDI-playback fallback in the caller.
        variant_flags, gain = build_fluidsynth_args(self._variant)
        cmd = [
            'fluidsynth',
            '-ni',                   # non-interactive, no MIDI input
            '-a', 'null',            # null audio driver — fast, no speaker output
            '-F', wav_path,          # output WAV file  (must come before positional args)
            '-r', str(sample_rate),  # sample rate
            '-g', f'{gain:.3f}',     # master gain set by active timbral variant
            *variant_flags,          # reverb/chorus -o overrides for BRIGHT/NEUTRAL/DARK
            sf2,                     # positional: SoundFont
            midi_path,               # positional: MIDI file
        ]

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with self._proc_lock:
                self._current_proc = proc
            try:
                proc.communicate(timeout=120)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                return False
            finally:
                with self._proc_lock:
                    if self._current_proc is proc:
                        self._current_proc = None

            return proc.returncode == 0 and os.path.exists(wav_path)
        except Exception as e:
            print(f'FluidSynth render error: {e}')
            return False
