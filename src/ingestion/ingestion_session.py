"""
Orchestrates a batch generation session driven by analysis JSON files.

One AnalysisJSON file produces *compositions_per_file* MIDI outputs,
each seeded deterministically from the top-scored seeds.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.composition.composition_config import CompositionConfig
from src.composition.composition_engine import CompositionEngine
from src.ingestion.analysis_schema import AnalysisJSON
from src.ingestion.directory_scanner import load_all_analysis_files
from src.ingestion.seed_matcher import resolve_genre, select_top_seeds
from src.ingestion.structure_builder import build_structure_from_harmony

logger = logging.getLogger(__name__)


@dataclass
class SessionResult:
    analysis_path: Path
    file_id: str
    genre: str
    outputs: List[Path] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return len(self.outputs)

    @property
    def failed_count(self) -> int:
        return len(self.errors)


class IngestionSession:
    """
    Drives a multi-file, multi-composition batch generation session.

    Usage::

        session = IngestionSession(engine, output_dir="out/", compositions_per_file=10)
        results = session.run_directory("analysis_jsons/")
    """

    def __init__(
        self,
        engine: CompositionEngine,
        output_dir: str | Path = "output",
        compositions_per_file: int = 10,
    ):
        self.engine = engine
        self.output_dir = Path(output_dir)
        self.compositions_per_file = compositions_per_file

    # ── Public API ───────────────────────────────────────────────────────────

    def run_directory(
        self, directory: str | Path, skip_invalid: bool = True
    ) -> List[SessionResult]:
        """Process every valid analysis JSON in *directory*."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if not self.engine._loaded:
            self.engine.load_seeds()

        file_pairs = load_all_analysis_files(directory, skip_invalid=skip_invalid)
        logger.info("Starting ingestion session: %d files", len(file_pairs))

        results: List[SessionResult] = []
        for path, analysis in file_pairs:
            results.append(self.run_single(path, analysis))
        return results

    def run_single(self, path: Path, analysis: AnalysisJSON) -> SessionResult:
        """Produce *compositions_per_file* MIDI files from one analysis document."""
        genre = resolve_genre(analysis)
        result = SessionResult(analysis_path=path, file_id=analysis.file_id, genre=genre)

        top_seeds = select_top_seeds(
            self.engine.seeds, analysis, genre, top_n=20
        )
        if not top_seeds:
            msg = f"No seeds found for genre '{genre}' in {path}"
            logger.warning(msg)
            result.errors.append(msg)
            return result

        structure = build_structure_from_harmony(analysis.harmony)

        for index in range(self.compositions_per_file):
            try:
                out_path = self._compose_one(analysis, genre, top_seeds, structure, index)
                result.outputs.append(out_path)
                logger.info("  [%d/%d] %s", index + 1, self.compositions_per_file, out_path.name)
            except Exception as exc:
                msg = f"Composition {index} failed for {path}: {exc}"
                logger.error(msg)
                result.errors.append(msg)

        return result

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _compose_one(
        self,
        analysis: AnalysisJSON,
        genre: str,
        top_seeds: List[Dict[str, Any]],
        structure: list,
        index: int,
    ) -> Path:
        seed = top_seeds[index % len(top_seeds)]
        seed_bpm = float(
            seed.get("instrument_patterns", {}).get("bpm")
            or seed.get("dna", {}).get("bpm", 120)
        )
        config = self._build_config(analysis, genre, seed, seed_bpm, structure, index)

        output_name = f"{analysis.file_id}_{genre}_{index:02d}.mid"
        output_path = self.output_dir / output_name

        midi_data = self.engine.compose(config)
        if hasattr(midi_data, "writeFile"):
            with open(output_path, "wb") as fh:
                midi_data.writeFile(fh)
        else:
            import mido
            midi_data.save(str(output_path))

        return output_path

    def _build_config(
        self,
        analysis: AnalysisJSON,
        genre: str,
        seed: Dict[str, Any],
        seed_bpm: float,
        structure: list,
        index: int,
    ) -> CompositionConfig:
        ha = analysis.harmony
        rh = analysis.rhythm

        complexity = round(5 + ha.harmonic_complexity * 5)
        mutation = min(0.8, 0.10 + index * 0.08)
        humanize_amount = 0.7 if rh.syncopation_score > 0.4 else 0.4
        seed_value = (int(seed_bpm * 100) + index * 1337) % 999_999

        key_str = ha.key
        starting_chord = ha.chord_sequence[0] if ha.chord_sequence else None

        cfg = CompositionConfig(
            genre=genre,
            bpm=rh.bpm,
            key=key_str,
            starting_chord=starting_chord,
            complexity=complexity,
            mutation=mutation,
            humanize_amount=humanize_amount,
            seed_value=seed_value,
            structure_override=structure if structure else None,
        )
        return cfg
