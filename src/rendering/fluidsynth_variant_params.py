"""
src.rendering.fluidsynth_variant_params
-----------------------------------------
Maps (genre, variant_id) → FluidSynth synthesiser parameters so that the
BRIGHT / NEUTRAL / DARK preview sounds genre-appropriate, not just a uniform
reverb sweep.

Design rationale
----------------
Each genre has a distinct acoustic signature in commercial productions:

  trap / hiphop   — dry booth (BRIGHT) through cavernous urban space (DARK)
  pop / jpop      — tight studio gloss (BRIGHT) through warm melancholy (DARK)
  edm / house     — club-ready punch (BRIGHT) through underground warehouse (DARK)
  techno          — clinical cold room (BRIGHT) through Berlin cathedral (DARK)
  dnb             — liquid clarity (BRIGHT) through neurofunk dark box (DARK)
  phonk           — lo-fi close (BRIGHT) through maximum distorted cave (DARK)
  cinematic       — bright hall (BRIGHT) through cathedral darkness (DARK)
  classical       — recital room (BRIGHT) through cathedral organ space (DARK)

Parameters
----------
synth.reverb.room-size (0-1) : decay time proxy.  0=dead booth, 1=cathedral.
synth.reverb.damp      (0-1) : HF absorption.  0=bright/airy, 1=dark/muffled.
synth.reverb.width     (0-1) : stereo spread of reverb tail.
synth.reverb.level     (0-1) : wet/dry balance.  Primary contrast axis.
synth.chorus.nr              : number of chorus voices (int).
synth.chorus.level           : chorus amplitude.
synth.chorus.speed           : LFO speed (Hz).
synth.chorus.depth           : pitch modulation depth (ms).
gain                         : FluidSynth -g master gain.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Per-genre, per-variant parameter tables
# 'gain' → FluidSynth -g flag.  Everything else → -o key=value overrides.
# ---------------------------------------------------------------------------

_GENRE_PARAMS: Dict[str, Dict[str, dict]] = {

    # ── Trap ─────────────────────────────────────────────────────────────
    'trap': {
        'bright': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.08, 'synth.reverb.damp': 0.01,
            'synth.reverb.width':     0.95, 'synth.reverb.level': 0.15,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 3, 'synth.chorus.level': 1.80,
            'synth.chorus.speed': 0.45, 'synth.chorus.depth': 3.0,
            'gain': 1.00,
        },
        'neutral': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.45, 'synth.reverb.damp': 0.25,
            'synth.reverb.width':     0.60, 'synth.reverb.level': 0.60,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 3, 'synth.chorus.level': 1.60,
            'synth.chorus.speed': 0.30, 'synth.chorus.depth': 6.0,
            'gain': 0.82,
        },
        'dark': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.90, 'synth.reverb.damp': 0.92,
            'synth.reverb.width':     0.20, 'synth.reverb.level': 0.90,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 2, 'synth.chorus.level': 0.90,
            'synth.chorus.speed': 0.15, 'synth.chorus.depth': 12.0,
            'gain': 0.65,
        },
    },

    # ── Hip-hop ───────────────────────────────────────────────────────────
    'hiphop': {
        'bright': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.20, 'synth.reverb.damp': 0.05,
            'synth.reverb.width':     0.90, 'synth.reverb.level': 0.30,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 4, 'synth.chorus.level': 2.00,
            'synth.chorus.speed': 0.42, 'synth.chorus.depth': 4.0,
            'gain': 0.95,
        },
        'neutral': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.50, 'synth.reverb.damp': 0.35,
            'synth.reverb.width':     0.55, 'synth.reverb.level': 0.65,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 3, 'synth.chorus.level': 1.70,
            'synth.chorus.speed': 0.30, 'synth.chorus.depth': 7.0,
            'gain': 0.80,
        },
        'dark': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.80, 'synth.reverb.damp': 0.85,
            'synth.reverb.width':     0.25, 'synth.reverb.level': 0.88,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 2, 'synth.chorus.level': 1.00,
            'synth.chorus.speed': 0.18, 'synth.chorus.depth': 13.0,
            'gain': 0.68,
        },
    },

    # ── Pop ───────────────────────────────────────────────────────────────
    'pop': {
        'bright': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.15, 'synth.reverb.damp': 0.02,
            'synth.reverb.width':     0.98, 'synth.reverb.level': 0.25,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 5, 'synth.chorus.level': 2.50,
            'synth.chorus.speed': 0.50, 'synth.chorus.depth': 3.0,
            'gain': 0.98,
        },
        'neutral': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.45, 'synth.reverb.damp': 0.20,
            'synth.reverb.width':     0.60, 'synth.reverb.level': 0.60,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 3, 'synth.chorus.level': 1.80,
            'synth.chorus.speed': 0.32, 'synth.chorus.depth': 6.5,
            'gain': 0.82,
        },
        'dark': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.70, 'synth.reverb.damp': 0.70,
            'synth.reverb.width':     0.35, 'synth.reverb.level': 0.82,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 2, 'synth.chorus.level': 1.10,
            'synth.chorus.speed': 0.20, 'synth.chorus.depth': 11.0,
            'gain': 0.70,
        },
    },

    # ── EDM ───────────────────────────────────────────────────────────────
    'edm': {
        'bright': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.25, 'synth.reverb.damp': 0.02,
            'synth.reverb.width':     0.99, 'synth.reverb.level': 0.35,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 5, 'synth.chorus.level': 2.80,
            'synth.chorus.speed': 0.55, 'synth.chorus.depth': 4.0,
            'gain': 0.95,
        },
        'neutral': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.55, 'synth.reverb.damp': 0.30,
            'synth.reverb.width':     0.65, 'synth.reverb.level': 0.65,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 3, 'synth.chorus.level': 1.80,
            'synth.chorus.speed': 0.30, 'synth.chorus.depth': 7.0,
            'gain': 0.80,
        },
        'dark': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.88, 'synth.reverb.damp': 0.90,
            'synth.reverb.width':     0.20, 'synth.reverb.level': 0.92,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 2, 'synth.chorus.level': 0.80,
            'synth.chorus.speed': 0.14, 'synth.chorus.depth': 14.0,
            'gain': 0.65,
        },
    },

    # ── House ─────────────────────────────────────────────────────────────
    'house': {
        'bright': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.20, 'synth.reverb.damp': 0.05,
            'synth.reverb.width':     0.92, 'synth.reverb.level': 0.30,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 4, 'synth.chorus.level': 2.20,
            'synth.chorus.speed': 0.46, 'synth.chorus.depth': 3.5,
            'gain': 0.96,
        },
        'neutral': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.50, 'synth.reverb.damp': 0.30,
            'synth.reverb.width':     0.55, 'synth.reverb.level': 0.65,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 3, 'synth.chorus.level': 1.80,
            'synth.chorus.speed': 0.30, 'synth.chorus.depth': 7.0,
            'gain': 0.80,
        },
        'dark': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.78, 'synth.reverb.damp': 0.78,
            'synth.reverb.width':     0.28, 'synth.reverb.level': 0.85,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 2, 'synth.chorus.level': 1.00,
            'synth.chorus.speed': 0.17, 'synth.chorus.depth': 12.0,
            'gain': 0.70,
        },
    },

    # ── J-Pop ─────────────────────────────────────────────────────────────
    'jpop': {
        'bright': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.12, 'synth.reverb.damp': 0.02,
            'synth.reverb.width':     0.99, 'synth.reverb.level': 0.20,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 5, 'synth.chorus.level': 2.80,
            'synth.chorus.speed': 0.55, 'synth.chorus.depth': 2.5,
            'gain': 1.00,
        },
        'neutral': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.40, 'synth.reverb.damp': 0.20,
            'synth.reverb.width':     0.65, 'synth.reverb.level': 0.55,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 3, 'synth.chorus.level': 1.90,
            'synth.chorus.speed': 0.35, 'synth.chorus.depth': 6.0,
            'gain': 0.82,
        },
        'dark': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.68, 'synth.reverb.damp': 0.65,
            'synth.reverb.width':     0.35, 'synth.reverb.level': 0.80,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 2, 'synth.chorus.level': 1.10,
            'synth.chorus.speed': 0.20, 'synth.chorus.depth': 10.5,
            'gain': 0.72,
        },
    },

    # ── Techno ────────────────────────────────────────────────────────────
    'techno': {
        'bright': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.18, 'synth.reverb.damp': 0.01,
            'synth.reverb.width':     0.80, 'synth.reverb.level': 0.25,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 2, 'synth.chorus.level': 1.20,
            'synth.chorus.speed': 0.35, 'synth.chorus.depth': 2.0,
            'gain': 0.95,
        },
        'neutral': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.60, 'synth.reverb.damp': 0.40,
            'synth.reverb.width':     0.50, 'synth.reverb.level': 0.70,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 3, 'synth.chorus.level': 1.60,
            'synth.chorus.speed': 0.28, 'synth.chorus.depth': 7.5,
            'gain': 0.78,
        },
        'dark': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.94, 'synth.reverb.damp': 0.88,
            'synth.reverb.width':     0.15, 'synth.reverb.level': 0.94,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 2, 'synth.chorus.level': 0.70,
            'synth.chorus.speed': 0.12, 'synth.chorus.depth': 15.0,
            'gain': 0.62,
        },
    },

    # ── Drum & Bass ───────────────────────────────────────────────────────
    'dnb': {
        'bright': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.22, 'synth.reverb.damp': 0.05,
            'synth.reverb.width':     0.90, 'synth.reverb.level': 0.35,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 4, 'synth.chorus.level': 2.00,
            'synth.chorus.speed': 0.48, 'synth.chorus.depth': 4.5,
            'gain': 0.94,
        },
        'neutral': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.50, 'synth.reverb.damp': 0.35,
            'synth.reverb.width':     0.55, 'synth.reverb.level': 0.65,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 3, 'synth.chorus.level': 1.70,
            'synth.chorus.speed': 0.30, 'synth.chorus.depth': 7.0,
            'gain': 0.80,
        },
        'dark': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.85, 'synth.reverb.damp': 0.92,
            'synth.reverb.width':     0.22, 'synth.reverb.level': 0.90,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 2, 'synth.chorus.level': 0.85,
            'synth.chorus.speed': 0.15, 'synth.chorus.depth': 13.5,
            'gain': 0.66,
        },
    },

    # ── Phonk ─────────────────────────────────────────────────────────────
    'phonk': {
        'bright': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.10, 'synth.reverb.damp': 0.05,
            'synth.reverb.width':     0.70, 'synth.reverb.level': 0.15,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 2, 'synth.chorus.level': 1.40,
            'synth.chorus.speed': 0.35, 'synth.chorus.depth': 3.0,
            'gain': 0.95,
        },
        'neutral': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.55, 'synth.reverb.damp': 0.55,
            'synth.reverb.width':     0.40, 'synth.reverb.level': 0.72,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 2, 'synth.chorus.level': 1.30,
            'synth.chorus.speed': 0.22, 'synth.chorus.depth': 8.0,
            'gain': 0.75,
        },
        'dark': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.95, 'synth.reverb.damp': 0.97,
            'synth.reverb.width':     0.15, 'synth.reverb.level': 0.95,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 2, 'synth.chorus.level': 0.70,
            'synth.chorus.speed': 0.12, 'synth.chorus.depth': 14.0,
            'gain': 0.60,
        },
    },

    # ── Cinematic ─────────────────────────────────────────────────────────
    'cinematic': {
        'bright': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.60, 'synth.reverb.damp': 0.10,
            'synth.reverb.width':     0.90, 'synth.reverb.level': 0.65,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 3, 'synth.chorus.level': 1.50,
            'synth.chorus.speed': 0.25, 'synth.chorus.depth': 5.0,
            'gain': 0.88,
        },
        'neutral': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.75, 'synth.reverb.damp': 0.35,
            'synth.reverb.width':     0.70, 'synth.reverb.level': 0.78,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 3, 'synth.chorus.level': 1.40,
            'synth.chorus.speed': 0.22, 'synth.chorus.depth': 7.0,
            'gain': 0.80,
        },
        'dark': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.98, 'synth.reverb.damp': 0.80,
            'synth.reverb.width':     0.40, 'synth.reverb.level': 0.95,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 2, 'synth.chorus.level': 1.00,
            'synth.chorus.speed': 0.15, 'synth.chorus.depth': 12.0,
            'gain': 0.68,
        },
    },

    # ── Classical ─────────────────────────────────────────────────────────
    'classical': {
        'bright': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.45, 'synth.reverb.damp': 0.10,
            'synth.reverb.width':     0.85, 'synth.reverb.level': 0.55,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 3, 'synth.chorus.level': 1.30,
            'synth.chorus.speed': 0.22, 'synth.chorus.depth': 4.0,
            'gain': 0.90,
        },
        'neutral': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.72, 'synth.reverb.damp': 0.30,
            'synth.reverb.width':     0.75, 'synth.reverb.level': 0.75,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 3, 'synth.chorus.level': 1.30,
            'synth.chorus.speed': 0.20, 'synth.chorus.depth': 6.5,
            'gain': 0.80,
        },
        'dark': {
            'synth.reverb.active':    1,
            'synth.reverb.room-size': 0.98, 'synth.reverb.damp': 0.75,
            'synth.reverb.width':     0.50, 'synth.reverb.level': 0.95,
            'synth.chorus.active':    1,
            'synth.chorus.nr': 2, 'synth.chorus.level': 1.00,
            'synth.chorus.speed': 0.15, 'synth.chorus.depth': 11.0,
            'gain': 0.68,
        },
    },
}

# Generic fallback used for any genre not in _GENRE_PARAMS
_FALLBACK: Dict[str, dict] = {
    'bright': {
        'synth.reverb.active': 1,
        'synth.reverb.room-size': 0.12, 'synth.reverb.damp': 0.02,
        'synth.reverb.width': 0.95,     'synth.reverb.level': 0.20,
        'synth.chorus.active': 1,
        'synth.chorus.nr': 5,  'synth.chorus.level': 2.50,
        'synth.chorus.speed': 0.50,     'synth.chorus.depth': 3.0,
        'gain': 0.95,
    },
    'neutral': {
        'synth.reverb.active': 1,
        'synth.reverb.room-size': 0.50, 'synth.reverb.damp': 0.30,
        'synth.reverb.width': 0.50,     'synth.reverb.level': 0.65,
        'synth.chorus.active': 1,
        'synth.chorus.nr': 3,  'synth.chorus.level': 1.80,
        'synth.chorus.speed': 0.30,     'synth.chorus.depth': 7.0,
        'gain': 0.80,
    },
    'dark': {
        'synth.reverb.active': 1,
        'synth.reverb.room-size': 0.96, 'synth.reverb.damp': 0.95,
        'synth.reverb.width': 0.20,     'synth.reverb.level': 0.96,
        'synth.chorus.active': 1,
        'synth.chorus.nr': 2,  'synth.chorus.level': 1.00,
        'synth.chorus.speed': 0.15,     'synth.chorus.depth': 14.0,
        'gain': 0.68,
    },
}


def build_fluidsynth_args(
    variant_id: str,
    genre: str = '',
    override_mode: bool = False,
) -> Tuple[List[str], float]:
    """
    Return (option_flags, gain) for *variant_id* and *genre*.

    option_flags is a flat list of '-o', 'key=value' pairs ready to be
    spliced into the FluidSynth subprocess command before the positional
    arguments (sf2 path and MIDI path).

    gain is the float for the -g master-gain flag.

    Parameters
    ----------
    variant_id : str
        Timbral variant ('bright', 'neutral', 'dark').
    genre : str
        Genre key used to select the appropriate parameter table.
    override_mode : bool
        True when the user has loaded a custom override SoundFont (e.g. a
        game SoundFont such as Mario).  Game SoundFonts have their samples
        mastered hot internally, so the normal gain values (0.80–1.00) cause
        clipping.  High chorus levels (up to 2.80) also cause harsh beating
        with square/triangle waves.  In override mode:
          - gain is capped at 0.50 (avoids output clipping)
          - chorus.level is capped at 0.60 (removes harsh intermodulation)
          - reverb.level is capped at 0.55 (prevents muddy wash)

    Unknown variant_id falls back to 'neutral'.
    Unknown genre uses the generic fallback table.
    """
    genre_table = _GENRE_PARAMS.get(genre, _FALLBACK)
    params      = genre_table.get(variant_id, genre_table.get('neutral', _FALLBACK['neutral']))
    gain        = float(params.get('gain', 0.80))

    if override_mode:
        # Custom/game SoundFonts clip at full gain — keep headroom.
        gain = min(gain, 0.50)

    flags: List[str] = []
    for key, value in params.items():
        if key == 'gain':
            continue

        # Tame chorus and reverb for custom SoundFonts that are already
        # heavily processed or have strong built-in timbres.
        if override_mode:
            if key == 'synth.chorus.level':
                value = min(float(value), 0.60)
            elif key == 'synth.reverb.level':
                value = min(float(value), 0.55)

        if isinstance(value, int):
            flags += ['-o', f'{key}={value}']
        else:
            flags += ['-o', f'{key}={value:.3f}']

    return flags, gain
