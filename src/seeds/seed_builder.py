"""
SeedBuilder — converts a folder of CSV song-analysis triples into JSON seed files.

Folder layout expected:
    <dataset_root>/
        <source_subfolder>/
            <song_id>/
                <song_id>_time_data.csv
                <song_id>_chords.csv
                <song_id>_timeline.csv
"""

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Optional

from src.seeds.csv_parser import (
    parse_time_data_csv,
    parse_chords_csv,
    parse_timeline_csv,
    build_chord_transitions,
    extract_instrument_patterns,
    compute_timeline_stats,
    extract_song_structure,
)
from src.seeds.genre_classifier import classify_genre
from src.patterns.extractors.bass_extractor import extract_bass_patterns_enhanced
from src.patterns.extractors.rhythm_extractor import extract_instrument_patterns_enhanced


class SeedBuilder:
    """
    Scans a dataset directory for CSV song-analysis triples, processes each song,
    and saves the results as JSON seed files grouped by genre and data source.
    """

    def __init__(self, dataset_dir: str, output_dir: str = 'seeds'):
        self.dataset_dir = Path(dataset_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)
        self.seeds: List[dict] = []
        self.genre_seeds: defaultdict = defaultdict(list)
        self.source_seeds: defaultdict = defaultdict(list)

    # ─── DISCOVERY ────────────────────────────────────────────────────────────

    def find_csv_triples(self) -> list:
        """Locate all complete (time_data, chords, timeline) CSV triples."""
        all_csvs = list(self.dataset_dir.rglob('*.csv'))
        print(f'  Scanning {self.dataset_dir}...')
        print(f'  Found {len(all_csvs)} CSV files total')

        by_folder: defaultdict = defaultdict(list)
        for f in all_csvs:
            by_folder[str(f.parent)].append(f)

        triples = []
        for folder, files in by_folder.items():
            td = ch = tl = key = None
            for f in files:
                name = f.stem
                if name.endswith('_time_data'):
                    td = str(f); key = name[:-10]
                elif name.endswith('_chords'):
                    ch = str(f); key = key or name[:-7]
                elif name.endswith('_timeline'):
                    tl = str(f); key = key or name[:-9]
            if td and ch and tl and key:
                triples.append((td, ch, tl, key))

        print(f'  {len(triples)} complete song triples found')
        return triples

    # ─── PROCESSING ───────────────────────────────────────────────────────────

    def _detect_source(self, filepath: str) -> str:
        fp = filepath.lower()
        if 'gigamidi' in fp:
            return 'GigaMIDI'
        if 'jamendo' in fp:
            return 'Jamendo'
        return 'Unknown'

    def process_single_song(
        self, td_path: str, ch_path: str, tl_path: str, song_id: str
    ) -> Optional[dict]:
        """Process one song triple and return its seed dict, or None on failure."""
        try:
            td = parse_time_data_csv(td_path)
            chords = parse_chords_csv(ch_path)
            timeline = parse_timeline_csv(tl_path)

            if not chords and not timeline:
                return None

            bpm = td.get('bpm', 120)
            if isinstance(bpm, str):
                bpm = 120

            transitions = build_chord_transitions(chords)
            patterns = extract_instrument_patterns_enhanced(tl_path, bpm)
            bass_patterns = extract_bass_patterns_enhanced(tl_path, bpm)
            stats = compute_timeline_stats(timeline, chords)
            structure = extract_song_structure(timeline, chords, td)
            genre = classify_genre(td, stats)
            source = self._detect_source(td_path)
            progression = [f"{c['root']}{c['quality']}" for c in chords[:200]]

            return {
                'song_id': song_id,
                'source': source,
                'genre': genre,
                'dna': {
                    'bpm': round(bpm, 2) if isinstance(bpm, (int, float)) else 120,
                    'key': td.get('key', 'C major'),
                    'time_signature': td.get('time_signature', '4/4'),
                    'syncopation': (
                        round(td.get('syncopation_score', 0.5), 3)
                        if isinstance(td.get('syncopation_score'), (int, float))
                        else 0.5
                    ),
                    'duration': (
                        round(td.get('duration', 180), 2)
                        if isinstance(td.get('duration'), (int, float))
                        else 180
                    ),
                },
                'chord_transitions': transitions,
                'chord_roots_used': list(set(c['root'] for c in chords)),
                'chord_qualities_used': list(set(c['quality'] for c in chords)),
                'progression_sample': progression[:50],
                'instrument_patterns': patterns,
                'bass_patterns': bass_patterns,
                'structure': structure,
                'stats': stats,
            }
        except Exception as e:
            print(f'  Warning: {song_id}: {e}')
            return None

    def build_all_seeds(self, progress_callback=None) -> int:
        """Process all song triples and populate internal seed lists."""
        triples = self.find_csv_triples()
        total = len(triples)
        success = 0

        for i, (td, ch, tl, sid) in enumerate(triples):
            if progress_callback:
                progress_callback(i + 1, total, sid)

            seed = self.process_single_song(td, ch, tl, sid)
            if seed:
                self.seeds.append(seed)
                self.genre_seeds[seed['genre']].append(seed)
                self.source_seeds[seed['source']].append(seed)
                success += 1

            if (i + 1) % 100 == 0:
                print(f'  [{i + 1}/{total}] {success} seeds...')

        print(f'Complete: {success}/{total} seeds')
        for src, seeds in self.source_seeds.items():
            genres = Counter(s['genre'] for s in seeds)
            print(f'  {src}: {len(seeds)} songs — {dict(genres)}')

        return success

    # ─── OUTPUT ───────────────────────────────────────────────────────────────

    def save_seeds(self):
        """Write master, per-genre, per-source, and stats JSON files."""
        mp = self.output_dir / 'master_seeds.json'
        with open(mp, 'w', encoding='utf-8') as f:
            json.dump(self.seeds, f, indent=2, default=str)
        print(f'  Master: {mp} ({len(self.seeds)} seeds)')

        for genre, seeds in self.genre_seeds.items():
            p = self.output_dir / f'seeds_{genre}.json'
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(seeds, f, indent=2, default=str)
            print(f'  {genre}: {len(seeds)} seeds')

        for source, seeds in self.source_seeds.items():
            p = self.output_dir / f'seeds_source_{source}.json'
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(seeds, f, indent=2, default=str)
            print(f'  Source {source}: {len(seeds)} seeds')

        stats = {
            'total_seeds': len(self.seeds),
            'by_genre': {g: len(s) for g, s in self.genre_seeds.items()},
            'by_source': {s: len(ss) for s, ss in self.source_seeds.items()},
            'output_dir': str(self.output_dir.resolve()),
        }
        with open(self.output_dir / 'seed_stats.json', 'w') as f:
            json.dump(stats, f, indent=2)

    def build_merged_transition_matrix(self, genre: str = None) -> dict:
        """Merge chord-transition matrices across all seeds (or one genre)."""
        target = self.genre_seeds.get(genre, []) if genre else self.seeds
        merged: defaultdict = defaultdict(Counter)
        for seed in target:
            for ch, fol in seed.get('chord_transitions', {}).items():
                for nc, p in fol.items():
                    merged[ch][nc] += p
        result = {}
        for ch, fol in merged.items():
            total = sum(fol.values())
            result[ch] = {k: round(v / total, 4) for k, v in fol.items()}
        return result

    def export_genre_matrices(self):
        """Export per-genre and global chord-transition matrices as JSON."""
        md = self.output_dir / 'matrices'
        md.mkdir(exist_ok=True)
        for genre in self.genre_seeds:
            matrix = self.build_merged_transition_matrix(genre)
            with open(md / f'matrix_{genre}.json', 'w') as f:
                json.dump(matrix, f, indent=2)
            print(f'  Matrix {genre}: {len(matrix)} chords')
        gm = self.build_merged_transition_matrix()
        with open(md / 'matrix_global.json', 'w') as f:
            json.dump(gm, f, indent=2)
        print(f'  Global matrix: {len(gm)} chords')
