"""
src.gui.mastering_panel — Compact mastering-chain widget for ExportDialog.

Displays:
  Row 1: Checkbutton  "APPLY MASTERING CHAIN"  (S.ORANGE accent)
           + dim subtitle showing the active stage count
  Row 2: Three Radiobuttons, one per MasteringTarget, colour-coded per platform
  Row 3: Info label showing the selected target's description

Usage::

    panel = MasteringPanel(parent_frame, styles=S)
    settings = panel.get_settings()
    # → {'enabled': True, 'target_id': 'streaming'}
"""
from __future__ import annotations

import tkinter as tk
from typing import Optional

from src.dsp.mastering_targets import BROADCAST, STREAMING, SYNC_LICENSING, MasteringTarget
from src.gui.styles import S

# ── Target list and per-target display colours ─────────────────────────────────
_TARGETS: list[MasteringTarget] = [STREAMING, BROADCAST, SYNC_LICENSING]

_TARGET_COLORS: dict[str, str] = {
    'streaming':      '#00e5ff',   # cyan — high-energy streaming platforms
    'broadcast':      '#ffd500',   # yellow — regulated broadcast standard
    'sync_licensing': '#a855f7',   # purple — premium sync/library placement
}

_SUBTITLE = "EQ · Bus Comp · Parallel · M/S · LUFS · Limiter"


class MasteringPanel(tk.Frame):
    """
    Self-contained mastering-chain control widget.

    Parameters
    ----------
    parent : tk.Widget
        Parent container (typically ExportDialog's body frame).
    styles : module or class, optional
        Style constants namespace (defaults to the global S from styles.py).
    """

    def __init__(
        self,
        parent,
        styles=None,
        **kwargs,
    ) -> None:
        self._S = styles or S
        S_      = self._S

        super().__init__(parent, bg=S_.BG2, **kwargs)

        # State variables
        self._enabled_var   = tk.BooleanVar(value=True)
        self._target_var    = tk.StringVar(value='streaming')

        # Build UI rows
        self._build_toggle_row()
        self._build_target_row()
        self._build_info_row()

        # Initialise state
        self._on_target_change()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_toggle_row(self) -> None:
        """Row 1 — master enable/disable checkbutton + subtitle."""
        S_ = self._S
        row = tk.Frame(self, bg=S_.BG2)
        row.pack(fill='x', pady=(4, 2))

        # Checkbutton in S.ORANGE so it stands out
        cb = tk.Checkbutton(
            row,
            text             = "APPLY MASTERING CHAIN",
            variable         = self._enabled_var,
            command          = self._on_toggle,
            font             = S_.FN_H,
            fg               = S_.ORANGE,
            bg               = S_.BG2,
            activeforeground = S_.TXT_BRT,
            activebackground = S_.BG2,
            selectcolor      = S_.BG3,
            bd               = 0,
            highlightthickness= 0,
            cursor           = 'hand2',
        )
        cb.pack(side='left')

        # Dim subtitle listing the DSP stages
        tk.Label(
            row,
            text   = _SUBTITLE,
            font   = S_.FN_X,
            fg     = S_.TXT_DIM,
            bg     = S_.BG2,
            anchor = 'w',
        ).pack(side='left', padx=(8, 0))

    def _build_target_row(self) -> None:
        """Row 2 — one Radiobutton per target, colour-coded."""
        S_  = self._S
        row = tk.Frame(self, bg=S_.BG2)
        row.pack(fill='x', pady=(2, 2))

        self._radio_widgets: list[tk.Radiobutton] = []

        for target in _TARGETS:
            color = _TARGET_COLORS.get(target.id, S_.CYAN)
            rb = tk.Radiobutton(
                row,
                text             = target.label,
                variable         = self._target_var,
                value            = target.id,
                command          = self._on_target_change,
                font             = S_.FN_S,
                fg               = color,
                bg               = S_.BG2,
                activeforeground = S_.TXT_BRT,
                activebackground = S_.BG2,
                selectcolor      = S_.BG3,
                bd               = 0,
                highlightthickness= 0,
                cursor           = 'hand2',
            )
            rb.pack(side='left', padx=(0, 10))
            self._radio_widgets.append(rb)

    def _build_info_row(self) -> None:
        """Row 3 — description label for the currently selected target."""
        S_  = self._S
        self._info_var = tk.StringVar()
        self._info_lbl = tk.Label(
            self,
            textvariable = self._info_var,
            font         = S_.FN_X,
            fg           = S_.TXT_DIM,
            bg           = S_.BG2,
            anchor       = 'w',
            justify      = 'left',
        )
        self._info_lbl.pack(fill='x', pady=(0, 4))

    # ── Event handlers ─────────────────────────────────────────────────────────

    def _on_toggle(self) -> None:
        """Enable or disable the target radio buttons based on checkbox state."""
        enabled = self._enabled_var.get()
        state   = 'normal' if enabled else 'disabled'
        for rb in self._radio_widgets:
            rb.configure(state=state)
        self._update_info_label()

    def _on_target_change(self) -> None:
        """Update the info label when the selected target changes."""
        self._update_info_label()

    def _update_info_label(self) -> None:
        """Refresh the info label to match the current target selection."""
        if not self._enabled_var.get():
            self._info_var.set("Mastering chain disabled — raw FluidSynth output")
            return

        tid = self._target_var.get()
        # Find matching target from _TARGETS list
        target: Optional[MasteringTarget] = next(
            (t for t in _TARGETS if t.id == tid), None
        )
        if target:
            self._info_var.set(target.description)
        else:
            self._info_var.set("")

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_settings(self) -> dict:
        """
        Return the current panel state as a plain dict.

        Returns
        -------
        dict with keys:
            'enabled'   : bool   — whether the mastering chain should run
            'target_id' : str    — selected MasteringTarget.id
        """
        return {
            'enabled':   self._enabled_var.get(),
            'target_id': self._target_var.get(),
        }
