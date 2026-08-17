"""
src/midi/groove_presets.py
──────────────────────────
Genre-aware default groove presets for all 10 tracks.

Each preset encodes music-theory-correct Tier-1 values so that a freshly
generated song already sounds well-balanced without any user tweaking.
Values are derived from the production guide JSON data (output_fader_db,
gain_staging, micro_timing_ms) and genre groove conventions:

  Swing %      50.0 = straight 16ths (trap/techno/DnB/EDM)
               52-54 = light shuffle (house/pop/hip-hop)
               60-66 = jazz/funk triplet feel (unused here but available)

  Timing nudge bass tracks sit 5-10 ms behind the grid in groove genres
               to give that pocket feel; leads sit dead on the grid.

  Gain (dB)    sourced from output_fader_db in each genre's JSON file.
               Encoded here so users see sensible defaults without loading
               the JSON themselves.

  Velocity     genre-typical ranges per instrument role (production guide
               gain_staging section: lufs_s converted to approximate MIDI
               velocity targets using the empirical mapping used by session
               engineers: –14 LUFS ≈ vel 95, –22 LUFS ≈ vel 55).

Public API
──────────
    presets = GroovePresetLibrary()
    settings: SongGrooveSettings = presets.get('trap')
"""

from __future__ import annotations

from typing import Dict

from src.midi.groove_settings import SongGrooveSettings, TrackGrooveSettings


# ── Per-genre preset tables ────────────────────────────────────────────────────
# Each entry is a dict keyed by GUI track name.
# Only fields that differ from identity defaults need to be specified.
# Missing tracks receive the default TrackGrooveSettings (identity).

_PRESETS: Dict[str, Dict[str, dict]] = {

    # ─────────────────────── TRAP ─────────────────────────────────────────────
    # Straight 16ths, punchy kick/bass, vocals/lead tamed, pads buried.
    'trap': {
        'drums':      dict(vel_min=80, vel_max=110, gain_db= 0.0, pan=  0, swing_pct=50.0, vel_curve='accent_1'),
        'bass':       dict(vel_min=90, vel_max=120, gain_db=-4.0, pan=  0, timing_nudge_ms=-8.0),
        'chords':     dict(vel_min=40, vel_max=75,  gain_db=-8.0, pan=  0, vel_curve='accent_1_3'),
        'lead':       dict(vel_min=65, vel_max=85,  gain_db=-4.0, pan=  0, vel_curve='flat'),
        'pad':        dict(vel_min=30, vel_max=65,  gain_db=-12.0,pan=  0),
        'arp':        dict(vel_min=55, vel_max=80,  gain_db=-9.0, pan=  0, swing_pct=50.0),
        'stabs':      dict(vel_min=70, vel_max=95,  gain_db=-7.0, pan=  0, vel_curve='accent_1'),
        'texture':    dict(vel_min=40, vel_max=70,  gain_db=-10.0,pan=  0),
        'fx':         dict(vel_min=50, vel_max=90,  gain_db=-10.0,pan=  0),
        'percussion': dict(vel_min=70, vel_max=100, gain_db=-7.0, pan=  0, swing_pct=50.0),
    },

    # ─────────────────────── HIP-HOP ──────────────────────────────────────────
    # Light swing (52 %), boom-bap emphasis on kick+snare, bass sits deep.
    'hiphop': {
        'drums':      dict(vel_min=75, vel_max=108, gain_db= 0.0, pan=  0, swing_pct=52.0, vel_curve='accent_1'),
        'bass':       dict(vel_min=85, vel_max=112, gain_db=-4.0, pan=  0, swing_pct=52.0, timing_nudge_ms=-10.0),
        'chords':     dict(vel_min=42, vel_max=72,  gain_db=-8.0, pan=  0, swing_pct=52.0, vel_curve='accent_1_3'),
        'lead':       dict(vel_min=60, vel_max=90,  gain_db=-5.0, pan=  0, swing_pct=52.0),
        'pad':        dict(vel_min=28, vel_max=60,  gain_db=-13.0,pan=  0),
        'arp':        dict(vel_min=50, vel_max=78,  gain_db=-9.0, pan=  0, swing_pct=52.0),
        'stabs':      dict(vel_min=65, vel_max=92,  gain_db=-7.0, pan=  0),
        'texture':    dict(vel_min=35, vel_max=68,  gain_db=-11.0,pan=  0),
        'fx':         dict(vel_min=45, vel_max=85,  gain_db=-10.0,pan=  0),
        'percussion': dict(vel_min=68, vel_max=98,  gain_db=-7.0, pan=  0, swing_pct=52.0),
    },

    # ─────────────────────── HOUSE ────────────────────────────────────────────
    # Light swing (53 %), four-on-the-floor kick is prominent, bass drives low end.
    'house': {
        'drums':      dict(vel_min=85, vel_max=112, gain_db=+1.0, pan=  0, swing_pct=53.0, vel_curve='flat'),
        'bass':       dict(vel_min=90, vel_max=116, gain_db=-3.0, pan=  0, swing_pct=53.0, timing_nudge_ms=-5.0),
        'chords':     dict(vel_min=45, vel_max=80,  gain_db=-7.0, pan=  0, swing_pct=53.0, vel_curve='accent_1_3'),
        'lead':       dict(vel_min=68, vel_max=92,  gain_db=-4.0, pan=  0, swing_pct=53.0),
        'pad':        dict(vel_min=32, vel_max=68,  gain_db=-12.0,pan=  0),
        'arp':        dict(vel_min=58, vel_max=85,  gain_db=-8.0, pan=  0, swing_pct=53.0),
        'stabs':      dict(vel_min=72, vel_max=96,  gain_db=-6.0, pan=  0, swing_pct=53.0),
        'texture':    dict(vel_min=38, vel_max=72,  gain_db=-10.0,pan=  0),
        'fx':         dict(vel_min=48, vel_max=88,  gain_db=-9.0, pan=  0),
        'percussion': dict(vel_min=72, vel_max=102, gain_db=-6.0, pan=  0, swing_pct=53.0),
    },

    # ─────────────────────── EDM ──────────────────────────────────────────────
    # Straight 16ths, festival loudness — leads prominent, pads wide and deep.
    'edm': {
        'drums':      dict(vel_min=88, vel_max=115, gain_db=+1.0, pan=  0, swing_pct=50.0, vel_curve='flat'),
        'bass':       dict(vel_min=92, vel_max=118, gain_db=-2.0, pan=  0, swing_pct=50.0),
        'chords':     dict(vel_min=50, vel_max=82,  gain_db=-6.0, pan=  0, vel_curve='accent_1_3'),
        'lead':       dict(vel_min=72, vel_max=98,  gain_db=-3.0, pan=  0, vel_curve='flat'),
        'pad':        dict(vel_min=38, vel_max=72,  gain_db=-10.0,pan=  0),
        'arp':        dict(vel_min=62, vel_max=90,  gain_db=-7.0, pan=  0, swing_pct=50.0),
        'stabs':      dict(vel_min=75, vel_max=100, gain_db=-5.0, pan=  0),
        'texture':    dict(vel_min=40, vel_max=72,  gain_db=-9.0, pan=  0),
        'fx':         dict(vel_min=52, vel_max=92,  gain_db=-8.0, pan=  0),
        'percussion': dict(vel_min=75, vel_max=105, gain_db=-5.0, pan=  0, swing_pct=50.0),
    },

    # ─────────────────────── TECHNO ───────────────────────────────────────────
    # Straight 16ths, industrial — kick dominant, everything else recedes.
    'techno': {
        'drums':      dict(vel_min=90, vel_max=115, gain_db=+2.0, pan=  0, swing_pct=50.0, vel_curve='flat'),
        'bass':       dict(vel_min=88, vel_max=115, gain_db=-3.0, pan=  0, swing_pct=50.0),
        'chords':     dict(vel_min=38, vel_max=72,  gain_db=-9.0, pan=  0),
        'lead':       dict(vel_min=62, vel_max=85,  gain_db=-6.0, pan=  0),
        'pad':        dict(vel_min=28, vel_max=62,  gain_db=-13.0,pan=  0),
        'arp':        dict(vel_min=58, vel_max=85,  gain_db=-8.0, pan=  0, swing_pct=50.0),
        'stabs':      dict(vel_min=70, vel_max=98,  gain_db=-5.0, pan=  0),
        'texture':    dict(vel_min=35, vel_max=68,  gain_db=-11.0,pan=  0),
        'fx':         dict(vel_min=50, vel_max=90,  gain_db=-7.0, pan=  0),
        'percussion': dict(vel_min=78, vel_max=108, gain_db=-5.0, pan=  0, swing_pct=50.0),
    },

    # ─────────────────────── DnB ──────────────────────────────────────────────
    # Straight 16ths, 170 BPM — Reese bass is the loudest element.
    'dnb': {
        'drums':      dict(vel_min=85, vel_max=112, gain_db=+1.0, pan=  0, swing_pct=50.0, vel_curve='accent_1'),
        'bass':       dict(vel_min=92, vel_max=118, gain_db=-2.0, pan=  0, swing_pct=50.0),
        'chords':     dict(vel_min=40, vel_max=72,  gain_db=-9.0, pan=  0),
        'lead':       dict(vel_min=65, vel_max=88,  gain_db=-5.0, pan=  0),
        'pad':        dict(vel_min=30, vel_max=65,  gain_db=-12.0,pan=  0),
        'arp':        dict(vel_min=58, vel_max=85,  gain_db=-8.0, pan=  0, swing_pct=50.0),
        'stabs':      dict(vel_min=72, vel_max=98,  gain_db=-6.0, pan=  0),
        'texture':    dict(vel_min=38, vel_max=70,  gain_db=-10.0,pan=  0),
        'fx':         dict(vel_min=50, vel_max=88,  gain_db=-8.0, pan=  0),
        'percussion': dict(vel_min=75, vel_max=105, gain_db=-5.0, pan=  0, swing_pct=50.0),
    },

    # ─────────────────────── PHONK ────────────────────────────────────────────
    # Straight or very light swing (51 %), dark and compressed, Memphis 808.
    'phonk': {
        'drums':      dict(vel_min=82, vel_max=112, gain_db= 0.0, pan=  0, swing_pct=51.0, vel_curve='accent_1'),
        'bass':       dict(vel_min=95, vel_max=122, gain_db=-3.0, pan=  0, swing_pct=51.0, timing_nudge_ms=-6.0),
        'chords':     dict(vel_min=38, vel_max=72,  gain_db=-9.0, pan=  0, vel_curve='accent_1_3'),
        'lead':       dict(vel_min=62, vel_max=85,  gain_db=-5.0, pan=  0),
        'pad':        dict(vel_min=28, vel_max=62,  gain_db=-13.0,pan=  0),
        'arp':        dict(vel_min=52, vel_max=78,  gain_db=-10.0,pan=  0, swing_pct=51.0),
        'stabs':      dict(vel_min=68, vel_max=95,  gain_db=-7.0, pan=  0),
        'texture':    dict(vel_min=35, vel_max=68,  gain_db=-11.0,pan=  0),
        'fx':         dict(vel_min=48, vel_max=88,  gain_db=-9.0, pan=  0),
        'percussion': dict(vel_min=72, vel_max=102, gain_db=-6.0, pan=  0, swing_pct=51.0),
    },

    # ─────────────────────── POP ──────────────────────────────────────────────
    # Light swing (51 %), bright and balanced — everything sits in a clear mix.
    'pop': {
        'drums':      dict(vel_min=78, vel_max=105, gain_db= 0.0, pan=  0, swing_pct=51.0, vel_curve='accent_1_3'),
        'bass':       dict(vel_min=80, vel_max=108, gain_db=-4.0, pan=  0, swing_pct=51.0, timing_nudge_ms=-5.0),
        'chords':     dict(vel_min=48, vel_max=78,  gain_db=-6.0, pan=  0, swing_pct=51.0, vel_curve='accent_1_3'),
        'lead':       dict(vel_min=70, vel_max=95,  gain_db=-3.0, pan=  0, swing_pct=51.0, vel_curve='crescendo'),
        'pad':        dict(vel_min=35, vel_max=68,  gain_db=-10.0,pan=  0),
        'arp':        dict(vel_min=55, vel_max=82,  gain_db=-8.0, pan=  0, swing_pct=51.0),
        'stabs':      dict(vel_min=68, vel_max=92,  gain_db=-6.0, pan=  0),
        'texture':    dict(vel_min=38, vel_max=72,  gain_db=-9.0, pan=  0),
        'fx':         dict(vel_min=48, vel_max=85,  gain_db=-8.0, pan=  0),
        'percussion': dict(vel_min=70, vel_max=100, gain_db=-5.0, pan=  0, swing_pct=51.0),
    },

    # ─────────────────────── J-POP ────────────────────────────────────────────
    # Light swing (51 %), melodic lead is the star, pads are soft and wide.
    'jpop': {
        'drums':      dict(vel_min=72, vel_max=100, gain_db=-1.0, pan=  0, swing_pct=51.0, vel_curve='accent_1_3'),
        'bass':       dict(vel_min=75, vel_max=100, gain_db=-5.0, pan=  0, swing_pct=51.0),
        'chords':     dict(vel_min=50, vel_max=80,  gain_db=-6.0, pan=  0, swing_pct=51.0, vel_curve='accent_1_3'),
        'lead':       dict(vel_min=72, vel_max=98,  gain_db=-2.0, pan=  0, swing_pct=51.0, vel_curve='crescendo'),
        'pad':        dict(vel_min=38, vel_max=72,  gain_db=-9.0, pan=  0),
        'arp':        dict(vel_min=58, vel_max=85,  gain_db=-7.0, pan=  0, swing_pct=51.0),
        'stabs':      dict(vel_min=65, vel_max=90,  gain_db=-6.0, pan=  0),
        'texture':    dict(vel_min=40, vel_max=72,  gain_db=-9.0, pan=  0),
        'fx':         dict(vel_min=48, vel_max=85,  gain_db=-8.0, pan=  0),
        'percussion': dict(vel_min=68, vel_max=98,  gain_db=-5.0, pan=  0, swing_pct=51.0),
    },

    # ─────────────────────── CINEMATIC ────────────────────────────────────────
    # Moderate swing (52 %), orchestral balance — wide dynamic range preserved.
    'cinematic': {
        'drums':      dict(vel_min=65, vel_max=105, gain_db=-1.0, pan=  0, swing_pct=52.0, vel_curve='accent_1'),
        'bass':       dict(vel_min=70, vel_max=100, gain_db=-5.0, pan=  0, swing_pct=52.0),
        'chords':     dict(vel_min=55, vel_max=88,  gain_db=-4.0, pan=  0, swing_pct=52.0, vel_curve='crescendo'),
        'lead':       dict(vel_min=68, vel_max=100, gain_db=-2.0, pan=  0, swing_pct=52.0, vel_curve='crescendo'),
        'pad':        dict(vel_min=42, vel_max=80,  gain_db=-7.0, pan=  0),
        'arp':        dict(vel_min=55, vel_max=85,  gain_db=-7.0, pan=  0, swing_pct=52.0),
        'stabs':      dict(vel_min=72, vel_max=100, gain_db=-5.0, pan=  0),
        'texture':    dict(vel_min=45, vel_max=78,  gain_db=-8.0, pan=  0),
        'fx':         dict(vel_min=50, vel_max=92,  gain_db=-7.0, pan=  0),
        'percussion': dict(vel_min=68, vel_max=100, gain_db=-5.0, pan=  0, swing_pct=52.0),
    },
}

# Fallback preset used when genre is unrecognised.
_DEFAULT_PRESET = 'pop'


class GroovePresetLibrary:
    """
    Provides theory-correct Tier-1 groove defaults for any recognised genre.

    Usage::

        lib = GroovePresetLibrary()
        settings = lib.get('trap')   # SongGrooveSettings with genre defaults
        genres   = lib.genre_list()  # list of available genre keys
    """

    def genre_list(self) -> list:
        """Return the list of genres with a registered preset."""
        return list(_PRESETS.keys())

    def get(self, genre: str) -> SongGrooveSettings:
        """
        Build a SongGrooveSettings populated with theory-correct defaults
        for *genre*.  Unrecognised genres fall back to 'pop'.
        """
        table = _PRESETS.get(genre, _PRESETS[_DEFAULT_PRESET])
        tracks = {}
        for track_key, overrides in table.items():
            tracks[track_key] = TrackGrooveSettings(**overrides)
        return SongGrooveSettings(tracks=tracks, apply_enabled=True)
