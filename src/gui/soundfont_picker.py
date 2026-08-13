"""
src.gui.soundfont_picker
-------------------------
Compact widget that lets the user select any .sf2 SoundFont from their
file system and use it for MIDI preview rendering.

Design rationale
----------------
The tool ships without bundled SoundFonts and discovers installed files
from standard paths via SoundFontLibrary.  This widget gives users two
modes:

  Genre auto  — SoundFontLibrary routes each genre to the best matching
                installed font (Fluid R3 for trap/hiphop, GeneralUser GS
                for pop/edm, Arachno for cinematic/classical).

  Custom .sf2 — User browses to any .sf2 on their PC.  The file stays
                active for all previews until "Genre auto" is clicked.
                Useful for comparing commercial fonts (e.g. Vienna Special
                Edition Lite, Musescore General, SGM-v2.01) against the
                defaults without moving files into any folder.

Persistence
-----------
The selected path is saved to data/user_sf_override.json so the choice
survives between sessions.  On startup the widget restores the last-used
font automatically, checking that the file still exists before applying.

Integration
-----------
    picker = SoundFontPickerWidget(parent, styles=S,
                                   fluid_renderer=_FLUID_RENDERER,
                                   log_fn=self._log)
    picker.pack(fill='x', padx=4, pady=(0, 2))

The widget calls fluid_renderer.set_override(path) — added in this
session to FluidSynthRenderer — to change the active SF2 at runtime
without recreating the renderer object.
"""

from __future__ import annotations

import json
import os
import pathlib
import tkinter as tk
from tkinter import filedialog
from typing import Callable, Optional

from src.gui.tooltips import ToolTip, TOOLTIPS

# Persisted user preference for custom SoundFont path.
_PREF_FILE = (
    pathlib.Path(__file__).parent.parent.parent
    / "data" / "user_sf_override.json"
)


class SoundFontPickerWidget:
    """
    Single-row widget for SoundFont selection.

    Layout:
        SOUNDFONT  [current sf name or 'genre auto']  [Browse .sf2…]  [Genre auto]

    Parameters
    ----------
    parent : tk.Frame
        Container frame (advisor tab).
    styles : object
        App styles namespace S.
    fluid_renderer : FluidSynthRenderer
        The module-level renderer singleton; set_override() is called on it.
    log_fn : Callable[[str], None], optional
        Single-line log callback for the app console.
    """

    def __init__(
        self,
        parent: tk.Frame,
        *,
        styles,
        fluid_renderer,
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._renderer = fluid_renderer
        self._log      = log_fn or (lambda _: None)
        self._S        = styles

        self._build(parent)
        self._restore()     # apply persisted SF choice from last session

    # ------------------------------------------------------------------
    # Public layout
    # ------------------------------------------------------------------

    def pack(self, **kwargs) -> None:
        self._frame.pack(**kwargs)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build(self, parent: tk.Frame) -> None:
        S = self._S
        self._frame = tk.Frame(parent, bg=S.BG2)

        tk.Label(
            self._frame,
            text="SOUNDFONT",
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG2,
            anchor="w",
            width=10,
        ).pack(side="left", padx=(4, 2))

        # Active SF name label — updated whenever the user changes the font.
        self._lbl = tk.Label(
            self._frame,
            text="genre auto",
            font=S.FN_X,
            fg=S.CYAN,
            bg=S.BG2,
            anchor="w",
        )
        self._lbl.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # Browse button — opens system file dialog for any .sf2
        btn_browse = tk.Button(
            self._frame,
            text="Browse .sf2 …",
            font=S.FN_S,
            fg=S.TXT_BRT,
            bg=S.BG_BTN,
            activeforeground=S.TXT_BRT,
            activebackground=S.BG_BTN_ACT,
            bd=0,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self._on_browse,
        )
        btn_browse.bind("<Enter>", lambda e: btn_browse.configure(bg=S.BG_BTN_HOV))
        btn_browse.bind("<Leave>", lambda e: btn_browse.configure(bg=S.BG_BTN))
        btn_browse.pack(side="left", padx=(0, 4))
        ToolTip(btn_browse, TOOLTIPS['advisor_sf_browse'])

        # Genre auto button — reverts to SoundFontLibrary routing
        btn_auto = tk.Button(
            self._frame,
            text="Genre auto",
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG_BTN,
            activeforeground=S.TXT_BRT,
            activebackground=S.BG_BTN_ACT,
            bd=0,
            padx=8,
            pady=3,
            cursor="hand2",
            command=self._on_clear,
        )
        btn_auto.bind("<Enter>", lambda e: btn_auto.configure(bg=S.BG_BTN_HOV))
        btn_auto.bind("<Leave>", lambda e: btn_auto.configure(bg=S.BG_BTN))
        btn_auto.pack(side="left", padx=(0, 4))
        ToolTip(btn_auto, TOOLTIPS['advisor_sf_auto'])

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_browse(self) -> None:
        """Open file dialog — user picks any .sf2 on their PC."""
        path = filedialog.askopenfilename(
            title="Select SoundFont (.sf2)",
            filetypes=[
                ("SoundFont 2", "*.sf2"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._apply(path)
            self._persist(path)

    def _on_clear(self) -> None:
        """Revert to SoundFontLibrary genre-routing (clear any override)."""
        self._renderer.set_override(None)
        self._lbl.config(text="genre auto", fg=self._S.CYAN)
        self._persist(None)
        self._log("SoundFont → genre auto-routing")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply(self, path: str) -> None:
        """Tell the renderer to use *path* and update the label.

        set_override() stores the path unconditionally; we still check
        existence here for immediate user feedback (orange label + warning
        log) without blocking the selection.  The renderer's render() will
        fall back to genre-auto if the file is gone by render time.
        """
        self._renderer.set_override(path)
        name    = os.path.basename(path)
        display = name if len(name) <= 40 else name[:37] + "…"

        if os.path.exists(path):
            self._lbl.config(text=display, fg=self._S.GREEN)
            self._log(f"SoundFont → {name}")
        else:
            # Path accepted but file missing — warn the user visibly
            self._lbl.config(text=f"? {display}", fg=self._S.YELLOW)
            self._log(f"SoundFont → {name}  [WARNING: file not found at this path]")

    def _persist(self, path: Optional[str]) -> None:
        """Write the current choice to disk for next session."""
        try:
            _PREF_FILE.parent.mkdir(parents=True, exist_ok=True)
            _PREF_FILE.write_text(
                json.dumps({"override": path}), encoding="utf-8"
            )
        except Exception:
            pass

    def _restore(self) -> None:
        """On startup, re-apply the SF that was active in the last session."""
        try:
            data = json.loads(_PREF_FILE.read_text(encoding="utf-8"))
            path = data.get("override")
            if path and os.path.exists(path):
                self._apply(path)
                # Log is suppressed here; the widget shows the restored name.
        except Exception:
            pass
