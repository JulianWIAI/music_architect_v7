"""
src.gui.fx_variant_panel
-------------------------
Compact collapsible panel in the ADVISOR tab that lets the user switch
between BRIGHT / NEUTRAL / DARK timbral variants of the FX chain.

Design rationale
----------------
The same genre + BPM + key can produce three distinct production flavors:

  BRIGHT  — air shelf, short bright reverbs, less saturation
  NEUTRAL — genre reference (no change from the JSON defaults)
  DARK    — tape saturation, long dark reverbs, less HF

Each genre has thematic names (e.g. pop: POLISHED / NATURAL / UNDERGROUND;
cinematic: EPIC / INTIMATE / ATMOSPHERIC) so the choice feels meaningful
rather than technical.

Integration
-----------
Pass four callbacks into the constructor:

    on_variant_change_fn : Callable[[str], None]
        Called with the new variant_id ('bright'/'neutral'/'dark')
        whenever the user clicks a variant button.  The app should
        re-render the advisor with the new merged chain_delta.

    get_genre_fn : Callable[[], str]
        Returns the currently active genre string.

    get_track_instruments_fn : Callable[[], dict]
        Returns {track_name: gm_program_int} for all active tracks.
        Used to display which instrument-class adjustments are active.

    get_variant_id_fn : Callable[[], str]
        Returns the currently active variant_id so the panel can
        highlight the correct button on re-render.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Dict, Optional

from src.composition.fx_chain_selector import FxChainSelector
from src.gui.collapsible_section import CollapsibleSection


# ── Timbral color mapping for button highlights ───────────────────────────────
# bright=yellow, neutral=cyan, dark=purple (BDRA-style visual language)
_VARIANT_COLORS = {
    "bright":  "#f0c060",   # warm yellow
    "neutral": "#60d0d0",   # cyan (matches app S.CYAN)
    "dark":    "#a060d0",   # purple / violet
}


class FxVariantPanel:
    """
    Three-button timbral variant selector for the ADVISOR tab.

    Shows:
      [BRIGHT label]  [NEUTRAL label]  [DARK label]
      Description line for the active variant
      Active instrument-class adjustments summary

    Parameters
    ----------
    parent : tk.Frame
        Parent container in the ADVISOR tab.
    styles : object
        App styles object (S). Used for fonts, colours, bg values.
    on_variant_change_fn : Callable[[str], None]
        Fired when the user picks a variant; receives the variant_id.
    get_genre_fn : Callable[[], str]
        Returns current genre so the panel can fetch variant labels.
    get_track_instruments_fn : Callable[[], dict]
        Returns {track: gm_program} so active instrument classes can be shown.
    get_variant_id_fn : Callable[[], str]
        Returns current variant_id for highlight synchronisation.
    """

    def __init__(
        self,
        parent: tk.Frame,
        *,
        styles,
        on_variant_change_fn: Callable[[str], None],
        get_genre_fn: Callable[[], str],
        get_track_instruments_fn: Callable[[], Dict[str, Optional[int]]],
        get_variant_id_fn: Callable[[], str],
    ) -> None:
        self._S                        = styles
        self._on_variant_change        = on_variant_change_fn
        self._get_genre                = get_genre_fn
        self._get_track_instruments    = get_track_instruments_fn
        self._get_variant_id           = get_variant_id_fn

        # ── Collapsible shell ─────────────────────────────────────────────
        self._cs = CollapsibleSection(
            parent,
            "FX CHAIN VARIANT  (bright / neutral / dark)",
            styles.ORANGE,
            collapsed=False,   # open by default — this is a key advisor feature
        )
        frame = self._cs.content_frame
        self._build(frame)

    # ------------------------------------------------------------------
    # Public layout
    # ------------------------------------------------------------------

    def pack(self, **kwargs) -> None:
        """Re-specify pack layout on the CollapsibleSection outer frame."""
        self._cs.outer.pack(**kwargs)

    # ------------------------------------------------------------------
    # Public update
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """
        Refresh button highlights and description for the current state.

        Call this after:
          • a new composition is generated (variant_id may have changed)
          • the user switches genre (variant labels change)
          • the user changes an instrument (instrument-class badge changes)
        """
        genre      = self._get_genre()
        variant_id = self._get_variant_id()
        variants   = FxChainSelector.get_all_variants(genre)
        active_v   = FxChainSelector.get_variant(genre, variant_id)

        # ── Update each button: highlight active, dim others ──────────
        for vid, btn in self._btns.items():
            is_active = (vid == variant_id)
            color = _VARIANT_COLORS.get(vid, self._S.CYAN)
            btn.configure(
                relief="solid" if is_active else "flat",
                bd=1 if is_active else 0,
                fg=color if is_active else self._S.TXT_DIM,
                highlightbackground=color if is_active else self._S.BG3,
            )

        # ── Active variant description ────────────────────────────────
        self._desc_lbl.config(
            text=f"  {active_v.get('description', '')}",
        )

        # ── Instrument-class summary ──────────────────────────────────
        track_insts = self._get_track_instruments()
        active_classes = []
        for track, gm in track_insts.items():
            if gm is None:
                continue
            cls = FxChainSelector.classify_instrument(gm)
            if cls:
                active_classes.append(f"{track.upper()} → {cls['label']}")

        if active_classes:
            self._inst_lbl.config(
                text=f"  Instrument adjustments: {', '.join(active_classes)}",
                fg=self._S.GREEN,
            )
        else:
            self._inst_lbl.config(
                text="  No instrument-class adjustments active for current selection",
                fg=self._S.TXT_DIM,
            )

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build(self, frame: tk.Frame) -> None:
        S = self._S
        genre    = self._get_genre()
        variants = FxChainSelector.get_all_variants(genre)

        # Build a name lookup for labels (may be empty on first call before
        # genre is known; refresh() will fix labels once genre is set)
        if not variants:
            variants = [
                {"id": "bright",  "label": "BRIGHT",  "description": ""},
                {"id": "neutral", "label": "NEUTRAL",  "description": ""},
                {"id": "dark",    "label": "DARK",     "description": ""},
            ]

        # ── Variant buttons row ───────────────────────────────────────────
        btn_row = tk.Frame(frame, bg=S.BG2)
        btn_row.pack(fill="x", padx=4, pady=(2, 2))

        self._btns: dict[str, tk.Button] = {}

        for v in variants:
            vid   = v["id"]
            label = v["label"]
            color = _VARIANT_COLORS.get(vid, S.CYAN)

            btn = tk.Button(
                btn_row,
                text=label,
                font=S.FN_S,
                fg=color,
                bg=S.BG_BTN,
                activeforeground=S.TXT_BRT,
                activebackground=S.BG_BTN_ACT,
                bd=0,
                padx=10,
                pady=3,
                cursor="hand2",
                highlightthickness=1,
                highlightbackground=color,
                command=lambda v_id=vid: self._on_click(v_id),
            )
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=S.BG_BTN_HOV))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=S.BG_BTN))
            btn.pack(side="left", padx=4)
            self._btns[vid] = btn

        # ── Active variant description ─────────────────────────────────────
        self._desc_lbl = tk.Label(
            frame,
            text="",
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG2,
            anchor="w",
        )
        self._desc_lbl.pack(fill="x", padx=4, pady=(0, 1))

        # ── Instrument-class active indicator ─────────────────────────────
        self._inst_lbl = tk.Label(
            frame,
            text="",
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG2,
            anchor="w",
        )
        self._inst_lbl.pack(fill="x", padx=4, pady=(0, 4))

        # Initial highlight state
        self.refresh()

    # ------------------------------------------------------------------
    # Internal callback
    # ------------------------------------------------------------------

    def _on_click(self, variant_id: str) -> None:
        """Variant button was clicked — notify app and refresh highlights."""
        self._on_variant_change(variant_id)
        self.refresh()
