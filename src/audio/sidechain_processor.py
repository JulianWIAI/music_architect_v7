"""
src/audio/sidechain_processor.py
──────────────────────────────────
Python bridge to the C++ SidechainFollower and a vectorised numpy fallback.

The sidechain follower applies kick-triggered gain reduction (the classic
"pump" effect) to the full mix buffer.  Trigger positions are extracted from
the composition dict's drum track so no real-time envelope detection is needed.

Genre-specific parameters
──────────────────────────
Attack is near-instant for all electronic genres because the gain reduction must
engage before the kick's body arrives (otherwise the pump is inaudible).

Release time controls the audible pump duration:
  short (50–80 ms)   → tight, danceable pump (EDM, Techno, DnB)
  medium (100–140 ms)→ heavier, flowing (Trap, Phonk)
  long  (150+ ms)    → subtle breathing (Pop, Hip-hop, J-pop)

Depth controls how much everything ducks when the kick hits:
  0.60–0.80 → classic commercial EDM/Techno pump (very audible)
  0.40–0.60 → trap/phonk weight without obvious pumping
  0.15–0.30 → subtle warmth — glues the mix without a visible effect
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import List

import numpy as np

# ── Try to use the compiled C++ SidechainFollower ────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _import_synth_core():
    """Add the project root to sys.path and try to import synth_core."""
    root_str = str(_PROJECT_ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    try:
        import synth_core as _sc
        return _sc
    except ImportError:
        return None


_synth_core   = _import_synth_core()
_CPP_AVAILABLE = (
    _synth_core is not None and
    hasattr(_synth_core, 'SidechainFollower')
)


# ── Genre parameter table ─────────────────────────────────────────────────────
# Tuples: (attack_ms, release_ms, depth)
# Values derived from analysis of commercial tracks per genre.

_GENRE_PARAMS: dict = {
    'edm':      (1.0,  80.0, 0.70),
    'house':    (1.0,  80.0, 0.68),
    'techno':   (0.5,  60.0, 0.75),
    'trap':     (1.0, 140.0, 0.55),
    'phonk':    (1.0, 130.0, 0.50),
    'dnb':      (1.0,  65.0, 0.45),
    'hiphop':   (2.0, 120.0, 0.25),
    'pop':      (2.0, 120.0, 0.20),
    'jpop':     (2.0, 110.0, 0.20),
}
# Genres not listed get a very light touch — present but not obvious.
_DEFAULT_PARAMS = (2.0, 120.0, 0.12)


# ── Kick event extractor ──────────────────────────────────────────────────────

# General MIDI percussion note numbers for bass drum hits.
_KICK_NOTES = frozenset({35, 36})   # 36 = Bass Drum 1, 35 = Bass Drum 2


def _extract_kick_triggers(composition: dict, sample_rate: int) -> List[int]:
    """
    Return sorted absolute sample indices for every kick hit in the composition.

    Only searches tracks whose MIDI channel is 9 (GM percussion channel) and
    whose note pitch is in _KICK_NOTES (35 = BD2, 36 = BD1).
    """
    cfg      = composition.get('config', {})
    bpm      = float(cfg.get('bpm', 120.0))
    beat_dur = 60.0 / bpm   # seconds per beat

    tracks     = composition.get('tracks',     {})
    track_info = composition.get('track_info', {})

    triggers: List[int] = []
    for name, events in tracks.items():
        if track_info.get(name, {}).get('channel', 0) != 9:
            continue   # skip melodic tracks

        for event in events:
            if len(event) < 3:
                continue
            time_beats = float(event[0])
            pitch      = int(event[2])
            if pitch in _KICK_NOTES:
                sample_idx = int(time_beats * beat_dur * sample_rate)
                triggers.append(sample_idx)

    return sorted(set(triggers))


# ── Vectorised numpy fallback ─────────────────────────────────────────────────

def _sidechain_numpy(
    buf:         np.ndarray,
    triggers:    List[int],
    sample_rate: int,
    attack_ms:   float,
    release_ms:  float,
    depth:       float,
) -> np.ndarray:
    """
    Apply sidechain gain reduction using vectorised numpy operations.

    The envelope is built analytically: between each pair of consecutive
    triggers the signal decays as a geometric sequence from 1.0 at the trigger
    sample.  This is O(N) with entirely numpy-level operations — no
    sample-by-sample Python loop.

    Where two decay tails overlap (trigger spacing < release time), the
    element-wise maximum is taken, which matches the correct audio behaviour
    (the stronger of two concurrent gain-reduction signals wins).
    """
    n = len(buf)
    if not triggers or depth < 0.001:
        return buf.copy()

    # Release: decay factor per sample.
    release_s     = max(release_ms, 1e-6) / 1000.0
    release_decay = math.exp(-1.0 / (release_s * sample_rate))

    # Attack: linear ramp over attack_samples for de-clicking the onset edge.
    # For attack_ms < 1 this is ≤ 44 samples at 44 100 Hz — inaudible as a
    # ramp but removes the mathematical discontinuity at the trigger point.
    attack_samples = max(1, int(attack_ms / 1000.0 * sample_rate))

    envelope = np.zeros(n, dtype=np.float32)
    valid    = [t for t in triggers if 0 <= t < n]
    if not valid:
        return buf.copy()

    # Sentinel at n so the last segment runs to the end of the buffer.
    endpoints = valid + [n]
    for seg_idx, t_start in enumerate(valid):
        t_end   = endpoints[seg_idx + 1]
        seg_len = t_end - t_start

        # Geometric decay from 1.0: [1, r, r^2, ..., r^(seg_len-1)]
        k   = np.arange(seg_len, dtype=np.float64)
        seg = np.power(release_decay, k).astype(np.float32)

        # Apply attack ramp at the trigger onset to avoid a hard edge.
        if attack_samples > 1:
            ramp_len  = min(attack_samples, seg_len)
            seg[:ramp_len] *= np.linspace(0.0, 1.0, ramp_len, dtype=np.float32)

        # Take element-wise max so overlapping tails from close triggers combine
        # correctly rather than one segment overwriting the other.
        np.maximum(envelope[t_start:t_end], seg, out=envelope[t_start:t_end])

    # Apply gain: gain = 1 - depth * envelope.
    gain   = np.subtract(1.0, depth * envelope, dtype=np.float32)
    return (buf * gain).astype(np.float32)


# ── C++ path (block-by-block) ─────────────────────────────────────────────────

_CPP_BLOCK_SIZE = 512   # matches DspSession block granularity


def _sidechain_cpp(
    buf:         np.ndarray,
    triggers:    List[int],
    sample_rate: int,
    attack_ms:   float,
    release_ms:  float,
    depth:       float,
) -> np.ndarray:
    """Process via the compiled C++ SidechainFollower in 512-sample blocks."""
    follower = _synth_core.SidechainFollower(
        sample_rate = sample_rate,
        attack_ms   = attack_ms,
        release_ms  = release_ms,
        depth       = depth,
    )
    follower.set_triggers(triggers)

    chunks = []
    for start in range(0, len(buf), _CPP_BLOCK_SIZE):
        chunk = np.ascontiguousarray(buf[start:start + _CPP_BLOCK_SIZE], dtype=np.float32)
        chunks.append(follower.process(chunk, start))

    return np.concatenate(chunks) if chunks else buf


# ── Public API ────────────────────────────────────────────────────────────────

def apply_sidechain(
    samples:     list,
    composition: dict,
    sample_rate: int,
) -> list:
    """
    Apply kick-triggered sidechain gain reduction to the audio buffer.

    Extracts kick hit times from the composition dict's drum track, builds a
    release-only envelope follower anchored to those positions, and applies
    depth-scaled gain reduction to the full mix.

    Returns the processed sample list.  Falls back to the unmodified input on
    any error so the render always produces valid audio.

    Parameters
    ----------
    samples     : List[float] — mono PCM from BuiltinSynthesizer.
    composition : dict — composition dict from CompositionEngine.compose().
    sample_rate : int — audio sample rate in Hz.
    """
    try:
        genre = composition.get('config', {}).get('genre', '')
        attack_ms, release_ms, depth = _GENRE_PARAMS.get(genre, _DEFAULT_PARAMS)

        triggers = _extract_kick_triggers(composition, sample_rate)
        if not triggers:
            return samples   # no kick events — nothing to sidechain

        buf = np.array(samples, dtype=np.float32)

        if _CPP_AVAILABLE:
            result = _sidechain_cpp(buf, triggers, sample_rate, attack_ms, release_ms, depth)
        else:
            result = _sidechain_numpy(buf, triggers, sample_rate, attack_ms, release_ms, depth)

        return result.tolist()

    except Exception:
        return samples   # graceful fallback — unprocessed audio is still valid
