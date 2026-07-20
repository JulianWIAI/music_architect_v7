"""
orchestrator.py -- 10-track parallel composition matrix orchestrator.

Architecture Overview:
    This module replaces the legacy CompositionEngine.compose() method as the
    primary entry point for generating a full 10-track MIDI composition.

    Pipeline (per composition):

        1. ContextManager.load_from_config()
               Resolves key, scale, BPM, structure, chord progression, seed.
               Injects golden matrices from previous generation if provided.

        2. KickGenerator.generate()        → 01_Kick notes
           PercussionGenerator.generate()  → 02_Percussion notes
           BassGenerator.generate()        → 03_Bass notes
           MelodyGenerator.generate()      → 04_Melody notes
           ChordsGenerator.generate()      → 05_Chords notes (uses melody density)
           PadGenerator.generate()         → 06_Pad notes (uses melody density)
           ArpGenerator.generate()         → 07_Arp notes
           StabsGenerator.generate()       → 08_Stabs notes
           TextureGenerator.generate()     → 09_Texture notes (complementary to melody)
           FXGenerator.generate()          → 10_FX notes

        3. Global humanizer pass
               MicroTimingHumanizer applied to stems 3-8 (bass through stabs).
               Drums have their own timing engine inside kick/percussion generators.

        4. Quantizer pass
               All tracks snapped to 1/64th-note grid (removes float drift).

        5. Phase alignment
               All tracks clipped/wrapped to total_beats for clean loops.

        6. EDM ciphers (genre-conditional)
               SidechainMatrix, StochasticBuildUp, PreDropVoid, AntiDropFakeOut,
               PolyrhythmicFilterSweep applied on top of the generated tracks.

        7. Composition dict assembled and returned.

    Output format (compatible with existing export_midi() in composition_engine.py):
        {
            'tracks':     OrderedDict of {track_name: [Note, ...]},
            'track_info': {track_name: {'channel': int, 'program': int}},
            'bpm':        float,
            'total_bars': int,
            'structure':  list,
            'chord_progression': list,
            'cc_events':  list,       # CC automation (sidechain, filter sweep)
            'pitch_events': list,     # Pitch bend (build-up riser)
            'key':        str,
            'genre':      str,
        }

Seeding strategy:
    Each generator receives rng = random.Random(seed_value + track_index)
    so generators are statistically independent while remaining reproducible.

        track index 0 → KickGenerator
        track index 1 → PercussionGenerator
        track index 2 → BassGenerator
        track index 3 → MelodyGenerator
        track index 4 → ChordsGenerator
        track index 5 → PadGenerator
        track index 6 → ArpGenerator
        track index 7 → StabsGenerator
        track index 8 → TextureGenerator
        track index 9 → FXGenerator
"""

from __future__ import annotations
import random
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from src.core.context_manager import ContextManager, SharedContext
from src.core.quantizer import quantize_tracks
from src.utils.humanizer import MicroTimingHumanizer
from src.utils.loop_alignment import align_all_tracks

from src.composition.composition_config import CompositionConfig
from src.composition.composition_engine import CompositionEngine   # for chord gen + structure
from src.composition.genre_constants import GENRE_INSTRUMENTS

from src.generators.kick       import KickGenerator
from src.generators.percussion import PercussionGenerator
from src.generators.bass       import BassGenerator
from src.generators.melody     import MelodyGenerator
from src.generators.chords     import ChordsGenerator
from src.generators.pad        import PadGenerator
from src.generators.arp        import ArpGenerator
from src.generators.stabs      import StabsGenerator
from src.generators.texture    import TextureGenerator
from src.generators.fx         import FXGenerator

# EDM ciphers -- applied post-generation for EDM and house genres
try:
    from src.composition.edm_cipher import (
        SidechainMatrix, StochasticBuildUp, PreDropVoid,
        AntiDropFakeOut, PolyrhythmicFilterSweep,
    )
    EDM_CIPHERS_AVAILABLE = True
except ImportError:
    EDM_CIPHERS_AVAILABLE = False

Note = Tuple[float, float, int, int]

# Which track indices receive global micro-timing humanization
# (Drums at index 0,1 use their own internal timing -- skip them)
_HUMANIZE_TRACK_NAMES = {
    '03_Bass', '04_Melody', '05_Chords', '06_Pad',
    '07_Arp',  '08_Stabs', '09_Texture',
}

# Track name → MIDI channel (for export compatibility)
_TRACK_CHANNELS = {
    '01_Kick':       9,
    '02_Percussion': 9,
    '03_Bass':       0,
    '04_Melody':     1,
    '05_Chords':     2,
    '06_Pad':        3,
    '07_Arp':        4,
    '08_Stabs':      5,
    '09_Texture':    6,
    '10_FX':         7,
}


class Orchestrator:
    """
    Drives the 10-track parallel generation pipeline.

    Typical usage (inside batch_commander or tests):

        engine  = CompositionEngine(seeds_dir='seeds', vocal_mask=False)
        engine.load_seeds()
        orc     = Orchestrator(engine)
        result  = orc.compose(config)
        # result is a composition dict ready for export_midi()
    """

    def __init__(self, composition_engine: CompositionEngine):
        # Reuse the existing engine for chord/structure generation and MIDI export
        self._engine  = composition_engine
        self._ctx_mgr = ContextManager()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def compose(
        self,
        config: CompositionConfig,
        seed_pool_path: Optional[str] = None,
    ) -> dict:
        """
        Generate a full 10-track composition from a CompositionConfig.

        Parameters
        ----------
        config         : CompositionConfig from batch_commander
        seed_pool_path : optional path to math_fitness_report.json (evolutionary injection)

        Returns
        -------
        Composition dict compatible with export_midi() in composition_engine.py
        """
        self._engine._ensure_loaded()

        # 1. Generate song structure and chord progression using existing engine
        structure  = self._engine.generate_structure(config)
        total_bars = sum(bars for _, bars in structure)
        num_chords = max(4, total_bars)
        chord_prog = self._engine.generate_chord_progression(
            config, num_chords=num_chords, structure=structure
        )

        # 2. Build SharedContext
        ctx = self._ctx_mgr.load_from_config(
            config            = config,
            structure         = structure,
            chord_progression = chord_prog,
            seed_pool_path    = seed_pool_path,
        )

        # 3. Run all 10 generators with offset seeds for independence
        kick_gen  = KickGenerator(ctx, self._make_rng(ctx, 0))
        perc_gen  = PercussionGenerator(ctx, self._make_rng(ctx, 1))
        bass_gen  = BassGenerator(ctx, self._make_rng(ctx, 2))
        mel_gen   = MelodyGenerator(ctx, self._make_rng(ctx, 3))

        # Run melody first -- chords, pad, texture consume melody notes
        kick_notes  = kick_gen.generate()
        perc_notes  = perc_gen.generate()
        bass_notes  = bass_gen.generate()
        mel_notes   = mel_gen.generate()

        # Pass melody notes to generators that need Harmonic Supersymmetry
        chord_gen   = ChordsGenerator(ctx, self._make_rng(ctx, 4), melody_notes=mel_notes)
        pad_gen     = PadGenerator(ctx, self._make_rng(ctx, 5), melody_notes=mel_notes)
        arp_gen     = ArpGenerator(ctx, self._make_rng(ctx, 6))
        stab_gen    = StabsGenerator(ctx, self._make_rng(ctx, 7))
        tex_gen     = TextureGenerator(ctx, self._make_rng(ctx, 8), melody_notes=mel_notes)
        fx_gen      = FXGenerator(ctx, self._make_rng(ctx, 9))

        chord_notes  = chord_gen.generate()
        pad_notes    = pad_gen.generate()
        arp_notes    = arp_gen.generate()
        stab_notes   = stab_gen.generate()
        tex_notes    = tex_gen.generate()
        fx_notes     = fx_gen.generate()

        # 4. Assemble raw tracks dict (ordered for MIDI track index stability)
        tracks: Dict[str, List[Note]] = OrderedDict([
            ('01_Kick',       kick_notes),
            ('02_Percussion', perc_notes),
            ('03_Bass',       bass_notes),
            ('04_Melody',     mel_notes),
            ('05_Chords',     chord_notes),
            ('06_Pad',        pad_notes),
            ('07_Arp',        arp_notes),
            ('08_Stabs',      stab_notes),
            ('09_Texture',    tex_notes),
            ('10_FX',         fx_notes),
        ])

        # 5. Global micro-timing humanization (stems 3-9, drums are skipped)
        humanizer = MicroTimingHumanizer(
            bpm       = ctx.bpm,
            seed      = ctx.seed_value,
            max_ms    = 12.0,
            vel_range = 8,
            intensity = config.humanize_amount,
        )
        for name in _HUMANIZE_TRACK_NAMES:
            tracks[name] = humanizer.humanize_track(tracks[name], name)

        # 6. Quantize all tracks to 1/64th-note grid
        tracks = quantize_tracks(tracks)

        # 7. Phase alignment -- clip all tails to loop boundary
        total_beats = total_bars * ctx.bar_beats
        tracks = align_all_tracks(tracks, total_beats, mode='clip')

        # 8. EDM cipher post-processing (sidechain, build-up, void, fake-out, sweep)
        cc_events: list     = []
        pitch_events: list  = []
        if ctx.genre in ('edm', 'house') and EDM_CIPHERS_AVAILABLE:
            tracks, cc_events, pitch_events = self._apply_edm_ciphers(
                tracks, ctx, config
            )

        # 9. Build instrument program mapping
        instr = GENRE_INSTRUMENTS.get(config.genre, {})
        track_info = {
            '01_Kick':       {'channel': 9,  'program': 0},
            '02_Percussion': {'channel': 9,  'program': 0},
            '03_Bass':       {'channel': 0,  'program': instr.get('bass',   38)},
            '04_Melody':     {'channel': 1,  'program': instr.get('lead',   80)},
            '05_Chords':     {'channel': 2,  'program': instr.get('chords', 89)},
            '06_Pad':        {'channel': 3,  'program': instr.get('pad',    95)},
            '07_Arp':        {'channel': 4,  'program': instr.get('arp',    81)},
            '08_Stabs':      {'channel': 5,  'program': instr.get('lead',   80)},
            '09_Texture':    {'channel': 6,  'program': instr.get('lead',   80)},
            '10_FX':         {'channel': 7,  'program': 119},   # 119 = Synth Drum
        }

        # 'config' sub-dict keeps backward compatibility with export_midi()
        # and batch_commander.py which reads comp["config"]["bpm"].
        return {
            'config': {
                'bpm':        round(ctx.bpm, 1),
                'genre':      ctx.genre,
                'key':        f"{ctx.key_root} {ctx.scale_name}",
                'complexity': config.complexity,
            },
            'tracks':            tracks,
            'track_info':        track_info,
            'bpm':               ctx.bpm,
            'total_bars':        ctx.total_bars,
            'duration_seconds':  round(ctx.total_bars * ctx.bar_beats * 60.0 / ctx.bpm, 2),
            'structure':         structure,
            'chord_progression': chord_prog,
            'cc_events':         cc_events,
            'pitch_events':      pitch_events,
            'key':               f"{ctx.key_root} {ctx.scale_name}",
            'genre':             ctx.genre,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_rng(ctx: SharedContext, track_index: int) -> random.Random:
        """
        Create a seeded random.Random for one track generator.

        Adding track_index to the seed ensures each generator is independent
        while remaining fully reproducible from the same master seed.
        """
        return random.Random(ctx.seed_value + track_index)

    def _apply_edm_ciphers(
        self,
        tracks: dict,
        ctx: SharedContext,
        config: CompositionConfig,
    ) -> Tuple[dict, list, list]:
        """
        Apply all 5 EDM production ciphers to the assembled tracks.

        Returns (modified_tracks, cc_events, pitch_events).
        """
        cc_events: list    = []
        pitch_events: list = []

        structure  = ctx.structure
        total_bars = ctx.total_bars
        bpm        = ctx.bpm
        seed       = ctx.seed_value

        # Cipher 1 -- Sidechain CC11 pump
        kick_times = [n[0] for n in tracks['01_Kick']]
        cc_events += SidechainMatrix.generate_cc(kick_times, total_bars)

        # Cipher 5 -- Polyrhythmic filter sweep CC74
        cc_events += PolyrhythmicFilterSweep.generate_cc(total_bars)

        # Cipher 2 -- Stochastic build-up (replaces build-section drums)
        _DROP_LIKE = frozenset({'drop', 'chorus'})
        bar_cur = 0
        for idx, (stype, sbars) in enumerate(structure):
            if (stype == 'build' and idx + 1 < len(structure)
                    and structure[idx + 1][0] in _DROP_LIKE):
                bu = StochasticBuildUp.generate(bar_cur, sbars, bpm)
                bu_s = bar_cur * 4.0
                bu_e = (bar_cur + sbars) * 4.0
                # Replace build-section kick and perc with the stochastic pattern
                tracks['01_Kick']       = [n for n in tracks['01_Kick']
                                            if not (bu_s <= n[0] < bu_e)]
                tracks['02_Percussion'] = [n for n in tracks['02_Percussion']
                                            if not (bu_s <= n[0] < bu_e)]
                tracks['01_Kick']       += bu['kick']
                tracks['02_Percussion'] += bu['perc']
                pitch_events            += bu['pitch_events']
            bar_cur += sbars

        # Cipher 3 -- Pre-Drop Void (mutes key stems 1-2 beats before drop)
        tracks = PreDropVoid.apply(tracks, structure)

        # Cipher 4 -- Anti-Drop Fake-Out (20% chance of minimalist drop entry)
        tracks = AntiDropFakeOut.apply(tracks, structure, seed=seed)

        return tracks, cc_events, pitch_events
