import sys
import os
import threading
import queue
import random
import json
import time as time_module
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from src.composition.composition_engine import CompositionEngine
    from src.composition.composition_config import CompositionConfig
    from src.composition.genre_constants import GENRE_BPM, GENRE_INSTRUMENTS, GENRE_SCALES, GENRE_CHORD_QUALITIES, STRUCTURE_TEMPLATES
    from src.seeds.seed_builder import SeedBuilder
    from src.rendering.wav_renderer import WAVRenderer
    ENGINE_AVAILABLE = True
    IMPORT_ERROR = ""
except ImportError as e:
    ENGINE_AVAILABLE = False
    IMPORT_ERROR = str(e)

try:
    from src.arrangement.fusion_config import FusionConfig
    from src.arrangement.fusion_presets import FUSION_PRESETS
    FUSION_AVAILABLE = True
except ImportError:
    FUSION_AVAILABLE = False
    FUSION_PRESETS = {}

try:
    import pygame
    import pygame.mixer
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

try:
    from src.generation.prompt_decoder import SemanticCipher, DecodedParams
    PROMPT_DECODER_AVAILABLE = True
except ImportError:
    PROMPT_DECODER_AVAILABLE = False

from src.gui.styles import S
from src.gui.constants import GM_INSTRUMENTS, DRUM_KITS, ROLE_INSTRUMENTS, NOTES, QUALITIES
from src.gui.midi_preview_player import MIDIPreviewPlayer
from src.gui.tooltips import ToolTip, TOOLTIPS
from src.gui.scrollable_frame import ScrollableFrame
from src.gui.collapsible_section import CollapsibleSection
from src.gui.track_instrument_row import TrackInstrumentRow

try:
    from src.rendering.fluidsynth_renderer import FluidSynthRenderer
    _FLUID_RENDERER = FluidSynthRenderer()
    FLUIDSYNTH_AVAILABLE = _FLUID_RENDERER.is_available()
except Exception:
    _FLUID_RENDERER     = None   # type: ignore
    FLUIDSYNTH_AVAILABLE = False

try:
    from src.export.utau_bridge import export as utau_export, RawNote
    UTAU_AVAILABLE = True
except ImportError:
    UTAU_AVAILABLE = False

try:
    from src.gui.instrument_builder import InstrumentBuilder
    INSTRUMENT_BUILDER_AVAILABLE = True
except ImportError:
    InstrumentBuilder = None          # type: ignore
    INSTRUMENT_BUILDER_AVAILABLE = False

try:
    from src.gui.advisor_actions import AdvisorActionsBar
    ADVISOR_ACTIONS_AVAILABLE = True
except ImportError:
    AdvisorActionsBar = None          # type: ignore
    ADVISOR_ACTIONS_AVAILABLE = False

try:
    from src.gui.advisor_query_panel import AdvisorQueryPanel
    ADVISOR_QUERY_AVAILABLE = True
except ImportError:
    AdvisorQueryPanel = None          # type: ignore
    ADVISOR_QUERY_AVAILABLE = False

try:
    from src.gui.fx_variant_panel import FxVariantPanel
    from src.composition.fx_chain_selector import FxChainSelector
    FX_VARIANT_AVAILABLE = True
except ImportError:
    FxVariantPanel = None             # type: ignore
    FxChainSelector = None            # type: ignore
    FX_VARIANT_AVAILABLE = False

try:
    from src.gui.soundfont_picker import SoundFontPickerWidget
    SF_PICKER_AVAILABLE = True
except ImportError:
    SoundFontPickerWidget = None      # type: ignore
    SF_PICKER_AVAILABLE = False

from src.gui.instrument_description_label import InstrumentDescriptionLabel
from src.composition.gm_descriptions import get_drum_description

try:
    from src.gui.spectral_chart import build_spectral_chart
    SPECTRAL_CHART_AVAILABLE = True
except ImportError:
    SPECTRAL_CHART_AVAILABLE = False

try:
    from src.composition.corpus_matcher import CorpusMatcher
    _CORPUS_MATCHER = CorpusMatcher()
    CORPUS_MATCH_AVAILABLE = True
except Exception:
    _CORPUS_MATCHER = None          # type: ignore
    CORPUS_MATCH_AVAILABLE = False

try:
    from src.gui.track_metadata_panel import TrackMetadataPanel
    from src.gui.waveform_widget import WaveformWidget
    from src.audio.audio_metadata import metadata_from_composition
    PLAYER_WIDGETS_AVAILABLE = True
except ImportError:
    TrackMetadataPanel = None       # type: ignore
    WaveformWidget     = None       # type: ignore
    PLAYER_WIDGETS_AVAILABLE = False

try:
    from src.gui.export_dialog import ExportDialog
    EXPORT_DIALOG_AVAILABLE = True
except ImportError:
    ExportDialog = None             # type: ignore
    EXPORT_DIALOG_AVAILABLE = False

try:
    from src.gui.mixer_panel import MixerPanel
    from src.midi.groove_processor import GrooveProcessor
    from src.midi.groove_settings import SongGrooveSettings
    GROOVE_AVAILABLE = True
except ImportError:
    MixerPanel       = None         # type: ignore
    GrooveProcessor  = None         # type: ignore
    SongGrooveSettings = None       # type: ignore
    GROOVE_AVAILABLE = False

try:
    from src.gui.timbre_editor_panel import TimbreEditorPanel
    TIMBRE_EDITOR_AVAILABLE = True
except ImportError:
    TimbreEditorPanel = None        # type: ignore
    TIMBRE_EDITOR_AVAILABLE = False


from src.gui.fader_utils import (
    _pos_to_db, _db_to_pos, gain_db_to_volume,
    _GAIN_STEPS, _GAIN_INF_FLOOR,
)

# Composition track name → groove settings key (same mapping as groove_processor._MIDI_NAME_TO_KEY)
_COMP_TRACK_TO_GROOVE_KEY = {
    '01_Kick':       'drums',
    '02_Percussion': 'percussion',
    '03_Bass':       'bass',
    '04_Melody':     'lead',
    '05_Chords':     'chords',
    '06_Pad':        'pad',
    '07_Arp':        'arp',
    '08_Stabs':      'stabs',
    '09_Texture':    'texture',
    '10_FX':         'fx',
}


def _inject_track_gains(composition: dict, groove_settings) -> None:
    """Write per-track linear gain into track_info so BuiltinSynthesizer can apply it."""
    if groove_settings is None:
        return
    ti = composition.get('track_info', {})
    for midi_name, groove_key in _COMP_TRACK_TO_GROOVE_KEY.items():
        if midi_name in ti:
            gdb = groove_settings.get(groove_key).gain_db
            # Treat ≤ -59.9 dB as -∞ (linear gain 0 = silence)
            ti[midi_name]['gain'] = 0.0 if gdb <= -59.9 else 10.0 ** (gdb / 20.0)


class SeedComposerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Seed Composer — Professional Music Generation Studio")
        self.root.geometry("1400x960")
        self.root.minsize(1100, 850)
        self.root.configure(bg=S.BG)

        self.engine = None
        self.current_composition = None
        self.current_midi_path = None
        self.current_wav_path = None
        # FX chain variant: 'bright', 'neutral', or 'dark'.
        # Updated from the composition seed after generation.
        self._current_variant_id = 'neutral'
        # Expand/collapse state: True when the left control panel is hidden
        # and the advisor fills the full window width.
        self._is_expanded = False
        self.vocal_ready_midi_path = None
        self.vocal_ready_wav_path = None
        self.vocal_ready_composition = None
        self.player = MIDIPreviewPlayer()
        self.msg_queue = queue.Queue()
        self.is_generating = False
        self.seeds_loaded = False
        self.track_vars = {}
        self.generation_counter = 0
        self._lyrics_json: dict = {}        # filled-out lyric scaffold from AI
        self._lyric_file_label: tk.Label   # declared; created in _build_utau_section
        self._external_midi_path: str | None = None
        # Player UI widgets — created in _build_output_panel; None until then
        self._metadata_panel: Optional['TrackMetadataPanel'] = None
        self._waveform_widget: Optional['WaveformWidget']    = None
        self._external_midi_notes: list | None = None
        self._external_midi_bpm: int = 120
        self._cipher = SemanticCipher() if PROMPT_DECODER_AVAILABLE else None
        # Groove & Mixer panel — built inside _build_advisor_tab; None until then.
        # Declared here so _on_genre_change is safe to call at any point during init.
        self._mixer_panel = None
        # Timbre editor panel — built inside _build_advisor_tab; None until then.
        self._timbre_editor = None
        # Piano roll widget — built inside _build_output_panel; None until then.
        self._piano_roll = None

        self._build_gui()
        self._init_engine()
        self._poll_queue()

    # ─────────────────────────────────────────────────────────────
    #  GUI CONSTRUCTION
    # ─────────────────────────────────────────────────────────────

    def _build_gui(self):
        main = tk.Frame(self.root, bg=S.BG)
        main.pack(fill='both', expand=True, padx=6, pady=6)

        tf = tk.Frame(main, bg=S.BG2, height=50)
        tf.pack(fill='x', pady=(0, 6)); tf.pack_propagate(False)
        tk.Label(tf, text="SEED COMPOSER", font=S.FN_BIG,
                 fg=S.TXT_BRT, bg=S.BG2).pack(side='left', padx=15, pady=8)
        tk.Label(tf, text="Professional Music Generation Studio",
                 font=S.FN_S, fg=S.TXT_DIM, bg=S.BG2).pack(side='left', padx=10)
        self.status_label = tk.Label(tf, text="● INIT", font=S.FN_S, fg=S.YELLOW, bg=S.BG2)
        self.status_label.pack(side='right', padx=15)

        # Expand button — packed right-to-left so it sits just left of the status label.
        self._btn_expand = tk.Button(
            tf,
            text="▷  EXPAND",
            font=S.FN_S,
            fg=S.TXT_DIM,
            bg=S.BG2,
            bd=0,
            padx=8,
            pady=0,
            cursor="hand2",
            activeforeground=S.CYAN,
            activebackground=S.BG2,
            relief="flat",
            command=self._toggle_expand,
        )
        self._btn_expand.pack(side='right', padx=(0, 6))

        content = tk.Frame(main, bg=S.BG)
        content.pack(fill='both', expand=True)

        left = tk.Frame(content, bg=S.BG2, width=540)
        left.pack(side='left', fill='y', padx=(0, 4)); left.pack_propagate(False)
        self._left_panel = left   # reference kept for expand/collapse toggling

        lc = tk.Canvas(left, bg=S.BG2, highlightthickness=0)
        sb = ttk.Scrollbar(left, orient='vertical', command=lc.yview)
        sf = tk.Frame(lc, bg=S.BG2)
        sf.bind('<Configure>', lambda e: lc.configure(scrollregion=lc.bbox('all')))
        lc.create_window((0, 0), window=sf, anchor='nw', width=520)
        lc.configure(yscrollcommand=sb.set)
        lc.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        # Use Enter/Leave so left and right scroll areas don't fight for the
        # global <MouseWheel> binding (last bind_all wins in Tkinter).
        import sys as _sys
        def _lp_enter(_e=None):
            if _sys.platform == 'win32':
                lc.bind_all('<MouseWheel>',
                            lambda e: lc.yview_scroll(int(-1 * e.delta / 120), 'units'))
            elif _sys.platform == 'darwin':
                lc.bind_all('<MouseWheel>',
                            lambda e: lc.yview_scroll(int(-1 * e.delta), 'units'))
            else:
                lc.bind_all('<Button-4>', lambda e: lc.yview_scroll(-3, 'units'))
                lc.bind_all('<Button-5>', lambda e: lc.yview_scroll(3, 'units'))

        def _lp_leave(_e=None):
            lc.unbind_all('<MouseWheel>')
            lc.unbind_all('<Button-4>')
            lc.unbind_all('<Button-5>')

        lc.bind('<Enter>', _lp_enter)
        lc.bind('<Leave>', _lp_leave)
        sf.bind('<Enter>', _lp_enter)   # also activate when over content widgets

        self._build_seed_section(sf)
        self._build_genre_section(sf)
        self._build_params_section(sf)
        self._build_tracks_section(sf)
        self._build_generate_section(sf)
        self._build_utau_section(sf)

        right = tk.Frame(content, bg=S.BG2)
        right.pack(side='right', fill='both', expand=True)
        self._build_output_panel(right)

    # ─── Seed Section ───

    def _build_seed_section(self, parent):
        frame = self._section(parent, "SEED DATABASE", S.CYAN)

        row = tk.Frame(frame, bg=S.BG2); row.pack(fill='x', pady=2)
        tk.Label(row, text="Dataset:", font=S.FN_S, fg=S.TXT, bg=S.BG2).pack(side='left')
        self.dataset_entry = tk.Entry(row, font=S.FN_S, bg=S.BG_INPUT, fg=S.TXT,
                                       insertbackground=S.CYAN, width=30)
        self.dataset_entry.insert(0, str(Path.home() / "Music" / "Research_training_data"))
        self.dataset_entry.pack(side='left', padx=4, fill='x', expand=True)
        self._cbtn(row, "Browse", self._browse_dataset, S.CYAN).pack(side='left', padx=2)
        self._tip(self.dataset_entry, 'dataset_entry')

        row2 = tk.Frame(frame, bg=S.BG2); row2.pack(fill='x', pady=2)
        tk.Label(row2, text="Seeds Dir:", font=S.FN_S, fg=S.TXT, bg=S.BG2).pack(side='left')
        self.seeds_entry = tk.Entry(row2, font=S.FN_S, bg=S.BG_INPUT, fg=S.TXT,
                                     insertbackground=S.CYAN, width=30)
        default_seeds = os.path.join(APP_DIR, "seeds")
        self.seeds_entry.insert(0, default_seeds)
        self.seeds_entry.pack(side='left', padx=4, fill='x', expand=True)
        self._cbtn(row2, "Browse", self._browse_seeds, S.CYAN).pack(side='left', padx=2)
        self._tip(self.seeds_entry, 'seeds_entry')

        row3 = tk.Frame(frame, bg=S.BG2); row3.pack(fill='x', pady=4)
        btn_build = self._cbtn(row3, "BUILD SEEDS FROM CSVs", self._build_seeds, S.PINK, wide=True)
        btn_build.pack(side='left', padx=2, fill='x', expand=True)
        btn_load = self._cbtn(row3, "LOAD SEEDS", self._load_seeds, S.GREEN, wide=True)
        btn_load.pack(side='left', padx=2, fill='x', expand=True)
        self._tip(btn_build, 'btn_build_seeds')
        self._tip(btn_load, 'btn_load_seeds')

        self.seed_status = tk.Label(frame, text="No seeds loaded — build or load seeds, or generate without",
                                     font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2, anchor='w', wraplength=480)
        self.seed_status.pack(fill='x', pady=2)

    # ─── Genre ───

    def _build_genre_section(self, parent):
        frame = self._section(parent, "GENRE", S.PINK)

        self.genre_var = tk.StringVar(value='pop')
        genres = ['pop', 'hiphop', 'trap', 'cinematic', 'classical', 'techno', 'jpop', 'phonk',
                  'edm', 'house']
        self.genre_list = genres
        grid = tk.Frame(frame, bg=S.BG2); grid.pack(fill='x', pady=4)
        for i, g in enumerate(genres):
            c = S.GENRE_CLR.get(g, S.CYAN)
            tk.Radiobutton(grid, text=g.upper(), variable=self.genre_var, value=g,
                           font=S.FN_S, fg=c, bg=S.BG2, selectcolor=S.BG3,
                           activebackground=S.BG3, activeforeground=c,
                           indicatoron=0, bd=0, padx=10, pady=5, width=9,
                           relief='flat', highlightthickness=1, highlightbackground=S.BG3,
                           command=self._on_genre_change
                           ).grid(row=i//4, column=i%4, padx=2, pady=2, sticky='ew')
            grid.columnconfigure(i%4, weight=1)

        # SF2 indicator — shows which soundfont will be used for the selected genre
        self.sf2_indicator = tk.Label(
            frame, text='', font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2, anchor='w',
        )
        self.sf2_indicator.pack(fill='x', padx=2, pady=(2, 0))
        self._refresh_sf2_indicator('pop')

        if FUSION_AVAILABLE and FUSION_PRESETS:
            fusion_frame = tk.Frame(frame, bg=S.BG2)
            fusion_frame.pack(fill='x', pady=(10, 4))

            self.fusion_enabled = tk.BooleanVar(value=False)
            fusion_cb = tk.Checkbutton(
                fusion_frame, text="FUSION MODE", variable=self.fusion_enabled,
                font=S.FN_S, fg=S.ORANGE, bg=S.BG2, selectcolor=S.BG3,
                activebackground=S.BG2, activeforeground=S.ORANGE,
                command=self._on_fusion_toggle
            )
            fusion_cb.pack(side='left', padx=5)

            self.fusion_preset_var = tk.StringVar(value='cyber_ninja')
            fusion_presets = list(FUSION_PRESETS.keys())

            self.fusion_combo = ttk.Combobox(
                fusion_frame,
                textvariable=self.fusion_preset_var,
                values=fusion_presets,
                state='disabled',
                width=18,
                font=S.FN_S
            )
            self.fusion_combo.pack(side='left', padx=10)

            self.fusion_desc_var = tk.StringVar(value="")
            self.fusion_desc_label = tk.Label(
                fusion_frame, textvariable=self.fusion_desc_var,
                font=S.FN_XS, fg=S.DIM, bg=S.BG2, anchor='w'
            )
            self.fusion_desc_label.pack(side='left', padx=10, fill='x', expand=True)

            self.fusion_combo.bind('<<ComboboxSelected>>', self._on_fusion_preset_change)

            custom_frame = tk.Frame(frame, bg=S.BG2)
            custom_frame.pack(fill='x', pady=(6, 4))

            self.fusion_custom = tk.BooleanVar(value=False)
            custom_cb = tk.Checkbutton(
                custom_frame, text="CUSTOM MIX", variable=self.fusion_custom,
                font=S.FN_S, fg=S.CYAN, bg=S.BG2, selectcolor=S.BG3,
                activebackground=S.BG2, activeforeground=S.CYAN,
                command=self._on_custom_fusion_toggle
            )
            custom_cb.pack(side='left', padx=5)

            self.fusion_genre1 = tk.StringVar(value='trap')
            self.fusion_genre1_combo = ttk.Combobox(
                custom_frame, textvariable=self.fusion_genre1,
                values=genres, state='disabled', width=10, font=S.FN_S
            )
            self.fusion_genre1_combo.pack(side='left', padx=4)
            self.fusion_genre1_combo.bind('<<ComboboxSelected>>', self._update_fusion_colors)

            self.genre1_pct_label = tk.Label(
                custom_frame, text="60%", font=("Consolas", 11, "bold"),
                fg=S.GENRE_CLR.get('trap', S.CYAN), bg=S.BG2, width=4
            )
            self.genre1_pct_label.pack(side='left', padx=2)

            slider_frame = tk.Frame(custom_frame, bg=S.BG2)
            slider_frame.pack(side='left', padx=4)

            self.fusion_ratio = tk.IntVar(value=60)
            self.fusion_ratio_scale = tk.Scale(
                slider_frame, from_=10, to=90, orient='horizontal',
                variable=self.fusion_ratio, length=120, sliderlength=20,
                font=S.FN_XS, fg=S.CYAN, bg=S.BG2, troughcolor=S.BG3,
                highlightthickness=0, bd=0, state='disabled',
                showvalue=False, command=self._on_ratio_change
            )
            self.fusion_ratio_scale.pack()

            self.genre2_pct_label = tk.Label(
                custom_frame, text="40%", font=("Consolas", 11, "bold"),
                fg=S.GENRE_CLR.get('jpop', S.PINK), bg=S.BG2, width=4
            )
            self.genre2_pct_label.pack(side='left', padx=2)

            self.fusion_genre2 = tk.StringVar(value='jpop')
            self.fusion_genre2_combo = ttk.Combobox(
                custom_frame, textvariable=self.fusion_genre2,
                values=genres, state='disabled', width=10, font=S.FN_S
            )
            self.fusion_genre2_combo.pack(side='left', padx=4)
            self.fusion_genre2_combo.bind('<<ComboboxSelected>>', self._update_fusion_colors)

            blend_frame = tk.Frame(frame, bg=S.BG2)
            blend_frame.pack(fill='x', pady=(2, 4), padx=40)

            self.blend_canvas = tk.Canvas(blend_frame, height=8, bg=S.BG3,
                                          highlightthickness=1, highlightbackground=S.BG3)
            self.blend_canvas.pack(fill='x')
            self.blend_canvas.bind('<Configure>', self._draw_blend_bar)

        else:
            self.fusion_enabled = tk.BooleanVar(value=False)
            self.fusion_preset_var = tk.StringVar(value='cyber_ninja')
            self.fusion_custom = tk.BooleanVar(value=False)

    def _on_fusion_toggle(self):
        enabled = self.fusion_enabled.get()
        if enabled:
            self.fusion_combo.config(state='readonly')
            self._on_fusion_preset_change(None)
            self._set_status("FUSION MODE ACTIVE", S.ORANGE)
            if not self.fusion_custom.get():
                pass
        else:
            self.fusion_combo.config(state='disabled')
            self.fusion_desc_var.set("")
            self.fusion_custom.set(False)
            self._on_custom_fusion_toggle()
            self._set_status("READY", S.GREEN)

    def _on_custom_fusion_toggle(self):
        custom = self.fusion_custom.get()

        if custom:
            self.fusion_enabled.set(True)
            self.fusion_combo.config(state='disabled')
            self.fusion_genre1_combo.config(state='readonly')
            self.fusion_genre2_combo.config(state='readonly')
            self.fusion_ratio_scale.config(state='normal')
            self._update_fusion_colors()
            self._set_status("CUSTOM FUSION MODE", S.CYAN)
        else:
            self.fusion_genre1_combo.config(state='disabled')
            self.fusion_genre2_combo.config(state='disabled')
            self.fusion_ratio_scale.config(state='disabled')
            if self.fusion_enabled.get():
                self.fusion_combo.config(state='readonly')
                self._on_fusion_preset_change(None)

    def _on_ratio_change(self, value):
        ratio = int(float(value))
        g1 = self.fusion_genre1.get()
        g2 = self.fusion_genre2.get()
        c1 = S.GENRE_CLR.get(g1, S.CYAN)
        c2 = S.GENRE_CLR.get(g2, S.PINK)

        self.genre1_pct_label.config(text=f"{ratio}%", fg=c1)
        self.genre2_pct_label.config(text=f"{100-ratio}%", fg=c2)

        self._draw_blend_bar()

    def _update_fusion_colors(self, event=None):
        g1 = self.fusion_genre1.get()
        g2 = self.fusion_genre2.get()
        c1 = S.GENRE_CLR.get(g1, S.CYAN)
        c2 = S.GENRE_CLR.get(g2, S.PINK)
        ratio = self.fusion_ratio.get()

        self.genre1_pct_label.config(text=f"{ratio}%", fg=c1)
        self.genre2_pct_label.config(text=f"{100-ratio}%", fg=c2)

        self._draw_blend_bar()

    def _draw_blend_bar(self, event=None):
        if not hasattr(self, 'blend_canvas'):
            return

        canvas = self.blend_canvas
        canvas.delete("all")

        width = canvas.winfo_width()
        height = canvas.winfo_height()

        if width < 10:
            return

        g1 = self.fusion_genre1.get() if hasattr(self, 'fusion_genre1') else 'trap'
        g2 = self.fusion_genre2.get() if hasattr(self, 'fusion_genre2') else 'jpop'
        c1 = S.GENRE_CLR.get(g1, S.CYAN)
        c2 = S.GENRE_CLR.get(g2, S.PINK)
        ratio = self.fusion_ratio.get() if hasattr(self, 'fusion_ratio') else 60

        x1_end = int(width * ratio / 100)
        canvas.create_rectangle(0, 0, x1_end, height, fill=c1, outline="")
        canvas.create_rectangle(x1_end, 0, width, height, fill=c2, outline="")

    def _on_fusion_preset_change(self, event):
        preset_name = self.fusion_preset_var.get()
        if preset_name in FUSION_PRESETS:
            preset = FUSION_PRESETS[preset_name]
            genres = " + ".join(preset['genres'])
            weights = "/".join([f"{int(w*100)}%" for w in preset['weights']])
            desc = f"{genres} ({weights})"
            self.fusion_desc_var.set(desc)

    # ─── Parameters ───

    def _build_params_section(self, parent):
        # Parameters section starts collapsed — click ▶ to expand
        cs = CollapsibleSection(parent, "PARAMETERS", S.PURPLE, collapsed=True)
        frame = cs.content_frame

        r = tk.Frame(frame, bg=S.BG2); r.pack(fill='x', pady=3)
        tk.Label(r, text="BPM:", font=S.FN_S, fg=S.TXT, bg=S.BG2, width=12, anchor='w').pack(side='left')
        self.bpm_auto = tk.BooleanVar(value=True)
        bpm_cb = tk.Checkbutton(r, text="Auto/Random", variable=self.bpm_auto, font=S.FN_X,
                                 fg=S.GREEN, bg=S.BG2, selectcolor=S.BG3,
                                 activebackground=S.BG2, command=self._toggle_bpm)
        bpm_cb.pack(side='left')
        self.bpm_scale = tk.Scale(r, from_=40, to=200, orient='horizontal',
                                   font=S.FN_X, fg=S.PURPLE, bg=S.BG2,
                                   troughcolor=S.BG_INPUT, highlightthickness=0,
                                   length=180, state='disabled')
        self.bpm_scale.set(120)
        self.bpm_scale.pack(side='left', padx=4, fill='x', expand=True)
        self._tip(bpm_cb, 'bpm_auto')
        self._tip(self.bpm_scale, 'bpm_scale')

        r2 = tk.Frame(frame, bg=S.BG2); r2.pack(fill='x', pady=3)
        tk.Label(r2, text="Key:", font=S.FN_S, fg=S.TXT, bg=S.BG2, width=12, anchor='w').pack(side='left')
        self.key_auto = tk.BooleanVar(value=True)
        key_cb = tk.Checkbutton(r2, text="Auto/Random", variable=self.key_auto, font=S.FN_X,
                                 fg=S.GREEN, bg=S.BG2, selectcolor=S.BG3,
                                 activebackground=S.BG2, command=self._toggle_key)
        key_cb.pack(side='left')
        self.key_root = ttk.Combobox(r2, values=NOTES, width=4, state='disabled')
        self.key_root.set('C'); self.key_root.pack(side='left', padx=2)
        self.key_mode = ttk.Combobox(r2, values=GENRE_SCALES.get('pop', ['major', 'minor']), width=14, state='disabled')
        self.key_mode.set(GENRE_SCALES.get('pop', ['major'])[0]); self.key_mode.pack(side='left', padx=2)
        self._tip(key_cb, 'key_auto')
        self._tip(self.key_root, 'key_root')
        self._tip(self.key_mode, 'key_mode')

        r3 = tk.Frame(frame, bg=S.BG2); r3.pack(fill='x', pady=3)
        tk.Label(r3, text="Start Chord:", font=S.FN_S, fg=S.TXT, bg=S.BG2, width=12, anchor='w').pack(side='left')
        self.chord_auto = tk.BooleanVar(value=True)
        chord_cb = tk.Checkbutton(r3, text="Auto/Random", variable=self.chord_auto, font=S.FN_X,
                                   fg=S.GREEN, bg=S.BG2, selectcolor=S.BG3,
                                   activebackground=S.BG2, command=self._toggle_chord)
        chord_cb.pack(side='left')
        self.chord_root = ttk.Combobox(r3, values=NOTES, width=4, state='disabled')
        self.chord_root.set('C'); self.chord_root.pack(side='left', padx=2)
        _pop_q = GENRE_CHORD_QUALITIES.get('pop', QUALITIES)
        self.chord_quality = ttk.Combobox(r3, values=_pop_q, width=6, state='disabled')
        self.chord_quality.set(_pop_q[0]); self.chord_quality.pack(side='left', padx=2)
        self._tip(chord_cb, 'chord_auto')
        self._tip(self.chord_root, 'chord_root')
        self._tip(self.chord_quality, 'chord_quality')

        r4 = tk.Frame(frame, bg=S.BG2); r4.pack(fill='x', pady=3)
        tk.Label(r4, text="Complexity:", font=S.FN_S, fg=S.TXT, bg=S.BG2, width=12, anchor='w').pack(side='left')
        self.complexity_scale = tk.Scale(r4, from_=0, to=10, orient='horizontal',
                                          font=S.FN_X, fg=S.ORANGE, bg=S.BG2,
                                          troughcolor=S.BG_INPUT, highlightthickness=0, length=220)
        self.complexity_scale.set(5)
        self.complexity_scale.pack(side='left', padx=4, fill='x', expand=True)
        self._tip(self.complexity_scale, 'complexity_scale')

        r5 = tk.Frame(frame, bg=S.BG2); r5.pack(fill='x', pady=3)
        tk.Label(r5, text="Humanize:", font=S.FN_S, fg=S.TXT, bg=S.BG2, width=12, anchor='w').pack(side='left')
        self.humanize_scale = tk.Scale(r5, from_=0, to=100, orient='horizontal',
                                        font=S.FN_X, fg=S.GREEN, bg=S.BG2,
                                        troughcolor=S.BG_INPUT, highlightthickness=0, length=220)
        self.humanize_scale.set(60)
        self.humanize_scale.pack(side='left', padx=4, fill='x', expand=True)
        self._tip(self.humanize_scale, 'humanize_scale')

        r_mut = tk.Frame(frame, bg=S.BG2); r_mut.pack(fill='x', pady=3)
        tk.Label(r_mut, text="Mutation:", font=S.FN_S, fg=S.TXT, bg=S.BG2, width=12, anchor='w').pack(side='left')

        mut_frame = tk.Frame(r_mut, bg=S.BG2)
        mut_frame.pack(side='left', fill='x', expand=True)

        tk.Label(mut_frame, text="SAFE", font=S.FN_XS, fg=S.GREEN, bg=S.BG2).pack(side='left')

        self.mutation_scale = tk.Scale(mut_frame, from_=0, to=100, orient='horizontal',
                                        font=S.FN_X, fg=S.YELLOW, bg=S.BG2,
                                        troughcolor=S.BG_INPUT, highlightthickness=0, length=180,
                                        command=self._on_mutation_change)
        self.mutation_scale.set(0)
        self.mutation_scale.pack(side='left', padx=4)
        self._tip(self.mutation_scale, 'mutation_scale')

        tk.Label(mut_frame, text="CHAOS", font=S.FN_XS, fg=S.RED, bg=S.BG2).pack(side='left')

        self.mutation_label = tk.Label(r_mut, text="0%", font=("Consolas", 10, "bold"),
                                        fg=S.GREEN, bg=S.BG2, width=5)
        self.mutation_label.pack(side='left', padx=4)

        r6 = tk.Frame(frame, bg=S.BG2); r6.pack(fill='x', pady=3)
        tk.Label(r6, text="Seed:", font=S.FN_S, fg=S.TXT, bg=S.BG2, width=12, anchor='w').pack(side='left')
        self.seed_entry = tk.Entry(r6, font=S.FN_S, bg=S.BG_INPUT, fg=S.TXT,
                                    insertbackground=S.CYAN, width=12)
        self.seed_entry.pack(side='left', padx=2)
        tk.Label(r6, text="(empty=random)", font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2).pack(side='left', padx=4)
        btn_rand_seed = self._cbtn(r6, "Rand", self._random_seed, S.YELLOW)
        btn_rand_seed.pack(side='left')
        self._tip(self.seed_entry, 'seed_entry')
        self._tip(btn_rand_seed, 'btn_rand_seed')

    # ─── Tracks ───

    def _build_tracks_section(self, parent):
        # Tracks section starts collapsed — click ▶ to expand
        cs = CollapsibleSection(parent, "TRACKS & INSTRUMENTS", S.GREEN, collapsed=True)
        frame = cs.content_frame

        top_row = tk.Frame(frame, bg=S.BG2); top_row.pack(fill='x', pady=(0, 4))
        btn_rand_all = self._cbtn(top_row, "RANDOMIZE ALL INSTRUMENTS",
                                  self._randomize_all_instruments, S.YELLOW, wide=True)
        btn_rand_all.pack(fill='x')
        self._tip(btn_rand_all, 'btn_randomize_all')

        tracks = ['drums', 'bass', 'chords', 'lead', 'pad', 'arp']
        for track in tracks:
            color = S.TRACK_CLR.get(track, S.CYAN)

            # Container holds two sub-rows: controls on row1, description on row2.
            container = tk.Frame(frame, bg=S.BG2)
            container.pack(fill='x', pady=2)
            row = tk.Frame(container, bg=S.BG2)
            row.pack(fill='x')

            enabled = tk.BooleanVar(value=True)
            en_cb = tk.Checkbutton(row, text=track.upper(), variable=enabled, font=S.FN_S,
                                    fg=color, bg=S.BG2, selectcolor=S.BG3,
                                    activebackground=S.BG2, width=7, anchor='w')
            en_cb.pack(side='left')
            self._tip(en_cb, 'track_enabled')

            # Volume fader — same log taper as the Groove & Mixer panel.
            # Drums default to 0 dB (unity); melodic tracks to −3 dB.
            tk.Label(row, text="Vol:", font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2).pack(side='left')
            _default_db   = 0.0 if track == 'drums' else (-6.0 if track in ('arp', 'lead', 'chords') else -3.0)
            _vol_pos_var  = tk.IntVar(value=int(_db_to_pos(_default_db) * _GAIN_STEPS))
            vol = tk.Scale(row, variable=_vol_pos_var, from_=0, to=_GAIN_STEPS,
                           resolution=1, orient='horizontal', font=S.FN_X,
                           fg=color, bg=S.BG2, troughcolor=S.BG_INPUT,
                           highlightthickness=0, length=80, showvalue=0)
            vol.pack(side='left', padx=2)
            self._tip(vol, 'track_volume')
            # Live dB readout label + double-click reset to 0 dB
            _vol_lbl = tk.Label(row, text='', font=S.FN_X, fg=S.TXT, bg=S.BG2, width=7)
            _vol_lbl.pack(side='left')
            def _make_vol_updater(pv=_vol_pos_var, lbl=_vol_lbl):
                def _upd(*_):
                    db = _pos_to_db(pv.get() / _GAIN_STEPS)
                    lbl.configure(text='-∞ dB' if db <= _GAIN_INF_FLOOR else f'{db:+.1f} dB')
                return _upd
            _vu = _make_vol_updater()
            _vol_pos_var.trace_add('write', _vu)
            vol.bind('<Double-Button-1>',
                     lambda e, pv=_vol_pos_var: pv.set(int(_db_to_pos(0.0) * _GAIN_STEPS)))
            _vu()  # set initial label text

            if track == 'drums':
                kit_values = [f"{k}: {v}" for k, v in sorted(DRUM_KITS.items())]
                inst = ttk.Combobox(row, values=kit_values, width=20, font=S.FN_X)
                inst.set("0: Standard Kit")
            else:
                inst_values = [f"{k}: {v}" for k, v in sorted(GM_INSTRUMENTS.items())]
                inst = ttk.Combobox(row, values=inst_values, width=20, font=S.FN_X)
                default_prog = GENRE_INSTRUMENTS.get('pop', {}).get(track, 0)
                inst.set(f"{default_prog}: {GM_INSTRUMENTS.get(default_prog, 'Piano')}")
            inst.pack(side='left', padx=4)
            self._tip(inst, 'track_instrument')

            rand_btn = self._cbtn(row, "Rand", lambda t=track: self._randomize_track_instrument(t),
                                   S.YELLOW)
            rand_btn.pack(side='left', padx=2)
            self._tip(rand_btn, 'btn_rand_instrument')

            # Row 2: sound-character description below the controls.
            # Indent spacer aligns text under the instrument area (past the track label).
            row2 = tk.Frame(container, bg=S.BG2)
            row2.pack(fill='x')
            tk.Label(row2, text="", bg=S.BG2, width=10, font=S.FN_X).pack(side='left')
            desc_fn = get_drum_description if track == 'drums' else None
            desc = InstrumentDescriptionLabel(row2, styles=S, max_chars=120,
                                              description_fn=desc_fn)
            desc.pack(side='left', fill='x', expand=True, padx=(2, 4))
            desc.attach(inst)

            self.track_vars[track] = {'enabled': enabled, 'volume': vol, 'instrument': inst}

        # ── Tracks 7-10: Stabs, Texture, FX, Percussion ─────────────────────
        # Each row is constructed by TrackInstrumentRow, which encapsulates the
        # checkbox, volume slider, instrument combobox, and Rand button in one
        # reusable class.  'percussion' is mode='percussion' — it shares the drum
        # channel (ch 9) so it has no program selector.
        _extended_tracks = [
            #  track key     mode          default   default    default
            #                              enabled   gain_db    program
            ('stabs',      'pitched',    True,    -3.0,      55),   # Orchestra Hit default
            ('texture',    'pitched',    True,    -4.0,      88),   # New Age Pad default
            ('fx',         'fx_sounds',  True,    -6.0,      96),   # Rain FX default
            ('percussion', 'percussion', True,    -4.0,      None), # no program — drum ch
        ]
        for _track, _mode, _enabled, _gain_db, _prog in _extended_tracks:
            _color = S.TRACK_CLR.get(_track, S.CYAN)
            _row = TrackInstrumentRow(
                frame,
                track=_track,
                mode=_mode,
                color=_color,
                default_enabled=_enabled,
                default_gain_db=_gain_db,
                default_program=_prog,
                log_fn=self._log,
                tip_fn=self._tip,
            )
            # Register in track_vars so the engine config builder and randomize
            # functions can access them the same way as the inline rows above.
            self.track_vars[_track] = {
                'enabled':    _row.enabled,
                'volume':     _row.volume,
                'instrument': _row.instrument,  # None for percussion
            }

    # ─── Generate ───

    def _build_generate_section(self, parent):
        frame = self._section(parent, "GENERATE", S.YELLOW)

        # ── AI Prompt input ──────────────────────────────────────────
        prompt_label_row = tk.Frame(frame, bg=S.BG2)
        prompt_label_row.pack(fill='x', pady=(0, 2))
        tk.Label(prompt_label_row, text="AI Prompt  (Describe your track):",
                 font=S.FN_S, fg=S.YELLOW, bg=S.BG2, anchor='w').pack(side='left')
        if not PROMPT_DECODER_AVAILABLE:
            tk.Label(prompt_label_row, text="[unavailable]",
                     font=S.FN_X, fg=S.RED, bg=S.BG2).pack(side='left', padx=4)

        prompt_row = tk.Frame(frame, bg=S.BG2)
        prompt_row.pack(fill='x', pady=(0, 2))

        self._prompt_entry = tk.Entry(
            prompt_row, font=S.FN_S, bg=S.BG_INPUT, fg=S.TXT,
            insertbackground=S.YELLOW,
            highlightthickness=1, highlightbackground=S.YELLOW,
        )
        self._prompt_entry.pack(side='left', fill='x', expand=True, padx=(0, 4))
        self._prompt_entry.bind('<Return>', lambda _: self._decode_and_show())
        self._tip(self._prompt_entry, 'prompt_entry')

        self._cbtn(prompt_row, "✕", self._clear_prompt, S.TXT_DIM).pack(side='left')

        # Placeholder hint
        tk.Label(frame,
                 text='e.g.  "fast dark trap beat with a huge drop"   or   "slow chill lofi at 85 bpm"',
                 font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2, anchor='w'
                 ).pack(fill='x', pady=(0, 2))

        # Decoded parameters feedback line
        self._decoded_label = tk.Label(
            frame, text="", font=S.FN_X,
            fg=S.CYAN, bg=S.BG2, anchor='w', wraplength=480
        )
        self._decoded_label.pack(fill='x', pady=(0, 4))

        tk.Frame(frame, bg=S.BG3, height=1).pack(fill='x', pady=(0, 4))

        # ── Output mode checkboxes ────────────────────────────────────
        # Both checked by default: every generation produces a paired set
        # (full beat + vocal-ready with open chord voicings and cleared vocal register).
        mode_row = tk.Frame(frame, bg=S.BG2); mode_row.pack(fill='x', pady=(0, 6))
        self.gen_full_beat    = tk.BooleanVar(value=True)
        self.gen_vocal_ready  = tk.BooleanVar(value=True)
        tk.Checkbutton(
            mode_row, text="Full Beat", variable=self.gen_full_beat,
            font=S.FN_S, fg=S.CYAN, bg=S.BG2, selectcolor=S.BG3,
            activebackground=S.BG2, activeforeground=S.CYAN,
        ).pack(side='left', padx=(0, 16))
        tk.Checkbutton(
            mode_row, text="Vocal-Ready Beat", variable=self.gen_vocal_ready,
            font=S.FN_S, fg=S.PINK, bg=S.BG2, selectcolor=S.BG3,
            activebackground=S.BG2, activeforeground=S.PINK,
        ).pack(side='left')
        tk.Label(mode_row, text="(open voicings · vocal freq cleared)",
                 font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2).pack(side='left', padx=(8, 0))

        # ── Buttons ──────────────────────────────────────────────────
        r = tk.Frame(frame, bg=S.BG2); r.pack(fill='x', pady=4)
        self.gen_btn = self._cbtn(r, "GENERATE NEW SONG", self._generate,
                                   S.CYAN, wide=True, big=True)
        self.gen_btn.pack(fill='x', padx=4, ipady=8)
        self._tip(self.gen_btn, 'btn_generate')

        # Batch button — same width/style as GENERATE for visual alignment
        r2 = tk.Frame(frame, bg=S.BG2); r2.pack(fill='x', pady=(0, 4))
        self.btn_batch = self._cbtn(r2, "Generate Batch (5x)", self._on_generate_batch,
                                     S.YELLOW, wide=True)
        self.btn_batch.pack(fill='x', padx=4, ipady=4)
        self._tip(self.btn_batch, 'btn_batch')

    # ─── Output Panel ───

    def _build_output_panel(self, parent):
        # ── Waveform widget — ABOVE the notebook so it's always visible ──────
        # Placed first so Tkinter's pack manager shrinks the notebook (expand=True)
        # before ever hiding the waveform or the player buttons below.
        if PLAYER_WIDGETS_AVAILABLE:
            self._waveform_widget = WaveformWidget(
                parent,
                styles  = S,
                on_seek = self._on_waveform_seek,
                height  = 60,
            )
            self._waveform_widget.pack(fill='x', padx=4, pady=(4, 0))

        self._out_nb = ttk.Notebook(parent)
        self._out_nb.pack(fill='both', expand=True, padx=4, pady=(2, 4))

        # ── Tab 1: OUTPUT ──
        out_tab = tk.Frame(self._out_nb, bg=S.BG2)
        self._out_nb.add(out_tab, text=' OUTPUT ')

        # ── Track metadata panel (title / artist / genre / duration / bitrate …) ──
        if PLAYER_WIDGETS_AVAILABLE:
            self._metadata_panel = TrackMetadataPanel(out_tab, styles=S)
            self._metadata_panel.pack(fill='x', padx=4, pady=(4, 0))
            tk.Frame(out_tab, bg=S.BG3, height=1).pack(fill='x', padx=4, pady=(2, 0))

        self.info_text = tk.Text(out_tab, font=S.FN_S, bg=S.BG, fg=S.TXT,
                                  insertbackground=S.CYAN, height=18, wrap='word',
                                  state='disabled', bd=0, highlightthickness=1,
                                  highlightbackground=S.BG3)
        self.info_text.pack(fill='both', expand=True, pady=4, padx=4)
        for tag, color in [('header', S.CYAN), ('value', S.GREEN), ('section', S.PINK),
                           ('chord', S.PURPLE), ('dim', S.TXT_DIM), ('warn', S.YELLOW)]:
            self.info_text.tag_configure(tag, foreground=color,
                                          font=S.FN_H if tag == 'header' else S.FN_S)

        self.progress_var = tk.DoubleVar()
        ttk.Progressbar(out_tab, variable=self.progress_var, maximum=100).pack(fill='x', pady=2, padx=4)
        self.progress_label = tk.Label(out_tab, text="", font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2)
        self.progress_label.pack(fill='x', padx=4)

        # ── Tab 2: ADVISOR ──
        # Outer frame holds the ScrollableFrame so the entire advisor panel
        # (palette selector, instrument builder, action buttons, advisor text)
        # can be scrolled as one unit — content below the visible area is no
        # longer hidden.  The advisor text widget retains its own internal
        # scrollbar for navigating long text independently.
        adv_tab = tk.Frame(self._out_nb, bg=S.BG2)
        self._out_nb.add(adv_tab, text=' ADVISOR ')
        adv_sf = ScrollableFrame(adv_tab, bg=S.BG2,
                                 scrollbar_bg=S.BG3, scrollbar_width=12)
        adv_sf.pack(fill='both', expand=True)
        self._build_advisor_tab(adv_sf.inner)

        # ── Tab 3: PIANO ROLL ──
        pr_tab = tk.Frame(self._out_nb, bg=S.BG2)
        self._out_nb.add(pr_tab, text=' PIANO ROLL ')
        try:
            from src.gui.piano_roll import PianoRollWidget
            self._piano_roll = PianoRollWidget(pr_tab)
            self._piano_roll.frame.pack(fill='both', expand=True)
        except Exception as _exc:
            print(f'[PianoRoll] failed to load: {_exc}')
            self._piano_roll = None
            tk.Label(pr_tab, text='Piano roll unavailable', fg=S.TXT_DIM, bg=S.BG2).pack(expand=True)

        bf = tk.Frame(parent, bg=S.BG2); bf.pack(fill='x', padx=6, pady=4)
        btn_play = self._cbtn(bf, "PLAY  Full Beat", self._play_preview, S.GREEN, wide=True)
        btn_play.pack(side='left', padx=2, fill='x', expand=True)
        btn_stop = self._cbtn(bf, "STOP", self._stop_playback, S.RED, wide=True)
        btn_stop.pack(side='left', padx=2, fill='x', expand=True)
        self._tip(btn_play, 'btn_play')
        self._tip(btn_stop, 'btn_stop')

        # Vocal-ready row — visible only after a vocal-ready version has been generated
        self._vr_frame = tk.Frame(parent, bg=S.BG2)
        self._vr_frame.pack(fill='x', padx=6, pady=(0, 2))
        self._btn_play_vr = self._cbtn(
            self._vr_frame, "PLAY  Vocal-Ready Beat",
            self._play_vocal_ready, S.PINK, wide=True,
        )
        self._btn_play_vr.pack(side='left', padx=2, fill='x', expand=True)
        self._cbtn(
            self._vr_frame, "EXPORT MIDI",
            self._export_vocal_midi, S.PINK,
        ).pack(side='left', padx=2)
        self._cbtn(
            self._vr_frame, "EXPORT WAV",
            self._export_vocal_wav, S.PINK,
        ).pack(side='left', padx=2)
        self._vr_frame.pack_forget()   # hidden until a vocal-ready MIDI is ready

        ef = tk.Frame(parent, bg=S.BG2); ef.pack(fill='x', padx=6, pady=2)
        btn_midi = self._cbtn(ef, "MIDI", self._export_midi, S.PURPLE, wide=True)
        btn_midi.pack(side='left', padx=2, fill='x', expand=True)
        # EXPORT AUDIO replaces the old single-format WAV button — opens the
        # multi-format dialog so users can choose WAV / MP3 / FLAC / OGG.
        btn_export_audio = self._cbtn(ef, "EXPORT AUDIO…", self._open_export_dialog, S.CYAN, wide=True)
        btn_export_audio.pack(side='left', padx=2, fill='x', expand=True)
        btn_json = self._cbtn(ef, "JSON", self._export_json, S.BLUE, wide=True)
        btn_json.pack(side='left', padx=2, fill='x', expand=True)
        self._tip(btn_midi, 'btn_midi')
        self._tip(btn_json, 'btn_json')

        lf = self._section(parent, "CONSOLE", S.TXT_DIM)
        self.log_text = tk.Text(lf, font=S.FN_X, bg=S.BG, fg=S.TXT_DIM,
                                 height=8, wrap='word', state='disabled', bd=0)
        self.log_text.pack(fill='both', expand=True, pady=2)

    # ─────────────────────────────────────────────────────────────
    #  GUI HELPERS
    # ─────────────────────────────────────────────────────────────

    def _section(self, parent, title, color):
        outer = tk.Frame(parent, bg=S.BG2); outer.pack(fill='x', padx=6, pady=4)
        tk.Label(outer, text=title, font=S.FN_H, fg=color, bg=S.BG2, anchor='w').pack(fill='x', pady=2)
        tk.Frame(outer, bg=color, height=1).pack(fill='x', pady=(0, 4))
        content = tk.Frame(outer, bg=S.BG2); content.pack(fill='x')
        return content

    def _cbtn(self, parent, text, command, color, wide=False, big=False):
        font = S.FN_H if big else S.FN_S
        btn = tk.Button(parent, text=text, command=command, font=font, fg=color,
                        bg=S.BG_BTN, activeforeground=S.TXT_BRT, activebackground=S.BG_BTN_ACT,
                        bd=0, padx=10 if wide else 6, pady=4 if big else 2, cursor='hand2',
                        highlightthickness=1, highlightbackground=color)
        btn.bind('<Enter>', lambda e: btn.configure(bg=S.BG_BTN_HOV))
        btn.bind('<Leave>', lambda e: btn.configure(bg=S.BG_BTN))
        return btn

    def _tip(self, widget: tk.Widget, key: str):
        """Attach a hover tooltip to a widget using a key from TOOLTIPS."""
        text = TOOLTIPS.get(key, "")
        if text:
            ToolTip(widget, text)

    def _log(self, msg):
        self.log_text.configure(state='normal')
        self.log_text.insert('end', f"{msg}\n")
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def _set_status(self, text, color=S.YELLOW):
        self.status_label.configure(text=f"● {text}", fg=color)

    def _info_clear(self):
        self.info_text.configure(state='normal')
        self.info_text.delete('1.0', 'end')
        self.info_text.configure(state='disabled')

    def _info_add(self, text, tag=None):
        self.info_text.configure(state='normal')
        self.info_text.insert('end', text, tag) if tag else self.info_text.insert('end', text)
        self.info_text.see('end')
        self.info_text.configure(state='disabled')

    # ─────────────────────────────────────────────────────────────
    #  PRODUCTION ADVISOR TAB
    # ─────────────────────────────────────────────────────────────

    def _build_advisor_tab(self, parent):
        # ── Query Without Generation panel ─────────────────────────────────
        # Lets the user type in genre / BPM / key of an external MIDI and get
        # the full advisor output without needing to generate a composition.
        if ADVISOR_QUERY_AVAILABLE:
            self._advisor_query = AdvisorQueryPanel(
                parent,
                styles            = S,
                update_advisor_fn = self._update_advisor,
                load_palettes_fn  = self._load_palettes_for,
                log_fn            = self._log,
            )
            self._advisor_query.pack(fill='x', padx=4, pady=(4, 2))
        else:
            self._advisor_query = None

        # ── Palette selector row ──
        pal_row = tk.Frame(parent, bg=S.BG2)
        pal_row.pack(fill='x', padx=4, pady=(4, 2))
        tk.Label(pal_row, text="PALETTE", font=S.FN_S, fg=S.TXT_DIM, bg=S.BG2,
                 width=8, anchor='w').pack(side='left')
        self._palette_var = tk.StringVar()
        self._palette_cb  = ttk.Combobox(pal_row, textvariable=self._palette_var,
                                          state='readonly', width=22, font=S.FN_S)
        self._palette_cb.pack(side='left', padx=4)
        self._tip(self._palette_cb, 'advisor_palette')
        self._branch_lbl = tk.Label(pal_row, text="", font=S.FN_X, fg=S.CYAN, bg=S.BG2)
        self._branch_lbl.pack(side='left', padx=4)
        self._palette_data = {}
        self._load_palettes_for('pop')
        self._palette_cb.bind('<<ComboboxSelected>>', lambda e: self._apply_palette_selection())

        # ── FX Chain Variant selector (BRIGHT / NEUTRAL / DARK) ──
        if FX_VARIANT_AVAILABLE:
            self._fx_variant_panel = FxVariantPanel(
                parent,
                styles                    = S,
                on_variant_change_fn      = self._on_variant_change,
                get_genre_fn              = lambda: self.genre_var.get(),
                get_track_instruments_fn  = self._get_track_instruments_for_advisor,
                get_variant_id_fn         = lambda: self._current_variant_id,
            )
            self._fx_variant_panel.pack(fill='x', padx=4, pady=(0, 2))
        else:
            self._fx_variant_panel = None

        # ── Instrument Builder (combinatoric selector) ──
        if INSTRUMENT_BUILDER_AVAILABLE:
            self._instrument_builder = InstrumentBuilder(
                parent,
                apply_callback=self._apply_builder,
                gm_instruments=GM_INSTRUMENTS,
                styles=S,
            )
            self._instrument_builder.pack(fill='x', padx=4, pady=(0, 2))
            self._instrument_builder.set_play_fn(self.player.play_wav)
        else:
            self._instrument_builder = None

        # ── Groove & Mixer panel ─────────────────────────────────────────────
        # Lives here in the ADVISOR tab so the user can generate once, then
        # iterate on groove settings and click [APPLY GROOVE & RE-RENDER] to
        # hear the result immediately without regenerating the composition.
        if GROOVE_AVAILABLE:
            try:
                self._mixer_panel = MixerPanel(
                    parent,
                    on_apply_fn=self._apply_groove_and_rerender,
                    get_composition_fn=lambda: self.current_composition,
                )
            except Exception as _exc:
                print(f'[GroovePanel] Construction failed: {_exc}')
                self._mixer_panel = None
        else:
            self._mixer_panel = None

        # ── Timbre editor panel ──────────────────────────────────────────────
        # Per-instrument preset + slider panel for kick, snare, hi-hat, melodic.
        # Parameters are collected via get_instrument_params() and injected into
        # the built-in synthesiser before every WAV render.
        if TIMBRE_EDITOR_AVAILABLE:
            try:
                self._timbre_editor = TimbreEditorPanel(parent, styles=S)
                self._timbre_editor.pack(fill='x', padx=4, pady=(0, 2))
            except Exception as _exc:
                print(f'[TimbreEditorPanel] Construction failed: {_exc}')
                self._timbre_editor = None
        else:
            self._timbre_editor = None

        # ── SoundFont picker ─────────────────────────────────────────────────
        # Always shown so users can configure a SoundFont path even when
        # FluidSynth is not yet installed.  SoundFontPickerWidget handles the
        # case where fluid_renderer is None by disabling renderer calls.
        if SF_PICKER_AVAILABLE:
            self._sf_picker = SoundFontPickerWidget(
                parent,
                styles         = S,
                fluid_renderer = _FLUID_RENDERER,   # may be None — widget handles it
                log_fn         = self._log,
            )
            self._sf_picker.pack(fill='x', padx=4, pady=(0, 4))
        else:
            self._sf_picker = None

        # ── Advisor action strip (preview + save + PDF export) ──
        if ADVISOR_ACTIONS_AVAILABLE:
            self._advisor_actions = AdvisorActionsBar(
                parent,
                styles               = S,
                get_engine_fn        = lambda: self.engine,
                fluid_renderer       = _FLUID_RENDERER,
                player               = self.player,
                build_config_fn      = self._build_config,
                want_vocal_fn        = lambda: self.gen_vocal_ready.get(),
                log_fn               = self._log,
                status_fn            = self._set_status,
                app_dir              = APP_DIR,
                save_pdf_fn          = self._export_advisor_pdf,
                export_audio_fn      = self._open_export_dialog_for_wav,
                get_muted_tracks_fn  = (
                    self._instrument_builder.get_muted_tracks
                    if self._instrument_builder is not None else None
                ),
                apply_groove_fn      = self._advisor_apply_groove,
                get_sample_assignments_fn = (
                    self._instrument_builder.get_sample_assignments
                    if self._instrument_builder is not None else None
                ),
                on_wav_ready_fn      = self._on_advisor_wav_ready,
                get_instrument_params_fn = self._get_instrument_params,
            )
            self._advisor_actions.pack(fill='x', padx=4)
        else:
            self._advisor_actions = None

        # ── Advisor text widget ──────────────────────────────────────────────
        # height=42 gives a tall but fixed block.  The outer ScrollableFrame
        # handles scrolling the whole advisor panel; this widget's own
        # scrollbar navigates within the (potentially very long) text output.
        adv_text_row = tk.Frame(parent, bg=S.BG2)
        adv_text_row.pack(fill='x', pady=(4, 4), padx=4)

        self.adv_text = tk.Text(
            adv_text_row, font=S.FN_X, bg=S.BG, fg=S.TXT,
            insertbackground=S.CYAN, height=42, wrap='none',
            state='disabled', bd=0, highlightthickness=1,
            highlightbackground=S.BG3,
        )
        sb = tk.Scrollbar(adv_text_row, command=self.adv_text.yview,
                          troughcolor=S.BG_INPUT)
        self.adv_text.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.adv_text.pack(side='left', fill='x', expand=True)
        for tag, color, font in [
            ('header',  S.CYAN,    S.FN_H),
            ('section', S.PINK,    S.FN_S),
            ('value',   S.GREEN,   S.FN_X),
            ('lbl',     S.TXT_DIM, S.FN_X),
            ('title',   S.ORANGE,  S.FN_S),
            ('warn',    S.YELLOW,  S.FN_X),
            ('dim',     S.TXT_DIM, S.FN_X),
            ('ok',      S.GREEN,   S.FN_X),
        ]:
            self.adv_text.tag_configure(tag, foreground=color, font=font)
        self._adv_add("  Select a palette above or generate a composition.\n", 'dim')

    def _load_palettes_for(self, genre):
        import json as _j, pathlib
        path = (pathlib.Path(__file__).parent.parent.parent
                / 'data' / 'production_guide' / 'json' / 'instrument_palettes.json')
        try:
            palettes = _j.loads(path.read_text(encoding='utf-8')).get(genre, [])
        except Exception:
            palettes = []
        self._palette_data = {p['name']: p for p in palettes}
        names = list(self._palette_data.keys())
        self._palette_cb['values'] = names
        if names:
            self._palette_cb.set(names[0])
            self._update_branch_label(self._palette_data[names[0]])
        else:
            self._palette_cb.set('')
            self._branch_lbl.config(text='')

    def _update_branch_label(self, palette):
        branch = palette.get('branch', '?')
        code   = palette.get('kick_code', '')
        self._branch_lbl.config(text=f"Branch {branch}  {code}")

    def _apply_palette_selection(self):
        name = self._palette_var.get()
        palette = self._palette_data.get(name)
        if not palette:
            return
        self._update_branch_label(palette)
        # Palette instrument keys (lead, pad, bass, chords, arp, stabs, texture, fx)
        # match track_vars keys exactly — no remapping needed.
        for pal_key, inst in palette['instruments'].items():
            tv = self.track_vars.get(pal_key, {})
            cb = tv.get('instrument')
            if cb:
                cb.set(f"{inst['gm']}: {inst['name']}")
        # Push palette into InstrumentBuilder so its dropdowns reflect the palette choice
        if self._instrument_builder is not None:
            self._instrument_builder.sync_from_palette(palette)
        self._log(f"Palette → {name} (Branch {palette['branch']})")
        if getattr(self, 'current_composition', None):
            self._update_advisor(self.current_composition)
        else:
            self._show_palette_in_advisor(palette)

    # ── FX variant helpers ─────────────────────────────────────────────────────

    def _on_variant_change(self, variant_id: str) -> None:
        """User clicked a variant button — store and re-render the advisor."""
        self._current_variant_id = variant_id
        self._log(f"FX variant → {variant_id.upper()}")
        if _FLUID_RENDERER is not None:
            _FLUID_RENDERER.set_variant(variant_id)
        if getattr(self, 'current_composition', None):
            self._update_advisor(self.current_composition)
        if self._fx_variant_panel is not None:
            self._fx_variant_panel.refresh()

    def _export_advisor_pdf(self) -> None:
        """
        Assemble the current advisor state and write a production guide PDF.

        Mirrors the data pipeline in _update_advisor() — loads the same JSON
        files and computes the same merged delta — then delegates all
        formatting to AdvisorPDFExporter so this method stays thin.

        Opens a save-as dialog first; does nothing if the user cancels.
        """
        import json as _json
        import pathlib
        from tkinter import filedialog

        comp = getattr(self, 'current_composition', None)
        if not comp:
            self._log("No composition to export — generate a song first.")
            return

        c     = comp['config']
        genre = c.get('genre', 'unknown')
        bpm   = c.get('bpm', 0)
        key   = c.get('key', '')

        # Load production guide JSON (same paths as _update_advisor)
        base = pathlib.Path(__file__).parent.parent.parent / 'data' / 'production_guide' / 'json'
        try:
            shared = _json.loads((base / 'shared.json').read_text(encoding='utf-8'))
        except Exception:
            shared = {}
        gdata = {}
        gpath = base / f'{genre}.json'
        if gpath.exists():
            try:
                gdata = _json.loads(gpath.read_text(encoding='utf-8'))
            except Exception:
                pass

        # Resolve active palette
        pal_name = getattr(self, '_palette_var', None)
        pal_name = pal_name.get() if pal_name else ''
        pal      = getattr(self, '_palette_data', {}).get(pal_name)
        pal_delta = (pal or {}).get('chain_delta', {})

        # Build three-layer merged delta
        track_instruments = self._get_track_instruments_for_advisor()
        if FX_VARIANT_AVAILABLE and FxChainSelector is not None:
            merged_delta   = FxChainSelector.build_merged_delta(
                genre, self._current_variant_id, pal_delta, track_instruments,
            )
            active_variant = FxChainSelector.get_variant(genre, self._current_variant_id)
        else:
            merged_delta   = pal_delta
            active_variant = {}

        # Default filename: pop_111bpm_D_major_advisor.pdf
        safe_key     = key.replace(' ', '_').replace('/', '-')
        default_name = f"{genre}_{int(bpm)}bpm_{safe_key}_advisor.pdf"

        dest = filedialog.asksaveasfilename(
            title             = "Export Production Guide",
            defaultextension  = ".pdf",
            filetypes         = [
                ("PDF document", "*.pdf"),
                ("Plain text",   "*.txt"),
                ("All files",    "*.*"),
            ],
            initialfile = default_name,
        )
        if not dest:
            return

        from src.export.advisor_pdf import AdvisorPDFExporter
        exporter = AdvisorPDFExporter(
            config            = c,
            palette           = pal,
            genre_data        = gdata,
            shared_data       = shared,
            variant_id        = self._current_variant_id,
            variant_record    = active_variant,
            merged_delta      = merged_delta,
            track_instruments = track_instruments,
        )

        ok = exporter.export(dest)
        if ok:
            self._log(f"Production guide -> {dest}")
            self._set_status("PDF SAVED", S.GREEN)
        else:
            self._log("PDF export failed — check console for details.")
            self._set_status("PDF EXPORT FAILED", S.RED)

    def _get_track_instruments_for_advisor(self) -> dict:
        """
        Return {track_name: gm_program_int} for all track_vars entries.

        Used by FxVariantPanel and FxChainSelector to detect which
        instrument class is active on each track for instrument-aware
        FX adjustments.
        """
        result = {}
        for track_name, vd in self.track_vars.items():
            inst_cb = vd.get('instrument')
            if inst_cb is None:
                continue
            raw = inst_cb.get()
            try:
                result[track_name] = int(raw.split(':')[0].strip())
            except (ValueError, IndexError):
                pass
        return result

    def _apply_builder(self, selection: dict) -> None:
        """Apply InstrumentBuilder APPLY selection to the left-panel track comboboxes.

        `selection` has the form returned by InstrumentBuilder.current_selection():
            {'branch': 'A', 'bass': {gm, name, code}, 'chords': {...}, ...}
        Builder uses track-space keys (melody, pads); track_vars uses the same
        'melody' key but 'texture' for the pad track, so only 'pads' is remapped.
        """
        # Builder uses 'melody' (→ track_vars 'lead') and 'pads' (→ track_vars 'pad').
        # All other builder keys (bass, chords, arp, stabs) match track_vars directly.
        _MAP = {'melody': 'lead', 'pads': 'pad'}
        for builder_key, inst in selection.items():
            if builder_key == 'branch' or not isinstance(inst, dict):
                continue
            left_key = _MAP.get(builder_key, builder_key)
            tv = self.track_vars.get(left_key)
            if tv and tv.get('instrument'):
                gm   = inst['gm']
                name = GM_INSTRUMENTS.get(gm, inst['name'])
                tv['instrument'].set(f"{gm}: {name}")
        self._log(f"Builder → applied Branch {selection.get('branch', '?')} selection")
        # With a composition loaded: re-render the full production advisor so the
        # new instrument choices appear in context.  Without a composition: show
        # the standalone builder validation panel instead.
        if getattr(self, 'current_composition', None):
            self._update_advisor(self.current_composition)
        elif self._instrument_builder is not None and INSTRUMENT_BUILDER_AVAILABLE:
            val = self._instrument_builder.current_validation()
            self._show_builder_validation(val, selection)

    def _show_builder_validation(self, val, selection: dict) -> None:
        """Render the full ValidationResult from InstrumentBuilder into the advisor text area."""
        self._adv_clear()
        A = self._adv_add
        branch = selection.get('branch', '?')
        score  = val.score
        label  = val.label
        # Score colour tag
        score_tag = 'ok' if score >= 90 else ('warn' if score >= 70 else 'lbl')
        A("═" * 52 + "\n", 'dim')
        A(f"  INSTRUMENT BUILDER — Branch {branch}\n", 'header')
        A("═" * 52 + "\n\n", 'dim')
        A(f"  {'SCORE':<14}", 'lbl');  A(f"{score}/100  {label}\n", score_tag)
        A("\n  SELECTION\n", 'section')
        A(f"  {'TRACK':<10} {'GM':>4}  {'NAME':<22} CODE\n", 'lbl')
        A("  " + "─" * 46 + "\n", 'dim')
        for key, inst in selection.items():
            if key == 'branch' or not isinstance(inst, dict):
                continue
            A(f"  {key.upper():<10}", 'lbl')
            A(f" {inst['gm']:>3}  ", 'dim')
            A(f"{inst['name']:<22}", 'value')
            A(f" {inst.get('code', '')}\n", 'ok')
        if val.violations:
            A("\n  VIOLATIONS\n", 'section')
            for v in val.violations:
                A(f"  ✗ {v}\n", 'warn')
        if val.warnings:
            A("\n  WARNINGS\n", 'section')
            for w in val.warnings:
                A(f"  ⚠ {w}\n", 'lbl')
        if not val.violations and not val.warnings:
            A("\n  No psychoacoustic conflicts detected.\n", 'ok')
        self.adv_text.see('1.0')

    def _show_palette_in_advisor(self, palette):
        self._adv_clear()
        A = self._adv_add
        A("═" * 52 + "\n", 'dim')
        A(f"  PALETTE — {palette['name'].upper()}  (Branch {palette['branch']})\n", 'header')
        A("═" * 52 + "\n\n", 'dim')
        A(f"  KICK TYPE   ", 'lbl'); A(f"{palette['kick_code']}\n", 'value')
        A(f"  NOTE        ", 'lbl'); A(f"{palette['kick_desc']}\n\n", 'dim')
        A("  INSTRUMENTS\n", 'section')
        A(f"  {'TRACK':<10} {'GM':>4}  {'NAME':<22} CODE\n", 'lbl')
        A("  " + "─" * 46 + "\n", 'dim')
        for track, inst in palette['instruments'].items():
            A(f"  {track.upper():<10}", 'lbl')
            A(f" {inst['gm']:>3}  ", 'dim')
            A(f"{inst['name']:<22}", 'value')
            A(f" {inst['code']}\n", 'ok')
        A("\n  MATRIX 1 CONSTRAINTS\n", 'section')
        A("  One D0 R0 at a time  ·  SC ratio ≥ 1.5  ·\n", 'dim')
        A("  Attack separation ≥ 1 step (same register)\n\n", 'dim')

    def _adv_clear(self):
        self.adv_text.configure(state='normal')
        self.adv_text.delete('1.0', 'end')
        self.adv_text.configure(state='disabled')

    def _adv_add(self, text, tag=None):
        self.adv_text.configure(state='normal')
        if tag:
            self.adv_text.insert('end', text, tag)
        else:
            self.adv_text.insert('end', text)
        self.adv_text.configure(state='disabled')

    def _update_advisor(self, comp):
        import json as _json, pathlib
        self._adv_clear()
        A = self._adv_add

        c     = comp['config']
        genre = c['genre']
        bpm   = c['bpm']
        key   = c['key']

        # Keep FluidSynth's genre-FX profile in sync with the advisor genre.
        if _FLUID_RENDERER is not None:
            _FLUID_RENDERER.set_genre(genre)

        base        = pathlib.Path(__file__).parent.parent.parent / 'data' / 'production_guide' / 'json'
        shared_path = base / 'shared.json'
        genre_path  = base / f'{genre}.json'

        try:
            shared = _json.loads(shared_path.read_text(encoding='utf-8'))
        except Exception:
            shared = {}

        gdata, has_genre = {}, False
        if genre_path.exists():
            try:
                gdata, has_genre = _json.loads(genre_path.read_text(encoding='utf-8')), True
            except Exception:
                pass

        A("═" * 52 + "\n", 'dim')
        A(f"  PRODUCTION ADVISOR — {genre.upper()}\n", 'header')
        A("═" * 52 + "\n\n", 'dim')
        A(f"  {'BPM':<14}", 'lbl');  A(f"{bpm}\n", 'value')
        A(f"  {'KEY':<14}", 'lbl');  A(f"{key}\n", 'value')

        # ── Active palette summary + instrument table ──
        pal_name = getattr(self, '_palette_var', None)
        pal_name = pal_name.get() if pal_name else ''
        pal = getattr(self, '_palette_data', {}).get(pal_name)
        if pal:
            from src.composition.gm_descriptions import get_description as _gm_desc
            A(f"  {'PALETTE':<14}", 'lbl')
            A(f"{pal['name']}  Branch {pal['branch']}  {pal['kick_code']}\n", 'value')
            A(f"  {'KICK':<14}", 'lbl'); A(f"{pal['kick_desc']}\n", 'dim')
            A("\n  INSTRUMENTS\n", 'section')
            A(f"  {'TRACK':<10} {'GM':>4}  {'NAME':<22} CODE\n", 'lbl')
            A("  " + "─" * 46 + "\n", 'dim')
            for track, inst in pal['instruments'].items():
                A(f"  {track.upper():<10}", 'lbl')
                A(f" {inst['gm']:>3}  ", 'dim')
                A(f"{inst['name']:<22}", 'value')
                A(f" {inst['code']}\n", 'ok')
                # Pedagogical description — helps students find an equivalent
                # instrument in their DAW when the GM name is not obvious.
                desc = _gm_desc(inst['gm'])
                A(f"  {'':10}  {'':3}   {desc}\n", 'dim')
        A("\n")

        if has_genre:
            for bkt in gdata.get('bpm_buckets', []):
                lo, hi = bkt.get('bpm_range', [0, 9999])
                if lo <= bpm <= hi:
                    A(f"  {'BUCKET':<14}", 'lbl')
                    A(f"{bkt['id']} (anchor {bkt['anchor_bpm']} BPM)\n", 'value')
                    A(f"  {'SCALES':<14}", 'lbl')
                    A(f"{', '.join(bkt.get('key_families', []))}\n", 'value')
                    break
            A(f"  {'PLR TARGET':<14}", 'lbl'); A(f"{gdata.get('plr_target_db', '?')} dB\n", 'value')
            A(f"  {'LRA':<14}", 'lbl');        A(f"{gdata.get('lra_target_lu', '?')} LU\n\n", 'value')
        else:
            A(f"\n  No production data for genre '{genre}'.\n\n", 'warn')
            return

        # ── Gain Staging ──
        A("  GAIN STAGING TARGETS\n", 'section')
        A(f"  {'TRACK':<12} {'RMS':>7} {'PEAK':>7} {'CF':>5}\n", 'lbl')
        A("  " + "─" * 34 + "\n", 'dim')
        delta_map = {
            'pop':      'pop_delta',
            'jpop':     'pop_delta',
            'edm':      'pop_delta',
            'house':    'pop_delta',
            'hiphop':   'hiphop_delta',
            'trap':     'hiphop_delta',
            'phonk':    'hiphop_delta',
            'techno':   'hiphop_delta',
            'dnb':      'hiphop_delta',
            'cinematic':'cine_delta',
            'classical':'cine_delta',
        }
        dk  = delta_map.get(genre, 'pop_delta')
        cgt = shared.get('clip_gain_targets', {})
        for track, vals in cgt.items():
            if track == 'note':
                continue
            rms  = vals.get('rms_dbfs', -18)
            peak = vals.get('peak_ceiling_dbfs', -6)
            cf   = vals.get('cf_db', 12)
            rms_eff = rms + vals.get(dk, 0)
            A(f"  {track.upper():<12}", 'lbl')
            A(f" {rms_eff:>6.1f}", 'value')
            A(f" {peak:>6.1f}", 'section')
            A(f" {cf:>3}dB\n", 'dim')

        # ── Effect Chains (palette + variant + instrument-class merged) ──
        tracks_data  = gdata.get('tracks', {})
        pal_delta    = (pal or {}).get('chain_delta', {})
        pal_insts    = (pal or {}).get('instruments', {})
        # palette key → genre JSON track name  (only the differing ones)
        _PAL_TO_TRACK = {'lead': 'melody', 'pad': 'pads', 'texture': 'pads'}

        # Build the three-layer merged delta (palette → variant → instrument).
        if FX_VARIANT_AVAILABLE and FxChainSelector is not None:
            track_instruments = self._get_track_instruments_for_advisor()
            merged_delta = FxChainSelector.build_merged_delta(
                genre,
                self._current_variant_id,
                pal_delta,
                track_instruments,
            )
            # Fetch the active variant's display label and description.
            active_variant = FxChainSelector.get_variant(genre, self._current_variant_id)
        else:
            merged_delta   = pal_delta
            active_variant = {}

        if tracks_data:
            has_any_delta = bool(merged_delta)
            hdr = "  EFFECT CHAINS"
            if has_any_delta:
                hdr += "  [palette-adjusted]"

            # Show which timbral flavor is active.
            v_label = active_variant.get('label', self._current_variant_id.upper())
            v_desc  = active_variant.get('description', '')
            A(f"\n{hdr}\n", 'section')
            A(f"  VARIANT  {v_label}", 'title')
            if v_desc:
                A(f"  — {v_desc}", 'dim')
            A("\n", 'dim')

            for tname, tdata in tracks_data.items():
                chain = tdata.get('effect_chain', [])
                if not chain:
                    continue
                delta_slots = {d['slot']: d for d in merged_delta.get(tname, [])}
                has_delta   = bool(delta_slots)
                A(f"\n  {tname.upper()}", 'title')
                if has_delta:
                    # find which palette instrument maps to this track
                    inst_key = next(
                        (k for k, v in _PAL_TO_TRACK.items() if v == tname),
                        tname  # bass/chords/arp/stabs/fx map directly
                    )
                    inst_name = pal_insts.get(inst_key, {}).get('name', '')
                    if inst_name:
                        A(f" [{inst_name}]", 'ok')
                role = tdata.get('role', '')
                A(f"  — {role}\n" if role else "\n", 'dim')
                for slot in chain:
                    sn = slot['slot']
                    d  = delta_slots.get(sn)
                    if d is None:
                        A(f"    [{sn}] ", 'lbl')
                        A(f"{slot['effect']:<28}", 'value')
                        A(f"{slot.get('params', '')}\n", 'dim')
                    elif d['action'] == 'disable':
                        A(f"    [{sn}] ", 'lbl')
                        A(f"{'[BYPASS]':<28}", 'dim')
                        A(f"{d.get('note', '')}\n", 'warn')
                    elif d['action'] == 'adjust':
                        A(f"    [{sn}] ", 'lbl')
                        A(f"{slot['effect']:<28}", 'value')
                        A(f"{d.get('note', '')}\n", 'ok')
                    elif d['action'] == 'swap':
                        A(f"    [{sn}] ", 'lbl')
                        A(f"{d.get('effect', slot['effect']):<28}", 'ok')
                        A(f"{d.get('params', '')}  —  {d.get('note', '')}\n", 'ok')
                # any 'add' entries from the merged delta (slot > max chain length)
                for ad in merged_delta.get(tname, []):
                    if ad['action'] == 'add':
                        A(f"    [{ad['slot']}+] ", 'lbl')
                        A(f"{ad.get('effect', ''):<28}", 'ok')
                        A(f"{ad.get('params', '')}  —  {ad.get('note', '')}\n", 'ok')

        # ── Frequency Allocation + Stereo Field ──
        freq = gdata.get('frequency_allocation', {})
        sf   = gdata.get('stereo_field', {})
        if freq:
            A("\n  FREQUENCY ALLOCATION\n", 'section')
            A(f"  {'TRACK':<12} {'HPF':>5} {'LPF':>6}  {'ZONE':<26} WIDTH\n", 'lbl')
            A("  " + "─" * 62 + "\n", 'dim')
            for tname, fdata in freq.items():
                hpf = str(fdata.get('hpf_hz', '—'))
                lpf = str(fdata.get('lpf_hz', '—')) if fdata.get('lpf_hz') else '—'
                zone = fdata.get('dominant_zone', '')[:24]
                sdata = sf.get(tname, {})
                width = sdata.get('width_pct', '—')
                cls   = sdata.get('class', '')
                width_str = f"{width}% {cls}" if cls and width != '—' else cls or str(width)
                A(f"  {tname.upper():<12}", 'lbl')
                A(f" {hpf:>5}", 'value')
                A(f" {lpf:>6}", 'dim')
                A(f"  {zone:<26}", 'dim')
                A(f" {width_str}\n", 'ok')

        # ── Parallel Compression ──
        pc = gdata.get('parallel_compression', {})
        if pc:
            A("\n  PARALLEL COMPRESSION (NY)\n", 'section')
            A(f"  {'WET BLEND':<14}", 'lbl'); A(f"{pc.get('wet_blend_pct', '?')}%\n", 'value')
            A(f"  {'RATIO':<14}", 'lbl');     A(f"{pc.get('ratio', '?')}\n", 'value')
            A(f"  {'THRESHOLD':<14}", 'lbl'); A(f"{pc.get('threshold_dbfs', '?')} dBFS\n", 'value')
            A(f"  {'RELEASE':<14}", 'lbl');   A(f"{pc.get('release_formula', '?')} ms\n")

        # ── M/S Mastering ──
        ms = gdata.get('ms_mastering', {})
        if ms:
            A("\n  M/S MASTERING INSERT\n", 'section')
            status = ms.get('status', 'N/A')
            A(f"  {'STATUS':<14}", 'lbl')
            A(f"{status}\n", 'warn' if status == 'MANDATORY' else 'dim')
            if status in ('MANDATORY', 'OPTIONAL'):
                A(f"  {'SIDE HPF':<14}", 'lbl')
                A(f"{ms.get('side_hpf_hz', '?')} Hz {ms.get('side_hpf_slope', '')}\n", 'value')
                A(f"  {'SIDE SHELF':<14}", 'lbl')
                A(f"+{ms.get('side_shelf_db', '?')} dB @ {ms.get('side_shelf_hz', '?')} Hz\n", 'value')
                A(f"  {'WIDTH':<14}", 'lbl')
                A(f"{ms.get('resulting_width_pct', '?')}%\n")

        # ── Export Specs ──
        exp = gdata.get('export_specs', {})
        if exp:
            A("\n  EXPORT TARGETS\n", 'section')
            for dest, d in exp.items():
                A(f"  {dest.upper()}\n", 'title')
                A(f"    {'LUFS-I':<12}", 'lbl'); A(f"{d.get('lufs_i', '?')} LUFS\n", 'value')
                A(f"    {'dBTP':<12}", 'lbl');   A(f"{d.get('dbtp', '?')} dBTP\n", 'value')
                A(f"    {'RATE':<12}", 'lbl');   A(f"{d.get('sample_rate_hz', '?')} Hz\n", 'value')
                if 'plr_db' in d:
                    A(f"    {'PLR':<12}", 'lbl'); A(f"{d['plr_db']} dB\n", 'value')

        # ── Spectral Allocation Map (Feature 2) ──────────────────────────────
        if SPECTRAL_CHART_AVAILABLE:
            freq = gdata.get('frequency_allocation', {})
            sf   = gdata.get('stereo_field', {})
            if freq:
                for text, tag in build_spectral_chart(freq, sf):
                    A(text, tag)

        # ── Corpus-Match Score (Feature 6) ───────────────────────────────────
        if CORPUS_MATCH_AVAILABLE and _CORPUS_MATCHER is not None:
            # Extract chord qualities used in the composition if available.
            chord_qualities: list = []
            try:
                chord_qualities = list(comp.get('chord_qualities_used', []))
            except Exception:
                pass
            if not chord_qualities:
                # Fallback: read from config chord_quality field (single value).
                cq = c.get('chord_quality', '')
                if cq:
                    chord_qualities = [cq]

            cm = _CORPUS_MATCHER.match(
                genre=genre,
                bpm=bpm,
                key=key,
                chord_qualities=chord_qualities,
            )
            score      = cm['score']
            bpm_m      = cm['bpm_match']
            scale_m    = cm['scale_match']
            chord_m    = cm['chord_match']
            n_seeds    = cm['seed_count']
            bpm_lo, bpm_hi = cm['bpm_range']

            # Colour the overall score: green ≥80, yellow ≥60, red <60.
            score_tag = 'ok' if score >= 80 else 'warn'

            A("\n  CORPUS MATCH\n", 'section')
            A(f"  {'OVERALL':<14}", 'lbl')
            A(f"{score}%", score_tag)
            seeds_note = f"  ({n_seeds} seeds)" if n_seeds else "  (parametric model)"
            A(f"{seeds_note}\n", 'dim')
            A(f"  {'BPM FIT':<14}", 'lbl')
            A(f"{bpm_m}%", 'value')
            A(f"  typical {bpm_lo}–{bpm_hi} BPM\n", 'dim')
            A(f"  {'SCALE FIT':<14}", 'lbl')
            A(f"{scale_m}%\n", 'value')
            A(f"  {'CHORD FIT':<14}", 'lbl')
            A(f"{chord_m}%\n", 'value')

            # Motivating interpretation line for the student.
            if score >= 90:
                A("  This composition is a strong corpus representative.\n", 'ok')
            elif score >= 75:
                A("  Good genre alignment — minor parameter adjustments would raise fit.\n", 'dim')
            elif score >= 55:
                A("  Moderate fit — consider BPM or scale adjustments to better match the genre.\n", 'warn')
            else:
                A("  Low corpus match — consider switching genre or adjusting BPM/key.\n", 'warn')

        # ── BPM Time Values ──
        A("\n  BPM TIME VALUES\n", 'section')
        q = 60000 / bpm
        for label, val in [
            ('1/4 NOTE',   f"{q:.1f} ms"),
            ('1/8 DOTTED', f"{q*0.75:.1f} ms"),
            ('1/16',       f"{15000/bpm:.1f} ms"),
            ('PRE-DELAY',  f"{3750/bpm:.1f} ms"),
            ('SC RELEASE', f"{30000/bpm:.1f} ms"),
            ('CMP RELEASE',f"{120000/bpm:.1f} ms"),
        ]:
            A(f"  {label:<14}", 'lbl'); A(f"{val}\n", 'value')

        self.adv_text.see('1.0')

    # ─────────────────────────────────────────────────────────────
    #  TOGGLE CALLBACKS
    # ─────────────────────────────────────────────────────────────

    def _toggle_expand(self) -> None:
        """
        Hide or restore the left control panel to give the advisor more space.

        EXPAND  — pack_forget() removes the left frame; the right panel stretches
                  to fill the full content area instantly (no geometry recalc needed
                  because the right frame uses fill='both', expand=True).
        RESTORE — re-pack the left frame with its original options so the two-column
                  layout is restored.  pack_propagate(False) is a frame property and
                  remains set, so the 540 px width is preserved.
        """
        if self._is_expanded:
            # Restore the left control panel
            self._left_panel.pack(side='left', fill='y', padx=(0, 4))
            self._btn_expand.config(text="▷  EXPAND", fg=S.TXT_DIM)
            self._is_expanded = False
        else:
            # Hide the left panel — right fills the full window width
            self._left_panel.pack_forget()
            self._btn_expand.config(text="◀  RESTORE", fg=S.CYAN)
            self._is_expanded = True

    def _toggle_bpm(self):
        self.bpm_scale.configure(state='disabled' if self.bpm_auto.get() else 'normal')

    def _toggle_key(self):
        st = 'disabled' if self.key_auto.get() else 'readonly'
        self.key_root.configure(state=st); self.key_mode.configure(state=st)

    def _toggle_chord(self):
        st = 'disabled' if self.chord_auto.get() else 'readonly'
        self.chord_root.configure(state=st); self.chord_quality.configure(state=st)

    def _refresh_sf2_indicator(self, genre: str) -> None:
        if not hasattr(self, 'sf2_indicator'):
            return
        if FLUIDSYNTH_AVAILABLE and _FLUID_RENDERER is not None:
            sf_name = _FLUID_RENDERER._library.display_name(genre)
            self.sf2_indicator.config(text=f'SF2: {sf_name}', fg=S.CYAN)
        else:
            self.sf2_indicator.config(text='SF2: not available', fg=S.TXT_DIM)

    def _on_genre_change(self):
        genre = self.genre_var.get()
        defaults = GENRE_INSTRUMENTS.get(genre, GENRE_INSTRUMENTS.get('pop', {}))
        for track, prog in defaults.items():
            if track in self.track_vars and self.track_vars[track]['instrument']:
                name = GM_INSTRUMENTS.get(prog, "Piano")
                self.track_vars[track]['instrument'].set(f"{prog}: {name}")
        self._refresh_sf2_indicator(genre)
        valid_scales = GENRE_SCALES.get(genre, ['major', 'minor'])
        self.key_mode['values'] = valid_scales
        if self.key_mode.get() not in valid_scales:
            self.key_mode.set(valid_scales[0])
        valid_qualities = GENRE_CHORD_QUALITIES.get(genre, QUALITIES)
        self.chord_quality['values'] = valid_qualities
        if self.chord_quality.get() not in valid_qualities:
            self.chord_quality.set(valid_qualities[0])
        if hasattr(self, '_palette_cb'):
            self._load_palettes_for(genre)
        if _FLUID_RENDERER is not None:
            _FLUID_RENDERER.set_genre(genre)
        # Keep the groove mixer preset dropdown in sync with the genre selector
        if self._mixer_panel is not None:
            self._mixer_panel.set_genre(genre)
        self._log(f"Genre -> {genre.upper()}")

    def _random_seed(self):
        self.seed_entry.delete(0, 'end')
        self.seed_entry.insert(0, str(random.randint(1, 999999)))

    def _on_mutation_change(self, value):
        val = int(float(value))
        self.mutation_label.config(text=f"{val}%")

        if val <= 30:
            color = S.GREEN
        elif val <= 60:
            color = S.YELLOW
        elif val <= 80:
            color = S.ORANGE
        else:
            color = S.RED

        self.mutation_label.config(fg=color)
        self.mutation_scale.config(fg=color)

    def _randomize_track_instrument(self, track):
        tv = self.track_vars.get(track, {})
        inst_widget = tv.get('instrument')
        # percussion shares the drum channel and has no program selector
        if inst_widget is None:
            return
        if track == 'drums':
            kit = random.choice(list(DRUM_KITS.items()))
            inst_widget.set(f"{kit[0]}: {kit[1]}")
        else:
            pool = ROLE_INSTRUMENTS.get(track, list(GM_INSTRUMENTS.keys()))
            prog = random.choice(pool)
            name = GM_INSTRUMENTS.get(prog, "Unknown")
            inst_widget.set(f"{prog}: {name}")
        self._log(f"Randomized {track}: {inst_widget.get()}")

    def _randomize_all_instruments(self):
        for track in self.track_vars:
            self._randomize_track_instrument(track)
        self._log("All instruments randomized!")

    # ─────────────────────────────────────────────────────────────
    #  ENGINE
    # ─────────────────────────────────────────────────────────────

    def _init_engine(self):
        if not ENGINE_AVAILABLE:
            self._set_status(f"ENGINE ERROR: {IMPORT_ERROR}", S.RED)
            self._log(f"Import error: {IMPORT_ERROR}")
            return
        self.engine = CompositionEngine()
        self._set_status("READY - Load seeds or generate without", S.GREEN)
        self._log("Engine ready. Seeds not loaded - using music theory fallback.")
        self._log(f"To load seeds, point Seeds Dir to your JSON seeds folder and click LOAD.")

    # ─────────────────────────────────────────────────────────────
    #  SEED OPERATIONS
    # ─────────────────────────────────────────────────────────────

    def _browse_dataset(self):
        p = filedialog.askdirectory(title="Select Dataset Root (Research_training_data)")
        if p:
            self.dataset_entry.delete(0, 'end')
            self.dataset_entry.insert(0, p)

    def _browse_seeds(self):
        p = filedialog.askdirectory(title="Select Seeds Directory")
        if p:
            self.seeds_entry.delete(0, 'end')
            self.seeds_entry.insert(0, p)

    def _build_seeds(self):
        dataset_dir = self.dataset_entry.get().strip()
        seeds_dir = self.seeds_entry.get().strip() or "seeds"
        if not dataset_dir:
            messagebox.showwarning("No Dataset", "Select your CSV dataset directory first.")
            return
        if not os.path.exists(dataset_dir):
            messagebox.showwarning("Not Found", f"Directory not found:\n{dataset_dir}")
            return

        self._set_status("BUILDING SEEDS...", S.PINK)
        self._log(f"Building from: {dataset_dir}")
        self._log(f"Output to: {os.path.abspath(seeds_dir)}")

        def _worker():
            try:
                builder = SeedBuilder(dataset_dir, seeds_dir)
                count = builder.build_all_seeds(
                    progress_callback=lambda i, t, s: self.msg_queue.put(('progress', i, t, f"{s}"))
                )
                if count > 0:
                    builder.save_seeds()
                    builder.export_genre_matrices()
                    self.msg_queue.put(('seed_done', count, seeds_dir))
                else:
                    self.msg_queue.put(('seed_fail', 'No valid CSV triples found. Check folder structure.'))
            except Exception as e:
                self.msg_queue.put(('seed_fail', str(e)))

        threading.Thread(target=_worker, daemon=True).start()

    def _load_seeds(self):
        seeds_dir = self.seeds_entry.get().strip() or "seeds"
        if not os.path.exists(seeds_dir):
            messagebox.showwarning("Not Found", f"Seeds directory not found:\n{seeds_dir}\n\n"
                                   f"Build seeds first, or browse to an existing seeds folder.")
            return

        self._set_status("LOADING SEEDS...", S.CYAN)
        try:
            self.engine = CompositionEngine(seeds_dir)
            self.engine.load_seeds()
            n = len(self.engine.seeds)
            genres = list(self.engine.genre_seeds.keys())
            self.seeds_loaded = True
            abs_path = os.path.abspath(seeds_dir)
            self.seed_status.configure(
                text=f"✓ {n} seeds loaded from: {abs_path}\nGenres: {', '.join(genres)}",
                fg=S.GREEN
            )
            self._set_status(f"LOADED: {n} seeds", S.GREEN)
            self._log(f"✓ {n} seeds from {abs_path}")
            self._log(f"  Genres: {genres}")
        except Exception as e:
            self._set_status(f"LOAD ERROR: {e}", S.RED)
            self._log(f"Error: {e}")

    # ─────────────────────────────────────────────────────────────
    #  GENERATION
    # ─────────────────────────────────────────────────────────────

    def _build_config(self):
        config = CompositionConfig()
        config.genre = self.genre_var.get()

        config.bpm = None if self.bpm_auto.get() else float(self.bpm_scale.get())
        config.key = None if self.key_auto.get() else f"{self.key_root.get()} {self.key_mode.get()}"
        config.starting_chord = None if self.chord_auto.get() else \
            f"{self.chord_root.get()}{self.chord_quality.get()}"

        config.complexity = int(self.complexity_scale.get())
        config.humanize_amount = self.humanize_scale.get() / 100.0

        if hasattr(self, 'mutation_scale'):
            config.mutation = self.mutation_scale.get() / 100.0
        else:
            config.mutation = 0.0

        seed_text = self.seed_entry.get().strip()
        config.seed_value = int(seed_text) if seed_text.isdigit() else None

        for track_name, vd in self.track_vars.items():
            if track_name not in config.tracks:
                config.tracks[track_name] = {'enabled': True, 'volume': 0.8, 'instrument': None}
            config.tracks[track_name]['enabled'] = vd['enabled'].get()
            # Convert fader position (0–_GAIN_STEPS) to linear volume (0–1)
            # using the same log taper as the Groove & Mixer panel.
            _vol_db = _pos_to_db(vd['volume'].get() / float(_GAIN_STEPS))
            config.tracks[track_name]['volume'] = gain_db_to_volume(_vol_db)
            if vd['instrument'] is not None:
                try:
                    config.tracks[track_name]['instrument'] = int(vd['instrument'].get().split(':')[0])
                except (ValueError, IndexError):
                    pass

        if FUSION_AVAILABLE and self.fusion_enabled.get():
            if hasattr(self, 'fusion_custom') and self.fusion_custom.get():
                genre1 = self.fusion_genre1.get()
                genre2 = self.fusion_genre2.get()
                ratio = self.fusion_ratio.get() / 100.0
                config.fusion = FusionConfig.custom(genre1, genre2, ratio)
                print(f"CUSTOM FUSION: {genre1.upper()} {int(ratio*100)}% + {genre2.upper()} {int((1-ratio)*100)}%")
            else:
                preset_name = self.fusion_preset_var.get()
                try:
                    config.fusion = FusionConfig.from_preset(preset_name)
                    print(f"FUSION PRESET: {preset_name.upper()}")
                except Exception as e:
                    print(f"Fusion error: {e}")

        # ── Prompt decoder overrides (applied last so they always win) ──
        if self._cipher:
            prompt_text = self._prompt_entry.get().strip()
            if prompt_text:
                decoded = self._cipher.decode_prompt(prompt_text)
                self._apply_prompt_overrides(config, decoded)
                self._decoded_label.configure(
                    text=f">  {decoded.summary()}", fg=S.CYAN)
                if decoded.matched_keywords:
                    self._log(f"Prompt decoded: {decoded.summary()}")

        return config

    def _generate(self):
        if self.is_generating:
            return
        if not self.engine:
            messagebox.showerror("No Engine", "Composition engine not available.")
            return

        self.player.stop()
        time_module.sleep(0.1)

        self.is_generating = True
        self.generation_counter += 1
        self._set_status("COMPOSING...", S.PINK)
        self._info_clear()
        self._info_add("GENERATING NEW COMPOSITION...\n", 'header')
        self.progress_var.set(0)
        # Clear the player UI so it doesn't show stale data from the previous song
        if self._waveform_widget is not None:
            self._waveform_widget.reset()
        if self._metadata_panel is not None:
            self._metadata_panel.update(None)

        config = self._build_config()
        gen_id = self.generation_counter

        want_full   = self.gen_full_beat.get()
        want_vocal  = self.gen_vocal_ready.get()
        if not want_full and not want_vocal:
            # Guard: at least one must be selected
            want_full = True

        # Always pin a seed so the composition is reproducible and the advisor
        # preview can re-compose the same song with different instruments.
        # Previously only pinned when want_vocal=True; now universal so that
        # AdvisorActionsBar.set_seed() always has a value to cache.
        if config.seed_value is None:
            config.seed_value = random.randint(1, 999999)
        self._last_gen_seed = config.seed_value   # cached for advisor re-render

        # Capture groove settings here on the main thread — GUI widgets must
        # not be accessed from inside the worker thread.
        _auto_groove_settings = None
        if GROOVE_AVAILABLE and self._mixer_panel is not None:
            try:
                _auto_groove_settings = self._mixer_panel.get_settings(
                    genre=getattr(config, 'genre', '') or ''
                )
            except Exception:
                _auto_groove_settings = None

        # Capture sample assignments on the main thread (GUI widget access).
        _sample_assignments = (
            self._instrument_builder.get_sample_assignments()
            if self._instrument_builder is not None else {}
        )

        # Capture timbre params on the main thread.
        _instrument_params = self._get_instrument_params()

        def _worker():
            try:
                temp_dir = Path(APP_DIR) / "temp_output"
                temp_dir.mkdir(exist_ok=True)
                _genre = getattr(config, 'genre', '')

                # ── Full Beat ──────────────────────────────────────────
                midi_path = None
                _wav_path = None
                if want_full:
                    self.msg_queue.put(('gen_progress', 10, "Composing full beat..."))
                    config.vocal_mask = False
                    composition = self.engine.compose(config)
                    _inject_track_gains(composition, _auto_groove_settings)
                    self.msg_queue.put(('gen_progress', 60, "Exporting full beat MIDI..."))
                    midi_path = str(temp_dir / f"preview_{gen_id}.mid")
                    self.engine.export_midi(composition, midi_path)
                else:
                    # We still need a composition object for the display
                    self.msg_queue.put(('gen_progress', 10, "Composing..."))
                    config.vocal_mask = False
                    composition = self.engine.compose(config)
                    _inject_track_gains(composition, _auto_groove_settings)

                # ── Vocal-Ready Beat ───────────────────────────────────
                vocal_midi_path = None
                vocal_wav_path  = None
                vr_composition  = None
                if want_vocal:
                    self.msg_queue.put(('gen_progress', 65, "Composing vocal-ready version..."))
                    config.vocal_mask = True
                    vr_composition = self.engine.compose(config)
                    _inject_track_gains(vr_composition, _auto_groove_settings)
                    config.vocal_mask = False   # restore
                    vocal_midi_path = str(temp_dir / f"preview_{gen_id}_vocal.mid")
                    self.engine.export_midi(vr_composition, vocal_midi_path)

                # Clean up old temp MIDI files (keep only the latest pair)
                for old in temp_dir.glob("preview_*.mid"):
                    if str(old) not in (midi_path, vocal_midi_path):
                        try: old.unlink()
                        except: pass

                # ── Auto-apply groove to MIDI before render ────────────
                # Groove is applied to a separate grooved copy so that
                # current_midi_path always stores the clean original MIDI.
                # That way "Apply Groove & Re-Render" still works correctly
                # and never double-processes an already-grooved file.
                _render_midi_path = midi_path   # default: original (no groove)
                if (want_full and midi_path
                        and GROOVE_AVAILABLE
                        and _auto_groove_settings is not None
                        and _auto_groove_settings.has_any_effect()):
                    try:
                        _bpm_for_groove = float(
                            composition.get('config', {}).get('bpm', 120.0))
                        _grooved_midi = str(temp_dir / f"preview_{gen_id}_grooved.mid")
                        if GrooveProcessor().process(
                                midi_path, _grooved_midi,
                                _auto_groove_settings, _bpm_for_groove):
                            _render_midi_path = _grooved_midi
                    except Exception:
                        pass   # fallback: render from original MIDI

                # ── FluidSynth WAV render ──────────────────────────────
                # Skip FluidSynth when samples are assigned: FluidSynth renders
                # from MIDI/SoundFont and cannot apply custom audio samples.
                _use_fluid = (
                    not bool(_sample_assignments)
                    and FLUIDSYNTH_AVAILABLE
                    and _FLUID_RENDERER is not None
                )
                if _use_fluid:
                    _sf_name = _FLUID_RENDERER._library.display_name(_genre)
                    if want_full and midi_path:
                        self.msg_queue.put(('gen_progress', 75,
                                            f'Rendering full beat [{_sf_name}]...'))
                        _wav_out = str(temp_dir / f'preview_{gen_id}.wav')
                        if _FLUID_RENDERER.render(_render_midi_path, _wav_out, genre=_genre):
                            _wav_path = _wav_out
                    if want_vocal and vocal_midi_path:
                        self.msg_queue.put(('gen_progress', 90,
                                            f'Rendering vocal-ready [{_sf_name}]...'))
                        _vr_wav_out = str(temp_dir / f'preview_{gen_id}_vocal.wav')
                        if _FLUID_RENDERER.render(vocal_midi_path, _vr_wav_out, genre=_genre):
                            vocal_wav_path = _vr_wav_out

                # ── Builtin-synth WAV fallback (macOS / no FluidSynth) ─────
                if want_full and _wav_path is None and composition is not None:
                    self.msg_queue.put(('gen_progress', 75,
                                        'Rendering audio (built-in synth — may take ~30 s)…'))

                    def _full_progress(done, total, _base=75, _span=20):
                        if total > 0:
                            pct = _base + int(_span * done / total)
                            self.msg_queue.put((
                                'gen_progress', pct,
                                f'Rendering audio… {done}/{total} events'))

                    _builtin_wav = str(temp_dir / f'preview_{gen_id}.wav')
                    try:
                        WAVRenderer().render_composition_to_wav(
                            composition, _builtin_wav,
                            progress_callback=_full_progress,
                            sample_assignments=_sample_assignments,
                            instrument_params=_instrument_params,
                            groove_settings=_auto_groove_settings)
                        _wav_path = _builtin_wav
                    except Exception as _e:
                        self.msg_queue.put(('gen_progress', 75,
                                            f'Built-in synth render failed: {_e}'))

                if want_vocal and vocal_wav_path is None and vr_composition is not None:
                    self.msg_queue.put(('gen_progress', 95,
                                        'Rendering vocal-ready audio (built-in synth)…'))
                    _vr_builtin_wav = str(temp_dir / f'preview_{gen_id}_vocal.wav')
                    try:
                        WAVRenderer().render_composition_to_wav(
                            vr_composition, _vr_builtin_wav,
                            sample_assignments=_sample_assignments,
                            instrument_params=_instrument_params,
                            groove_settings=_auto_groove_settings)
                        vocal_wav_path = _vr_builtin_wav
                    except Exception as _e:
                        self.msg_queue.put(('gen_progress', 95,
                                            f'Built-in synth vocal render failed: {_e}'))

                # Clean up old WAV previews
                keep_wavs = {_wav_path, vocal_wav_path} - {None}
                for old in temp_dir.glob('preview_*.wav'):
                    if str(old) not in keep_wavs:
                        try: old.unlink()
                        except: pass

                self.msg_queue.put((
                    'gen_done', composition,
                    midi_path, _wav_path,
                    vocal_midi_path, vocal_wav_path,
                    vr_composition,
                ))
            except Exception as e:
                self.msg_queue.put(('gen_error', str(e)))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_generate_batch(self):
        if not getattr(self, 'engine', None):
            self._info_add("Engine not loaded yet.", "warn")
            return

        self.btn_batch.config(state=tk.DISABLED)
        self._set_status("GENERATING BATCH...", "orange")

        genre = self.genre_var.get().lower()

        def batch_worker():
            try:
                self.engine.generate_batch(
                    count=5,
                    genre=genre,
                    base_output_dir=os.path.join(APP_DIR, "cinematic_batch")
                )

                self.root.after(0, lambda: self._set_status("BATCH COMPLETE", "green"))
                self.root.after(0, lambda: self._info_add(
                    f"Successfully exported 5 {genre} tracks to /cinematic_batch/", "info"))

            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self._set_status("BATCH ERROR", "red"))
                self.root.after(0, lambda m=error_msg: self._info_add(f"Error: {m}", "warn"))
            finally:
                self.root.after(0, lambda: self.btn_batch.config(state=tk.NORMAL))

        threading.Thread(target=batch_worker, daemon=True).start()

    def _display_composition(self, comp):
        self._info_clear()
        c = comp['config']
        self._info_add("=======================================\n", 'dim')
        self._info_add("    COMPOSITION GENERATED\n", 'header')
        self._info_add("=======================================\n\n", 'dim')

        for label, val in [("GENRE", c['genre'].upper()), ("BPM", c['bpm']),
                           ("KEY", c['key']), ("COMPLEXITY", f"{c['complexity']}/10"),
                           ("BARS", comp['total_bars']),
                           ("DURATION", f"{comp['duration_seconds']:.1f}s")]:
            self._info_add(f"{label:12s}", 'section')
            self._info_add(f"{val}\n", 'value')

        self._info_add("\nSTRUCTURE\n", 'header')
        for stype, bars in comp['structure']:
            self._info_add(f"  [{stype.upper():12s}] ", 'section')
            self._info_add(f"{bars} bars\n")

        self._info_add("\nCHORDS\n", 'header')
        prog = comp['chord_progression']
        for i in range(0, min(len(prog), 32), 4):
            self._info_add(f"  {' -> '.join(prog[i:i+4])}\n", 'chord')
        if len(prog) > 32:
            self._info_add(f"  ... ({len(prog)-32} more)\n", 'dim')

        self._info_add("\nTRACKS\n", 'header')
        for name, events in comp['tracks'].items():
            self._info_add(f"  {name.upper():8s}", 'section')
            self._info_add(f" {len(events)} events\n", 'value')

    # ─────────────────────────────────────────────────────────────
    #  PLAYBACK & EXPORT
    # ─────────────────────────────────────────────────────────────

    def _play_preview(self):
        if not self.current_midi_path or not os.path.exists(self.current_midi_path):
            messagebox.showinfo("No Preview", "Generate a song first!")
            return
        # Prefer WAV if already rendered (better quality), otherwise play MIDI directly
        if self.current_wav_path and os.path.exists(self.current_wav_path):
            success = self.player.play_wav(self.current_wav_path, start_sec=0.0)
        else:
            success = self.player.play_midi(self.current_midi_path)
        if success:
            self._set_status("PLAYING", S.GREEN)
            # Reset waveform playhead to the beginning
            if self._waveform_widget is not None:
                self._waveform_widget.update_playhead(0.0)
        else:
            msg = "Install pygame for playback:\npip install pygame" if not PYGAME_AVAILABLE else "Playback failed"
            self._log(msg)

    def _on_waveform_seek(self, fraction: float) -> None:
        """
        Called when the user clicks or drags on the waveform canvas.

        If audio is currently playing, seeks to the new position.
        If audio is loaded but stopped, starts playback from the clicked position
        so the user can explore the song without pressing PLAY first.
        """
        if self._waveform_widget is None:
            return
        dur = self._waveform_widget._duration
        if dur <= 0:
            return
        target_sec = fraction * dur

        if self.player.is_busy():
            # Already playing — reposition without restarting
            self.player.seek(target_sec)
        elif self.current_wav_path and os.path.exists(self.current_wav_path):
            # Not playing — start from the clicked position
            success = self.player.play_wav(self.current_wav_path, start_sec=target_sec)
            if success:
                self._set_status("PLAYING", S.GREEN)

    def _play_vocal_ready(self):
        if not self.vocal_ready_midi_path and not self.vocal_ready_wav_path:
            self._log("No vocal-ready version available — generate first.")
            return
        if self.vocal_ready_wav_path and os.path.exists(self.vocal_ready_wav_path):
            success = self.player.play_wav(self.vocal_ready_wav_path)
        else:
            success = self.player.play_midi(self.vocal_ready_midi_path)
        if success:
            self._set_status("PLAYING  Vocal-Ready", S.PINK)
        else:
            self._log("Vocal-ready playback failed.")

    def _stop_playback(self):
        # Cancel any in-progress FluidSynth render (kills the subprocess)
        if FLUIDSYNTH_AVAILABLE and _FLUID_RENDERER is not None:
            _FLUID_RENDERER.cancel()
        self.player.stop()
        self._set_status("STOPPED", S.YELLOW)

    # ── Advisor WAV callback ──────────────────────────────────────────────────

    def _on_advisor_wav_ready(self, wav_path: str) -> None:
        """Update waveform widget and current_wav_path after an advisor preview render."""
        self.current_wav_path = wav_path
        if PLAYER_WIDGETS_AVAILABLE and self._waveform_widget is not None:
            self._waveform_widget.load_wav(wav_path)

    def _get_instrument_params(self) -> dict:
        """
        Return the current timbre parameters from the TimbreEditorPanel.

        Returns an empty dict when the panel is not available so all callers
        can treat the result as a plain dict without None-guards.
        """
        if self._timbre_editor is None:
            return {}
        try:
            raw = self._timbre_editor.get_instrument_params()
            # Filter out None entries so callers can do a plain dict.get()
            return {k: v for k, v in raw.items() if v is not None}
        except Exception:
            return {}

    # ── Groove helpers ────────────────────────────────────────────────────────

    def _advisor_apply_groove(
        self, comp: dict, mid_path: str, genre: str, bpm: float
    ) -> str:
        """
        Apply current Groove & Mixer settings to an advisor preview composition.

        Called by AdvisorActionsBar after composing so the advisor preview
        reflects any gain/mute changes the user made in the Groove section.

        Modifies *comp* in-place (injects 'gain' into track_info for the
        built-in synth path) and returns a (possibly grooved) MIDI path
        for the FluidSynth path.
        """
        if self._mixer_panel is None:
            return mid_path
        groove_settings = self._mixer_panel.get_settings(genre=genre)
        groove_settings.apply_enabled = True
        # Inject gains into composition dict so built-in synth respects them.
        _inject_track_gains(comp, groove_settings)
        # Process MIDI with GrooveProcessor for FluidSynth CC7/CC10.
        if GROOVE_AVAILABLE and groove_settings.has_any_effect():
            grooved = str(Path(APP_DIR) / 'temp_output' / 'advisor_grooved.mid')
            try:
                if GrooveProcessor().process(mid_path, grooved, groove_settings, bpm):
                    return grooved
            except Exception:
                pass
        return mid_path

    def _apply_groove_and_rerender(self) -> None:
        """
        Apply the current groove settings to the cached MIDI and re-render.

        Called when the user clicks [APPLY GROOVE & RE-RENDER] in MixerPanel.
        The composition engine is NOT invoked — the existing MIDI is reused,
        so this is fast (~3-5 s with FluidSynth) and non-destructive: the
        original clean MIDI is always preserved for further iterations.

        Flow:
          current_midi_path  →  GrooveProcessor  →  grooved temp MIDI
                             →  FluidSynth        →  grooved WAV
                             →  waveform widget updated, current_wav_path updated
        """
        if not self.current_midi_path or not os.path.exists(self.current_midi_path):
            self._log("Groove: no MIDI available — generate a song first.")
            return
        if self.is_generating:
            self._log("Groove: render already in progress — please wait.")
            return
        if not GROOVE_AVAILABLE or self._mixer_panel is None:
            self._log("Groove: groove module not available.")
            return

        # Capture settings on the main thread before the worker starts.
        # genre is read first so it can be forwarded into SongGrooveSettings
        # for MicroTimingEngine genre-aware grid generation in GrooveProcessor.
        genre = self.genre_var.get()
        groove_settings = self._mixer_panel.get_settings(genre=genre)
        # Force processing even if the "Apply groove" checkbox is unchecked —
        # the user explicitly clicked the button, so their gain/pan/swing
        # changes should always take effect.
        groove_settings.apply_enabled = True
        bpm = 120.0
        if self.current_composition:
            bpm = float(self.current_composition.get('config', {}).get('bpm', 120.0))

        # Capture sample assignments on the main thread before the worker starts.
        _groove_sample_assignments = (
            self._instrument_builder.get_sample_assignments()
            if self._instrument_builder is not None else {}
        )

        # Capture timbre params on the main thread.
        _groove_instrument_params = self._get_instrument_params()

        # Deep-copy the composition on the main thread before the worker starts.
        # This ensures the worker operates on a private snapshot — _inject_track_gains
        # can then mutate it freely without touching the shared current_composition.
        # It also guarantees that a second Apply Groove always starts from the same
        # original events regardless of what the previous run modified.
        import copy as _copy
        _groove_comp = _copy.deepcopy(self.current_composition) if self.current_composition else None

        self.is_generating = True
        self._mixer_panel.set_busy(True)
        self._set_status("APPLYING GROOVE...", S.ORANGE)
        self._log("Groove: processing MIDI and re-rendering...")

        def _worker():
            try:
                temp_dir = Path(APP_DIR) / "temp_output"
                temp_dir.mkdir(exist_ok=True)

                midi_to_render = self.current_midi_path

                # Apply groove transforms if any settings differ from identity.
                if groove_settings.has_any_effect():
                    grooved_mid = str(temp_dir / "groove_preview.mid")
                    ok = GrooveProcessor().process(
                        midi_to_render, grooved_mid, groove_settings, bpm
                    )
                    if ok:
                        midi_to_render = grooved_mid

                # Render: skip FluidSynth when samples are assigned so that
                # SampleEngine can substitute audio on the built-in synth path.
                wav_out  = str(temp_dir / "groove_preview.wav")
                rendered = False

                if (not bool(_groove_sample_assignments)
                        and FLUIDSYNTH_AVAILABLE
                        and _FLUID_RENDERER is not None):
                    rendered = _FLUID_RENDERER.render(midi_to_render, wav_out, genre=genre)

                if not rendered and _groove_comp is not None:
                    try:
                        _inject_track_gains(_groove_comp, groove_settings)
                        WAVRenderer().render_composition_to_wav(
                            _groove_comp, wav_out,
                            sample_assignments=_groove_sample_assignments,
                            instrument_params=_groove_instrument_params,
                            groove_settings=groove_settings,
                        )
                        rendered = True
                    except Exception:
                        pass

                if rendered and os.path.exists(wav_out):
                    self.msg_queue.put(('groove_done', wav_out))
                else:
                    self.msg_queue.put(('groove_fail', 'Render produced no output'))

            except Exception as exc:
                self.msg_queue.put(('groove_fail', str(exc)))

        threading.Thread(target=_worker, daemon=True).start()

    def _open_export_dialog(self) -> None:
        """Open the multi-format audio export dialog."""
        if not EXPORT_DIALOG_AVAILABLE:
            self._log("Export dialog not available.")
            return
        if not self.current_wav_path or not os.path.exists(self.current_wav_path):
            messagebox.showinfo(
                "No audio",
                "No rendered WAV found.\nGenerate a song first, then export.",
            )
            return
        ExportDialog(
            parent      = self.root,
            styles      = S,
            source_wav  = self.current_wav_path,
            composition = self.current_composition,
            gen_number  = self.generation_counter,
            log_fn      = self._log,
            variant_id  = self._current_variant_id,
        )

    def _open_export_dialog_for_wav(self, wav_path: str) -> None:
        """Open the export dialog for an arbitrary wav_path (used by AdvisorActionsBar)."""
        if not EXPORT_DIALOG_AVAILABLE:
            self._log("Export dialog not available.")
            return
        if not wav_path or not os.path.exists(wav_path):
            messagebox.showinfo("No audio", "No rendered WAV found.")
            return
        ExportDialog(
            parent      = self.root,
            styles      = S,
            source_wav  = wav_path,
            composition = self.current_composition,
            gen_number  = self.generation_counter,
            log_fn      = self._log,
            variant_id  = self._current_variant_id,
        )

    def _export_midi(self):
        if not self.current_composition: messagebox.showinfo("", "Generate first!"); return
        p = filedialog.asksaveasfilename(
            defaultextension=".mid", filetypes=[("MIDI", "*.mid")],
            initialfile=f"SeedComposer_{self.current_composition['config']['genre']}.mid")
        if p:
            self.engine.export_midi(self.current_composition, p)
            self._log(f"MIDI -> {p}"); self._set_status("MIDI EXPORTED", S.GREEN)

    def _export_vocal_midi(self):
        if not self.vocal_ready_midi_path:
            messagebox.showinfo("", "No vocal-ready version generated yet."); return
        genre = self.current_composition['config']['genre'] if self.current_composition else 'track'
        p = filedialog.asksaveasfilename(
            defaultextension=".mid", filetypes=[("MIDI", "*.mid")],
            initialfile=f"SeedComposer_{genre}_vocal_ready.mid")
        if p:
            import shutil
            shutil.copy2(self.vocal_ready_midi_path, p)
            self._log(f"Vocal-Ready MIDI -> {p}"); self._set_status("VOCAL MIDI EXPORTED", S.PINK)

    def _export_vocal_wav(self):
        if not self.vocal_ready_wav_path:
            messagebox.showinfo("", "No vocal-ready WAV available — FluidSynth may be unavailable."); return
        genre = self.current_composition['config']['genre'] if self.current_composition else 'track'
        p = filedialog.asksaveasfilename(
            defaultextension=".wav", filetypes=[("WAV", "*.wav")],
            initialfile=f"SeedComposer_{genre}_vocal_ready.wav")
        if p:
            import shutil
            shutil.copy2(self.vocal_ready_wav_path, p)
            self._log(f"Vocal-Ready WAV -> {p}"); self._set_status("VOCAL WAV EXPORTED", S.PINK)

    def _export_wav(self):
        if not self.current_composition: messagebox.showinfo("", "Generate first!"); return
        p = filedialog.asksaveasfilename(
            defaultextension=".wav", filetypes=[("WAV", "*.wav")],
            initialfile=f"SeedComposer_{self.current_composition['config']['genre']}.wav")
        if not p: return
        self._set_status("RENDERING WAV...", S.ORANGE)
        _export_ip = self._get_instrument_params()
        _export_groove = None
        if GROOVE_AVAILABLE and self._mixer_panel is not None:
            try:
                _export_groove = self._mixer_panel.get_settings(
                    genre=self.current_composition.get('config', {}).get('genre', ''))
            except Exception:
                pass
        def _w():
            try:
                WAVRenderer().render_composition_to_wav(
                    self.current_composition, p,
                    instrument_params=_export_ip,
                    groove_settings=_export_groove)
                self.msg_queue.put(('wav_done', p))
            except Exception as e:
                self.msg_queue.put(('wav_error', str(e)))
        threading.Thread(target=_w, daemon=True).start()

    def _export_json(self):
        if not self.current_composition: messagebox.showinfo("", "Generate first!"); return
        p = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")],
            initialfile=f"SeedComposer_{self.current_composition['config']['genre']}.json")
        if p:
            export = {k: v for k, v in self.current_composition.items() if k != 'tracks'}
            export['track_sizes'] = {k: len(v) for k, v in self.current_composition['tracks'].items()}
            with open(p, 'w') as f: json.dump(export, f, indent=2, default=str)
            self._log(f"JSON -> {p}"); self._set_status("JSON EXPORTED", S.GREEN)

    # ─────────────────────────────────────────────────────────────
    #  MESSAGE QUEUE
    # ─────────────────────────────────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                self._handle_msg(msg)
        except queue.Empty:
            pass

        # Advance the waveform playhead while audio is playing
        if (PLAYER_WIDGETS_AVAILABLE
                and self._waveform_widget is not None
                and self.player.is_busy()):
            dur = self._waveform_widget._duration
            if dur > 0:
                current_sec = self.player.get_current_sec()
                self._waveform_widget.update_playhead(current_sec / dur)

        self.root.after(50, self._poll_queue)

    def _handle_msg(self, msg):
        t = msg[0]
        if t == 'progress':
            _, cur, total, txt = msg
            self.progress_var.set(cur/total*100)
            self.progress_label.configure(text=f"[{cur}/{total}] {txt}")
        elif t == 'seed_done':
            _, count, sd = msg
            abs_path = os.path.abspath(sd)
            self.seed_status.configure(text=f"Built {count} seeds -> {abs_path}", fg=S.GREEN)
            self._set_status(f"SEEDS BUILT: {count}", S.GREEN)
            self._log(f"✓ {count} seeds saved to {abs_path}")
            self.progress_var.set(100)
            self.seeds_entry.delete(0, 'end')
            self.seeds_entry.insert(0, sd)
            self._load_seeds()
        elif t == 'seed_fail':
            self._set_status(f"SEED ERROR: {msg[1]}", S.RED)
            self._log(f"Error: {msg[1]}")
        elif t == 'gen_progress':
            self.progress_var.set(msg[1])
            self.progress_label.configure(text=msg[2])
            self._info_add(f"  {msg[2]}\n", 'dim')
        elif t == 'groove_done':
            # Groove re-render succeeded — update waveform and current WAV path.
            wav = msg[1]
            self.current_wav_path = wav
            self.is_generating = False
            if self._mixer_panel is not None:
                self._mixer_panel.set_busy(False)
            if PLAYER_WIDGETS_AVAILABLE and self._waveform_widget is not None:
                self._waveform_widget.load_wav(wav)
            self._set_status("GROOVE APPLIED — ready to play / export", S.GREEN)
            self._log("Groove: re-render complete.")
        elif t == 'groove_fail':
            self.is_generating = False
            if self._mixer_panel is not None:
                self._mixer_panel.set_busy(False)
            self._set_status("GROOVE RENDER FAILED", S.RED)
            self._log(f"Groove error: {msg[1] if len(msg) > 1 else 'unknown'}")
        elif t == 'gen_done':
            _, comp, midi, wav, vocal_midi, vocal_wav, vr_comp = msg
            self.current_composition    = comp
            self.current_midi_path      = midi
            self.current_wav_path       = wav
            self.vocal_ready_midi_path  = vocal_midi
            self.vocal_ready_wav_path   = vocal_wav
            self.vocal_ready_composition = vr_comp
            self.is_generating = False
            self.progress_var.set(100)
            self.progress_label.configure(text="Done!")
            self._display_composition(comp)
            if self._piano_roll is not None:
                self._piano_roll.load(comp)
            # Solo cache is stale after a new generation — clear it silently.
            if self._mixer_panel is not None:
                self._mixer_panel._reset_all_solos()
            # ── Update metadata panel and waveform ────────────────────────────
            if PLAYER_WIDGETS_AVAILABLE:
                if self._metadata_panel is not None:
                    meta = metadata_from_composition(
                        comp, wav, self.generation_counter,
                    )
                    self._metadata_panel.update(meta)
                if self._waveform_widget is not None and wav and os.path.exists(wav):
                    self._waveform_widget.load_wav(wav)
            # Auto-select the timbral variant deterministically from the seed
            # so each composition gets a consistent default flavor.
            if FX_VARIANT_AVAILABLE and FxChainSelector is not None:
                _seed = getattr(self, '_last_gen_seed', None)
                if _seed is not None:
                    _genre = comp['config']['genre']
                    self._current_variant_id = FxChainSelector.select_variant_id(_genre, _seed)
                    if self._fx_variant_panel is not None:
                        self._fx_variant_panel.refresh()
            self._update_advisor(comp)
            # Propagate the pinned seed to AdvisorActionsBar so its preview
            # re-composes the same note structure with different instruments.
            if self._advisor_actions is not None:
                self._advisor_actions.set_seed(getattr(self, '_last_gen_seed', None))
            # Show/hide the vocal-ready play button based on whether it was generated
            if vocal_midi:
                self._vr_frame.pack(fill='x', padx=6, pady=(0, 2))
            else:
                self._vr_frame.pack_forget()
            parts = ["Full Beat" if midi else None, "Vocal-Ready" if vocal_midi else None]
            label = " + ".join(p for p in parts if p)
            self._set_status(f"READY — {label} generated", S.GREEN)
            c = comp['config']
            self._log(f"✓ {c['genre'].upper()} | {c['bpm']} BPM | {c['key']} | "
                      f"{comp['total_bars']} bars | {comp['duration_seconds']:.1f}s")
            if vocal_midi:
                self._log(f"  Vocal-ready MIDI → {vocal_midi}")
            self._update_scaffold_source_label()

            if self.bpm_auto.get():
                self.bpm_scale.configure(state='normal')
                self.bpm_scale.set(int(c['bpm']))
                self.bpm_scale.configure(state='disabled')
            if self.key_auto.get():
                parts = c['key'].split()
                if parts:
                    self.key_root.configure(state='readonly')
                    self.key_root.set(parts[0])
                    self.key_root.configure(state='disabled')
                if len(parts) > 1:
                    self.key_mode.configure(state='readonly')
                    self.key_mode.set(parts[1])
                    self.key_mode.configure(state='disabled')
            if self.chord_auto.get() and c.get('starting_chord'):
                sc = c['starting_chord']
                if len(sc) > 1 and sc[1] in '#b':
                    cr, cq = sc[:2], sc[2:] or 'maj7'
                else:
                    cr, cq = sc[0], sc[1:] or 'maj7'
                self.chord_root.configure(state='readonly')
                self.chord_root.set(cr)
                self.chord_root.configure(state='disabled')
                self.chord_quality.configure(state='readonly')
                self.chord_quality.set(cq)
                self.chord_quality.configure(state='disabled')
        elif t == 'gen_error':
            self.is_generating = False
            self._set_status(f"ERROR: {msg[1]}", S.RED)
            self._info_add(f"\nERROR: {msg[1]}\n", 'warn')
        elif t == 'wav_done':
            self._set_status("WAV EXPORTED", S.GREEN)
            self._log(f"WAV -> {msg[1]}")
        elif t == 'wav_error':
            self._set_status(f"WAV ERROR: {msg[1]}", S.RED)

    # ─────────────────────────────────────────────────────────────
    #  PROMPT DECODER
    # ─────────────────────────────────────────────────────────────

    def _clear_prompt(self):
        self._prompt_entry.delete(0, 'end')
        self._decoded_label.configure(text="", fg=S.CYAN)

    def _decode_and_show(self):
        """Run the decoder and update the feedback label without generating."""
        if not self._cipher:
            return
        text = self._prompt_entry.get().strip()
        if not text:
            self._decoded_label.configure(text="", fg=S.CYAN)
            return
        decoded = self._cipher.decode_prompt(text)
        if decoded.is_empty():
            self._decoded_label.configure(
                text="No recognisable parameters detected.", fg=S.YELLOW)
        else:
            self._decoded_label.configure(
                text=f">  {decoded.summary()}", fg=S.CYAN)

    def _apply_prompt_overrides(self, config: 'CompositionConfig',
                                decoded: 'DecodedParams') -> None:
        """
        Merge decoded prompt parameters into *config*, overriding any
        GUI-widget values that were set to their defaults / auto.
        """
        if decoded.is_empty():
            return

        if decoded.genre:
            config.genre = decoded.genre
            self.genre_var.set(decoded.genre)   # sync radio button

        if decoded.bpm is not None:
            config.bpm = decoded.bpm

        if decoded.scale_hint:
            # Determine the root note: keep whatever was set, else default 'C'
            root = 'C'
            if config.key:
                parts = config.key.split()
                root = parts[0] if parts else 'C'
            config.key = f"{root} {decoded.scale_hint}"

        if decoded.tension_multiplier is not None:
            config.tension_multiplier = decoded.tension_multiplier

        if decoded.complexity is not None:
            config.complexity = decoded.complexity

    # ─────────────────────────────────────────────────────────────
    #  UTAU BRIDGE SECTION
    # ─────────────────────────────────────────────────────────────

    def _build_utau_section(self, parent):
        frame = self._section(parent, "VOCAL SYNTH", S.ORANGE)

        # ── Step 1 ────────────────────────────────────────────────
        tk.Label(frame, text="① Export note scaffold  →  paste into AI  →  fill syllables",
                 font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2, anchor='w').pack(fill='x', pady=(0, 2))

        r1 = tk.Frame(frame, bg=S.BG2); r1.pack(fill='x', pady=2)
        self._cbtn(r1, "EXPORT LYRIC SCAFFOLD JSON", self._export_lyric_scaffold,
                   S.CYAN, wide=True).pack(side='left', fill='x', expand=True, padx=(0, 4))

        # External MIDI loader — lets the user scaffold any .mid from disk
        ext_row = tk.Frame(frame, bg=S.BG2); ext_row.pack(fill='x', pady=(2, 0))
        self._cbtn(ext_row, "LOAD MIDI FROM FILE", self._load_external_midi,
                   S.ORANGE).pack(side='left', padx=(0, 6))
        self._ext_midi_label = tk.Label(ext_row, text="No file loaded",
                                        font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2, anchor='w')
        self._ext_midi_label.pack(side='left', fill='x', expand=True)
        self._clear_ext_btn = self._cbtn(ext_row, "✕", self._clear_external_midi, S.TXT_DIM)
        # hidden until a file is loaded
        self._clear_ext_btn.pack_forget()

        # Live source indicator — shows which MIDI will feed the scaffold
        self._scaffold_source_label = tk.Label(
            frame, text="Source: none — generate a song or load a MIDI",
            font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2, anchor='w',
        )
        self._scaffold_source_label.pack(fill='x', pady=(2, 4))

        # ── Step 2 ────────────────────────────────────────────────
        tk.Frame(frame, bg=S.BG3, height=1).pack(fill='x', pady=4)
        tk.Label(frame, text="② Upload AI-filled JSON with syllables / lyrics",
                 font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2, anchor='w').pack(fill='x', pady=(0, 2))

        r2 = tk.Frame(frame, bg=S.BG2); r2.pack(fill='x', pady=2)
        self._cbtn(r2, "IMPORT LYRICS JSON", self._import_lyrics_json,
                   S.GREEN, wide=True).pack(side='left', padx=(0, 6))
        self._lyric_file_label = tk.Label(r2, text="No file loaded",
                                           font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2,
                                           anchor='w', width=28)
        self._lyric_file_label.pack(side='left', fill='x', expand=True)

        # ── Step 3 ────────────────────────────────────────────────
        tk.Frame(frame, bg=S.BG3, height=1).pack(fill='x', pady=4)
        tk.Label(frame, text="③ Generate .ustx  (OpenUTAU vocal project)",
                 font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2, anchor='w').pack(fill='x', pady=(0, 2))

        r3 = tk.Frame(frame, bg=S.BG2); r3.pack(fill='x', pady=2)
        self._cbtn(r3, "GENERATE .USTX", self._generate_ustx,
                   S.ORANGE, wide=True).pack(side='left', padx=(0, 6))

        singer_frame = tk.Frame(r3, bg=S.BG2); singer_frame.pack(side='left', fill='x', expand=True)
        tk.Label(singer_frame, text="Singer:", font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2).pack(side='left')
        self._singer_entry = tk.Entry(singer_frame, font=S.FN_S, bg=S.BG_INPUT,
                                       fg=S.TXT, insertbackground=S.ORANGE, width=18)
        self._singer_entry.insert(0, "Kasane Teto")
        self._singer_entry.pack(side='left', padx=4)

        if not UTAU_AVAILABLE:
            tk.Label(frame, text="⚠  pyyaml not installed — pip install pyyaml",
                     font=S.FN_X, fg=S.YELLOW, bg=S.BG2).pack(fill='x', pady=2)

    # ── UTAU handler methods ──────────────────────────────────────

    @staticmethod
    def _midi_to_note_name(midi: int) -> str:
        names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        octave = (midi // 12) - 1
        return f"{names[midi % 12]}{octave}"

    # ── External MIDI helpers ─────────────────────────────────────

    @staticmethod
    def _parse_midi_melody(path: str):
        """Return (notes, bpm) from a MIDI file, auto-detecting the melody track.

        notes: list of (beat_pos, duration_beats, pitch_midi, velocity)
        Detection order: channel 2 (Music Architect melody) → channel with
        most notes in the singable range (C3–C6) → channel with most notes.
        Channel 9 (drums) is always excluded.
        """
        import mido
        mid = mido.MidiFile(path)
        tpb = mid.ticks_per_beat or 480

        tempo = 500000  # 120 BPM default
        for track in mid.tracks:
            for msg in track:
                if msg.type == 'set_tempo':
                    tempo = msg.tempo
                    break

        bpm = round(60_000_000 / tempo)

        notes_by_ch: dict = {}
        for track in mid.tracks:
            tick = 0
            active: dict = {}
            for msg in track:
                tick += msg.time
                if msg.type == 'note_on' and msg.velocity > 0:
                    active[(msg.channel, msg.note)] = (tick, msg.velocity)
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    key = (msg.channel, msg.note)
                    if key in active:
                        start, vel = active.pop(key)
                        notes_by_ch.setdefault(msg.channel, []).append(
                            (start, tick - start, msg.note, vel)
                        )

        notes_by_ch.pop(9, None)   # drop drums
        if not notes_by_ch:
            return [], bpm

        if 2 in notes_by_ch and notes_by_ch[2]:
            chosen = notes_by_ch[2]
        else:
            def _score(ch):
                return sum(1 for _, _, p, _ in notes_by_ch[ch] if 48 <= p <= 84)
            best = max(notes_by_ch, key=lambda ch: (_score(ch), len(notes_by_ch[ch])))
            chosen = notes_by_ch[best]

        notes = sorted(
            [(s / tpb, d / tpb, p, v) for s, d, p, v in chosen],
            key=lambda x: x[0],
        )
        return notes, bpm

    def _load_external_midi(self):
        p = filedialog.askopenfilename(
            filetypes=[("MIDI files", "*.mid *.midi"), ("All files", "*.*")],
            title="Select MIDI file for lyric scaffold",
        )
        if not p:
            return
        try:
            notes, bpm = self._parse_midi_melody(p)
        except Exception as e:
            messagebox.showerror("MIDI parse error", str(e)); return
        if not notes:
            messagebox.showwarning("No melody found",
                "Could not detect a melody track in this MIDI file."); return
        self._external_midi_path  = p
        self._external_midi_notes = notes
        self._external_midi_bpm   = bpm
        fname = os.path.basename(p)
        self._ext_midi_label.configure(text=fname, fg=S.GREEN)
        self._clear_ext_btn.pack(side='left', padx=2)
        self._update_scaffold_source_label()
        self._log(f"External MIDI loaded: {fname}  ({len(notes)} melody notes, {bpm} BPM)")

    def _clear_external_midi(self):
        self._external_midi_path  = None
        self._external_midi_notes = None
        self._external_midi_bpm   = 120
        self._ext_midi_label.configure(text="No file loaded", fg=S.TXT_DIM)
        self._clear_ext_btn.pack_forget()
        self._update_scaffold_source_label()

    def _update_scaffold_source_label(self):
        if not hasattr(self, '_scaffold_source_label'):
            return
        if self._external_midi_notes:
            fname = os.path.basename(self._external_midi_path)
            self._scaffold_source_label.configure(
                text=f"Source: {fname}  (external MIDI)", fg=S.ORANGE)
        elif self.vocal_ready_composition:
            self._scaffold_source_label.configure(
                text="Source: Vocal-Ready Beat  (auto-selected)", fg=S.PINK)
        elif self.current_composition:
            self._scaffold_source_label.configure(
                text="Source: Full Beat", fg=S.CYAN)
        else:
            self._scaffold_source_label.configure(
                text="Source: none — generate a song or load a MIDI", fg=S.TXT_DIM)

    # ── Scaffold export ───────────────────────────────────────────

    @staticmethod
    def _to_monophonic(notes: list, tolerance: float = 0.02) -> list:
        """Collapse polyphonic note lists to a single singable lead line.

        Notes that start within `tolerance` beats of each other are treated
        as simultaneous (a chord).  From each chord only the highest-pitched
        note is kept — that is the note a vocalist would sing.  The rest are
        harmonic support and have no place in a lyric scaffold.

        tolerance=0.02 beats ≈ 6 ms at 200 BPM — safely below any intentional
        stagger between successive melody notes.
        """
        if not notes:
            return []
        sorted_notes = sorted(notes, key=lambda n: n[0])
        groups: list[list] = []
        current: list = [sorted_notes[0]]
        for note in sorted_notes[1:]:
            if note[0] - current[0][0] <= tolerance:
                current.append(note)
            else:
                groups.append(current)
                current = [note]
        groups.append(current)
        # Keep only the highest pitch from each simultaneous group
        return [max(g, key=lambda n: n[2]) for g in groups]

    def _export_lyric_scaffold(self):
        # Priority: external MIDI > vocal-ready composition > full beat
        if self._external_midi_notes:
            notes_raw = self._external_midi_notes
            fname     = os.path.basename(self._external_midi_path)
            song_name = os.path.splitext(fname)[0]
            meta = {
                'song_name':  song_name,
                'genre':      'Unknown',
                'bpm':        self._external_midi_bpm,
                'key':        'Unknown',
                'total_bars': None,
            }
        elif self.vocal_ready_composition:
            comp = self.vocal_ready_composition
            cfg  = comp['config']
            notes_raw = sorted(comp['tracks'].get('04_Melody', []), key=lambda n: n[0])
            if not notes_raw:
                messagebox.showwarning("No melody", "Vocal-Ready Beat has no melody notes."); return
            meta = {
                'song_name':  f"SeedComposer_{cfg['genre']}_vocal_ready",
                'genre':      cfg['genre'],
                'bpm':        cfg['bpm'],
                'key':        cfg['key'],
                'total_bars': comp['total_bars'],
            }
        elif self.current_composition:
            comp = self.current_composition
            cfg  = comp['config']
            notes_raw = sorted(comp['tracks'].get('04_Melody', []), key=lambda n: n[0])
            if not notes_raw:
                messagebox.showwarning("No melody", "The composition has no 04_Melody notes."); return
            meta = {
                'song_name':  f"SeedComposer_{cfg['genre']}",
                'genre':      cfg['genre'],
                'bpm':        cfg['bpm'],
                'key':        cfg['key'],
                'total_bars': comp['total_bars'],
            }
        else:
            messagebox.showinfo("No source",
                "Generate a song or load an external MIDI file first.")
            return

        # Reduce polyphonic melody to a single singable lead line.
        # Simultaneous notes (chords / harmonic support) are collapsed to
        # the highest pitch only — the note a vocalist would actually sing.
        raw_count  = len(notes_raw)
        notes_mono = self._to_monophonic(notes_raw)

        notes_out = []
        for i, (beat_pos, dur_beats, pitch, vel) in enumerate(notes_mono):
            notes_out.append({
                "note_index":     i,
                "beat_position":  round(float(beat_pos), 4),
                "duration_beats": round(float(dur_beats), 4),
                "pitch_midi":     int(pitch),
                "pitch_name":     self._midi_to_note_name(int(pitch)),
                "lyric":          "la",
            })

        scaffold = {
            "song_name":    meta['song_name'],
            "genre":        meta['genre'],
            "bpm":          meta['bpm'],
            "key":          meta['key'],
            "instructions": (
                f"Fill each 'lyric' field with ONE syllable that fits the melody. "
                f"Genre: {meta['genre'].upper()}, Key: {meta['key']}, BPM: {meta['bpm']}. "
                f"Keep syllables natural and singable. "
                f"Do NOT change any other fields."
            ),
            "notes": notes_out,
        }
        if meta['total_bars'] is not None:
            scaffold["total_bars"] = meta['total_bars']

        p = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile=f"lyric_scaffold_{meta['song_name']}.json",
            title="Save Lyric Scaffold JSON",
        )
        if not p:
            return

        with open(p, 'w', encoding='utf-8') as f:
            json.dump(scaffold, f, indent=2, ensure_ascii=False)

        reduction = f"{raw_count} → {len(notes_out)}" if raw_count != len(notes_out) else str(len(notes_out))
        self._log(f"Lyric scaffold -> {p}  ({reduction} notes, polyphony collapsed to lead line)")
        self._set_status("SCAFFOLD EXPORTED — fill lyrics with AI", S.CYAN)

    def _import_lyrics_json(self):
        p = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            title="Select AI-filled Lyrics JSON",
        )
        if not p:
            return

        try:
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Load error", f"Could not read JSON:\n{e}")
            return

        if 'notes' not in data or not isinstance(data['notes'], list):
            messagebox.showerror("Format error",
                                 "JSON must contain a 'notes' list.\n"
                                 "Export a scaffold first, fill it with AI, then import.")
            return

        has_lyric = all('lyric' in n for n in data['notes'])
        if not has_lyric:
            messagebox.showwarning("Missing lyrics",
                                   "Some notes are missing the 'lyric' field. Check the JSON.")

        self._lyrics_json = data
        fname = Path(p).name
        self._lyric_file_label.configure(text=fname, fg=S.GREEN)
        self._log(f"Lyrics loaded: {fname}  ({len(data['notes'])} notes)")
        self._set_status("LYRICS IMPORTED — ready to generate USTX", S.GREEN)

    def _generate_ustx(self):
        if not UTAU_AVAILABLE:
            messagebox.showerror("Unavailable",
                                 "pyyaml is required for USTX export.\npip install pyyaml")
            return

        if not self._lyrics_json:
            messagebox.showinfo("No lyrics", "Import a lyrics JSON first (Step 2).")
            return

        data = self._lyrics_json
        notes_data = data.get('notes', [])
        if not notes_data:
            messagebox.showwarning("Empty", "The lyrics JSON has no notes.")
            return

        # Resolve BPM — prefer from lyrics JSON, fall back to current composition
        bpm = float(data.get('bpm') or
                    (self.current_composition['config']['bpm'] if self.current_composition else 120.0))
        song_name = data.get('song_name', 'SeedComposer')
        singer    = self._singer_entry.get().strip() or 'Kasane Teto'
        tpqn      = 480

        # Convert scaffold notes → RawNote (beat→tick)
        raw_all = []
        for n in notes_data:
            tick     = int(round(float(n['beat_position']) * tpqn))
            dur_tick = max(1, int(round(float(n['duration_beats']) * tpqn)))
            lyric    = str(n.get('lyric', 'la')).strip() or 'la'
            raw_all.append(RawNote(
                tick     = tick,
                duration = dur_tick,
                pitch    = int(n['pitch_midi']),
                velocity = 100,
                lyric    = lyric,
            ))

        raw_all.sort(key=lambda r: r.tick)

        # Group into phrases: split at gaps > 4 beats (4 * tpqn ticks)
        GAP_THRESHOLD = 4 * tpqn
        phrases: list[list] = []
        current_phrase: list = []
        prev_end = 0

        for rn in raw_all:
            if current_phrase and (rn.tick - prev_end) > GAP_THRESHOLD:
                phrases.append(current_phrase)
                current_phrase = []
            current_phrase.append(rn)
            prev_end = rn.tick + rn.duration

        if current_phrase:
            phrases.append(current_phrase)

        if not phrases:
            messagebox.showwarning("Empty", "No phrase groups could be built from the notes.")
            return

        p = filedialog.asksaveasfilename(
            defaultextension=".ustx",
            filetypes=[("OpenUTAU project", "*.ustx"), ("All files", "*.*")],
            initialfile=f"{song_name}.ustx",
            title="Save USTX Vocal Project",
        )
        if not p:
            return

        try:
            utau_export(
                output_path = Path(p),
                phrases     = phrases,
                tpqn        = tpqn,
                bpm         = bpm,
                song_name   = song_name,
                singer      = singer,
            )
            self._log(f"USTX -> {p}  ({len(phrases)} phrase(s), {len(raw_all)} notes)")
            self._set_status("USTX GENERATED", S.ORANGE)
            messagebox.showinfo("Done",
                                f"USTX project saved:\n{p}\n\n"
                                f"Open in OpenUTAU to edit and render the vocal track.")
        except Exception as e:
            self._set_status(f"USTX ERROR: {e}", S.RED)
            messagebox.showerror("USTX Error", str(e))

    def cleanup(self):
        self.player.cleanup()


def main():
    root = tk.Tk()
    # Enable dark-mode title bar on Windows 10/11 via undocumented DWM API.
    # Skipped on macOS and Linux where this API does not exist.
    if sys.platform == "win32":
        try:
            import ctypes
            root.update()
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int))
        except Exception:
            pass

    # ── ttk.Combobox popup-list colours ─────────────────────────────────────────
    # The dropdown listbox is a plain tk.Listbox under the hood — ttk.Style
    # cannot reach it.  The Tk option database is the only cross-platform way
    # to dark-theme it; it must be populated before any widget is created.
    root.option_add('*TCombobox*Listbox.background',        S.BG_INPUT)
    root.option_add('*TCombobox*Listbox.foreground',        S.TXT)
    root.option_add('*TCombobox*Listbox.selectBackground',  S.BG_BTN_ACT)
    root.option_add('*TCombobox*Listbox.selectForeground',  S.TXT_BRT)
    root.option_add('*TCombobox*Listbox.font',              ('Consolas', 9))

    # ── ttk.Style — professional dark theme ─────────────────────────────────────
    style = ttk.Style()
    style.theme_use('clam')   # 'clam' gives full colour control on Win/Mac/Linux

    # Combobox — dark field, accent arrow, subtle border
    style.configure('TCombobox',
        fieldbackground  = S.BG_INPUT,
        background       = S.BG_BTN,
        foreground       = S.TXT,
        selectbackground = S.BG_BTN_ACT,
        selectforeground = S.TXT_BRT,
        arrowcolor       = S.CYAN,          # studio-blue arrow matches primary accent
        arrowsize        = 14,
        bordercolor      = S.BG3,
        lightcolor       = S.BG3,
        darkcolor        = S.BG3,
        insertcolor      = S.CYAN,
        padding          = (4, 3),
    )
    style.map('TCombobox',
        fieldbackground = [('disabled', S.BG2),      ('readonly', S.BG_INPUT)],
        foreground      = [('disabled', S.TXT_DIM),  ('readonly', S.TXT)],
        background      = [('disabled', S.BG_BTN),   ('active', S.BG_BTN_HOV),
                           ('pressed', S.BG_BTN_ACT)],
        bordercolor     = [('focus', S.CYAN),         ('hover', S.BG_BTN_HOV)],
        arrowcolor      = [('disabled', S.TXT_DIM),   ('pressed', S.TXT_BRT)],
    )

    # Progress bar — accent colour fill, dark trough
    style.configure('TProgressbar',
        troughcolor = S.BG_INPUT,
        background  = S.CYAN,
        bordercolor = S.BG3,
        lightcolor  = S.CYAN,
        darkcolor   = S.CYAN,
    )

    # Notebook tabs — clean studio look, accent on selected tab
    style.configure('TNotebook',
        background  = S.BG2,
        borderwidth = 0,
        tabmargins  = [0, 0, 0, 0],
    )
    style.configure('TNotebook.Tab',
        background = S.BG3,
        foreground = S.TXT_DIM,
        padding    = [10, 4],
        font       = S.FN_S,
        borderwidth = 0,
    )
    style.map('TNotebook.Tab',
        background = [('selected', S.BG_BTN)],
        foreground = [('selected', S.TXT_BRT)],
    )

    # Scrollbar — neutral, unobtrusive
    style.configure('TScrollbar',
        background  = S.BG3,
        troughcolor = S.BG2,
        bordercolor = S.BG3,
        arrowcolor  = S.TXT_DIM,
        relief      = 'flat',
    )
    style.map('TScrollbar',
        background = [('active', S.BG_BTN_HOV)],
        arrowcolor = [('active', S.TXT)],
    )

    app = SeedComposerApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.cleanup(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
