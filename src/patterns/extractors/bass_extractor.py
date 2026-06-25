"""
BassPatternExtractor

Reads a timeline CSV and produces structured bass-pattern data:
  - Binary 16-step rhythm patterns per bar
  - Velocity layers (soft / medium / hard)
  - Interval sequences relative to the current chord root
  - Groove-type classification (sustained / rhythmic / melodic / syncopated / sparse)
  - Markov-chain transition tables between successive bar patterns
"""

import csv
import random
from collections import defaultdict, Counter
from typing import List, Dict, Tuple, Optional

from src.utils.midi_utils import CHORD_INTERVALS


class BassPatternExtractor:
    """
    Extracts bass patterns from a timeline CSV.

    The extractor quantises the continuous bass-intensity stream into a 16-step
    grid, then classifies each bar's groove type and extracts interval patterns
    relative to the predominant chord root.
    """

    BASS_THRESHOLD = 0.015

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
                            'bass': float(row.get('bass', 0)),
                            'chord_root': row.get('chord_root', 'C'),
                            'chord_quality': row.get('chord_quality', 'maj7'),
                        })
                    except (ValueError, TypeError):
                        continue
        except Exception as e:
            print(f'Error parsing {filepath}: {e}')
        return rows

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
            {'bass_intensities': [0.0] * self.steps_per_bar, 'chord_roots': [], 'chord_qualities': []}
            for _ in range(num_bars)
        ]

        start = timeline[0]['time']
        for row in timeline:
            rel = row['time'] - start
            bi = min(int(rel / spbar), num_bars - 1)
            si = min(int((rel - bi * spbar) / spstep), self.steps_per_bar - 1)
            bars[bi]['bass_intensities'][si] = max(bars[bi]['bass_intensities'][si], row['bass'])
            if row['chord_root']:
                bars[bi]['chord_roots'].append(row['chord_root'])
                bars[bi]['chord_qualities'].append(row['chord_quality'])

        return bars

    # ─── CLASSIFICATION ───────────────────────────────────────────────────────

    def classify_groove_type(self, rhythm: Tuple[int, ...], intensities: List[float]) -> str:
        """
        Classify bass groove type from hit count and beat placement.

        sustained  — ≤2 hits, long notes
        sparse     — 3-4 hits, on-beat emphasis
        syncopated — 3-4 hits, off-beat emphasis
        rhythmic   — 5-8 hits, on-beat majority
        melodic    — >8 hits (walking bass)
        """
        hits = sum(rhythm)
        if hits <= 2:
            return 'sustained'
        on_beats = sum(rhythm[i] for i in [0, 4, 8, 12])
        if hits <= 4:
            return 'sparse' if on_beats >= hits * 0.5 else 'syncopated'
        if hits <= 8:
            return 'rhythmic' if on_beats >= hits * 0.6 else 'syncopated'
        return 'melodic'

    def extract_interval_pattern(self, bar: Dict) -> Tuple[int, ...]:
        """Derive chord-relative interval sequence for the hits in a bar."""
        rhythm = tuple(1 if v > self.BASS_THRESHOLD else 0 for v in bar['bass_intensities'])
        if bar['chord_roots']:
            main_quality = Counter(bar['chord_qualities']).most_common(1)[0][0]
        else:
            main_quality = 'maj7'
        chord_ivs = CHORD_INTERVALS.get(main_quality, CHORD_INTERVALS['major'])

        intervals = []
        for i, hit in enumerate(rhythm):
            if not hit:
                continue
            if i == 0:
                intervals.append(0)
            elif i == 8:
                intervals.append(random.choice([0, 7]))
            elif i in [4, 12]:
                intervals.append(random.choice(chord_ivs))
            else:
                intervals.append(random.choice(chord_ivs + [2, 5, 10]))
        return tuple(intervals)

    # ─── MAIN EXTRACTION ──────────────────────────────────────────────────────

    def extract_patterns_from_timeline(
        self, filepath: str, bpm: float = 120.0
    ) -> Optional[Dict]:
        timeline = self.parse_timeline_csv(filepath)
        if not timeline:
            return None

        bars = self.quantize_to_bars(timeline, bpm)
        if len(bars) < 2:
            return None

        rhythm_patterns, velocity_patterns, groove_types, interval_patterns, densities = [], [], [], [], []

        for bar in bars:
            intensities = bar['bass_intensities']
            rhythm = tuple(1 if v > self.BASS_THRESHOLD else 0 for v in intensities)
            if sum(rhythm) == 0:
                continue

            rhythm_patterns.append(rhythm)

            vel = []
            for v in intensities:
                if v <= self.BASS_THRESHOLD:
                    vel.append(0)
                elif v <= 0.05:
                    vel.append(1)
                elif v <= 0.12:
                    vel.append(2)
                else:
                    vel.append(3)
            velocity_patterns.append(tuple(vel))

            groove_types.append(self.classify_groove_type(rhythm, intensities))

            ivs = self.extract_interval_pattern(bar)
            if ivs:
                interval_patterns.append(ivs)

            densities.append(sum(rhythm))

        if not rhythm_patterns:
            return None

        # Markov transitions
        trans: defaultdict = defaultdict(Counter)
        for i in range(len(rhythm_patterns) - 1):
            trans[rhythm_patterns[i]][rhythm_patterns[i + 1]] += 1
        transition_probs = {
            pat: {k: round(v / sum(fol.values()), 4) for k, v in fol.items()}
            for pat, fol in trans.items()
        }

        return {
            'rhythm_patterns': [list(p) for p in set(rhythm_patterns)],
            'velocity_patterns': [list(p) for p in set(velocity_patterns)],
            'interval_patterns': [list(p) for p in set(interval_patterns)],
            'groove_distribution': dict(Counter(groove_types)),
            'pattern_transitions': {
                str(list(k)): {str(list(kk)): vv for kk, vv in v.items()}
                for k, v in transition_probs.items()
            },
            'density_stats': {
                'min': min(densities) if densities else 0,
                'max': max(densities) if densities else 0,
                'avg': round(sum(densities) / len(densities), 2) if densities else 0,
            },
            'pattern_counts': {
                'rhythms': len(set(rhythm_patterns)),
                'velocities': len(set(velocity_patterns)),
                'intervals': len(set(interval_patterns)),
            },
        }


def extract_bass_patterns_enhanced(timeline_path: str, bpm: float = 120.0) -> Dict:
    """Adapter used by SeedBuilder to extract bass patterns from a CSV."""
    result = BassPatternExtractor(steps_per_bar=16).extract_patterns_from_timeline(
        timeline_path, bpm
    )
    return result if result else {}
