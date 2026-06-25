"""
RhythmPatternExtractor

Reads a timeline CSV and converts continuous per-frame intensity values into
discrete 16-step binary patterns for kick, snare, hihat, bass, synth, and pad.
Also builds Markov-chain transition tables between successive bar patterns.
"""

import csv
import json
from collections import defaultdict, Counter
from typing import List, Dict, Tuple, Optional


class RhythmPatternExtractor:
    """
    Extracts quantised rhythm patterns from timeline CSV files.

    All six instrument channels are processed simultaneously so that the
    resulting patterns share the same bar-grid alignment.
    """

    THRESHOLDS = {
        'kick': 0.03, 'snare': 0.02, 'hihat': 0.01,
        'bass': 0.02, 'synth': 0.02, 'pad': 0.02,
    }

    VELOCITY_LEVELS = {'soft': 0.05, 'medium': 0.10, 'hard': 0.20}

    def __init__(self, steps_per_bar: int = 16):
        self.steps_per_bar = steps_per_bar

    # ─── PARSING ──────────────────────────────────────────────────────────────

    def parse_timeline_csv(self, filepath: str) -> List[Dict]:
        rows = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for row in csv.DictReader(f, delimiter=';'):
                    try:
                        rows.append({
                            'time': float(row.get('time_seconds', 0)),
                            'kick': float(row.get('kick', 0)),
                            'snare': float(row.get('snare', 0)),
                            'hihat': float(row.get('hihat', 0)),
                            'bass': float(row.get('bass', 0)),
                            'synth': float(row.get('synth', 0)),
                            'pad': float(row.get('pad', 0)),
                            'chord_root': row.get('chord_root', 'C'),
                            'chord_quality': row.get('chord_quality', 'maj7'),
                        })
                    except (ValueError, TypeError):
                        continue
        except Exception as e:
            print(f'Error parsing {filepath}: {e}')
        return rows

    def estimate_bpm(self, timeline: List[Dict], default_bpm: float = 120.0) -> float:
        """Estimate BPM from kick-drum inter-onset intervals."""
        if len(timeline) < 10:
            return default_bpm
        kick_times = [r['time'] for r in timeline if r['kick'] > self.THRESHOLDS['kick'] * 2]
        if len(kick_times) < 4:
            return default_bpm
        intervals = [kick_times[i + 1] - kick_times[i] for i in range(len(kick_times) - 1)]
        valid = [i for i in intervals if 0.2 < i < 2.0]
        if not valid:
            return default_bpm
        quantized = [round(i * 20) / 20 for i in valid]
        most_common = Counter(quantized).most_common(1)
        if most_common:
            bpm = 60.0 / most_common[0][0]
            while bpm < 60:
                bpm *= 2
            while bpm > 180:
                bpm /= 2
            return round(bpm, 1)
        return default_bpm

    # ─── QUANTISATION ─────────────────────────────────────────────────────────

    def quantize_to_bars(self, timeline: List[Dict], bpm: float) -> List[Dict]:
        if not timeline:
            return []
        spb = 60.0 / bpm
        spbar = spb * 4
        spstep = spbar / self.steps_per_bar
        duration = timeline[-1]['time'] - timeline[0]['time']
        num_bars = int(duration / spbar) + 1

        bars = [
            {inst: [0.0] * self.steps_per_bar for inst in self.THRESHOLDS} | {'chord_roots': []}
            for _ in range(num_bars)
        ]

        start = timeline[0]['time']
        for row in timeline:
            rel = row['time'] - start
            bi = min(int(rel / spbar), num_bars - 1)
            si = min(int((rel - bi * spbar) / spstep), self.steps_per_bar - 1)
            for inst in self.THRESHOLDS:
                bars[bi][inst][si] = max(bars[bi][inst][si], row[inst])
            if row['chord_root']:
                bars[bi]['chord_roots'].append(row['chord_root'])

        return bars

    # ─── CONVERSION ───────────────────────────────────────────────────────────

    def convert_to_binary_pattern(self, intensities: List[float], threshold: float) -> Tuple:
        return tuple(1 if v > threshold else 0 for v in intensities)

    def convert_to_velocity_pattern(self, intensities: List[float], threshold: float) -> Tuple:
        lv = self.VELOCITY_LEVELS
        pattern = []
        for v in intensities:
            if v <= threshold:
                pattern.append(0)
            elif v <= lv['soft']:
                pattern.append(1)
            elif v <= lv['medium']:
                pattern.append(2)
            else:
                pattern.append(3)
        return tuple(pattern)

    # ─── EXTRACTION ───────────────────────────────────────────────────────────

    def extract_patterns_from_timeline(
        self, filepath: str, provided_bpm: Optional[float] = None
    ) -> Optional[Dict]:
        timeline = self.parse_timeline_csv(filepath)
        if not timeline:
            return None

        bpm = provided_bpm or self.estimate_bpm(timeline)
        bars = self.quantize_to_bars(timeline, bpm)
        if len(bars) < 2:
            return None

        instruments = list(self.THRESHOLDS.keys())
        patterns = {inst: [] for inst in instruments}
        velocity_patterns = {inst: [] for inst in instruments}

        for bar in bars:
            for inst in instruments:
                binary = self.convert_to_binary_pattern(bar[inst], self.THRESHOLDS[inst])
                velocity = self.convert_to_velocity_pattern(bar[inst], self.THRESHOLDS[inst])
                if sum(binary) > 0:
                    patterns[inst].append(binary)
                    velocity_patterns[inst].append(velocity)

        transitions = {}
        for inst in instruments:
            inst_pats = patterns[inst]
            if len(inst_pats) < 2:
                continue
            trans: defaultdict = defaultdict(Counter)
            for i in range(len(inst_pats) - 1):
                trans[inst_pats[i]][inst_pats[i + 1]] += 1
            transitions[inst] = {
                pat: {k: round(v / sum(fol.values()), 4) for k, v in fol.items()}
                for pat, fol in trans.items()
            }

        unique_p = {inst: list(set(pats)) for inst, pats in patterns.items()}
        unique_v = {inst: list(set(pats)) for inst, pats in velocity_patterns.items()}

        return {
            'bpm': bpm,
            'num_bars': len(bars),
            'drum_patterns': {inst: [list(p) for p in unique_p[inst]] for inst in instruments},
            'drum_velocity_patterns': {inst: [list(p) for p in unique_v[inst]] for inst in instruments},
            'bass_patterns': [list(p) for p in unique_p['bass']],
            'bass_velocity_patterns': [list(p) for p in unique_v['bass']],
            'pattern_transitions': {
                inst: {
                    str(list(k)): {str(list(kk)): vv for kk, vv in v.items()}
                    for k, v in trans.items()
                }
                for inst, trans in transitions.items()
            },
            'pattern_counts': {inst: len(unique_p[inst]) for inst in instruments},
        }


def extract_instrument_patterns_enhanced(timeline_path: str, bpm: float = 120.0) -> Dict:
    """Adapter used by SeedBuilder to extract all rhythm patterns from a CSV."""
    result = RhythmPatternExtractor(steps_per_bar=16).extract_patterns_from_timeline(
        timeline_path, bpm
    )
    return result if result else {}
