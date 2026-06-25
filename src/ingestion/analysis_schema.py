"""
Typed contract for incoming analysis JSON files produced by the analysis pipeline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class SectionBoundary:
    type: str
    start_bar: int
    end_bar: int


@dataclass
class GenreMetadata:
    assigned_genre_cluster: str
    bpm_estimate: float
    user_genre_override: Optional[str] = None
    confidence: float = 1.0
    is_percussive: bool = False


@dataclass
class RhythmBlock:
    bpm: float
    time_signature: str = "4/4"
    kick_pattern: List[int] = field(default_factory=lambda: [1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0])
    snare_pattern: List[int] = field(default_factory=lambda: [0,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0])
    hihat_pattern: List[int] = field(default_factory=lambda: [1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0])
    syncopation_score: float = 0.0
    groove_type: str = "straight"
    energy_profile: List[float] = field(default_factory=list)


@dataclass
class HarmonyBlock:
    key: str
    scale_type: str
    root_note: str
    chord_sequence: List[str] = field(default_factory=list)
    harmonic_complexity: float = 0.5
    avg_chord_duration_bars: int = 4
    section_boundaries: List[SectionBoundary] = field(default_factory=list)


@dataclass
class AnalysisJSON:
    file_id: str
    genre_metadata: GenreMetadata
    rhythm: RhythmBlock
    harmony: HarmonyBlock


def _parse_section_boundary(raw: dict) -> SectionBoundary:
    return SectionBoundary(
        type=raw["type"],
        start_bar=int(raw["start_bar"]),
        end_bar=int(raw["end_bar"]),
    )


def _parse_rhythm(raw: dict) -> RhythmBlock:
    return RhythmBlock(
        bpm=float(raw["bpm"]),
        time_signature=raw.get("time_signature", "4/4"),
        kick_pattern=raw.get("kick_pattern", [1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0]),
        snare_pattern=raw.get("snare_pattern", [0,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0]),
        hihat_pattern=raw.get("hihat_pattern", [1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0]),
        syncopation_score=float(raw.get("syncopation_score", 0.0)),
        groove_type=raw.get("groove_type", "straight"),
        energy_profile=raw.get("energy_profile", []),
    )


def _parse_harmony(raw: dict) -> HarmonyBlock:
    boundaries = [_parse_section_boundary(b) for b in raw.get("section_boundaries", [])]
    return HarmonyBlock(
        key=raw["key"],
        scale_type=raw.get("scale_type", "major"),
        root_note=raw.get("root_note", raw["key"].split()[0]),
        chord_sequence=raw.get("chord_sequence", []),
        harmonic_complexity=float(raw.get("harmonic_complexity", 0.5)),
        avg_chord_duration_bars=int(raw.get("avg_chord_duration_bars", 4)),
        section_boundaries=boundaries,
    )


def _parse_genre_metadata(raw: dict) -> GenreMetadata:
    return GenreMetadata(
        assigned_genre_cluster=raw["assigned_genre_cluster"],
        bpm_estimate=float(raw.get("bpm_estimate", 120.0)),
        user_genre_override=raw.get("user_genre_override") or None,
        confidence=float(raw.get("confidence", 1.0)),
        is_percussive=bool(raw.get("is_percussive", False)),
    )


def load_analysis_json(path: Path) -> AnalysisJSON:
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return AnalysisJSON(
        file_id=raw.get("file_id", path.stem),
        genre_metadata=_parse_genre_metadata(raw["genre_metadata"]),
        rhythm=_parse_rhythm(raw["rhythm"]),
        harmony=_parse_harmony(raw["harmony"]),
    )


def validate_analysis_json(raw: dict) -> List[str]:
    """Return list of validation error strings; empty list means valid."""
    errors: List[str] = []
    for top in ("genre_metadata", "rhythm", "harmony"):
        if top not in raw:
            errors.append(f"Missing top-level key: '{top}'")
    gm = raw.get("genre_metadata", {})
    if "assigned_genre_cluster" not in gm:
        errors.append("genre_metadata.assigned_genre_cluster is required")
    rh = raw.get("rhythm", {})
    if "bpm" not in rh:
        errors.append("rhythm.bpm is required")
    ha = raw.get("harmony", {})
    if "key" not in ha:
        errors.append("harmony.key is required")
    return errors
