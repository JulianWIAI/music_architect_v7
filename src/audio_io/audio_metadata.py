"""
audio_metadata.py — Metadata dataclasses for embedding into audio files.

Three levels of metadata are supported:

1. String tags  (AudioFileMetadata.title / .artist / .comment)
   Written into the WAV LIST INFO chunk so DAWs and media players can
   display the information without parsing the audio data.

2. Loop points  (LoopPoint, stored in AudioFileMetadata.loops)
   Written into the WAV smpl chunk.  Recognised by hardware samplers,
   Ableton Live, Logic Pro, and SFZ / SF2 players to define regions
   that should loop during playback.

3. Instrument info  (InstrumentInfo, stored in AudioFileMetadata.instrument)
   Written into the WAV inst chunk.  Tells samplers the MIDI root note,
   velocity range, and gain setting so the sample plays back at correct
   pitch and level without manual mapping.

Format compatibility
--------------------
All three metadata types are written as binary RIFF sub-chunks appended
to WAV files by WAVChunkWriter.  They are not supported for AIFF / RF64 /
CAF / W64 in this implementation (those formats require different chunk
layouts that are not exposed by soundfile's Python API).

String tags are WAV-only (LIST INFO).  Loop and instrument chunks are
WAV-only (smpl, inst).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class LoopPoint:
    """
    A single loop region defined as sample frame indices.

    Parameters
    ----------
    start : int
        First frame of the loop (inclusive, zero-based).
    end : int
        Last frame of the loop (inclusive).
        Must be > start.
    loop_id : int
        Arbitrary integer identifier used by the sampler to distinguish
        multiple loops in the same file.  Usually 0 for the first loop.
    """

    start:   int
    end:     int
    loop_id: int = 0


@dataclass
class InstrumentInfo:
    """
    MIDI instrument parameters stored in the WAV inst chunk.

    These values tell hardware and software samplers how to interpret the
    sample without user intervention:

    base_note : int
        MIDI note number at which the sample plays back at its recorded
        pitch.  Middle C = 60.  Range 0–127.
    fine_tune : int
        Additional pitch offset in cents (1/100 semitone).  Range −50 to +50.
    gain_db : int
        Output gain adjustment in whole dB.  Usually 0.
    low_note / high_note : int
        MIDI note range over which this sample is mapped.  Notes outside
        this range are handled by other samples in the instrument.
    low_vel / high_vel : int
        MIDI velocity range for this sample layer.  127 = full velocity.
    """

    base_note:  int = 60   # Middle C
    fine_tune:  int = 0    # Cents, −50 … +50
    gain_db:    int = 0    # dB, usually 0
    low_note:   int = 0    # MIDI note range low
    high_note:  int = 127  # MIDI note range high
    low_vel:    int = 0    # Velocity range low
    high_vel:   int = 127  # Velocity range high


@dataclass
class AudioFileMetadata:
    """
    Optional metadata bundle passed to AudioWriter.write().

    All fields are optional; pass only the ones you need.  Unsupported
    fields for a given format are silently ignored.

    Parameters
    ----------
    title : str, optional
        Track or cue title written into the WAV LIST INFO INAM field.
    artist : str, optional
        Artist or composer written into the WAV LIST INFO IART field.
    comment : str, optional
        Free-text comment written into the WAV LIST INFO ICMT field.
    instrument : InstrumentInfo, optional
        MIDI instrument parameters written into the WAV inst chunk.
    loops : list of LoopPoint
        Loop regions written into the WAV smpl chunk.  Empty by default.
    """

    title:      Optional[str]            = None
    artist:     Optional[str]            = None
    comment:    Optional[str]            = None
    instrument: Optional[InstrumentInfo] = None
    loops:      List[LoopPoint]          = field(default_factory=list)
