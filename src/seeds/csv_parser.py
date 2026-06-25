"""
CSV parsing and musical analysis helpers for the seed-building pipeline.

Handles reading the three-file CSV format produced by the analysis toolchain:
  <song_id>_time_data.csv   — BPM, key, time signature, duration
  <song_id>_chords.csv      — chord change events
  <song_id>_timeline.csv    — per-frame instrument intensities + chord labels
"""

import csv
from collections import Counter, defaultdict
from typing import List, Dict


# ─── CSV PARSERS ──────────────────────────────────────────────────────────────

def parse_time_data_csv(filepath: str) -> dict:
    """Parse a time-data CSV into a flat parameter dict."""
    data = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            param = row.get('parameter', '')
            value = row.get('value', '')
            try:
                data[param] = value if '/' in value else float(value)
            except (ValueError, TypeError):
                data[param] = value
    return data


def parse_chords_csv(filepath: str) -> List[dict]:
    """Parse a chords CSV into a list of chord-event dicts."""
    chords = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f, delimiter=';'):
            try:
                chords.append({
                    'start': float(row['start_time']),
                    'end': float(row['end_time']),
                    'chord': row['chord'],
                    'root': row['root'],
                    'quality': row['quality'],
                })
            except (ValueError, KeyError):
                continue
    return chords


def parse_timeline_csv(filepath: str) -> List[dict]:
    """Parse a timeline CSV into a list of per-frame event dicts."""
    events = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f, delimiter=';'):
            try:
                events.append({
                    'time': float(row['time_seconds']),
                    'chord': row['chord'],
                    'chord_root': row['chord_root'],
                    'chord_quality': row['chord_quality'],
                    'kick': float(row.get('kick', 0)),
                    'snare': float(row.get('snare', 0)),
                    'hihat': float(row.get('hihat', 0)),
                    'bass': float(row.get('bass', 0)),
                    'synth': float(row.get('synth', 0)),
                    'pad': float(row.get('pad', 0)),
                    'harmonic_ratio': float(row.get('harmonic_ratio', 0)),
                    'dominant_instrument': row.get('dominant_instrument', 'bass'),
                })
            except (ValueError, KeyError):
                continue
    return events


# ─── ANALYSIS HELPERS ─────────────────────────────────────────────────────────

def build_chord_transitions(chords: List[dict]) -> dict:
    """Build a normalised chord-to-chord transition probability matrix."""
    trans = defaultdict(Counter)
    for i in range(len(chords) - 1):
        trans[chords[i]['chord']][chords[i + 1]['chord']] += 1
    result = {}
    for ch, fol in trans.items():
        total = sum(fol.values())
        result[ch] = {k: v / total for k, v in fol.items()}
    return result


def extract_instrument_patterns(timeline: List[dict], bpm: float) -> dict:
    """Quantise raw timeline events into 16th-note hit dicts per instrument."""
    if not timeline or bpm <= 0:
        return {}
    bd = 60.0 / bpm
    sixteenth = bd / 4.0
    instruments = ['kick', 'snare', 'hihat', 'bass', 'synth', 'pad']
    patterns = {}
    bar_len = bd * 4
    for inst in instruments:
        hits = [
            {
                'time': round(round(ev['time'] / sixteenth) * sixteenth, 4),
                'velocity': round(min(1.0, ev.get(inst, 0)), 3),
            }
            for ev in timeline if ev.get(inst, 0) > 0.02
        ]
        if hits:
            early = [h for h in hits if h['time'] < bar_len * 4]
            phits = [
                {'pos': round((h['time'] % bar_len) / bd, 4), 'vel': h['velocity']}
                for h in early
            ]
            patterns[inst] = {
                'hits': phits[:64],
                'density': len(hits) / max(1, len(timeline)),
                'avg_velocity': round(
                    sum(h['velocity'] for h in hits) / max(1, len(hits)), 3
                ),
            }
        else:
            patterns[inst] = {'hits': [], 'density': 0.0, 'avg_velocity': 0.0}
    return patterns


def compute_timeline_stats(timeline: List[dict], chords: List[dict]) -> dict:
    """Compute aggregate statistics from a song's timeline and chord data."""
    if not timeline:
        return {}
    n = len(timeline)
    return {
        'kick_density': sum(1 for e in timeline if e['kick'] > 0.02) / n,
        'snare_density': sum(1 for e in timeline if e['snare'] > 0.02) / n,
        'hihat_density': sum(1 for e in timeline if e['hihat'] > 0.02) / n,
        'bass_density': sum(e['bass'] for e in timeline) / n,
        'synth_density': sum(e['synth'] for e in timeline) / n,
        'pad_density': sum(e['pad'] for e in timeline) / n,
        'harmonic_ratio_avg': sum(e['harmonic_ratio'] for e in timeline) / n,
        'dominant_instrument': Counter(
            e['dominant_instrument'] for e in timeline
        ).most_common(1)[0][0],
        'chord_variety': len(set(c['chord'] for c in chords)) if chords else 0,
    }


def extract_song_structure(
    timeline: List[dict], chords: List[dict], time_data: dict
) -> List[dict]:
    """Segment a song's timeline into labelled structural sections."""
    if not timeline:
        return [{'type': 'verse', 'start': 0, 'end': 180, 'energy': 0.5}]

    duration = time_data.get('duration', timeline[-1]['time'] if timeline else 180)
    bpm = time_data.get('bpm', 120)
    bar_len = (60.0 / bpm) * 4

    bars = []
    t = 0.0
    while t < duration:
        bar_end = t + bar_len
        evts = [e for e in timeline if t <= e['time'] < bar_end]
        energy = (
            sum(
                e['kick'] + e['snare'] + e['hihat'] + e['bass'] + e['synth'] + e['pad']
                for e in evts
            )
            / max(1, len(evts))
            if evts
            else 0
        )
        bars.append({'start': round(t, 2), 'end': round(bar_end, 2), 'energy': round(energy, 4)})
        t = bar_end

    if not bars:
        return [{'type': 'verse', 'start': 0, 'end': duration, 'energy': 0.5}]

    max_e = max(b['energy'] for b in bars) or 1
    sections: List[dict] = []
    cur = None
    sec_start = 0.0

    for i, bar in enumerate(bars):
        ne = bar['energy'] / max_e
        if ne < 0.15:
            st = 'intro' if i < 4 else ('outro' if i > len(bars) - 4 else 'break')
        elif ne < 0.4:
            st = 'verse'
        elif ne < 0.7:
            st = 'chorus'
        else:
            st = 'drop'

        if st != cur:
            if cur:
                sections.append({
                    'type': cur,
                    'start': round(sec_start, 2),
                    'end': round(bar['start'], 2),
                    'energy': round(ne, 3),
                })
            cur = st
            sec_start = bar['start']

    if cur:
        sections.append({
            'type': cur,
            'start': round(sec_start, 2),
            'end': round(duration, 2),
            'energy': 0.5,
        })

    return sections or [{'type': 'verse', 'start': 0, 'end': duration, 'energy': 0.5}]
