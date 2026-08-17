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
                Useful for comparing commercial fonts (e.g. Crisis 3.51,
                Vienna Special Edition Lite, SGM-v2.01) against the
                defaults without moving files into any folder.

Font type toggle (PRO / RETRO)
-------------------------------
When a custom SF2 is loaded, a PRO / RETRO toggle appears next to AUTO:

  PRO   — Full mastering pipeline (genre EQ, bus compressor, LUFS
          normalisation, true-peak limiter).  Use for professional-quality
          GM fonts like Crisis 3.51, MuseScore General, SGM-v2.01.

  RETRO — Mastering chain bypassed, gain capped at 0.50, chorus and
          reverb tamed.  Use for 8-bit / game SoundFonts (Mario, SNES)
          that clip and distort under the standard mastering chain.

The default when loading any new font is PRO, so professional fonts
work correctly without any extra clicks.

Persistence
-----------
The selected path and font type are saved to data/user_sf_override.json
so the choice survives between sessions.  On startup the widget restores
the last-used font and type automatically.

Integration
-----------
    picker = SoundFontPickerWidget(parent, styles=S,
                                   fluid_renderer=_FLUID_RENDERER,
                                   log_fn=self._log)
    picker.pack(fill='x', padx=4, pady=(0, 2))

The widget calls fluid_renderer.set_override(path) and
fluid_renderer.set_font_type(font_type) to change the active SF2 and
processing mode at runtime without recreating the renderer object.
"""

from __future__ import annotations

import json
import os
import pathlib
import tkinter as tk
from tkinter import filedialog
from typing import Callable, Optional

from src.gui.tooltips import ToolTip, TOOLTIPS

# Persisted user preference for custom SoundFont path and font type.
_PREF_FILE = (
    pathlib.Path(__file__).parent.parent.parent
    / "data" / "user_sf_override.json"
)

# Font type constants — stored in JSON and passed to the renderer.
_TYPE_PRO   = 'professional'
_TYPE_RETRO = 'retro'

# Toggle idle colours — dimmed when no custom font is loaded.
# Active state uses S.BG_BTN (background) + S.GREEN or S.ORANGE (border).
_TOGGLE_IDLE_BG = '#2a2a32'   # neutral dark — matches BG_BTN family
_TOGGLE_IDLE_FG = '#484858'   # dimmed text  — visually recedes when inactive


class SoundFontPickerWidget:
    """
    Single-row widget for SoundFont selection with PRO / RETRO type toggle.

    Layout (genre auto mode):
        SOUNDFONT  [genre auto]  [◉ LOAD SF2]  [AUTO]  [PRO▪]  [RETRO▪]

    Layout (custom SF loaded):
        SOUNDFONT  [filename.sf2]  [◉ LOAD SF2]  [AUTO]  [● PRO]  [RETRO]
                                                          or
                                                          [PRO]  [● RETRO]

    Parameters
    ----------
    parent : tk.Frame
        Container frame (advisor tab).
    styles : object
        App styles namespace S.
    fluid_renderer : FluidSynthRenderer
        The module-level renderer singleton; set_override() and
        set_font_type() are called on it.
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
        self._renderer  = fluid_renderer
        self._log       = log_fn or (lambda _: None)
        self._S         = styles
        self._font_type = _TYPE_PRO   # default for any newly loaded font

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

        # Outer container
        self._frame = tk.Frame(parent, bg=S.BG2)

        # ── Status row — shown when FluidSynth is not installed ─────────────
        if self._renderer is None:
            tk.Label(
                self._frame,
                text="FluidSynth not installed — install it to use a SoundFont for preview.",
                font=S.FN_X,
                fg=S.YELLOW,
                bg=S.BG2,
                anchor="w",
            ).pack(fill='x', padx=4, pady=(2, 0))

        # ── Picker row ────────────────────────────────────────────────────────
        pick_row = tk.Frame(self._frame, bg=S.BG2)
        pick_row.pack(fill='x')

        tk.Label(
            pick_row,
            text="SOUNDFONT",
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG2,
            anchor="w",
            width=10,
        ).pack(side="left", padx=(4, 2))

        # Active SF name label — updated whenever the user changes the font.
        # Shows "genre auto" by default; green when a valid custom SF2 is loaded.
        self._lbl = tk.Label(
            pick_row,
            text="genre auto" if self._renderer is not None else "—",
            font=S.FN_X,
            fg=S.CYAN if self._renderer is not None else S.TXT_DIM,
            bg=S.BG2,
            anchor="w",
        )
        self._lbl.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # ── Browse button ─────────────────────────────────────────────────────
        # fg=S.CYAN: coloured text reads on both dark BG_BTN and macOS native
        # light-grey button face (Aqua overrides bg but not fg).
        btn_browse = tk.Button(
            pick_row,
            text="◉  LOAD SF2",
            font=('Consolas', 10, 'bold'),
            fg=S.CYAN,
            bg=S.BG_BTN,
            activeforeground=S.TXT_BRT,
            activebackground=S.BG_BTN_ACT,
            bd=0,
            padx=12,
            pady=5,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=S.CYAN,
            command=self._on_browse,
        )
        btn_browse.bind("<Enter>", lambda e: btn_browse.configure(bg=S.BG_BTN_HOV))
        btn_browse.bind("<Leave>", lambda e: btn_browse.configure(bg=S.BG_BTN))
        btn_browse.pack(side="left", padx=(0, 4))
        ToolTip(btn_browse, TOOLTIPS['advisor_sf_browse'])

        # ── Auto button ───────────────────────────────────────────────────────
        _auto_fg = S.TXT if self._renderer is not None else S.TXT_DIM
        btn_auto = tk.Button(
            pick_row,
            text="AUTO",
            font=('Consolas', 9, 'bold'),
            fg=_auto_fg,
            bg=S.BG_BTN,
            activeforeground=S.TXT_BRT,
            activebackground=S.BG_BTN_ACT,
            bd=0,
            padx=10,
            pady=5,
            cursor="hand2" if self._renderer is not None else "arrow",
            highlightthickness=1,
            highlightbackground=S.BG3,
            state=tk.NORMAL if self._renderer is not None else tk.DISABLED,
            command=self._on_clear,
        )
        if self._renderer is not None:
            btn_auto.bind("<Enter>", lambda e: btn_auto.configure(bg=S.BG_BTN_HOV))
            btn_auto.bind("<Leave>", lambda e: btn_auto.configure(bg=S.BG_BTN))
        btn_auto.pack(side="left", padx=(0, 6))
        ToolTip(btn_auto, TOOLTIPS['advisor_sf_auto'])

        # ── Separator ─────────────────────────────────────────────────────────
        tk.Frame(pick_row, bg=S.BG3, width=1, height=20).pack(
            side="left", padx=(0, 6), pady=2
        )

        # ── PRO / RETRO toggle buttons ────────────────────────────────────────
        # Both are always visible.  They are disabled (dimmed) while genre auto
        # is active because the mastering mode only matters for custom fonts.
        # Uses same dark-bg / highlight-border pattern as the rest of the app.
        self._btn_pro = tk.Button(
            pick_row,
            text="PRO",
            font=('Consolas', 9, 'bold'),
            fg=_TOGGLE_IDLE_FG,
            bg=_TOGGLE_IDLE_BG,
            activeforeground=S.TXT_BRT,
            activebackground=S.BG_BTN_ACT,
            bd=0,
            padx=9,
            pady=5,
            cursor="arrow",
            highlightthickness=1,
            highlightbackground=S.BG3,
            state=tk.DISABLED,
            command=lambda: self._on_set_type(_TYPE_PRO),
        )
        self._btn_pro.pack(side="left", padx=(0, 2))
        ToolTip(self._btn_pro, TOOLTIPS['advisor_sf_pro'])
        # Store S reference for _update_toggle (called after build)
        self._S = S

        self._btn_retro = tk.Button(
            pick_row,
            text="RETRO",
            font=('Consolas', 9, 'bold'),
            fg=_TOGGLE_IDLE_FG,
            bg=_TOGGLE_IDLE_BG,
            activeforeground=S.TXT_BRT,
            activebackground=S.BG_BTN_ACT,
            bd=0,
            padx=9,
            pady=5,
            cursor="arrow",
            highlightthickness=1,
            highlightbackground=S.BG3,
            state=tk.DISABLED,
            command=lambda: self._on_set_type(_TYPE_RETRO),
        )
        self._btn_retro.pack(side="left", padx=(0, 4))
        ToolTip(self._btn_retro, TOOLTIPS['advisor_sf_retro'])

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
            # Default new fonts to Professional — the user can switch to
            # Retro explicitly if it turns out to be a game SoundFont.
            self._font_type = _TYPE_PRO
            self._apply(path)
            self._persist(path)

    def _on_clear(self) -> None:
        """Revert to SoundFontLibrary genre-routing (clear any override)."""
        if self._renderer is not None:
            self._renderer.set_override(None)
            self._renderer.set_font_type(_TYPE_PRO)
        self._font_type = _TYPE_PRO
        self._lbl.config(text="genre auto", fg=self._S.CYAN)
        self._update_toggle(has_override=False)
        self._persist(None)
        self._log("SoundFont → genre auto-routing")

    def _on_set_type(self, font_type: str) -> None:
        """Called when the user clicks PRO or RETRO."""
        self._font_type = font_type
        if self._renderer is not None:
            self._renderer.set_font_type(font_type)
        self._update_toggle(has_override=True)
        label = "Professional (full mastering)" if font_type == _TYPE_PRO else "Retro/Game (mastering bypassed)"
        self._log(f"SoundFont type → {label}")
        self._persist_type_only()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply(self, path: str) -> None:
        """Tell the renderer to use *path* and update the label.

        Guards the renderer calls so the widget works even when
        fluid_renderer is None (FluidSynth not installed).  The path and
        type are still persisted for when FluidSynth is installed later.
        """
        if self._renderer is not None:
            self._renderer.set_override(path)
            self._renderer.set_font_type(self._font_type)

        name    = os.path.basename(path)
        display = name if len(name) <= 36 else name[:33] + "…"

        if os.path.exists(path):
            self._lbl.config(text=display, fg=self._S.GREEN)
            self._log(f"SoundFont → {name}")
        else:
            self._lbl.config(text=f"? {display}", fg=self._S.YELLOW)
            self._log(f"SoundFont → {name}  [WARNING: file not found at this path]")

        # Enable and refresh the PRO/RETRO toggle buttons.
        self._update_toggle(has_override=True)

    def _update_toggle(self, has_override: bool) -> None:
        """Enable/disable and visually select PRO or RETRO buttons.

        When genre auto is active (has_override=False) both buttons are
        greyed out — the mastering type only matters for custom fonts.

        When a custom font is active the selected button gets a coloured
        highlight border (green for PRO, amber for RETRO) and bright text;
        the unselected button reverts to the idle dimmed state.

        This follows the same dark-bg / coloured-border pattern as _cbtn
        so both buttons stay readable on macOS regardless of the Aqua theme.
        """
        S = self._S

        if not has_override:
            # Disabled state — genre auto, no custom font loaded.
            for btn in (self._btn_pro, self._btn_retro):
                btn.configure(
                    state=tk.DISABLED,
                    fg=_TOGGLE_IDLE_FG,
                    bg=_TOGGLE_IDLE_BG,
                    highlightbackground=S.BG3,
                    cursor="arrow",
                )
            return

        # Custom font active — highlight the selected mode via border colour.
        is_pro = self._font_type == _TYPE_PRO

        # Active button: coloured fg + coloured border — reads on macOS native
        # light button face (Aqua overrides bg but not fg).
        self._btn_pro.configure(
            state=tk.NORMAL,
            cursor="hand2",
            bg=S.BG_BTN,
            fg=S.GREEN         if is_pro  else _TOGGLE_IDLE_FG,
            highlightbackground=S.GREEN  if is_pro  else S.BG3,
        )
        self._btn_retro.configure(
            state=tk.NORMAL,
            cursor="hand2",
            bg=S.BG_BTN,
            fg=S.ORANGE        if not is_pro else _TOGGLE_IDLE_FG,
            highlightbackground=S.ORANGE if not is_pro else S.BG3,
        )

    def _persist(self, path: Optional[str]) -> None:
        """Write the current path and font type to disk for next session."""
        try:
            _PREF_FILE.parent.mkdir(parents=True, exist_ok=True)
            _PREF_FILE.write_text(
                json.dumps({"override": path, "font_type": self._font_type}),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _persist_type_only(self) -> None:
        """Update only the font_type field in the persisted JSON, keeping path."""
        try:
            data = json.loads(_PREF_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        data["font_type"] = self._font_type
        try:
            _PREF_FILE.parent.mkdir(parents=True, exist_ok=True)
            _PREF_FILE.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

    def _restore(self) -> None:
        """On startup, re-apply the SF and type that were active last session."""
        try:
            data = json.loads(_PREF_FILE.read_text(encoding="utf-8"))
            # Restore font type first so _apply() sends the right value.
            saved_type = data.get("font_type", _TYPE_PRO)
            if saved_type in (_TYPE_PRO, _TYPE_RETRO):
                self._font_type = saved_type
            path = data.get("override")
            if path and os.path.exists(path):
                self._apply(path)
                # Log is suppressed here; the widget label shows the name.
        except Exception:
            pass
