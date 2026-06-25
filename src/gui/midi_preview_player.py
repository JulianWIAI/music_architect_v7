try:
    import pygame
    import pygame.mixer
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


class MIDIPreviewPlayer:
    def __init__(self):
        self.is_playing = False
        self._initialized = False

    def _init(self):
        if not PYGAME_AVAILABLE:
            return False
        if not self._initialized:
            try:
                pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=2048)
                self._initialized = True
            except:
                return False
        return True

    def play_wav(self, wav_path):
        if not self._init():
            return False
        try:
            self.stop()
            pygame.mixer.music.load(wav_path)
            pygame.mixer.music.play()
            self.is_playing = True
            return True
        except Exception as e:
            print(f"Play error: {e}")
            return False

    def stop(self):
        if self._initialized and PYGAME_AVAILABLE:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.unload()
            except:
                pass
        self.is_playing = False

    def is_busy(self):
        if self._initialized and PYGAME_AVAILABLE:
            try:
                return pygame.mixer.music.get_busy()
            except:
                return False
        return False

    def cleanup(self):
        self.stop()
        if self._initialized and PYGAME_AVAILABLE:
            try:
                pygame.mixer.quit()
            except:
                pass
