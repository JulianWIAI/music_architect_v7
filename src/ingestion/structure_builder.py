"""
Converts SectionBoundary lists from HarmonyBlock into the
List[Tuple[str, int]] structure format consumed by CompositionEngine.
"""

from __future__ import annotations

from typing import List, Tuple

from src.ingestion.analysis_schema import HarmonyBlock, SectionBoundary

_KNOWN_TYPES = {
    "intro", "verse", "pre_chorus", "prechorus", "chorus", "bridge",
    "build", "drop", "break", "climax", "tension", "resolution",
    "outro", "coda", "exposition", "development", "recapitulation",
}

_TYPE_ALIASES = {
    "pre-chorus": "pre_chorus",
    "prechorus": "pre_chorus",
    "hook": "chorus",
    "refrain": "chorus",
    "interlude": "bridge",
    "breakdown": "break",
    "buildup": "build",
    "drop": "drop",
    "ending": "outro",
    "opening": "intro",
    "beginning": "intro",
}


def _map_section_type(raw_type: str) -> str:
    t = raw_type.lower().strip().replace(" ", "_")
    if t in _KNOWN_TYPES:
        return t
    return _TYPE_ALIASES.get(t, "verse")


def section_boundaries_to_structure(
    boundaries: List[SectionBoundary],
) -> List[Tuple[str, int]]:
    """
    Convert a list of SectionBoundary objects to (section_type, bars) pairs.
    Bar counts are derived from end_bar - start_bar; sections with 0 bars
    are silently dropped.
    """
    structure: List[Tuple[str, int]] = []
    for sb in boundaries:
        bars = sb.end_bar - sb.start_bar
        if bars <= 0:
            continue
        section_type = _map_section_type(sb.type)
        structure.append((section_type, bars))
    return structure


def build_structure_from_harmony(harmony: HarmonyBlock) -> List[Tuple[str, int]]:
    """
    Build a structure list from a HarmonyBlock's section_boundaries.
    Ensures at least an intro and outro exist.
    """
    if not harmony.section_boundaries:
        return []
    structure = section_boundaries_to_structure(harmony.section_boundaries)
    return _ensure_intro_outro(structure)


def _ensure_intro_outro(
    structure: List[Tuple[str, int]],
) -> List[Tuple[str, int]]:
    """
    Guarantee the structure starts with 'intro' and ends with 'outro'.
    Inserts minimal 4-bar sections only when completely absent.
    """
    if not structure:
        return [("intro", 4), ("verse", 16), ("outro", 4)]

    if structure[0][0] != "intro":
        structure = [("intro", 4)] + structure
    if structure[-1][0] != "outro":
        structure = structure + [("outro", 4)]
    return structure
