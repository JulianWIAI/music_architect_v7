"""
FluidSynthRenderer

Renders MIDI files to WAV using the FluidSynth command-line tool.
Requires: fluidsynth installed on PATH and a .sf2 SoundFont file.
"""

import os
import subprocess
from typing import Optional


class FluidSynthRenderer:
    """
    High-quality MIDI-to-WAV renderer via FluidSynth.

    Falls back gracefully when FluidSynth or a SoundFont is unavailable —
    callers should check is_available() before invoking render().
    """

    SOUNDFONT_SEARCH_PATHS = [
        r'C:\soundfonts\FluidR3_GM.sf2',
        r'C:\soundfonts\GeneralUser_GS.sf2',
        '/usr/share/sounds/sf2/FluidR3_GM.sf2',
        '/usr/share/soundfonts/FluidR3_GM.sf2',
        os.path.expanduser('~/soundfonts/FluidR3_GM.sf2'),
    ]

    def __init__(self, soundfont_path: Optional[str] = None):
        self.soundfont = soundfont_path
        self._find_soundfont()

    def _find_soundfont(self):
        if self.soundfont and os.path.exists(self.soundfont):
            return
        for path in self.SOUNDFONT_SEARCH_PATHS:
            if os.path.exists(path):
                self.soundfont = path
                return

    def is_available(self) -> bool:
        """Return True if FluidSynth is on PATH and a SoundFont file was found."""
        try:
            result = subprocess.run(['fluidsynth', '--version'], capture_output=True, timeout=5)
            return result.returncode == 0 and self.soundfont is not None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def render(self, midi_path: str, wav_path: str, sample_rate: int = 44100) -> bool:
        """Render *midi_path* to *wav_path* using FluidSynth. Returns True on success."""
        if not self.is_available():
            return False
        try:
            cmd = [
                'fluidsynth', '-ni',
                self.soundfont, midi_path,
                '-F', wav_path,
                '-r', str(sample_rate),
                '-g', '0.8',
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=120)
            return result.returncode == 0 and os.path.exists(wav_path)
        except Exception as e:
            print(f'FluidSynth error: {e}')
            return False
