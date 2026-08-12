"""
src.composition.gm_descriptions
--------------------------------
Pedagogical one-line descriptions for all 128 General MIDI programs.

Purpose
-------
Newcomers browsing the GM instrument list see names like "Sawtooth Lead"
or "Polysynth" that tell them little about the actual sound.  These
descriptions add three pieces of information that help a student find an
equivalent in any DAW or hardware synth:

  1. Sound colour   — bright / dark / warm / cold / metallic / woody
  2. Excitation type — struck / bowed / blown / plucked / synthesized
  3. Character / context — electronic / organic / jazz / classical /
                           aggressive / gentle / cinematic / retro

Format
------
Each description is a short string (≤ 68 chars) following the pattern:
    "Colour + excitation · character — context hint"

Public API
----------
GM_DESCRIPTIONS : Dict[int, str]
    Maps GM program number (0-127) to its description.

get_description(program) → str
    Returns the description, or a generic fallback for unknown programs.
"""

from __future__ import annotations
from typing import Dict

# ── Full 128-program description table ────────────────────────────────────────
# Organised by GM family (comments mark family boundaries).

GM_DESCRIPTIONS: Dict[int, str] = {

    # ── Piano (0 – 7) ─────────────────────────────────────────────────────────
    0:  "Warm struck strings · acoustic, full-bodied, natural, universally known",
    1:  "Brighter grand · less resonance, crisper attack, acoustic upright feel",
    2:  "Bell-like electric piano · metallic shimmer, 70s funk, analogue warmth",
    3:  "Vintage electric piano · soulful, slightly gritty, jazzy, Wurlitzer-like",
    4:  "Clean electric piano · digital clarity, pop/soul icon (Rhodes-style)",
    5:  "FM electric piano · punchy, glassy, 80s digital, slightly cold",
    6:  "Harpsichord · baroque, plucked string, thin and bright, very historical",
    7:  "Clavinet · funky, percussive, wah-like attack — Stevie Wonder classic",

    # ── Chromatic Percussion (8 – 15) ─────────────────────────────────────────
    8:  "Celesta · tiny bell-box, delicate, fairy-tale, light and airy, pure",
    9:  "Glockenspiel · bright metallic bell, sparkly, childlike, short decay",
    10: "Music box · miniature, very delicate, nostalgic toy sound, faint",
    11: "Vibraphone · smooth metallic sustain, jazz icon, mellow, gentle vibrato",
    12: "Marimba · wooden struck bars, warm, tropical, flowing, organic texture",
    13: "Xylophone · crisp wooden attack, brighter than marimba, staccato feel",
    14: "Tubular bells · orchestral resonance, ceremonial, church-like, deep",
    15: "Dulcimer · Appalachian folk, plucked metal strings, earthy, vintage",

    # ── Organ (16 – 23) ───────────────────────────────────────────────────────
    16: "Hammond organ · warm drawbars, Leslie-speaker wobble, rock / jazz soul",
    17: "Percussive organ · tighter attack than Hammond, punchy, less sustain",
    18: "Rock organ · aggressive Hammond, overdriven edge, stadium-rock energy",
    19: "Church pipe organ · grand, sacred, massive implied reverb, full spectrum",
    20: "Reed organ · reedy, accordion-like, vintage, slightly nasal mid-heavy",
    21: "Accordion · French café, reedy push-pull bellows, folk, very organic",
    22: "Harmonica · bluesy breath reed, American roots, organic, expressive",
    23: "Tango accordion · dramatic, darker than regular accordion, Latin dance",

    # ── Guitar (24 – 31) ──────────────────────────────────────────────────────
    24: "Nylon string guitar · soft, warm, classical / bossa nova, very organic",
    25: "Steel string guitar · bright acoustic, folk / singer-songwriter, open",
    26: "Jazz guitar · clean hollow-body electric, warm, mellow, short decay",
    27: "Clean electric guitar · crystal clear, no distortion, pop / funk rhythm",
    28: "Muted electric guitar · palm-muted, chunky percussive attack, funky",
    29: "Overdrive guitar · warm crunch, classic rock, slight breakup, medium gain",
    30: "Distorted guitar · heavy saturated tone, metal / rock, aggressive",
    31: "Guitar harmonics · ethereal bell-overtone, glassy, sparse, very pure",

    # ── Bass (32 – 39) ────────────────────────────────────────────────────────
    32: "Acoustic upright bass · warm, round, jazz / acoustic, very organic",
    33: "Electric finger bass · smooth round low end, warm, classic pop / rock",
    34: "Electric pick bass · sharper attack, punchy, rock, defined transient",
    35: "Fretless bass · smooth slides, no fret noise, Jaco-style, fluid and jazzy",
    36: "Slap bass 1 · thumb-pop technique, funky, bright transient, R&B / funk",
    37: "Slap bass 2 · brighter pop-slap, tight and rhythmic, punchier pop",
    38: "Synth bass 1 · smooth subby electronic bass, analog warmth, no breath",
    39: "Synth bass 2 · brighter synth bass, more bite, electronic / house / dance",

    # ── Strings (40 – 47) ─────────────────────────────────────────────────────
    40: "Violin · bright bowed string, expressive, natural, classical / cinematic",
    41: "Viola · darker than violin, mid-register bowed, warmer and fuller color",
    42: "Cello · deep rich bowed string, emotional, lower register, very expressive",
    43: "Contrabass · very deep bowed string, orchestral foundation, dark",
    44: "Tremolo strings · fast bowing shimmer, tense, dramatic suspense builder",
    45: "Pizzicato strings · plucked strings, light bouncy feel, delicate staccato",
    46: "Orchestral harp · flowing glissandos, shimmering, fairy-tale, ethereal",
    47: "Timpani · deep orchestral drum, booming impact, cinematic, percussive",

    # ── Ensemble (48 – 55) ────────────────────────────────────────────────────
    48: "String ensemble 1 · full lush strings, warm, orchestral pad, cinematic",
    49: "String ensemble 2 · slower attack strings, softer, more atmospheric",
    50: "Synth strings 1 · electronic strings imitation, 80s texture, cold warmth",
    51: "Synth strings 2 · smoother synth strings, pad-like, background texture",
    52: "Choir Aahs · human choir, warm vowel blend, sacred, wide and organic",
    53: "Voice Oohs · breathy vowel texture, ethereal, ghost-like, floating",
    54: "Synth voice · robotic pitch-shifted vocal, electronic, eerie, uncanny",
    55: "Orchestra hit · dramatic full-band stab, cinematic impact, iconic 80s/90s",

    # ── Brass (56 – 63) ───────────────────────────────────────────────────────
    56: "Trumpet · bright piercing brass, fanfare, punchy transient, jazz / soul",
    57: "Trombone · full slide brass, lower than trumpet, smooth or growling",
    58: "Tuba · very deep round brass, heavy, sub-register, orchestral foundation",
    59: "Muted trumpet · nasal buzzy hat-mute, intimate jazz, talking quality",
    60: "French horn · warm round brass, heroic, orchestral, darker than trumpet",
    61: "Brass section · full band brass, punchy ensemble, soul / funk / orchestral",
    62: "Synth brass 1 · electronic brass, 80s metallic attack, artificial punch",
    63: "Synth brass 2 · softer synth brass, rounder attack, analogue-warm",

    # ── Reed (64 – 71) ────────────────────────────────────────────────────────
    64: "Soprano saxophone · bright nasal reed, highest sax, jazzy, emotional",
    65: "Alto saxophone · brighter sax, lighter than tenor, jazz / pop / R&B",
    66: "Tenor saxophone · rich warm reed, iconic jazz / rock sax, slightly raspy",
    67: "Baritone saxophone · deep beefy reed, dark low register, full body",
    68: "Oboe · nasal thin reed, classical orchestra, slightly melancholic",
    69: "English horn · darker oboe, lower, melancholic depth, cinematic",
    70: "Bassoon · deep wooden reed, classical, low register, slightly buzzy",
    71: "Clarinet · smooth warm reed, classical / jazz, wide range, pure tone",

    # ── Pipe (72 – 79) ────────────────────────────────────────────────────────
    72: "Piccolo · highest flute, very bright, piercing, bird-like whistle",
    73: "Flute · airy breathy blown pipe, classical, flowing, pure and organic",
    74: "Recorder · folk blown pipe, gentle, Renaissance / medieval, simple",
    75: "Pan flute · breathy hollow blown, world / ethnic, natural and floating",
    76: "Blown bottle · pure whistle sine-like tone, very minimal, almost clean",
    77: "Shakuhachi · Japanese bamboo flute, breathy, meditative, world music",
    78: "Whistle · tin-whistle, Celtic / folk, bright and simple, very airy",
    79: "Ocarina · small clay flute, round and hollow, world, child-like warmth",

    # ── Synth Lead (80 – 87) ──────────────────────────────────────────────────
    80: "Square wave lead · digital buzzy, 8-bit video-game feel, retro computer",
    81: "Sawtooth lead · bright, cutting, full harmonics — machine-like, electronic",
    82: "Calliope lead · flute-like synth, soft and hollow, circus / fairground",
    83: "Chiff lead · metallic breathy attack, airy, new-age flute hybrid",
    84: "Charang lead · distorted synth-guitar hybrid, aggressive, electronic rock",
    85: "Voice lead · robotic singing synth, uncanny-valley vocal, sci-fi",
    86: "Fifths lead · stacked-fifth power chord synth, electronic muscle, fat",
    87: "Bass + Lead · dual-layer synth, deep bass fused with cutting lead",

    # ── Synth Pad (88 – 95) ───────────────────────────────────────────────────
    88: "New Age pad · airy shimmer, slow attack, electronic, celestial warmth",
    89: "Warm pad · full round swell, slow attack, comforting, analogue-like",
    90: "Polysynth pad · bright 80s polyphonic synth, glassy shimmer, electronic",
    91: "Choir pad · synthetic choir texture, heavenly, wide, very atmospheric",
    92: "Bowed glass pad · eerie glass-harmonica effect, slowly builds, haunting",
    93: "Metallic pad · cold industrial shimmer, electronic metallic glow, icy",
    94: "Halo pad · ethereal angelic texture, dreamlike, ultra-slow evolving",
    95: "Sweep pad · evolving filter sweep, sci-fi, slowly morphing, spacious",

    # ── Synth FX (96 – 103) ───────────────────────────────────────────────────
    96: "FX: Rain · white-noise pitch drops, ambient texture, non-tonal effect",
    97: "FX: Soundtrack · cinematic dense swell, background noise-bed, filmic",
    98: "FX: Crystal · glassy bell-like hits, sparse and airy, very short decay",
    99: "FX: Atmosphere · diffuse haze, cinematic tension texture, background blur",
    100:"FX: Brightness · high-frequency sheen, glittery air enhancement layer",
    101:"FX: Goblins · dark bubbling texture, horror-game, unsettling and murky",
    102:"FX: Echoes · repeating decaying ping, spatial depth, ambient space",
    103:"FX: Sci-Fi · electronic space sound, robotic futuristic noise texture",

    # ── Ethnic (104 – 111) ────────────────────────────────────────────────────
    104:"Sitar · Indian plucked string, twangy drone resonance, meditative",
    105:"Banjo · American folk plucked, bright twangy resonance, rootsy",
    106:"Shamisen · Japanese plucked lute, sharp attack, thin and nasal",
    107:"Koto · Japanese zither, plucked delicate, pentatonic-fitting, ancient",
    108:"Kalimba · African thumb piano, gentle metallic ping, minimal, organic",
    109:"Bagpipe · droning reed pipe, Scottish / Celtic, continuous low drone",
    110:"Fiddle · bright folk violin, lively dance energy, rustic and organic",
    111:"Shanai · Indian reed instrument, nasal, ceremonial, very bright",

    # ── Percussive (112 – 119) ────────────────────────────────────────────────
    112:"Tinkle bell · tiny high bell hits, childlike, ornamental, very short",
    113:"Agogo · Brazilian metal cowbell, bright percussive ping, rhythmic",
    114:"Steel drums · Caribbean warm metallic pitch, tropical, round tone",
    115:"Woodblock · crisp dry wooden click, very short, metronome-like",
    116:"Taiko drum · large Japanese drum, deep booming, ceremonial, cinematic",
    117:"Melodic tom · tuned drum, punchy pitched hit, 80s power-fill sound",
    118:"Synth drum · electronic drum hit, 808-style pitch-mapped, per-note",
    119:"Reverse cymbal · backward crash whoosh, build-up effect, transition",

    # ── Sound Effects (120 – 127) ─────────────────────────────────────────────
    120:"Guitar fret noise · string-squeak detail, realistic texture, non-pitched",
    121:"Breath noise · breathy air burst, human texture, ambient non-pitched",
    122:"Seashore · ocean wave noise, ambient, completely non-pitched, texture",
    123:"Bird tweet · chirping bird, naturalistic, non-pitched, ambient detail",
    124:"Telephone ring · mechanical ring tone burst, incidental, very short",
    125:"Helicopter · rhythmic rotor noise, industrial texture, non-pitched",
    126:"Applause · crowd clapping, performance context, ambient noise texture",
    127:"Gunshot · single impact click, percussive effect, cinematic hit",
}

# ── Fallback for unknown programs ─────────────────────────────────────────────
_FAMILY_NAMES = [
    "Piano", "Chromatic Perc", "Organ", "Guitar",
    "Bass", "Strings", "Ensemble", "Brass",
    "Reed", "Pipe", "Synth Lead", "Synth Pad",
    "Synth FX", "Ethnic", "Percussive", "Sound FX",
]


def get_description(program: int) -> str:
    """
    Return a pedagogical description for a GM program number.

    Falls back to a family-name string when the program is out of range
    or not in the dictionary (should not happen in practice).
    """
    if program in GM_DESCRIPTIONS:
        return GM_DESCRIPTIONS[program]
    if 0 <= program <= 127:
        family = _FAMILY_NAMES[program // 8]
        return f"GM program {program} · {family} family"
    return f"GM program {program}"
