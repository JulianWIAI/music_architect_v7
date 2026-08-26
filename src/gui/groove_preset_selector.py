"""
src/gui/groove_preset_selector.py
──────────────────────────────────
Named groove preset selector widget for the Groove & Mix panel.

Wraps NamedGroovePresetLibrary to expose multiple named groove feels per
genre (e.g. Techno: Minimal / Hard Industrial / Detroit / Hypnotic).

Public API
──────────
GroovePresetSelector(parent, styles, on_change_fn=None)
    set_genre(genre: str) -> None
        Repopulate the combobox with preset names for the new genre.
        Called by app.py whenever the user changes the genre control.
    get_settings() -> SongGrooveSettings | None
        Returns the SongGrooveSettings for the currently selected preset,
        or None if no genre has been set.
    get_preset_name() -> str
        Returns the display string currently shown in the combobox.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from src.midi.groove_presets import NamedGroovePresetLibrary
from src.midi.groove_settings import SongGrooveSettings


# ── Short one-line descriptions shown next to the combobox ───────────────────
# Keys are preset names exactly as stored in _NAMED_PRESETS.

_DESCRIPTIONS: dict[str, str] = {
    'Standard':       'Grid-locked, balanced dynamics',
    'Dark Memphis':   'Deeper pocket, compressed lows',
    'Melodic Trap':   'Lighter feel, melodic emphasis',
    'Phonk Trap':     'Extreme sub pocket, maximum lag',
    'Minimal':        'Hypnotic locked grid, light velocity',
    'Hard Industrial':'Maximum aggression, high contrast',
    'Detroit':        'Slight shuffle, organic feel',
    'Hypnotic':       'Soft dynamics, slow-building tension',
    'Deep Chill':     'Laid-back swing, warm pocket',
    'Tech House':     'Tight, minimal swing',
    'Classic House':  'Lush swing, full chord presence',
    'Boom Bap':       'Heavy swing, punchy emphasis',
    'Lo-Fi Chill':    'Loose vintage feel, low velocity',
    'Modern Rap':     'Tight trap-influenced, clean grid',
    'Classic Drift':  'Dark Memphis compression',
    'Brazilian Rave': 'Hard and fast, extreme energy',
    'Slowed Chopped': 'Maximum pocket, slow drag',
    'Festival':       'Massive upfront energy',
    'Future Bass':    'Melodic, lush dynamics',
    'Progressive':    'Structured, building arrangement',
    'Radio Hit':      'Bright and forward',
    'Indie':          'Organic human feel',
    'Dance Pop':      'Energetic, driving',
    'Default':        'Genre default settings',
}


class GroovePresetSelector(tk.Frame):
    """
    Compact single-row widget for selecting a named groove feel preset.

    Placed inside the Groove & Mix panel, directly beneath the genre
    selector.  When the user picks a preset the optional *on_change_fn*
    is called with the resulting SongGrooveSettings so the caller can
    apply the groove immediately.

    Parameters
    ----------
    parent : tk.Widget
        Parent widget.
    styles : object
        App styles namespace (S).  Must expose BG2, FN_X, TXT_DIM,
        BG_INPUT, TXT_BRT.
    on_change_fn : callable, optional
        Called with (SongGrooveSettings) whenever the selection changes.
    """

    def __init__(
        self,
        parent: tk.Widget,
        styles,
        on_change_fn: Optional[Callable[[SongGrooveSettings], None]] = None,
    ) -> None:
        S = styles
        super().__init__(parent, bg=S.BG2)
        self._S           = S
        self._lib         = NamedGroovePresetLibrary()
        self._genre: str  = ''
        self._var         = tk.StringVar(value='Default')
        self._on_change_fn = on_change_fn

        self._build_ui()

    # ── Public API ───────────────────────────────────────────────────────────

    def set_genre(self, genre: str) -> None:
        """
        Repopulate the combobox with named presets for *genre*.

        If the genre has no named presets the combobox is set to a single
        'Default' entry.  The description label is updated silently without
        firing the external on_change_fn.
        """
        self._genre = genre.lower()
        names = self._lib.genre_names(self._genre)

        if not names:
            self._combo['values'] = ['Default']
            self._var.set('Default')
            self._update_description('Default')
            return

        self._combo['values'] = names
        self._var.set(names[0])
        self._update_description(names[0])

    def get_settings(self) -> Optional[SongGrooveSettings]:
        """
        Return SongGrooveSettings for the currently selected preset.

        Returns None if no genre has been set yet.
        """
        if not self._genre:
            return None
        name = self._var.get()
        if name == 'Default' or not name:
            return None
        return self._lib.get_named(self._genre, name)

    def get_preset_name(self) -> str:
        """Return the display string currently shown in the combobox."""
        return self._var.get()

    # ── Construction ─────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        S = self._S

        # "FEEL" label — fixed width so the combobox aligns with other rows
        tk.Label(
            self,
            text='FEEL',
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG2,
            width=5,
            anchor='w',
        ).pack(side='left', padx=(0, 4))

        # Preset combobox
        self._combo = ttk.Combobox(
            self,
            textvariable=self._var,
            state='readonly',
            width=22,
            font=S.FN_X,
        )
        self._combo['values'] = ['Default']
        self._combo.pack(side='left', padx=(0, 6))
        self._combo.bind('<<ComboboxSelected>>', self._on_change)

        # Description label — italic, dimmed, updates on selection
        self._desc_lbl = tk.Label(
            self,
            text=_DESCRIPTIONS.get('Default', ''),
            font=(S.FN_X[0], S.FN_X[1], 'italic') if len(S.FN_X) == 2
                 else (S.FN_X[0], S.FN_X[1], 'italic'),
            fg=S.TXT_DIM,
            bg=S.BG2,
            anchor='w',
        )
        self._desc_lbl.pack(side='left', fill='x', expand=True)

        # Apply combobox field styling if BG_INPUT is available
        self._style_combobox()

    def _style_combobox(self) -> None:
        """Apply dark-theme field colours to the combobox via ttk.Style."""
        S = self._S
        style = ttk.Style(self)
        style_name = 'GrooveFeel.TCombobox'
        try:
            bg_input = S.BG_INPUT
            fg       = S.TXT_BRT if hasattr(S, 'TXT_BRT') else S.TXT_DIM
            style.configure(
                style_name,
                fieldbackground=bg_input,
                background=bg_input,
                foreground=fg,
                selectbackground=bg_input,
                selectforeground=fg,
            )
            self._combo.configure(style=style_name)
        except Exception:
            # Style application is cosmetic only; ignore failures gracefully.
            pass

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _on_change(self, event=None) -> None:
        """Handle combobox selection change."""
        name = self._var.get()
        self._update_description(name)
        if self._on_change_fn is not None:
            settings = self.get_settings()
            if settings is not None:
                self._on_change_fn(settings)

    def _update_description(self, name: str) -> None:
        """Update the description label for the given preset name."""
        desc = _DESCRIPTIONS.get(name, '')
        self._desc_lbl.config(text=desc)
