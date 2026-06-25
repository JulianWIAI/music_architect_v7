"""
Batch seed builder — CLI script.

Scans a dataset directory for CSV analysis triples and builds JSON seed files.

Usage:
    python scripts/build_seeds.py <dataset_root> [-o <output_dir>]

The dataset root must contain nested song folders, each with three CSV files:
    <song_id>_time_data.csv
    <song_id>_chords.csv
    <song_id>_timeline.csv
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Allow running the script directly from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.seeds.seed_builder import SeedBuilder


def main():
    parser = argparse.ArgumentParser(description='Build JSON seeds from a CSV dataset.')
    parser.add_argument('dataset_dir', help='Root folder containing song CSV sub-folders')
    parser.add_argument('-o', '--output', default='seeds', help='Output directory for seed files')
    args = parser.parse_args()

    if not os.path.exists(args.dataset_dir):
        print(f'Dataset not found: {args.dataset_dir}')
        sys.exit(1)

    print('Batch Seed Builder')
    print(f'  Dataset : {args.dataset_dir}')
    print(f'  Output  : {args.output}')
    print()

    start = time.time()
    builder = SeedBuilder(args.dataset_dir, args.output)

    def progress(i, total, song_id):
        pct = i / total * 100
        bar = '#' * int(pct / 2) + '.' * (50 - int(pct / 2))
        print(f'\r  [{bar}] {pct:.1f}% ({i}/{total}) {song_id[:30]:30s}', end='', flush=True)

    count = builder.build_all_seeds(progress_callback=progress)
    print()

    if count > 0:
        builder.save_seeds()
        builder.export_genre_matrices()

        elapsed = time.time() - start
        print(f'\n{count} seeds built in {elapsed:.1f}s')
        print(f'Output: {Path(args.output).resolve()}')

        print('\nGenre breakdown:')
        for genre, seeds in sorted(builder.genre_seeds.items()):
            print(f'  {genre:12s}: {len(seeds):4d} songs')

        print('\nSource breakdown:')
        for source, seeds in sorted(builder.source_seeds.items()):
            print(f'  {source:12s}: {len(seeds):4d} songs')
    else:
        print('No seeds created. Check CSV file naming:')
        print('  <song_id>_time_data.csv')
        print('  <song_id>_chords.csv')
        print('  <song_id>_timeline.csv')


if __name__ == '__main__':
    main()
