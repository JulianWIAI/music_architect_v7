"""
bass_architect.py — Per-song bass instrument and rhythmic archetype selection.

Why this module exists
----------------------
Two structural problems cause bass lines to sound identical across songs:

  1. Fixed instrument — the engine reads the GUI's bass track selector, which
     holds one value for the entire session.  Pop songs always get program 33,
     hip-hop always gets 38.  No variety session-to-session.

  2. Fixed rhythmic template — the fallback generator (used when seed data
     contains no bass patterns for a genre) emits the same hardcoded 5-note
     sequence every bar: root on beat 1, root on beat 2, fifth on beat 3,
     root on 3.5, root on 4.  Identical regardless of key, seed, or section.

This module solves both problems:

  Instrument pools — 3-5 genre-appropriate GM program numbers per genre.
      A different program is randomly drawn for each song, giving each
      composition a distinct timbral identity while staying within the
      genre's sonic vocabulary.

  Rhythmic archetypes — 6-8 16-step binary patterns per genre encoding
      genuinely distinct rhythmic feels (walking 8ths, sparse root-only,
      funk 16ths, boom-bap, syncopated push, pedal tone, etc.).  One is
      drawn per song and used as the primary rhythmic template for the
      fallback generator, replacing the single hardcoded pattern.

  Note palettes — per-genre list of semitone offsets from the chord root
      used for non-anchor steps.  Pop bass favours bright major-chord tones
      (root, third, fifth, octave); cinematic favours open power intervals
      (root, fifth, octave); hip-hop uses minor-seventh flavouring
      (root, b3, fifth, b7) for characteristic darkness.

Music theory grounding
----------------------
Every instrument pool is constrained to instruments that actually appear
in the genre's commercial productions:

  Pop     : Electric basses (finger, pick, fretless, slap) and synth bass.
            Bright articulate tones; finger bass (33) defines mainstream pop.
  Hip-hop : Synth bass 1+2 and the "Bass + Lead" layered program (87) for
            the sub-heavy character of boom-bap and trap-hop.
  Cinematic: Acoustic orchestral basses (contrabass 43, cello 42, acoustic 32).
            The contrabass (43) provides the sub-frequency foundation typical
            of Hans Zimmer / John Williams action scoring.

Rhythmic archetypes are grounded in the same genre analysis used for
GENRE_DRUM_PATTERNS — each pattern reflects a distinct commercial production
school rather than arbitrary variation.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple


# ── GM programme pools per genre ─────────────────────────────────────────────
# Each pool contains 3-5 appropriate programs.  A random draw per song ensures
# the bass timbre varies even when the user leaves the GUI selector unchanged.

BASS_INSTRUMENT_POOLS: Dict[str, List[int]] = {
    # Finger bass (33) is the pop standard; pick (34) = punchy alt-pop;
    # fretless (35) = smooth R&B-pop; slap (36) = funk-pop / disco;
    # synth bass 1 (38) = darker modern pop production.
    'pop':      [33, 34, 35, 36, 38],

    # Synth bass 1 (38) = classic boom-bap sub; synth bass 2 (39) = warmer;
    # bass+lead (87) = sub-heavy 808-adjacent; finger (33) = live jazz-hop.
    'hiphop':   [38, 39, 87, 33],

    # Contrabass (43) = orchestral foundation; cello (42) = high countermelody;
    # acoustic bass (32) = intimate smaller-ensemble cues.
    'cinematic': [43, 42, 32],

    # bass+lead (87) = 808-style sub; synth bass 1 (38) = trap workhorse;
    # synth bass 2 (39) = darker sub variant.
    'trap':     [87, 38, 39],

    # Synth bass 1 is the house standard; pick bass (34) for acid-house edge;
    # bass+lead (87) for the sub-depth of modern deep house.
    'house':    [38, 34, 87],

    # All synth programs for EDM; bass+lead (87) adds the sub-layer typical
    # of big-room and future-bass productions.
    'edm':      [38, 39, 87],

    # Minimal techno stays fully electronic; synth bass 2 (39) has the
    # rounder character suited to deep minimal techno.
    'techno':   [38, 39, 87],

    # J-pop leans toward acoustic-electric basses; slap bass (36) appears
    # in city-pop and idol-pop productions.
    'jpop':     [33, 34, 36, 38],

    # Phonk's bass+lead (87) mimics the 808 sub while retaining a melodic
    # character; slap (36) appears in Memphis-era phonk samples.
    'phonk':    [87, 38, 39, 36],

    # DnB sub-bass is almost always fully synthetic; bass+lead (87) gives
    # the sub-bass presence needed for 170+ BPM drops.
    'dnb':      [38, 87, 39],

    # Classical uses only acoustic instruments: acoustic bass (32) for
    # pizzicato figures, cello (42) for arco lines, contrabass (43) for depth.
    'classical': [32, 42, 43],
}

_DEFAULT_INSTRUMENT_POOL = [33, 38, 87]

# ── 16-step rhythmic archetypes per genre ────────────────────────────────────
# Each value in the inner list is 1 (hit) or 0 (rest) for one 16th-note step.
# Chosen to cover clearly distinct rhythmic feels — not slight variations on
# the same pattern.

BASS_ARCHETYPES: Dict[str, List[List[int]]] = {
    'pop': [
        # Root on beats 1 and 3 — simplest possible pop foundation
        [1,0,0,0, 0,0,0,0, 1,0,0,0, 0,0,0,0],
        # Straight 8th-note walking bass — Motown / classic pop
        [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0],
        # Syncopated push — anticipates beat 2; "leaning" groove
        [1,0,0,1, 0,0,1,0, 1,0,0,0, 0,0,1,0],
        # Motown bounce — quarters with 8th fill on beat 3
        [1,0,0,0, 1,0,0,0, 1,0,1,0, 0,0,1,0],
        # Funk 16th density — Bruno Mars / Mark Ronson pocket
        [1,1,0,1, 0,0,1,0, 1,0,1,1, 0,1,0,0],
        # Half-time emotional — one hit per bar; maximum space for vocal
        [1,0,0,0, 0,0,0,0, 0,0,1,0, 0,0,0,0],
        # Pop-rock bounce — pairs of quarter + 8th
        [1,0,0,0, 1,0,1,0, 1,0,0,0, 1,0,1,0],
        # Disco four-on-floor with approach note on "and" of beat 4
        [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,1,0],
        # R&B upbeat — root + anticipation on "and" of beat 2, root on 3.
        # Used throughout R&B-pop crossover production (SZA, H.E.R. territory).
        [1,0,0,0, 0,0,1,0, 1,0,0,0, 0,0,0,0],
        # Locked chorus drive — all four beats plus 8th on beat 3.
        # Standard high-energy chorus bass lock used in arena pop.
        [1,0,0,0, 1,0,0,0, 1,0,1,0, 1,0,0,0],
        # New wave / synth-pop arpeggio — stepping 8th pairs offset by a beat.
        # Duran Duran / New Order / A-ha characteristic bass motion.
        [1,0,1,0, 0,1,0,0, 1,0,1,0, 0,1,0,0],
        # Gospel approach — root on 1+3, anticipation note on "and" of 4.
        # The approach note pulls the listener forward into the next bar.
        [1,0,0,0, 0,0,0,0, 1,0,0,0, 0,0,0,1],
        # Ballad single — one hit, sustained the entire bar.
        # Ed Sheeran / Adele production: silence IS the arrangement choice.
        [1,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0],
        # Dembow-influenced — reggaeton-pop anticipation feel.
        # Modern Latin-pop crossover (Bad Bunny / J Balvin pop collabs).
        [1,0,0,0, 0,0,0,1, 1,0,0,0, 0,0,0,1],
        # Kick mirror — root on 1, rest on 3.5 and "and" of 3.
        # Bass follows the standard kick placement, creating a locked pocket.
        [1,0,0,0, 0,0,0,0, 1,0,0,1, 0,0,0,0],
        # Bar-end fill — tight 16th pair on beats 3-4 driving into next bar.
        # Common in pre-chorus build sections and verse-to-chorus transitions.
        [1,0,0,0, 0,0,0,0, 1,0,0,0, 1,1,0,0],
        # Soul crossing — 8th-note pairs on 1 and 3 with offbeat "and" hits.
        # Neo-soul / Silk Sonic groove; bass crosses the beat with the drummer.
        [1,0,0,0, 0,1,0,0, 1,0,0,0, 0,1,0,0],
        # Neo-soul float — D'Angelo / Erykah Badu looseness.
        # Notes float around the grid; beat 1 anchors, others drift slightly.
        [1,0,0,1, 0,0,0,0, 1,0,0,0, 0,0,1,0],
    ],
    'hiphop': [
        # Classic boom-bap — root on 1 and 3; rest of bar breathes
        [1,0,0,0, 0,0,0,0, 1,0,0,0, 0,0,0,0],
        # J Dilla pocket — off-grid syncopation; "leans" behind the beat
        [1,0,0,0, 0,0,1,0, 0,1,0,0, 0,0,1,0],
        # Single-hit 808 — just beat 1; maximum space for the mix
        [1,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0],
        # Trap-hop — syncopated cluster at beat 1, ghost on "and" of 3
        [1,0,0,1, 0,0,0,0, 1,0,0,0, 0,0,1,0],
        # West coast bounce — triplet-leaning roll; Dr. Dre / Snoop territory
        [1,0,0,0, 0,0,1,0, 1,0,0,0, 1,0,0,0],
        # Soul walking — loose 8th feel; beats 2 and 4 get the weight
        [1,0,1,0, 0,0,1,0, 1,0,1,0, 0,0,1,0],
        # Drill — bass mirrors the UK drill kick stagger; 1 + 2.5 + late 4
        [1,0,0,0, 0,0,1,0, 0,0,1,0, 0,0,0,1],
        # Abstract / lo-fi — beat 1 anchor, one late-bar ghost note
        [1,0,0,0, 0,0,0,0, 0,0,0,1, 0,0,0,0],
        # Wu-Tang sparse — single root, ghost note on "and" of 4.
        # RZA's approach: the bar is mostly air; the ghost creates menace.
        [1,0,0,0, 0,0,0,0, 0,0,0,0, 0,1,0,0],
        # Kendrick haunted — root on 1, displaced off-beat hit on beat 3.
        # TPAB / DAMN. texture: bass feels unmoored, psychologically unsettling.
        [1,0,0,0, 0,0,0,0, 0,1,0,0, 0,0,0,0],
        # OutKast bounce — root on 1+3 with bar-end anticipation.
        # Atlanta bounce tradition; the late anticipation drives the energy forward.
        [1,0,0,0, 0,0,0,0, 1,0,0,0, 0,0,0,1],
        # Cali lean — root on 1, floating offbeats on "and" of 2 and "and" of 4.
        # The space between hits is the groove; extremely laid-back pocket.
        [1,0,0,0, 0,1,0,0, 0,0,0,0, 0,1,0,0],
        # MF DOOM jazz flip — erratic, sample-derived displacement.
        # Irregular positions echo the jazz samples DOOM built beats from.
        [1,0,0,1, 0,0,0,0, 0,1,0,0, 0,0,1,0],
        # Future melodic 808 — rolling movement across the bar.
        # Melodic 808 bass lines (Future, Gunna) move through the chord changes.
        [1,0,0,0, 0,1,0,0, 1,0,0,0, 0,0,1,0],
        # Grimy underground — dense, gritty NY underground texture.
        # Inspired by the compressed, punchy bass of No I.D. / Just Blaze era.
        [1,1,0,0, 1,0,0,1, 0,0,1,0, 1,0,0,0],
        # Rolling syncopated — first half locked, second half syncopated.
        # Creates a satisfying "drop" within the bar on beat 3.
        [1,0,0,0, 1,0,0,0, 0,0,1,0, 0,0,1,0],
        # Abstract cascade — three hits in diminishing-step positions.
        # Instrumental hip-hop / Madlib territory; melodic without being obvious.
        [1,0,0,1, 0,0,1,0, 0,0,0,1, 0,0,0,0],
        # 8th pairs on 1+3 — busy boom-bap variant; roots on 8th pairs.
        # Heard in Pete Rock, Premier productions where bass doubles the kick.
        [1,0,1,0, 0,0,0,0, 1,0,1,0, 0,0,0,0],
    ],
    'cinematic': [
        # Pedal tone — single sustained hit; harmonics do the work
        [1,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0],
        # Stately quarter notes — Hans Zimmer march / Gladiator style
        [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0],
        # Tension ostinato — 8th pulse for 2 beats, then silence for impact
        [1,0,1,0, 1,0,1,0, 1,0,0,0, 0,0,0,0],
        # Epic sparse — downbeat plus late-bar anticipation into next section
        [1,0,0,0, 0,0,0,0, 1,0,0,0, 0,0,0,1],
        # Counterpoint pairs — 8th-note dyads at beats 1+2 and 3+4
        [1,0,0,0, 0,1,0,0, 1,0,0,0, 0,1,0,0],
        # Dramatic half-time — hit on 1, displaced answer on "and" of 3
        [1,0,0,0, 0,0,0,0, 0,1,0,0, 0,0,0,0],
        # Triplet against 4/4 — 6/8 polyrhythm creates grandeur and sweep
        [1,0,0,1, 0,0,1,0, 0,1,0,0, 1,0,0,0],
        # Heroic half-pulse — beats 1 and 3 only; two wide steps per bar.
        # Interstellar / The Dark Knight: space between hits feels massive.
        [1,0,0,0, 0,0,0,0, 1,0,0,0, 0,0,0,0],
        # Double-impact — quick 16th pair then silence; Hans Zimmer "BRAAM".
        # The fast double-hit followed by reverberant void is a Zimmer signature
        # (Inception, The Dark Knight Rises, Interstellar).
        [1,1,0,0, 0,0,0,0, 1,1,0,0, 0,0,0,0],
        # War drums sync — beats 1+2 locked, syncopated fill on 3+4.
        # Military percussion tradition from Gladiator, Troy, 300 scoring.
        [1,0,0,0, 1,0,0,0, 0,0,1,0, 1,0,0,0],
        # Chase sequence — urgent 8th pairs, asymmetric; action-film motif.
        # The unequal 3-2-3-2 grouping prevents the groove from settling,
        # which mirrors the physical urgency of a chase scene.
        [1,0,1,0, 0,0,0,0, 1,0,1,0, 0,0,1,0],
        # Heartbeat — two 8ths at beats 1 and 3; "dun-dun" psychological motif.
        # Used extensively in horror / psychological thriller scoring to invoke
        # the listener's own pulse as a subconscious tension device.
        [1,0,1,0, 0,0,0,0, 1,0,1,0, 0,0,0,0],
        # Pizzicato scatter — irregular plucked positions; chamber-ensemble feel.
        # Ennio Morricone influence: bass as a melodic actor, not just rhythm.
        [1,0,0,0, 0,0,0,1, 0,0,1,0, 0,0,0,0],
        # Ascending sparse — three hits in rising-tension positions.
        # Each hit is further into the bar than the last, creating a slow climb.
        [1,0,0,0, 0,0,1,0, 0,0,0,0, 0,0,0,1],
        # Basso continuo motor — full 8th-note drive; Baroque / Bach foundation.
        # Bach's basso continuo lines ran 8th-note motors under counterpoint;
        # this translates to high-intensity action cue scoring (Danny Elfman).
        [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0],
        # Anacrusis — upbeat anticipation into beats 2 and 4.
        # Classical music "pickup" tradition; each beat is anticipated by its
        # preceding 16th, pulling the phrase forward — Beethoven / Brahms idiom.
        [0,0,0,1, 1,0,0,0, 0,0,0,1, 1,0,0,0],
        # Impact-void — massive hit on 1, re-entry late in the bar.
        # The silence between hit and re-entry creates the sense of a vast space
        # — used in space / sci-fi scoring (Gravity, Interstellar, Ad Astra).
        [1,0,0,0, 0,0,0,0, 0,0,0,1, 0,0,0,0],
    ],
    'trap': [
        # Classic 808 cluster — hits 1, "and" of 1, "and" of 2
        [1,0,0,1, 0,0,0,0, 1,0,0,0, 0,1,0,0],
        # Rolling 8ths — melodic 808 run
        [1,0,1,0, 0,0,1,0, 1,0,0,1, 0,0,1,0],
        # Half-time massive — single hit; 808 sustains fill the bar
        [1,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0],
        # Synth-bass melodic 16ths — ascending/descending implied by pitch engine
        [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1],
        # Emo trap — hits 1, late-3, leaves wide space
        [1,0,0,0, 0,0,0,0, 0,0,0,1, 0,0,0,0],
        # Bounce — paired double-hits on beat 1 and 3
        [1,1,0,0, 0,0,0,0, 1,1,0,0, 0,0,0,0],
        # Rage — constant 8th-note sub pressure
        [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0],
    ],
    'house': [
        # Deep house 4/4 — every downbeat
        [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0],
        # Offbeat only — bass answers the kick on the "ands"
        [0,0,1,0, 0,0,1,0, 0,0,1,0, 0,0,1,0],
        # Full 8th walk — Chicago house drive
        [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0],
        # UK garage 2-step — syncopated, skips beat 2
        [1,0,0,1, 0,0,1,0, 1,0,0,0, 1,0,1,0],
        # Afro-house clave — 3+3+2 feel
        [1,0,0,1, 0,0,1,0, 0,1,0,0, 0,0,0,0],
        # Jackin' staccato — short double-hit on 1 and 3
        [1,1,0,0, 0,0,0,0, 1,1,0,0, 0,0,0,0],
    ],
    'edm': [
        # Four-on-floor pump — every downbeat
        [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0],
        # Sidechain-implied 8ths — constant 8th sub
        [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0],
        # Future bass syncopated — floats around the beat
        [1,0,0,1, 0,0,1,0, 0,1,0,0, 1,0,0,0],
        # Big room half-time — single massive sub hit
        [1,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0],
        # Trance quarter + anticipation
        [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,1],
        # Electro/hardstyle — quarter hits with 16th double on beat 3
        [1,0,0,0, 1,0,0,0, 1,1,0,0, 1,0,0,0],
    ],
    'techno': [
        # Minimal 4/4 — pure downbeats
        [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0],
        # Full 8th industrial drive
        [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0],
        # Detroit offbeat — bass on the "and" of every beat
        [0,0,1,0, 0,0,1,0, 0,0,1,0, 0,0,1,0],
        # Polyrhythmic cross — 3-against-4 pattern (hits every 3 steps)
        [1,0,0,1, 0,0,1,0, 0,1,0,0, 1,0,0,0],
        # EBM quarter march
        [1,0,0,0, 1,0,0,0, 0,0,1,0, 0,0,1,0],
    ],
    'jpop': [
        # Bright 8th walk — standard j-pop
        [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0],
        # Offbeat bounce — hits on "and" of beat 1 and 3
        [0,0,1,0, 0,0,0,0, 0,0,1,0, 0,0,0,0],
        # Pop-rock quarters
        [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0],
        # City pop run — syncopated; Tatsuro Yamashita feel
        [1,0,0,0, 0,1,0,0, 1,0,0,1, 0,0,1,0],
        # Idol-pop bounce
        [1,0,0,0, 1,0,1,0, 1,0,0,0, 0,0,1,0],
    ],
    'phonk': [
        # Single massive hit — only beat 1
        [1,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0],
        # Classic Memphis syncopation
        [1,0,0,1, 0,0,0,0, 1,0,0,0, 0,1,0,0],
        # Triplet 808 roll
        [1,0,0,1, 0,0,1,0, 0,0,1,0, 0,0,0,1],
        # Drift phonk — rolling 8ths like a rolling car
        [1,0,1,0, 0,0,1,0, 1,0,0,1, 0,0,0,0],
        # Rage phonk — every 16th step active
        [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0],
    ],
    'dnb': [
        # Amen-derived — sparse kick-aligned bass
        [1,0,0,0, 0,0,1,0, 0,1,0,0, 0,0,1,0],
        # Liquid rolling 8ths
        [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0],
        # Neurofunk asymmetric
        [1,0,0,1, 0,1,0,0, 1,0,0,0, 0,1,0,1],
        # Half-time DnB (Ivy Lab) — hip-hop bass at 170 bpm
        [1,0,0,0, 0,0,0,0, 1,0,0,0, 0,0,0,0],
        # Step-drum rollout
        [1,1,0,0, 1,0,1,0, 1,1,0,0, 1,0,1,0],
    ],
    'classical': [
        # Pizzicato quarter — Baroque bass line foundation
        [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0],
        # Alberti-adjacent 8th — Classical period accompaniment
        [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0],
        # Sparse arco — single downbeat, sustained
        [1,0,0,0, 0,0,0,0, 1,0,0,0, 0,0,0,0],
    ],
}

_DEFAULT_ARCHETYPE = [1,0,0,0, 0,0,0,0, 1,0,0,0, 0,0,0,0]

# ── Melodic note palettes ─────────────────────────────────────────────────────
# Semitone offsets from the chord root used for non-anchor steps.
# Anchor steps (0, 4, 8, 12) always prefer the root; palette applies to others.
# Expressed as lists of (offset, weight) so common tones are preferred.

BASS_NOTE_PALETTES: Dict[str, List[Tuple[int, float]]] = {
    # Pop: bright major-chord tones — root, major third, fifth, octave
    'pop':      [(0, 3.0), (4, 1.5), (7, 2.0), (12, 1.0), (-5, 0.5)],
    # Hip-hop: dark minor-7th flavouring — root, minor third, fifth, flat-7th
    'hiphop':   [(0, 3.0), (3, 1.5), (7, 2.0), (10, 1.0), (12, 0.5)],
    # Cinematic: open power intervals — root, fifth, octave
    'cinematic':[(0, 4.0), (7, 2.0), (12, 1.5), (-5, 0.8)],
    # Trap: sub-heavy root and fifth, rare b7 for movement
    'trap':     [(0, 5.0), (7, 1.5), (10, 0.8), (12, 0.5)],
    # House: functional root-fifth-octave groove
    'house':    [(0, 3.0), (5, 1.0), (7, 2.0), (12, 1.0)],
    # EDM: root and fifth with minor 7th for modern EDM flavour
    'edm':      [(0, 3.5), (7, 2.0), (10, 1.0), (12, 0.8)],
    # Techno: minimal — root and fifth only
    'techno':   [(0, 4.0), (7, 2.5), (12, 0.8)],
    # J-Pop: bright — major chord tones including 6th for sweetness
    'jpop':     [(0, 3.0), (4, 1.5), (7, 2.0), (9, 0.8), (12, 1.0)],
    # Phonk: dark minor, Memphis-flavoured tritone tension
    'phonk':    [(0, 4.0), (3, 1.5), (6, 0.5), (10, 1.0), (12, 0.5)],
    # DnB: minor third and fifth driving forward
    'dnb':      [(0, 3.5), (3, 1.0), (7, 2.0), (10, 0.8), (12, 0.5)],
    # Classical: root, third, fifth — functional voice leading
    'classical':[(0, 3.0), (4, 1.5), (7, 2.0), (12, 1.0)],
}

_DEFAULT_PALETTE: List[Tuple[int, float]] = [(0, 3.0), (7, 2.0), (12, 1.0)]

_GENRE_ALIASES: Dict[str, str] = {
    'hip-hop': 'hiphop',
    'hip_hop': 'hiphop',
}


class BassArchitect:
    """
    Returns a per-song (instrument_program, archetype_pattern, note_palette)
    triple suited to the genre.

    All methods are class-level — no instance required.  Thread-safe for
    concurrent MIDI generation workers.
    """

    @classmethod
    def select(
        cls,
        genre:      str,
        seed_value: Optional[int] = None,
    ) -> Tuple[int, List[int], List[Tuple[int, float]]]:
        """
        Draw a random (program, archetype, palette) triple for one song.

        Parameters
        ----------
        genre      : Genre string (e.g. 'pop', 'cinematic', 'hiphop').
        seed_value : Optional RNG seed for reproducibility.

        Returns
        -------
        (program, archetype, palette) where:
          program   — GM MIDI program number for the bass track
          archetype — 16-element binary list (16th-note on/off pattern)
          palette   — list of (semitone_offset, weight) for note selection
        """
        if seed_value is not None:
            rng = random.Random(seed_value ^ 0xBA55)  # isolated RNG, won't perturb global state
        else:
            rng = random.Random()

        canon   = _GENRE_ALIASES.get(genre.lower(), genre.lower())

        program  = rng.choice(BASS_INSTRUMENT_POOLS.get(canon, _DEFAULT_INSTRUMENT_POOL))
        archetype = rng.choice(BASS_ARCHETYPES.get(canon, [_DEFAULT_ARCHETYPE]))
        palette  = BASS_NOTE_PALETTES.get(canon, _DEFAULT_PALETTE)

        return program, archetype, palette

    @classmethod
    def pick_note(
        cls,
        palette:    List[Tuple[int, float]],
        root_midi:  int,
        anchor:     bool = False,
    ) -> int:
        """
        Return a MIDI note appropriate for the given step.

        anchor=True forces the root note (used on step 0 and strong beats).
        Otherwise, a note is drawn from palette using weighted random selection.
        The result is clamped to a playable bass register (28–60).
        """
        if anchor or not palette:
            note = root_midi
        else:
            offsets = [o for o, _ in palette]
            weights = [w for _, w in palette]
            offset  = random.choices(offsets, weights=weights, k=1)[0]
            note    = root_midi + offset

        # Clamp to bass register
        while note > 60:
            note -= 12
        while note < 28:
            note += 12
        return note
