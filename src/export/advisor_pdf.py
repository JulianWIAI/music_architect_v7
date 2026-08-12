"""
src.export.advisor_pdf
-----------------------
Generates a printable A4 PDF production guide from the advisor's current state.

Dependency
----------
fpdf2 >= 2.7.0  (listed in requirements.txt — pip install fpdf2)

If fpdf2 is not installed, export() automatically falls back to a
formatted .txt file so the workflow is never blocked.

Data model
----------
AdvisorPDFExporter receives pre-assembled dicts already computed by
_update_advisor() in app.py — it does NOT reload any JSON files itself.
This keeps the class stateless, independently testable, and free of
app-layer imports.

PDF layout  (A4 portrait, 15 mm margins each side, 180 mm usable width)
------------------------------------------------------------------------
  1. Title block    — genre, BPM, key, generation date
  2. Palette        — name, branch, BDRA code, kick description
  3. FX Variant     — active timbral flavour label and description
  4. Instruments    — GM table with one-line sound-character descriptions
  5. BPM targets    — bucket, allowed scales, PLR target, LRA
  6. Gain staging   — RMS / peak / CF per track
  7. Effect chains  — base chain with merged variant + instrument deltas
  8. Frequency      — HPF / LPF / zone / stereo width per track
  9. Parallel comp  — New York compression settings
 10. M/S mastering  — mid-side insert parameters

Colour scheme (light background, optimised for printing)
---------------------------------------------------------
  Dark navy    — main title
  Medium blue  — section headers
  Near-black   — body text
  Grey         — secondary / parameter values
  Green        — active variant / instrument adjustments
  Orange       — bypassed / disabled slots
"""

from __future__ import annotations

import pathlib
from datetime import date as _date
from typing import Dict, List, Optional, Tuple

try:
    from fpdf import FPDF
    _FPDF_OK = True
except ImportError:
    FPDF   = None   # type: ignore
    _FPDF_OK = False

from src.composition.gm_descriptions import get_description as _gm_desc

# ── Page geometry ─────────────────────────────────────────────────────────────
_MARGIN = 15            # mm, all four sides
_PAGE_W = 180           # mm, usable width (210 − 2×15)
_LINE_H = 5             # mm, standard body line height

# ── Colour palette (RGB) ──────────────────────────────────────────────────────
_C_TITLE   = (15,  35,  80)    # dark navy — main heading
_C_SECTION = (30,  90, 170)    # blue — section headings
_C_BODY    = (20,  20,  20)    # near-black — body text
_C_DIM     = (110, 110, 110)   # grey — secondary / params
_C_OK      = (25, 125,  55)    # green — adjustments active
_C_WARN    = (175,  75,  20)   # orange — bypassed slots
_C_RULE    = (190, 195, 210)   # light blue-grey — separator rules


def _safe(text: str) -> str:
    """Replace non-Latin-1 Unicode characters with ASCII equivalents.

    fpdf2 uses Latin-1 encoding with the built-in fonts (Helvetica, Courier,
    Times).  Characters outside that range raise an encoding error, so we
    normalise them here rather than require a custom TTF font.
    """
    return (
        str(text)
        .replace('→', '->')   # →
        .replace('←', '<-')   # ←
        .replace('≠', '!=')   # ≠
        .replace('≤', '<=')   # ≤
        .replace('≥', '>=')   # ≥
        .replace('…', '...')  # …
        .replace('—', '--')   # —  em-dash
        .replace('–', '-')    # –  en-dash
        .replace('▶', '>')    # ▶
        .replace('⬇', 'v')    # ⬇
        .replace('’', "'")    # '
        .replace('‘', "'")    # '
        .replace('“', '"')    # "
        .replace('”', '"')    # "
    )


class _PagedPDF(FPDF if _FPDF_OK else object):
    """FPDF subclass that adds a page-number footer to every page."""

    def footer(self) -> None:
        self.set_y(-12)
        self.set_x(self.l_margin)   # defensive: set_y resets X, but be explicit
        self.set_font('Helvetica', 'I', 7)
        self.set_text_color(*_C_DIM)
        self.cell(
            0, 5,
            text=f'Music Architect Production Guide  |  page {self.page_no()}',
            align='C',
        )


class AdvisorPDFExporter:
    """
    Converts production advisor data to a printable A4 PDF (or .txt fallback).

    Parameters
    ----------
    config : dict
        Composition config — must contain 'genre', 'bpm', 'key'.
    palette : dict | None
        Active palette dict (name, branch, instruments, chain_delta, …).
    genre_data : dict
        Parsed genre JSON (tracks, bpm_buckets, frequency_allocation, …).
    shared_data : dict
        Parsed shared.json (clip_gain_targets).
    variant_id : str
        Active FX variant id — 'bright', 'neutral', or 'dark'.
    variant_record : dict
        Full variant record from fx_variants.json (label, description).
    merged_delta : dict
        Three-layer merged chain delta (palette + variant + instrument).
    track_instruments : dict
        {track_name: gm_program_int} for all active tracks.
    generated_at : str | None
        ISO date string; defaults to today if omitted.
    """

    def __init__(
        self,
        *,
        config:           dict,
        palette:          Optional[dict],
        genre_data:       dict,
        shared_data:      dict,
        variant_id:       str,
        variant_record:   dict,
        merged_delta:     dict,
        track_instruments: Dict[str, int],
        generated_at:     Optional[str] = None,
    ) -> None:
        self._cfg    = config
        self._pal    = palette
        self._gdata  = genre_data
        self._shared = shared_data
        self._vid    = variant_id
        self._var    = variant_record
        self._delta  = merged_delta
        self._tinsts = track_instruments
        self._today  = generated_at or _date.today().isoformat()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def export(self, output_path: str) -> bool:
        """
        Write the production guide to *output_path*.

        Tries PDF first; falls back to a .txt file if fpdf2 is missing or
        if the PDF render raises an unexpected exception.

        Returns True on success, False on total failure.
        """
        if _FPDF_OK:
            try:
                return self._export_pdf(output_path)
            except Exception as exc:
                print(f"[AdvisorPDFExporter] PDF render error: {exc}")
                # Fall through to text fallback
        txt_path = str(pathlib.Path(output_path).with_suffix('.txt'))
        return self._export_txt(txt_path)

    # ------------------------------------------------------------------
    # PDF rendering
    # ------------------------------------------------------------------

    def _export_pdf(self, path: str) -> bool:
        pdf = _PagedPDF(orientation='P', unit='mm', format='A4')
        pdf.set_margins(_MARGIN, _MARGIN, _MARGIN)
        pdf.set_auto_page_break(auto=True, margin=_MARGIN + 8)  # 23 mm: 15 mm margin + 8 mm footer clearance
        pdf.add_page()

        self._title_block(pdf)
        self._palette_section(pdf)
        self._instruments_section(pdf)
        self._bpm_section(pdf)
        self._gain_section(pdf)
        self._effects_section(pdf)
        self._frequency_section(pdf)
        self._parallel_section(pdf)
        self._ms_section(pdf)

        pdf.output(path)
        return True

    # ── Section: title block ──────────────────────────────────────────

    def _title_block(self, pdf: 'FPDF') -> None:
        c     = self._cfg
        genre = c.get('genre', '').upper()
        bpm   = c.get('bpm', '')
        key   = c.get('key', '')

        # Main title
        pdf.set_font('Helvetica', 'B', 18)
        pdf.set_text_color(*_C_TITLE)
        pdf.cell(0, 10, text='MUSIC ARCHITECT -- PRODUCTION GUIDE')
        pdf.ln()

        # Subtitle line
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(*_C_DIM)
        subtitle = f'Genre: {genre}   |   BPM: {bpm}   |   Key: {key}   |   {self._today}'
        pdf.cell(0, 6, text=_safe(subtitle))
        # ln() with no argument advances Y by the last cell height (6 mm).
        # ln(2) would only move 2 mm — placing the rule inside the subtitle area.
        pdf.ln()

        self._rule(pdf)

    # ── Section: palette + FX variant ────────────────────────────────

    def _palette_section(self, pdf: 'FPDF') -> None:
        pal = self._pal
        if not pal:
            return

        self._section_head(pdf, 'PALETTE & FX VARIANT')

        self._kv(pdf, 'Palette',
                 f"{pal.get('name', '')}  Branch {pal.get('branch', '')}  {pal.get('kick_code', '')}")
        self._kv(pdf, 'Kick', pal.get('kick_desc', ''))

        v_label = self._var.get('label', self._vid.upper())
        v_desc  = self._var.get('description', '')
        self._kv(pdf, 'FX Variant',
                 f"{v_label} -- {v_desc}" if v_desc else v_label,
                 vc=_C_OK)

        pdf.ln(2)

    # ── Section: instruments ──────────────────────────────────────────

    def _instruments_section(self, pdf: 'FPDF') -> None:
        pal = self._pal
        if not pal:
            return

        self._section_head(pdf, 'INSTRUMENTS')

        # Column widths (mm): track 28, gm 14, name 62, code 42, rest pad
        col = (28, 14, 62, 40)

        # Header row
        pdf.set_font('Helvetica', 'B', 8)
        pdf.set_text_color(*_C_DIM)
        for txt, w in zip(('TRACK', 'GM', 'NAME', 'CODE'), col):
            pdf.cell(w, _LINE_H, text=txt)
        pdf.ln()
        self._thin_rule(pdf)

        for track, inst in pal.get('instruments', {}).items():
            gm   = inst.get('gm', 0)
            name = inst.get('name', '')
            code = inst.get('code', '')
            desc = _safe(_gm_desc(gm))

            # Reset X to the left margin before every data row.
            # multi_cell() leaves X at its *start* position (the indented
            # description offset), so without this reset every subsequent
            # track name is drawn from that indented position rather than
            # the TRACK column, pushing it progressively to the right.
            pdf.set_x(pdf.l_margin)

            # Data row: track | gm | name | code
            pdf.set_font('Helvetica', 'B', 8)
            pdf.set_text_color(*_C_BODY)
            pdf.cell(col[0], _LINE_H, text=_safe(track.upper()))
            pdf.set_font('Courier', '', 8)
            pdf.set_text_color(*_C_DIM)
            pdf.cell(col[1], _LINE_H, text=str(gm))
            pdf.set_text_color(*_C_BODY)
            pdf.cell(col[2], _LINE_H, text=_safe(name))
            pdf.set_text_color(*_C_OK)
            pdf.cell(col[3], _LINE_H, text=_safe(code))
            pdf.ln()

            # Description sub-row — indented past the TRACK + GM columns
            if desc:
                pdf.set_x(_MARGIN + col[0] + col[1])
                pdf.set_font('Helvetica', 'I', 7)
                pdf.set_text_color(*_C_DIM)
                pdf.multi_cell(
                    _PAGE_W - col[0] - col[1],
                    4,
                    text=desc,
                )

            pdf.ln(1)   # breathing room between instrument rows

    # ── Section: BPM bucket + scale targets ──────────────────────────

    def _bpm_section(self, pdf: 'FPDF') -> None:
        gdata = self._gdata
        bpm   = self._cfg.get('bpm', 0)
        if not gdata:
            return

        self._section_head(pdf, 'BPM TARGETS')

        for bkt in gdata.get('bpm_buckets', []):
            lo, hi = bkt.get('bpm_range', [0, 9999])
            if lo <= bpm <= hi:
                self._kv(pdf, 'Bucket',
                         f"{bkt['id']}  (anchor {bkt.get('anchor_bpm', '?')} BPM)")
                self._kv(pdf, 'Scales',
                         ', '.join(bkt.get('key_families', [])))
                break

        self._kv(pdf, 'PLR Target',
                 f"{gdata.get('plr_target_db', '?')} dB")
        self._kv(pdf, 'LRA',
                 f"{gdata.get('lra_target_lu', '?')} LU")
        pdf.ln(2)

    # ── Section: gain staging ─────────────────────────────────────────

    def _gain_section(self, pdf: 'FPDF') -> None:
        cgt = self._shared.get('clip_gain_targets', {})
        if not cgt:
            return

        self._section_head(pdf, 'GAIN STAGING TARGETS')

        # Map genre to its loudness-curve delta key from shared.json:
        # pop_delta = bright/compressed, hiphop_delta = punchy/loud, cine_delta = wide dynamic range.
        genre = self._cfg.get('genre', '')
        delta_map = {
            'pop': 'pop_delta', 'jpop': 'pop_delta',
            'edm': 'pop_delta', 'house': 'pop_delta',
            'hiphop': 'hiphop_delta', 'trap': 'hiphop_delta',
            'phonk': 'hiphop_delta', 'techno': 'hiphop_delta',
            'dnb': 'hiphop_delta',
            'cinematic': 'cine_delta', 'classical': 'cine_delta',
        }
        dk = delta_map.get(genre, 'pop_delta')   # unknown genres fall back to pop_delta

        # Column widths: track 32, rms 20, peak 20, cf 20
        col = (32, 24, 24, 20)

        pdf.set_font('Helvetica', 'B', 8)
        pdf.set_text_color(*_C_DIM)
        for txt, w in zip(('TRACK', 'RMS (dBFS)', 'PEAK (dBFS)', 'CF'), col):
            pdf.cell(w, _LINE_H, text=txt)
        pdf.ln()
        self._thin_rule(pdf)

        for track, vals in cgt.items():
            if track == 'note':
                continue
            rms     = vals.get('rms_dbfs', -18)
            peak    = vals.get('peak_ceiling_dbfs', -6)
            cf      = vals.get('cf_db', 12)   # crest factor (peak-to-RMS, dB); 12 dB is typical for electronic/MIDI audio
            rms_eff = rms + vals.get(dk, 0)

            pdf.set_font('Helvetica', 'B', 8)
            pdf.set_text_color(*_C_BODY)
            pdf.cell(col[0], _LINE_H, text=_safe(track.upper()))
            pdf.set_font('Courier', '', 8)
            pdf.set_text_color(*_C_SECTION)
            pdf.cell(col[1], _LINE_H, text=f'{rms_eff:.1f}')
            pdf.set_text_color(*_C_OK)
            pdf.cell(col[2], _LINE_H, text=f'{peak:.1f}')
            pdf.set_text_color(*_C_DIM)
            pdf.cell(col[3], _LINE_H, text=f'{cf} dB')
            pdf.ln()

        pdf.ln(2)

    # ── Section: effect chains ────────────────────────────────────────

    def _effects_section(self, pdf: 'FPDF') -> None:
        tracks_data = self._gdata.get('tracks', {})
        if not tracks_data:
            return

        v_label = self._var.get('label', self._vid.upper())
        v_desc  = self._var.get('description', '')
        self._section_head(
            pdf,
            f'EFFECT CHAINS  [{v_label}]' + (f' -- {v_desc}' if v_desc else ''),
        )

        for tname, tdata in tracks_data.items():
            chain = tdata.get('effect_chain', [])
            if not chain:
                continue

            delta_slots = {
                d['slot']: d for d in self._delta.get(tname, [])
            }

            # Track sub-header
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_text_color(*_C_BODY)
            pdf.cell(0, _LINE_H, text=_safe(tname.upper()))
            pdf.ln()

            role = tdata.get('role', '')
            if role:
                pdf.set_font('Helvetica', 'I', 7)
                pdf.set_text_color(*_C_DIM)
                pdf.cell(0, 4, text=_safe(role))
                pdf.ln()

            # Chain slots
            for slot in chain:
                sn = slot['slot']
                d  = delta_slots.get(sn)
                effect = _safe(slot.get('effect', ''))
                params = _safe(slot.get('params', ''))

                pdf.set_font('Courier', '', 8)
                pdf.set_x(_MARGIN + 4)   # slight indent for slots

                if d is None:
                    # Unmodified slot
                    pdf.set_text_color(*_C_DIM)
                    pdf.cell(10, 4, text=f'[{sn}]')
                    pdf.set_text_color(*_C_BODY)
                    pdf.cell(55, 4, text=effect)
                    pdf.set_text_color(*_C_DIM)
                    pdf.multi_cell(_PAGE_W - 65 - 4, 4, text=params)

                elif d['action'] == 'disable':
                    pdf.set_text_color(*_C_DIM)
                    pdf.cell(10, 4, text=f'[{sn}]')
                    pdf.set_text_color(*_C_WARN)
                    pdf.cell(55, 4, text='[BYPASS]')
                    pdf.multi_cell(
                        _PAGE_W - 65 - 4, 4,
                        text=_safe(d.get('note', '')),
                    )

                elif d['action'] == 'adjust':
                    pdf.set_text_color(*_C_DIM)
                    pdf.cell(10, 4, text=f'[{sn}]')
                    pdf.set_text_color(*_C_BODY)
                    pdf.cell(55, 4, text=effect)
                    pdf.set_text_color(*_C_OK)
                    pdf.multi_cell(
                        _PAGE_W - 65 - 4, 4,
                        text=_safe(d.get('note', '')),
                    )

                elif d['action'] == 'swap':
                    new_fx = _safe(d.get('effect', effect))
                    pdf.set_text_color(*_C_DIM)
                    pdf.cell(10, 4, text=f'[{sn}]')
                    pdf.set_text_color(*_C_OK)
                    pdf.cell(55, 4, text=new_fx)
                    pdf.multi_cell(
                        _PAGE_W - 65 - 4, 4,
                        text=_safe(d.get('note', '')),
                    )

            # 'add' entries (extra slots beyond the base chain)
            for ad in self._delta.get(tname, []):
                if ad['action'] == 'add':
                    pdf.set_x(_MARGIN + 4)
                    pdf.set_font('Courier', '', 8)
                    pdf.set_text_color(*_C_DIM)
                    pdf.cell(10, 4, text=f'[{ad["slot"]}+]')
                    pdf.set_text_color(*_C_OK)
                    pdf.cell(55, 4, text=_safe(ad.get('effect', '')))
                    pdf.multi_cell(
                        _PAGE_W - 65 - 4, 4,
                        text=_safe(ad.get('note', '')),
                    )

            pdf.ln(1)

        pdf.ln(1)

    # ── Section: frequency allocation ─────────────────────────────────

    def _frequency_section(self, pdf: 'FPDF') -> None:
        freq = self._gdata.get('frequency_allocation', {})
        sf   = self._gdata.get('stereo_field', {})
        if not freq:
            return

        self._section_head(pdf, 'FREQUENCY ALLOCATION & STEREO FIELD')

        col = (28, 16, 16, 54, 36)   # track, hpf, lpf, zone, width

        pdf.set_font('Helvetica', 'B', 8)
        pdf.set_text_color(*_C_DIM)
        for txt, w in zip(('TRACK', 'HPF', 'LPF', 'ZONE', 'WIDTH'), col):
            pdf.cell(w, _LINE_H, text=txt)
        pdf.ln()
        self._thin_rule(pdf)

        for tname, fdata in freq.items():
            hpf   = str(fdata.get('hpf_hz', '--'))
            lpf   = str(fdata.get('lpf_hz', '--')) if fdata.get('lpf_hz') else '--'
            zone  = fdata.get('dominant_zone', '')
            sdata = sf.get(tname, {})
            wp    = sdata.get('width_pct', '--')
            cls   = sdata.get('class', '')
            width = f'{wp}% {cls}'.strip() if cls and wp != '--' else str(wp)

            pdf.set_font('Helvetica', 'B', 8)
            pdf.set_text_color(*_C_BODY)
            pdf.cell(col[0], _LINE_H, text=_safe(tname.upper()))
            pdf.set_font('Courier', '', 8)
            pdf.set_text_color(*_C_SECTION)
            pdf.cell(col[1], _LINE_H, text=hpf)
            pdf.set_text_color(*_C_DIM)
            pdf.cell(col[2], _LINE_H, text=lpf)
            pdf.set_text_color(*_C_BODY)
            pdf.cell(col[3], _LINE_H, text=_safe(zone[:30]))
            pdf.set_text_color(*_C_OK)
            pdf.cell(col[4], _LINE_H, text=_safe(width))
            pdf.ln()

        pdf.ln(2)

    # ── Section: parallel compression ─────────────────────────────────

    def _parallel_section(self, pdf: 'FPDF') -> None:
        pc = self._gdata.get('parallel_compression', {})
        if not pc:
            return

        self._section_head(pdf, 'PARALLEL COMPRESSION (New York)')
        self._kv(pdf, 'Wet blend',  f"{pc.get('wet_blend_pct', '?')} %")
        self._kv(pdf, 'Ratio',      str(pc.get('ratio', '?')))
        self._kv(pdf, 'Threshold',  f"{pc.get('threshold_dbfs', '?')} dBFS")
        self._kv(pdf, 'Release',    f"{pc.get('release_formula', '?')} ms")
        pdf.ln(2)

    # ── Section: M/S mastering ────────────────────────────────────────

    def _ms_section(self, pdf: 'FPDF') -> None:
        ms = self._gdata.get('ms_mastering', {})
        if not ms:
            return

        self._section_head(pdf, 'M/S MASTERING INSERT')
        status = ms.get('status', 'N/A')
        self._kv(pdf, 'Status', status,
                 vc=_C_WARN if status == 'MANDATORY' else _C_DIM)

        if status in ('MANDATORY', 'OPTIONAL'):
            self._kv(pdf, 'Side HPF',
                     f"{ms.get('side_hpf_hz', '?')} Hz  {ms.get('side_hpf_slope', '')}")
            self._kv(pdf, 'Side shelf',
                     f"+{ms.get('side_shelf_db', '?')} dB @ {ms.get('side_shelf_hz', '?')} Hz")
            self._kv(pdf, 'Resulting width',
                     f"{ms.get('resulting_width_pct', '?')} %")

    # ------------------------------------------------------------------
    # Formatting helpers (all take pdf as first argument)
    # ------------------------------------------------------------------

    def _section_head(self, pdf: 'FPDF', title: str) -> None:
        """Bold blue section heading with a horizontal rule beneath it."""
        pdf.ln(1)
        pdf.set_x(pdf.l_margin)     # reset X so cell(w=_PAGE_W) always has full room
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_text_color(*_C_SECTION)
        pdf.cell(_PAGE_W, 6, text=_safe(title))   # explicit width, not 0
        pdf.ln()
        self._rule(pdf)

    def _rule(self, pdf: 'FPDF') -> None:
        """Full-width separator rule in the rule colour."""
        y = pdf.get_y()
        pdf.set_draw_color(*_C_RULE)
        pdf.set_line_width(0.4)
        pdf.line(_MARGIN, y, _MARGIN + _PAGE_W, y)
        pdf.ln(2)

    def _thin_rule(self, pdf: 'FPDF') -> None:
        """Lighter, thinner rule used between table header and rows."""
        y = pdf.get_y()
        pdf.set_draw_color(*_C_RULE)
        pdf.set_line_width(0.2)
        pdf.line(_MARGIN, y, _MARGIN + _PAGE_W, y)
        pdf.ln(1)

    def _kv(
        self,
        pdf:   'FPDF',
        label: str,
        value: str,
        vc:    Tuple[int, int, int] = None,
    ) -> None:
        """Key–value row: bold grey label + monospace body value.

        Always resets X to l_margin first so multi_cell's width arithmetic
        is correct regardless of what the previous draw call left the cursor at.
        multi_cell(0, h) computes w = page_w - r_margin - x, so if x has
        drifted past l_margin+40, the available space can become tiny and
        fpdf2 raises 'Not enough horizontal space to render a single character'.
        """
        pdf.set_x(pdf.l_margin)     # anchor X before computing the value column
        pdf.set_font('Helvetica', 'B', 8)
        pdf.set_text_color(*_C_DIM)
        pdf.cell(40, _LINE_H, text=_safe(label))
        pdf.set_font('Courier', '', 9)
        pdf.set_text_color(*(vc or _C_BODY))
        pdf.multi_cell(_PAGE_W - 40, _LINE_H, text=_safe(value))   # explicit width

    # ------------------------------------------------------------------
    # Plain-text fallback
    # ------------------------------------------------------------------

    def _export_txt(self, path: str) -> bool:
        """
        Write a formatted plain-text production guide to *path*.

        Used when fpdf2 is not installed.  Produces the same information
        as the PDF in a readable monospace layout.
        """
        lines: List[str] = []

        def h(text: str) -> None:
            lines.append('')
            lines.append('=' * 72)
            lines.append(f'  {text}')
            lines.append('=' * 72)

        def kv(label: str, value: str) -> None:
            lines.append(f'  {label:<16}{value}')

        def rule() -> None:
            lines.append('-' * 72)

        # Title
        c     = self._cfg
        genre = c.get('genre', '').upper()
        bpm   = c.get('bpm', '')
        key   = c.get('key', '')
        lines.append('=' * 72)
        lines.append('  MUSIC ARCHITECT -- PRODUCTION GUIDE')
        lines.append(f'  Genre: {genre}  |  BPM: {bpm}  |  Key: {key}  |  {self._today}')
        lines.append('=' * 72)

        # Palette
        pal = self._pal
        if pal:
            h('PALETTE & FX VARIANT')
            kv('Palette', f"{_safe(pal.get('name', ''))}  Branch {pal.get('branch', '')}  {pal.get('kick_code', '')}")
            kv('Kick', _safe(pal.get('kick_desc', '')))
            v_label = _safe(self._var.get('label', self._vid.upper()))
            v_desc  = _safe(self._var.get('description', ''))
            kv('FX Variant', f"{v_label} -- {v_desc}" if v_desc else v_label)

        # Instruments
        if pal:
            h('INSTRUMENTS')
            lines.append(f"  {'TRACK':<10} {'GM':>4}  {'NAME':<24} CODE")
            rule()
            for track, inst in pal.get('instruments', {}).items():
                gm   = inst.get('gm', 0)
                name = inst.get('name', '')
                code = inst.get('code', '')
                desc = _safe(_gm_desc(gm))
                lines.append(f"  {track.upper():<10} {gm:>4}  {name:<24} {code}")
                lines.append(f"  {'':10} {'':4}  {desc}")

        # BPM targets
        gdata = self._gdata
        if gdata:
            h('BPM TARGETS')
            bpm_v = self._cfg.get('bpm', 0)
            for bkt in gdata.get('bpm_buckets', []):
                lo, hi = bkt.get('bpm_range', [0, 9999])
                if lo <= bpm_v <= hi:
                    kv('Bucket', f"{bkt['id']}  (anchor {bkt.get('anchor_bpm', '?')} BPM)")
                    kv('Scales', ', '.join(bkt.get('key_families', [])))
                    break
            kv('PLR Target', f"{gdata.get('plr_target_db', '?')} dB")
            kv('LRA', f"{gdata.get('lra_target_lu', '?')} LU")

        # Gain staging
        cgt = self._shared.get('clip_gain_targets', {})
        if cgt:
            h('GAIN STAGING TARGETS')
            lines.append(f"  {'TRACK':<12} {'RMS':>7} {'PEAK':>7} {'CF':>5}")
            rule()
            dk = {
                'pop': 'pop_delta', 'jpop': 'pop_delta',
                'edm': 'pop_delta', 'house': 'pop_delta',
                'hiphop': 'hiphop_delta', 'trap': 'hiphop_delta',
                'phonk': 'hiphop_delta', 'techno': 'hiphop_delta',
                'dnb': 'hiphop_delta',
                'cinematic': 'cine_delta', 'classical': 'cine_delta',
            }.get(self._cfg.get('genre', ''), 'pop_delta')
            for track, vals in cgt.items():
                if track == 'note':
                    continue
                rms     = vals.get('rms_dbfs', -18) + vals.get(dk, 0)
                peak    = vals.get('peak_ceiling_dbfs', -6)
                cf      = vals.get('cf_db', 12)
                lines.append(
                    f"  {track.upper():<12} {rms:>6.1f} {peak:>6.1f} {cf:>3}dB"
                )

        # Effect chains
        tracks_data = gdata.get('tracks', {}) if gdata else {}
        if tracks_data:
            v_label = self._var.get('label', self._vid.upper())
            h(f'EFFECT CHAINS  [{v_label}]')
            for tname, tdata in tracks_data.items():
                chain = tdata.get('effect_chain', [])
                if not chain:
                    continue
                lines.append(f'\n  {tname.upper()}')
                ds = {d['slot']: d for d in self._delta.get(tname, [])}
                for slot in chain:
                    sn     = slot['slot']
                    d      = ds.get(sn)
                    fx     = _safe(slot.get('effect', ''))
                    params = _safe(slot.get('params', ''))
                    if d is None:
                        lines.append(f"    [{sn}] {fx:<28} {params}")
                    elif d['action'] == 'disable':
                        lines.append(f"    [{sn}] [BYPASS]                     {_safe(d.get('note', ''))}")
                    elif d['action'] == 'adjust':
                        lines.append(f"    [{sn}] {fx:<28} * {_safe(d.get('note', ''))}")
                    elif d['action'] == 'swap':
                        lines.append(f"    [{sn}] {_safe(d.get('effect', fx)):<28} * {_safe(d.get('note', ''))}")
                for ad in self._delta.get(tname, []):
                    if ad['action'] == 'add':
                        lines.append(f"    [{ad['slot']}+] {_safe(ad.get('effect', '')):<28} + {_safe(ad.get('note', ''))}")

        try:
            # utf-8-sig writes a UTF-8 BOM so Windows Notepad auto-detects
            # the encoding instead of interpreting multi-byte chars as CP1252.
            pathlib.Path(path).write_text('\n'.join(lines), encoding='utf-8-sig')
            return True
        except Exception as exc:
            print(f"[AdvisorPDFExporter] TXT write error: {exc}")
            return False
