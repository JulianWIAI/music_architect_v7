"""
midi_preview_player.py

Thin wrapper around pygame.mixer.music for WAV and MIDI playback.

Adds seek support on top of the basic play/stop API:
  - play_wav(path, start_sec)  — load and play, optionally from a mid-file offset.
  - seek(target_sec)           — jump to a new position while playing or paused.
  - get_current_sec()          — returns the current playback position in seconds.

Seeking uses pygame.mixer.music.play(0, start_sec), which is supported for
WAV and MP3 in pygame 2.x.  On older pygame or unsupported formats the seek
call is silently ignored and the audio continues from where it was; the visual
playhead may drift but no exception is raised.
"""

try:
    import pygame
    import pygame.mixer
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


class MIDIPreviewPlayer:
    """
    Audio player backed by pygame.mixer.music.

    Keeps track of the logical playback start position so that
    get_current_sec() can combine pygame's get_pos() (elapsed ms since
    last play() call) with the user-requested start offset.
    """

    def __init__(self):
        self.is_playing     = False
        self._initialized   = False
        # Offset in seconds from which the current play() call started.
        # Used to compute absolute position: start_sec + get_pos_ms / 1000.
        self._play_start_sec: float = 0.0

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init(self) -> bool:
        """Lazily initialise pygame.mixer on first use."""
        if not PYGAME_AVAILABLE:
            return False
        if not self._initialized:
            try:
                pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=2048)
                self._initialized = True
            except Exception:
                return False
        return True

    # ── Playback ──────────────────────────────────────────────────────────────

    def play_wav(self, wav_path: str, start_sec: float = 0.0) -> bool:
        """
        Load *wav_path* and start playback from *start_sec*.

        Parameters
        ----------
        wav_path  : Absolute path to the WAV file.
        start_sec : Position in seconds to begin playback from.
                    Requires pygame 2.x for WAV format; silently ignored on older
                    versions (playback always starts from 0 in that case).
        """
        if not self._init():
            return False
        try:
            self.stop()
            pygame.mixer.music.load(wav_path)
            pygame.mixer.music.play(0, start_sec)
            self._play_start_sec = start_sec
            self.is_playing      = True
            return True
        except Exception as exc:
            print(f"[MIDIPreviewPlayer] play_wav error: {exc}")
            return False

    def play_midi(self, midi_path: str) -> bool:
        """
        Play a MIDI file directly via pygame.

        Works on Windows (via DirectSound) and macOS (via CoreAudio).
        MIDI playback does not support seeking — get_current_sec() returns
        elapsed time only, with no file-offset correction.
        """
        if not self._init():
            return False
        try:
            self.stop()
            pygame.mixer.music.load(midi_path)
            pygame.mixer.music.play()
            self._play_start_sec = 0.0
            self.is_playing      = True
            return True
        except Exception as exc:
            print(f"[MIDIPreviewPlayer] play_midi error: {exc}")
            return False

    def seek(self, target_sec: float) -> bool:
        """
        Jump to *target_sec* in the currently loaded track.

        Re-issues play(0, target_sec) which works for MP3/OGG in all pygame
        versions and for WAV in pygame >= 2.1.  When the format does not
        support a start offset the audio restarts from 0, which is the
        least-surprising fallback.

        Returns True when the seek command was issued without error,
        regardless of whether the underlying format honoured it.
        """
        if not self._initialized or not PYGAME_AVAILABLE:
            return False
        try:
            pygame.mixer.music.play(0, target_sec)
            self._play_start_sec = target_sec
            self.is_playing      = True
            return True
        except Exception as exc:
            print(f"[MIDIPreviewPlayer] seek error: {exc}")
            return False

    def stop(self) -> None:
        """Stop playback, unload the current track, and reset the position counter."""
        if self._initialized and PYGAME_AVAILABLE:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            except Exception:
                pass
        self.is_playing      = False
        self._play_start_sec = 0.0

    # ── Position Query ────────────────────────────────────────────────────────

    def is_busy(self) -> bool:
        """Return True if audio is actively playing."""
        if self._initialized and PYGAME_AVAILABLE:
            try:
                return pygame.mixer.music.get_busy()
            except Exception:
                return False
        return False

    def get_current_sec(self) -> float:
        """
        Return the estimated current playback position in seconds.

        Combines the user-requested start offset with pygame's elapsed-time
        counter (get_pos returns ms since the last play() call).
        Returns 0.0 when not playing or pygame is unavailable.
        """
        if not self._initialized or not PYGAME_AVAILABLE:
            return 0.0
        try:
            pos_ms = pygame.mixer.music.get_pos()
            if pos_ms < 0:
                # pygame returns -1 when not playing
                return self._play_start_sec
            return self._play_start_sec + pos_ms / 1000.0
        except Exception:
            return 0.0

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self) -> None:
        """Tear down pygame.mixer on application exit."""
        self.stop()
        if self._initialized and PYGAME_AVAILABLE:
            try:
                pygame.mixer.quit()
            except Exception:
                pass
        self._initialized = False
