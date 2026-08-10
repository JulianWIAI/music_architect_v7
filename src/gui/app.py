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
    from src.composition.genre_constants import GENRE_BPM, GENRE_INSTRUMENTS, STRUCTURE_TEMPLATES
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


class SeedComposerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SEED COMPOSER - CYBERPUNK EDITION")
        self.root.geometry("1300x920")
        self.root.minsize(1100, 750)
        self.root.configure(bg=S.BG)

        self.engine = None
        self.current_composition = None
        self.current_midi_path = None
        self.current_wav_path = None
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
        self._external_midi_notes: list | None = None
        self._external_midi_bpm: int = 120
        self._cipher = SemanticCipher() if PROMPT_DECODER_AVAILABLE else None

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
                 fg=S.CYAN, bg=S.BG2).pack(side='left', padx=15, pady=8)
        tk.Label(tf, text="AI-POWERED MUSIC GENERATION STUDIO",
                 font=S.FN_S, fg=S.TXT_DIM, bg=S.BG2).pack(side='left', padx=10)
        self.status_label = tk.Label(tf, text="● INIT", font=S.FN_S, fg=S.YELLOW, bg=S.BG2)
        self.status_label.pack(side='right', padx=15)

        content = tk.Frame(main, bg=S.BG)
        content.pack(fill='both', expand=True)

        left = tk.Frame(content, bg=S.BG2, width=540)
        left.pack(side='left', fill='y', padx=(0, 4)); left.pack_propagate(False)

        lc = tk.Canvas(left, bg=S.BG2, highlightthickness=0)
        sb = ttk.Scrollbar(left, orient='vertical', command=lc.yview)
        sf = tk.Frame(lc, bg=S.BG2)
        sf.bind('<Configure>', lambda e: lc.configure(scrollregion=lc.bbox('all')))
        lc.create_window((0, 0), window=sf, anchor='nw', width=520)
        lc.configure(yscrollcommand=sb.set)
        lc.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        lc.bind_all("<MouseWheel>", lambda e: lc.yview_scroll(int(-1*(e.delta/120)), "units"))

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
        self.key_mode = ttk.Combobox(r2, values=['major', 'minor'], width=6, state='disabled')
        self.key_mode.set('major'); self.key_mode.pack(side='left', padx=2)
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
        self.chord_quality = ttk.Combobox(r3, values=QUALITIES, width=6, state='disabled')
        self.chord_quality.set('maj7'); self.chord_quality.pack(side='left', padx=2)
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
            row = tk.Frame(frame, bg=S.BG2); row.pack(fill='x', pady=2)

            enabled = tk.BooleanVar(value=True)
            en_cb = tk.Checkbutton(row, text=track.upper(), variable=enabled, font=S.FN_S,
                                    fg=color, bg=S.BG2, selectcolor=S.BG3,
                                    activebackground=S.BG2, width=7, anchor='w')
            en_cb.pack(side='left')
            self._tip(en_cb, 'track_enabled')

            tk.Label(row, text="Vol:", font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2).pack(side='left')
            vol = tk.Scale(row, from_=0, to=100, orient='horizontal', font=S.FN_X,
                           fg=color, bg=S.BG2, troughcolor=S.BG_INPUT,
                           highlightthickness=0, length=80, showvalue=0)
            vol.set(80 if track != 'arp' else 50)
            vol.pack(side='left', padx=2)
            self._tip(vol, 'track_volume')

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

            self.track_vars[track] = {'enabled': enabled, 'volume': vol, 'instrument': inst}

        # ── Tracks 7-10: Stabs, Texture, FX, Percussion ─────────────────────
        # Each row is constructed by TrackInstrumentRow, which encapsulates the
        # checkbox, volume slider, instrument combobox, and Rand button in one
        # reusable class.  'percussion' is mode='percussion' — it shares the drum
        # channel (ch 9) so it has no program selector.
        _extended_tracks = [
            #  track key     mode          default  default  default
            #                              enabled  volume   program
            ('stabs',      'pitched',    True,    70,      55),   # Orchestra Hit default
            ('texture',    'pitched',    True,    60,      88),   # New Age Pad default
            ('fx',         'fx_sounds',  True,    50,      96),   # Rain FX default
            ('percussion', 'percussion', True,    60,      None), # no program — drum ch
        ]
        for _track, _mode, _enabled, _vol, _prog in _extended_tracks:
            _color = S.TRACK_CLR.get(_track, S.CYAN)
            _row = TrackInstrumentRow(
                frame,
                track=_track,
                mode=_mode,
                color=_color,
                default_enabled=_enabled,
                default_volume=_vol,
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
        info_frame = self._section(parent, "COMPOSITION OUTPUT", S.CYAN)

        self.info_text = tk.Text(info_frame, font=S.FN_S, bg=S.BG, fg=S.TXT,
                                  insertbackground=S.CYAN, height=18, wrap='word',
                                  state='disabled', bd=0, highlightthickness=1,
                                  highlightbackground=S.BG3)
        self.info_text.pack(fill='both', expand=True, pady=4)
        for tag, color in [('header', S.CYAN), ('value', S.GREEN), ('section', S.PINK),
                           ('chord', S.PURPLE), ('dim', S.TXT_DIM), ('warn', S.YELLOW)]:
            self.info_text.tag_configure(tag, foreground=color,
                                          font=S.FN_H if tag == 'header' else S.FN_S)

        self.progress_var = tk.DoubleVar()
        ttk.Progressbar(info_frame, variable=self.progress_var, maximum=100).pack(fill='x', pady=2)
        self.progress_label = tk.Label(info_frame, text="", font=S.FN_X, fg=S.TXT_DIM, bg=S.BG2)
        self.progress_label.pack(fill='x')

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
        btn_wav = self._cbtn(ef, "WAV", self._export_wav, S.ORANGE, wide=True)
        btn_wav.pack(side='left', padx=2, fill='x', expand=True)
        btn_json = self._cbtn(ef, "JSON", self._export_json, S.BLUE, wide=True)
        btn_json.pack(side='left', padx=2, fill='x', expand=True)
        self._tip(btn_midi, 'btn_midi')
        self._tip(btn_wav, 'btn_wav')
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
    #  TOGGLE CALLBACKS
    # ─────────────────────────────────────────────────────────────

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
            config.tracks[track_name]['volume'] = vd['volume'].get() / 100.0
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

        config = self._build_config()
        gen_id = self.generation_counter

        want_full   = self.gen_full_beat.get()
        want_vocal  = self.gen_vocal_ready.get()
        if not want_full and not want_vocal:
            # Guard: at least one must be selected
            want_full = True

        # Pin a shared seed so both compose() calls produce the same structure
        # and harmonic content — the vocal-ready version is a true paired variant,
        # not a different song with vocal_mask applied.
        if want_vocal and config.seed_value is None:
            config.seed_value = random.randint(1, 999999)

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
                    self.msg_queue.put(('gen_progress', 60, "Exporting full beat MIDI..."))
                    midi_path = str(temp_dir / f"preview_{gen_id}.mid")
                    self.engine.export_midi(composition, midi_path)
                else:
                    # We still need a composition object for the display
                    self.msg_queue.put(('gen_progress', 10, "Composing..."))
                    config.vocal_mask = False
                    composition = self.engine.compose(config)

                # ── Vocal-Ready Beat ───────────────────────────────────
                vocal_midi_path = None
                vocal_wav_path  = None
                vr_composition  = None
                if want_vocal:
                    self.msg_queue.put(('gen_progress', 65, "Composing vocal-ready version..."))
                    config.vocal_mask = True
                    vr_composition = self.engine.compose(config)
                    config.vocal_mask = False   # restore
                    vocal_midi_path = str(temp_dir / f"preview_{gen_id}_vocal.mid")
                    self.engine.export_midi(vr_composition, vocal_midi_path)

                # Clean up old temp MIDI files (keep only the latest pair)
                for old in temp_dir.glob("preview_*.mid"):
                    if str(old) not in (midi_path, vocal_midi_path):
                        try: old.unlink()
                        except: pass

                # ── FluidSynth WAV render ──────────────────────────────
                if FLUIDSYNTH_AVAILABLE and _FLUID_RENDERER is not None:
                    _sf_name = _FLUID_RENDERER._library.display_name(_genre)
                    if want_full and midi_path:
                        self.msg_queue.put(('gen_progress', 75,
                                            f'Rendering full beat [{_sf_name}]...'))
                        _wav_out = str(temp_dir / f'preview_{gen_id}.wav')
                        if _FLUID_RENDERER.render(midi_path, _wav_out, genre=_genre):
                            _wav_path = _wav_out
                    if want_vocal and vocal_midi_path:
                        self.msg_queue.put(('gen_progress', 90,
                                            f'Rendering vocal-ready [{_sf_name}]...'))
                        _vr_wav_out = str(temp_dir / f'preview_{gen_id}_vocal.wav')
                        if _FLUID_RENDERER.render(vocal_midi_path, _vr_wav_out, genre=_genre):
                            vocal_wav_path = _vr_wav_out

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
            success = self.player.play_wav(self.current_wav_path)
        else:
            success = self.player.play_midi(self.current_midi_path)
        if success:
            self._set_status("PLAYING", S.GREEN)
        else:
            msg = "Install pygame for playback:\npip install pygame" if not PYGAME_AVAILABLE else "Playback failed"
            self._log(msg)

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
        def _w():
            try:
                WAVRenderer().render_composition_to_wav(self.current_composition, p)
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
        frame = self._section(parent, "UTAU / VOCAL SYNTH", S.ORANGE)

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

        notes_out = []
        for i, (beat_pos, dur_beats, pitch, vel) in enumerate(notes_raw):
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

        self._log(f"Lyric scaffold -> {p}  ({len(notes_out)} notes)")
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

    style = ttk.Style(); style.theme_use('clam')
    style.configure('TCombobox', fieldbackground=S.BG_INPUT, background=S.BG_BTN,
                    foreground=S.TXT, arrowcolor=S.CYAN)
    style.map('TCombobox',
              fieldbackground=[('disabled', S.BG_INPUT), ('readonly', S.BG_INPUT)],
              foreground=[('disabled', S.CYAN), ('readonly', S.TXT)],
              background=[('disabled', S.BG_BTN)])
    style.configure('TProgressbar', troughcolor=S.BG_INPUT, background=S.CYAN)

    app = SeedComposerApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.cleanup(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
