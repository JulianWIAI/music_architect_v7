"""
src/gui/instrument_builder.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Combinatoric instrument selector widget for the Production Advisor tab.

Architecture overview
─────────────────────
InstrumentBuilder is a self-contained tk.Frame.  It owns:
  · A KICK combobox whose value determines the Matrix 1 Branch (A / B / C).
  · Six track comboboxes (bass → chords → melody → arp → pads → stabs),
    each filtered live to only show Branch-compliant instruments.
  · A live compatibility score (0-100) computed by bdra_rules.validate_selection,
    reflecting adherence to the five psychoacoustic principles P1-P5.
  · A collapsible content frame so the panel can be hidden when not needed.

Data flow
─────────
  User changes KICK  →  _on_kick_change()
      → re-filter all track comboboxes for the new Branch
      → refresh BDRA labels (green = compliant, yellow = override)
      → refresh score

  User changes TRACK →  _on_track_change(track)
      → compute which Branches accept this instrument (compatible_branches)
      → if current kick Branch is incompatible, auto-switch kick to first
        compatible Branch, then re-filter everything
      → otherwise just refresh labels + score

  Palette selected   →  sync_from_palette(palette)
      → sets kick combobox to palette.branch
      → maps palette instrument keys to builder track keys and sets comboboxes

  APPLY clicked      →  _apply()
      → calls apply_callback(current_selection()) where selection is
        {'branch': 'A', 'bass': {'gm':38,'name':'...','code':'B1 D1 A0 R1'}, ...}
        The caller (App._apply_builder) maps 'melody'→'lead', 'pads'→'pad'.

Comments convention
────────────────────
Public methods have docstrings.  Private helpers have one-line comments where
the 'why' is non-obvious.  Psychoacoustic principles referenced as P1-P5 (see
bdra_rules.py module docstring for full definitions).
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional

from src.composition import bdra_rules as _br
from src.composition.gm_descriptions import get_description as _gm_desc
from src.gui.tooltips import ToolTip, TOOLTIPS


# ── Track configuration ───────────────────────────────────────────────────────
# Each tuple: (builder_key, display_label, styles.TRACK_CLR lookup key)
# builder_key matches bdra_instruments.json AND bdra_rules.BRANCH_RULES keys.
# 'melody' is displayed as 'LEAD' so the UI matches the left-panel vocabulary.
_TRACKS: List[tuple] = [
    ('bass',   'BASS',   'bass'),
    ('chords', 'CHORDS', 'chords'),
    ('melody', 'LEAD',   'lead'),
    ('arp',    'ARP',    'arp'),
    ('pads',   'PAD',    'pad'),
    ('stabs',  'STABS',  'stabs'),
]

# Maps builder track key → display label for the description strip.
_TRACKS_DISPLAY: dict = {t[0]: t[1] for t in _TRACKS}


class InstrumentBuilder(tk.Frame):
    """
    Combinatoric instrument selector frame.

    Parameters
    ----------
    parent          : Tkinter parent widget (the advisor tab frame).
    apply_callback  : Called with current_selection() dict when user clicks APPLY.
    gm_instruments  : {int: str} GM program-number → name (passed from App).
    styles          : The styles namespace (S) from src/gui/styles.py.
    """

    def __init__(
        self,
        parent: tk.Widget,
        apply_callback: Callable[[dict], None],
        gm_instruments: Dict[int, str],
        styles,
    ) -> None:
        super().__init__(parent, bg=styles.BG2)

        self._apply_cb    = apply_callback
        self._gm          = gm_instruments
        self._S           = styles
        # Load curated instrument catalogue once at construction time
        self._catalogue   = _br.load_instruments()  # {track: [{gm,name,code}]}

        # Re-entrance guard — prevents cascade when code sets combobox values
        self._busy = False

        # Widgets populated by _build_ui()
        self._kick_var:    tk.StringVar          = tk.StringVar()
        self._track_vars:  Dict[str, tk.StringVar]    = {}
        self._track_cbs:   Dict[str, ttk.Combobox]   = {}
        self._track_lbls:  Dict[str, tk.Label]        = {}
        self._track_tips:  Dict[str, object]          = {}  # ToolTip per combobox
        self._score_lbl:   Optional[tk.Label]         = None
        self._viol_lbl:    Optional[tk.Label]         = None
        self._branch_badge: Optional[tk.Label]        = None

        self._expanded = True   # collapse state

        self._build_ui()
        # Initialise combobox contents with Branch A defaults
        self._on_kick_change()
        # Pre-populate every combobox tooltip so hovering any track immediately
        # shows its description rather than an empty popup.
        for track_key, _, _ in _TRACKS:
            inst = self._inst(track_key)
            if inst:
                tip = self._track_tips.get(track_key)
                if tip:
                    tip.text = _gm_desc(inst.get('gm', 0))
        # Show the first track's description in the INFO strip
        self._refresh_desc(_TRACKS[0][0])

    # ─────────────────────────────────────────────────────────────────────
    #  UI construction  (called once from __init__)
    # ─────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        S = self._S

        # ── Toggle header ─────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=S.BG2)
        hdr.pack(fill='x', pady=(2, 0))

        self._toggle_btn = tk.Button(
            hdr, text='▼ INSTRUMENT BUILDER',
            font=S.FN_S, fg=S.PINK, bg=S.BG2,
            bd=0, activebackground=S.BG3, activeforeground=S.PINK,
            cursor='hand2', anchor='w',
            command=self._toggle,
        )
        self._toggle_btn.pack(side='left')

        # Branch badge updates whenever the kick combobox changes
        self._branch_badge = tk.Label(
            hdr, text='', font=S.FN_X, fg=S.CYAN, bg=S.BG2,
        )
        self._branch_badge.pack(side='left', padx=8)

        # ── Collapsible content ───────────────────────────────────────────
        self._content = tk.Frame(self, bg=S.BG2)
        self._content.pack(fill='x')

        # ── Kick row ──────────────────────────────────────────────────────
        # The kick type is the Matrix 1 root; three canonical BDRA codes
        # correspond to Branches A (pure sine/808), B (acoustic layered),
        # and C (sub-boom/taiko).
        kick_opts = [
            f"{k['branch']}  {k['code']}  {k['desc']}"
            for k in _br.KICK_BRANCHES
        ]
        self._kick_var.set(kick_opts[0])

        kick_row = tk.Frame(self._content, bg=S.BG2)
        kick_row.pack(fill='x', pady=1)

        tk.Label(
            kick_row, text='KICK', font=S.FN_X,
            fg=S.TXT_DIM, bg=S.BG2, width=7, anchor='w',
        ).pack(side='left', padx=(4, 0))

        kick_cb = ttk.Combobox(
            kick_row, textvariable=self._kick_var,
            values=kick_opts, state='readonly', width=42, font=S.FN_X,
        )
        kick_cb.pack(side='left', padx=4)
        kick_cb.bind('<<ComboboxSelected>>', lambda _e: self._on_kick_change())
        ToolTip(kick_cb, TOOLTIPS['advisor_kick'])

        # ── Track rows ────────────────────────────────────────────────────
        for track_key, display, color_key in _TRACKS:
            color   = S.TRACK_CLR.get(color_key, S.CYAN)
            insts   = self._catalogue.get(track_key, [])
            options = [_fmt(i) for i in insts]

            var = tk.StringVar()

            row = tk.Frame(self._content, bg=S.BG2)
            row.pack(fill='x', pady=1)

            tk.Label(
                row, text=display, font=S.FN_X, fg=color,
                bg=S.BG2, width=7, anchor='w',
            ).pack(side='left', padx=(4, 0))

            cb = ttk.Combobox(
                row, textvariable=var,
                values=options, state='readonly', width=42, font=S.FN_X,
            )
            if options:
                cb.set(options[0])
            cb.pack(side='left', padx=4)

            # Hover tooltip on the combobox itself — shows the full sound
            # description of the currently selected instrument.  Text is
            # updated dynamically in _refresh_desc() on every change.
            tip = ToolTip(cb, "")
            self._track_tips[track_key] = tip

            # BDRA code label — green inside branch range, yellow when overridden
            code_lbl = tk.Label(
                row, text='', font=S.FN_X,
                fg=S.GREEN, bg=S.BG2, width=13, anchor='w',
            )
            code_lbl.pack(side='left', padx=(2, 0))

            # trace_add fires on every var write, including programmatic sets;
            # the _busy guard in _on_track_change prevents re-entrance loops.
            var.trace_add('write', lambda *_a, t=track_key: self._on_track_change(t))

            self._track_vars[track_key] = var
            self._track_cbs[track_key]  = cb
            self._track_lbls[track_key] = code_lbl

        # ── Sound-character description strip ─────────────────────────────
        # A single label that updates to show a pedagogical description of
        # whichever instrument the user most recently changed.  Placed here
        # (between track rows and score) so it is always visible without
        # needing to resize the panel.
        desc_row = tk.Frame(self._content, bg=S.BG2)
        desc_row.pack(fill='x', pady=(2, 0))

        tk.Label(
            desc_row, text='INFO', font=S.FN_X,
            fg=S.TXT_DIM, bg=S.BG2, width=7, anchor='w',
        ).pack(side='left', padx=(4, 0))

        self._desc_lbl = tk.Label(
            desc_row, text='Select an instrument to see its description…',
            font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2, anchor='w',
        )
        self._desc_lbl.pack(side='left', padx=4, fill='x', expand=True)
        # Tooltip on the INFO label so hovering shows the full unclipped text
        self._desc_tooltip = ToolTip(self._desc_lbl, "")

        # ── Score row ─────────────────────────────────────────────────────
        score_row = tk.Frame(self._content, bg=S.BG2)
        score_row.pack(fill='x', pady=(4, 1))

        tk.Label(
            score_row, text='SCORE', font=S.FN_X,
            fg=S.TXT_DIM, bg=S.BG2, width=7, anchor='w',
        ).pack(side='left', padx=(4, 0))

        self._score_lbl = tk.Label(
            score_row, text='—', font=S.FN_S, fg=S.GREEN, bg=S.BG2,
        )
        self._score_lbl.pack(side='left', padx=4)
        ToolTip(self._score_lbl, TOOLTIPS['advisor_score'])

        # First violation shown inline (space-constrained; full list in advisor text)
        self._viol_lbl = tk.Label(
            score_row, text='', font=S.FN_X,
            fg=S.YELLOW, bg=S.BG2, anchor='w',
        )
        self._viol_lbl.pack(side='left', padx=4, fill='x', expand=True)

        # ── Apply button ──────────────────────────────────────────────────
        btn_row = tk.Frame(self._content, bg=S.BG2)
        btn_row.pack(fill='x', pady=(2, 6))

        apply_btn = tk.Button(
            btn_row, text='APPLY TO TRACKS',
            font=S.FN_X, fg=S.BG, bg=S.GREEN,
            activebackground=S.CYAN, activeforeground=S.BG,
            bd=0, padx=8, pady=2, cursor='hand2',
            command=self._apply,
        )
        apply_btn.pack(side='right', padx=4)
        ToolTip(apply_btn, TOOLTIPS['advisor_apply'])

    # ─────────────────────────────────────────────────────────────────────
    #  Event handlers
    # ─────────────────────────────────────────────────────────────────────

    def _on_kick_change(self) -> None:
        """
        Kick Branch changed → re-filter all track comboboxes.

        Reads the branch letter from the kick combobox, calls
        filter_instruments() per track to rebuild each combobox's option
        list, then restores the prior selection if still valid.
        """
        if self._busy:
            return
        self._busy = True
        try:
            branch = self._branch()
            kb = next((k for k in _br.KICK_BRANCHES if k['branch'] == branch),
                      _br.KICK_BRANCHES[0])
            self._branch_badge.config(
                text=f"Branch {branch}  {kb['code']}  {kb['desc']}"
            )

            for track, cb in self._track_cbs.items():
                prior   = self._track_vars[track].get()
                insts   = self._catalogue.get(track, [])
                valid   = _br.filter_instruments(branch, track, insts)
                options = [_fmt(i) for i in valid]
                cb['values'] = options
                if options:
                    cb.set(prior if prior in options else options[0])
                else:
                    cb.set('')

            self._refresh_labels()
            self._refresh_score()
        finally:
            self._busy = False

    def _on_track_change(self, track: str) -> None:
        """
        A non-kick track instrument changed → bidirectional constraint update.

        Computes which Branches accept the new instrument (compatible_branches).
        If the current kick Branch is not in that set, auto-switches to the
        first compatible Branch (bidirectional propagation from Section B rule).
        Otherwise, refreshes labels and score only.
        """
        if self._busy:
            return

        inst = self._inst(track)
        if inst is None:
            return

        # Find which branches support this instrument on this track
        compat = _br.compatible_branches(track, inst['code'])
        cur    = self._branch()

        if compat and cur not in compat:
            # Auto-switch kick to first branch that accepts this instrument
            new_branch = compat[0]
            new_kick   = next(
                (f"{k['branch']}  {k['code']}  {k['desc']}"
                 for k in _br.KICK_BRANCHES if k['branch'] == new_branch),
                None,
            )
            if new_kick:
                self._kick_var.set(new_kick)
            # Full re-filter now that kick has changed
            self._on_kick_change()
        else:
            # Kick stays; refresh display only
            self._refresh_labels()
            self._refresh_score()

        # Update the description strip to show the newly selected instrument
        self._refresh_desc(track)

    # ─────────────────────────────────────────────────────────────────────
    #  Live display updates
    # ─────────────────────────────────────────────────────────────────────

    def _refresh_labels(self) -> None:
        """
        Recolour each BDRA code label.

        Green  = instrument is inside the Branch's valid range for this track.
        Yellow = user has overridden with an out-of-range instrument (still
                 allowed — the builder never blocks, only informs).
        """
        S      = self._S
        branch = self._branch()
        for track, lbl in self._track_lbls.items():
            inst = self._inst(track)
            if inst is None:
                lbl.config(text='', fg=S.TXT_DIM)
                continue
            rules  = _br.BRANCH_RULES.get(branch, {}).get(track, {})
            ok     = _br.in_range(inst['code'], rules) if rules else True
            lbl.config(text=inst['code'], fg=S.GREEN if ok else S.YELLOW)

    def _refresh_score(self) -> None:
        """
        Run the five-principle validator and update the score label.

        Score colours:  ≥90 green · ≥70 yellow · ≥50 orange · <50 red.
        The first violation (if any) is shown inline; the full list is
        available via current_validation().
        """
        S      = self._S
        branch = self._branch()

        # Build selection dict {track: code} for the validator
        sel = {}
        for t in self._track_cbs:
            inst = self._inst(t)
            if inst:
                sel[t] = inst['code']
        if not sel:
            return

        result = _br.validate_selection(branch, sel)

        color = (S.GREEN  if result.score >= 90 else
                 S.YELLOW if result.score >= 70 else
                 S.ORANGE if result.score >= 50 else S.RED)

        self._score_lbl.config(
            text=f"{result.score}/100  {result.label}", fg=color,
        )

        if result.violations:
            self._viol_lbl.config(
                text=f"· {result.violations[0]}", fg=S.YELLOW,
            )
        elif result.warnings:
            self._viol_lbl.config(
                text=f"· {result.warnings[0]}", fg=S.TXT_DIM,
            )
        else:
            self._viol_lbl.config(text='', fg=S.TXT_DIM)

    def _refresh_desc(self, track: str) -> None:
        """
        Update the INFO strip and combobox tooltip for *track*.

        Shows a clipped description in the INFO label (to fit the panel
        width) and the full text in the hover tooltip on both the INFO label
        and the instrument's combobox so students can always read the whole
        description without the panel needing to be wider.
        """
        if not hasattr(self, '_desc_lbl'):
            return
        inst = self._inst(track)
        if inst is None:
            return

        display = _TRACKS_DISPLAY.get(track, track.upper())
        full_desc = _gm_desc(inst.get('gm', 0))
        # Visible label: track name prefix + clipped description
        clipped = full_desc[:54] + "…" if len(full_desc) > 55 else full_desc
        self._desc_lbl.config(text=f"{display:<8}{clipped}")

        # Update both tooltips with the full, unclipped description
        self._desc_tooltip.text = f"{display}: {full_desc}"
        tip = self._track_tips.get(track)
        if tip:
            tip.text = full_desc

    # ─────────────────────────────────────────────────────────────────────
    #  Public API
    # ─────────────────────────────────────────────────────────────────────

    def sync_from_palette(self, palette: dict) -> None:
        """
        Populate builder state from a palette dict (instrument_palettes.json).

        Palette instrument keys differ from builder keys in two places:
            'lead'    → 'melody'  (palette uses UI name; builder uses guide name)
            'pad'     → 'pads'    (same reason)
            'texture' → 'pads'    (texture is a second pad layer; builder merges)

        Sets the kick combobox to palette.branch, re-filters all tracks,
        then sets each combobox to the palette's instrument (by name+code or
        by GM number as fallback).
        """
        if not palette:
            return

        branch  = palette.get('branch', 'A')
        kick_str = next(
            (f"{k['branch']}  {k['code']}  {k['desc']}"
             for k in _br.KICK_BRANCHES if k['branch'] == branch),
            None,
        )
        if kick_str:
            self._kick_var.set(kick_str)
        self._on_kick_change()  # re-filter before setting instruments

        _pal_to_builder = {'lead': 'melody', 'pad': 'pads', 'texture': 'pads'}

        for pal_key, inst_data in palette.get('instruments', {}).items():
            builder_key = _pal_to_builder.get(pal_key, pal_key)
            if builder_key not in self._track_cbs:
                continue
            cb     = self._track_cbs[builder_key]
            target = _fmt(inst_data)
            if target in cb['values']:
                cb.set(target)
            else:
                # Fallback: match by GM number when name/code string differs
                gm = inst_data.get('gm')
                for opt in cb['values']:
                    cand = next(
                        (i for i in self._catalogue.get(builder_key, [])
                         if _fmt(i) == opt and i['gm'] == gm),
                        None,
                    )
                    if cand:
                        cb.set(opt)
                        break

        self._refresh_labels()
        self._refresh_score()

    def current_selection(self) -> dict:
        """
        Return the current instrument selection.

        Returns
        -------
        dict with key 'branch' ('A'/'B'/'C') plus one entry per track:
            {'gm': int, 'name': str, 'code': 'B? D? A? R?'}
        Tracks with no valid selection are omitted.
        """
        sel: dict = {'branch': self._branch()}
        for track in self._track_cbs:
            inst = self._inst(track)
            if inst:
                sel[track] = inst
        return sel

    def current_validation(self) -> _br.ValidationResult:
        """Run and return the full ValidationResult for the current selection."""
        branch = self._branch()
        sel    = {t: i['code'] for t in self._track_cbs if (i := self._inst(t))}
        return _br.validate_selection(branch, sel)

    # ─────────────────────────────────────────────────────────────────────
    #  Internal helpers
    # ─────────────────────────────────────────────────────────────────────

    def _apply(self) -> None:
        """Trigger the apply callback with the current selection."""
        self._apply_cb(self.current_selection())

    def _toggle(self) -> None:
        """Show or hide the collapsible content frame."""
        self._expanded = not self._expanded
        if self._expanded:
            self._content.pack(fill='x')
            self._toggle_btn.config(text='▼ INSTRUMENT BUILDER')
        else:
            self._content.pack_forget()
            self._toggle_btn.config(text='▶ INSTRUMENT BUILDER')

    def _branch(self) -> str:
        """Extract the branch letter from the kick combobox value."""
        v = self._kick_var.get()
        return v[0] if v and v[0] in ('A', 'B', 'C') else 'A'

    def _inst(self, track: str) -> Optional[dict]:
        """Return the catalogue entry for the current combobox value on *track*."""
        val = self._track_vars.get(track, tk.StringVar()).get()
        return next(
            (i for i in self._catalogue.get(track, []) if _fmt(i) == val),
            None,
        )


# ── Module-level helper ────────────────────────────────────────────────────────

def _fmt(inst: dict) -> str:
    """Format a catalogue entry as the combobox display string: 'Name  CODE'."""
    return f"{inst['name']}  {inst['code']}"
