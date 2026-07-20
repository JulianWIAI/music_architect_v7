"""
phrase_boundaries.py -- Phrase boundary calculator for all section-aware generators.

Music Theory Context:
    A "phrase" in music is a complete musical thought, typically spanning 2 or 4
    bars.  Phrase boundaries mark the start/end of these thoughts and are the
    natural places to:
      - Change chord voicings
      - Restart pad sustain blocks
      - Accent the downbeat (crash, bass hit, stab)
      - Vary the melody rhythm

    Section boundaries are a special case: they mark major structural transitions
    (verse → chorus, build → drop).  The last bar before a section boundary is
    the "pickup" bar -- often treated with extra energy or a fill.

Data Model:
    Structure = List[Tuple[str, int]]  -- list of (section_name, bars) pairs
    PhraseBoundary namedtuple:
        beat        : absolute beat position of this boundary
        bar_index   : absolute bar index
        section_type: name of the section that starts here
        is_section  : True for major section boundaries, False for 4-bar phrase marks
        is_pickup   : True for the bar immediately BEFORE a section boundary
"""

from __future__ import annotations
from typing import List, NamedTuple, Tuple


class PhraseBoundary(NamedTuple):
    beat:         float   # absolute beat position
    bar_index:    int     # absolute bar index
    section_type: str     # section name at this boundary
    is_section:   bool    # True = major structural boundary
    is_pickup:    bool    # True = bar immediately before a section boundary


def compute_phrase_boundaries(
    structure: List[Tuple[str, int]],
    phrase_bars: int = 4,
    bar_beats:   float = 4.0,
) -> List[PhraseBoundary]:
    """
    Walk a song structure and return every phrase and section boundary.

    Parameters
    ----------
    structure   : list of (section_name, bars) pairs
    phrase_bars : how many bars constitute one phrase (default 4)
    bar_beats   : beats per bar (default 4.0 for 4/4 time)

    Returns
    -------
    Sorted list of PhraseBoundary objects covering the full song.
    """
    boundaries: List[PhraseBoundary] = []
    bar_index  = 0
    beat       = 0.0

    for sec_idx, (section_type, bars) in enumerate(structure):
        sec_start_bar  = bar_index
        sec_start_beat = beat

        # Major section boundary at the start of every section
        boundaries.append(PhraseBoundary(
            beat         = sec_start_beat,
            bar_index    = sec_start_bar,
            section_type = section_type,
            is_section   = True,
            is_pickup    = False,
        ))

        # 4-bar phrase marks within the section (skip the first -- already added above)
        for phrase_bar in range(phrase_bars, bars, phrase_bars):
            boundaries.append(PhraseBoundary(
                beat         = sec_start_beat + phrase_bar * bar_beats,
                bar_index    = sec_start_bar  + phrase_bar,
                section_type = section_type,
                is_section   = False,
                is_pickup    = False,
            ))

        # Pickup bar: the last bar of this section, if a new section follows
        if sec_idx < len(structure) - 1:
            pickup_bar  = bars - 1
            pickup_beat = sec_start_beat + pickup_bar * bar_beats
            # Only mark if not already the section boundary itself
            if pickup_bar > 0:
                boundaries.append(PhraseBoundary(
                    beat         = pickup_beat,
                    bar_index    = sec_start_bar + pickup_bar,
                    section_type = section_type,
                    is_section   = False,
                    is_pickup    = True,
                ))

        bar_index += bars
        beat       = bar_index * bar_beats

    # Sort by beat position; remove duplicate beats (section + pickup can collide for 1-bar sections)
    seen_beats: set = set()
    unique: List[PhraseBoundary] = []
    for b in sorted(boundaries, key=lambda x: (x.beat, not x.is_section)):
        if b.beat not in seen_beats:
            unique.append(b)
            seen_beats.add(b.beat)

    return unique


def bars_in_section(structure: List[Tuple[str, int]], section_name: str) -> List[int]:
    """
    Return a list of all bar counts for sections with the given name.

    Useful for querying how long each 'verse' is when there are multiple verses.
    """
    return [bars for stype, bars in structure if stype == section_name]


def section_start_beats(structure: List[Tuple[str, int]],
                        bar_beats: float = 4.0) -> dict:
    """
    Return a dict mapping section_type to the list of absolute beat positions
    where sections of that type begin.

    Example:
        {'intro': [0.0], 'verse': [8.0, 40.0], 'chorus': [24.0, 56.0], ...}
    """
    result: dict = {}
    beat = 0.0
    for section_type, bars in structure:
        if section_type not in result:
            result[section_type] = []
        result[section_type].append(beat)
        beat += bars * bar_beats
    return result


def total_bars(structure: List[Tuple[str, int]]) -> int:
    """Sum all bar counts across the structure."""
    return sum(bars for _, bars in structure)


def beat_to_bar(beat: float, bar_beats: float = 4.0) -> int:
    """Convert an absolute beat position to a bar index (0-based)."""
    return int(beat / bar_beats)


def bar_section(bar_index: int,
                structure: List[Tuple[str, int]]) -> Tuple[str, int]:
    """
    Return (section_type, bar_within_section) for a given absolute bar index.

    Raises ValueError if bar_index is beyond the total song length.
    """
    cursor = 0
    for section_type, bars in structure:
        if cursor <= bar_index < cursor + bars:
            return section_type, bar_index - cursor
        cursor += bars
    raise ValueError(f"bar_index {bar_index} is past end of structure (total={cursor} bars)")
