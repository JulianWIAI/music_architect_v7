"""
production_batch_commercial.py — 3-generation evolutionary chain for
Pop, House, and EDM, targeting bright commercial sync-licensing music.

Harmonic shift vs. the Trap/Hip-Hop pipeline
----------------------------------------------
The Trap/Hip-Hop chain uses dark, aggressive modes (Phrygian, pentatonic_minor,
dorian) tuned to 808-driven sub-bass production.  Commercial sync requires the
opposite: clean diatonic brightness, upbeat energy, minimal dissonance.

This script enforces the harmonic shift by patching GENRE_SCALES in-place
at import time (before any CompositionEngine or golden-pool code runs), locking
all three target genres to bright scale pools only:

  Pop   → ['major', 'lydian', 'pentatonic_major', 'mixolydian']
  House → ['major', 'mixolydian', 'pentatonic_major', 'dorian']  (dorian
          is kept because house's characteristic minor-to-major Dm7-G7
          moves sit within dorian's bright, funky colour)
  EDM   → ['major', 'lydian', 'pentatonic_major', 'mixolydian']

Excluded explicitly: minor, phrygian, harmonic_minor, melodic_minor,
pentatonic_minor, blues, japanese, chromatic.

Generation schedule
-------------------
  Gen 1 :  100 tracks / genre  — free exploration, bright scales only
  Gen 2 :  250 tracks / genre  — top 20 % Gen 1 seeds, mut=0.10
  Gen 3 :  500 tracks / genre  — top 20 % Gen 2 seeds, mut=0.05

After Gen 3:
  • Grade all tracks with calibrated grader + genre-aware config
  • Filter winners at score_floor = 45.0
  • Generate one vocal_mask=True sibling per winner (seed-locked, same params)

Output layout
-------------
  commercial_run/
    gen1/pop/     100 track dirs
    gen1/house/   100 track dirs
    gen1/edm/     100 track dirs
    gen2/pop/     250 track dirs
    gen2/house/   250 track dirs
    gen2/edm/     250 track dirs
    gen3/pop/     500 track dirs
    gen3/house/   500 track dirs
    gen3/edm/     500 track dirs
    gen3/vocal_ready/pop/     sibling dirs (winners only)
    gen3/vocal_ready/house/   sibling dirs (winners only)
    gen3/vocal_ready/edm/     sibling dirs (winners only)
    commercial_chain_manifest.json

Resource throttling
-------------------
Each compose call runs inside a daemon thread with a 30-second watchdog.
Hung seeds are logged to watchdog_log.json and skipped automatically.

CLI
---
python production_batch_commercial.py
python production_batch_commercial.py --out-dir my_commercial_run
python production_batch_commercial.py --gen1 50 --gen2 100 --gen3 200
python production_batch_commercial.py --skip-to-gen 3
python production_batch_commercial.py --score-floor 50.0
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
#  BRIGHT SCALE ENFORCEMENT — applied BEFORE any composition import
# ─────────────────────────────────────────────────────────────────────────────
# Python dicts are mutable objects shared by reference.  Because composition_engine
# imports GENRE_SCALES with `from genre_constants import GENRE_SCALES`, it holds a
# reference to the same dict object.  Mutating the dict here propagates instantly
# into both _config_free (uses GENRE_SCALES.get(...)) and config_from_golden
# (reads GENRE_SCALES for the 25% scale mutation step).  No monkey-patching of
# individual functions is required.

from src.composition.genre_constants import GENRE_SCALES as _GS

# Store originals so restore() can undo the patch if needed.
_ORIGINAL_SCALES: Dict[str, list] = {g: list(v) for g, v in _GS.items()}

# Bright-only pools per target genre.
BRIGHT_SCALES: Dict[str, List[str]] = {
    'pop':   ['major', 'lydian', 'pentatonic_major', 'mixolydian'],
    'house': ['major', 'mixolydian', 'pentatonic_major', 'dorian'],
    'edm':   ['major', 'lydian', 'pentatonic_major', 'mixolydian'],
}

# Dark scales we actively exclude (logged in snapshot for audit trail).
DARK_SCALES: set = {
    'minor', 'phrygian', 'harmonic_minor', 'melodic_minor',
    'pentatonic_minor', 'blues', 'japanese', 'chromatic',
}


def _apply_bright_patch() -> None:
    """Overwrite GENRE_SCALES entries for Pop/House/EDM with bright-only pools."""
    for genre, bright_pool in BRIGHT_SCALES.items():
        _GS[genre] = bright_pool


def _restore_scale_patch() -> None:
    """Restore the original GENRE_SCALES (useful for test teardown)."""
    for genre, original in _ORIGINAL_SCALES.items():
        _GS[genre] = original


# Apply immediately at module load — before any golden config or free config runs.
_apply_bright_patch()


# ─────────────────────────────────────────────────────────────────────────────
#  Main imports (after scale patch is live)
# ─────────────────────────────────────────────────────────────────────────────

from src.orchestration.batch_commander import (
    _config_free,
    _config_from_pool,
    _build_seed_info,
    _melody_to_raw_notes,
    _split_into_phrases,
    _TPQN,
)
from src.orchestration.telemetry_grader_midi import _process_genre
from src.composition.composition_engine import CompositionEngine, GoldenMatrixPool
from src.composition.composition_config import CompositionConfig
from src.composition.genre_constants import GENRE_BPM

try:
    from src.core.orchestrator import Orchestrator as _Orchestrator
    _ORC_AVAILABLE = True
except ImportError:
    _ORC_AVAILABLE = False

try:
    from src.export.utau_bridge import export as _utau_export, RawNote as _RawNote
    _UTAU_OK = True
except ImportError:
    _UTAU_OK = False

# ─────────────────────────────────────────────────────────────────────────────
#  Pipeline constants
# ─────────────────────────────────────────────────────────────────────────────

COMMERCIAL_GENRES: List[str] = ['pop', 'house', 'edm']

# Genre-appropriate sync-licensing prompts for SemanticCipher (not used for
# scale selection — scale is locked via BRIGHT_SCALES — but kept for metadata).
GENRE_PROMPTS: Dict[str, str] = {
    'pop':   'bright upbeat pop commercial major key 120bpm',
    'house': 'uplifting house music major key 124bpm four on floor',
    'edm':   'bright festival EDM major key 130bpm euphoric drop',
}

# Tracks per genre per generation.
GEN_SIZES: List[int] = [100, 250, 500]

# Top fraction of each generation that seeds the next.
TOP_PCT: float = 0.20

# Mutation schedule: broader in Gen1→Gen2, tight in Gen2→Gen3.
# Index 0 = used when producing Gen2 FROM Gen1 seeds.
# Index 1 = used when producing Gen3 FROM Gen2 seeds.
MUT_SCHEDULE: List[float] = [0.10, 0.05]

# Fitness floor for the Gen3 sibling pass (vocal_mask=True).
SCORE_FLOOR: float = 45.0

# Watchdog timeout per track (seconds).
WATCHDOG_S: int = 30

# Default output root (separate from evolutionary_run/ and production_run/).
DEFAULT_OUT_DIR: Path = Path("commercial_run")


# ─────────────────────────────────────────────────────────────────────────────
#  Watchdog-protected compose
# ─────────────────────────────────────────────────────────────────────────────

import threading


def _compose_watchdog(orc, config, seed_pool_path: Optional[str],
                      timeout: int = WATCHDOG_S) -> dict:
    """
    Run orc.compose(config) in a daemon thread with a timeout guard.

    Returns the composition dict on success.
    Raises TimeoutError if the thread is still alive after `timeout` seconds.
    Hung threads are background daemons — they will not block process exit.
    """
    result: List[Optional[dict]]      = [None]
    error:  List[Optional[Exception]] = [None]

    def _worker() -> None:
        try:
            result[0] = orc.compose(config, seed_pool_path=seed_pool_path)
        except Exception as exc:
            error[0] = exc

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout)

    if t.is_alive():
        raise TimeoutError(f"Compose exceeded {timeout}s  (seed={config.seed_value})")
    if error[0] is not None:
        raise error[0]
    return result[0]


# ─────────────────────────────────────────────────────────────────────────────
#  Bright-locked config builders
# ─────────────────────────────────────────────────────────────────────────────

def _config_bright_free(genre: str) -> tuple:
    """
    Free-exploration config with bright scale enforcement.

    Delegates to batch_commander._config_free, then verifies the chosen scale
    is in the bright pool.  If the 25% mutation step drifted to a dark scale
    (shouldn't happen after the GENRE_SCALES patch, but defensive), re-draws.

    Returns (config, params, None) identical to _config_free signature.
    """
    bpm_range  = GENRE_BPM.get(genre, (100, 130))
    target_bpm = sum(bpm_range) / 2.0

    config, params, gs = _config_free(
        genre, target_bpm, bpm_range,
        target_scale=None, strict_scale=False, base_tension=0.3,
    )

    # Safety re-lock: if a dark scale slipped through, replace with bright.
    if params['scale'] in DARK_SCALES:
        bright_pool = BRIGHT_SCALES.get(genre, ['major'])
        new_scale   = random.choice(bright_pool)
        new_root    = params['root']
        config.key  = f"{new_root} {new_scale}"
        params['scale'] = new_scale
        params['key']   = config.key

    return config, params, gs


def _config_bright_injection(pool: GoldenMatrixPool, genre: str) -> tuple:
    """
    Golden-pool injection with bright scale enforcement.

    Delegates to batch_commander._config_from_pool, then re-locks any dark
    scale that crept in via the 25% mutation step.

    Returns (config, params, golden_source).
    """
    config, params, gs = _config_from_pool(pool)

    if params['scale'] in DARK_SCALES:
        bright_pool  = BRIGHT_SCALES.get(genre, ['major'])
        new_scale    = random.choice(bright_pool)
        new_root     = params['root']
        config.key   = f"{new_root} {new_scale}"
        params['scale'] = new_scale
        params['key']   = config.key

    return config, params, gs


# ─────────────────────────────────────────────────────────────────────────────
#  Single-generation runner
# ─────────────────────────────────────────────────────────────────────────────

def _run_commercial_gen(
    genre:            str,
    count:            int,
    outdir:           Path,
    engine:           CompositionEngine,
    orc,
    gen_label:        str,
    seed_pool_path:   Optional[str] = None,
    mut_factor:       float = 0.0,
    vocal_mask:       bool  = False,
    generation_level: int   = 1,
) -> List[dict]:
    """
    Generate `count` commercial tracks for `genre` into `outdir`.

    Uses bright-locked free exploration (seed_pool_path=None) or bright-locked
    golden injection (seed_pool_path provided).

    Returns the list of per-track manifest entries.
    """
    outdir.mkdir(parents=True, exist_ok=True)

    # ── Batch-level resume guard: entire genre batch already complete ─────────
    _batch_manifest = outdir / "batch_manifest.json"
    if _batch_manifest.exists():
        print(f"\n  [{gen_label.upper()}] {genre.upper()} — batch_manifest.json found, already complete — skipping")
        existing = json.loads(_batch_manifest.read_text(encoding="utf-8"))
        return existing.get("tracks", [])

    pool: Optional[GoldenMatrixPool] = None
    if seed_pool_path and Path(seed_pool_path).exists():
        pool = GoldenMatrixPool.from_report(seed_pool_path, mut_factor)

    mode_label = (
        f"golden injection  pool={pool.summary()}  bright-locked"
        if pool else f"free exploration  bright-scales={BRIGHT_SCALES[genre]}"
    )
    print(f"\n  [{gen_label.upper()}] {genre.upper()}  {count} tracks -> {outdir}")
    print(f"  {mode_label}")

    batch_tracks:    List[dict] = []
    timed_out_seeds: List[int]  = []

    for i in range(count):
        track_name = f"track_{i:03d}"
        track_dir  = outdir / track_name
        track_dir.mkdir(exist_ok=True)

        # ── Track-level resume guard: track already rendered ──────────────────
        _meta_path = track_dir / "generation_metadata.json"
        if _meta_path.exists():
            try:
                _existing = json.loads(_meta_path.read_text(encoding="utf-8"))
                _gp = _existing.get("generation_params", {})
                batch_tracks.append({
                    "track_index":      i,
                    "track_name":       track_name,
                    "render_seed":      _gp.get("seed_value", 0),
                    "generation_level": generation_level,
                    "bpm":              round(_gp.get("bpm", 0), 2),
                    "key":              _gp.get("key", ""),
                    "scale":            _gp.get("scale", ""),
                    "total_notes":      _existing.get("outputs", {}).get("total_notes", 0),
                    "elapsed_s":        _existing.get("generation_duration_seconds", 0),
                    "vocal_mask":       vocal_mask,
                    "golden_source":    _existing.get("golden_source"),
                })
            except Exception:
                pass  # corrupt metadata — re-render this track
            else:
                continue

        # ── Build config (bright-locked) ──────────────────────────────────────
        if pool is not None:
            config, gen_params, golden_source = _config_bright_injection(pool, genre)
        else:
            config, gen_params, golden_source = _config_bright_free(genre)

        # Force genre so prompt-decoded genre doesn't override
        config.genre    = genre
        gen_params['genre'] = genre
        config.vocal_mask   = vocal_mask

        t_start = time.time()

        # ── Compose (watchdog-protected) ──────────────────────────────────────
        try:
            comp = _compose_watchdog(orc, config, seed_pool_path, WATCHDOG_S)
        except TimeoutError as exc:
            elapsed = time.time() - t_start
            seed    = gen_params["seed_value"]
            print(f"  [WATCHDOG] [{i+1}/{count}] {track_name}  seed={seed}  ({elapsed:.0f}s) — skipped")
            timed_out_seeds.append(seed)
            (track_dir / "watchdog_timeout.json").write_text(
                json.dumps({"seed": seed, "elapsed_s": round(elapsed, 1)}),
                encoding="utf-8",
            )
            continue
        except Exception as exc:
            print(f"  [ERROR] [{i+1}/{count}] {track_name}: {exc}")
            continue

        t_elapsed = round(time.time() - t_start, 3)
        gen_params["bpm"] = comp["config"]["bpm"]

        # ── MIDI export ───────────────────────────────────────────────────────
        midi_path = track_dir / f"{track_name}.mid"
        try:
            engine.export_midi(comp, str(midi_path))
        except Exception as exc:
            print(f"  [WARN] MIDI export failed {track_name}: {exc}")

        # ── USTX export (optional) ────────────────────────────────────────────
        if _UTAU_OK:
            melody_notes = comp["tracks"].get("04_Melody", [])
            if melody_notes:
                try:
                    phrases = _split_into_phrases(_melody_to_raw_notes(melody_notes))
                    if phrases:
                        _utau_export(
                            output_path = track_dir / f"{track_name}.ustx",
                            phrases     = phrases,
                            tpqn        = _TPQN,
                            bpm         = comp["config"]["bpm"],
                            song_name   = track_name,
                            singer      = "TIGER DS",
                        )
                except Exception:
                    pass

        # ── Per-track metadata ────────────────────────────────────────────────
        render_seed       = gen_params["seed_value"]
        track_note_counts = {k: len(v) for k, v in comp["tracks"].items()}
        total_notes       = sum(track_note_counts.values())

        metadata: dict = {
            "track_index":       i,
            "render_seed":       render_seed,
            "generation":        gen_label,
            "generation_level":  generation_level,
            "genre":             genre,
            "commercial_run":    True,
            "bright_scale_pool": BRIGHT_SCALES.get(genre, ['major']),
            "generation_mode":   "golden_injection" if pool else "free_exploration",
            "generation_params": gen_params,
            "seed_info":         _build_seed_info(engine, genre),
            "outputs": {
                "midi_path":         str(midi_path.relative_to(outdir)),
                "track_note_counts": track_note_counts,
                "total_notes":       total_notes,
            },
            "structure":          comp["structure"],
            "chord_progression":  comp["chord_progression"][:32],
            "generation_timestamp":        time.strftime("%Y-%m-%dT%H:%M:%S"),
            "generation_duration_seconds": t_elapsed,
            "vocal_mask_active":           vocal_mask,
        }
        if golden_source:
            metadata["golden_source"] = golden_source

        (track_dir / "generation_metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

        batch_tracks.append({
            "track_index":      i,
            "track_name":       track_name,
            "render_seed":      render_seed,
            "generation_level": generation_level,
            "bpm":              round(gen_params["bpm"], 2),
            "key":              gen_params["key"],
            "scale":            gen_params["scale"],
            "total_notes":      total_notes,
            "elapsed_s":        t_elapsed,
            "vocal_mask":       vocal_mask,
            "golden_source":    golden_source,
        })

        print(
            f"  [{i+1:>4}/{count}] {track_name}"
            f"  bpm={gen_params['bpm']:.1f}"
            f"  key={gen_params['key']:<22}"
            f"  notes={total_notes}"
            f"  seed={render_seed}"
            + (f"  [#{golden_source['rank']} s={golden_source['score']:.1f}]"
               if golden_source else "")
            + f"  ({t_elapsed:.2f}s)"
        )

    # ── Write batch manifest ──────────────────────────────────────────────────
    manifest = {
        "generation":        gen_label,
        "generation_level":  generation_level,
        "genre":             genre,
        "vocal_mask":        vocal_mask,
        "bright_scale_pool": BRIGHT_SCALES.get(genre, ['major']),
        "count_requested":   count,
        "count_completed":   len(batch_tracks),
        "timed_out_count":   len(timed_out_seeds),
        "seed_pool":         seed_pool_path,
        "mutation_factor":   mut_factor,
        "tracks":            batch_tracks,
    }
    (outdir / "batch_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    if timed_out_seeds:
        (outdir / "watchdog_log.json").write_text(
            json.dumps({"timed_out_seeds": timed_out_seeds}), encoding="utf-8"
        )
        print(f"\n  Watchdog: {len(timed_out_seeds)} seed(s) timed out")

    return batch_tracks


# ─────────────────────────────────────────────────────────────────────────────
#  Grade + pool builder (adapted from omni_render._grade_and_pool)
# ─────────────────────────────────────────────────────────────────────────────

def _archive_pool(evo_pool: dict, genre_dir: Path, mut_factor: float) -> None:
    """
    Archive the evolutionary pool to generation_archive/<genre>/ with a
    timestamped filename so each generation's seeds are permanently preserved.

    Uses the shared generation_archive/ root (same location as trap/hiphop
    archives) — filenames include gen_tag and genre to avoid collisions.
    """
    genre   = genre_dir.name
    gen_tag = genre_dir.parent.name    # 'gen1', 'gen2', 'gen3'
    ts      = time.strftime("%Y%m%d_%H%M%S")
    n_keep  = evo_pool['golden_count']

    archive_dir = Path("generation_archive") / genre
    archive_dir.mkdir(parents=True, exist_ok=True)

    name  = f"{gen_tag}_{genre}_commercial_top{n_keep}_mut{int(mut_factor*100):03d}_{ts}.json"
    path  = archive_dir / name
    path.write_text(json.dumps(evo_pool, indent=2), encoding="utf-8")
    print(f"  Archive -> generation_archive/{genre}/{name}")


def _grade_and_pool(
    genre_dir:  Path,
    next_mut:   float,
    top_pct:    float = TOP_PCT,
) -> Tuple[dict, Path]:
    """
    Grade a completed generation directory and produce:
      - math_fitness_report.json   (full grader output)
      - evolutionary_pool.json     (top top_pct% golden matrices)

    Returns (report_dict, evolutionary_pool_path).
    """
    print(f"\n  Grading {genre_dir.name.upper()}/{genre_dir.parent.name.upper()} ...")
    report     = _process_genre(genre_dir)
    n_scored   = report["tracks_scored"]

    report_path = genre_dir / "math_fitness_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"  {n_scored} tracks scored  ->  {report_path.name}")

    # Top-5 summary
    leaderboard = report.get("leaderboard", [])
    if leaderboard:
        print(f"  {'Rank':<5} {'Track':<14} {'Score':>7}  {'Key':<20}")
        print(f"  {'-'*50}")
        for e in leaderboard[:5]:
            key_str = e.get("generation_params", {}).get("key", "?")
            print(f"  #{e['rank']:<4} {e['track_name']:<14} {e['score']:>7.2f}  {key_str:<20}")

    # Select top fraction for next generation
    n_keep = max(1, int(len(leaderboard) * top_pct))
    top    = leaderboard[:n_keep]

    if top:
        print(f"\n  Top {n_keep}/{n_scored} selected ({top_pct*100:.0f}%)"
              f"  score range [{top[-1]['score']:.2f} – {top[0]['score']:.2f}]")

        # Verify all top seeds have bright scales (audit step)
        dark_seeds = [
            e for e in top
            if e.get("generation_params", {}).get("scale", "major") in DARK_SCALES
        ]
        if dark_seeds:
            print(f"  [WARN] {len(dark_seeds)} top-seed(s) have dark scales — "
                  f"will be re-locked on next gen injection")
        else:
            bright_scales_used = {
                e.get("generation_params", {}).get("scale", "major") for e in top
            }
            print(f"  Bright scales in top pool: {sorted(bright_scales_used)}")

    # Build evolutionary pool
    golden_matrices = [
        {
            "rank":              i + 1,
            "track_name":        e["track_name"],
            "score":             e["score"],
            "generation_params": e["generation_params"],
            "seed_info":         {},
            "structure":         [],
            "chord_progression": [],
            "breakdown":         e.get("penalties", {}),
        }
        for i, e in enumerate(top)
    ]

    evo_pool = {
        "genre":           genre_dir.name,
        "source_gen":      str(genre_dir),
        "commercial_run":  True,
        "bright_scales":   BRIGHT_SCALES.get(genre_dir.name, ['major']),
        "top_pct":         top_pct,
        "tracks_scored":   n_scored,
        "golden_count":    n_keep,
        "mutation_factor": next_mut,
        "golden_matrices": golden_matrices,
    }

    evo_pool_path = genre_dir / "evolutionary_pool.json"
    evo_pool_path.write_text(json.dumps(evo_pool, indent=2), encoding="utf-8")
    print(f"  Evolutionary pool ({n_keep} seeds) -> {evo_pool_path.name}")

    # Merge fitness scores back into batch_manifest.json
    manifest_path = genre_dir / "batch_manifest.json"
    if manifest_path.exists():
        try:
            manifest  = json.loads(manifest_path.read_text(encoding="utf-8"))
            score_map = {e["track_name"]: e for e in leaderboard}
            for t in manifest.get("tracks", []):
                lb = score_map.get(t.get("track_name"), {})
                t["fitness_score"] = lb.get("score")
                t["penalties"]     = lb.get("penalties", {})
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        except Exception as exc:
            print(f"  [WARN] Could not merge scores into manifest: {exc}")

    # Archive to generation_archive/<genre>/
    _archive_pool(evo_pool, genre_dir, next_mut)

    return report, evo_pool_path


# ─────────────────────────────────────────────────────────────────────────────
#  Gen 3 Sibling Pass (vocal_mask = True for winners above score floor)
# ─────────────────────────────────────────────────────────────────────────────

def _run_sibling_pass(
    winner_dirs: List[Path],
    out_root:    Path,
    genre:       str,
    engine:      CompositionEngine,
    orc,
    prod_mut:    float = MUT_SCHEDULE[-1],
) -> List[dict]:
    """
    Render one vocal-ready sibling per Gen 3 winner.

    The winner's exact seed_value + generation_params are replayed with
    vocal_mask=True, guaranteeing a perfectly paired instrumental+vocal set.
    Bright scale re-lock is applied here too for robustness.
    """
    outdir = out_root / genre
    outdir.mkdir(parents=True, exist_ok=True)

    manifest_entries: List[dict] = []
    total = len(winner_dirs)
    print(f"\n  [VOCAL SIBLINGS] {genre.upper()}  {total} winners -> {outdir}")

    for idx, win_dir in enumerate(winner_dirs):
        meta_path = win_dir / "generation_metadata.json"
        if not meta_path.exists():
            print(f"  [SKIP] No metadata in {win_dir.name}")
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  [SKIP] Cannot read {win_dir.name}: {exc}")
            continue

        params = meta.get("generation_params", {})

        # Re-lock scale to bright (defensive — winner's scale should already be bright)
        scale = params.get("scale", "major")
        if scale in DARK_SCALES:
            scale       = random.choice(BRIGHT_SCALES.get(genre, ['major']))
            params['scale'] = scale
            params['key']   = f"{params.get('root', 'C')} {scale}"

        track_name = f"sibling_{idx:03d}_{win_dir.name}"
        track_dir  = outdir / track_name
        track_dir.mkdir(exist_ok=True)

        config = CompositionConfig(
            genre              = params.get("genre", genre),
            bpm                = params.get("bpm"),
            key                = params.get("key"),
            complexity         = params.get("complexity", 5),
            mutation           = prod_mut,
            seed_value         = params.get("seed_value"),
            tension_multiplier = params.get("tension_multiplier", 0.0),
            humanize_amount    = params.get("humanize_amount", 0.6),
            vocal_mask         = True,
        )

        t_start = time.time()
        try:
            comp = _compose_watchdog(orc, config, None, WATCHDOG_S)
        except TimeoutError:
            print(f"  [WATCHDOG] {track_name} timed out — skipped")
            continue
        except Exception as exc:
            print(f"  [ERROR] {track_name}: {exc}")
            continue
        t_elapsed = round(time.time() - t_start, 3)

        midi_path = track_dir / f"{track_name}.mid"
        try:
            engine.export_midi(comp, str(midi_path))
        except Exception as exc:
            print(f"  [WARN] MIDI export failed {track_name}: {exc}")

        sibling_meta = {
            "sibling_index":               idx,
            "source_instrumental":         str(win_dir),
            "source_seed":                 params.get("seed_value"),
            "genre":                       genre,
            "commercial_run":              True,
            "bright_scale_pool":           BRIGHT_SCALES.get(genre, ['major']),
            "generation_params":           params,
            "vocal_mask_active":           True,
            "generation_timestamp":        time.strftime("%Y-%m-%dT%H:%M:%S"),
            "generation_duration_seconds": t_elapsed,
        }
        (track_dir / "generation_metadata.json").write_text(
            json.dumps(sibling_meta, indent=2), encoding="utf-8"
        )

        manifest_entries.append({
            "track_name":          track_name,
            "source_instrumental": win_dir.name,
            "seed":                params.get("seed_value"),
            "bpm":                 round(float(params.get("bpm") or 0), 2),
            "key":                 params.get("key"),
            "elapsed_s":           t_elapsed,
        })

        print(
            f"  [{idx+1:>3}/{total}] {track_name}"
            f"  bpm={float(params.get('bpm') or 0):.1f}"
            f"  key={str(params.get('key', '?')):<22}"
            f"  seed={params.get('seed_value')}"
            f"  ({t_elapsed:.2f}s)"
        )

    return manifest_entries


# ─────────────────────────────────────────────────────────────────────────────
#  Pre-flight validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_commercial_pipeline() -> bool:
    """
    Confirm all pipeline requirements before committing to a multi-hour run.
    Returns True only if every check passes.
    """
    import inspect
    checks: List[Tuple[str, bool]] = []

    # 1. Bright scale patch is live
    ok1 = all(_GS.get(g) == BRIGHT_SCALES[g] for g in COMMERCIAL_GENRES)
    checks.append(("Bright scale patch active (Pop/House/EDM)", ok1))

    # 2. No dark scales in any commercial genre pool
    ok2 = not any(
        s in DARK_SCALES
        for g in COMMERCIAL_GENRES
        for s in _GS.get(g, [])
    )
    checks.append(("No dark scales in commercial pools", ok2))

    # 3. IntroVarietyProtocol (80/20) present in engine
    try:
        from src.composition.composition_engine import CompositionEngine
        src_text = inspect.getsource(CompositionEngine.generate_chord_track)
        ok3 = "_INTRO_VARIETY_PCT" in src_text and "_INTRO_SIGNATURE" in src_text
    except Exception:
        ok3 = False
    checks.append(("IntroVarietyProtocol (80/20 split)", ok3))

    # 4. BillboardIntroMatrix registered with 4 archetypes
    try:
        from src.generators.intro import BillboardIntroMatrix
        ok4 = len(BillboardIntroMatrix.ARCHETYPE_NAMES) >= 4
    except Exception:
        ok4 = False
    checks.append(("BillboardIntroMatrix (4 archetypes)", ok4))

    # 5. Pop/House/EDM have Billboard archetypes in their genre pools
    try:
        from src.composition.intro_archetype_registry import get_archetypes, _BILLBOARD_NAMES
        ok5 = all(
            any(a in _BILLBOARD_NAMES for a in (get_archetypes(g) or ()))
            for g in COMMERCIAL_GENRES
        )
    except Exception:
        ok5 = False
    checks.append(("Registry: Billboard names in Pop/House/EDM pools", ok5))

    # 6. Genre-aware grader config exists for all commercial genres
    try:
        from src.orchestration.genre_grader_config import get_grader_config
        ok6 = all(
            get_grader_config(g) is not None for g in COMMERCIAL_GENRES
        )
    except Exception:
        ok6 = False
    checks.append(("Genre-aware grader config (Pop/House/EDM)", ok6))

    # 7. Watchdog > 0
    checks.append(("Watchdog resource throttling", WATCHDOG_S > 0))

    all_pass = all(ok for _, ok in checks)
    print("\n  Commercial Pipeline Pre-flight Check")
    print(f"  {'Check':<45} {'Status'}")
    print(f"  {'-'*56}")
    for label, ok in checks:
        print(f"  {label:<45} {'PASS' if ok else 'FAIL'}")
    print()
    return all_pass


# ─────────────────────────────────────────────────────────────────────────────
#  System snapshot (audit trail)
# ─────────────────────────────────────────────────────────────────────────────

def write_commercial_snapshot(out_path: Path, out_root: Path) -> dict:
    """Write a point-in-time snapshot of the commercial chain configuration."""
    try:
        git_hash = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except Exception:
        git_hash = "unavailable"

    import hashlib

    def _sha(p: Path) -> str:
        try:
            return hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        except OSError:
            return "unreadable"

    src_files: dict = {}
    for p in sorted(Path("src").rglob("*.py")):
        src_files[p.as_posix()] = {"sha256_prefix": _sha(p), "size_bytes": p.stat().st_size}
    for name in ("production_batch_commercial.py", "omni_render.py"):
        p = Path(name)
        if p.exists():
            src_files[name] = {"sha256_prefix": _sha(p), "size_bytes": p.stat().st_size}

    snapshot = {
        "snapshot_type": "commercial_chain_pre_run",
        "timestamp":     time.strftime("%Y-%m-%dT%H:%M:%S"),
        "git_commit":    git_hash,
        "target_genres": COMMERCIAL_GENRES,
        "out_root":      str(out_root.resolve()),
        "harmonic_config": {
            "description":  "Bright commercial sync — Major/Lydian/Mixolydian only",
            "bright_pools": BRIGHT_SCALES,
            "excluded_dark_scales": sorted(DARK_SCALES),
            "patch_method": "in-place mutation of genre_constants.GENRE_SCALES shared dict",
        },
        "generation_schedule": {
            "gen1_tracks_per_genre": GEN_SIZES[0],
            "gen2_tracks_per_genre": GEN_SIZES[1],
            "gen3_tracks_per_genre": GEN_SIZES[2],
            "top_pct":               TOP_PCT,
            "mut_gen1_to_gen2":      MUT_SCHEDULE[0],
            "mut_gen2_to_gen3":      MUT_SCHEDULE[1],
            "sibling_score_floor":   SCORE_FLOOR,
        },
        "intro_variety_protocol": {
            "variety_pct":   80,
            "signature_pct": 20,
            "billboard_archetypes": [
                "pedal_point",
                "syncopated_anticipation",
                "four_chord_loop",
                "inverted_filter_sweep",
            ],
            "pop_pool":   ["piano_staccato", "pluck_arpeggio", "atmospheric_pad",
                           "pedal_point", "four_chord_loop", "syncopated_anticipation"],
            "house_pool": ["lpf_bass_groove", "percussive_build", "chord_stab",
                           "syncopated_anticipation", "inverted_filter_sweep"],
            "edm_pool":   ["filter_sweep", "mono_pluck", "impact_drone",
                           "pedal_point", "inverted_filter_sweep", "syncopated_anticipation"],
        },
        "watchdog_s":            WATCHDOG_S,
        "source_file_fingerprints": src_files,
    }

    out_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(f"  Snapshot -> {out_path.resolve()}")
    return snapshot


# ─────────────────────────────────────────────────────────────────────────────
#  Main chain
# ─────────────────────────────────────────────────────────────────────────────

def run_commercial_chain(
    engine,
    orc,
    genres:      List[str] = None,
    gen_sizes:   List[int] = None,
    out_root:    Path      = DEFAULT_OUT_DIR,
    score_floor: float     = SCORE_FLOOR,
    skip_to_gen: int       = 1,
) -> None:
    """
    Full Gen 1 → Gen 2 → Gen 3 + Sibling chain for commercial genres.

    Parameters
    ----------
    engine      : Initialised CompositionEngine with seeds loaded.
    orc         : Modular Orchestrator (or None for legacy engine.compose).
    genres      : Override list of genres (default: COMMERCIAL_GENRES).
    gen_sizes   : Override [gen1_count, gen2_count, gen3_count].
    out_root    : Root output directory (default: commercial_run/).
    score_floor : Minimum score for Gen 3 sibling eligibility.
    skip_to_gen : Start from this generation (1, 2, or 3). Requires existing
                  evolutionary_pool.json from the previous generation.
    """
    if genres   is None: genres   = COMMERCIAL_GENRES
    if gen_sizes is None: gen_sizes = GEN_SIZES

    out_root.mkdir(parents=True, exist_ok=True)
    run_ts = time.strftime("%Y%m%d_%H%M%S")
    total_t0 = time.time()

    header = f"MUSIC ARCHITECT V7  —  COMMERCIAL SYNC CHAIN  {run_ts}"
    print(f"\n{'='*len(header)}")
    print(header)
    print(f"  Genres      : {genres}")
    print(f"  Gen sizes   : {gen_sizes}  tracks/genre")
    print(f"  Scale pools : Pop={BRIGHT_SCALES['pop']}")
    print(f"                House={BRIGHT_SCALES['house']}")
    print(f"                EDM={BRIGHT_SCALES['edm']}")
    print(f"  Score floor : {score_floor}  (Gen 3 sibling eligibility)")
    print(f"  Start gen   : {skip_to_gen}")
    print(f"  Output root : {out_root.resolve()}")
    print(f"{'='*len(header)}\n")

    # pool_paths[genre] = path to evolutionary_pool.json from previous gen
    pool_paths: Dict[str, Optional[str]] = {g: None for g in genres}

    # If resuming from Gen 2 or Gen 3, pre-load the prior gen's pool
    if skip_to_gen > 1:
        for genre in genres:
            prior_gen = skip_to_gen - 1
            prior_pool = out_root / f"gen{prior_gen}" / genre / "evolutionary_pool.json"
            if prior_pool.exists():
                pool_paths[genre] = str(prior_pool)
                print(f"  Resume: loaded Gen {prior_gen} pool for {genre}: {prior_pool.name}")
            else:
                print(f"  [WARN] Prior pool not found for {genre}: {prior_pool}"
                      f" — will use free exploration for Gen {skip_to_gen}")

    # ── Generations 1 and 2 ───────────────────────────────────────────────────
    for gen_idx, gen_size in enumerate(gen_sizes[:2]):
        gen_num   = gen_idx + 1
        gen_label = f"gen{gen_num}"

        if gen_num < skip_to_gen:
            print(f"  [SKIP] Generation {gen_num} (skip_to_gen={skip_to_gen})")
            continue

        # Mutation used when generating this gen
        this_mut = MUT_SCHEDULE[gen_idx - 1] if gen_idx > 0 else 0.0
        # Mutation baked into the pool that seeds the NEXT gen
        next_mut = MUT_SCHEDULE[gen_idx] if gen_idx < len(MUT_SCHEDULE) else MUT_SCHEDULE[-1]

        divider = "-" * 65
        print(f"\n{divider}")
        print(
            f"  GENERATION {gen_num}  |  {gen_size} tracks/genre  "
            f"|  {'golden injection  mut='+str(this_mut) if gen_num > 1 else 'free exploration'}"
            f"  |  bright scales only"
        )
        print(divider)

        for genre in genres:
            genre_dir = out_root / gen_label / genre
            _run_commercial_gen(
                genre            = genre,
                count            = gen_size,
                outdir           = genre_dir,
                engine           = engine,
                orc              = orc,
                gen_label        = gen_label,
                seed_pool_path   = pool_paths[genre],
                mut_factor       = this_mut,
                vocal_mask       = False,
                generation_level = gen_num,
            )

        # Grade + pool for next generation
        print(f"\n{'-'*40}")
        print(f"  GRADING GENERATION {gen_num}  (next gen will use mut={next_mut})")
        print(f"{'-'*40}")

        for genre in genres:
            genre_dir = out_root / gen_label / genre
            _, evo_pool_path = _grade_and_pool(genre_dir, next_mut=next_mut)
            pool_paths[genre] = str(evo_pool_path)

    # ── Generation 3 ─────────────────────────────────────────────────────────
    gen3_label = "gen3"
    gen3_size  = gen_sizes[2]

    if skip_to_gen <= 3:
        gen3_mut = MUT_SCHEDULE[-1]   # tightest refinement

        divider = "-" * 65
        print(f"\n{divider}")
        print(
            f"  GENERATION 3  |  {gen3_size} tracks/genre"
            f"  |  golden injection  mut={gen3_mut}  |  bright scales only"
        )
        print(divider)

        for genre in genres:
            genre_dir = out_root / gen3_label / genre
            _run_commercial_gen(
                genre            = genre,
                count            = gen3_size,
                outdir           = genre_dir,
                engine           = engine,
                orc              = orc,
                gen_label        = gen3_label,
                seed_pool_path   = pool_paths[genre],
                mut_factor       = gen3_mut,
                vocal_mask       = False,
                generation_level = 3,
            )

    # ── Grade Gen 3 + Sibling Pass ────────────────────────────────────────────
    print(f"\n{'-'*65}")
    print(f"  GRADING GENERATION 3  +  SIBLING PASS (score >= {score_floor})")
    print(f"{'-'*65}")

    vocal_root = out_root / gen3_label / "vocal_ready"
    vocal_root.mkdir(parents=True, exist_ok=True)

    gen3_summary: dict = {}

    for genre in genres:
        genre_dir = out_root / gen3_label / genre

        print(f"\n  Grading Gen 3 [{genre.upper()}] ...")
        report = _process_genre(genre_dir)

        report_path = genre_dir / "math_fitness_report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        leaderboard = report.get("leaderboard", [])
        score_map   = {e["track_name"]: e["score"] for e in leaderboard}

        n_scored  = report["tracks_scored"]
        top_score = leaderboard[0]["score"] if leaderboard else 0
        print(f"  {n_scored} tracks scored  |  top score={top_score:.2f}  ->  {report_path.name}")

        # Build also the pool for future use (archive)
        _grade_and_pool(genre_dir, next_mut=MUT_SCHEDULE[-1])

        # Filter winners at score floor
        winner_dirs: List[Path] = []
        for track_dir in sorted(p for p in genre_dir.iterdir() if p.is_dir()):
            score = score_map.get(track_dir.name, 0.0)
            if score >= score_floor:
                winner_dirs.append(track_dir)

        pass_rate = len(winner_dirs) / max(1, n_scored) * 100
        print(
            f"\n  Sibling filter  : {len(winner_dirs)}/{n_scored} pass"
            f"  ({pass_rate:.1f}%)  |  floor={score_floor}"
        )

        # Sibling pass
        sibling_entries = _run_sibling_pass(
            winner_dirs = winner_dirs,
            out_root    = vocal_root,
            genre       = genre,
            engine      = engine,
            orc         = orc,
        )

        gen3_summary[genre] = {
            "gen3_generated":   gen3_size,
            "gen3_scored":      n_scored,
            "gen3_passed":      len(winner_dirs),
            "pass_rate_pct":    round(pass_rate, 1),
            "top_score":        top_score,
            "siblings_created": len(sibling_entries),
            "score_floor":      score_floor,
            "gen3_dir":         str(genre_dir),
            "siblings_dir":     str(vocal_root / genre),
        }

    # ── Final manifest ────────────────────────────────────────────────────────
    total_elapsed = time.time() - total_t0

    chain_manifest = {
        "run_timestamp":   run_ts,
        "out_root":        str(out_root.resolve()),
        "genres":          genres,
        "gen_sizes":       gen_sizes,
        "bright_scales":   BRIGHT_SCALES,
        "excluded_dark":   sorted(DARK_SCALES),
        "score_floor":     score_floor,
        "total_elapsed_s": round(total_elapsed, 1),
        "gen3_results":    gen3_summary,
    }

    manifest_path = out_root / "commercial_chain_manifest.json"
    manifest_path.write_text(json.dumps(chain_manifest, indent=2), encoding="utf-8")

    print(f"\n{'='*65}")
    print(f"  COMMERCIAL CHAIN COMPLETE  —  {total_elapsed/60:.1f} min")
    print()
    print(f"  {'Genre':<8} {'Gen3 Tracks':>12} {'Passed':>7} {'Siblings':>9} {'Top Score':>10}")
    print(f"  {'-'*52}")
    for genre in genres:
        s = gen3_summary.get(genre, {})
        print(
            f"  {genre.upper():<8}"
            f"  {s.get('gen3_generated',0):>11}"
            f"  {s.get('gen3_passed',0):>6}"
            f"  {s.get('siblings_created',0):>8}"
            f"  {s.get('top_score',0):>9.2f}"
        )
    print()
    print(f"  Manifest -> {manifest_path.resolve()}")
    print(f"{'='*65}\n")


# ─────────────────────────────────────────────────────────────────────────────
#  CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="production_batch_commercial",
        description=(
            "Music Architect V7 — Commercial Sync Chain  "
            "(Pop / House / EDM, bright major scales, 3-generation evolution)"
        ),
    )
    parser.add_argument(
        "--out-dir", default=str(DEFAULT_OUT_DIR), dest="out_dir",
        help=f"Output root directory (default: {DEFAULT_OUT_DIR})",
    )
    parser.add_argument(
        "--genres", nargs="+", default=COMMERCIAL_GENRES,
        help=f"Genres to run (default: {COMMERCIAL_GENRES})",
    )
    parser.add_argument(
        "--gen1", type=int, default=GEN_SIZES[0], metavar="N",
        help=f"Tracks per genre in Gen 1 (default: {GEN_SIZES[0]})",
    )
    parser.add_argument(
        "--gen2", type=int, default=GEN_SIZES[1], metavar="N",
        help=f"Tracks per genre in Gen 2 (default: {GEN_SIZES[1]})",
    )
    parser.add_argument(
        "--gen3", type=int, default=GEN_SIZES[2], metavar="N",
        help=f"Tracks per genre in Gen 3 (default: {GEN_SIZES[2]})",
    )
    parser.add_argument(
        "--score-floor", type=float, default=SCORE_FLOOR, dest="score_floor",
        metavar="F",
        help=f"Minimum fitness score for Gen 3 sibling eligibility (default: {SCORE_FLOOR})",
    )
    parser.add_argument(
        "--skip-to-gen", type=int, default=1, choices=[1, 2, 3], dest="skip_to_gen",
        metavar="N",
        help=(
            "Skip to this generation. 2 requires gen1/*/evolutionary_pool.json, "
            "3 requires gen2/*/evolutionary_pool.json. (default: 1)"
        ),
    )

    args = parser.parse_args()
    out_root  = Path(args.out_dir)
    gen_sizes = [args.gen1, args.gen2, args.gen3]

    # Pre-flight
    print("Pre-flight commercial pipeline validation ...")
    if not validate_commercial_pipeline():
        print("  [WARN] One or more checks failed — review the output above.")
        print("         Continuing anyway.\n")
    else:
        print("  All checks passed.\n")

    # Snapshot
    out_root.mkdir(parents=True, exist_ok=True)
    print("Writing pre-run system snapshot ...")
    write_commercial_snapshot(out_root / "commercial_snapshot.json", out_root)
    print()

    # Initialise composition stack
    print("Initialising composition stack (loading seeds) ...")
    t0     = time.time()
    engine = CompositionEngine(seeds_dir="seeds")
    engine.load_seeds()
    orc    = _Orchestrator(engine) if _ORC_AVAILABLE else None
    print(f"Ready in {time.time()-t0:.1f}s  "
          f"({'modular orchestrator' if orc else 'legacy engine'})\n")

    run_commercial_chain(
        engine      = engine,
        orc         = orc,
        genres      = args.genres,
        gen_sizes   = gen_sizes,
        out_root    = out_root,
        score_floor = args.score_floor,
        skip_to_gen = args.skip_to_gen,
    )


if __name__ == "__main__":
    main()
