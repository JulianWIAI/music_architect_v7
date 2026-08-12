"""
src.gui.advisor_query_panel
-----------------------------
A collapsible panel in the ADVISOR tab that lets the user type in the
parameters of an *external* MIDI file — genre, BPM, key — and get the
full production advisor output (palettes, effect chains, gain staging,
BPM time values, …) without having to generate a new song.

Design rationale
----------------
Students who import a third-party MIDI into their DAW already know:
  • the genre  (e.g. trap)
  • the tempo  (e.g. 140 BPM)
  • the key    (e.g. A minor)

They do NOT need to run the composition engine — they just need the
advisor's recommendations for that genre/BPM/key combination.
AdvisorQueryPanel synthesises a minimal composition dict from those three
parameters and hands it straight to the advisor renderer.

Integration
-----------
Wire the panel into the advisor tab by passing two callbacks:
    update_advisor_fn  : Callable[[dict], None]
        The app's _update_advisor method; receives the synthetic comp dict.
    load_palettes_fn   : Callable[[str], None]
        The app's _load_palettes_for method; refreshes palette dropdowns
        to match the selected genre before the advisor renders.

Usage example (inside App._build_advisor_tab):
    query_panel = AdvisorQueryPanel(
        parent,
        styles             = S,
        update_advisor_fn  = self._update_advisor,
        load_palettes_fn   = self._load_palettes_for,
        log_fn             = self._log,
    )
    query_panel.pack(fill='x', padx=4, pady=(0, 2))
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional

from src.gui.collapsible_section import CollapsibleSection


# ── Genre / key constants ─────────────────────────────────────────────────────

_GENRES = [
    'pop', 'hiphop', 'trap', 'cinematic', 'classical',
    'techno', 'jpop', 'phonk', 'edm', 'house', 'dnb',
]

_NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# All scale / mode names supported by the engine (superset — genre_constants
# restricts which ones appear per genre, but the advisor only uses genre + BPM
# + key label so any name is valid here).
_MODES = [
    'major', 'minor', 'dorian', 'phrygian', 'lydian',
    'mixolydian', 'locrian', 'harmonic minor', 'melodic minor',
    'pentatonic major', 'pentatonic minor', 'blues',
]

_BPM_MIN, _BPM_MAX, _BPM_DEFAULT = 40, 240, 120


class AdvisorQueryPanel:
    """
    Collapsible query form: Genre + BPM + Key → Advisor output.

    The panel is collapsed by default so it does not distract users who
    have already generated a composition.  Expanding it reveals three
    inputs and a single "GET RECOMMENDATIONS" button.

    Parameters
    ----------
    parent : tk.Frame
        Parent container inside the ADVISOR tab.
    styles : object
        App styles object (attributes: BG2, FN_S, FN_X, FN_H, CYAN,
        TXT_DIM, GREEN, YELLOW, PINK, BG_BTN, BG_BTN_ACT, BG_BTN_HOV,
        BG_INPUT, TXT_BRT).
    update_advisor_fn : Callable[[dict], None]
        Called with a synthetic composition dict when the user clicks
        GET RECOMMENDATIONS.  Receives:
            {'config': {'genre': str, 'bpm': float, 'key': str}}
    load_palettes_fn : Callable[[str], None]
        Called with the selected genre string before update_advisor_fn
        so that the palette combobox is refreshed first.
    log_fn : Callable[[str], None], optional
        Log a status string to the app's log panel.
    """

    def __init__(
        self,
        parent: tk.Frame,
        *,
        styles,
        update_advisor_fn: Callable[[dict], None],
        load_palettes_fn: Callable[[str], None],
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._update_advisor = update_advisor_fn
        self._load_palettes  = load_palettes_fn
        self._log_fn         = log_fn
        self._S              = styles

        # Build a collapsible section so the form is hidden by default.
        self._cs = CollapsibleSection(
            parent,
            "QUERY WITHOUT GENERATION  (type in your MIDI's parameters)",
            styles.YELLOW,
            collapsed=True,
        )
        frame = self._cs.content_frame

        self._build_form(frame)

    # ------------------------------------------------------------------
    # Public layout delegation
    # ------------------------------------------------------------------

    def pack(self, **kwargs) -> None:
        """Re-specify pack layout on the CollapsibleSection's outer frame.

        CollapsibleSection packs its outer frame automatically in __init__,
        so this call overrides those defaults with caller-supplied values.
        """
        self._cs.outer.pack(**kwargs)

    # ------------------------------------------------------------------
    # Form construction
    # ------------------------------------------------------------------

    def _build_form(self, frame: tk.Frame) -> None:
        """Build the Genre / BPM / Key input row and the submit button."""
        S = self._S
        row = tk.Frame(frame, bg=S.BG2)
        row.pack(fill='x', pady=(2, 4))

        # ── Genre ─────────────────────────────────────────────────────
        tk.Label(
            row, text="GENRE", font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2
        ).pack(side='left', padx=(4, 2))

        self._genre_var = tk.StringVar(value='pop')
        genre_cb = ttk.Combobox(
            row,
            textvariable=self._genre_var,
            values=_GENRES,
            state='readonly',
            width=10,
            font=S.FN_X,
        )
        genre_cb.pack(side='left', padx=(0, 8))

        # ── BPM ───────────────────────────────────────────────────────
        tk.Label(
            row, text="BPM", font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2
        ).pack(side='left', padx=(0, 2))

        # Validate that only digits are typed
        vcmd = (frame.register(self._validate_bpm), '%P')
        self._bpm_var = tk.StringVar(value=str(_BPM_DEFAULT))
        bpm_entry = tk.Entry(
            row,
            textvariable=self._bpm_var,
            validate='key',
            validatecommand=vcmd,
            width=5,
            font=S.FN_X,
            fg=S.CYAN,
            bg=S.BG_INPUT,
            insertbackground=S.CYAN,
            relief='flat',
            bd=1,
        )
        bpm_entry.pack(side='left', padx=(0, 8))

        # ── Key root + mode ───────────────────────────────────────────
        tk.Label(
            row, text="KEY", font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2
        ).pack(side='left', padx=(0, 2))

        self._root_var = tk.StringVar(value='C')
        root_cb = ttk.Combobox(
            row,
            textvariable=self._root_var,
            values=_NOTES,
            state='readonly',
            width=4,
            font=S.FN_X,
        )
        root_cb.pack(side='left', padx=(0, 2))

        self._mode_var = tk.StringVar(value='major')
        mode_cb = ttk.Combobox(
            row,
            textvariable=self._mode_var,
            values=_MODES,
            state='readonly',
            width=16,
            font=S.FN_X,
        )
        mode_cb.pack(side='left', padx=(0, 12))

        # ── Submit button ─────────────────────────────────────────────
        btn = tk.Button(
            row,
            text="GET RECOMMENDATIONS",
            command=self._on_submit,
            font=S.FN_S,
            fg=S.YELLOW,
            bg=S.BG_BTN,
            activeforeground=S.TXT_BRT,
            activebackground=S.BG_BTN_ACT,
            bd=0,
            padx=8,
            pady=3,
            cursor='hand2',
            highlightthickness=1,
            highlightbackground=S.YELLOW,
        )
        btn.bind('<Enter>', lambda e: btn.configure(bg=S.BG_BTN_HOV))
        btn.bind('<Leave>', lambda e: btn.configure(bg=S.BG_BTN))
        btn.pack(side='left')

        # ── Help hint ─────────────────────────────────────────────────
        tk.Label(
            frame,
            text=(
                "  Enter the genre, tempo and key of any external MIDI file.\n"
                "  The advisor will recommend palettes, instruments, effect\n"
                "  chains and mix targets — no generation required."
            ),
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG2,
            justify='left',
        ).pack(anchor='w', padx=4, pady=(0, 4))

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_bpm(value: str) -> bool:
        """Allow only digit strings (or empty while the user is clearing)."""
        return value == "" or value.isdigit()

    def _on_submit(self) -> None:
        """Validate inputs, build a minimal comp dict, fire the advisor."""
        genre = self._genre_var.get().strip()
        bpm_str = self._bpm_var.get().strip()
        root = self._root_var.get().strip()
        mode = self._mode_var.get().strip()

        # ── Validate BPM ──────────────────────────────────────────────
        if not bpm_str.isdigit():
            messagebox.showwarning(
                "Invalid BPM",
                "Please enter a whole number between "
                f"{_BPM_MIN} and {_BPM_MAX}.",
            )
            return

        bpm = int(bpm_str)
        if not (_BPM_MIN <= bpm <= _BPM_MAX):
            messagebox.showwarning(
                "BPM out of range",
                f"BPM must be between {_BPM_MIN} and {_BPM_MAX}.",
            )
            return

        # ── Refresh palettes for the new genre ────────────────────────
        self._load_palettes(genre)

        # ── Build minimal composition dict ────────────────────────────
        # _update_advisor only reads comp['config']['genre/bpm/key'];
        # the rest of the production data comes from the JSON files.
        comp = {
            'config': {
                'genre': genre,
                'bpm':   float(bpm),
                'key':   f"{root} {mode}",
            }
        }

        if self._log_fn:
            self._log_fn(
                f"Advisor query: {genre.upper()}  {bpm} BPM  {root} {mode}"
            )

        self._update_advisor(comp)
