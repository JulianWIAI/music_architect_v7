"""
batch_commander.py — Headless CLI for evolutionary fitness-loop generation.

Generates N complete 10-track compositions from a single natural-language
prompt, mutating BPM / key / scale per track while locking the genre.
Each track folder contains the MIDI, an optional USTX vocal scaffold, and a
generation_metadata.json ledger file for downstream scoring scripts.

Usage
-----
python -m src.orchestration.batch_commander \\
    --prompt "aggressive dark trap beat" \\
    --count 100 \\
    --outdir "./batch_output" \\
    [--seed 42] \\
    [--singer "TIGER DS"] \\
    [--seeds-dir "seeds"]
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import List, Optional

from src.composition.composition_engine import CompositionEngine
from src.composition.composition_config import CompositionConfig
from src.composition.genre_constants import GENRE_BPM, GENRE_SCALES
from src.generation.prompt_decoder import SemanticCipher

try:
    from src.export.utau_bridge import export as utau_export, RawNote
    _UTAU_OK = True
except ImportError:
    _UTAU_OK = False

# ── Constants ─────────────────────────────────────────────────────────────────

_ROOTS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
_TPQN  = 480
_PHRASE_GAP_TICKS = _TPQN * 4   # 4-beat silence → new vocal phrase


# ── USTX helpers ─────────────────────────────────────────────────────────────

def _melody_to_raw_notes(melody_notes) -> list:
    """Convert engine melody tuples (beat_pos, dur_beats, pitch, vel) → RawNote list."""
    notes = []
    for beat_pos, dur_beats, pitch, vel in melody_notes:
        tick = int(beat_pos * _TPQN)
        dur  = max(1, int(dur_beats * _TPQN))
        notes.append(RawNote(tick=tick, duration=dur, pitch=pitch, velocity=vel, lyric="la"))
    return notes


def _split_into_phrases(raw_notes: list) -> List[list]:
    """Group RawNote list into sub-lists separated by gaps > 4 beats."""
    if not raw_notes:
        return []
    raw_notes = sorted(raw_notes, key=lambda n: n.tick)
    phrases: List[list] = []
    current = [raw_notes[0]]
    for i in range(1, len(raw_notes)):
        prev = raw_notes[i - 1]
        curr = raw_notes[i]
        gap  = curr.tick - (prev.tick + prev.duration)
        if gap > _PHRASE_GAP_TICKS:
            phrases.append(current)
            current = []
        current.append(curr)
    if current:
        phrases.append(current)
    return [p for p in phrases if p]


# ── Metadata helpers ──────────────────────────────────────────────────────────

def _build_seed_info(engine: CompositionEngine, genre: str) -> dict:
    genre_list   = engine.genre_seeds.get(genre, [])
    sample_size  = min(5, len(genre_list))
    sample_idx   = sorted(random.sample(range(len(genre_list)), sample_size)) if genre_list else []
    return {
        "seeds_dir":                 str(engine.seeds_dir),
        "total_loaded":              len(engine.seeds),
        "genre_seed_count":          len(genre_list),
        "genre_seed_indices_sample": sample_idx,
    }


# ── Core generation loop ──────────────────────────────────────────────────────

def run_batch(
    prompt:    str,
    count:     int,
    outdir:    str,
    seed:      Optional[int] = None,
    singer:    str = "TIGER DS",
    seeds_dir: str = "seeds",
) -> None:
    """
    Generate *count* tracks from *prompt* and write them to *outdir*.

    Parameters
    ----------
    prompt    : Natural-language description (e.g. "dark aggressive trap beat")
    count     : Number of tracks to produce
    outdir    : Root output directory (created if missing)
    seed      : Optional global RNG seed for full reproducibility
    singer    : UTAU singer name embedded in .ustx files
    seeds_dir : Path to the seeds directory loaded by CompositionEngine
    """
    out_path = Path(outdir)
    out_path.mkdir(parents=True, exist_ok=True)

    # ── Engine + seeds ────────────────────────────────────────────────────────
    engine = CompositionEngine(seeds_dir=seeds_dir)
    engine.load_seeds()

    # ── Decode prompt once ────────────────────────────────────────────────────
    cipher      = SemanticCipher()
    base_params = cipher.decode_prompt(prompt)

    target_genre = base_params.genre or "pop"
    bpm_range    = GENRE_BPM.get(target_genre, (100, 130))
    target_bpm   = (
        base_params.bpm
        if base_params.bpm is not None
        else (bpm_range[0] + bpm_range[1]) / 2.0
    )
    target_scale = base_params.scale_hint
    strict_scale = target_scale is not None
    base_tension     = base_params.tension_multiplier if base_params.tension_multiplier is not None else 0.5
    base_complexity  = base_params.complexity         if base_params.complexity         is not None else 5

    if seed is not None:
        random.seed(seed)

    print(f"Batch Commander — prompt: '{prompt}'")
    print(f"  genre={target_genre}  bpm~{target_bpm:.1f}  "
          f"scale={'locked:'+target_scale if strict_scale else 'flexible'}  count={count}")
    if not _UTAU_OK:
        print("  [INFO] USTX export disabled (mido/pyyaml not installed)")

    batch_tracks: list = []

    for i in range(count):
        track_name = f"track_{i:03d}"
        track_dir  = out_path / track_name
        track_dir.mkdir(exist_ok=True)

        # ── Bounded mutation ──────────────────────────────────────────────────
        mutated_bpm       = float(max(bpm_range[0], min(bpm_range[1],
                                      target_bpm + random.uniform(-5.0, 5.0))))
        mutated_root      = random.choice(_ROOTS)
        genre_scale_pool  = GENRE_SCALES.get(target_genre, ["major", "minor"])
        mutated_scale     = target_scale if strict_scale else random.choice(genre_scale_pool)
        mutated_key       = f"{mutated_root} {mutated_scale}"
        mutated_tension   = float(max(0.0, min(1.5, base_tension + random.uniform(-0.2, 0.2))))
        mutated_complexity= random.randint(3, 9)
        mutated_mutation  = round(random.uniform(0.1, 0.7), 3)
        mutated_humanize  = round(random.uniform(0.4, 0.9), 3)
        mutated_seed      = random.randint(0, 999_999)

        # ── Build config ──────────────────────────────────────────────────────
        config = CompositionConfig(
            genre              = target_genre,
            bpm                = mutated_bpm,
            key                = mutated_key,
            complexity         = mutated_complexity,
            tension_multiplier = mutated_tension,
            mutation           = mutated_mutation,
            humanize_amount    = mutated_humanize,
            seed_value         = mutated_seed,
        )
        config.tracks['arp']['enabled'] = True

        t_start = time.time()

        # ── Compose ───────────────────────────────────────────────────────────
        try:
            comp = engine.compose(config)
        except Exception as exc:
            print(f"  [ERROR] Compose failed for {track_name}: {exc}")
            continue

        # ── Export MIDI ───────────────────────────────────────────────────────
        midi_path = track_dir / f"{track_name}.mid"
        try:
            engine.export_midi(comp, str(midi_path))
        except Exception as exc:
            print(f"  [ERROR] MIDI export failed for {track_name}: {exc}")

        # ── Export USTX ───────────────────────────────────────────────────────
        ustx_path = track_dir / f"{track_name}.ustx"
        if _UTAU_OK:
            melody_notes = comp["tracks"].get("04_Melody", [])
            if melody_notes:
                try:
                    raw_notes = _melody_to_raw_notes(melody_notes)
                    phrases   = _split_into_phrases(raw_notes)
                    if phrases:
                        utau_export(
                            output_path = ustx_path,
                            phrases     = phrases,
                            tpqn        = _TPQN,
                            bpm         = comp["config"]["bpm"],
                            song_name   = track_name,
                            singer      = singer,
                        )
                except Exception as exc:
                    print(f"  [WARN] USTX export failed for {track_name}: {exc}")

        t_elapsed = round(time.time() - t_start, 3)

        # ── Intelligence ledger ───────────────────────────────────────────────
        track_note_counts = {k: len(v) for k, v in comp["tracks"].items()}
        total_notes       = sum(track_note_counts.values())

        metadata = {
            "track_index":    i,
            "prompt":         prompt,
            "prompt_decoded": base_params.summary(),
            "generation_params": {
                "genre":              target_genre,
                "bpm":                comp["config"]["bpm"],
                "key":                mutated_key,
                "root":               mutated_root,
                "scale":              mutated_scale,
                "scale_locked":       strict_scale,
                "complexity":         mutated_complexity,
                "tension_multiplier": round(mutated_tension, 3),
                "mutation":           mutated_mutation,
                "seed_value":         mutated_seed,
                "humanize_amount":    mutated_humanize,
            },
            "seed_info":         _build_seed_info(engine, target_genre),
            "outputs": {
                "midi_path":          str(midi_path.relative_to(out_path)),
                "ustx_path":          str(ustx_path.relative_to(out_path)) if ustx_path.exists() else None,
                "track_note_counts":  track_note_counts,
                "total_notes":        total_notes,
            },
            "structure":          comp["structure"],
            "chord_progression":  comp["chord_progression"][:32],
            "generation_timestamp":          time.strftime("%Y-%m-%dT%H:%M:%S"),
            "generation_duration_seconds":   t_elapsed,
        }

        meta_path = track_dir / "generation_metadata.json"
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(metadata, fh, indent=2)

        batch_tracks.append({
            "track_index": i,
            "track_name":  track_name,
            "bpm":         comp["config"]["bpm"],
            "key":         mutated_key,
            "total_notes": total_notes,
        })

        print(f"  [{i+1:>4}/{count}] {track_name}  bpm={mutated_bpm:.1f}  "
              f"key={mutated_key:<14}  notes={total_notes}  ({t_elapsed:.2f}s)")

    # ── Batch manifest ────────────────────────────────────────────────────────
    manifest = {
        "prompt":       prompt,
        "count":        count,
        "base_decoded": base_params.summary(),
        "base_params": {
            "genre":              target_genre,
            "bpm":                round(target_bpm, 2),
            "scale":              target_scale,
            "scale_locked":       strict_scale,
            "tension_multiplier": round(base_tension, 3),
            "complexity":         base_complexity,
        },
        "tracks": batch_tracks,
    }
    manifest_path = out_path / "batch_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    print(f"\nDone. {len(batch_tracks)}/{count} tracks written to '{outdir}'")
    print(f"Manifest: {manifest_path}")


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="batch_commander",
        description="Music Architect — headless evolutionary batch generator",
    )
    parser.add_argument("--prompt",    required=True,     help="Natural-language track description")
    parser.add_argument("--count",     type=int, default=10, help="Number of tracks to generate (default: 10)")
    parser.add_argument("--outdir",    default="./batch_output", help="Output directory (default: ./batch_output)")
    parser.add_argument("--seed",      type=int, default=None,   help="Global RNG seed for reproducibility")
    parser.add_argument("--singer",    default="TIGER DS",       help="UTAU singer name (default: TIGER DS)")
    parser.add_argument("--seeds-dir", default="seeds",          dest="seeds_dir",
                        help="Path to seeds directory (default: seeds)")

    args = parser.parse_args()
    run_batch(
        prompt    = args.prompt,
        count     = args.count,
        outdir    = args.outdir,
        seed      = args.seed,
        singer    = args.singer,
        seeds_dir = args.seeds_dir,
    )


if __name__ == "__main__":
    main()
