"""
src.gui.instrument_description_label
--------------------------------------
A lightweight Tkinter widget that shows a live sound-character description
for whichever GM instrument is currently selected in a combobox.

Pedagogical purpose
-------------------
When a student selects "81: Sawtooth Lead" they see a clipped hint on the row:

    "Sawtooth lead · bright, cutting…"

And hovering over the label (or the combobox) pops a full tooltip:

    "Sawtooth lead · bright, cutting, full harmonics — machine-like, electronic"

That one-liner tells them whether to look for something organic or
synthetic, bright or dark, and gives a quick context anchor so they can
match it to a plugin or hardware instrument they already know.

Usage
-----
    desc = InstrumentDescriptionLabel(row_frame, styles=S)
    desc.pack(side='left', padx=6, fill='x', expand=True)
    desc.attach(combobox)   # binding done here; updates on selection change

The label text is updated immediately on attach (reflects current value)
and again every time the user changes the combobox selection.
Both the label AND the attached combobox get a dynamic hover tooltip that
always shows the full (non-clipped) description text.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional

from src.composition.gm_descriptions import get_description, get_drum_description
from src.gui.tooltips import ToolTip


class InstrumentDescriptionLabel:
    """
    A tk.Label that tracks a GM instrument combobox and shows the
    sound-character description of the currently selected program.

    The visible label text is clipped to *max_chars* so it fits in a
    narrow track row.  Hovering over the label — or over the combobox
    it is attached to — pops a ToolTip with the full, unclipped text.

    Parameters
    ----------
    parent : tk.Frame
        The frame to pack the label into.
    styles : object
        The app Styles object; needs attributes FN_X, TXT_DIM, BG2.
    max_chars : int, optional
        Truncate the visible label to this many characters.  Default: 28.
        (Keeps it short enough not to push the row off-screen on a
        typical 1300 px window with the current left-panel layout.)
    """

    def __init__(
        self,
        parent: tk.Frame,
        styles,
        max_chars: int = 28,
        description_fn=None,
    ) -> None:
        self._max = max_chars
        # Caller can supply get_drum_description (or any int→str fn) for non-melodic tracks.
        self._desc_fn = description_fn if description_fn is not None else get_description
        self._full_text = ""          # always the complete, unclipped text

        self._label = tk.Label(
            parent,
            text="",
            font=styles.FN_X,
            fg=styles.TXT_DIM,
            bg=styles.BG2,
            anchor="w",
            justify="left",
        )
        # Wrap text to exactly the width allocated by the geometry manager.
        # Without this, tk.Label renders on a single line and is visually
        # clipped when the panel is narrower than the text.
        self._label.bind(
            "<Configure>",
            lambda e: self._label.configure(wraplength=e.width) if e.width > 1 else None,
        )
        # Tooltip starts empty; updated dynamically in _refresh().
        self._tooltip = ToolTip(self._label, "")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def pack(self, **kwargs) -> None:
        """Delegate pack() so the caller can position the label normally."""
        self._label.pack(**kwargs)

    def grid(self, **kwargs) -> None:
        """Delegate grid() layout as an alternative to pack."""
        self._label.grid(**kwargs)

    def attach(self, combobox: ttk.Combobox) -> None:
        """
        Bind this label to *combobox*.

        - Updates the label immediately to reflect the combobox's current
          value.
        - Subscribes to <<ComboboxSelected>> so the label updates whenever
          the user picks a different instrument.
        - Attaches a dynamic ToolTip to *combobox* itself so students can
          hover over the dropdown to read the full description without
          needing to find the label.
        """
        cb = combobox

        # Bind label refresh to combobox changes
        cb.bind("<<ComboboxSelected>>", lambda _e: self._refresh(cb), add="+")

        # Attach a ToolTip on the combobox that always shows the current
        # full description.  We keep a reference so _refresh() can update it.
        self._cb_tooltip = ToolTip(cb, "")

        # Initial update so the label shows something right after attach()
        self._refresh(cb)

    def update_from_program(self, program: int) -> None:
        """Manually set the description for a specific GM *program* (0-127)."""
        self._full_text = self._desc_fn(program)
        self._apply(self._full_text)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refresh(self, combobox: ttk.Combobox) -> None:
        """Read the current combobox value, update label and both tooltips."""
        raw = combobox.get()
        program = self._parse_program(raw)
        full = self._desc_fn(program) if program is not None else ""
        self._full_text = full
        self._apply(full)

    def _apply(self, full: str) -> None:
        """Push *full* text to the clipped label and update both tooltips."""
        self._label.config(text=self._clip(full))
        # ToolTip.text is a plain attribute — overwrite it directly
        self._tooltip.text = full
        if hasattr(self, "_cb_tooltip"):
            self._cb_tooltip.text = full

    @staticmethod
    def _parse_program(raw: str) -> Optional[int]:
        """
        Extract the GM program number from a 'prog: Name' combobox string.

        Returns None if parsing fails (empty string, malformed, etc.).
        """
        try:
            return int(raw.split(":")[0].strip())
        except (ValueError, IndexError, AttributeError):
            return None

    def _clip(self, text: str) -> str:
        """Truncate *text* to self._max characters, appending '…' if cut."""
        if len(text) <= self._max:
            return text
        return text[: self._max - 1] + "…"
