import random
from typing import List, Dict, Tuple

NOTE_TO_MIDI = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3,
    'E': 4, 'Fb': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7,
    'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11, 'Cb': 11,
}

MIDI_TO_NOTE = {v: k for k, v in NOTE_TO_MIDI.items() if '#' not in k and 'b' not in k}
MIDI_TO_NOTE.update({1: 'C#', 3: 'D#', 6: 'F#', 8: 'G#', 10: 'A#'})

CHORD_INTERVALS = {
    'major': [0, 4, 7], 'minor': [0, 3, 7], 'dim': [0, 3, 6],
    'aug': [0, 4, 8], 'sus4': [0, 5, 7], 'sus2': [0, 2, 7],
    '7': [0, 4, 7, 10], 'maj7': [0, 4, 7, 11], 'min7': [0, 3, 7, 10],
    'dim7': [0, 3, 6, 9], 'min': [0, 3, 7], 'maj': [0, 4, 7],
    '9': [0, 4, 7, 10, 14], 'add9': [0, 4, 7, 14],
    'min9': [0, 3, 7, 10, 14], 'maj9': [0, 4, 7, 11, 14],
    '11': [0, 4, 7, 10, 14, 17], '13': [0, 4, 7, 10, 14, 21],
    '6': [0, 4, 7, 9], 'min6': [0, 3, 7, 9],
}

SCALE_INTERVALS = {
    'major': [0, 2, 4, 5, 7, 9, 11],
    'minor': [0, 2, 3, 5, 7, 8, 10],
    'dorian': [0, 2, 3, 5, 7, 9, 10],
    'mixolydian': [0, 2, 4, 5, 7, 9, 10],
    'pentatonic_major': [0, 2, 4, 7, 9],
    'pentatonic_minor': [0, 3, 5, 7, 10],
    'harmonic_minor': [0, 2, 3, 5, 7, 8, 11],
    'melodic_minor': [0, 2, 3, 5, 7, 9, 11],
    'phrygian': [0, 1, 3, 5, 7, 8, 10],
    'lydian': [0, 2, 4, 6, 7, 9, 11],
    'blues': [0, 3, 5, 6, 7, 10],
    'japanese': [0, 1, 5, 7, 8],
    'chromatic': list(range(12)),
}

KICK = 36
SNARE = 38
RIMSHOT = 37
CLAP = 39
HIHAT_CLOSED = 42
HIHAT_OPEN = 46
HIHAT_PEDAL = 44
CRASH = 49
RIDE = 51
TOM_LOW = 45
TOM_MID = 47
TOM_HIGH = 50

GENRE_DRUM_PATTERNS = {
    'pop': [
        {   # standard pop — kick on 1,2,3 with offbeat; 8th hihat
            'kick':  [(0, 100), (4, 80), (8, 90), (10, 60)],
            'snare': [(4, 100), (12, 100)],
            'hihat': [(0,70),(2,85),(4,70),(6,85),(8,70),(10,85),(12,70),(14,85)],
        },
        {   # syncopated pop — pushed kick, ghost snare on 10
            'kick':  [(0, 110), (3, 65), (8, 100), (11, 60)],
            'snare': [(4, 105), (10, 70), (12, 95)],
            'hihat': [(0,65),(2,80),(4,65),(5,45),(6,80),(8,65),(10,80),(12,65),(14,80)],
        },
        {   # four-on-the-floor pop — driving quarter-note kick
            'kick':  [(0, 105), (4, 100), (8, 105), (12, 100)],
            'snare': [(4, 100), (12, 100)],
            'hihat': [(0,75),(2,60),(4,75),(6,60),(8,75),(10,60),(12,75),(14,60)],
        },
        {   # half-time pop — snare only on beat 3 (bar 8 downbeat), wide open feel
            # Popularised by Billie Eilish / Finneas productions; creates space.
            'kick':  [(0, 105), (3, 60), (8, 95)],
            'snare': [(8, 110)],
            'hihat': [(0,70),(2,55),(4,70),(6,55),(8,70),(10,55),(12,70),(14,55)],
        },
        {   # lo-fi pop — swing 16ths, ghost snares, open hihat accent
            # Lo-fi / bedroom pop groove; low velocity ghost hits add warmth.
            'kick':  [(0, 95), (8, 90), (11, 50)],
            'snare': [(4, 85), (12, 90), (6, 40), (14, 38)],
            'hihat': [(i, 55 if i % 2 == 0 else 38) for i in range(16)] + [(7, 60)],
        },
        {   # funk-pop — 16th kick cluster on beat 1, open hihat on "e-and" of 2
            # Inspired by Bruno Mars / Mark Ronson pocket groove.
            'kick':  [(0, 110), (1, 55), (6, 70), (8, 105), (13, 55)],
            'snare': [(4, 100), (12, 100)],
            'hihat': [(i, 70) for i in range(0, 16, 2)] + [(5, 80), (13, 80)],
        },
        {   # power pop — heavy kick on all four with pushed snare anticipation
            # Stadium-rock inspired; similar to Foo Fighters / Paramore production.
            'kick':  [(0, 115), (4, 110), (8, 115), (12, 110)],
            'snare': [(3, 45), (4, 105), (11, 45), (12, 105)],
            'hihat': [(i * 2, 80) for i in range(8)],
        },
        {   # disco-pop — 4/4 kick, open hihat on 2+4 upbeats, 8th closed hats
            # Roland TR-909 flavoured; used extensively in Dua Lipa / Kylie production.
            'kick':  [(i * 4, 108) for i in range(4)],
            'snare': [(4, 100), (12, 100)],
            'hihat': [(i, 65 if i % 4 != 2 else 45) for i in range(0, 16, 2)]
                     + [(2, 80), (10, 80)],   # open-hat accent on upbeats
        },
    ],
    'hiphop': [
        {   # classic boom bap — sparse kick, 16th hihat velocity swing
            'kick':  [(0, 110), (8, 90)],
            'snare': [(4, 100), (12, 95)],
            'hihat': [(i, 65 if i % 2 == 0 else 45) for i in range(16)],
        },
        {   # trap-influenced hip-hop — syncopated kick, dense hihat
            'kick':  [(0, 115), (3, 60), (10, 85)],
            'snare': [(4, 100), (12, 95)],
            'hihat': [(i, 60) for i in range(16)] + [(i + 0.5, 35) for i in range(0, 16, 4)],
        },
        {   # soulful hip-hop — loose feel, kick on 1 and "and-of-2"
            'kick':  [(0, 110), (6, 70), (9, 75)],
            'snare': [(4, 100), (12, 90), (13, 55)],
            'hihat': [(0,70),(2,55),(4,70),(6,55),(8,70),(10,55),(12,70),(14,55)],
        },
        {   # abstract / instrumental hip-hop — J Dilla-influenced off-grid feel
            # Dilla's MPC quantise-off approach: kicks and snares land slightly late,
            # creating a uniquely "human" behind-the-beat feel.
            'kick':  [(0, 110), (0.5, 42), (9, 90), (12, 50)],
            'snare': [(4, 95), (4.5, 38), (13, 100)],
            'hihat': [(i, 50 if i % 2 == 0 else 35) for i in range(16)],
        },
        {   # west coast bounce — rolling kick pattern, 16th hihat with accent swing
            # G-funk / Dr. Dre school; kick triplet leans give the characteristic roll.
            'kick':  [(0, 115), (2, 60), (5, 45), (8, 110), (11, 55)],
            'snare': [(4, 105), (12, 100)],
            'hihat': [(i, 70 if i % 4 == 0 else 48) for i in range(16)],
        },
        {   # lo-fi hip-hop — soft kick, brush-snare feel, sparse hats
            # Chillhop / lo-fi beats aesthetic; low velocities create intimacy.
            'kick':  [(0, 85), (8, 80)],
            'snare': [(4, 75), (12, 72), (10, 40)],
            'hihat': [(i * 2, 45 if i % 2 == 0 else 32) for i in range(8)],
        },
        {   # drill — staggered kick cluster, 16th-note hi-hat triplet bursts
            # UK Drill / Pop Smoke / Headie One pattern; kick clusters around beat 3.
            'kick':  [(0, 115), (9, 70), (10, 55), (12, 105)],
            'snare': [(4, 110), (12, 110)],
            'hihat': [(i, 55) for i in range(16)] + [(i + 0.33, 38) for i in range(4, 12, 2)],
        },
        {   # new-school trap-hop — half-time snare, rolling 16ths
            # Post-Malone / Juice WRLD cross-genre feel; half-time groove with trap hats.
            'kick':  [(0, 115), (3, 55), (6, 45), (10, 90)],
            'snare': [(8, 115)],
            'hihat': [(i, 55 + (20 if i % 3 == 0 else 0)) for i in range(16)],
        },
        {   # boom-bap variant — rimshot push, hi-hat with open accent on "and-of-4"
            # Nas / Illmatic production style; snare replaced by rimshot; open hat on 14.
            'kick':  [(0, 110), (7, 55), (8, 95)],
            'snare': [(4, 100), (12, 95)],
            'hihat': [(i * 2, 60) for i in range(8)] + [(14, 85)],  # open hat on 14
        },
    ],
    'trap': [
        {   # classic trap — sparse kick, dense 16th + 8th-triplet hihat
            'kick':  [(0, 120), (3, 60), (6, 50), (10, 100), (14, 50)],
            'snare': [(4, 110), (12, 110)],
            'hihat': [(i, 50 + (30 if i % 3 == 0 else 0)) for i in range(16)] +
                     [(i + 0.5, 40) for i in range(0, 16, 2)],
        },
        {   # half-time trap — snare on 3 only, machine-gun hihat
            'kick':  [(0, 120), (6, 65)],
            'snare': [(8, 115)],
            'hihat': [(i, 55) for i in range(16)] + [(i + 0.33, 38) for i in range(0, 16, 2)],
        },
        {   # hard trap — double kick, heavy synth-snare, rolling hihat
            'kick':  [(0, 120), (2, 55), (8, 115), (10, 55)],
            'snare': [(4, 115), (12, 115)],
            'hihat': [(i, 55 + (25 if i % 2 == 0 else 0)) for i in range(16)] +
                     [(i + 0.5, 40) for i in range(0, 16, 3)],
        },
        {   # emo trap — half-time snare on 3, slow kick cluster, sparse triplet hats
            # Juice WRLD / Lil Peep aesthetic; melancholy is partly rhythmic — the
            # half-time snare slows the perceived energy, creating emotional heaviness.
            'kick':  [(0, 115), (5, 50), (8, 100), (13, 45)],
            'snare': [(8, 115)],
            'hihat': [(i, 45) for i in range(0, 16, 3)],
        },
        {   # rage trap — Playboi Carti / Destroy Lonely pattern; very fast open hats
            # Rage beat hallmark: accented open hi-hats on offbeats, minimal snare.
            'kick':  [(0, 120), (4, 65), (10, 110)],
            'snare': [(4, 115), (12, 115)],
            'hihat': [(i, 60) for i in range(16)]
                     + [(i + 0.5, 55) for i in range(16)]   # dense offbeat open hats
                     + [(i + 0.25, 38) for i in range(0, 16, 4)],
        },
        {   # minimal trap — single kick, clap instead of snare, sparse 8th hats
            # Lil Baby / Gunna melodic-trap minimalism; space IS the groove.
            'kick':  [(0, 118), (11, 60)],
            'snare': [(4, 100), (12, 100)],   # map to clap in engine
            'hihat': [(i * 2, 50) for i in range(8)],
        },
        {   # bounce trap — New Orleans-influenced fast kick triplet
            # BlocBoy JB / Drake "Shoot" bounce feel; kick triplet on beat 1 and 3.
            'kick':  [(0, 120), (1, 58), (2, 50), (8, 115), (9, 55), (10, 45)],
            'snare': [(4, 110), (12, 110)],
            'hihat': [(i, 50 if i % 2 == 0 else 35) for i in range(16)],
        },
        {   # cloud trap — very soft velocities, reverb-heavy feel implied by spacing
            # Bladee / Drain Gang aesthetic; soft, melancholy pocket feel.
            'kick':  [(0, 100), (7, 45), (10, 88)],
            'snare': [(4, 90), (12, 90)],
            'hihat': [(i, 40 + (15 if i % 4 == 0 else 0)) for i in range(16)],
        },
        {   # drill trap — dark syncopation, UK-influenced kick stagger
            # Fivio Foreign / Kay Flock style; kick stagger creates menacing tension.
            'kick':  [(0, 118), (9, 65), (10, 50), (12, 112)],
            'snare': [(4, 115), (12, 115)],
            'hihat': [(i, 52) for i in range(16)] + [(i + 0.33, 35) for i in range(2, 14, 3)],
        },
    ],
    'cinematic': [
        {   # epic impact — half-time, no hihat
            'kick':  [(0, 100), (8, 80)],
            'snare': [(8, 70)],
            'hihat': [],
        },
        {   # tribal — triplet kick feel, no snare
            'kick':  [(0, 110), (3, 75), (7, 65)],
            'snare': [],
            'hihat': [],
        },
        {   # tension — single kick per bar, sparse rim hits
            'kick':  [(0, 90)],
            'snare': [(6, 55), (12, 60)],
            'hihat': [],
        },
        {   # taiko march — military two-step, building intensity
            # Hans Zimmer / Inception style; low-frequency taiko thunder on 1 and 3.
            'kick':  [(0, 115), (8, 105), (6, 50)],
            'snare': [(4, 80), (12, 80)],
            'hihat': [],
        },
        {   # battle pulse — rapid 8th-note kick with rimshot accents
            # Action-sequence scoring; unrelenting 8th pulse drives urgency.
            'kick':  [(i * 2, 95 if i % 4 == 0 else 70) for i in range(8)],
            'snare': [(4, 55), (10, 60), (14, 65)],
            'hihat': [],
        },
        {   # horror tension — erratic ultra-sparse kick, no regular pulse
            # Suspense cue design; silence IS the tension — minimal elements only.
            'kick':  [(0, 80), (11, 55)],
            'snare': [(13, 45)],
            'hihat': [],
        },
        {   # epic 6/8 — triplet feel (adapted to 16-step grid) for grand feel
            # Trailer music / BrainPower style; triplet-weighted kicks.
            'kick':  [(0, 115), (5, 70), (8, 105), (10, 55), (13, 75)],
            'snare': [(8, 85)],
            'hihat': [],
        },
        {   # ethereal — very light percussion, ostinato-like rim pattern
            # Ambient / drone cinematic; only texture touches.
            'kick':  [(0, 65)],
            'snare': [(3, 40), (7, 38), (11, 42), (15, 38)],
            'hihat': [],
        },
    ],
    'classical': [
        {'kick': [], 'snare': [], 'hihat': []},
        {'kick': [], 'snare': [], 'hihat': []},
        {'kick': [], 'snare': [], 'hihat': []},
    ],
    'techno': [
        {   # classic 4/4 — four-on-floor, straight 8th hihat
            'kick':  [(i * 4, 110) for i in range(4)],
            'snare': [(4, 90), (12, 90)],
            'hihat': [(i, 80 if i % 2 == 0 else 60) for i in range(16)],
        },
        {   # industrial — double kick on 1 and 2.5, heavy hits, sparse hihat
            'kick':  [(0, 115), (2, 70), (4, 110), (8, 115), (10, 70), (12, 110)],
            'snare': [(4, 95), (8, 70), (12, 95)],
            'hihat': [(i * 4, 65) for i in range(4)],
        },
        {   # driving techno — 4/4 kick, dense 16th hihat, rimshot snare
            'kick':  [(i * 4, 110) for i in range(4)],
            'snare': [(4, 85), (12, 85)],
            'hihat': [(i, 75 if i % 4 != 0 else 90) for i in range(16)],
        },
        {   # Detroit minimal — 4/4 kick, clap on 2+4, sparse offbeat hihat
            # Robert Hood / Plastikman school; restraint IS the aesthetic.
            'kick':  [(i * 4, 108) for i in range(4)],
            'snare': [(4, 80), (12, 80)],
            'hihat': [(i * 4 + 2, 55) for i in range(4)],   # only offbeat hats
        },
        {   # hard techno / Berghain — heavy kick with sidechain-implication accent
            # Slam / Paula Temple style; every kick is a full-body hit.
            'kick':  [(i * 4, 120) for i in range(4)],
            'snare': [(4, 100), (12, 100)],
            'hihat': [(i, 85 if i % 4 == 2 else 55) for i in range(16)],
        },
        {   # EBM / industrial-techno — kick on 1+2+3, martial straight-8th hihat
            # Skinny Puppy / Front 242 influence; aggressive straight-8th march.
            'kick':  [(0, 115), (4, 100), (8, 115), (10, 65)],
            'snare': [(4, 95), (12, 95)],
            'hihat': [(i * 2, 75) for i in range(8)],
        },
        {   # acid techno — 4/4 kick, open-hihat on offbeat (Roland TR-909 open)
            # Roland 909 acid pattern; open hi-hat on the "and" of beat 2 and 4.
            'kick':  [(i * 4, 112) for i in range(4)],
            'snare': [(4, 90), (12, 90)],
            'hihat': [(i * 2, 65) for i in range(8)] + [(6, 85), (14, 85)],
        },
        {   # polyrhythmic techno — kick on 4/4, snare stagger at 3/4 crossrhythm
            # Cross-rhythm technique common in late-night techno sets; disorienting
            # but compelling — two patterns with different cycle lengths overlap.
            'kick':  [(i * 4, 110) for i in range(4)],
            'snare': [(3, 80), (9, 75), (15, 78)],    # 3-step snare against 4/4
            'hihat': [(i, 70 if i % 4 == 0 else 50) for i in range(16)],
        },
    ],
    'jpop': [
        {   # bright jpop — offbeat kick feel, 8th hihat
            'kick':  [(0, 95), (6, 70), (8, 90), (14, 50)],
            'snare': [(4, 95), (12, 100)],
            'hihat': [(i, 65 + ((i // 2) % 2) * 20) for i in range(0, 16, 2)],
        },
        {   # energetic jpop — four-on-floor kick, ghost snare on 10, 16th hihat
            'kick':  [(0, 100), (4, 85), (8, 100), (12, 85)],
            'snare': [(4, 100), (10, 65), (12, 100)],
            'hihat': [(i, 70) for i in range(0, 16, 2)] + [(5, 45), (13, 45)],
        },
        {   # kawaii jpop — bouncy kick, ghost 16ths, loose hihat
            'kick':  [(0, 90), (4, 75), (8, 90)],
            'snare': [(4, 90), (12, 95), (13, 55)],
            'hihat': [(i, 60) for i in range(0, 16, 2)] + [(i + 1, 38) for i in range(0, 16, 4)],
        },
        {   # anime ballad jpop — half-time feel, soft snare, open cymbal accent
            # Slow emotional anime OP/ED type; wide dynamic range, spacious.
            'kick':  [(0, 85), (8, 80)],
            'snare': [(8, 90), (14, 55)],
            'hihat': [(i * 2, 45) for i in range(8)] + [(12, 75)],   # cymbal accent
        },
        {   # city pop revival — 16th-note groove kick, funky snare, 8th closed hat
            # Inspired by Mariya Takeuchi / Tatsuro Yamashita; city pop grooves back.
            'kick':  [(0, 100), (3, 50), (8, 95), (11, 55), (13, 45)],
            'snare': [(4, 95), (12, 100)],
            'hihat': [(i * 2, 65 if i % 2 == 0 else 50) for i in range(8)],
        },
        {   # idol pop jpop — tight hi-energy, double kick anticipation
            # AKB48 / BTS-adjacent production energy; push the kick before beat 1.
            'kick':  [(0, 110), (15, 55), (4, 90), (8, 110), (12, 90)],
            'snare': [(4, 105), (12, 105)],
            'hihat': [(i, 75) for i in range(0, 16, 2)],
        },
        {   # vocaloid / electronic jpop — synthesised drum feel, triplet hat bursts
            # DECO*27 / Kikuo territory; electronic precision with expressive velocity.
            'kick':  [(0, 105), (6, 60), (8, 100), (14, 55)],
            'snare': [(4, 100), (12, 100)],
            'hihat': [(i, 65) for i in range(0, 16, 2)]
                     + [(i + 0.33, 40) for i in range(2, 10, 4)],   # triplet bursts
        },
        {   # oshare kei / visual kei jpop — punk-influenced double snare push
            # The GazettE / Dir en grey lighter side; snare push on upbeats.
            'kick':  [(0, 110), (8, 105), (10, 55)],
            'snare': [(4, 100), (7, 50), (12, 105), (15, 48)],
            'hihat': [(i * 2, 80) for i in range(8)],
        },
    ],
    'phonk': [
        {   # drift phonk — classic cowbell-snare pattern, triplet hihat
            'kick':  [(0, 120), (4, 60), (8, 110), (11, 70), (14, 50)],
            'snare': [(4, 115), (12, 115)],
            'hihat': [(i, 55 + (25 if i % 2 == 0 else 0)) for i in range(16)] +
                     [(i + 0.33, 35) for i in range(0, 16, 3)],
        },
        {   # memphis phonk — sparse kick, snare on 14, 16th hihat
            'kick':  [(0, 120), (3, 70), (8, 110)],
            'snare': [(4, 115), (14, 90)],
            'hihat': [(i, 60) for i in range(16)],
        },
        {   # dark phonk — syncopated kick, heavy snare, offbeat hihat
            'kick':  [(0, 120), (6, 65), (10, 100), (14, 55)],
            'snare': [(4, 110), (12, 110)],
            'hihat': [(i, 50) for i in range(0, 16, 2)] + [(i + 0.5, 35) for i in range(0, 16, 4)],
        },
        {   # mafia phonk — stripped down, single heavy kick, slow triplet hats
            # Eastern European phonk wave; very sparse, ominous atmosphere.
            'kick':  [(0, 122), (10, 65)],
            'snare': [(4, 112), (12, 115)],
            'hihat': [(i, 48) for i in range(0, 16, 3)],   # triplet hats only
        },
        {   # cowbell phonk — TR-808 cowbell rhythm (mapped to snare here)
            # The cowbell IS phonk — Three 6 Mafia ancestry.
            'kick':  [(0, 120), (5, 55), (8, 115), (13, 50)],
            'snare': [(4, 115), (8, 55), (12, 115), (14, 65)],  # cowbell-like double
            'hihat': [(i, 50 if i % 3 == 0 else 35) for i in range(16)],
        },
        {   # rage phonk / fanum tax — very fast hihat 32nd note feel
            # Angst-driven rage phonk; extremely dense hats over sparse kick.
            'kick':  [(0, 120), (9, 60), (12, 112)],
            'snare': [(4, 115), (12, 115)],
            'hihat': [(i * 0.5, 50 + (20 if i % 4 == 0 else 0)) for i in range(32)],
        },
        {   # lo-fi phonk — low velocity, almost hip-hop feel, slow triplet hats
            # Introspective side of phonk; slower tempo feel through sparse hits.
            'kick':  [(0, 100), (8, 95), (11, 45)],
            'snare': [(4, 95), (12, 100)],
            'hihat': [(i * 2, 42 if i % 2 == 0 else 30) for i in range(8)],
        },
        {   # anthemic phonk — pop crossover feel; four-on-floor kick, punchy snare
            # TikTok viral phonk crossover; danceable kick + classic phonk snare.
            'kick':  [(i * 4, 115) for i in range(4)],
            'snare': [(4, 112), (12, 112)],
            'hihat': [(i, 55 + (20 if i % 2 == 0 else 0)) for i in range(16)],
        },
    ],
    'edm': [
        {   # festival EDM — 4/4 kick, snare on 2&4, accented 16th hihat
            'kick':  [(i * 4, 112) for i in range(4)],
            'snare': [(4, 100), (12, 100)],
            'hihat': [(i, 70 + (10 if i % 4 == 0 else 0)) for i in range(16)],
        },
        {   # progressive EDM — 4/4 kick, ghost snare on 8, dense hihat
            'kick':  [(i * 4, 112) for i in range(4)],
            'snare': [(4, 105), (8, 55), (12, 105)],
            'hihat': [(i, 75) for i in range(16)],
        },
        {   # hard dance — double kick on 1 and 2.5, 8th hihat
            'kick':  [(0, 115), (2, 60), (4, 112), (8, 115), (10, 60), (12, 112)],
            'snare': [(4, 100), (12, 100)],
            'hihat': [(i, 70) for i in range(0, 16, 2)],
        },
        {   # big room EDM — accentuated 4/4, half-time snare, cymbal accents
            # Tiësto / W&W Mainstage style; massive drops need massive drums.
            'kick':  [(i * 4, 120) for i in range(4)],
            'snare': [(8, 115)],   # half-time snare for "wall" feel
            'hihat': [(i * 4 + 2, 65) for i in range(4)],   # open hat on offbeats
        },
        {   # future bass EDM — half-time kick feel, layered hihat 16ths
            # Flume / Marshmello style; wide, pitch-shifted drums, half-time pocket.
            'kick':  [(0, 112), (3, 50), (10, 105)],
            'snare': [(8, 110)],
            'hihat': [(i, 60 if i % 2 == 0 else 42) for i in range(16)]
                     + [(i + 0.5, 35) for i in range(0, 16, 4)],
        },
        {   # melodic dubstep / Illenium — emotional half-time, syncopated kick
            # Softer, melodic EDM style; kick avoids beat 1 at times for float.
            'kick':  [(0, 105), (5, 50), (8, 100), (13, 55)],
            'snare': [(8, 110), (15, 55)],
            'hihat': [(i * 2, 55 if i % 2 == 0 else 40) for i in range(8)],
        },
        {   # trance — 4/4 kick, clap on 2+4, signature 16th hihat roll on bar-end
            # ATB / Ferry Corsten style; driving relentless energy from hats.
            'kick':  [(i * 4, 110) for i in range(4)],
            'snare': [(4, 90), (12, 90)],
            'hihat': [(i, 72 if i != 15 else 90) for i in range(16)],
        },
        {   # electro house / Justice — distorted 4/4 kick, heavy offbeat open hat
            # Ed Banger records sound; aggressive, punchy, always moving.
            'kick':  [(0, 118), (4, 112), (8, 118), (12, 112)],
            'snare': [(4, 95), (12, 95)],
            'hihat': [(i * 2, 70) for i in range(8)] + [(2, 90), (10, 90)],
        },
    ],
    'house': [
        {   # deep house — 4/4 kick, offbeat (upbeat) hihat
            'kick':  [(i * 4, 108) for i in range(4)],
            'snare': [(4, 95), (12, 95)],
            'hihat': [(i * 2 + 1, 70) for i in range(8)],
        },
        {   # chicago house — 4/4 kick, straight 8th hihat
            'kick':  [(i * 4, 108) for i in range(4)],
            'snare': [(4, 90), (12, 90)],
            'hihat': [(i * 2, 75) for i in range(8)],
        },
        {   # funky house — syncopated kick on 1, 2.5, 3; 8th hihat with accent swing
            'kick':  [(0, 110), (2, 55), (4, 108), (8, 110), (10, 55), (12, 108)],
            'snare': [(4, 95), (12, 95)],
            'hihat': [(i * 2, 70 if i % 2 == 0 else 55) for i in range(8)],
        },
        {   # tech house — tight 4/4 kick, stutter snare, 16th hihat groove
            # Carl Cox / Fisher production; metronomic yet alive with 16th hats.
            'kick':  [(i * 4, 112) for i in range(4)],
            'snare': [(4, 90), (7, 45), (12, 90), (15, 42)],   # stutter ghost
            'hihat': [(i, 65 if i % 2 == 0 else 48) for i in range(16)],
        },
        {   # afro house — polyrhythmic kick (3+3+2 clave feel), conga-like snare
            # Black Coffee / Themba inspired; West African rhythmic DNA.
            'kick':  [(0, 110), (3, 65), (6, 55), (8, 108), (11, 60)],
            'snare': [(4, 80), (7, 55), (12, 80), (15, 52)],
            'hihat': [(i * 2, 65) for i in range(8)] + [(1, 45), (9, 45)],
        },
        {   # UK garage / speed garage — syncopated 2-step kick feel
            # Classic 2-step: kick is NOT on every beat — rhythm swings and skips.
            'kick':  [(0, 110), (3, 55), (8, 105), (12, 65), (14, 50)],
            'snare': [(4, 95), (12, 95)],
            'hihat': [(i * 2, 60 if i % 2 == 0 else 45) for i in range(8)],
        },
        {   # jackin' house — staccato kick accent, hand-clap on 2+4, 8th hats
            # Classic Chicago style; "jackin'" refers to the rhythmic body jolt.
            'kick':  [(0, 112), (1, 55), (8, 110), (9, 50)],  # staccato double kick
            'snare': [(4, 100), (12, 100)],
            'hihat': [(i * 2, 68) for i in range(8)],
        },
        {   # minimal deep house — 4/4 kick, very sparse clap, no hihat (space)
            # Moodymann / Larry Heard territory; less is more.
            'kick':  [(i * 4, 105) for i in range(4)],
            'snare': [(4, 70), (12, 70)],
            'hihat': [],   # intentionally empty — creates cavernous space
        },
    ],
    'dnb': [
        {   # amen-style breakbeat — kick on 1, snare locked 2+4, rolling 16th hats
            'kick':  [(0, 120), (3, 60), (9, 95), (11, 65)],
            'snare': [(4, 125), (12, 125)],
            'hihat': [(i, 65 if i % 4 == 0 else 50) for i in range(16)],
        },
        {   # liquid dnb — sparse kick, ghost snare, continuous 16th hats
            'kick':  [(0, 118), (6, 55), (9, 90)],
            'snare': [(4, 120), (12, 120), (10, 60)],
            'hihat': [(i, 60 if i % 2 == 0 else 45) for i in range(16)],
        },
        {   # neurofunk — asymmetric kick cluster, tight 16th hats
            'kick':  [(0, 120), (2, 55), (3, 70), (10, 95), (14, 50)],
            'snare': [(4, 122), (12, 122)],
            'hihat': [(i, 70 if i % 4 == 0 else 52) for i in range(16)],
        },
        {   # jump-up / step-drum — rolling double kick, snare push, shredding hats
            'kick':  [(0, 122), (1, 58), (8, 120), (9, 55), (13, 75)],
            'snare': [(4, 125), (11, 58), (12, 125)],
            'hihat': [(i, 65 + (20 if i % 4 == 0 else 0)) for i in range(16)],
        },
        {   # dark / techstep DnB — harsh kick stagger, rimshot accent, minimal hats
            # Ed Rush & Optical / Tech Itch style; menacing and precise.
            'kick':  [(0, 122), (2, 60), (9, 115), (11, 55)],
            'snare': [(4, 125), (12, 125), (7, 50)],   # ghost snare on 7
            'hihat': [(i * 4, 55) for i in range(4)],   # very sparse
        },
        {   # minimal rolling DnB — hypnotic kick loop, continuous quiet 16ths
            # Dillinja / Metalheadz production; kick feels like a machine heartbeat.
            'kick':  [(0, 118), (5, 55), (9, 112), (13, 50)],
            'snare': [(4, 120), (12, 120)],
            'hihat': [(i, 48) for i in range(16)],   # very quiet, textural only
        },
        {   # halftime DnB (Ivy Lab / Goth Trad) — half-time feel at 170 bpm
            # Half-time DnB: the kick and snare operate at half the expected rate,
            # creating a hip-hop texture at 170 bpm — a disorienting hybrid.
            'kick':  [(0, 118), (3, 55), (9, 100)],
            'snare': [(8, 120)],   # single snare on bar 3 for half-time
            'hihat': [(i, 55 + (20 if i % 4 == 0 else 0)) for i in range(16)],
        },
        {   # jazzy / intelligent DnB — swing 16ths, double snare roll
            # LTJ Bukem / Good Looking Records; the jazz influence via 16th-note swing.
            'kick':  [(0, 115), (7, 55), (9, 105)],
            'snare': [(4, 118), (11, 55), (12, 120)],   # double snare roll feel
            'hihat': [(i, 58 if i % 2 == 0 else 40) for i in range(16)],
        },
    ],
}

# MPC-style swing percentage per genre (0.50 = straight, 0.67 = full triplet)
GENRE_SWING: Dict[str, float] = {
    'house':  0.56,
    'hiphop': 0.58,
    'trap':   0.54,
    'phonk':  0.54,
    'jpop':   0.52,
    'edm':    0.52,   # subtle hi-hat swing prevents mechanical rigidity
}

GENRE_BPM = {
    'pop': (100, 130), 'hiphop': (70, 100), 'trap': (130, 165),
    'cinematic': (60, 100), 'classical': (70, 140), 'techno': (125, 150),
    'jpop': (110, 145), 'phonk': (130, 160),
    'edm': (128, 145), 'house': (120, 130),
    'dnb': (170, 175),
}

GENRE_SCALES = {
    'pop': ['major', 'mixolydian'],
    'hiphop': ['minor', 'dorian', 'pentatonic_minor'],
    'trap': ['minor', 'phrygian', 'pentatonic_minor'],
    'cinematic': ['minor', 'harmonic_minor', 'lydian'],
    'classical': ['major', 'minor', 'dorian', 'lydian'],
    'techno': ['minor', 'dorian', 'pentatonic_minor'],
    'jpop': ['major', 'lydian', 'japanese', 'pentatonic_major'],
    'phonk': ['minor', 'phrygian', 'blues'],
    'edm': ['minor', 'phrygian', 'pentatonic_minor'],
    'house': ['minor', 'dorian', 'major'],
    'dnb':   ['minor', 'dorian', 'phrygian', 'pentatonic_minor'],
}

GENRE_INSTRUMENTS = {
    'pop': {'chords': 0, 'lead': 80, 'bass': 33, 'pad': 88, 'arp': 80},
    'hiphop': {'chords': 4, 'lead': 80, 'bass': 38, 'pad': 89, 'arp': 81},
    'trap': {'chords': 81, 'lead': 80, 'bass': 38, 'pad': 95, 'arp': 81},
    'cinematic': {'chords': 48, 'lead': 68, 'bass': 43, 'pad': 92, 'arp': 46},
    'classical': {'chords': 0, 'lead': 40, 'bass': 42, 'pad': 48, 'arp': 46},
    'techno': {'chords': 81, 'lead': 80, 'bass': 38, 'pad': 95, 'arp': 81},
    'jpop': {'chords': 0, 'lead': 80, 'bass': 33, 'pad': 89, 'arp': 11},
    'phonk': {'chords': 4, 'lead': 80, 'bass': 87, 'pad': 95, 'arp': 81},
    'edm':   {'chords': 89, 'lead': 80, 'bass': 38, 'pad': 95, 'arp': 81},
    'house': {'chords': 4,  'lead': 80, 'bass': 38, 'pad': 89, 'arp': 81},
    'dnb':   {'chords': 81, 'lead': 80, 'bass': 38, 'pad': 89, 'arp': 81},
}

STRUCTURE_TEMPLATES = {
    'pop': [
        ('intro', 8), ('verse', 16), ('pre_chorus', 8), ('chorus', 16),
        ('verse', 16), ('pre_chorus', 8), ('chorus', 16),
        ('bridge', 8), ('chorus', 16), ('outro', 8),
    ],
    'hiphop': [
        ('intro', 8), ('verse', 16), ('chorus', 8), ('verse', 16),
        ('chorus', 8), ('verse', 16), ('chorus', 16), ('outro', 8),
    ],
    'trap': [
        ('intro', 8), ('build', 8), ('drop', 16), ('verse', 16),
        ('build', 8), ('drop', 16), ('break', 4),
        ('verse', 16), ('drop', 16), ('outro', 8),
    ],
    'cinematic': [
        ('intro', 16), ('build', 16), ('climax', 16), ('break', 8),
        ('tension', 16), ('build', 8), ('climax', 16),
        ('resolution', 16), ('outro', 16),
    ],
    'classical': [
        ('exposition', 32), ('bridge', 8), ('development', 32),
        ('break', 4), ('recapitulation', 32), ('coda', 16),
    ],
    'techno': [
        ('intro', 16), ('build', 16), ('drop', 32), ('break', 8),
        ('build', 8), ('drop', 32), ('outro', 16),
    ],
    'jpop': [
        ('intro', 8), ('verse', 16), ('pre_chorus', 8), ('chorus', 16),
        ('verse', 16), ('pre_chorus', 8), ('chorus', 16),
        ('bridge', 12), ('chorus', 16), ('outro', 8),
    ],
    'phonk': [
        ('intro', 8), ('build', 8), ('drop', 16), ('verse', 16),
        ('break', 4), ('drop', 16), ('bridge', 8), ('drop', 16), ('outro', 8),
    ],
    'edm': [
        ('intro', 16), ('build', 16), ('drop', 32), ('break', 8),
        ('build', 8), ('drop', 32), ('break', 4),
        ('build', 8), ('drop', 16), ('outro', 8),
    ],
    'house': [
        ('intro', 8), ('verse', 16), ('build', 8), ('chorus', 16),
        ('break', 8), ('build', 8), ('chorus', 16), ('outro', 8),
    ],
    'dnb': [
        ('intro', 8), ('break', 8), ('drop', 16),
        ('break', 8), ('drop',  32),
        ('break', 4), ('drop',  16), ('outro', 8),
    ],
}


def note_name_to_midi(note: str, octave: int = 4) -> int:
    base = note[:2] if len(note) > 1 and note[1] in '#b' else note[0]
    return NOTE_TO_MIDI.get(base, 0) + (octave + 1) * 12


def get_chord_midi_notes(root: str, quality: str, octave: int = 4) -> List[int]:
    root_midi = note_name_to_midi(root, octave)
    q = quality.lower().strip()
    intervals = CHORD_INTERVALS.get(q)
    if not intervals:
        if 'min' in q and '7' in q:
            intervals = CHORD_INTERVALS['min7']
        elif 'maj' in q and '7' in q:
            intervals = CHORD_INTERVALS['maj7']
        elif 'dim' in q:
            intervals = CHORD_INTERVALS['dim']
        elif 'aug' in q:
            intervals = CHORD_INTERVALS['aug']
        elif 'sus4' in q:
            intervals = CHORD_INTERVALS['sus4']
        elif 'sus2' in q:
            intervals = CHORD_INTERVALS['sus2']
        elif '7' in q:
            intervals = CHORD_INTERVALS['7']
        elif 'min' in q:
            intervals = CHORD_INTERVALS['minor']
        else:
            intervals = CHORD_INTERVALS['major']
    return [root_midi + i for i in intervals]


def parse_chord_string(chord_str: str) -> Tuple[str, str]:
    if not chord_str:
        return ('C', 'major')
    if len(chord_str) > 1 and chord_str[1] in '#b':
        root = chord_str[:2]
        quality = chord_str[2:] if len(chord_str) > 2 else 'major'
    else:
        root = chord_str[0]
        quality = chord_str[1:] if len(chord_str) > 1 else 'major'
    if not quality:
        quality = 'major'
    return root, quality


def get_scale_notes(root: str, scale_type: str, octave: int = 4) -> List[int]:
    root_midi = note_name_to_midi(root, octave)
    intervals = SCALE_INTERVALS.get(scale_type, SCALE_INTERVALS['major'])
    return [root_midi + i for i in intervals]


def weighted_choice(options: Dict[str, float]) -> str:
    if not options:
        return 'Cmaj7'
    items = list(options.items())
    weights = [w for _, w in items]
    total = sum(weights)
    if total == 0:
        return random.choice([k for k, _ in items])
    r = random.uniform(0, total)
    cumulative = 0
    for item, weight in items:
        cumulative += weight
        if r <= cumulative:
            return item
    return items[-1][0]


def humanize(value: float, amount: float = 0.015) -> float:
    return max(0, value + random.uniform(-amount, amount))


def humanize_velocity(vel: int, amount: int = 12) -> int:
    return max(1, min(127, vel + random.randint(-amount, amount)))
