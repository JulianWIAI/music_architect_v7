"""
watermark_engine.py — Dual-layer steganographic watermarking for MIDI catalogs.

Layer 1 — MetaMessage Header (Standard Watermark)
    Inserts a hidden track at position 0 of every MIDI file containing:
      • MetaMessage('track_name')  — machine-readable sentinel for extraction
      • MetaMessage('copyright')   — human-readable ownership claim
      • MetaMessage('text')        — catalog tag + SHA-256 of filename (hex)
    No audio impact; readable by any DAW, MIDI inspector, or hex editor.

Layer 2 — Velocity LSB Steganography (Deep Watermark)
    Encodes a 12-byte payload as 96 bits into the Least Significant Bits of
    note_on velocities across all musical (non-watermark) tracks.

    Payload layout (12 bytes = 96 bits):
        [0:4]  MAGIC       b"MA7\\x00"  — 4-byte magic sentinel
        [4:12] FILE_HASH   first 8 bytes of SHA-256(filename) — per-file fingerprint

    LSB modification rules:
        target = (velocity & 0xFE) | bit
        • velocity 127, bit 0 → 126  (subtract 1, stays in [1,127])
        • velocity 1,   bit 0 → 2    (would be 0 = note_off; nudge to 2)
        • all other cases      → standard clear + set, delta at most ±1
    Maximum perceptible velocity delta: 1 unit — inaudible in practice.

Output
    Mirrored directory tree under Watermarked_Catalog/:
        Watermarked_Catalog/production_run/...
        Watermarked_Catalog/commercial_run/...

Extraction
    extract_watermark(filepath) reads and decodes both layers, prints results.

Usage
    python watermark_engine.py                  # watermark entire catalog
    python watermark_engine.py --extract FILE   # decode a watermarked file
    python watermark_engine.py --verify         # watermark + immediate verify on one file
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Optional

import mido

# ─────────────────────────────────────────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent

CATALOG_DIRS: list[Path] = [
    ROOT / "Final commercial batch" / "production_run",
    ROOT / "Final commercial batch" / "commercial_run",
]

OUT_ROOT = ROOT / "Watermarked_Catalog"

# Layer 1 text constants
COPYRIGHT_TEXT     = "(C) 2026 MUSIC_ARCHITECT_V7 - AUTHORIZED_COMMERCIAL_SYNC_ASSET_CLASS_A"
CATALOG_TAG        = "MUSIC_ARCHITECT_V7_COMMERCIAL_SYNC_ASSET_CLASS_A"
WATERMARK_SENTINEL = "_WM_MA7_"   # track_name value used to locate watermark track

# Layer 2 LSB payload constants
MAGIC              = b"MA7\x00"   # 4 bytes — magic header for extraction validation
LSB_PAYLOAD_BYTES  = 12           # 4 magic + 8 filename hash → 96 bits → 96 notes minimum
LSB_PAYLOAD_BITS   = LSB_PAYLOAD_BYTES * 8


# ─────────────────────────────────────────────────────────────────────────────
#  Layer 1 helpers
# ─────────────────────────────────────────────────────────────────────────────

def _file_hash(filepath: Path) -> bytes:
    """First 8 bytes of SHA-256 of the canonical filename (no path)."""
    return hashlib.sha256(filepath.name.encode("utf-8")).digest()[:8]


def _make_watermark_track(filepath: Path) -> mido.MidiTrack:
    """
    Build the hidden MetaMessage track (Layer 1).

    The track contains three MetaMessages and the mandatory end_of_track.
    All events are at time=0 so they add zero MIDI duration.
    """
    hash_hex         = _file_hash(filepath).hex().upper()
    catalog_payload  = (
        f"AUTHORIZED_COMMERCIAL_SYNC_ASSET_CLASS_A"
        f" | {CATALOG_TAG}"
        f" | SHA256_FNAME={hash_hex}"
    )

    track = mido.MidiTrack()
    track.append(mido.MetaMessage("track_name",  name=WATERMARK_SENTINEL,  time=0))
    track.append(mido.MetaMessage("copyright",   text=COPYRIGHT_TEXT,       time=0))
    track.append(mido.MetaMessage("text",        text=catalog_payload,      time=0))
    track.append(mido.MetaMessage("end_of_track",                           time=0))
    return track


# ─────────────────────────────────────────────────────────────────────────────
#  Layer 2 helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_payload_bits(filepath: Path) -> list[int]:
    """
    Return the 96-bit payload as a list of ints (0 or 1), MSB-first.

    Layout: MAGIC[4] + SHA-256(filename)[0:8] = 12 bytes = 96 bits.
    """
    payload = MAGIC + _file_hash(filepath)
    bits: list[int] = []
    for byte in payload:
        for shift in range(7, -1, -1):   # MSB first
            bits.append((byte >> shift) & 1)
    return bits


def _embed_lsb(velocity: int, bit: int) -> int:
    """
    Set the LSB of velocity to bit, keeping velocity in [1, 127].

    Standard case:  velocity = (velocity & 0xFE) | bit   → delta at most 1
    Edge cases:
        velocity 127, bit 0  → 126  (AND clears to 126, which is already correct)
        velocity 1,   bit 0  → would yield 0 (= note_off) → nudge to 2
        velocity 0           → caller must skip (note_off alias, do not modify)
    """
    v = (velocity & 0xFE) | bit
    if v == 0:      # velocity 1 + bit 0: (1 & 0xFE)=0, illegal — nudge to 2
        v = 2
    return v


def _embed_in_track(track: mido.MidiTrack, bits: list[int], cursor: int) -> int:
    """
    Walk every note_on in the track and embed bits[cursor:] into velocity LSBs.
    Skips note_on with velocity=0 (they are semantically note_off events).
    Returns the updated cursor position.
    """
    for msg in track:
        if cursor >= len(bits):
            break
        if msg.type == "note_on" and msg.velocity > 0:
            msg.velocity = _embed_lsb(msg.velocity, bits[cursor])
            cursor += 1
    return cursor


def _extract_from_track(track: mido.MidiTrack, bits: list[int]) -> None:
    """Append LSBs of all note_on velocities (velocity > 0) to bits."""
    for msg in track:
        if msg.type == "note_on" and msg.velocity > 0:
            bits.append(msg.velocity & 1)


def _bits_to_bytes(bits: list[int]) -> bytes:
    """Reconstruct bytes from a flat MSB-first bit list."""
    out = bytearray()
    for i in range(0, len(bits) - (len(bits) % 8), 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | bits[i + j]
        out.append(byte)
    return bytes(out)


# ─────────────────────────────────────────────────────────────────────────────
#  Core watermark function
# ─────────────────────────────────────────────────────────────────────────────

def watermark_midi(src: Path, dst: Path) -> dict:
    """
    Apply both watermark layers to src, write result to dst.

    Returns a status dict with embed stats.
    """
    mid = mido.MidiFile(str(src))

    # ── Layer 1: inject watermark track at position 0 ────────────────────────
    wm_track = _make_watermark_track(src)
    mid.tracks.insert(0, wm_track)

    # If the file was Type 0 (single track), upgrade to Type 1 so the extra
    # track is valid. Type 2 is left as-is; Type 1 unchanged.
    if mid.type == 0:
        mid.type = 1

    # ── Layer 2: embed LSB payload into musical tracks ───────────────────────
    bits         = _build_payload_bits(src)
    cursor       = 0
    musical_tracks_used = 0

    for track in mid.tracks:
        if cursor >= len(bits):
            break
        # Skip the watermark track we just inserted (identified by sentinel)
        has_sentinel = any(
            getattr(msg, "name", None) == WATERMARK_SENTINEL
            for msg in track
            if msg.is_meta and msg.type == "track_name"
        )
        if has_sentinel:
            continue
        prev_cursor  = cursor
        cursor       = _embed_in_track(track, bits, cursor)
        if cursor > prev_cursor:
            musical_tracks_used += 1

    # ── Save ─────────────────────────────────────────────────────────────────
    dst.parent.mkdir(parents=True, exist_ok=True)
    mid.save(str(dst))

    return {
        "src":              str(src),
        "dst":              str(dst),
        "bits_embedded":    cursor,
        "bits_required":    LSB_PAYLOAD_BITS,
        "fully_embedded":   cursor >= LSB_PAYLOAD_BITS,
        "tracks_used":      musical_tracks_used,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Extraction / verification
# ─────────────────────────────────────────────────────────────────────────────

def extract_watermark(filepath: str | Path) -> None:
    """
    Decode and print both watermark layers from a watermarked MIDI file.

    Prints:
        Layer 1  — MetaMessage text payloads from the watermark track
        Layer 2  — Decoded LSB binary payload (magic check + filename hash)
    """
    path = Path(filepath)
    mid  = mido.MidiFile(str(path))

    print(f"\n{'='*60}")
    print(f"  WATERMARK EXTRACTION: {path.name}")
    print(f"{'='*60}")

    # ── Layer 1: locate watermark track and read MetaMessages ─────────────────
    wm_track_found = False
    for i, track in enumerate(mid.tracks):
        is_wm = any(
            getattr(msg, "name", None) == WATERMARK_SENTINEL
            for msg in track
            if msg.is_meta and msg.type == "track_name"
        )
        if not is_wm:
            continue

        wm_track_found = True
        print(f"\n  [Layer 1]  MetaMessage Header  (track {i})")
        for msg in track:
            if not msg.is_meta:
                continue
            if msg.type == "track_name":
                print(f"    track_name  : {msg.name!r}")
            elif msg.type == "copyright":
                print(f"    copyright   : {msg.text}")
            elif msg.type == "text":
                print(f"    text        : {msg.text}")
        break

    if not wm_track_found:
        print("  [Layer 1]  WARNING: no watermark track found (SENTINEL not present)")

    # ── Layer 2: extract LSBs from all non-watermark tracks ───────────────────
    bits: list[int] = []
    for track in mid.tracks:
        is_wm = any(
            getattr(msg, "name", None) == WATERMARK_SENTINEL
            for msg in track
            if msg.is_meta and msg.type == "track_name"
        )
        if is_wm:
            continue
        _extract_from_track(track, bits)
        if len(bits) >= LSB_PAYLOAD_BITS:
            break

    print(f"\n  [Layer 2]  Velocity LSB Steganography")
    print(f"    bits collected : {len(bits)} (need {LSB_PAYLOAD_BITS} for full payload)")

    if len(bits) < LSB_PAYLOAD_BITS:
        print("    WARNING: insufficient note_on events — payload only partially recoverable")

    payload = _bits_to_bytes(bits[:LSB_PAYLOAD_BITS])

    # Validate magic header
    magic_ok = payload[:4] == MAGIC
    print(f"    raw bytes (hex): {payload.hex().upper()}")
    print(f"    magic header   : {payload[:4]!r}  {'✓ VALID' if magic_ok else '✗ INVALID'}")

    if magic_ok and len(payload) >= LSB_PAYLOAD_BYTES:
        embedded_hash = payload[4:12]
        print(f"    filename hash  : {embedded_hash.hex().upper()}")

        # Cross-check against the current filename
        expected_hash = _file_hash(path)
        match = embedded_hash == expected_hash
        print(f"    hash match     : {'✓ VERIFIED — filename matches embedded hash' if match else '✗ MISMATCH'}")
        if not match:
            print(f"    expected       : {expected_hash.hex().upper()}")
    else:
        print("    payload corrupt or incomplete — magic check failed")

    print(f"{'='*60}\n")


# ─────────────────────────────────────────────────────────────────────────────
#  Catalog batch runner
# ─────────────────────────────────────────────────────────────────────────────

def watermark_catalog(
    catalog_dirs: list[Path] = CATALOG_DIRS,
    out_root:     Path        = OUT_ROOT,
    verbose:      bool        = True,
) -> None:
    """
    Iterate every .mid file across catalog_dirs, watermark each one, and
    write the result into a mirrored directory tree under out_root.

    Mirrors:
        <catalog_dir>/foo/bar/track.mid
        → out_root/<catalog_dir.name>/foo/bar/track.mid
    """
    out_root.mkdir(parents=True, exist_ok=True)

    total_files  = 0
    total_ok     = 0
    total_failed = 0
    partial_embed = 0

    for catalog_dir in catalog_dirs:
        if not catalog_dir.exists():
            print(f"[WARN] Catalog dir not found, skipping: {catalog_dir}")
            continue

        mid_files = sorted(catalog_dir.rglob("*.mid"))
        print(f"\n  Scanning: {catalog_dir}")
        print(f"  Found   : {len(mid_files)} .mid files\n")

        for src in mid_files:
            total_files += 1
            # Mirror relative path under out_root/<catalog_name>/
            rel    = src.relative_to(catalog_dir)
            dst    = out_root / catalog_dir.name / rel

            try:
                result = watermark_midi(src, dst)
            except Exception as exc:
                print(f"  [ERROR] {src.name}: {exc}")
                total_failed += 1
                continue

            total_ok += 1
            if not result["fully_embedded"]:
                partial_embed += 1
                status = f"[PARTIAL {result['bits_embedded']}/{result['bits_required']} bits]"
            else:
                status = "[OK]"

            if verbose:
                print(
                    f"  {status:<12}  {src.name:<45}"
                    f"  tracks_used={result['tracks_used']}"
                )

    print(f"\n{'─'*60}")
    print(f"  Watermarked  : {total_ok}/{total_files} files")
    print(f"  Partial embed: {partial_embed} (too few notes for full payload)")
    print(f"  Failed       : {total_failed}")
    print(f"  Output root  : {out_root.resolve()}")
    print(f"{'─'*60}\n")


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dual-layer MIDI steganographic watermark engine"
    )
    parser.add_argument(
        "--extract", metavar="FILE",
        help="Decode and print watermark layers from a single .mid file"
    )
    parser.add_argument(
        "--verify", metavar="FILE",
        help="Watermark a single file in-place (to a temp copy) then extract to verify"
    )
    parser.add_argument(
        "--out-dir", metavar="DIR", default=str(OUT_ROOT),
        help=f"Output root for watermarked catalog (default: {OUT_ROOT})"
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress per-file output"
    )
    args = parser.parse_args()

    if args.extract:
        extract_watermark(args.extract)
        return

    if args.verify:
        src  = Path(args.verify)
        dst  = src.with_stem(src.stem + "_wm_verify")
        print(f"Watermarking {src.name} → {dst.name} ...")
        result = watermark_midi(src, dst)
        print(f"  bits embedded: {result['bits_embedded']}/{result['bits_required']}")
        extract_watermark(dst)
        return

    watermark_catalog(
        out_root=Path(args.out_dir),
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()
