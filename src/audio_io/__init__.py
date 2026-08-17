"""
src.audio_io — High-quality multi-format audio I/O package.

Public surface
--------------
AudioWriter     — writes float audio to WAV / AIFF / RF64 / CAF / W64
OutputSpec      — configuration: format, bit depth, sample rate, dithering
AudioFormat     — container format enum  (WAV, AIFF, RF64, CAF, W64)
BitDepth        — sample encoding enum   (INT_16, INT_24, FLOAT_32, FLOAT_64)
AudioFileMetadata — optional metadata bundle (tags, loops, instrument info)
LoopPoint       — a single loop region (start / end frame)
InstrumentInfo  — MIDI instrument parameters (root note, velocity range, …)

Quick start
-----------
    from src.audio_io import AudioWriter, OutputSpec, AudioFormat, BitDepth

    writer = AudioWriter()                             # 24-bit WAV, 44.1 kHz
    writer.write('output.wav', samples)

    spec = OutputSpec(format=AudioFormat.AIFF, bit_depth=BitDepth.FLOAT_32)
    writer.write('output.aiff', samples, spec=spec)   # 32-bit float AIFF

Internal modules (not part of the public API)
---------------------------------------------
dithering          — TPDFDither (used internally by AudioWriter)
soundfile_backend  — libsndfile availability detection and format maps
wav_chunk_writer   — WAVChunkWriter (appends smpl/inst/LIST INFO chunks)
"""

from src.audio_io.audio_format import AudioFormat, BitDepth, OutputSpec
from src.audio_io.audio_metadata import AudioFileMetadata, InstrumentInfo, LoopPoint
from src.audio_io.audio_writer import AudioWriter

__all__ = [
    'AudioWriter',
    'OutputSpec',
    'AudioFormat',
    'BitDepth',
    'AudioFileMetadata',
    'LoopPoint',
    'InstrumentInfo',
]
