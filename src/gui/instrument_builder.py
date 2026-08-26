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
from src.gui.sample_assignment_panel import SampleAssignmentPanel


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
        self._mute_vars:   Dict[str, tk.BooleanVar]  = {}   # mute state per track
        self._track_name_lbls: Dict[str, tk.Label]   = {}   # dimmed when muted
        self._score_lbl:   Optional[tk.Label]         = None
        self._viol_lbl:    Optional[tk.Label]         = None
        self._branch_badge: Optional[tk.Label]        = None
        # P1-P5 principle status labels (populated in _build_ui)
        self._principle_lbls: Dict[str, tk.Label]    = {}
        # Fix suggestion rows
        self._fix_rows:    List[dict]                 = []

        self._expanded = True   # collapse state
        self._sample_panel: Optional[SampleAssignmentPanel] = None
        # Combobox widgets for PERC / TEXTURE / FX (outside BDRA catalogue)
        self._extra_track_vars: Dict[str, tk.StringVar]      = {}
        self._extra_track_cbs:  Dict[str, ttk.Combobox]     = {}
        self._extra_mute_vars:  Dict[str, tk.BooleanVar]     = {}
        self._extra_track_name_lbls: Dict[str, tk.Label]    = {}
        self._extra_track_lbls: Dict[str, tk.Label]         = {}  # BDRA code labels

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

        kick_mute_var = tk.BooleanVar(value=False)
        self._mute_vars['drums'] = kick_mute_var
        kick_mute_btn = tk.Checkbutton(
            kick_row, text='', variable=kick_mute_var,
            font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
            selectcolor=S.BG3, activebackground=S.BG2,
            width=1, indicatoron=True,
            command=lambda mv=kick_mute_var: self._on_kick_mute_toggle(mv),
        )
        kick_mute_btn.pack(side='left', padx=(2, 0))
        ToolTip(kick_mute_btn, "Mute KICK in advisor preview.\nMuted tracks are excluded from the next render.")

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

            var      = tk.StringVar()
            mute_var = tk.BooleanVar(value=False)   # True = muted in preview
            self._mute_vars[track_key] = mute_var

            row = tk.Frame(self._content, bg=S.BG2)
            row.pack(fill='x', pady=1)

            # Mute toggle — dims the label when active; excluded from preview render
            mute_btn = tk.Checkbutton(
                row, text='', variable=mute_var,
                font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
                selectcolor=S.BG3, activebackground=S.BG2,
                width=1, indicatoron=True,
                command=lambda tk=track_key, mv=mute_var, c=color: self._on_mute_toggle(tk, mv, c),
            )
            mute_btn.pack(side='left', padx=(2, 0))
            ToolTip(mute_btn, f"Mute {display} in advisor preview.\nMuted tracks are excluded from the next render.")

            tk.Label(
                row, text=display, font=S.FN_X, fg=color,
                bg=S.BG2, width=6, anchor='w',
            ).pack(side='left', padx=(1, 0))
            self._track_name_lbls[track_key] = row.winfo_children()[-1]

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

        # ── Extra track rows: PERC / TEXTURE / FX ────────────────────────
        # These tracks exist in the composition but outside the BDRA melodic
        # catalogue.  TEXTURE and FX participate in BDRA range display and
        # density scoring; PERCUSSION uses GM channel 9 rhythm rules only.
        _EXTRA_TRACKS = [
            ('percussion', 'PERC',    'percussion'),
            ('texture',    'TEXTURE', 'texture'),
            ('fx',         'FX',      'fx'),
        ]



        for track_key, display, color_key in _EXTRA_TRACKS:
            color   = S.TRACK_CLR.get(color_key, S.CYAN)
            insts   = _EXTRA_INSTRUMENTS.get(track_key, [])
            options = [_fmt_extra(i) for i in insts]

            var      = tk.StringVar()
            mute_var = tk.BooleanVar(value=False)
            self._extra_mute_vars[track_key] = mute_var

            row = tk.Frame(self._content, bg=S.BG2)
            row.pack(fill='x', pady=1)

            # Mute toggle — same style as the six BDRA melodic track rows
            mute_btn = tk.Checkbutton(
                row, text='', variable=mute_var,
                font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
                selectcolor=S.BG3, activebackground=S.BG2,
                width=1, indicatoron=True,
                command=lambda key=track_key, mv=mute_var, c=color: (
                    self._on_extra_mute_toggle(key, mv, c)
                ),
            )
            mute_btn.pack(side='left', padx=(2, 0))
            ToolTip(mute_btn, f"Mute {display} in advisor preview.\n"
                              f"Muted tracks are excluded from the next render.")

            name_lbl = tk.Label(
                row, text=display, font=S.FN_X,
                fg=color, bg=S.BG2, width=6, anchor='w',
            )
            name_lbl.pack(side='left', padx=(1, 0))
            self._extra_track_name_lbls[track_key] = name_lbl

            cb = ttk.Combobox(
                row, textvariable=var,
                values=options, state='readonly', width=42, font=S.FN_X,
            )
            if options:
                cb.set(options[0])
            cb.pack(side='left', padx=4)

            # BDRA code label — shows range compliance for texture and fx.
            # Percussion has no BDRA code, so this label stays empty for it.
            code_lbl = tk.Label(
                row, text='', font=S.FN_X,
                fg=S.GREEN, bg=S.BG2, width=13, anchor='w',
            )
            code_lbl.pack(side='left', padx=(2, 0))
            self._extra_track_lbls[track_key] = code_lbl

            # Fire label + score refresh on any selection change
            var.trace_add('write', lambda *_a, t=track_key: (
                self._refresh_labels_extra(t),
                self._refresh_score(),
            ))

            self._extra_track_vars[track_key] = var
            self._extra_track_cbs[track_key]  = cb

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

        # First violation shown inline (space-constrained)
        self._viol_lbl = tk.Label(
            score_row, text='', font=S.FN_X,
            fg=S.YELLOW, bg=S.BG2, anchor='w',
        )
        self._viol_lbl.pack(side='left', padx=4, fill='x', expand=True)

        # ── P1-P5 principle breakdown (pedagogical) ───────────────────────
        # Five compact rows, one per psychoacoustic principle.
        # Icon: ✓ green (pass) · ✗ red (fail) · ⚠ yellow (warn).
        # Hovering over any row shows the full academic rationale.
        breakdown_frame = tk.Frame(self._content, bg=S.BG2)
        breakdown_frame.pack(fill='x', pady=(2, 0))

        tk.Label(
            breakdown_frame, text='THEORY', font=S.FN_X,
            fg=S.TXT_DIM, bg=S.BG2, width=7, anchor='w',
        ).pack(side='left', padx=(4, 2))

        p_row = tk.Frame(breakdown_frame, bg=S.BG2)
        p_row.pack(side='left', fill='x', expand=True)

        for pid, info in _br.PRINCIPLE_INFO.items():
            lbl = tk.Label(
                p_row, text=f'{pid} ✓', font=S.FN_X,
                fg=S.GREEN, bg=S.BG2, padx=4,
            )
            lbl.pack(side='left')
            tip_text = (
                f"{pid} — {info['name']}\n"
                f"Law: {info['law']}\n\n"
                f"PASS: {info['pass']}\n"
                f"FAIL: {info['fail']}"
            )
            ToolTip(lbl, tip_text)
            self._principle_lbls[pid] = lbl

        # ── Fix suggestions (Feature 5) ───────────────────────────────────
        # Up to 3 rows; each row shown/hidden dynamically by _refresh_score().
        self._fix_frame = tk.Frame(self._content, bg=S.BG2)
        self._fix_frame.pack(fill='x', pady=(1, 0))

        for _ in range(3):
            fix_row = tk.Frame(self._fix_frame, bg=S.BG2)
            lbl = tk.Label(
                fix_row, text='', font=S.FN_X,
                fg=S.ORANGE, bg=S.BG2, anchor='w',
            )
            lbl.pack(side='left', padx=(74, 2), fill='x', expand=True)
            btn = tk.Button(
                fix_row, text='APPLY FIX',
                font=S.FN_X, fg=S.BG, bg=S.ORANGE,
                activebackground=S.YELLOW, activeforeground=S.BG,
                bd=0, padx=6, pady=1, cursor='hand2',
            )
            btn.pack(side='right', padx=4)
            self._fix_rows.append({'row': fix_row, 'lbl': lbl, 'btn': btn, 'fix': None})

        # ── Sample assignment panel (per-track audio file selection) ────────
        self._sample_panel = SampleAssignmentPanel(self._content, styles=S)
        self._sample_panel.pack(fill='x', padx=4, pady=(4, 2))

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

            # Build valid option lists first so we know which priors survive.
            valid_map: dict = {}
            for track in self._track_cbs:
                insts = self._catalogue.get(track, [])
                valid_map[track] = _br.filter_instruments(branch, track, insts)

            # Only run the optimizer for tracks whose prior selection is no
            # longer valid (e.g. on first init, or after a branch switch that
            # invalidates some picks).  Tracks with a still-valid prior are
            # kept as-is so manual edits survive a kick-branch change.
            needs_opt = any(
                self._track_vars[t].get() not in [_fmt(i) for i in v]
                for t, v in valid_map.items() if v
            )
            best = _br.best_selection(branch, self._catalogue) if needs_opt else {}

            for track, cb in self._track_cbs.items():
                prior   = self._track_vars[track].get()
                valid   = valid_map[track]
                options = [_fmt(i) for i in valid]
                cb['values'] = options
                if options:
                    if prior in options:
                        cb.set(prior)                          # keep manual pick
                    elif track in best:
                        cb.set(_fmt(best[track]))              # use optimised pick
                    else:
                        cb.set(options[0])
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

        # Also update BDRA code labels for extra tracks (texture, fx)
        for extra_key in self._extra_track_lbls:
            self._refresh_labels_extra(extra_key)

    def _refresh_labels_extra(self, track_key: str) -> None:
        """Update the BDRA code label for an extra track (TEXTURE or FX)."""
        S   = self._S
        lbl = self._extra_track_lbls.get(track_key)
        if lbl is None:
            return
        inst = self._inst_extra(track_key)
        if inst is None or not inst.get('code'):
            lbl.config(text='', fg=S.TXT_DIM)
            return
        branch = self._branch()
        rules  = _br.BRANCH_RULES.get(branch, {}).get(track_key, {})
        ok     = _br.in_range(inst['code'], rules) if rules else True
        lbl.config(text=inst['code'], fg=S.GREEN if ok else S.YELLOW)

    def _refresh_score(self) -> None:
        """
        Run the five-principle validator; update score label, P1-P5 breakdown,
        and fix suggestion rows.

        Score colours:  ≥90 green · ≥70 yellow · ≥50 orange · <50 red.
        """
        S      = self._S
        branch = self._branch()

        sel = {}
        for t in self._track_cbs:
            inst = self._inst(t)
            if inst:
                sel[t] = inst['code']
        if not sel:
            return

        # Texture and fx contribute to the density budget (P4) but are kept
        # out of the P3 attack-separation check to avoid false onset conflicts
        # when intentionally layering texture over pads at the same A/R.
        density_extra = 0
        for extra_key in ('texture', 'fx'):
            extra_inst = self._inst_extra(extra_key)
            if extra_inst and extra_inst.get('code'):
                density_extra += _br.parse_bdra(extra_inst['code']).get('D', 0)

        result = _br.validate_selection(branch, sel, density_extra=density_extra)

        color = (S.GREEN  if result.score >= 90 else
                 S.YELLOW if result.score >= 70 else
                 S.ORANGE if result.score >= 50 else S.RED)

        self._score_lbl.config(text=f"{result.score}/100  {result.label}", fg=color)

        if result.violations:
            self._viol_lbl.config(text=f"· {result.violations[0]}", fg=S.YELLOW)
        elif result.warnings:
            self._viol_lbl.config(text=f"· {result.warnings[0]}", fg=S.TXT_DIM)
        else:
            self._viol_lbl.config(text='', fg=S.TXT_DIM)

        # ── P1-P5 principle icons ─────────────────────────────────────────
        status_cfg = {
            'pass': ('✓', S.GREEN),
            'warn': ('⚠', S.YELLOW),
            'fail': ('✗', S.RED),
        }
        for pid, lbl in self._principle_lbls.items():
            status = result.principles.get(pid, 'pass')
            icon, clr = status_cfg.get(status, ('?', S.TXT_DIM))
            lbl.config(text=f'{pid} {icon}', fg=clr)

        # ── Fix suggestions ───────────────────────────────────────────────
        fixes = _br.suggest_fixes(branch, self._catalogue, sel)
        for i, row_data in enumerate(self._fix_rows):
            if i < len(fixes):
                fix = fixes[i]
                track  = fix['track']
                inst   = fix['inst']
                gain   = fix['gain']
                row_data['fix'] = fix
                row_data['lbl'].config(
                    text=f"FIX {track.upper()} → {inst['name']}  {inst['code']}"
                         f"  (+{gain} pts → {fix['new_score']}/100)",
                )
                row_data['btn'].config(
                    command=lambda f=fix: self._apply_fix(f),
                )
                row_data['row'].pack(fill='x', pady=0)
            else:
                row_data['fix'] = None
                row_data['row'].pack_forget()

    def _on_kick_mute_toggle(self, mute_var: tk.BooleanVar) -> None:
        """KICK mute toggled — no label to dim (KICK label uses fixed TXT_DIM color)."""
        pass

    def _on_mute_toggle(self, track: str, mute_var: tk.BooleanVar, color: str) -> None:
        """Dim the track name label when muted; restore when unmuted."""
        lbl = self._track_name_lbls.get(track)
        if lbl:
            lbl.config(fg=self._S.TXT_DIM if mute_var.get() else color)

    def _on_extra_mute_toggle(self, track: str, mute_var: tk.BooleanVar, color: str) -> None:
        """Dim the extra track name label when muted; restore when unmuted."""
        lbl = self._extra_track_name_lbls.get(track)
        if lbl:
            lbl.config(fg=self._S.TXT_DIM if mute_var.get() else color)

    def _apply_fix(self, fix: dict) -> None:
        """Apply a single fix suggestion — set the combobox to the suggested instrument."""
        track = fix['track']
        inst  = fix['inst']
        cb    = self._track_cbs.get(track)
        if cb is None:
            return
        target = _fmt(inst)
        if target in cb['values']:
            cb.set(target)
        # trace fires _on_track_change → _refresh_score automatically

    def get_muted_tracks(self) -> set:
        """Return the set of track keys currently muted (excluded from advisor preview)."""
        muted = {t for t, mv in self._mute_vars.items() if mv.get()}
        muted.update(t for t, mv in self._extra_mute_vars.items() if mv.get())
        return muted

    def get_sample_assignments(self) -> dict:
        """Return the current sample assignments from the SAMPLES panel.

        Returns a {builder_key: file_path} dict suitable for passing to
        WAVRenderer.render_composition_to_wav(sample_assignments=...).
        Returns an empty dict when no samples have been assigned or the
        sample panel was not built.
        """
        if self._sample_panel is None:
            return {}
        return self._sample_panel.get_assignments()

    def set_play_fn(self, fn) -> None:
        """Inject the audio preview callable into the sample panel's ▶ buttons."""
        if self._sample_panel is not None:
            self._sample_panel.set_play_fn(fn)

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
            'texture' → extra combobox  (routed to _extra_track_cbs['texture'])
            'fx'      → extra combobox  (routed to _extra_track_cbs['fx'])

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

        # 'lead' and 'pad' use different keys in the palette vs the builder.
        # 'texture' and 'fx' go to their own extra-track comboboxes, handled below.
        _pal_to_builder = {'lead': 'melody', 'pad': 'pads'}

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

        # Sync texture and fx to their own extra-track comboboxes.
        # Match by GM number since palette instrument names can differ from
        # the names used in _EXTRA_INSTRUMENTS (e.g. "Sweep Pad" vs "Pad 8  Sweep").
        for extra_key in ('texture', 'fx'):
            inst_data = palette.get('instruments', {}).get(extra_key)
            if inst_data is None:
                continue
            cb = self._extra_track_cbs.get(extra_key)
            if cb is None:
                continue
            gm = inst_data.get('gm')
            matching = next(
                (_fmt_extra(i) for i in _EXTRA_INSTRUMENTS.get(extra_key, [])
                 if i['gm'] == gm),
                None,
            )
            if matching and matching in cb['values']:
                cb.set(matching)

        # ── Optimize around palette picks ─────────────────────────────────
        # Run coordinate descent with the palette instruments as the seed so
        # the score reaches 100/100 where possible.  Only swaps a palette pick
        # when doing so raises the overall BDRA score — genre character is
        # preserved for instruments that don't cause psychoacoustic violations.
        branch = self._branch()
        seed   = {t: self._inst(t) for t in self._track_cbs if self._inst(t)}
        best   = _br.best_selection(branch, self._catalogue, seed=seed)

        self._busy = True
        try:
            for track, inst in best.items():
                cb = self._track_cbs.get(track)
                if cb is None:
                    continue
                target = _fmt(inst)
                if target not in cb['values']:
                    # Instrument optimised to a catalogue entry not yet listed
                    # (shouldn't happen, but guard anyway)
                    cb['values'] = list(cb['values']) + [target]
                cb.set(target)
        finally:
            self._busy = False

        self._refresh_labels()
        self._refresh_score()

    def current_selection(self) -> dict:
        """
        Return the current instrument selection for all tracks.

        Returns
        -------
        dict with key 'branch' ('A'/'B'/'C') plus one entry per track.
        BDRA tracks: {'gm': int, 'name': str, 'code': 'B? D? A? R?'}
        Extra tracks (PERC/TEXTURE/FX): {'gm': int, 'name': str, 'code': ''}
        """
        sel: dict = {'branch': self._branch()}

        # BDRA melodic tracks
        for track in self._track_cbs:
            inst = self._inst(track)
            if inst:
                sel[track] = inst

        # Extra tracks — PERC / TEXTURE / FX
        for track_key in self._extra_track_cbs:
            inst = self._inst_extra(track_key)
            if inst:
                sel[track_key] = {
                    'gm':   inst['gm'],
                    'name': inst['name'],
                    'code': inst.get('code', ''),  # empty for percussion
                }

        return sel

    def _inst_extra(self, track_key: str) -> Optional[dict]:
        """Return the selected instrument dict for an extra (non-BDRA) track."""
        val = self._extra_track_vars.get(track_key, tk.StringVar()).get()
        return next(
            (i for i in _EXTRA_INSTRUMENTS.get(track_key, [])
             if _fmt_extra(i) == val),
            None,
        )

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


# ── Module-level helpers ──────────────────────────────────────────────────────

def _fmt(inst: dict) -> str:
    """Format a BDRA catalogue entry as the combobox display string."""
    return f"{inst['name']}  {inst['code']}"


def _fmt_extra(inst: dict) -> str:
    """Format an extra-track instrument as 'GM## — Name'."""
    return f"GM{inst['gm']:03d}  {inst['name']}"


# GM instrument lists for PERC, TEXTURE, and FX.
# These tracks are outside the BDRA catalogue and do not participate in
# the psychoacoustic scoring — the lists are chosen for musical utility.
_EXTRA_INSTRUMENTS: Dict[str, List[dict]] = {
    'percussion': [
        {'gm':  0, 'name': 'Standard Kit'},
        {'gm':  8, 'name': 'Room Kit'},
        {'gm': 16, 'name': 'Power Kit'},
        {'gm': 24, 'name': 'Electronic Kit'},
        {'gm': 25, 'name': 'TR-808 Kit'},
        {'gm': 32, 'name': 'Jazz Kit'},
        {'gm': 40, 'name': 'Brush Kit'},
        {'gm': 48, 'name': 'Orchestra Kit'},
    ],
    'texture': [
        # BDRA codes follow the same taxonomy as the pads catalogue.
        # Metallic Pad (A=1) is out of range for strict-A3 branches — it will
        # show yellow, which is correct (non-standard texture choice).
        {'gm': 48, 'name': 'Strings Ensemble 1', 'code': 'B1 D2 A3 R2'},
        {'gm': 49, 'name': 'Strings Ensemble 2', 'code': 'B1 D3 A3 R2'},
        {'gm': 50, 'name': 'Synth Strings 1',    'code': 'B2 D2 A3 R2'},
        {'gm': 88, 'name': 'Pad 1  New Age',      'code': 'B2 D2 A3 R3'},
        {'gm': 89, 'name': 'Pad 2  Warm',         'code': 'B1 D1 A3 R2'},
        {'gm': 90, 'name': 'Pad 3  Polysynth',    'code': 'B2 D2 A3 R2'},
        {'gm': 91, 'name': 'Pad 4  Choir',        'code': 'B1 D3 A3 R2'},
        {'gm': 92, 'name': 'Pad 5  Bowed',        'code': 'B1 D2 A3 R2'},
        {'gm': 93, 'name': 'Pad 6  Metallic',     'code': 'B3 D2 A1 R2'},
        {'gm': 94, 'name': 'Pad 7  Halo',         'code': 'B1 D2 A3 R2'},
        {'gm': 95, 'name': 'Pad 8  Sweep',        'code': 'B1 D3 A3 R2'},
    ],
    'fx': [
        # FX BDRA codes derived from their spectral character.
        # Crystal is sparse + instantaneous (same code as the arp catalogue entry).
        {'gm':  96, 'name': 'FX 1  Rain',       'code': 'B3 D3 A3 R3'},
        {'gm':  97, 'name': 'FX 2  Soundtrack', 'code': 'B3 D3 A3 R3'},
        {'gm':  98, 'name': 'FX 3  Crystal',    'code': 'B3 D1 A0 R3'},
        {'gm':  99, 'name': 'FX 4  Atmosphere', 'code': 'B1 D3 A3 R2'},
        {'gm': 100, 'name': 'FX 5  Brightness', 'code': 'B3 D3 A3 R3'},
        {'gm': 101, 'name': 'FX 6  Goblins',    'code': 'B2 D2 A2 R2'},
        {'gm': 102, 'name': 'FX 7  Echoes',     'code': 'B3 D3 A3 R3'},
        {'gm': 103, 'name': 'FX 8  Sci-fi',     'code': 'B3 D3 A3 R3'},
        {'gm': 122, 'name': 'Breath Noise',      'code': 'B2 D1 A0 R3'},
        {'gm': 123, 'name': 'Seashore',          'code': 'B1 D2 A3 R2'},
    ],
}
