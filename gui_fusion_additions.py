"""
═══════════════════════════════════════════════════════════════════════════════
GUI FUSION ADDITIONS FOR gui_composer.py
═══════════════════════════════════════════════════════════════════════════════

Follow these steps to add fusion controls to your GUI:
"""

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: Add import at top of gui_composer.py
# ═══════════════════════════════════════════════════════════════════════════════

"""
Add this import with your other imports:

from genre_fusion import FusionConfig, FUSION_PRESETS
"""


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: Replace your _build_genre_section method with this new version
# ═══════════════════════════════════════════════════════════════════════════════

"""
Replace your entire _build_genre_section method with this:
"""

def _build_genre_section(self, parent):
    frame = self._section(parent, "◢ GENRE ◣", S.PINK)
    
    # ─── Standard Genre Selection ───
    self.genre_var = tk.StringVar(value='pop')
    genres = ['pop','hiphop','trap','cinematic','classical','techno','jpop','phonk']
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
    
    # ─── FUSION MODE ───
    fusion_frame = tk.Frame(frame, bg=S.BG2)
    fusion_frame.pack(fill='x', pady=(10, 4))
    
    # Fusion checkbox
    self.fusion_enabled = tk.BooleanVar(value=False)
    fusion_cb = tk.Checkbutton(
        fusion_frame, text="🎮 FUSION MODE", variable=self.fusion_enabled,
        font=S.FN_S, fg=S.ORANGE, bg=S.BG2, selectcolor=S.BG3,
        activebackground=S.BG2, activeforeground=S.ORANGE,
        command=self._on_fusion_toggle
    )
    fusion_cb.pack(side='left', padx=5)
    
    # Fusion preset dropdown
    self.fusion_preset_var = tk.StringVar(value='cyber_ninja')
    fusion_presets = list(FUSION_PRESETS.keys())
    
    # Format preset names nicely for display
    preset_display = [p.replace('_', ' ').upper() for p in fusion_presets]
    
    self.fusion_combo = ttk.Combobox(
        fusion_frame, 
        textvariable=self.fusion_preset_var,
        values=fusion_presets,
        state='disabled',  # Disabled until fusion is enabled
        width=18,
        font=S.FN_S
    )
    self.fusion_combo.pack(side='left', padx=10)
    
    # Fusion description label
    self.fusion_desc_var = tk.StringVar(value="")
    self.fusion_desc_label = tk.Label(
        fusion_frame, textvariable=self.fusion_desc_var,
        font=S.FN_XS, fg=S.DIM, bg=S.BG2, anchor='w'
    )
    self.fusion_desc_label.pack(side='left', padx=10, fill='x', expand=True)
    
    # Bind preset change to update description
    self.fusion_combo.bind('<<ComboboxSelected>>', self._on_fusion_preset_change)
    
    # ─── Custom Fusion (Optional - shows when clicking "CUSTOM") ───
    custom_frame = tk.Frame(frame, bg=S.BG2)
    custom_frame.pack(fill='x', pady=(4, 0))
    
    # Custom fusion checkbox
    self.fusion_custom = tk.BooleanVar(value=False)
    custom_cb = tk.Checkbutton(
        custom_frame, text="Custom Mix:", variable=self.fusion_custom,
        font=S.FN_XS, fg=S.DIM, bg=S.BG2, selectcolor=S.BG3,
        activebackground=S.BG2, activeforeground=S.CYAN,
        command=self._on_custom_fusion_toggle
    )
    custom_cb.pack(side='left', padx=5)
    
    # Genre 1 dropdown
    self.fusion_genre1 = tk.StringVar(value='trap')
    self.fusion_genre1_combo = ttk.Combobox(
        custom_frame, textvariable=self.fusion_genre1,
        values=genres, state='disabled', width=10, font=S.FN_XS
    )
    self.fusion_genre1_combo.pack(side='left', padx=2)
    
    # Ratio slider
    tk.Label(custom_frame, text="+", font=S.FN_XS, fg=S.DIM, bg=S.BG2).pack(side='left')
    
    self.fusion_ratio = tk.IntVar(value=60)
    self.fusion_ratio_scale = tk.Scale(
        custom_frame, from_=20, to=80, orient='horizontal',
        variable=self.fusion_ratio, length=80, sliderlength=15,
        font=S.FN_XS, fg=S.CYAN, bg=S.BG2, troughcolor=S.BG3,
        highlightthickness=0, bd=0, state='disabled',
        showvalue=False
    )
    self.fusion_ratio_scale.pack(side='left', padx=2)
    
    # Ratio display
    self.fusion_ratio_label = tk.Label(
        custom_frame, text="60/40", font=S.FN_XS, fg=S.DIM, bg=S.BG2, width=6
    )
    self.fusion_ratio_label.pack(side='left')
    self.fusion_ratio.trace_add('write', self._update_ratio_label)
    
    # Genre 2 dropdown
    self.fusion_genre2 = tk.StringVar(value='jpop')
    self.fusion_genre2_combo = ttk.Combobox(
        custom_frame, textvariable=self.fusion_genre2,
        values=genres, state='disabled', width=10, font=S.FN_XS
    )
    self.fusion_genre2_combo.pack(side='left', padx=2)


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: Add these new methods to your GUI class
# ═══════════════════════════════════════════════════════════════════════════════

def _on_fusion_toggle(self):
    """Called when fusion checkbox is toggled."""
    enabled = self.fusion_enabled.get()
    
    if enabled:
        self.fusion_combo.config(state='readonly')
        self._on_fusion_preset_change(None)  # Update description
        # Disable standard genre selection visual feedback
        self._set_status("FUSION MODE ACTIVE", S.ORANGE)
    else:
        self.fusion_combo.config(state='disabled')
        self.fusion_desc_var.set("")
        # Also disable custom if fusion is off
        self.fusion_custom.set(False)
        self._on_custom_fusion_toggle()
        self._set_status("READY", S.GREEN)


def _on_fusion_preset_change(self, event):
    """Called when fusion preset is changed."""
    preset_name = self.fusion_preset_var.get()
    if preset_name in FUSION_PRESETS:
        preset = FUSION_PRESETS[preset_name]
        genres = " + ".join(preset['genres'])
        weights = "/".join([f"{int(w*100)}%" for w in preset['weights']])
        desc = f"{genres} ({weights}) - {preset['description']}"
        self.fusion_desc_var.set(desc)


def _on_custom_fusion_toggle(self):
    """Called when custom fusion checkbox is toggled."""
    custom = self.fusion_custom.get()
    fusion_on = self.fusion_enabled.get()
    
    if custom and fusion_on:
        # Enable custom controls, disable preset dropdown
        self.fusion_combo.config(state='disabled')
        self.fusion_genre1_combo.config(state='readonly')
        self.fusion_genre2_combo.config(state='readonly')
        self.fusion_ratio_scale.config(state='normal')
        self.fusion_desc_var.set("Custom mix - select genres and ratio")
    else:
        # Disable custom controls
        self.fusion_genre1_combo.config(state='disabled')
        self.fusion_genre2_combo.config(state='disabled')
        self.fusion_ratio_scale.config(state='disabled')
        if fusion_on:
            self.fusion_combo.config(state='readonly')
            self._on_fusion_preset_change(None)


def _update_ratio_label(self, *args):
    """Update the ratio display label."""
    ratio = self.fusion_ratio.get()
    self.fusion_ratio_label.config(text=f"{ratio}/{100-ratio}")


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: Update _build_config() to include fusion
# ═══════════════════════════════════════════════════════════════════════════════

"""
In your _build_config() method, ADD this block AFTER you create the config 
and set config.genre, but BEFORE the return statement:
"""

    # ─── FUSION CONFIG ───
    if self.fusion_enabled.get():
        if self.fusion_custom.get():
            # Custom fusion
            genre1 = self.fusion_genre1.get()
            genre2 = self.fusion_genre2.get()
            ratio = self.fusion_ratio.get() / 100.0
            config.fusion = FusionConfig.custom(genre1, genre2, ratio)
            print(f"◢ CUSTOM FUSION: {genre1} + {genre2} ({int(ratio*100)}/{int((1-ratio)*100)}) ◣")
        else:
            # Preset fusion
            preset_name = self.fusion_preset_var.get()
            config.fusion = FusionConfig.from_preset(preset_name)
            print(f"◢ FUSION PRESET: {preset_name.upper()} ◣")


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5: Update _display_composition() to show fusion info
# ═══════════════════════════════════════════════════════════════════════════════

"""
In _display_composition(), ADD this after showing the genre:

Find this line:
    for label, val in [("GENRE", c['genre'].upper()), ...

And change it to:
"""

    # Check if fusion was used
    fusion_info = ""
    if hasattr(config, 'fusion') and config.fusion:
        fusion_info = f" [FUSION: {' + '.join(config.fusion.genres)}]"
    
    for label, val in [("GENRE", c['genre'].upper() + fusion_info), ("BPM", c['bpm']),
                       ("KEY", c['key']), ("COMPLEXITY", f"{c['complexity']}/10"),
                       ("BARS", comp['total_bars']),
                       ("DURATION", f"{comp['duration_seconds']:.1f}s")]:


# ═══════════════════════════════════════════════════════════════════════════════
# COMPLETE UPDATED _build_config() METHOD
# ═══════════════════════════════════════════════════════════════════════════════

"""
Here's the complete _build_config method with fusion support:
"""

def _build_config(self):
    config = CompositionConfig()
    config.genre = self.genre_var.get()

    # BPM: None means the engine picks randomly from genre range or seeds
    config.bpm = None if self.bpm_auto.get() else float(self.bpm_scale.get())

    # Key: None means random
    config.key = None if self.key_auto.get() else f"{self.key_root.get()} {self.key_mode.get()}"

    # Chord: None means random
    config.starting_chord = None if self.chord_auto.get() else \
        f"{self.chord_root.get()}{self.chord_quality.get()}"

    config.complexity = int(self.complexity_scale.get())
    config.humanize_amount = self.humanize_scale.get() / 100.0

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

    # ─── FUSION CONFIG ───
    if self.fusion_enabled.get():
        if self.fusion_custom.get():
            # Custom fusion
            genre1 = self.fusion_genre1.get()
            genre2 = self.fusion_genre2.get()
            ratio = self.fusion_ratio.get() / 100.0
            config.fusion = FusionConfig.custom(genre1, genre2, ratio)
        else:
            # Preset fusion
            preset_name = self.fusion_preset_var.get()
            config.fusion = FusionConfig.from_preset(preset_name)

    return config
