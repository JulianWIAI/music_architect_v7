"""
soundfont_library.py — SF2 soundfont discovery and genre-based routing.

Timbral rationale for the 3-font genre split
---------------------------------------------
Fluid R3 GM  (MIT license — free for any use)
    Controlled low end, punchy bass and kick patches, warm mid-range.
    Best for bass-heavy and darker genres where weight in the sub-register
    matters more than upper-register clarity.
    → trap, hip-hop, phonk, techno, dnb

GeneralUser GS v1.472  (S. Christian Collins — free for any use incl. commercial)
    Bright, clean upper harmonics.  Piano, guitar, and string patches are
    particularly well-rendered.  Good synth leads for EDM.  The 'commercial'
    sound — sits well in a mix without EQ intervention.
    → pop, j-pop, edm, house

Arachno SoundFont v1.0  (Maxime Abbey — verify license before use)
    Rich orchestral palette; strings, brass, choirs, and piano are standouts.
    The most expressive option for dramatic, sustained, and layered textures.
    Recommended for public presentation of cinematic and classical output.
    → cinematic, classical

When a preferred SF2 is not installed the library falls back to whichever
font IS available, so the system always renders audio.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional


# ── Candidate paths per SF2 key ───────────────────────────────────────────────
# Listed in order of preference; the first existing path wins for each key.
# Windows path matching is case-insensitive, so C:\SoundFonts == C:\soundfonts.

_SF2_SEARCH: Dict[str, List[str]] = {
    'fluid_r3': [
        r'C:\SoundFonts\FluidR3_GM.sf2',
        r'C:\soundfonts\FluidR3_GM.sf2',
        r'C:\SoundFonts\FluidR3_GM2.sf2',
        os.path.expanduser(r'~\soundfonts\FluidR3_GM.sf2'),
        os.path.expanduser(r'~\Documents\soundfonts\FluidR3_GM.sf2'),
        '/usr/share/sounds/sf2/FluidR3_GM.sf2',
        '/usr/share/soundfonts/FluidR3_GM.sf2',
        os.path.expanduser('~/soundfonts/FluidR3_GM.sf2'),
        # macOS Homebrew fallback — FluidSynth ships VintageDreams as its
        # bundled SF2.  The /opt/homebrew/share path is version-independent
        # (Homebrew maintains it as a stable symlink to the latest Cellar).
        '/opt/homebrew/share/fluid-synth/sf2/VintageDreamsWaves-v2.sf2',
        '/usr/local/share/fluid-synth/sf2/VintageDreamsWaves-v2.sf2',
    ],
    'generaluser': [
        # Exact installed filename first, then common variants
        r'C:\SoundFonts\GeneralUser GS v1.472.sf2',
        r'C:\SoundFonts\GeneralUser GS v1.471.sf2',
        r'C:\SoundFonts\GeneralUser_GS.sf2',
        r'C:\SoundFonts\GeneralUser GS.sf2',
        r'C:\soundfonts\GeneralUser GS v1.472.sf2',
        r'C:\soundfonts\GeneralUser GS v1.471.sf2',
        r'C:\soundfonts\GeneralUser_GS.sf2',
        os.path.expanduser(r'~\soundfonts\GeneralUser_GS.sf2'),
        os.path.expanduser(r'~\Downloads\GeneralUser GS v1.472.sf2'),
        os.path.expanduser('~/soundfonts/GeneralUser_GS.sf2'),
        # macOS Homebrew fallback
        '/opt/homebrew/share/fluid-synth/sf2/VintageDreamsWaves-v2.sf2',
        '/usr/local/share/fluid-synth/sf2/VintageDreamsWaves-v2.sf2',
    ],
    'arachno': [
        r'C:\SoundFonts\Arachno SoundFont - Version 1.0.sf2',
        r'C:\soundfonts\Arachno SoundFont - Version 1.0.sf2',
        r'C:\SoundFonts\Arachno.sf2',
        os.path.expanduser(r'~\soundfonts\Arachno SoundFont - Version 1.0.sf2'),
        os.path.expanduser('~/soundfonts/Arachno SoundFont - Version 1.0.sf2'),
        # macOS Homebrew fallback
        '/opt/homebrew/share/fluid-synth/sf2/VintageDreamsWaves-v2.sf2',
        '/usr/local/share/fluid-synth/sf2/VintageDreamsWaves-v2.sf2',
    ],
}

# ── Genre → SF2 preference ────────────────────────────────────────────────────
# Three-way split based on timbral strengths described above.

_GENRE_PREFERENCE: Dict[str, str] = {
    # Bright, melodic → GeneralUser GS
    'pop':       'generaluser',
    'jpop':      'generaluser',
    'edm':       'generaluser',
    'house':     'generaluser',
    # Rich orchestral → Arachno
    'cinematic': 'arachno',
    'classical': 'arachno',
    # Bass-heavy / dark → Fluid R3
    'trap':      'fluid_r3',
    'hiphop':    'fluid_r3',
    'hip-hop':   'fluid_r3',
    'phonk':     'fluid_r3',
    'techno':    'fluid_r3',
    'dnb':       'fluid_r3',
}

# Human-readable names for logging and UI
_SF2_DISPLAY: Dict[str, str] = {
    'fluid_r3':   'Fluid R3 GM',
    'generaluser': 'GeneralUser GS',
    'arachno':    'Arachno SF v1.0',
}


class SoundFontLibrary:
    """
    Discovers installed SF2 files at construction time and routes genre
    requests to the most appropriate font.

    Usage
    -----
        library = SoundFontLibrary()
        sf2_path = library.select(genre='cinematic')  # → Arachno path
        print(library.summary())                      # lists what was found
    """

    def __init__(self) -> None:
        # Discover which SF2s are actually installed
        self._available: Dict[str, str] = {}
        for sf_key, candidates in _SF2_SEARCH.items():
            for path in candidates:
                if os.path.exists(path):
                    self._available[sf_key] = path
                    break

    # ── Public interface ──────────────────────────────────────────────────────

    @property
    def any_available(self) -> bool:
        """True if at least one SF2 file was found."""
        return bool(self._available)

    @property
    def default(self) -> Optional[str]:
        """Path of the first discovered SF2 (fallback when no genre given)."""
        return next(iter(self._available.values()), None)

    def select(self, genre: str = '') -> Optional[str]:
        """
        Return the path of the best-matching SF2 for *genre*.

        Falls back to any available SF2 if the genre-preferred font is not
        installed.  Returns None only when no SF2 at all is found.
        """
        if not self._available:
            return None
        preferred_key = _GENRE_PREFERENCE.get(genre.lower(), 'generaluser')
        return self._available.get(preferred_key) or self.default

    def display_name(self, genre: str = '') -> str:
        """Return the human-readable name of the SF2 that select() would use."""
        if not self._available:
            return 'none'
        preferred_key = _GENRE_PREFERENCE.get(genre.lower(), 'generaluser')
        resolved_key  = preferred_key if preferred_key in self._available else next(iter(self._available))
        return _SF2_DISPLAY.get(resolved_key, resolved_key)

    def summary(self) -> str:
        """One-line summary of discovered fonts, for logging."""
        if not self._available:
            return 'No SF2 soundfonts found — audio requires FluidSynth + an SF2 file.'
        names = [_SF2_DISPLAY.get(k, k) for k in self._available]
        return f'Soundfonts available: {", ".join(names)}'
