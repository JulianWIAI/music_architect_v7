"""
Smoke tests for the UTAU bridge port.
Run: python tests/test_utau_bridge.py
"""
import sys, math, tempfile, pathlib
sys.path.insert(0, '.')

import yaml

from src.export.utau_bridge import (
    RawNote, WorkNote,
    _sanitize_lyric, _convert_ticks, _merge_clusters, _remove_chords,
    _enforce_durations, _humanized_velocity,
    TINY_THRESHOLD, MAIN_THRESHOLD, CLUSTER_GAP_MAX, CHORD_WINDOW,
    SOFT_MIN_DURATION, HARD_MIN_DURATION,
    export,
)

# --- constants (must match C# values exactly) ---
assert TINY_THRESHOLD == 40,    f"TINY_THRESHOLD mismatch: {TINY_THRESHOLD}"
assert MAIN_THRESHOLD == 200,   f"MAIN_THRESHOLD mismatch: {MAIN_THRESHOLD}"
assert CLUSTER_GAP_MAX == 20,   f"CLUSTER_GAP_MAX mismatch: {CLUSTER_GAP_MAX}"
assert CHORD_WINDOW == 20,      f"CHORD_WINDOW mismatch: {CHORD_WINDOW}"
assert SOFT_MIN_DURATION == 480
assert HARD_MIN_DURATION == 240
print("Constants: PASS")

# --- _sanitize_lyric ---
for bad in ('', 'True', 'false', 'YES', 'on', 'null', '~'):
    assert _sanitize_lyric(bad) == 'la', f"Should sanitize {bad!r}"
assert _sanitize_lyric('hello') == 'hello'
assert _sanitize_lyric('  la  ') == 'la'
print("_sanitize_lyric: PASS")

# --- _convert_ticks ---
raw = [RawNote(tick=960, duration=480, pitch=60, velocity=100)]
work = _convert_ticks(raw, tpqn=960)
assert work[0].position == 480
assert work[0].duration == 240
print("_convert_ticks (960->480): PASS")

# --- _merge_clusters: pickup fold ---
mc_notes = [
    WorkNote(position=0,  duration=30,  pitch=60, lyric='p'),
    WorkNote(position=40, duration=500, pitch=62, lyric='la'),
]
merged = _merge_clusters(mc_notes)
assert len(merged) == 1
assert merged[0].position == 0
assert merged[0].duration == 540
assert 'p' in merged[0].lyric and 'la' in merged[0].lyric
print("_merge_clusters (pickup fold): PASS")

# --- _merge_clusters: gap too large, no merge ---
mc2 = [
    WorkNote(position=0,   duration=30,  pitch=60, lyric='p'),
    WorkNote(position=100, duration=500, pitch=62, lyric='la'),
]
merged2 = _merge_clusters(mc2)
assert len(merged2) == 2
print("_merge_clusters (no merge when gap>MAX): PASS")

# --- _remove_chords ---
rc = [
    WorkNote(position=0,  duration=480, pitch=60, lyric='a'),
    WorkNote(position=10, duration=240, pitch=64, lyric='b'),
]
deduped = _remove_chords(rc)
assert len(deduped) == 1
assert deduped[0].duration == 480
print("_remove_chords (keep longest in window): PASS")

# --- _enforce_durations ---
ed = [
    WorkNote(position=0,   duration=100, pitch=60, lyric='a'),
    WorkNote(position=300, duration=100, pitch=62, lyric='b'),
]
_enforce_durations(ed)
# Pass1: 100 -> 480.  Pass2: gap=300, cap to 299, hard floor max(299,240)=299
assert ed[0].duration == 299, f"Expected 299, got {ed[0].duration}"
# Last note: only pass1 -> 480
assert ed[1].duration == 480
print("_enforce_durations (soft-min + gap-cap): PASS")

ed2 = [
    WorkNote(position=0,   duration=50, pitch=60, lyric='a'),
    WorkNote(position=100, duration=50, pitch=62, lyric='b'),
]
_enforce_durations(ed2)
assert ed2[0].duration == HARD_MIN_DURATION, f"Expected 240, got {ed2[0].duration}"
print("_enforce_durations (hard floor): PASS")

# --- _humanized_velocity ---
for i in range(20):
    v = _humanized_velocity(i, 20)
    assert 85 <= v <= 115, f"vel={v} out of range at i={i}"
assert [_humanized_velocity(i,20) for i in range(20)] == [_humanized_velocity(i,20) for i in range(20)]
print("_humanized_velocity (range + determinism): PASS")

# --- Full pipeline + YAML output ---
phrases = [
    [
        RawNote(tick=0,    duration=480, pitch=60, velocity=100, lyric='la'),
        RawNote(tick=500,  duration=480, pitch=62, velocity=90,  lyric='la'),
        RawNote(tick=1000, duration=480, pitch=64, velocity=80,  lyric='la'),
    ],
    [
        RawNote(tick=2000, duration=480, pitch=65, velocity=95, lyric='yes'),
        RawNote(tick=2500, duration=480, pitch=67, velocity=85, lyric='true'),
    ],
]

out_path = pathlib.Path(tempfile.mktemp(suffix='.ustx'))
export(out_path, phrases, tpqn=480, bpm=120.0, song_name='test_export')
content = out_path.read_text(encoding='utf-8')
out_path.unlink()

doc = yaml.safe_load(content)
assert doc['resolution'] == 480
assert doc['bpm'] == 120.0
assert doc['tracks'][0]['track_name'] == 'Vocal'

vp = doc['voice_parts'][0]
assert len(vp['notes']) == 5, f"Expected 5 notes, got {len(vp['notes'])}"

# YAML-reserved lyrics must be sanitized to 'la'
for note in vp['notes']:
    lyr = note['lyric']
    assert lyr.lower() not in {'yes', 'true', 'false', 'no', 'on', 'off'}, \
        f"Unsanitized lyric: {lyr!r}"
print("YAML bool lyric sanitization: PASS")

# phoneme_expressions must NOT appear
for note in vp['notes']:
    assert 'phoneme_expressions' not in note
print("phoneme_expressions absent: PASS")

# pitch data present on every note
for note in vp['notes']:
    assert note['pitch']['snap_first'] is True
    assert len(note['pitch']['data']) == 2
print("Pitch data on all notes: PASS")

# velocity curve
curves = vp['curves']
assert curves[0]['abbr'] == 'vel'
assert len(curves[0]['xs']) == 5
print("Velocity curve (5 entries): PASS")

# expressions block
assert 'vel' in doc['expressions']
assert 'pitd' in doc['expressions']
print("Expressions block: PASS")

print()
print("ALL PASS")
