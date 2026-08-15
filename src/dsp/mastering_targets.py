"""
src.dsp.mastering_targets — Export loudness target presets.

Defines MasteringTarget dataclasses for common distribution platforms:
  - STREAMING    : Spotify / Apple Music / YouTube  (-14 LUFS, -1 dBTP)
  - BROADCAST    : EBU R128 broadcast              (-23 LUFS ±0.5, -3 dBTP)
  - SYNC_LICENSING: Music library / sync placement  (-16 LUFS, -1 dBTP)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MasteringTarget:
    """Immutable loudness target definition for a specific distribution channel."""

    id:             str    # machine-readable key (e.g. 'streaming')
    label:          str    # display name shown in the UI
    target_lufs:    float  # integrated loudness target (LUFS)
    true_peak_dbfs: float  # true-peak ceiling (dBTP)
    description:    str    # human-readable one-line description


# ── Built-in presets ───────────────────────────────────────────────────────────

STREAMING = MasteringTarget(
    id             = 'streaming',
    label          = 'STREAMING',
    target_lufs    = -14.0,
    true_peak_dbfs = -1.0,
    description    = 'Spotify/Apple/YouTube  (-14 LUFS, -1 dBTP)',
)

BROADCAST = MasteringTarget(
    id             = 'broadcast',
    label          = 'BROADCAST',
    target_lufs    = -23.0,
    true_peak_dbfs = -3.0,
    description    = 'EBU R128 broadcast  (-23 LUFS ±0.5, -3 dBTP)',
)

SYNC_LICENSING = MasteringTarget(
    id             = 'sync_licensing',
    label          = 'SYNC / LICENSING',
    target_lufs    = -16.0,
    true_peak_dbfs = -1.0,
    description    = 'Music library / sync placement  (-16 LUFS, -1 dBTP)',
)

# ── Lookup dict ───────────────────────────────────────────────────────────────

TARGETS: dict[str, MasteringTarget] = {
    t.id: t for t in [STREAMING, BROADCAST, SYNC_LICENSING]
}
