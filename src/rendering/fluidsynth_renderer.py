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
import shutil
import subprocess
import threading
from typing import Optional

from src.rendering.soundfont_library import SoundFontLibrary
from src.rendering.fluidsynth_variant_params import build_fluidsynth_args


def _find_fluidsynth() -> Optional[str]:
    """
    Locate the FluidSynth executable, returning the full path or None.

    macOS GUI apps (launched from PyCharm, Finder, or the Dock) receive a
    stripped PATH that excludes Homebrew's prefix, so a bare ``shutil.which``
    call often fails even when FluidSynth is installed.  This function tries
    several locations in priority order:

    1. ``shutil.which('fluidsynth')``  — works when PATH is correct (terminal)
    2. ``/opt/homebrew/bin/fluidsynth``  — Homebrew on Apple Silicon (M1/M2/M3)
    3. ``/usr/local/bin/fluidsynth``     — Homebrew on Intel Mac / manual install
    4. ``/usr/bin/fluidsynth``           — system-wide install (rare)

    Returns
    -------
    str | None
        Full executable path if a working binary is found; None otherwise.
    """
    # Priority 1: respect whatever PATH the process has
    via_path = shutil.which('fluidsynth')
    if via_path:
        return via_path

    # Priority 2-4: hardcoded Homebrew / system fallbacks for GUI-launched apps
    for candidate in (
        '/opt/homebrew/bin/fluidsynth',   # Apple Silicon Homebrew
        '/usr/local/bin/fluidsynth',      # Intel Homebrew / manual
        '/usr/bin/fluidsynth',            # system package managers
    ):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    return None


# Resolved once at import time — avoids repeated filesystem lookups.
_FLUIDSYNTH_EXE: Optional[str] = _find_fluidsynth()

try:
    from src.dsp.mastering_chain import MasteringChain
    _MASTERING_AVAILABLE = True
except Exception:
    _MASTERING_AVAILABLE = False


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
        self._genre: str = ''
        # 'professional' → full mastering chain, full gain (default).
        # 'retro'        → mastering bypassed, gain capped at 0.50.
        self._font_type: str = 'professional'
        self._library = SoundFontLibrary()
        self._current_proc: Optional[subprocess.Popen] = None
        self._proc_lock = threading.Lock()

    # ── Availability ──────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """
        Return True if a FluidSynth executable and at least one SF2 are found.

        Uses the module-level _FLUIDSYNTH_EXE resolved at import time, which
        searches Homebrew paths so the check works even when the app is launched
        from PyCharm or the macOS Dock (which strips the shell PATH).
        """
        if _FLUIDSYNTH_EXE is None:
            return False
        try:
            result = subprocess.run(
                [_FLUIDSYNTH_EXE, '--version'],
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

    def set_variant(self, variant_id: str) -> None:
        """Store the timbral variant used for the next render ('bright'/'neutral'/'dark')."""
        self._variant = variant_id if variant_id in ('bright', 'neutral', 'dark') else 'neutral'

    def set_genre(self, genre: str) -> None:
        """Store the genre so build_fluidsynth_args() selects the matching FX profile."""
        self._genre = genre or ''

    def set_font_type(self, font_type: str) -> None:
        """
        Set how the custom override SoundFont should be processed.

        'professional' — full mastering chain, standard gain.  Use for
                         high-quality GM fonts (Crisis 3.51, SGM, etc.).
        'retro'        — mastering chain bypassed, gain capped at 0.50,
                         chorus and reverb tamed.  Use for game / 8-bit
                         SoundFonts that clip or distort at full settings.

        Has no effect when no override is set (genre-routed fonts always
        use the full pipeline regardless of this setting).
        """
        self._font_type = font_type if font_type in ('professional', 'retro') else 'professional'

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
        #
        # override_mode=True only when the user loaded a custom SoundFont AND
        # marked it as 'retro' (game / 8-bit).  Retro mode caps gain at 0.50
        # and tames chorus/reverb so hot game-font samples don't clip.
        # Professional custom fonts (Crisis 3.51, SGM, etc.) keep full gain
        # and the full mastering chain regardless of being an override.
        using_override = (
            self._override is not None and self._font_type == 'retro'
        )
        variant_flags, gain = build_fluidsynth_args(
            self._variant, self._genre, override_mode=using_override
        )
        cmd = [
            _FLUIDSYNTH_EXE,
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

            wav_ok = proc.returncode == 0 and os.path.exists(wav_path)
            # Apply mastering chain in-place on the preview WAV so that
            # both listening and export reflect the full production sound.
            #
            # The mastering chain (compressor, LUFS normaliser, true-peak
            # limiter) was calibrated for professional SoundFonts (Fluid R3,
            # GeneralUser GS, Arachno).  Applying it to custom/game SoundFonts
            # (e.g. Mario) that are already hot and timbrely distinct causes
            # heavy over-compression — the classic "broken speaker / airport PA"
            # artefact.  When the user has loaded an override font we skip the
            # mastering chain so the raw FluidSynth output (already tamed by
            # the reduced gain/chorus in override_mode) is written unmodified.
            if wav_ok and _MASTERING_AVAILABLE and not using_override:
                try:
                    chain = MasteringChain()
                    ok_m, msg_m = chain.process(
                        wav_in     = wav_path,
                        wav_out    = wav_path,   # in-place via internal tempfile
                        genre      = self._genre or genre,
                        variant_id = self._variant,
                        target_id  = 'streaming',
                    )
                    if not ok_m:
                        print(f'[FluidSynthRenderer] Mastering skipped: {msg_m}')
                except Exception as me:
                    print(f'[FluidSynthRenderer] Mastering error (preview unaffected): {me}')
            return wav_ok
        except Exception as e:
            print(f'FluidSynth render error: {e}')
            return False
