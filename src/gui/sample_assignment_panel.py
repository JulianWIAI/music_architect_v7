"""
src/gui/sample_assignment_panel.py
────────────────────────────────────
Collapsible panel for per-track sample file assignment.

One row per melodic track (BASS, CHORDS, LEAD, ARP, PAD, STABS, TEXTURE, FX).
The user browses to a single audio file via the OS file dialog — no folder
scanning, so the UI never freezes.

The panel is style-compatible with InstrumentBuilder: it accepts the same
`styles` object (attribute access: BG2, FN_S, FN_X, TXT_DIM, TXT_BRT,
PINK, BG_BTN, BG_BTN_ACT, BG_BTN_HOV, GREEN, YELLOW).

Public API
----------
SampleAssignmentPanel(parent, styles)
    get_assignments() -> dict[str, str]
        Returns {builder_key: file_path} for every track that has a sample.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import Dict, Optional

# File types presented in the OS browser dialog
_FILE_TYPES = [
    ('Audio files',  '*.wav *.aiff *.aif *.flac *.ogg *.mp3'),
    ('WAV',          '*.wav'),
    ('All files',    '*.*'),
]

# Rows displayed in the panel: (builder_key, display_label)
_TRACKS = [
    ('bass',    'BASS'),
    ('chords',  'CHORDS'),
    ('melody',  'LEAD'),
    ('arp',     'ARP'),
    ('pads',    'PAD'),
    ('stabs',   'STABS'),
    ('texture', 'TEXTURE'),
    ('fx',      'FX'),
]

# Maximum filename length shown in the label before truncation
_MAX_LABEL = 22


class SampleAssignmentPanel(tk.Frame):
    """
    Collapsible sample-assignment panel.

    Parameters
    ----------
    parent : tk.Widget
        Parent widget (typically the InstrumentBuilder content frame).
    styles : object
        Styles namespace with colour / font attributes (same object used by
        InstrumentBuilder and the rest of the app).
    """

    def __init__(self, parent: tk.Widget, styles) -> None:
        S = styles
        super().__init__(parent, bg=S.BG2)
        self._S           = S
        self._expanded    = True
        # builder_key → absolute file path
        self._assignments: Dict[str, str]     = {}
        # builder_key → path label widget (updated on browse / clear)
        self._path_lbls:   Dict[str, tk.Label] = {}

        self._build_ui()

    # ── Public API ──────────────────────────────────────────────────────────

    def get_assignments(self) -> Dict[str, str]:
        """Return a copy of the current {builder_key: file_path} mapping."""
        return dict(self._assignments)

    # ── Construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        S = self._S

        # Toggle header — matches InstrumentBuilder header style
        hdr = tk.Frame(self, bg=S.BG2)
        hdr.pack(fill='x', pady=(2, 0))

        self._toggle_btn = tk.Button(
            hdr,
            text='▼ SAMPLES',
            font=S.FN_S,
            fg=S.PINK,
            bg=S.BG2,
            bd=0,
            activebackground=S.BG3 if hasattr(S, 'BG3') else S.BG2,
            activeforeground=S.PINK,
            cursor='hand2',
            anchor='w',
            command=self._toggle,
        )
        self._toggle_btn.pack(side='left')

        status_lbl = tk.Label(
            hdr,
            text='',
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG2,
        )
        status_lbl.pack(side='left', padx=6)
        self._status_lbl = status_lbl

        # Collapsible content frame
        self._content = tk.Frame(self, bg=S.BG2)
        self._content.pack(fill='x')

        for track_key, display in _TRACKS:
            self._build_row(track_key, display)

    def _build_row(self, track_key: str, display: str) -> None:
        S = self._S
        row = tk.Frame(self._content, bg=S.BG2)
        row.pack(fill='x', padx=4, pady=1)

        # Track name label (fixed width so filename column aligns)
        tk.Label(
            row,
            text=display,
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG2,
            width=7,
            anchor='w',
        ).pack(side='left')

        # Filename label — shows truncated basename or dash when empty
        path_lbl = tk.Label(
            row,
            text='—',
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG2,
            anchor='w',
        )
        path_lbl.pack(side='left', fill='x', expand=True)
        self._path_lbls[track_key] = path_lbl

        # Clear button
        clr = tk.Button(
            row,
            text='✕',
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG2,
            bd=0,
            activeforeground=S.YELLOW if hasattr(S, 'YELLOW') else S.TXT_DIM,
            activebackground=S.BG2,
            cursor='hand2',
            command=lambda k=track_key: self._clear(k),
        )
        clr.pack(side='right', padx=(0, 2))

        # Browse button — consistent with BG_BTN buttons elsewhere in the app
        brw = tk.Button(
            row,
            text='Browse',
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG_BTN if hasattr(S, 'BG_BTN') else S.BG2,
            bd=0,
            activeforeground=S.TXT_BRT if hasattr(S, 'TXT_BRT') else S.TXT_DIM,
            activebackground=S.BG_BTN_ACT if hasattr(S, 'BG_BTN_ACT') else S.BG2,
            cursor='hand2',
            command=lambda k=track_key, d=display: self._browse(k, d),
        )
        brw.pack(side='right', padx=2)
        # Hover effect
        if hasattr(S, 'BG_BTN_HOV'):
            brw.bind('<Enter>', lambda e, b=brw: b.configure(bg=S.BG_BTN_HOV))
            brw.bind('<Leave>', lambda e, b=brw: b.configure(
                bg=S.BG_BTN if hasattr(S, 'BG_BTN') else S.BG2))

    # ── Interaction ─────────────────────────────────────────────────────────

    def _browse(self, track_key: str, display: str) -> None:
        """Open OS file dialog (non-blocking, returns immediately when cancelled)."""
        path = filedialog.askopenfilename(
            title=f'Select sample for {display}',
            filetypes=_FILE_TYPES,
        )
        if path:
            self._set(track_key, path)

    def _set(self, track_key: str, path: str) -> None:
        self._assignments[track_key] = path
        name = Path(path).name
        short = name if len(name) <= _MAX_LABEL else name[:_MAX_LABEL - 1] + '…'
        lbl = self._path_lbls.get(track_key)
        if lbl:
            lbl.config(text=short, fg=self._S.GREEN if hasattr(self._S, 'GREEN') else self._S.TXT_DIM)
        self._update_status()

    def _clear(self, track_key: str) -> None:
        self._assignments.pop(track_key, None)
        lbl = self._path_lbls.get(track_key)
        if lbl:
            lbl.config(text='—', fg=self._S.TXT_DIM)
        self._update_status()

    def _update_status(self) -> None:
        n = len(self._assignments)
        self._status_lbl.config(
            text=f'({n} assigned)' if n > 0 else '',
            fg=self._S.CYAN if hasattr(self._S, 'CYAN') else self._S.TXT_DIM,
        )

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        arrow = '▼' if self._expanded else '▶'
        self._toggle_btn.config(text=f'{arrow} SAMPLES')
        if self._expanded:
            self._content.pack(fill='x')
        else:
            self._content.pack_forget()
