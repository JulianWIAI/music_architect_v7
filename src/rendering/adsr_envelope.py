"""
ADSREnvelope — Attack / Decay / Sustain / Release amplitude envelope generator.
"""


class ADSREnvelope:
    """
    Computes a normalised amplitude value at any point in a note's lifetime.

    Parameters are all in seconds; sustain is a level in [0, 1].
    """

    def __init__(self, attack: float = 0.01, decay: float = 0.1,
                 sustain: float = 0.7, release: float = 0.15):
        self.attack = attack
        self.decay = decay
        self.sustain = sustain
        self.release = release

    def get_amplitude(self, t: float, duration: float) -> float:
        """Return the envelope amplitude [0, 1] at time *t* for a note of *duration* seconds."""
        if t < 0:
            return 0.0
        if t < self.attack:
            return t / self.attack
        t2 = t - self.attack
        if t2 < self.decay:
            return 1.0 - (1.0 - self.sustain) * (t2 / self.decay)
        if t < duration:
            return self.sustain
        t3 = t - duration
        if t3 < self.release:
            return self.sustain * (1.0 - t3 / self.release)
        return 0.0
