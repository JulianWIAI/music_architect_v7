"""
src.ingestion — data-ingestion framework for analysis-JSON-driven generation.

Public API::

    from src.ingestion import IngestionSession, load_analysis_json, scan_analysis_dir

    session = IngestionSession(engine, output_dir="out/", compositions_per_file=10)
    results = session.run_directory("analysis_jsons/")
"""

from src.ingestion.analysis_schema import (
    AnalysisJSON,
    GenreMetadata,
    HarmonyBlock,
    RhythmBlock,
    SectionBoundary,
    load_analysis_json,
    validate_analysis_json,
)
from src.ingestion.directory_scanner import load_all_analysis_files, scan_analysis_dir
from src.ingestion.ingestion_session import IngestionSession, SessionResult
from src.ingestion.seed_matcher import resolve_genre, score_seed, select_top_seeds
from src.ingestion.structure_builder import (
    build_structure_from_harmony,
    section_boundaries_to_structure,
)

__all__ = [
    "AnalysisJSON",
    "GenreMetadata",
    "HarmonyBlock",
    "RhythmBlock",
    "SectionBoundary",
    "load_analysis_json",
    "validate_analysis_json",
    "load_all_analysis_files",
    "scan_analysis_dir",
    "IngestionSession",
    "SessionResult",
    "resolve_genre",
    "score_seed",
    "select_top_seeds",
    "build_structure_from_harmony",
    "section_boundaries_to_structure",
]
