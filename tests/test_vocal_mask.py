"""
Vocal Space Mask — batch validation test.

Generates one track per genre (10 total) with vocal_mask=True and verifies
that no melody or arp notes fall inside the C4–C6 exclusion zone (MIDI 60–83)
during verse and hook sections.

Run:
    python test_vocal_mask.py

Output:
    batch_test_vocal_mask/  — MIDI files for manual inspection
    Console report          — PASS / FAIL per genre with violating note counts
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.composition.composition_engine import CompositionEngine
from src.composition.composition_config import CompositionConfig

# -- Constants mirrored from composition_engine.py -----------------------------
VOCAL_MASK_LOW      = 60    # C4
VOCAL_MASK_HIGH     = 84    # C6 (exclusive)
VOCAL_MASK_SECTIONS = {'verse', 'hook', 'chorus', 'pre_chorus'}
CHECKED_TRACKS      = ('04_Melody', '07_Arp')

GENRES = [
    'pop', 'hiphop', 'trap', 'cinematic', 'classical',
    'techno', 'jpop', 'phonk', 'edm', 'house',
]

OUT_DIR = Path('batch_test_vocal_mask')


def _verse_hook_beat_ranges(structure: list) -> list[tuple[float, float]]:
    """Return [(start_beat, end_beat), ...] for every verse/hook section."""
    ranges = []
    beat = 0.0
    for section_type, bars in structure:
        end_beat = beat + bars * 4
        if section_type in VOCAL_MASK_SECTIONS:
            ranges.append((beat, end_beat))
        beat = end_beat
    return ranges


def _violations_in_track(
    notes: list,
    beat_ranges: list[tuple[float, float]],
) -> list[int]:
    """Return MIDI pitches that land inside the exclusion zone during target sections."""
    bad = []
    for time, _dur, pitch, _vel in notes:
        if not (VOCAL_MASK_LOW <= pitch < VOCAL_MASK_HIGH):
            continue
        for start, end in beat_ranges:
            if start <= time < end:
                bad.append(pitch)
                break
    return bad


def run_test() -> None:
    OUT_DIR.mkdir(exist_ok=True)

    engine = CompositionEngine(seeds_dir='seeds', vocal_mask=True)
    engine.load_seeds()

    print()
    print('=' * 62)
    print('  VOCAL SPACE MASK — C4–C6 exclusion zone validation')
    print('  Sections checked: verse, hook, chorus, pre_chorus')
    print('  Tracks checked:   04_Melody, 07_Arp')
    print('=' * 62)

    results = []

    for genre in GENRES:
        config = CompositionConfig(
            genre=genre,
            complexity=6,
            vocal_mask=True,
        )

        try:
            comp = engine.compose(config)
        except Exception as exc:
            print(f'  {genre:<12}  ERROR during compose: {exc}')
            results.append((genre, None, {}))
            continue

        structure   = comp['structure']
        beat_ranges = _verse_hook_beat_ranges(structure)
        tracks      = comp['tracks']

        violations: dict[str, list[int]] = {}
        for track_key in CHECKED_TRACKS:
            notes = tracks.get(track_key, [])
            bad   = _violations_in_track(notes, beat_ranges)
            if bad:
                violations[track_key] = bad

        passed = len(violations) == 0
        results.append((genre, passed, violations))

        # Export MIDI regardless of pass/fail for manual inspection
        midi_path = OUT_DIR / f'{genre}_vocal_mask_test.mid'
        try:
            engine.export_midi(comp, str(midi_path))
        except Exception as exc:
            print(f'  [WARN] MIDI export failed for {genre}: {exc}')

        # Console line
        status = 'PASS' if passed else 'FAIL'
        section_info = (
            f'  {len(beat_ranges)} verse/hook section(s), '
            f'{sum(b-a for a,b in beat_ranges):.0f} beats'
        )
        if passed:
            print(f'  {genre:<12}  [{status}]{section_info}')
        else:
            total_v = sum(len(v) for v in violations.values())
            print(f'  {genre:<12}  [{status}]  {total_v} violation(s):')
            for track_key, pitches in violations.items():
                unique = sorted(set(pitches))
                print(f'             {track_key}: MIDI pitches {unique}')

    # -- Summary ---------------------------------------------------------------
    passed_count = sum(1 for _, p, _ in results if p is True)
    failed_count = sum(1 for _, p, _ in results if p is False)
    error_count  = sum(1 for _, p, _ in results if p is None)

    print('-' * 62)
    print(f'  Result: {passed_count} PASS  /  {failed_count} FAIL  /  {error_count} ERROR')
    print(f'  MIDI files written to: {OUT_DIR.resolve()}')
    print('=' * 62)
    print()

    sys.exit(0 if failed_count == 0 and error_count == 0 else 1)


if __name__ == '__main__':
    run_test()
