"""
context_manager.py -- Seed Engine: parses external MIDI databank seeds and locks
shared musical context (key, scale, motifs, BPM) for all 10 track generators.

Architecture Role:
    The ContextManager is the single source of truth shared across all 10
    TrackGenerator instances.  Every generator reads from it; none write to it.
    This prevents harmonic drift (generators accidentally drifting to different
    keys) and ensures rhythmic motifs are coherent across stems.

Data flow:
    1. BatchCommander passes a CompositionConfig + optional seed_pool JSON path
       to the Orchestrator.
    2. Orchestrator creates one ContextManager per track composition.
    3. ContextManager.load_from_config() resolves:
           - key_root   (string, e.g. 'C')
           - scale_name (string, e.g. 'minor')
           - scale_notes (list of MIDI pitch classes in 0..11)
           - bpm
           - total_bars
           - structure  (section list)
           - chord_progression (list of chord strings)
           - seed_value (int, drives all RNG in all generators)
    4. If a seed_pool JSON was injected, the golden matrices are loaded and
       made available for mutation-based generation.

Seed Pool Format (math_fitness_report.json):
    {
      "golden_matrices": [
        {"key": "Am", "scale": "minor", "bpm": 128, "chord_root": "A", ...},
        ...
      ]
    }
"""

from __future__ import annotations
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Re-use existing genre constants rather than duplicating them
from src.composition.genre_constants import (
    SCALE_INTERVALS, GENRE_BPM, GENRE_SCALES, get_scale_notes, NOTE_TO_MIDI,
)
from src.composition.composition_config import CompositionConfig


class SharedContext:
    """
    Immutable musical context shared by all 10 track generators.

    Attributes
    ----------
    key_root        : str   -- e.g. 'C', 'F#', 'Bb'
    scale_name      : str   -- e.g. 'minor', 'dorian'
    scale_notes     : list  -- MIDI pitch classes [0..11] for this key+scale
    scale_midi      : list  -- concrete MIDI notes spanning octaves 2-6
    bpm             : float
    total_bars      : int
    bar_beats       : float -- beats per bar (4.0 for 4/4)
    total_beats     : float -- total_bars * bar_beats
    structure       : list  -- [(section_type, bars), ...]
    chord_prog      : list  -- list of chord strings for the full song
    seed_value      : int   -- master RNG seed
    genre           : str
    vocal_mask      : bool
    complexity      : int   -- 1-10
    golden_matrices : list  -- top-N seeds from previous generation (may be [])
    mutation_factor : float -- how much to deviate from golden seeds (0.0-1.0)
    """

    def __init__(self, **kwargs: Any):
        # Musical key and scale
        self.key_root:    str   = kwargs.get('key_root',    'C')
        self.scale_name:  str   = kwargs.get('scale_name',  'minor')
        self.scale_notes: list  = kwargs.get('scale_notes', [])
        self.scale_midi:  list  = kwargs.get('scale_midi',  [])

        # Temporal
        self.bpm:         float = kwargs.get('bpm',         120.0)
        self.total_bars:  int   = kwargs.get('total_bars',  32)
        self.bar_beats:   float = kwargs.get('bar_beats',   4.0)
        self.total_beats: float = self.total_bars * self.bar_beats

        # Structure and harmony
        self.structure:   list  = kwargs.get('structure',   [])
        self.chord_prog:  list  = kwargs.get('chord_prog',  [])

        # Generation control
        self.seed_value:  int   = kwargs.get('seed_value',  0)
        self.genre:       str   = kwargs.get('genre',       'pop')
        self.vocal_mask:  bool  = kwargs.get('vocal_mask',  False)
        self.complexity:  int   = kwargs.get('complexity',  5)

        # Evolutionary injection
        self.golden_matrices: list  = kwargs.get('golden_matrices', [])
        self.mutation_factor: float = kwargs.get('mutation_factor', 0.0)


class ContextManager:
    """
    Resolves a CompositionConfig into a SharedContext and optionally
    injects golden matrices from a previous generation's fitness report.
    """

    def __init__(self):
        self._context: Optional[SharedContext] = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def load_from_config(
        self,
        config: CompositionConfig,
        structure: List[Tuple[str, int]],
        chord_progression: List[str],
        seed_pool_path: Optional[str] = None,
    ) -> SharedContext:
        """
        Build and cache the SharedContext from a CompositionConfig.

        Parameters
        ----------
        config            : CompositionConfig from batch_commander
        structure         : resolved song structure list
        chord_progression : Markov-generated chord string list
        seed_pool_path    : optional path to math_fitness_report.json

        Returns
        -------
        SharedContext populated with all musical context.
        """
        # --- Resolve key and scale -----------------------------------------
        key_string = config.key or 'C minor'
        parts      = key_string.split()
        key_root   = parts[0] if parts else 'C'
        scale_name = parts[1] if len(parts) > 1 else 'minor'

        # Numeric pitch classes for the key+scale combination
        scale_notes = get_scale_notes(key_root, scale_name)

        # Concrete MIDI notes spanning octaves 2-6 (C2=36 to B6=107)
        root_pc    = NOTE_TO_MIDI.get(key_root, 0)
        intervals  = SCALE_INTERVALS.get(scale_name, SCALE_INTERVALS['minor'])
        scale_midi = []
        for octave in range(2, 7):
            base = 24 + (octave - 2) * 12   # C2=36, C3=48, ...
            for interval in intervals:
                note = base + root_pc + interval
                if 24 <= note <= 107:
                    scale_midi.append(note)
        scale_midi = sorted(set(scale_midi))

        # --- Resolve BPM -------------------------------------------------------
        bpm = config.bpm or GENRE_BPM.get(config.genre, 120.0)

        # --- Resolve seed -------------------------------------------------------
        # Use config.seed_value if provided; otherwise derive from genre hash
        seed_value = (
            config.seed_value
            if config.seed_value is not None
            else abs(hash(config.genre + key_root))
        )

        # --- Load golden matrices (evolutionary injection) ----------------------
        golden_matrices = []
        mutation_factor = 0.0
        if seed_pool_path:
            golden_matrices, mutation_factor = self._load_golden_matrices(seed_pool_path)

        # --- Assemble context --------------------------------------------------
        total_bars = sum(bars for _, bars in structure)

        self._context = SharedContext(
            key_root        = key_root,
            scale_name      = scale_name,
            scale_notes     = list(scale_notes),
            scale_midi      = scale_midi,
            bpm             = bpm,
            total_bars      = total_bars,
            bar_beats       = 4.0,
            structure       = structure,
            chord_prog      = chord_progression,
            seed_value      = seed_value,
            genre           = config.genre,
            vocal_mask      = config.vocal_mask,
            complexity      = config.complexity,
            golden_matrices = golden_matrices,
            mutation_factor = mutation_factor,
        )
        return self._context

    @property
    def context(self) -> Optional[SharedContext]:
        """Return the most recently loaded SharedContext."""
        return self._context

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_golden_matrices(
        self, path: str
    ) -> Tuple[List[Dict], float]:
        """
        Parse a math_fitness_report.json produced by the telemetry grader.

        Returns (golden_matrices, mutation_factor).
        Returns ([], 0.0) if the file is missing or malformed.
        """
        p = Path(path)
        if not p.exists():
            return [], 0.0
        try:
            with open(p, 'r', encoding='utf-8') as fh:
                report = json.load(fh)
            golden = report.get('golden_matrices', [])
            # mutation_factor may be embedded in the report (set by batch_commander)
            mutation = float(report.get('mutation_factor', 0.05))
            return golden, mutation
        except Exception as e:
            print(f"[ContextManager] Failed to load seed pool '{path}': {e}")
            return [], 0.0

    def make_seeded_rng(self, offset: int = 0) -> random.Random:
        """
        Return a seeded random.Random instance for a track generator.

        Each generator should pass a unique offset (its track index 0-9)
        so that generators are statistically independent while still being
        deterministic from the shared seed.
        """
        if self._context is None:
            return random.Random(0)
        return random.Random(self._context.seed_value + offset)
