"""
src.gui.track_instrument_row
----------------------------
Self-contained widget row for a single instrument track in the
TRACKS & INSTRUMENTS panel of the Seed Composer GUI.

Each row contains:
    - Enabled / disabled checkbox
    - Volume slider  (0 – 100)
    - Instrument combobox  (omitted for 'percussion' mode)
    - Randomise button     (omitted for 'percussion' mode)

Row modes
---------
'drums'      Combobox shows drum-kit programs  (DRUM_KITS).
'pitched'    Combobox shows role-appropriate GM programs
             (ROLE_INSTRUMENTS[track], or all 128 GM programs as fallback).
'fx_sounds'  Combobox shows the GM FX bank  (programs 96 – 103).
'percussion' No combobox and no Rand button; the track shares the drum
             channel and its kit is controlled by the 'drums' row.

Public attributes (set after construction)
------------------------------------------
enabled    : tk.BooleanVar
volume     : tk.Scale
instrument : ttk.Combobox | None   (None for 'percussion' mode)
"""

from __future__ import annotations

import random
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from src.gui.styles import S
from src.gui.constants import GM_INSTRUMENTS, DRUM_KITS, ROLE_INSTRUMENTS
from src.gui.tooltips import ToolTip, TOOLTIPS
from src.gui.instrument_description_label import InstrumentDescriptionLabel
from src.gui.fader_utils import (
    _pos_to_db, _db_to_pos, _GAIN_STEPS, _GAIN_INF_FLOOR,
)


# ---------------------------------------------------------------------------
# TrackInstrumentRow
# ---------------------------------------------------------------------------

class TrackInstrumentRow:
    """
    Builds and owns the widgets for one track row.

    Parameters
    ----------
    parent          : tk.Frame
        Parent frame; the row is packed into it immediately.
    track           : str
        Internal track key used in config.tracks
        (e.g. 'stabs', 'texture', 'fx', 'percussion').
    mode            : str
        One of 'drums' | 'pitched' | 'fx_sounds' | 'percussion'.
    color           : str
        Hex accent colour used for the label and the Rand button outline.
    default_enabled  : bool
        Initial state of the enabled checkbox.
    default_gain_db  : float
        Initial fader position in dB.  0.0 = unity (no velocity scaling),
        −∞ (≤ −60) = silence.  Displayed with the same log taper as the
        Groove & Mixer panel gain fader.
    default_program  : int | None
        Initial GM program number shown in the combobox.
        Ignored for 'drums' (always starts on "0: Standard Kit")
        and 'percussion' (no combobox).
    log_fn          : callable | None
        Optional callback(str) for logging messages to the GUI log panel.
    tip_fn          : callable | None
        Optional callback(widget, key) that attaches a ToolTip.
        When None the class attaches tooltips itself using TOOLTIPS.
    """

    # Valid mode identifiers
    _VALID_MODES = {'drums', 'pitched', 'fx_sounds', 'percussion'}

    def __init__(
        self,
        parent: tk.Frame,
        track: str,
        mode: str,
        color: str,
        default_enabled:  bool           = True,
        default_gain_db:  float          = -3.0,
        default_program:  Optional[int]  = None,
        log_fn: Optional[Callable[[str], None]] = None,
        tip_fn: Optional[Callable[[tk.Widget, str], None]] = None,
    ) -> None:
        if mode not in self._VALID_MODES:
            raise ValueError(f"Invalid mode '{mode}'. Choose from {self._VALID_MODES}.")

        # Store parameters
        self._track   = track
        self._mode    = mode
        self._color   = color
        self._log_fn  = log_fn
        self._tip_fn  = tip_fn

        # These are set by _build() and exposed as public attributes
        self.enabled:    tk.BooleanVar         = tk.BooleanVar(value=default_enabled)
        self.volume:     Optional[tk.Scale]    = None
        self.instrument: Optional[ttk.Combobox] = None

        # Build all widgets — two sub-rows inside a container frame
        self._build(parent, default_gain_db, default_program)

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------

    def _build(
        self,
        parent:          tk.Frame,
        default_gain_db: float,
        default_program: Optional[int],
    ) -> None:
        """
        Build two sub-rows inside a container frame:
          Row 1 — checkbox · vol slider · combobox · Rand button
          Row 2 — sound-character description (indented, full panel width)
        """
        container = tk.Frame(parent, bg=S.BG2)
        container.pack(fill='x', pady=2)

        row1 = tk.Frame(container, bg=S.BG2)
        row1.pack(fill='x')

        # ── Enabled checkbox ──────────────────────────────────────────
        en_cb = tk.Checkbutton(
            row1,
            text=self._track.upper(),
            variable=self.enabled,
            font=S.FN_S,
            fg=self._color,
            bg=S.BG2,
            selectcolor=S.BG3,
            activebackground=S.BG2,
            width=9,          # wider than original 7 to fit 'PERCUSSION'
            anchor='w',
        )
        en_cb.pack(side='left')
        self._attach_tip(en_cb, 'track_enabled')

        # ── Volume fader (−∞ to +6 dB, log taper) ───────────────────
        # Uses the same DAW fader curve as the Groove & Mixer panel:
        # 0 dB (unity) sits at 80 % of travel; double-click resets.
        tk.Label(
            row1, text="Vol:", font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2
        ).pack(side='left')

        _init_pos = int(_db_to_pos(max(-60.0, min(6.0, default_gain_db))) * _GAIN_STEPS)
        self._vol_pos_var = tk.IntVar(value=_init_pos)

        self.volume = tk.Scale(
            row1,
            variable=self._vol_pos_var,
            from_=0, to=_GAIN_STEPS, resolution=1,
            orient='horizontal',
            font=S.FN_X,
            fg=self._color,
            bg=S.BG2,
            troughcolor=S.BG_INPUT,
            highlightthickness=0,
            length=80,
            showvalue=0,
        )
        self.volume.pack(side='left', padx=2)
        self._attach_tip(self.volume, 'track_volume')

        # Live dB readout label
        self._vol_lbl = tk.Label(row1, text='', font=S.FN_X, fg=S.TXT, bg=S.BG2, width=7)
        self._vol_lbl.pack(side='left')

        def _refresh_vol_lbl(*_):
            db = _pos_to_db(self._vol_pos_var.get() / _GAIN_STEPS)
            self._vol_lbl.configure(
                text='-∞ dB' if db <= _GAIN_INF_FLOOR else f'{db:+.1f} dB'
            )

        self._vol_pos_var.trace_add('write', _refresh_vol_lbl)
        # Double-click resets to 0 dB
        self.volume.bind(
            '<Double-Button-1>',
            lambda _: self._vol_pos_var.set(int(_db_to_pos(0.0) * _GAIN_STEPS)),
        )
        _refresh_vol_lbl()  # set initial text

        # ── Instrument combobox (skipped for percussion) ──────────────
        if self._mode == 'percussion':
            tk.Label(
                row1,
                text="(drum channel – no program)",
                font=S.FN_X,
                fg=S.TXT_DIM,
                bg=S.BG2,
            ).pack(side='left', padx=4)
            return   # instrument stays None; no description row needed

        # Build the combobox values list based on mode
        combobox_values = self._get_combobox_values()

        self.instrument = ttk.Combobox(
            row1, values=combobox_values, width=22, font=S.FN_X
        )
        initial = self._resolve_default_program(default_program)
        self.instrument.set(initial)
        self.instrument.pack(side='left', padx=4)
        self._attach_tip(self.instrument, 'track_instrument')

        # ── Randomise button ──────────────────────────────────────────
        rand_btn = self._make_button(row1, "Rand", self.randomize, self._color)
        rand_btn.pack(side='left', padx=2)
        self._attach_tip(rand_btn, 'btn_rand_instrument')

        # ── Description row (below row 1) ─────────────────────────────
        # Indent spacer aligns the text under the instrument area rather
        # than starting flush with the track checkbox.
        row2 = tk.Frame(container, bg=S.BG2)
        row2.pack(fill='x')
        tk.Label(row2, text="", bg=S.BG2, width=10, font=S.FN_X).pack(side='left')
        self._desc = InstrumentDescriptionLabel(row2, styles=S, max_chars=120)
        self._desc.pack(side='left', fill='x', expand=True, padx=(2, 4))
        self._desc.attach(self.instrument)

    # ------------------------------------------------------------------
    # Combobox helpers
    # ------------------------------------------------------------------

    def _get_combobox_values(self) -> list[str]:
        """Return the list of formatted strings for the combobox."""
        if self._mode == 'drums':
            # Drum kits sorted by program number
            return [f"{k}: {v}" for k, v in sorted(DRUM_KITS.items())]

        if self._mode == 'fx_sounds':
            # GM FX bank: programs 96 – 103
            return [
                f"{prog}: {GM_INSTRUMENTS[prog]}"
                for prog in range(96, 104)
            ]

        # 'pitched': use role-specific pool or all 128 GM instruments
        pool = ROLE_INSTRUMENTS.get(self._track)
        if pool:
            return [
                f"{prog}: {GM_INSTRUMENTS.get(prog, 'Unknown')}"
                for prog in pool
            ]
        # Fallback: full GM list
        return [f"{k}: {v}" for k, v in sorted(GM_INSTRUMENTS.items())]

    def _resolve_default_program(self, default_program: Optional[int]) -> str:
        """Convert a numeric program to the 'prog: Name' string shown in combobox."""
        if self._mode == 'drums':
            return "0: Standard Kit"

        if default_program is not None:
            name = GM_INSTRUMENTS.get(default_program, "Unknown")
            return f"{default_program}: {name}"

        # No explicit default — pick the first entry from the role pool
        pool = ROLE_INSTRUMENTS.get(self._track)
        if pool:
            prog = pool[0]
            return f"{prog}: {GM_INSTRUMENTS.get(prog, 'Unknown')}"

        # Final fallback: acoustic grand piano
        return "0: Acoustic Grand Piano"

    # ------------------------------------------------------------------
    # Randomise
    # ------------------------------------------------------------------

    def randomize(self) -> None:
        """
        Pick a random instrument from the role-appropriate pool and update
        the combobox. Also calls log_fn if one was provided.
        """
        if self.instrument is None:
            # Percussion mode — nothing to randomise
            return

        if self._mode == 'drums':
            kit = random.choice(list(DRUM_KITS.items()))
            self.instrument.set(f"{kit[0]}: {kit[1]}")

        elif self._mode == 'fx_sounds':
            # Random pick from the FX bank (programs 96 – 103)
            prog = random.randint(96, 103)
            self.instrument.set(f"{prog}: {GM_INSTRUMENTS.get(prog, 'FX')}")

        else:
            # 'pitched': draw from role pool or full GM list
            pool = ROLE_INSTRUMENTS.get(self._track, list(GM_INSTRUMENTS.keys()))
            prog = random.choice(pool)
            self.instrument.set(f"{prog}: {GM_INSTRUMENTS.get(prog, 'Unknown')}")

        if self._log_fn:
            self._log_fn(f"Randomized {self._track}: {self.instrument.get()}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_button(
        self,
        parent: tk.Frame,
        text: str,
        command: Callable,
        color: str,
    ) -> tk.Button:
        """Create a styled button matching the app's _cbtn style."""
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            font=S.FN_S,
            fg=color,
            bg=S.BG_BTN,
            activeforeground=S.TXT_BRT,
            activebackground=S.BG_BTN_ACT,
            bd=0,
            padx=6,
            pady=2,
            cursor='hand2',
            highlightthickness=1,
            highlightbackground=color,
        )
        btn.bind('<Enter>', lambda e: btn.configure(bg=S.BG_BTN_HOV))
        btn.bind('<Leave>', lambda e: btn.configure(bg=S.BG_BTN))
        return btn

    def _attach_tip(self, widget: tk.Widget, key: str) -> None:
        """Attach a hover tooltip. Uses tip_fn if provided, otherwise direct ToolTip."""
        if self._tip_fn:
            self._tip_fn(widget, key)
        else:
            text = TOOLTIPS.get(key, "")
            if text:
                ToolTip(widget, text)
