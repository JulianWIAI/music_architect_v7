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
        # Pass genre so GrooveProcessor can activate MicroTimingEngine grids
        # for any track the user has not manually configured in advanced mode.
        return SongGrooveSettings(tracks=tracks, apply_enabled=True, genre=genre)


# ── Named presets — multiple feels per genre ───────────────────────────────────
# Each genre has 3-5 named presets that differ in:
#   swing_pct    -- triplet feel (50=straight, 67=full triplet)
#   vel contrast -- ratio between accented and ghost notes
#   timing nudge -- bass/lead ahead of or behind the grid (ms)
#   humanize     -- timing jitter amount
#
# Music theory constraints:
#   * swing_pct must align with the subdivision grid (1/16 or 1/8 swing)
#   * bass timing nudge is negative (behind beat) for pocket; positive (ahead) for urgency
#   * velocity min/max defines dynamic range -- wider = more expressive

# Structure: {genre: {preset_name: {track: overrides}}}
# Each track override dict may contain any subset of TrackGrooveSettings fields.
# Fields not listed fall through to the base _PRESETS[genre] defaults.

_NAMED_PRESETS: Dict[str, Dict[str, Dict[str, dict]]] = {

    # ──────────────────────────── TRAP ────────────────────────────────────────
    'trap': {
        # Faithful reproduction of the base preset — serves as the reference.
        'Standard': {
            'drums': dict(swing_pct=50.0, vel_min=80, vel_max=110),
            'bass':  dict(timing_nudge_ms=-8.0, vel_min=90, vel_max=120),
        },
        # Slower, heavier feel: darker velocity window, bass pushed deeper into
        # the pocket, chords dialled back for a more menacing atmosphere.
        'Dark Memphis': {
            'drums':  dict(swing_pct=51.0, vel_min=75, vel_max=105),
            'bass':   dict(timing_nudge_ms=-12.0),
            'chords': dict(vel_min=30, vel_max=65),
        },
        # Lighter and more melodic: reduced velocities across the board and a
        # shallower bass nudge so the groove breathes rather than pounds.
        'Melodic Trap': {
            'drums': dict(swing_pct=50.0, vel_min=70, vel_max=95),
            'bass':  dict(timing_nudge_ms=-5.0),
            'lead':  dict(vel_min=70, vel_max=95),
        },
        # Extreme sub pocket — maximum bass behind-beat for that subsonic drag.
        'Phonk Trap': {
            'drums': dict(swing_pct=50.0),
            'bass':  dict(timing_nudge_ms=-15.0, vel_min=95, vel_max=125),
        },
    },

    # ──────────────────────────── TECHNO ──────────────────────────────────────
    'techno': {
        # Perfectly quantised grid, moderate velocity — hypnotic and repetitive.
        'Minimal': {
            'drums': dict(swing_pct=50.0, vel_min=85, vel_max=108),
            'bass':  dict(swing_pct=50.0, vel_min=82, vel_max=108),
        },
        # Maximum aggression: loud transients, tight grid, stabs present.
        'Hard Industrial': {
            'drums': dict(swing_pct=50.0, vel_min=95, vel_max=120),
            'bass':  dict(swing_pct=50.0, vel_min=90, vel_max=118),
            'stabs': dict(vel_min=80, vel_max=105),
        },
        # Slight swing from Detroit techno tradition; organic and warm.
        'Detroit': {
            'drums': dict(swing_pct=52.0, vel_min=80, vel_max=108),
            'bass':  dict(swing_pct=52.0, vel_min=80, vel_max=108),
        },
        # Wide-dynamic build: low peak velocity, pad buried for atmosphere.
        'Hypnotic': {
            'drums': dict(swing_pct=50.0, vel_min=80, vel_max=100),
            'bass':  dict(swing_pct=50.0, vel_min=78, vel_max=100),
            'pad':   dict(vel_min=35, vel_max=70),
        },
    },

    # ──────────────────────────── HOUSE ───────────────────────────────────────
    'house': {
        # Laidback feel: heavier swing, bass behind the beat, wide dynamics.
        'Deep Chill': {
            'drums': dict(swing_pct=54.0, vel_min=78, vel_max=105),
            'bass':  dict(swing_pct=54.0, timing_nudge_ms=-8.0, vel_min=78, vel_max=105),
        },
        # Tighter and more DJ-friendly: minimal swing, punchy stabs.
        'Tech House': {
            'drums': dict(swing_pct=51.0, vel_min=88, vel_max=115),
            'stabs': dict(vel_min=75, vel_max=100),
        },
        # Full classic house feel: moderate swing, lush chords, arpeggios.
        'Classic House': {
            'drums':  dict(swing_pct=53.0, vel_min=85, vel_max=112),
            'chords': dict(vel_min=50, vel_max=85),
            'arp':    dict(vel_min=60, vel_max=88),
        },
    },

    # ──────────────────────────── HIP-HOP ─────────────────────────────────────
    'hiphop': {
        # Heavy triplet swing, bass deep in the pocket — classic boom bap.
        'Boom Bap': {
            'drums': dict(swing_pct=55.0, vel_min=75, vel_max=108),
            'bass':  dict(swing_pct=55.0, timing_nudge_ms=-12.0),
        },
        # Loose vintage feel: moderate swing, lower velocities, timing jitter.
        'Lo-Fi Chill': {
            'drums': dict(swing_pct=53.0, vel_min=65, vel_max=95,
                          timing_humanize_ms=10.0),
        },
        # Contemporary production: straight grid, tight bass nudge, punchy.
        'Modern Rap': {
            'drums': dict(swing_pct=50.0, vel_min=80, vel_max=112),
            'bass':  dict(timing_nudge_ms=-6.0),
        },
    },

    # ──────────────────────────── PHONK ───────────────────────────────────────
    'phonk': {
        # Faithful to the base preset — the classic dark drift.
        'Classic Drift': {
            'drums': dict(swing_pct=51.0, vel_min=82, vel_max=112),
        },
        # Brazilian rave phonk: louder, heavier sub, straight grid.
        'Brazilian Rave': {
            'drums': dict(swing_pct=50.0, vel_min=92, vel_max=118),
            'bass':  dict(vel_min=100, vel_max=125),
        },
        # Slowed + chopped aesthetic: mild swing, extreme bass pocket delay.
        'Slowed Chopped': {
            'drums': dict(swing_pct=52.0, vel_min=70, vel_max=100),
            'bass':  dict(timing_nudge_ms=-18.0),
        },
    },

    # ──────────────────────────── EDM ─────────────────────────────────────────
    'edm': {
        # Festival-ready: full energy, bright lead pushed to the front.
        'Festival': {
            'drums': dict(swing_pct=50.0, vel_min=90, vel_max=118),
            'lead':  dict(vel_min=75, vel_max=100),
        },
        # Future bass: slight swing, melodic pads create the wash.
        'Future Bass': {
            'drums': dict(swing_pct=52.0, vel_min=82, vel_max=108),
            'pad':   dict(vel_min=45, vel_max=78),
        },
        # Progressive: straight grid, structured arpeggio motion.
        'Progressive': {
            'drums': dict(swing_pct=50.0, vel_min=85, vel_max=112),
            'arp':   dict(vel_min=65, vel_max=92),
        },
    },

    # ──────────────────────────── POP ─────────────────────────────────────────
    'pop': {
        # Polished radio sound: light swing, bright lead.
        'Radio Hit': {
            'drums': dict(swing_pct=51.0, vel_min=78, vel_max=105),
            'lead':  dict(vel_min=72, vel_max=98),
        },
        # Indie feel: more swing, lower velocities, subtle timing jitter.
        'Indie': {
            'drums': dict(swing_pct=52.0, vel_min=68, vel_max=95,
                          timing_humanize_ms=8.0),
        },
        # Uptempo dance pop: straight grid, energetic arpeggio.
        'Dance Pop': {
            'drums': dict(swing_pct=50.0, vel_min=85, vel_max=112),
            'arp':   dict(vel_min=60, vel_max=88),
        },
    },
}


class NamedGroovePresetLibrary:
    """
    Provides multiple named groove presets per genre.

    Each named preset stores only the track-level parameters that differ from
    the genre's base default (held in _PRESETS).  When building a
    SongGrooveSettings, the named overrides are merged on top of the base so
    that every track always receives sensible genre-correct values even if the
    named preset does not mention it.

    Usage::

        lib = NamedGroovePresetLibrary()
        names   = lib.genre_names('trap')        # ['Dark Memphis', 'Melodic Trap', ...]
        settings = lib.get_named('trap', 'Dark Memphis')   # SongGrooveSettings
        genres  = lib.all_genres()               # list of genres with named presets
    """

    def genre_names(self, genre: str) -> list:
        """
        Return the available named preset names for *genre*, sorted
        alphabetically.  Returns an empty list if *genre* has no named
        presets.
        """
        return sorted(_NAMED_PRESETS.get(genre, {}).keys())

    def all_genres(self) -> list:
        """Return the list of genres that have at least one named preset."""
        return sorted(_NAMED_PRESETS.keys())

    def get_named(self, genre: str, preset_name: str) -> SongGrooveSettings:
        """
        Build a SongGrooveSettings for *genre* / *preset_name*.

        Merge strategy
        --------------
        1. Start from the base genre defaults in _PRESETS (or _DEFAULT_PRESET
           if the genre is not in _PRESETS).
        2. Layer the named preset's per-track overrides on top — named values
           always win over base values.
        3. Construct one TrackGrooveSettings per merged track dict.

        Falls back gracefully:
          - Unknown genre   -> uses _DEFAULT_PRESET base with no overrides.
          - Unknown preset  -> uses the base genre defaults with no overrides.
        """
        # 1. Fetch the base genre table (a dict of {track: {field: value}}).
        base_table: Dict[str, dict] = _PRESETS.get(
            genre, _PRESETS[_DEFAULT_PRESET]
        )

        # 2. Fetch the named preset's override table (may be empty).
        named_table: Dict[str, dict] = (
            _NAMED_PRESETS.get(genre, {}).get(preset_name, {})
        )

        # 3. Build the merged per-track dicts.
        #    We iterate over the union of keys from both tables so that tracks
        #    only present in the named override are also included.
        all_track_keys = set(base_table.keys()) | set(named_table.keys())
        tracks = {}
        for track_key in all_track_keys:
            merged: dict = {}
            # Base values first
            if track_key in base_table:
                merged.update(base_table[track_key])
            # Named overrides win
            if track_key in named_table:
                merged.update(named_table[track_key])
            tracks[track_key] = TrackGrooveSettings(**merged)

        return SongGrooveSettings(tracks=tracks, apply_enabled=True, genre=genre)
