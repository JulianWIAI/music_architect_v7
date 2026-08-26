"""
src/gui/timbre_editor_panel.py
────────────────────────────────
Per-instrument timbre preset selector and parameter editor.

Four instrument roles are exposed: KICK, SNARE/PERC, HI-HAT, MELODIC.
Each role has:
  - A preset combobox (e.g. Punchy, Space, Industrial, ...)
  - Three parameter sliders for the most impactful parameters

Changing a preset loads its values into the sliders so the user can
fine-tune from the preset baseline.  The sliders always win over the preset
values when get_instrument_params() is called — the preset is just a
starting point.

Public API
──────────
TimbreEditorPanel(parent, styles)
    get_instrument_params() -> dict
        Returns {
            'kick':    PercussionParams | None,
            'snare':   PercussionParams | None,
            'hihat':   PercussionParams | None,
            'melodic': MelodicParams    | None,
        }
        None values mean "use built-in default synthesis" for that role.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Optional, Tuple, Union

from src.rendering.instrument_params import (
    KICK_PRESETS, SNARE_PRESETS, HIHAT_PRESETS, MELODIC_PRESETS,
    PercussionParams, MelodicParams, list_presets, get_preset,
)

try:
    from src.gui.tooltips import ToolTip
    _TIP = True
except ImportError:
    _TIP = False


# ── Sentinel value shown at the top of every preset combobox ─────────────────
_NONE_OPTION = '(none)'

# ── Role definitions ──────────────────────────────────────────────────────────
# (role_key, display_label)
_ROLES: List[Tuple[str, str]] = [
    ('kick',    'KICK'),
    ('snare',   'SNARE'),
    ('hihat',   'HI-HAT'),
    ('melodic', 'MELODIC'),
]

# ── Per-role slider specifications ─────────────────────────────────────────────
# Each entry: (param_name, display_label, from_, to_, resolution, scale_factor)
# scale_factor is applied when READING slider → param value (param = slider / factor).
# For percentage sliders (0–100 display) the underlying param is 0.0–1.0,
# so scale_factor=100.  For direct ms/Hz values, scale_factor=1.
_SLIDER_SPECS: Dict[str, List[Tuple[str, str, float, float, float, float]]] = {
    'kick': [
        # param_name         label            from   to     resolution  scale_factor
        ('pitch_end_hz',  'Pitch End (Hz)', 20.0, 200.0,  1.0,        1.0),
        ('noise_amount',  'Noise (%)',       0.0, 100.0,  1.0,        100.0),
        ('decay_ms',      'Decay (ms)',     50.0, 1000.0, 10.0,       1.0),
    ],
    'snare': [
        ('pitch_end_hz',  'Pitch (Hz)',     80.0, 400.0,  1.0,        1.0),
        ('noise_amount',  'Noise (%)',       0.0, 100.0,  1.0,        100.0),
        ('decay_ms',      'Decay (ms)',     30.0, 400.0,  5.0,        1.0),
    ],
    'hihat': [
        ('decay_ms',      'Decay (ms)',     10.0, 400.0,  5.0,        1.0),
        ('noise_amount',  'Noise (%)',       0.0, 100.0,  1.0,        100.0),
        ('drive',         'Drive (%)',       0.0, 100.0,  1.0,        100.0),
    ],
    'melodic': [
        ('attack_ms',     'Attack (ms)',     1.0, 500.0,  1.0,        1.0),
        ('brightness',    'Brightness (%)', 0.0, 100.0,  1.0,        100.0),
        ('drive',         'Drive (%)',       0.0, 100.0,  1.0,        100.0),
    ],
}

# ── Tooltip text per role combobox and per slider ─────────────────────────────
_COMBO_TIPS: Dict[str, str] = {
    'kick':    'Kick drum synthesis preset — sets the starting point for the sliders.\n'
               'Select (none) to use the built-in default kick synthesis.',
    'snare':   'Snare / percussion synthesis preset.\n'
               'Select (none) to use the built-in default snare synthesis.',
    'hihat':   'Hi-hat synthesis preset.\n'
               'Select (none) to use the built-in default hi-hat synthesis.',
    'melodic': 'Melodic instrument preset — applies to bass, lead, chords, pad, arp, and texture.\n'
               'Select (none) to use the built-in default melodic synthesis.',
}

_SLIDER_TIPS: Dict[str, str] = {
    'kick/pitch_end_hz':   'Target frequency at the end of the pitch sweep.\n'
                           'Lower = deeper sub boom.  Higher = punchy click.\n'
                           'Typical: 40–80 Hz for sub kicks, 80–150 Hz for punchy kicks.',
    'kick/noise_amount':   'Noise layer blended into the kick body.\n'
                           '0% = pure tone.  10–20% adds texture without muddying the low end.\n'
                           'Very high values turn the kick into a noise burst.',
    'kick/decay_ms':       'Time for the kick transient to fade out.\n'
                           'Short (50–150 ms) = tight, punchy.  Long (400–800 ms) = boomy.',
    'snare/pitch_end_hz':  'Centre frequency of the snare body tone.\n'
                           'Lower = thicker, more tom-like.  Higher = crisper snap.',
    'snare/noise_amount':  'Noise layer that creates the snare wire rattle.\n'
                           'Higher values give more "snare wire" character.',
    'snare/decay_ms':      'Snare decay length.\n'
                           'Short = tight, dry.  Long = roomy, open.',
    'hihat/decay_ms':      'Open vs closed hat character.\n'
                           'Short (10–60 ms) = closed, choppy.  Long (200–400 ms) = open, washy.',
    'hihat/noise_amount':  'Metallic noise content of the hat.\n'
                           'Higher = more noise, broader frequency spread.',
    'hihat/drive':         'Soft saturation adds grit and presence to the hat transient.\n'
                           'Small amounts (10–30%) are often enough.',
    'melodic/attack_ms':   'Time to reach full volume from silence.\n'
                           'Short = pluck, percussive attack.  Long = smooth pad fade-in.',
    'melodic/brightness':  'High-frequency harmonic content.\n'
                           '0% = warm, rounded sine-wave character.\n'
                           '100% = bright, cutting, saw-wave character.',
    'melodic/drive':       'Soft tanh saturation applied to the output.\n'
                           'Adds warmth and harmonic richness at low values;\n'
                           'creates distortion / aggression at high values.',
}

# ── Header accent colours per role ────────────────────────────────────────────
# Resolved at build time against the styles object.
def _role_color(role: str, S) -> str:
    if role == 'kick':
        return getattr(S, 'YELLOW', getattr(S, 'CYAN', '#c89a38'))
    if role == 'snare':
        return getattr(S, 'ORANGE', getattr(S, 'CYAN', '#b86838'))
    if role == 'hihat':
        return getattr(S, 'TXT_BRT', '#e4e4f0')
    if role == 'melodic':
        return getattr(S, 'CYAN', '#5ba3d0')
    return getattr(S, 'TXT_DIM', '#585868')


class TimbreEditorPanel(tk.Frame):
    """
    Collapsible per-instrument timbre preset selector and parameter editor.

    Parameters
    ----------
    parent : tk.Widget
        Parent widget (typically the InstrumentBuilder content frame or
        the main app notebook tab).
    styles : object
        App styles namespace (S).  Must expose BG2, BG3, FN_S, FN_X,
        TXT_DIM, TXT_BRT, PINK, CYAN, YELLOW, ORANGE, BG_INPUT, BG_BTN,
        BG_BTN_ACT.
    """

    def __init__(self, parent: tk.Widget, styles) -> None:
        S = styles
        super().__init__(parent, bg=S.BG2)
        self._S = S

        # State
        self._expanded: bool = True

        # {role: StringVar} — tracks the selected preset name per role
        self._preset_vars: Dict[str, tk.StringVar] = {}

        # {(role, param_name): DoubleVar} — tracks each slider value
        self._vars: Dict[Tuple[str, str], tk.DoubleVar] = {}

        # {role: ttk.Combobox} — combobox widgets
        self._combos: Dict[str, ttk.Combobox] = {}

        self._build_ui()

    # ── Public API ───────────────────────────────────────────────────────────

    def get_instrument_params(self) -> Dict[str, Optional[Union[PercussionParams, MelodicParams]]]:
        """
        Return current params for all four roles.

        For each role the slider values are read and used to override the
        selected preset baseline.  If the combobox shows '(none)' the role
        returns None, meaning "use built-in default synthesis".

        Returns
        -------
        dict with keys 'kick', 'snare', 'hihat', 'melodic'.
        """
        result: Dict[str, Optional[Union[PercussionParams, MelodicParams]]] = {}

        for role, _ in _ROLES:
            preset_name = self._preset_vars[role].get()
            if preset_name == _NONE_OPTION:
                result[role] = None
                continue

            # Get the preset as a baseline (copy its values into a dict)
            base = get_preset(role, preset_name)
            params = self._build_params(role, base)
            result[role] = params

        return result

    # ── Construction ─────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        S = self._S

        # ── Collapsible header ─────────────────────────────────────────────
        hdr = tk.Frame(self, bg=S.BG2)
        hdr.pack(fill='x', pady=(2, 0))

        self._toggle_btn = tk.Button(
            hdr,
            text='▼ TIMBRE',
            font=S.FN_S,
            fg=S.PINK,
            bg=S.BG2,
            bd=0,
            activebackground=getattr(S, 'BG3', S.BG2),
            activeforeground=S.PINK,
            cursor='hand2',
            anchor='w',
            command=self._toggle,
        )
        self._toggle_btn.pack(side='left')
        if _TIP:
            ToolTip(self._toggle_btn,
                    'Per-instrument synthesis preset and parameter editor.\n\n'
                    'Select a preset to load its values into the sliders.\n'
                    'The sliders always override the preset — the preset is just\n'
                    'a starting point for fine-tuning.\n\n'
                    'Select (none) to use the built-in default synthesis for that role.\n'
                    'Only affects the built-in synth path — C++ and FluidSynth are unaffected.')

        # Thin accent separator
        tk.Frame(self, bg=S.PINK, height=1).pack(fill='x', pady=(2, 4))

        # ── Content frame (collapsible) ────────────────────────────────────
        self._content = tk.Frame(self, bg=S.BG2)
        self._content.pack(fill='x')

        for role, label in _ROLES:
            self._build_role_section(role, label)

    def _build_role_section(self, role: str, display_label: str) -> None:
        """Build the preset combobox + sliders section for one instrument role."""
        S = self._S
        color = _role_color(role, S)

        # Section container
        section = tk.Frame(self._content, bg=S.BG2)
        section.pack(fill='x', padx=4, pady=(4, 2))

        # Role header label
        tk.Label(
            section,
            text=display_label,
            font=S.FN_X,
            fg=color,
            bg=S.BG2,
            anchor='w',
        ).pack(fill='x', padx=2)

        # Preset combobox row
        combo_row = tk.Frame(section, bg=S.BG2)
        combo_row.pack(fill='x', padx=4, pady=(1, 2))

        tk.Label(
            combo_row,
            text='Preset',
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG2,
            width=7,
            anchor='w',
        ).pack(side='left')

        preset_var = tk.StringVar(value=_NONE_OPTION)
        self._preset_vars[role] = preset_var

        names = [_NONE_OPTION] + list_presets(role)
        combo = ttk.Combobox(
            combo_row,
            textvariable=preset_var,
            values=names,
            state='readonly',
            width=18,
            font=S.FN_X,
        )
        combo.pack(side='left', padx=(0, 4))
        self._combos[role] = combo
        if _TIP:
            ToolTip(combo, _COMBO_TIPS.get(role, ''))

        # Bind selection to load preset values into sliders
        combo.bind('<<ComboboxSelected>>', lambda e, r=role: self._load_preset(r))

        # Apply combobox field colour styling
        self._style_combobox(combo)

        # Slider rows
        specs = _SLIDER_SPECS.get(role, [])
        for param_name, label, from_, to_, resolution, _scale in specs:
            self._build_slider_row(section, role, param_name, label,
                                   from_, to_, resolution)

        # Light divider between roles
        tk.Frame(self._content, bg=getattr(S, 'BG3', S.BG2), height=1).pack(
            fill='x', padx=6, pady=(2, 0))

    def _build_slider_row(
        self,
        parent: tk.Frame,
        role: str,
        param_name: str,
        label: str,
        from_: float,
        to_: float,
        resolution: float,
    ) -> None:
        """Build a single labelled horizontal slider."""
        S = self._S

        row = tk.Frame(parent, bg=S.BG2)
        row.pack(fill='x', padx=4, pady=1)

        tk.Label(
            row,
            text=label,
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG2,
            width=14,
            anchor='w',
        ).pack(side='left')

        var = tk.DoubleVar(value=(from_ + to_) / 2.0)
        self._vars[(role, param_name)] = var

        # Value readout label — updates live as the slider moves
        readout = tk.Label(
            row,
            text=_fmt(var.get(), resolution),
            font=S.FN_X,
            fg=S.TXT_DIM,
            bg=S.BG2,
            width=6,
            anchor='e',
        )
        readout.pack(side='right')

        slider = tk.Scale(
            row,
            variable=var,
            orient='horizontal',
            from_=from_,
            to=to_,
            resolution=resolution,
            relief='flat',
            bd=0,
            highlightthickness=0,
            bg=S.BG2,
            fg=S.TXT_DIM,
            troughcolor=getattr(S, 'BG3', S.BG2),
            activebackground=getattr(S, 'CYAN', '#5ba3d0'),
            showvalue=False,
            command=lambda v, lbl=readout, res=resolution: lbl.config(
                text=_fmt(float(v), res)
            ),
        )
        slider.pack(side='left', fill='x', expand=True, padx=(2, 4))
        if _TIP:
            tip_text = _SLIDER_TIPS.get(f'{role}/{param_name}')
            if tip_text:
                ToolTip(slider, tip_text)

    # ── Interaction ──────────────────────────────────────────────────────────

    def _load_preset(self, role: str) -> None:
        """
        Load the selected preset's parameter values into the sliders.

        If '(none)' is selected the sliders are left unchanged (no reset
        is performed — the user's previous values are preserved).
        """
        preset_name = self._preset_vars[role].get()
        if preset_name == _NONE_OPTION:
            return

        preset = get_preset(role, preset_name)
        if preset is None:
            return

        specs = _SLIDER_SPECS.get(role, [])
        for param_name, _label, from_, to_, _res, scale_factor in specs:
            raw_val = getattr(preset, param_name, None)
            if raw_val is None:
                continue
            # Convert from param units to slider display units
            slider_val = raw_val * scale_factor
            # Clamp to slider range to avoid tk errors
            slider_val = max(from_, min(to_, slider_val))
            var = self._vars.get((role, param_name))
            if var is not None:
                var.set(slider_val)

    def _toggle(self) -> None:
        """Flip the collapsed/expanded state of the content area."""
        self._expanded = not self._expanded
        arrow = '▼' if self._expanded else '▶'
        self._toggle_btn.config(text=f'{arrow} TIMBRE')
        if self._expanded:
            self._content.pack(fill='x')
        else:
            self._content.pack_forget()

    # ── Param construction ───────────────────────────────────────────────────

    def _build_params(
        self,
        role: str,
        base: Optional[Union[PercussionParams, MelodicParams]],
    ) -> Optional[Union[PercussionParams, MelodicParams]]:
        """
        Build a param dataclass for *role* using slider display values,
        with the selected preset as a baseline for fields not exposed in
        the sliders.
        """
        specs = _SLIDER_SPECS.get(role, [])

        # Collect overridden values from sliders (converted back to param units)
        overrides: Dict[str, float] = {}
        for param_name, _label, _from, _to, _res, scale_factor in specs:
            var = self._vars.get((role, param_name))
            if var is not None:
                # Slider is in display units; divide by scale_factor → param units
                overrides[param_name] = var.get() / scale_factor

        if role in ('kick', 'snare', 'hihat'):
            return self._build_percussion_params(base, overrides)
        if role == 'melodic':
            return self._build_melodic_params(base, overrides)
        return None

    def _build_percussion_params(
        self,
        base: Optional[PercussionParams],
        overrides: Dict[str, float],
    ) -> PercussionParams:
        """
        Construct a PercussionParams using *base* for all non-slider fields
        and *overrides* for the slider-exposed fields.
        """
        # Start from a sensible default if there is no base preset
        if base is None:
            base = PercussionParams(
                pitch_start_hz=180.0, pitch_end_hz=50.0,
                sweep_ms=40.0, noise_amount=0.10,
                decay_ms=280.0, body_freq_hz=0.0, drive=0.0,
            )

        return PercussionParams(
            pitch_start_hz=base.pitch_start_hz,
            pitch_end_hz=overrides.get('pitch_end_hz', base.pitch_end_hz),
            sweep_ms=base.sweep_ms,
            noise_amount=overrides.get('noise_amount', base.noise_amount),
            decay_ms=overrides.get('decay_ms', base.decay_ms),
            body_freq_hz=base.body_freq_hz,
            drive=overrides.get('drive', base.drive),
        )

    def _build_melodic_params(
        self,
        base: Optional[MelodicParams],
        overrides: Dict[str, float],
    ) -> MelodicParams:
        """
        Construct a MelodicParams using *base* for all non-slider fields
        and *overrides* for the slider-exposed fields.
        """
        if base is None:
            base = MelodicParams(
                harmonic_richness=0.6, brightness=0.5,
                attack_ms=15.0, decay_ms=200.0,
                sustain_level=0.70, release_ms=300.0,
                noise_amount=0.0, drive=0.0,
            )

        return MelodicParams(
            harmonic_richness=base.harmonic_richness,
            brightness=overrides.get('brightness', base.brightness),
            attack_ms=overrides.get('attack_ms', base.attack_ms),
            decay_ms=base.decay_ms,
            sustain_level=base.sustain_level,
            release_ms=base.release_ms,
            noise_amount=base.noise_amount,
            drive=overrides.get('drive', base.drive),
        )

    # ── Styling helpers ──────────────────────────────────────────────────────

    def _style_combobox(self, combo: ttk.Combobox) -> None:
        """Apply dark-theme field colours to a combobox via ttk.Style."""
        S = self._S
        style = ttk.Style(self)
        style_name = 'Timbre.TCombobox'
        try:
            bg_input = getattr(S, 'BG_INPUT', S.BG2)
            fg       = getattr(S, 'TXT_BRT', S.TXT_DIM)
            style.configure(
                style_name,
                fieldbackground=bg_input,
                background=bg_input,
                foreground=fg,
                selectbackground=bg_input,
                selectforeground=fg,
            )
            combo.configure(style=style_name)
        except Exception:
            pass


# ── Module-level helper ───────────────────────────────────────────────────────

def _fmt(value: float, resolution: float) -> str:
    """Format a slider value for the readout label."""
    if resolution >= 1.0:
        return str(int(round(value)))
    decimal_places = max(0, -int(round(
        __import__('math').log10(resolution)
    )))
    return f'{value:.{decimal_places}f}'
