"""
Python port of C# UstxExportService and MidiParserService.

Pipeline (mirrors the C# exactly):
  parse_file()        — scan MIDI tracks, extract BPM / TPQN metadata
  build_phrases()     — read vocal track, split on eighth-note gaps
  export()            — 5-stage sanitization → YAML serialization
  process_midi_to_ustx() — all-in-one convenience wrapper

Stage constants (in 480-res USTX ticks, matching C# values):
  TINY_THRESHOLD   = 40    pickup consonants shorter than this
  MAIN_THRESHOLD   = 200   syllable beat, at least this long
  CLUSTER_GAP_MAX  = 20    max gap inside a cluster / cluster-to-main
  CHORD_WINDOW     = 20    positions within this window are treated as chords
  SOFT_MIN_DURATION = 480  one beat — applied before gap-cap
  HARD_MIN_DURATION = 240  absolute floor even after gap-cap
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import mido
    _MIDO_OK = True
except ImportError:
    _MIDO_OK = False
    print("WARNING: mido not installed.  Run: pip install mido")

try:
    import yaml
    _YAML_OK = True
except ImportError:
    _YAML_OK = False
    print("WARNING: pyyaml not installed.  Run: pip install pyyaml")

# ---------------------------------------------------------------------------
# Pipeline constants (verbatim from C# UstxExportService)
# ---------------------------------------------------------------------------

_USTX_RESOLUTION   = 480
TINY_THRESHOLD     = 40
MAIN_THRESHOLD     = 200
CLUSTER_GAP_MAX    = 20
CHORD_WINDOW       = 20
SOFT_MIN_DURATION  = 480
HARD_MIN_DURATION  = 240

# YAML-reserved strings (case-insensitive, matches C# YamlBooleans / YamlReserved)
_YAML_RESERVED_LC = frozenset({
    "true", "false", "yes", "no", "on", "off", "null", "~",
})

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RawNote:
    """Note in original MIDI tick space (output of build_phrases)."""
    tick: int        # absolute start tick in source TPQN
    duration: int    # in source TPQN ticks
    pitch: int       # MIDI note number 0-127
    velocity: int
    lyric: str = "la"


@dataclass
class WorkNote:
    """Mutable note in 480-res USTX tick space, used during pipeline processing."""
    position: int
    duration: int
    pitch: int
    lyric: str = "la"


@dataclass
class TrackInfo:
    index: int
    name: str
    note_count: int


@dataclass
class ParsedMidi:
    file_path: str
    ticks_per_quarter_note: int = 480
    bpm: float = 120.0
    tracks: List[TrackInfo] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API — parser (port of MidiParserService)
# ---------------------------------------------------------------------------

def parse_file(midi_path: str | Path) -> ParsedMidi:
    """
    Port of MidiParserService.ParseFile().

    Returns MIDI metadata: TPQN, BPM, and a list of non-empty tracks
    with their names and note counts.
    """
    _require_mido()
    midi = mido.MidiFile(str(midi_path))
    result = ParsedMidi(
        file_path=str(midi_path),
        ticks_per_quarter_note=midi.ticks_per_beat,
    )

    # Extract BPM from the first SetTempo event across all tracks
    result.bpm = _extract_bpm(midi)

    for idx, track in enumerate(midi.tracks):
        note_count = sum(
            1 for msg in track if msg.type == "note_on" and msg.velocity > 0
        )
        if note_count == 0:
            continue
        name = next(
            (msg.name for msg in track if msg.type == "track_name"),
            f"Track {idx}",
        )
        result.tracks.append(TrackInfo(index=idx, name=name, note_count=note_count))

    return result


def build_phrases(
    midi_path: str | Path,
    track_index: int,
    default_lyric: str = "la",
) -> Tuple[List[List[RawNote]], bool]:
    """
    Port of MidiParserService.BuildPhrases().

    Reads the specified track, converts delta times to absolute ticks,
    pairs note-on / note-off events into RawNote objects, and splits
    the note sequence into phrases wherever the inter-note gap exceeds
    an eighth note (tpqn // 2 ticks).

    Returns:
        (phrases, has_chords)
        phrases    — list of phrase lists, each phrase a list of RawNote
        has_chords — True if any two notes in the track overlap in time
    """
    _require_mido()
    midi = mido.MidiFile(str(midi_path))
    tpqn = midi.ticks_per_beat
    eighth_note_ticks = tpqn // 2

    if track_index >= len(midi.tracks):
        return [], False

    track = midi.tracks[track_index]

    # Collect notes from delta-time stream
    active: dict = {}          # pitch → (abs_start_tick, velocity)
    completed: List[RawNote] = []
    abs_tick = 0

    for msg in track:
        abs_tick += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            active[msg.note] = (abs_tick, msg.velocity)
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            if msg.note in active:
                start, vel = active.pop(msg.note)
                dur = abs_tick - start
                if dur > 0:
                    completed.append(RawNote(
                        tick=start,
                        duration=dur,
                        pitch=msg.note,
                        velocity=vel,
                        lyric=_sanitize_lyric(default_lyric),
                    ))

    if not completed:
        return [], False

    completed.sort(key=lambda n: n.tick)

    # Chord detection: any note starts before the previous one ends
    has_chords = any(
        completed[i].tick < completed[i - 1].tick + completed[i - 1].duration
        for i in range(1, len(completed))
    )

    # Split into phrases on gaps > eighth note
    phrases: List[List[RawNote]] = []
    current: List[RawNote] = []

    for i, note in enumerate(completed):
        current.append(note)
        if i < len(completed) - 1:
            gap = completed[i + 1].tick - (note.tick + note.duration)
            if gap > eighth_note_ticks:
                phrases.append(current)
                current = []

    if current:
        phrases.append(current)

    return [p for p in phrases if p], has_chords


# ---------------------------------------------------------------------------
# Public API — exporter (port of UstxExportService)
# ---------------------------------------------------------------------------

def export(
    output_path: str | Path,
    phrases: List[List[RawNote]],
    tpqn: int,
    bpm: float = 120.0,
    song_name: str = "Voxweaver Export",
    singer: str = "TIGER DS",
) -> None:
    """
    Port of UstxExportService.Export().

    Accepts all phrases (each a list of RawNote with absolute MIDI ticks),
    flattens them, runs the 5-stage sanitization pipeline, and writes a
    valid .ustx YAML file to *output_path*.

    Stage 1  — Convert MIDI ticks to 480-resolution USTX ticks.
    Stage 2  — MergeClusters: fold tiny pickup notes into the following main note.
    Stage 3  — RemoveChords: within each position window, keep the longest note.
    Stage 4  — EnforceDurations: soft-min 480, cap to gap, hard-floor 240.
    Stage 5  — Serialize to .ustx YAML with ForceStringQuoting for lyrics.
    """
    _require_mido()
    _require_yaml()

    all_raw: List[RawNote] = [n for phrase in phrases for n in phrase]

    # Stage 1
    work: List[WorkNote] = _convert_ticks(all_raw, tpqn)
    # Stage 2
    work = _merge_clusters(work)
    # Stage 3
    work = _remove_chords(work)
    # Stage 4
    _enforce_durations(work)
    # Stage 5
    ustx = _build_ustx_dict(work, bpm, song_name, singer)
    _write_yaml(ustx, output_path)


def process_midi_to_ustx(
    midi_path: str | Path,
    output_path: str | Path,
    track_index: int = 1,
    bpm: Optional[float] = None,
    song_name: str = "",
    default_lyric: str = "la",
    singer: str = "TIGER DS",
) -> ParsedMidi:
    """
    All-in-one convenience wrapper: parse → build_phrases → export.

    If *bpm* is None, BPM is read from the MIDI file's SetTempo event.
    *song_name* defaults to the MIDI file's stem when not provided.

    Returns the ParsedMidi metadata for caller inspection.
    """
    parsed = parse_file(midi_path)
    effective_bpm = bpm if bpm is not None else parsed.bpm
    effective_name = song_name or Path(midi_path).stem

    phrases, _ = build_phrases(midi_path, track_index, default_lyric=default_lyric)
    if not phrases:
        raise ValueError(
            f"No notes found in track {track_index} of {midi_path}"
        )

    export(
        output_path=output_path,
        phrases=phrases,
        tpqn=parsed.ticks_per_quarter_note,
        bpm=effective_bpm,
        song_name=effective_name,
        singer=singer,
    )
    return parsed


# ---------------------------------------------------------------------------
# Pipeline — Stage 1: tick conversion
# ---------------------------------------------------------------------------

def _convert_ticks(notes: List[RawNote], tpqn: int) -> List[WorkNote]:
    """Scale from source TPQN to 480-res USTX ticks (C# Export stage 1)."""
    scale = _USTX_RESOLUTION / tpqn
    return [
        WorkNote(
            position=int(n.tick * scale),
            duration=max(1, int(n.duration * scale)),
            pitch=n.pitch,
            lyric=_sanitize_lyric(n.lyric),
        )
        for n in notes
    ]


# ---------------------------------------------------------------------------
# Pipeline — Stage 2: MergeClusters
# ---------------------------------------------------------------------------

def _merge_clusters(notes: List[WorkNote]) -> List[WorkNote]:
    """
    Port of UstxExportService.MergeClusters().

    Collects runs of tiny pickup notes (duration < TINY_THRESHOLD) that
    are mutually adjacent (gap < CLUSTER_GAP_MAX) and immediately precede
    a main note (duration >= MAIN_THRESHOLD, gap < CLUSTER_GAP_MAX).
    When found, extends the main note's start back to the first pickup and
    combines their lyrics.  Isolated tiny notes that have no following main
    note are emitted unchanged.
    """
    result: List[WorkNote] = []
    i = 0

    while i < len(notes):
        # Normal note: pass through immediately
        if notes[i].duration >= TINY_THRESHOLD:
            result.append(notes[i])
            i += 1
            continue

        # Collect consecutive tiny notes
        cluster = [notes[i]]
        j = i + 1
        while j < len(notes) and notes[j].duration < TINY_THRESHOLD:
            between_gap = notes[j].position - (
                notes[j - 1].position + notes[j - 1].duration
            )
            if between_gap > CLUSTER_GAP_MAX:
                break
            cluster.append(notes[j])
            j += 1

        # Try to fold cluster into a following main note
        did_merge = False
        if j < len(notes) and notes[j].duration >= MAIN_THRESHOLD:
            last_end   = cluster[-1].position + cluster[-1].duration
            gap_to_main = notes[j].position - last_end
            if gap_to_main < CLUSTER_GAP_MAX:
                orig      = notes[j]
                new_end   = orig.position + orig.duration
                new_start = cluster[0].position
                syllables = [n.lyric for n in cluster] + [orig.lyric]
                result.append(WorkNote(
                    position=new_start,
                    duration=new_end - new_start,
                    pitch=orig.pitch,
                    lyric=" ".join(s for s in syllables if s),
                ))
                i = j + 1
                did_merge = True

        if not did_merge:
            # No eligible main note — emit tiny notes individually
            result.extend(cluster)
            i = j

    return result


# ---------------------------------------------------------------------------
# Pipeline — Stage 3: RemoveChords
# ---------------------------------------------------------------------------

def _remove_chords(notes: List[WorkNote]) -> List[WorkNote]:
    """
    Port of UstxExportService.RemoveChords().

    Groups notes whose positions fall within CHORD_WINDOW ticks of each
    other.  Within each group, keeps the note with the longest duration
    and combines distinct non-empty lyrics from the group.
    """
    result: List[WorkNote] = []
    i = 0

    while i < len(notes):
        j = i + 1
        while (j < len(notes) and
               abs(notes[j].position - notes[i].position) < CHORD_WINDOW):
            j += 1

        group = sorted(notes[i:j], key=lambda n: -n.duration)
        best  = group[0]
        seen: dict = {}
        for n in group:
            if n.lyric:
                seen[n.lyric] = None   # preserve insertion order, deduplicate
        result.append(WorkNote(
            position=best.position,
            duration=best.duration,
            pitch=best.pitch,
            lyric=" ".join(seen.keys()),
        ))
        i = j

    return result


# ---------------------------------------------------------------------------
# Pipeline — Stage 4: EnforceDurations
# ---------------------------------------------------------------------------

def _enforce_durations(notes: List[WorkNote]) -> None:
    """
    Port of UstxExportService.EnforceDurations().  Mutates list in-place.

    Pass 1 — soft minimum 480: every note is extended to at least one beat.
    Pass 2 — gap cap + hard floor:
      • cap each note's duration to (next_start - current_start - 1) so
        no note's tail overlaps the following note's head;
      • then enforce HARD_MIN_DURATION=240 regardless of gap.
    """
    # Pass 1: soft minimum
    for n in notes:
        n.duration = max(n.duration, SOFT_MIN_DURATION)

    # Pass 2: gap cap, then hard floor
    for i in range(len(notes) - 1):
        gap = notes[i + 1].position - notes[i].position
        if gap > 0:
            notes[i].duration = min(notes[i].duration, gap - 1)
        notes[i].duration = max(notes[i].duration, HARD_MIN_DURATION)


# ---------------------------------------------------------------------------
# Pipeline — Stage 5: USTX dict construction
# ---------------------------------------------------------------------------

def _humanized_velocity(index: int, total: int) -> int:
    """
    Port of UstxExportService.HumanizedVelocity().

    Multi-frequency sine contour: deterministic (no Random), reproducible,
    sounds natural.  Output clamped to [85, 115].
    """
    phase = index / max(total - 1.0, 1) * 2 * math.pi
    v = int(
        100
        + 10 * math.sin(phase * 3.7 + 0.5)
        +  5 * math.sin(phase * 7.1)
    )
    return max(85, min(115, v))


def _build_ustx_dict(
    work_notes: List[WorkNote],
    bpm: float,
    song_name: str,
    singer: str,
) -> dict:
    """Build the full .ustx dict matching the C# UstxProject POCO graph."""
    total = len(work_notes)
    vel_xs = [n.position for n in work_notes]
    vel_ys = [_humanized_velocity(i, total) for i in range(total)]

    ustx_notes = []
    for wn in work_notes:
        ustx_notes.append({
            "position": wn.position,
            "duration": wn.duration,
            "tone":     wn.pitch,
            "lyric":    wn.lyric,
            "pitch": {
                "data": [
                    {"x": -40.0, "y": 0.0, "shape": "l"},
                    {"x":   0.0, "y": 0.0, "shape": "l"},
                ],
                "snap_first": True,
            },
            "vibrato": {
                "length": 0,  "period": 175, "depth": 25,
                "in":    10,  "out":    10,  "shift": 0, "drift": 0,
            },
            "note_expressions": {},
        })

    return {
        "name":         song_name,
        "comment":      "",
        "output_dir":   "Vocal",
        "caches_dir":   "UCache",
        "ustx_version": "0.6",
        "resolution":   _USTX_RESOLUTION,
        "bpm":          round(bpm, 3),
        "beat_per_bar": 4,
        "beat_unit":    4,
        "expressions": {
            "vel":  {"name": "velocity (curve)",        "abbr": "vel",  "type": "Curve",
                     "min": 0,     "max": 200,  "default_value": 100, "is_flag": False},
            "vol":  {"name": "volume (curve)",           "abbr": "vol",  "type": "Curve",
                     "min": 0,     "max": 200,  "default_value": 100, "is_flag": False},
            "dyn":  {"name": "dynamics (curve)",         "abbr": "dyn",  "type": "Curve",
                     "min": -240,  "max": 120,  "default_value": 0,   "is_flag": False},
            "pitd": {"name": "pitch deviation (curve)",  "abbr": "pitd", "type": "Curve",
                     "min": -1200, "max": 1200, "default_value": 0,   "is_flag": False},
        },
        "tracks": [{
            "track_name":   "Vocal",
            "singer":       singer,
            "phonemizer":   "OpenUtau.Core.DiffSinger.DiffSingerEnglishPhonemizer",
            "renderer_settings": {"renderer": "DIFFSINGER"},
        }],
        "voice_parts": [{
            "name":     "Vocal",
            "comment":  "",
            "track_no": 0,
            "position": 0,
            "notes":    ustx_notes,
            "curves": [{
                "abbr":      "vel",
                "xs":        vel_xs,
                "ys":        vel_ys,
                "is_sample": False,
            }],
        }],
        "wave_parts": [],
    }


# ---------------------------------------------------------------------------
# YAML serialization with ForceStringQuoting
# ---------------------------------------------------------------------------

if _YAML_OK:
    class _UstxDumper(yaml.Dumper):
        """
        Custom PyYAML Dumper that replicates C# ForceStringQuotingEmitter:
        any string that is empty or case-insensitively matches a YAML 1.1
        boolean / null keyword is emitted with double-quote style, preventing
        OpenUtau from deserializing lyric "True" / "false" / "yes" as booleans.
        """

    def _quoted_str_representer(
        dumper: yaml.Dumper, data: str
    ) -> yaml.ScalarNode:
        if data == "" or data.lower() in _YAML_RESERVED_LC:
            return dumper.represent_scalar(
                "tag:yaml.org,2002:str", data, style='"'
            )
        return dumper.represent_scalar("tag:yaml.org,2002:str", data)

    _UstxDumper.add_representer(str, _quoted_str_representer)


def _write_yaml(ustx_dict: dict, output_path: str | Path) -> None:
    _require_yaml()
    with open(output_path, "w", encoding="utf-8") as fh:
        yaml.dump(
            ustx_dict,
            fh,
            Dumper=_UstxDumper,       # type: ignore[name-defined]
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_lyric(raw: str) -> str:
    """
    Port of UstxExportService.SanitizeLyric().

    Replaces empty strings and YAML-reserved words with the neutral lyric
    'la' so OpenUtau never deserializes a lyric as a boolean or null.
    """
    t = (raw or "").strip()
    if not t or t.lower() in _YAML_RESERVED_LC:
        return "la"
    return t


def _extract_bpm(midi: "mido.MidiFile") -> float:  # type: ignore[name-defined]
    """Port of MidiParserService.ExtractBpm()."""
    for track in midi.tracks:
        for msg in track:
            if msg.type == "set_tempo" and msg.tempo > 0:
                return round(60_000_000 / msg.tempo, 3)
    return 120.0


def _require_mido() -> None:
    if not _MIDO_OK:
        raise ImportError("mido is required: pip install mido")


def _require_yaml() -> None:
    if not _YAML_OK:
        raise ImportError("pyyaml is required: pip install pyyaml")
