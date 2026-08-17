"""
wav_chunk_writer.py — WAV-specific RIFF chunk appender.

After soundfile writes a WAV file it closes the file handle, leaving a
well-formed RIFF WAV on disk.  This module opens that file in binary mode
and appends additional RIFF sub-chunks that soundfile's Python API does not
expose:

  LIST INFO chunk  — string metadata (title, artist, comment)
  smpl chunk       — sampler loop points
  inst chunk       — MIDI instrument parameters

All three chunk types are part of the official RIFF WAV specification
(Microsoft Multimedia Programmer's Reference, 1991) and are recognised by
DAWs (Logic Pro, Ableton Live, Reaper), hardware samplers, and SFZ / SF2
players on both Windows and macOS.

RIFF structure overview
-----------------------
A WAV file is a RIFF container:

    Offset 0  : b'RIFF'              (4 bytes, chunk identifier)
    Offset 4  : <total size − 8>     (4 bytes, little-endian uint32)
    Offset 8  : b'WAVE'              (4 bytes, form type)
    Offset 12 : [sub-chunks …]       (variable)

Each sub-chunk follows the pattern:
    <4-byte tag> <4-byte payload size (little-endian)> <payload bytes>

After appending new sub-chunks we update the RIFF size at offset 4 so that
any RIFF-aware parser counts the new chunks as part of the file.

Cross-platform notes
--------------------
Only Python's built-in `struct` module is used.  No platform-specific
system calls or libraries are needed.  The file is read entirely into memory,
modified, and written back — safe for files up to several hundred MB; for
files larger than ~1 GB prefer RF64 format (where chunk appending is not
implemented here and not necessary because RF64 already carries its own
extended size fields).
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import List

from src.audio_io.audio_metadata import AudioFileMetadata, InstrumentInfo, LoopPoint


class WAVChunkWriter:
    """
    Appends metadata RIFF sub-chunks to an existing WAV file.

    The file must already be a valid RIFF WAV (written by soundfile or any
    other writer) before calling append_metadata().

    Usage
    -----
        writer = WAVChunkWriter()
        writer.append_metadata(Path('output.wav'), metadata, sample_rate=44100)
    """

    # ── Public entry point ────────────────────────────────────────────────────

    def append_metadata(
        self,
        filepath:    Path,
        metadata:    AudioFileMetadata,
        sample_rate: int,
    ) -> None:
        """
        Append all metadata chunks present in *metadata* to *filepath*.

        Parameters
        ----------
        filepath    : path to an already-written WAV file (must be RIFF/WAVE)
        metadata    : AudioFileMetadata with any combination of title, artist,
                      comment, instrument, and loops
        sample_rate : sample rate of the audio in the file; needed to calculate
                      the smpl chunk's Sample Period field (1e9 / sample_rate ns)

        Raises
        ------
        ValueError  : if *filepath* is not a valid RIFF WAV file
        OSError     : if the file cannot be read or written
        """
        extra = b''

        # Build each chunk only if the corresponding metadata is present
        string_chunk = self._build_list_info_chunk(metadata)
        if string_chunk:
            extra += string_chunk

        if metadata.loops:
            extra += self._build_smpl_chunk(metadata.loops, sample_rate)

        if metadata.instrument:
            extra += self._build_inst_chunk(metadata.instrument)

        # Nothing to append — return immediately without touching the file
        if not extra:
            return

        self._patch_riff_file(filepath, extra)

    # ── LIST INFO chunk (string tags) ─────────────────────────────────────────

    def _build_list_info_chunk(self, metadata: AudioFileMetadata) -> bytes:
        """
        Build a WAV LIST INFO chunk containing string metadata.

        The LIST INFO chunk is the standard RIFF mechanism for embedding
        human-readable text into WAV files.  It is a LIST chunk whose
        form type is 'INFO', followed by individual INFO sub-chunks:

            INAM  — track name / title
            IART  — artist / composer
            ICMT  — free-text comment

        Each string is null-terminated and padded to an even byte count
        (RIFF requirement: all chunk payloads must be even-sized).

        Returns b'' if none of title, artist, or comment are set.
        """
        # Collect only the tags that are actually provided
        tags: list[tuple[bytes, str]] = []
        if metadata.title:
            tags.append((b'INAM', metadata.title))
        if metadata.artist:
            tags.append((b'IART', metadata.artist))
        if metadata.comment:
            tags.append((b'ICMT', metadata.comment))

        if not tags:
            return b''  # No string metadata — skip the chunk entirely

        # Build the payload: 'INFO' form type + individual tag sub-chunks
        info_payload = b'INFO'
        for tag_id, value in tags:
            # Encode as UTF-8, null-terminate, pad to even length
            encoded = value.encode('utf-8') + b'\x00'
            if len(encoded) % 2:
                encoded += b'\x00'   # RIFF even-size padding
            # Each sub-chunk: 4-byte tag ID + 4-byte size + payload
            info_payload += struct.pack('<4sI', tag_id, len(encoded)) + encoded

        # Wrap in the outer LIST chunk
        return struct.pack('<4sI', b'LIST', len(info_payload)) + info_payload

    # ── smpl chunk (loop points) ──────────────────────────────────────────────

    def _build_smpl_chunk(self, loops: List[LoopPoint], sample_rate: int) -> bytes:
        """
        Build a WAV smpl (sampler) chunk for the given loop regions.

        The smpl chunk is defined in the RIFF Multimedia Specification and
        is supported by all major DAWs and hardware samplers.  It stores:

        - Sample Period: the duration of one sample in nanoseconds
          (= 1,000,000,000 / sample_rate).  Used by samplers for pitch
          correction when the file is assigned to a non-root note.
        - MIDI Unity Note: the MIDI note at which the sample plays at
          its recorded pitch (fixed to 60 = middle C here; callers that
          need a different root note should use InstrumentInfo.base_note
          via the inst chunk instead).
        - One loop entry (24 bytes) per LoopPoint.

        Parameters
        ----------
        loops       : list of LoopPoint objects (start, end, loop_id)
        sample_rate : sample rate of the audio, used for Sample Period field
        """
        # Sample Period in nanoseconds: duration of one sample frame
        sample_period = int(1_000_000_000 / sample_rate)
        n_loops = len(loops)

        # smpl header: 9 uint32 fields preceding the loop entries (36 bytes)
        header = struct.pack(
            '<9I',
            0,              # Manufacturer  (0 = not vendor-specific)
            0,              # Product       (0 = not vendor-specific)
            sample_period,  # Sample Period in nanoseconds
            60,             # MIDI Unity Note (middle C)
            0,              # MIDI Pitch Fraction (sub-cent, 0 = exact)
            0,              # SMPTE Format  (0 = not SMPTE-locked)
            0,              # SMPTE Offset  (not used)
            n_loops,        # Number of Sample Loops that follow
            0,              # Sampler Data  (extra bytes after loops, 0 = none)
        )

        # Loop entries: 6 uint32 fields each = 24 bytes per loop
        loop_data = b''
        for lp in loops:
            loop_data += struct.pack(
                '<6I',
                lp.loop_id,  # Cue Point ID — links to a cue chunk if present
                0,           # Type: 0 = forward loop (most common)
                lp.start,    # Start frame (inclusive, zero-based)
                lp.end,      # End frame   (inclusive)
                0,           # Fraction — sub-sample loop start precision; 0 = none
                0,           # Play Count — 0 = loop indefinitely
            )

        payload = header + loop_data

        # RIFF rule: all chunk payloads must be even-sized
        if len(payload) % 2:
            payload += b'\x00'

        return struct.pack('<4sI', b'smpl', len(payload)) + payload

    # ── inst chunk (instrument info) ──────────────────────────────────────────

    def _build_inst_chunk(self, info: InstrumentInfo) -> bytes:
        """
        Build a WAV inst (instrument) chunk.

        The inst chunk is 7 bytes long and tells samplers:
        - Which MIDI note reproduces the sample at its recorded pitch (base_note)
        - A fine-tune offset in cents (fine_tune)
        - A gain adjustment in dB (gain_db)
        - The MIDI note and velocity range to which this sample is mapped

        Parameters
        ----------
        info : InstrumentInfo dataclass with MIDI mapping parameters
        """
        # inst payload: 3 signed bytes + 4 unsigned bytes = 7 bytes
        payload = struct.pack(
            '<bbbBBBB',
            info.base_note,   # UnshiftedNote — signed byte, MIDI 0–127
            info.fine_tune,   # FineTune      — signed byte, cents (−50 to +50)
            info.gain_db,     # Gain          — signed byte, dB (usually 0)
            info.low_note,    # LowNote       — unsigned byte, MIDI note range low
            info.high_note,   # HighNote      — unsigned byte, MIDI note range high
            info.low_vel,     # LowVelocity   — unsigned byte, velocity range low
            info.high_vel,    # HighVelocity  — unsigned byte, velocity range high
        )

        # The inst payload is 7 bytes — pad to 8 (RIFF even-size requirement)
        payload += b'\x00'

        return struct.pack('<4sI', b'inst', len(payload)) + payload

    # ── RIFF file patcher ─────────────────────────────────────────────────────

    def _patch_riff_file(self, filepath: Path, extra_chunks: bytes) -> None:
        """
        Append *extra_chunks* to an existing RIFF WAV file in-place, then
        update the RIFF size field so the file remains well-formed.

        RIFF size field (bytes 4–7): total file length minus the 8 bytes
        occupied by the 'RIFF' tag and the size field itself.

        After appending:
            new_riff_size = len(original_data) + len(extra_chunks) − 8

        Parameters
        ----------
        filepath     : path to the WAV file to patch
        extra_chunks : raw bytes of one or more complete RIFF sub-chunks
                       (each already containing the 4-byte tag and 4-byte size)

        Raises
        ------
        ValueError   : if the file does not begin with 'RIFF' / 'WAVE'
        """
        # Read the entire file into memory
        data = filepath.read_bytes()

        # Validate RIFF WAV structure before touching anything
        if len(data) < 12 or data[:4] != b'RIFF' or data[8:12] != b'WAVE':
            raise ValueError(
                f"Cannot append chunks: '{filepath.name}' is not a valid RIFF WAV file."
            )

        # Concatenate the new chunk bytes at the end
        new_data = data + extra_chunks

        # Update the RIFF size field at offset 4 (little-endian uint32)
        new_riff_size = len(new_data) - 8
        new_data = new_data[:4] + struct.pack('<I', new_riff_size) + new_data[8:]

        # Write back atomically (overwrite in place)
        filepath.write_bytes(new_data)
