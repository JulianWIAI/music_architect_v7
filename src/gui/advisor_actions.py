"""
src/gui/advisor_actions.py
━━━━━━━━━━━━━━━━━━━━━━━━━━
Action strip for the Production Advisor tab — preview, WAV download, MIDI
download, and vocal MIDI download with the instruments currently selected in
the advisor palette / InstrumentBuilder.

Purpose
───────
The advisor tab shows *what* instruments to use and *why*.  This module
closes the loop: the user can instantly hear the result before committing
anything to a DAW, and can download any combination of:
  · Full-beat WAV            — high-quality FluidSynth render
  · Full-beat MIDI           — same notes, new instrument program changes
  · Vocal-ready MIDI         — vocal_mask=True scaffold with new instruments

Render strategy
───────────────
WAV rendering via FluidSynth is tried first; if it fails the bar falls back
to pygame MIDI playback of the full-beat MIDI.  This handles the common case
on Windows where FluidSynth is installed but the WAV output path or audio
driver setup causes render failures.  FLUIDSYNTH_AVAILABLE only tests that
`fluidsynth --version` works — not that an actual WAV render succeeds.

The MIDI download is enabled as soon as the MIDI file is created (before the
FluidSynth render starts), so the user always gets a usable output even if
the WAV render fails.

Step logging
────────────
Each phase of the worker (compose / export-MIDI / FluidSynth) is logged via
log_fn so the user can see exactly where a failure occurs without digging
into a console traceback.

Threading model
───────────────
Compose + FluidSynth render run in a daemon background thread.  UI updates
are posted back to the main thread via Tkinter's widget.after(0, callable)
mechanism, which is safe to call from non-main threads without a shared queue.

Seed pinning
────────────
App calls set_seed(seed) after every successful generation.  The cached seed
is injected into the re-composition config so that chord progression, rhythm,
and structure are identical to the original — only the timbres change.
If no seed has been cached (first preview before any generation), a fresh
random seed is used for that session.

Dependency injection
────────────────────
All external dependencies are injected at construction time; AdvisorActionsBar
never imports from app.py.

    get_engine_fn() → CompositionEngine | None
        Called at render time (lazy engine loading supported).

    fluid_renderer  : FluidSynthRenderer | None
        Module-level singleton; may be None if FluidSynth is not installed.

    player          : MIDIPreviewPlayer
        Used for WAV and MIDI playback.

    build_config_fn() → CompositionConfig
        Reads the current state of all UI controls; must be called on the
        main thread.

    want_vocal_fn() → bool
        Returns True when the "Vocal-Ready Beat" checkbox is ticked.

    log_fn(str)
        Single-line log message (goes to the app's console panel).

    status_fn(str, color)
        Updates the main status bar.

    app_dir : str
        Application root directory; temp_output/ is created inside it.
"""
from __future__ import annotations

import os
import random
import shutil
import threading
from pathlib import Path
from tkinter import filedialog
from typing import Callable, Optional

import tkinter as tk
from src.gui.tooltips import ToolTip, TOOLTIPS
from src.rendering.wav_renderer import WAVRenderer as _WAVRenderer


class AdvisorActionsBar(tk.Frame):
    """
    Button strip for the Production Advisor tab.

    Provides four one-click actions on the current palette / InstrumentBuilder
    instrument selection:

      ▶  PREVIEW WITH INSTRUMENTS
            Re-composes with the pinned seed, renders WAV via FluidSynth, and
            auto-plays.  Falls back to pygame MIDI playback if WAV fails.

      ⬇  SAVE WAV
            Saves the rendered WAV.  Enabled only after a successful FluidSynth
            render.

      ⬇  STANDARD MIDI
            Saves the full-beat MIDI (same song structure, new instruments).
            Enabled as soon as the MIDI is written — before WAV render — so
            the user always gets a downloadable file.

      ⬇  VOCAL MIDI
            Saves the vocal-ready MIDI scaffold (vocal_mask=True, new instruments).
            Enabled only when vocal-ready was included in the preview render.

    Parameters
    ----------
    parent          : Tkinter parent widget (the advisor tab frame).
    styles          : The styles namespace S from src/gui/styles.py.
    get_engine_fn   : Callable → CompositionEngine | None.
    fluid_renderer  : FluidSynthRenderer instance (or None if unavailable).
    player          : MIDIPreviewPlayer instance for WAV and MIDI playback.
    build_config_fn : Callable → CompositionConfig (reads UI widget state).
    want_vocal_fn   : Callable → bool (checks the "Vocal-Ready" checkbox).
    log_fn          : Callable(str) — single-line log to the app console.
    status_fn       : Callable(str, color) — update the app status bar.
    app_dir         : Application root directory (temp_output/ lives here).
    save_pdf_fn     : Callable() | None — called when the user clicks
                      "EXPORT PDF".  Injected by app.py; omit to hide the
                      button entirely (backwards-compatible default).
    """

    def __init__(
        self,
        parent: tk.Widget,
        *,
        styles,
        get_engine_fn:      Callable,
        fluid_renderer,
        player,
        build_config_fn:    Callable,
        want_vocal_fn:      Callable[[], bool],
        log_fn:             Callable[[str], None],
        status_fn:          Callable[[str, str], None],
        app_dir:            str,
        save_pdf_fn:        Optional[Callable[[], None]] = None,
        export_audio_fn:    Optional[Callable[[str], None]] = None,
        get_muted_tracks_fn: Optional[Callable[[], set]] = None,
        apply_groove_fn:    Optional[Callable] = None,
    ) -> None:
        super().__init__(parent, bg=styles.BG2)

        self._S                  = styles
        self._get_engine         = get_engine_fn
        self._renderer           = fluid_renderer
        self._player             = player
        self._build_config       = build_config_fn
        self._want_vocal         = want_vocal_fn
        self._log                = log_fn
        self._status             = status_fn
        self._app_dir            = app_dir
        self._save_pdf           = save_pdf_fn
        # Called with the rendered WAV path to open the multi-format export dialog.
        self._export_audio       = export_audio_fn
        # Returns set of track keys to silence in the next preview render.
        self._get_muted_tracks   = get_muted_tracks_fn or (lambda: set())
        # Called after compose+export to apply current groove/mixer gains to
        # both the composition dict (built-in synth) and the MIDI (FluidSynth).
        # Signature: fn(comp: dict, mid_path: str, genre: str, bpm: float) -> str
        # Returns (possibly modified) mid_path.
        self._apply_groove_fn    = apply_groove_fn

        # Seed cached by App.set_seed() after every generation.
        # None → a fresh random seed is used for that preview session.
        self._seed: Optional[int] = None

        # Paths from the most recent preview render.
        self._wav_path:        Optional[str] = None
        self._midi_path:       Optional[str] = None   # full-beat MIDI
        self._vocal_midi_path: Optional[str] = None

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    # ── Button colour registry ────────────────────────────────────────────────
    # Stores (active_bg, active_fg, hover_bg) for each managed button so that
    # _enable_btn() can restore the correct colour after a disable/enable cycle.
    # Keys are tk.Button instances set during _build_ui().
    _btn_palette: dict = {}

    @staticmethod
    def _lighten(hex_col: str, factor: float = 1.22) -> str:
        """Return a lightened hex colour for hover states."""
        r = min(255, int(int(hex_col[1:3], 16) * factor))
        g = min(255, int(int(hex_col[3:5], 16) * factor))
        b = min(255, int(int(hex_col[5:7], 16) * factor))
        return f'#{r:02x}{g:02x}{b:02x}'

    def _enable_btn(self, btn: tk.Button) -> None:
        """Restore a button to its active colour scheme and enable clicks."""
        # Palette stores (bg, fg, bg_hover, accent) — accent is the highlight border colour.
        entry = self._btn_palette.get(btn, (self._S.BG_BTN, self._S.TXT_BRT, self._S.BG_BTN_HOV, self._S.BG3))
        bg, fg, bg_h, accent = entry
        btn.config(state=tk.NORMAL, bg=bg, fg=fg, cursor='hand2',
                   highlightbackground=accent)
        btn.bind('<Enter>', lambda e, _b=btn, _h=bg_h: _b.config(bg=_h))
        btn.bind('<Leave>', lambda e, _b=btn, _bg=bg: _b.config(bg=_bg))

    def _disable_btn(self, btn: tk.Button) -> None:
        """Grey out a button and remove hover effects."""
        btn.config(state=tk.DISABLED, bg=self._S.BG_BTN, fg=self._S.TXT_DIM,
                   cursor='arrow', highlightbackground=self._S.BG3)
        btn.unbind('<Enter>')
        btn.unbind('<Leave>')

    def _build_ui(self) -> None:
        """
        Create the separator and five action buttons.

        Matches the _cbtn pattern used by the rest of the app:
          bg=BG_BTN (dark), fg=TXT_BRT (bright white), bd=0,
          highlightthickness=1, highlightbackground=accent colour.

        This renders correctly on macOS (which overrides relief='flat' with
        native Aqua styling, turning coloured backgrounds light grey and
        making white text unreadable).  By keeping the dark BG_BTN fill and
        using a coloured 1px border for identity, each button is clearly
        legible on both macOS Retina and Windows.
        """
        S = self._S
        self._btn_palette = {}   # reset on re-build (shouldn't happen but be safe)

        # Thin divider line
        tk.Frame(self, bg=S.BG3, height=1).pack(fill='x', pady=(4, 0))

        row = tk.Frame(self, bg=S.BG2)
        row.pack(fill='x', pady=(5, 5), padx=2)

        # Per-button accent colour used for BOTH fg text AND the 1px highlight
        # border.  This matches the app's _cbtn pattern: coloured text on a dark
        # bg reads correctly on macOS (where Aqua overrides bg to native light
        # grey — white text would disappear, coloured text remains visible).
        # Colours are mid-saturation muted tones — not neon — so they look
        # professional on Retina and Windows displays alike.
        _ACCENT = {
            'preview': S.CYAN,    # steel blue  — primary listen/render action
            'export':  S.ORANGE,  # muted amber — audio file export
            'midi':    S.PURPLE,  # muted violet — MIDI output
            'vocal':   S.PINK,    # muted rose  — vocal scaffold
            'pdf':     S.GREEN,   # muted sage  — document export
        }

        def _btn(key: str, text: str, cmd, disabled: bool = False) -> tk.Button:
            """
            Create an action button matching the app's _cbtn style.

            fg = accent colour — readable on dark BG_BTN AND on macOS native
            light-grey button face (Aqua theme overrides bg but not fg).
            highlightbackground = same accent — 1px coloured border for identity.
            """
            accent = _ACCENT[key]
            b = tk.Button(
                row,
                text=text,
                font=('Consolas', 10, 'bold'),
                fg=S.TXT_DIM if disabled else accent,
                bg=S.BG_BTN,
                activeforeground=S.TXT_BRT,
                activebackground=S.BG_BTN_ACT,
                bd=0,
                padx=14, pady=6,
                cursor='arrow' if disabled else 'hand2',
                highlightthickness=1,
                highlightbackground=S.BG3 if disabled else accent,
                state=tk.DISABLED if disabled else tk.NORMAL,
                command=cmd,
                disabledforeground=S.TXT_DIM,
            )
            # Store (bg, fg, hover_bg, accent) so _enable_btn() can fully restore.
            self._btn_palette[b] = (S.BG_BTN, accent, S.BG_BTN_HOV, accent)

            if not disabled:
                b.bind('<Enter>', lambda e, _b=b: _b.config(bg=S.BG_BTN_HOV))
                b.bind('<Leave>', lambda e, _b=b: _b.config(bg=S.BG_BTN))
            return b

        # ▶ PREVIEW — always active once engine is loaded
        self._btn_preview = _btn('preview', '▶  PREVIEW WITH INSTRUMENTS', self._on_preview)
        self._btn_preview.pack(side='left', padx=(0, 3))
        ToolTip(self._btn_preview, TOOLTIPS['advisor_preview'])

        # ⬇ EXPORT AUDIO — enabled after successful render
        self._btn_export = _btn('export', '⬇  EXPORT AUDIO…', self._on_export_audio, disabled=True)
        self._btn_export.pack(side='left', padx=(0, 3))
        ToolTip(self._btn_export, TOOLTIPS.get('advisor_save_wav', 'Export rendered audio in multiple formats'))

        # ⬇ STANDARD MIDI — enabled as soon as the MIDI file is written
        self._btn_midi = _btn('midi', '⬇  STANDARD MIDI', self._on_save_midi, disabled=True)
        self._btn_midi.pack(side='left', padx=(0, 3))
        ToolTip(self._btn_midi, TOOLTIPS['advisor_save_midi'])

        # ⬇ VOCAL MIDI — enabled when vocal-ready was included in the preview
        self._btn_vocal = _btn('vocal', '⬇  VOCAL MIDI', self._on_save_vocal_midi, disabled=True)
        self._btn_vocal.pack(side='left', padx=(0, 3))
        ToolTip(self._btn_vocal, TOOLTIPS['advisor_save_vocal_midi'])

        # ⬇ EXPORT PDF — present only when the app injects save_pdf_fn
        if self._save_pdf is not None:
            self._btn_pdf = _btn('pdf', '⬇  EXPORT PDF', self._save_pdf)
            self._btn_pdf.pack(side='left')
            ToolTip(self._btn_pdf, TOOLTIPS['advisor_export_pdf'])

    # ── Public API ────────────────────────────────────────────────────────────

    def set_seed(self, seed: Optional[int]) -> None:
        """
        Cache the seed used by the most recent generation.

        App calls this after every successful generation so that the advisor
        preview re-uses the same seed, guaranteeing the note structure is
        identical (chord progression, rhythm, structure) — only timbres differ.
        """
        self._seed = seed

    # ── Button callbacks ──────────────────────────────────────────────────────

    def _on_preview(self) -> None:
        """
        Trigger a background re-compose + FluidSynth render.

        Guards:
          · Engine not loaded → log and return.
          · Button disabled during render to prevent overlapping threads.

        Note: FluidSynth availability is NOT checked here because
        FLUIDSYNTH_AVAILABLE only verifies `fluidsynth --version`, not that
        WAV rendering actually works.  The worker handles renderer=None
        gracefully and falls back to MIDI playback.
        """
        engine = self._get_engine()
        if engine is None:
            self._log("Composition engine not loaded — generate a song first.")
            return

        # Stop any currently playing audio BEFORE starting the render thread.
        # On Windows, pygame holds an open file handle on the WAV while it plays.
        # FluidSynth writes to the same temp path (advisor_preview.wav), so if
        # the file is still locked, FluidSynth exits with ACCESS DENIED, render()
        # returns False, and the preview silently falls back to MIDI playback —
        # which ignores the selected SoundFont entirely.
        self._player.stop()

        self._btn_preview.config(state=tk.DISABLED)
        self._status("RENDERING ADVISOR PREVIEW…", self._S.ORANGE)

        # Resolve seed on the main thread (avoids races with set_seed()).
        seed       = self._seed if self._seed is not None else random.randint(1, 999_999)  # 6 digits: short enough to read in a log and retype manually
        want_vocal = self._want_vocal()

        # Read all UI widget state on the main thread, then override seed.
        config            = self._build_config()
        config.seed_value = seed

        # Apply muted tracks: set enabled=False so the composition engine
        # omits those voices from the MIDI before FluidSynth renders.
        muted = self._get_muted_tracks()
        if muted:
            self._log(f"  Muted tracks: {', '.join(sorted(muted)).upper()}")
            for track_key in muted:
                # config.tracks uses 'lead' for melody; builder uses 'melody'
                cfg_key = 'lead' if track_key == 'melody' else track_key
                if cfg_key in config.tracks:
                    config.tracks[cfg_key]['enabled'] = False

        self._log(f"Advisor preview: composing (seed={seed}, genre={config.genre})…")

        threading.Thread(
            target=self._render_worker,
            args=(engine, config, want_vocal),
            daemon=True,
        ).start()

    def _render_worker(self, engine, config, want_vocal: bool) -> None:
        """
        Background thread: compose → export MIDI → FluidSynth WAV render.

        Phases
        ------
        1. Compose full beat (vocal_mask=False) and export to MIDI.
           Posts midi_ready immediately so the MIDI download is available
           even if the WAV render subsequently fails.

        2. FluidSynth WAV render.  Failures are treated as non-fatal:
           the MIDI is still usable and pygame MIDI playback is used as
           a fallback so the user can still audition the new instruments.

        3. If want_vocal: compose again with vocal_mask=True and export
           the vocal-ready MIDI.

        All UI callbacks are posted via self.after(0, …) — the safe
        cross-thread mechanism for Tkinter widgets.
        """
        try:
            temp_dir = Path(self._app_dir) / "temp_output"
            temp_dir.mkdir(exist_ok=True)
            genre = config.genre

            # ── Phase 1: compose + export MIDI ─────────────────────────────
            config.vocal_mask = False
            self.after(0, self._log, "  [1/3] Composing full beat…")
            comp     = engine.compose(config)
            mid_path = str(temp_dir / "advisor_preview.mid")
            engine.export_midi(comp, mid_path)

            # Apply the current Groove & Mixer settings so the advisor preview
            # reflects any gain/mute changes the user made in that panel.
            # _apply_groove_fn injects gains into comp (built-in synth path)
            # and re-processes the MIDI with GrooveProcessor (FluidSynth path).
            if self._apply_groove_fn is not None:
                try:
                    _bpm = float(comp.get('config', {}).get('bpm', 120.0))
                    mid_path = self._apply_groove_fn(comp, mid_path, genre, _bpm)
                except Exception:
                    pass   # non-fatal — render continues with ungrooved MIDI

            # Verify the MIDI file was actually written
            midi_ok = os.path.exists(mid_path) and os.path.getsize(mid_path) > 0
            if not midi_ok:
                # export_midi returned early (MIDI library unavailable)
                self.after(0, self._on_render_error,
                           "MIDI export produced an empty file — "
                           "check that midiutil is installed.")
                return

            midi_size = os.path.getsize(mid_path)
            self.after(0, self._log,
                       f"  [1/3] MIDI ready ({midi_size} bytes) — "
                       "click ⬇ STANDARD MIDI to save.")

            # Enable MIDI download immediately — before the (slower) WAV render
            self.after(0, self._on_midi_ready, mid_path)

            # ── Phase 2: FluidSynth WAV render ─────────────────────────────
            wav_path: Optional[str] = None
            if self._renderer is not None and self._renderer.is_available():
                # Log the active SF2 so the user can confirm the SoundFont
                # picker selection is being honoured (shows filename, not path).
                active = self._renderer.active_sf2(genre)
                sf2_label = os.path.basename(active) if active else 'none'
                self.after(0, self._log, f"  [2/3] FluidSynth WAV render  [{sf2_label}]…")
                _wav_out = str(temp_dir / "advisor_preview.wav")
                wav_ok   = self._renderer.render(mid_path, _wav_out, genre=genre)
                if wav_ok:
                    wav_path = _wav_out
                    self.after(0, self._log, "  [2/3] WAV render complete.")
                else:
                    # FluidSynth failed — log it; MIDI fallback will be used
                    self.after(
                        0, self._log,
                        "  [2/3] FluidSynth WAV render failed "
                        "(returncode ≠ 0 or output missing). "
                        "Falling back to MIDI playback.",
                    )
            else:
                self.after(0, self._log,
                           "  [2/3] FluidSynth not available — using MIDI playback.")

            # ── Phase 2b: built-in synth fallback ──────────────────────────
            # When FluidSynth is unavailable or failed, render via the
            # built-in synthesiser so the ⬇ EXPORT AUDIO button is enabled
            # and playback is deterministic (same seed → same audio every time).
            # Progress is logged every 500 events so the user sees activity
            # during the (potentially slow) pure-Python synthesis pass.
            if wav_path is None:
                self.after(0, self._log,
                           "  [2/3] Built-in synth fallback — rendering WAV "
                           "(may take ~30 s without C++ extension)…")
                _builtin_wav = str(temp_dir / "advisor_preview.wav")
                _last_logged = [0]

                def _adv_progress(done, total, _self=self, _ll=_last_logged):
                    # Log at most once per 500 events to avoid flooding the panel
                    if done - _ll[0] >= 500 or done == total:
                        _ll[0] = done
                        _self.after(0, _self._log,
                                    f"  [2/3] Synthesising… {done}/{total} events")

                try:
                    _WAVRenderer().render_composition_to_wav(
                        comp, _builtin_wav, progress_callback=_adv_progress)
                    wav_path = _builtin_wav
                    self.after(0, self._log,
                               "  [2/3] Built-in synth WAV ready.")
                except Exception as _e:
                    self.after(0, self._log,
                               f"  [2/3] Built-in synth render failed: {_e}")

            # ── Phase 3: vocal-ready MIDI ───────────────────────────────────
            vocal_mid_path: Optional[str] = None
            if want_vocal:
                self.after(0, self._log, "  [3/3] Composing vocal-ready version…")
                config.vocal_mask = True
                vr_comp           = engine.compose(config)
                config.vocal_mask = False       # restore for safety
                vocal_mid_path    = str(temp_dir / "advisor_vocal.mid")
                engine.export_midi(vr_comp, vocal_mid_path)
                if not (os.path.exists(vocal_mid_path)
                        and os.path.getsize(vocal_mid_path) > 0):
                    vocal_mid_path = None
                    self.after(0, self._log, "  [3/3] Vocal MIDI export failed.")
                else:
                    self.after(0, self._log, "  [3/3] Vocal MIDI ready.")
            else:
                self.after(0, self._log, "  [3/3] Vocal-ready skipped (checkbox off).")

            self.after(0, self._on_render_done, mid_path, wav_path, vocal_mid_path)

        except Exception as exc:
            self.after(0, self._on_render_error, str(exc))

    def _on_midi_ready(self, mid_path: str) -> None:
        """
        Main-thread callback: MIDI file written, enable the STANDARD MIDI button.

        Called early in the render — before the (slower) FluidSynth pass —
        so the user is never blocked on WAV rendering to get a MIDI.
        """
        self._midi_path = mid_path
        if os.path.exists(mid_path):
            self._enable_btn(self._btn_midi)

    def _on_render_done(
        self,
        mid_path:       str,
        wav_path:       Optional[str],
        vocal_mid_path: Optional[str],
    ) -> None:
        """
        Main-thread callback when the full render thread completes.

        Priority:
          1. Play WAV if available (best quality).
          2. Fall back to pygame MIDI playback if WAV render failed.
          3. If neither works, show an informative status message.
        """
        self._midi_path        = mid_path
        self._wav_path         = wav_path
        self._vocal_midi_path  = vocal_mid_path

        self._enable_btn(self._btn_preview)

        # WAV path is set → FluidSynth succeeded
        if wav_path and os.path.exists(wav_path):
            self._enable_btn(self._btn_export)
            self._player.play_wav(wav_path)
            self._status("ADVISOR PREVIEW  ▶  PLAYING (WAV)", self._S.CYAN)

        # No WAV → try MIDI playback as fallback
        elif mid_path and os.path.exists(mid_path):
            # pygame plays the MIDI with the soundfont / system synthesiser
            success = self._player.play_midi(mid_path)
            if success:
                self._status("ADVISOR PREVIEW  ▶  PLAYING (MIDI)", self._S.CYAN)
                self._log(
                    "WAV render failed — playing MIDI instead. "
                    "Install FluidSynth + an SF2 file for WAV quality."
                )
            else:
                self._status("ADVISOR PREVIEW — MIDI ready, playback unavailable",
                             self._S.YELLOW)
                self._log(
                    "MIDI file is ready for download. "
                    "Install pygame for in-app playback."
                )

        else:
            # Both MIDI and WAV unavailable — something went very wrong
            self._status("ADVISOR PREVIEW — compose/export failed", self._S.RED)

        # Vocal MIDI
        if vocal_mid_path and os.path.exists(vocal_mid_path):
            self._enable_btn(self._btn_vocal)
            self._log("Vocal MIDI ready — click  ⬇ VOCAL MIDI  to save.")

    def _on_render_error(self, error: str) -> None:
        """Main-thread error handler: re-enables button and logs the exception."""
        self._enable_btn(self._btn_preview)
        self._status("ADVISOR PREVIEW ERROR", self._S.RED)
        self._log(f"Advisor preview error: {error}")

    # ── Save dialogs ──────────────────────────────────────────────────────────

    def _on_export_audio(self) -> None:
        """Open the multi-format export dialog for the advisor preview WAV."""
        if not self._wav_path or not os.path.exists(self._wav_path):
            return
        if self._export_audio is not None:
            self._export_audio(self._wav_path)
        else:
            # Fallback: plain WAV copy if the export dialog isn't available.
            dest = filedialog.asksaveasfilename(
                defaultextension=".wav",
                filetypes=[("WAV audio", "*.wav")],
                initialfile="advisor_preview.wav",
            )
            if dest:
                shutil.copy2(self._wav_path, dest)
                self._log(f"Advisor WAV → {dest}")
                self._status("WAV SAVED", self._S.GREEN)

    def _on_save_midi(self) -> None:
        """
        Save the full-beat MIDI (same song structure, new instruments).

        This is the standard MIDI the user would drag into a DAW — it contains
        program_change events for all the instruments currently selected in the
        palette / InstrumentBuilder, embedded at MIDI generation time.
        """
        if not self._midi_path or not os.path.exists(self._midi_path):
            return
        dest = filedialog.asksaveasfilename(
            defaultextension=".mid",
            filetypes=[("MIDI", "*.mid")],
            initialfile="advisor_standard.mid",
        )
        if dest:
            shutil.copy2(self._midi_path, dest)
            self._log(f"Advisor Standard MIDI → {dest}")
            self._status("STANDARD MIDI SAVED", self._S.GREEN)

    def _on_save_vocal_midi(self) -> None:
        """
        Save the vocal-ready MIDI scaffold to a user-chosen path.

        The scaffold uses vocal_mask=True: melody is collapsed to a
        monophonic lead line and supporting tracks are attenuated.
        The lead instrument reflects the current selection, so the
        vocalist hears the correct timbre for their audition.
        """
        if not self._vocal_midi_path or not os.path.exists(self._vocal_midi_path):
            return
        dest = filedialog.asksaveasfilename(
            defaultextension=".mid",
            filetypes=[("MIDI", "*.mid")],
            initialfile="advisor_vocal_ready.mid",
        )
        if dest:
            shutil.copy2(self._vocal_midi_path, dest)
            self._log(f"Advisor Vocal MIDI → {dest}")
            self._status("VOCAL MIDI SAVED", self._S.GREEN)
