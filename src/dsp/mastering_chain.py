"""
src.dsp.mastering_chain — Full post-mastering DSP orchestrator.

Pipeline (in order):
  1. Read WAV → float32 numpy array
  2. Genre EQ (ParametricEQ)
  3. Bus Compressor  (light glue: 2:1, 30 ms attack, threshold from genre JSON)
  4. Parallel Compression (NY-style blend from genre JSON)
  5. M/S Processing (side HPF + stereo width shelf, stereo only)
  6. LUFS Normalisation (ITU-R BS.1770-4) to target platform
  7. Limiter (true-peak ceiling from target preset)
  8. Write 24-bit WAV (vectorised, no Python loop)

The main entry point is MasteringChain().process(...).
"""
from __future__ import annotations

import json
import shutil
import tempfile
import wave
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from src.dsp.compressor import Compressor, Limiter
from src.dsp.equalizer import build_genre_eq
from src.dsp.loudness import measure_lufs, normalize_to_lufs
from src.dsp.mastering_targets import TARGETS, MasteringTarget
from src.dsp.ms_processor import from_genre_data as ms_from_genre
from src.dsp.parallel_compression import from_genre_data as pc_from_genre

# ── Genre JSON directory ───────────────────────────────────────────────────────
_GENRE_JSON_DIR = Path(__file__).parent.parent.parent / 'data' / 'production_guide' / 'json'


# ── Genre data loader ──────────────────────────────────────────────────────────

def _load_genre_data(genre: str) -> dict:
    """
    Load the genre JSON file from *_GENRE_JSON_DIR/<genre>.json*.

    Returns an empty dict if the file does not exist or cannot be parsed.
    """
    path = _GENRE_JSON_DIR / f'{genre}.json'
    if not path.is_file():
        return {}
    try:
        with path.open(encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {}


# ── WAV I/O ───────────────────────────────────────────────────────────────────

def _read_wav_float32(path: str) -> Tuple[np.ndarray, int]:
    """
    Read a WAV file and return (samples_float32, sample_rate).

    Supports 8-bit unsigned, 16-bit, 24-bit, and 32-bit float PCM.
    Output shape: (N,) for mono, (N, n_ch) for multi-channel.
    """
    with wave.open(path, 'rb') as wf:
        n_ch   = wf.getnchannels()
        sw     = wf.getsampwidth()   # bytes per sample
        sr     = wf.getframerate()
        n_fr   = wf.getnframes()
        raw    = wf.readframes(n_fr)

    raw = np.frombuffer(raw, dtype=np.uint8)

    if sw == 1:
        # 8-bit PCM: unsigned [0, 255] → float [-1, 1)
        samples = (raw.astype(np.float32) - 128.0) / 128.0
    elif sw == 2:
        # 16-bit signed PCM
        samples = raw.view(np.dtype('<i2')).astype(np.float32) / 32768.0
    elif sw == 3:
        # 24-bit PCM — no native numpy dtype; unpack manually (vectorised)
        total   = len(raw) // 3
        raw3    = raw[: total * 3].reshape(total, 3)
        # Zero-extend to int32 (little-endian: bytes [0]=LSB, [2]=MSB)
        i32     = (raw3[:, 0].astype(np.int32)
                   | (raw3[:, 1].astype(np.int32) << 8)
                   | (raw3[:, 2].astype(np.int32) << 16))
        # Sign-extend bit 23
        i32[i32 >= (1 << 23)] -= (1 << 24)
        samples = i32.astype(np.float32) / float(1 << 23)
    elif sw == 4:
        # 32-bit float PCM
        samples = raw.view(np.dtype('<f4')).astype(np.float32)
    else:
        raise ValueError(f"Unsupported WAV sample width: {sw} bytes")

    if n_ch > 1:
        samples = samples.reshape(-1, n_ch)

    return samples, sr


def _write_wav_float32(
    path:      str,
    samples:   np.ndarray,
    sr:        int,
    bit_depth: int = 24,
) -> None:
    """
    Write *samples* (float32) to a WAV file at *path*.

    Supports 16-bit (int16) and 24-bit (packed, vectorised) output.
    The 24-bit packer uses only numpy operations — no Python sample loop.
    """
    flat = samples.flatten().astype(np.float32)
    n_ch = samples.shape[1] if samples.ndim == 2 else 1

    if bit_depth == 24:
        # ── Vectorised 24-bit packing ──────────────────────────────────────────
        # Scale float → int32, clamp to 24-bit range
        vals = (flat * 8_388_607.0).clip(-8_388_608, 8_388_607).astype(np.int32)

        buf          = np.empty(len(vals) * 3, dtype=np.uint8)
        buf[0::3]    = (vals         & 0xFF).astype(np.uint8)  # LSB
        buf[1::3]    = ((vals >>  8) & 0xFF).astype(np.uint8)  # middle byte
        buf[2::3]    = ((vals >> 16) & 0xFF).astype(np.uint8)  # MSB (sign here)
        raw_bytes    = buf.tobytes()
        sw           = 3

    elif bit_depth == 16:
        vals      = (flat * 32767.0).clip(-32768, 32767).astype(np.dtype('<i2'))
        raw_bytes = vals.tobytes()
        sw        = 2

    else:
        raise ValueError(f"Unsupported bit depth: {bit_depth}")

    with wave.open(path, 'wb') as wf:
        wf.setnchannels(n_ch)
        wf.setsampwidth(sw)
        wf.setframerate(sr)
        wf.writeframes(raw_bytes)


# ── Mastering chain ────────────────────────────────────────────────────────────

class MasteringChain:
    """
    Full post-mastering DSP chain.

    Instantiate once and call process() for each render.
    """

    def process(
        self,
        wav_in:     str,
        wav_out:    str,
        genre:      str            = 'pop',
        variant_id: str            = 'neutral',
        target_id:  str            = 'streaming',
        genre_data: Optional[dict] = None,
    ) -> Tuple[bool, str]:
        """
        Apply the full mastering chain to *wav_in* and write *wav_out*.

        Parameters
        ----------
        wav_in : str
            Path to the input WAV rendered by FluidSynth.
        wav_out : str
            Path where the mastered WAV will be written.
            Can equal *wav_in* — a tempfile is used internally.
        genre : str
            Genre key (e.g. 'trap', 'pop').
        variant_id : str
            EQ variant key ('bright', 'neutral', 'dark').
        target_id : str
            Loudness target preset ID ('streaming', 'broadcast', 'sync_licensing').
        genre_data : dict, optional
            Pre-loaded genre JSON dict; loaded from disk if None.

        Returns
        -------
        (True, status_message) on success, or (False, error_message) on failure.
        """
        try:
            # ── 1. Read input WAV ──────────────────────────────────────────────
            samples, sr = _read_wav_float32(wav_in)

            # ── 2. Load genre data ─────────────────────────────────────────────
            if genre_data is None:
                genre_data = _load_genre_data(genre)

            # ── 3. Genre parametric EQ ─────────────────────────────────────────
            samples = build_genre_eq(genre, variant_id, sr).apply(samples, sr)

            # ── 4. Bus Compressor ──────────────────────────────────────────────
            # Threshold from genre JSON bus_inserts.master.comp_threshold_dbfs
            master_bus  = (genre_data
                           .get('bus_inserts', {})
                           .get('master', {}))
            bus_thr_db  = float(master_bus.get('comp_threshold_dbfs', -22.0))
            bus_comp    = Compressor(
                threshold_db = bus_thr_db,
                ratio        = 2.0,
                attack_ms    = 30.0,
                release_ms   = 300.0,
                knee_db      = 4.0,
                makeup_db    = 1.5,
            )
            samples = bus_comp.process(samples, sr)

            # ── 5. NY-style parallel compression ──────────────────────────────
            samples = pc_from_genre(genre_data).process(samples, sr)

            # ── 6. M/S processing (stereo only) ───────────────────────────────
            if samples.ndim == 2 and samples.shape[1] >= 2:
                samples = ms_from_genre(genre_data).process(samples, sr)

            # ── 7. LUFS normalisation ──────────────────────────────────────────
            target: MasteringTarget = TARGETS.get(target_id, TARGETS['streaming'])
            samples = normalize_to_lufs(samples, sr, target.target_lufs)

            # ── 8. True-peak limiter ───────────────────────────────────────────
            samples = Limiter(ceiling_db=target.true_peak_dbfs).process(samples, sr)

            # ── 9. Write output WAV ────────────────────────────────────────────
            if wav_in == wav_out:
                # In-place: write to a temp file then atomically move
                tmp_fd, tmp_path = tempfile.mkstemp(suffix='.wav')
                import os
                os.close(tmp_fd)
                _write_wav_float32(tmp_path, samples, sr, bit_depth=24)
                shutil.move(tmp_path, wav_out)
            else:
                _write_wav_float32(wav_out, samples, sr, bit_depth=24)

            # ── 10. Measure final loudness and compose status message ──────────
            final_lufs = measure_lufs(samples, sr)
            lufs_str   = f'{final_lufs:.1f}' if not (final_lufs == float('-inf')) else '-inf'
            msg = (
                f'Mastered → {target.label}  '
                f'({target.target_lufs} LUFS, {target.true_peak_dbfs} dBTP)  '
                f'[measured: {lufs_str} LUFS]'
            )
            return True, msg

        except Exception as exc:
            return False, str(exc)
