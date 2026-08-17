"""
spectral_chart.py

Generates an ASCII frequency-band allocation chart for the Production Advisor.

Each row represents one mix track; each column is a canonical frequency band.
The chart shows which band the track *owns* (full block ██) versus which band
it occupies secondarily (light block ░░), derived from hpf_hz / lpf_hz /
dominant_zone fields in the genre production-guide JSON.

Output is a list of (text, tag) pairs compatible with the advisor's A() helper
so colours are applied consistently with the rest of the advisor panel.
"""

import re
from typing import List, Tuple, Dict, Any


def _parse_hz(value, default: int) -> int:
    """
    Safely convert a frequency value to int.

    Handles plain numbers as well as sweep-notation strings like '400->30'
    that appear in some genre JSON files (the first integer in the string is
    used as the representative frequency).

    Args:
        value:   Raw value from the genre JSON (int, float, or str).
        default: Fallback when the value is falsy or contains no digits.

    Returns:
        int: Parsed frequency in Hz, or *default* if parsing fails.
    """
    if not value:
        return default
    # Already a number — fast path
    if isinstance(value, (int, float)):
        return int(value)
    # String path: extract the first run of digits (e.g. '400->30' → 400)
    m = re.search(r'\d+', str(value))
    return int(m.group()) if m else default

# Canonical bands: (label, lo_hz, hi_hz)
_BANDS: List[Tuple[str, int, int]] = [
    ('SUB',    20,    80),
    ('BASS',   80,   250),
    ('LO-MID', 250,  2000),
    ('MID',   2000,  5000),
    ('HI-MID',5000, 10000),
    ('AIR',  10000, 20000),
]

_BAR_WIDTH = 6   # characters per band cell

_DOMINANT_ZONE_KEYWORDS: Dict[str, int] = {
    # maps a substring of dominant_zone text to the band index it implies
    'sub':     0,
    '808':     0,
    'bass':    1,
    'lo-mid':  2,
    'low-mid': 2,
    'mid':     3,
    'presence':3,
    'hi-mid':  4,
    'high-mid':4,
    'air':     5,
    'brillian':5,
}


def _band_mask(hpf: int, lpf: int, dominant_idx: int) -> List[str]:
    """
    Return one character per band: '██' for active, '░░' for dominant, '  ' for absent.
    hpf / lpf define the active range; dominant_idx marks the owned centre.
    """
    cells = []
    for idx, (_lbl, lo, hi) in enumerate(_BANDS):
        if hi <= hpf or lo >= lpf:
            cells.append('  ')          # completely outside range
        elif idx == dominant_idx:
            cells.append('██')          # owned zone
        else:
            cells.append('░░')          # occupied but not dominant
    return cells


def _infer_dominant(dominant_zone_text: str, hpf: int, lpf: int) -> int:
    """Guess the dominant band index from the dominant_zone description string."""
    low = dominant_zone_text.lower()
    for keyword, idx in _DOMINANT_ZONE_KEYWORDS.items():
        if keyword in low:
            return idx
    # fallback: pick the band with the most overlap
    best_idx, best_overlap = 0, 0
    for idx, (_lbl, lo, hi) in enumerate(_BANDS):
        overlap = max(0, min(hi, lpf) - max(lo, hpf))
        if overlap > best_overlap:
            best_overlap, best_idx = overlap, idx
    return best_idx


def build_spectral_chart(
    freq_data: Dict[str, Any],
    stereo_data: Dict[str, Any],
) -> List[Tuple[str, str]]:
    """
    Build the spectral allocation chart rows.

    Parameters
    ----------
    freq_data    : gdata['frequency_allocation'] dict  {track_name: {hpf_hz, lpf_hz, dominant_zone}}
    stereo_data  : gdata['stereo_field'] dict          {track_name: {width_pct, class}}

    Returns
    -------
    List of (text, advisor_tag) pairs ready for A() calls.
    """
    if not freq_data:
        return []

    lines: List[Tuple[str, str]] = []

    # Header
    lines.append(('\n  SPECTRAL ALLOCATION MAP\n', 'section'))

    # Band header row
    band_row = '  ' + f"{'TRACK':<10}  "
    for lbl, lo, hi in _BANDS:
        band_row += f'{lbl:^{_BAR_WIDTH}} '
    lines.append((band_row + '\n', 'lbl'))

    # Hz range subrow
    hz_row = '  ' + ' ' * 12
    for _lbl, lo, hi in _BANDS:
        tag = f'{lo//1000}k' if lo >= 1000 else str(lo)
        tag += '-'
        tag += f'{hi//1000}k' if hi >= 1000 else str(hi)
        hz_row += f'{tag:^{_BAR_WIDTH}} '
    lines.append((hz_row + '\n', 'dim'))

    lines.append(('  ' + '─' * (12 + (_BAR_WIDTH + 1) * len(_BANDS)) + '\n', 'dim'))

    for track, fdata in freq_data.items():
        hpf = _parse_hz(fdata.get('hpf_hz', 20), default=20)
        lpf = _parse_hz(fdata.get('lpf_hz', 20000), default=20000)
        dom_text = fdata.get('dominant_zone', '')
        dom_idx = _infer_dominant(dom_text, hpf, lpf)
        cells = _band_mask(hpf, lpf, dom_idx)

        sdata = stereo_data.get(track, {})
        width = sdata.get('width_pct', '')
        stereo_cls = sdata.get('class', '')
        width_str = f'{width}% {stereo_cls}'.strip() if width else stereo_cls

        track_label = f'{track.upper():<10}'
        bar = ' '.join(f'{c:^{_BAR_WIDTH}}' for c in cells)

        lines.append((f'  {track_label}  ', 'lbl'))
        # colour the dominant cell differently — we emit the whole bar as one string
        # and rely on the 'value' tag for active bands; a simpler approach keeps
        # the bar as a single tagged run since the Text widget tags by range.
        lines.append((bar, 'value'))
        if width_str:
            lines.append((f'  {width_str}', 'dim'))
        lines.append(('\n', 'dim'))

    return lines
