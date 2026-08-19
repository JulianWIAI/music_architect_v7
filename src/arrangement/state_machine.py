"""
src/arrangement/state_machine.py
─────────────────────────────────
Section-level state machine for song arrangement.

``SongStateMachine`` drives the coarse song structure by:

1. Tracking which section is currently active and how many bars remain in it.
2. Using the genre's Markov transition matrix (from ``section_constants``) to
   stochastically pick the next section when the bar counter expires.
3. Signalling the caller when a fill window opens (2 bars before a transition).

The machine is intentionally decoupled from the bar clock — callers must
invoke ``advance_bar()`` exactly once per bar of audio/MIDI generation.

No section data is duplicated here: the ``DEFAULT_TRANSITIONS`` and
``SECTION_BAR_RANGES`` dicts are imported directly from ``section_constants``.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional, TYPE_CHECKING

from src.arrangement.section_constants import DEFAULT_TRANSITIONS, SECTION_BAR_RANGES

if TYPE_CHECKING:
    from src.midi.genre_profiles import GenreProfile


# Number of bars before a transition where ``should_fill()`` becomes True.
_FILL_WINDOW_BARS: int = 2


class SongStateMachine:
    """
    Finite-state machine over song sections driven by Markov transitions.

    Each state (section) has an associated bar count drawn from the
    ``GenreProfile.section_bars`` dict or from ``SECTION_BAR_RANGES`` as a
    fallback.  When the bar counter reaches zero the machine samples the next
    section from the genre's transition probability row.

    Parameters
    ----------
    genre : str
        Genre key, must match a key in ``DEFAULT_TRANSITIONS``.  Falls back
        to ``"pop"`` if the genre is not found.
    seed : int | None
        Random seed for reproducible section ordering.
    """

    def __init__(self, genre: str, seed: Optional[int] = None) -> None:
        # Resolve transition matrix; fall back to 'pop' for unknown genres.
        if genre in DEFAULT_TRANSITIONS:
            self._transitions: Dict[str, Dict[str, float]] = DEFAULT_TRANSITIONS[genre]
        else:
            self._transitions = DEFAULT_TRANSITIONS.get("pop", {})

        self._rng = random.Random(seed)

        # Start in the intro section.
        self._section: str = "intro"
        # Default bar length for intro (will be overridden by first get_section_length call).
        self._bars_left: int = SECTION_BAR_RANGES.get("intro", (4, 8))[1]

        # Track whether the song has reached a terminal state.
        self._finished: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def current_section(self) -> str:
        """Return the name of the currently active section."""
        return self._section

    def bars_remaining(self) -> int:
        """
        Return how many bars remain in the current section.

        This value is decremented by each call to ``advance_bar()``.
        """
        return self._bars_left

    def advance_bar(self) -> Optional[str]:
        """
        Decrement the bar counter by one.

        When the counter reaches zero the machine transitions to the next
        section (selected via the Markov matrix) and returns the new section
        name.  Returns ``None`` when still within the current section.

        If the machine has already reached a terminal state (``"outro"`` with
        no outgoing transitions) subsequent calls return ``None`` and have no
        effect.
        """
        if self._finished:
            return None

        self._bars_left = max(0, self._bars_left - 1)

        if self._bars_left > 0:
            return None

        # Bar counter expired — pick the next section.
        next_section = self._sample_transition(self._section)

        if next_section is None:
            # Terminal state reached (empty transition dict, e.g. "outro").
            self._finished = True
            return None

        self._section = next_section
        # Reset bar counter using SECTION_BAR_RANGES midpoint as default.
        lo, hi = SECTION_BAR_RANGES.get(next_section, (8, 16))
        self._bars_left = (lo + hi) // 2

        return next_section

    def force_transition(self, target: str) -> None:
        """
        Immediately jump to *target* section, resetting the bar counter.

        Useful for manual override from the GUI or test harness.
        Clears the ``_finished`` flag so the machine can continue after
        a forced transition even from a terminal state.
        """
        self._section = target
        lo, hi = SECTION_BAR_RANGES.get(target, (8, 16))
        self._bars_left = (lo + hi) // 2
        self._finished = False

    def should_fill(self) -> bool:
        """
        Return ``True`` when a fill should be triggered.

        A fill is appropriate when exactly ``_FILL_WINDOW_BARS`` bars remain
        before the current section ends, giving the fill generator time to
        prepare the transition event.
        """
        return self._bars_left <= _FILL_WINDOW_BARS and not self._finished

    def get_section_length(
        self, section: str, profile: "GenreProfile"
    ) -> int:
        """
        Resolve the bar length for *section* using the given profile.

        Priority:
        1. ``profile.section_bars[section]`` if present.
        2. Midpoint of ``SECTION_BAR_RANGES[section]`` if present.
        3. 8 bars as a safe fallback.

        Parameters
        ----------
        section : str
            The section name to look up.
        profile : GenreProfile
            Active genre profile whose ``section_bars`` dict is consulted first.
        """
        # Profile-specific override takes priority.
        if section in profile.section_bars:
            return profile.section_bars[section]

        # Fallback to SECTION_BAR_RANGES midpoint.
        if section in SECTION_BAR_RANGES:
            lo, hi = SECTION_BAR_RANGES[section]
            return (lo + hi) // 2

        return 8  # generic safe default

    def is_finished(self) -> bool:
        """Return True once the machine has reached a terminal section."""
        return self._finished

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sample_transition(self, section: str) -> Optional[str]:
        """
        Sample the next section from the transition matrix row for *section*.

        Returns ``None`` when there are no outgoing transitions (terminal state).
        """
        row = self._transitions.get(section, {})
        if not row:
            return None

        keys = list(row.keys())
        weights = [row[k] for k in keys]
        return self._rng.choices(keys, weights=weights, k=1)[0]
