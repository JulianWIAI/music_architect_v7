"""
src.rendering.fluidsynth_variant_params
-----------------------------------------
Maps BRIGHT / NEUTRAL / DARK variant IDs to FluidSynth synthesiser
parameters that audibly shift the timbre toward the variant's character.

All parameters are passed to FluidSynth via the -o flag, which overrides
built-in defaults at render time without editing any config file.

Design intent — maximise audible contrast
------------------------------------------
Parameters are pushed to near-extremes so the three variants are
unmistakably different without post-processing:

  BRIGHT  Very dry (level 0.20), tiny room (size 0.12), no HF absorption
          → instruments sound close, present, almost no room ambience.
          Fast chorus shimmer adds air without smearing transients.

  NEUTRAL Moderate room (size 0.50), half-wet (level 0.65), light damping
          → reference balance; sounds like a treated studio room.

  DARK    Fully wet (level 0.96), cathedral-size room (size 0.96),
          heavy HF absorption (damp 0.95) → instruments sit far back
          inside a cavernous, muffled space; slow deep chorus adds thickness.

synth.reverb.damp (0.0–1.0)
    High-frequency absorption in the reverb tail.
    0.0 = bright, airy tail.  1.0 = dark, muffled tail.

synth.reverb.room-size (0.0–1.0)
    Reverb decay time proxy.  0.0 = dead booth.  1.0 = cathedral.

synth.reverb.level (0.0–1.0)
    Wet/dry balance.  The primary contrast knob: 0.20 (BRIGHT) vs
    0.96 (DARK) is a 14 dB swing in wet signal — easily audible.

synth.reverb.width (0.0–1.0)
    Stereo spread of the reverb tail.  Wider = more spatial on BRIGHT.

synth.chorus.depth / speed
    Higher depth + slower speed = warm, thick pitch modulation (DARK).
    Lower depth + faster speed  = subtle crisp shimmer (BRIGHT).

gain
    BRIGHT raised to 0.95 to compensate for the dry mix sounding quieter.
    DARK lowered to 0.68; the very wet reverb adds perceived loudness.
"""

from __future__ import annotations

from typing import List, Tuple

# ── Per-variant parameter tables ──────────────────────────────────────────────
# 'gain' maps to the FluidSynth -g flag.
# All other keys map to -o key=value overrides.

_PARAMS: dict = {
    'bright': {
        'synth.reverb.active':    1,      # ensure reverb unit is on
        'synth.reverb.room-size': 0.12,   # tiny booth → almost no tail
        'synth.reverb.damp':      0.02,   # near-zero HF absorption → airy tail
        'synth.reverb.width':     0.95,   # maximum stereo spread
        'synth.reverb.level':     0.20,   # very dry → transients up front
        'synth.chorus.active':    1,      # ensure chorus unit is on
        'synth.chorus.nr':        5,      # more voices → sparkly shimmer
        'synth.chorus.level':     2.50,
        'synth.chorus.speed':     0.50,   # fast LFO → crisp movement
        'synth.chorus.depth':     3.0,    # shallow depth → subtle, not seasick
        'gain': 0.95,                     # louder to compensate for dry mix
    },
    'neutral': {
        'synth.reverb.active':    1,
        'synth.reverb.room-size': 0.50,   # mid-size treated room
        'synth.reverb.damp':      0.30,
        'synth.reverb.width':     0.50,
        'synth.reverb.level':     0.65,
        'synth.chorus.active':    1,
        'synth.chorus.nr':        3,
        'synth.chorus.level':     1.80,
        'synth.chorus.speed':     0.30,
        'synth.chorus.depth':     7.0,
        'gain': 0.80,
    },
    'dark': {
        'synth.reverb.active':    1,
        'synth.reverb.room-size': 0.96,   # cathedral → very long tail
        'synth.reverb.damp':      0.95,   # maximum HF absorption → muffled
        'synth.reverb.width':     0.20,   # narrow → instruments buried in mono wash
        'synth.reverb.level':     0.96,   # almost fully wet → deep in the room
        'synth.chorus.active':    1,
        'synth.chorus.nr':        2,      # fewer voices → thick, slow throb
        'synth.chorus.level':     1.00,
        'synth.chorus.speed':     0.15,   # very slow LFO → warm, heavy movement
        'synth.chorus.depth':     14.0,   # deep pitch modulation
        'gain': 0.68,                     # pull back; wet reverb adds loudness
    },
}


def build_fluidsynth_args(variant_id: str) -> Tuple[List[str], float]:
    """
    Return (option_flags, gain) for *variant_id*.

    option_flags is a flat list of '-o', 'key=value' pairs ready to be
    spliced into the FluidSynth subprocess command before the positional
    arguments (sf2 path and MIDI path).

    gain is the float for the -g master-gain flag.

    An unrecognised variant_id falls back to 'neutral'.
    """
    params = _PARAMS.get(variant_id, _PARAMS['neutral'])
    gain   = float(params.get('gain', 0.80))

    flags: List[str] = []
    for key, value in params.items():
        if key == 'gain':
            continue
        # chorus.nr is an integer; all others are floats
        if isinstance(value, int):
            flags += ['-o', f'{key}={value}']
        else:
            flags += ['-o', f'{key}={value:.3f}']

    return flags, gain
