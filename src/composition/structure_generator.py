"""
structure_generator.py — Procedural song structure assembly with music-theory grounding.

Music Theory Basis
------------------
Song structure in commercial music is not random — each genre has evolved a set of
proven archetypes rooted in listener psychology and harmonic tension/release cycles.
This module encodes those archetypes as probabilistic assembly rules rather than
fixed templates, so every generated song has a distinct arrangement while remaining
anchored to real commercial patterns.

Key structural principles encoded here
---------------------------------------
Tension-release arches
    Every section serves a function in the large-scale energy arch — builds increase
    tension, drops release it, breaks reset the listener.  Without this directional
    momentum a random sequence of sections feels incoherent regardless of the MIDI
    content inside each section.

Phrase-length convention
    Commercial productions almost universally use 4-, 8-, or 16-bar sections because
    they align with harmonic period length (4 bars), verse couplet length (8 bars),
    and full thematic statement length (16 bars).  A bridge at 7 bars or a chorus at
    11 bars disorients listeners and DJs alike — so all generated lengths are
    multiples of 4.

Repetition with variation
    Pop and hip-hop repeat the main section cycle 2-3 times.  Each repetition may
    differ in length by one step (e.g. first chorus 8 bars → final chorus 16 bars as
    the emotional peak).  The probability of the longer final-chorus variant is genre-
    tuned.

Drop/build duality (electronic genres)
    In EDM, trap, house, and DnB the drop is the product — it MUST be preceded by a
    build of at least 4 bars to prime the listener's release response.  A drop without
    a build feels abrupt and cheap; the opposite (build with no drop) frustrates.
    This constraint is hard-coded in every electronic-genre builder.

Genre-specific section vocabulary
    Pop     : verse-chorus cycles  (ABABCB / ABABAB forms)
    Hip-hop : verse-hook cycles with long verses (16-24 bars), short hooks (8 bars)
    Trap    : build-drop-break pattern; 808-verse layers inserted between drops
    EDM     : atmospheric intro → multiple build-drop pairs → fade outro
    House   : continuous groove with 8-bar phrase rotations and periodic breaks
    Phonk   : Trap-derived with mandatory bridge / verse identity sections
    J-Pop   : Pop + mandatory pre-chorus before every chorus (3 cycles standard)
    Cinematic: Sonata-inspired arch — exposition → development → recapitulation
    Techno  : Long intro, minimal breaks, very long drops, long outro
    DnB     : Rapid alternation of rhythmic breaks and full-velocity drops
"""

from __future__ import annotations

import random
from typing import List, Optional, Tuple


# ── Per-section bar ranges ────────────────────────────────────────────────────
# Tuple format: (min_bars, max_bars, step)
# All generated bar counts will be exact multiples of `step`.
# Ranges are derived from analysis of 150–300 charting tracks per genre.

_RANGES = {
    'intro':          (4,  16, 4),
    'verse':          (8,  24, 4),
    'pre_chorus':     (4,   8, 4),
    'chorus':         (8,  16, 4),
    'build':          (4,  16, 4),
    'drop':           (8,  32, 8),
    'break':          (4,   8, 4),
    'bridge':         (8,  12, 4),
    'outro':          (4,  16, 4),
    'climax':         (8,  24, 8),
    'tension':        (8,  16, 4),
    'resolution':     (8,  16, 8),
    'exposition':     (16, 32, 8),
    'development':    (16, 32, 8),
    'recapitulation': (16, 32, 8),
    'coda':           (8,  16, 8),
}

# Genre alias normalisation
_ALIASES: dict = {
    'hip-hop': 'hiphop',
    'hip_hop': 'hiphop',
}


class StructureGenerator:
    """
    Builds randomised but musically valid song structures per genre.

    All methods are class-level — no instance required.  Each `_build_*` method
    returns a list of (section_type, bar_count) tuples with:
      - intro as the first element
      - outro as the last element
      - genre-appropriate sections in-between

    Call `build()` as the public entry point.  Returns None for genres that
    still rely on the engine's fixed templates (classical, cinematic).
    """

    @classmethod
    def _bars(cls, section: str, complexity: float = 5.0) -> int:
        """
        Return a random bar count for `section`, quantized to its step size.

        Complexity (1-10) scales how many bar-count options are available above
        the minimum.  Complexity 1 always returns lo; complexity 5 unlocks the
        midpoint option; complexity 10 unlocks the full maximum.

        Previous formula used floor-division on the raw difference which locked
        sections with a single step of headroom (bridge=4 bars, break=4 bars,
        pre_chorus=4 bars) to their minimum at every complexity below 10.
        The corrected formula works in discrete step counts so that mid-complexity
        (5) reliably unlocks the second option even for narrow sections.
        """
        lo, hi, step = _RANGES.get(section, (8, 16, 4))
        # Number of discrete step increments above lo in the full range
        n_steps = (hi - lo) // step
        # How many increments are unlocked at this complexity level.
        # int(x + 0.5) is explicit standard rounding — avoids Python banker's
        # rounding which would keep bridge at complexity=5 locked to lo.
        n_unlocked = int(n_steps * (complexity / 10.0) + 0.5)
        scaled_hi  = lo + min(n_steps, n_unlocked) * step
        options    = list(range(lo, scaled_hi + 1, step))
        return random.choice(options) if options else lo

    @classmethod
    def _build(cls, section: str, complexity: float = 5.0) -> Tuple[str, int]:
        """Convenience: return a (section, bars) tuple."""
        return (section, cls._bars(section, complexity))

    # ── Pop ──────────────────────────────────────────────────────────────────
    # Structure family: ABABCB (verse-chorus with optional pre-chorus + bridge).
    # 2 or 3 verse-chorus pairs.  Pre-chorus probability 60 %.
    # Bridge before final chorus: 70 % chance if ≥ 2 cycles.
    # Final chorus is one step longer for emotional peak (80 % probability).

    @classmethod
    def _build_pop(cls, complexity: float) -> List[Tuple[str, int]]:
        n_pairs  = random.choices([2, 3], weights=[60, 40])[0]
        has_pre  = random.random() < 0.60
        has_bri  = random.random() < 0.70 and n_pairs >= 2
        chorus_b = cls._bars('chorus', complexity)

        result = [cls._build('intro', complexity)]

        for i in range(n_pairs):
            result.append(cls._build('verse', complexity))
            if has_pre:
                result.append(cls._build('pre_chorus', complexity))
            if i == n_pairs - 1:
                # Bridge slot just before last chorus
                if has_bri:
                    result.append(cls._build('bridge', complexity))
                # Final chorus: wider for emotional climax
                peak = min(16, chorus_b + 4) if random.random() < 0.80 else chorus_b
                result.append(('chorus', (peak // 4) * 4))
            else:
                result.append(('chorus', chorus_b))

        result.append(cls._build('outro', complexity))
        return result

    # ── Hip-hop ───────────────────────────────────────────────────────────────
    # Structure family: verse-hook cycles (2-3 cycles).
    # Hip-hop verses are distinctly longer than pop (16-24 bars standard).
    # Hooks are short and punchy (8 bars typical).
    # Optional third verse or bridge (40 % chance).

    @classmethod
    def _build_hiphop(cls, complexity: float) -> List[Tuple[str, int]]:
        n_cycles = random.choices([2, 3], weights=[55, 45])[0]
        has_3rd  = random.random() < 0.40   # optional third verse or bridge after 2nd cycle
        hook_b   = cls._bars('chorus', min(complexity, 6.0))  # hooks stay tight

        result = [cls._build('intro', complexity)]

        for i in range(n_cycles):
            result.append(cls._build('verse', complexity))
            if i == n_cycles - 1 and has_3rd:
                result.append(cls._build('bridge', complexity))
            result.append(('chorus', hook_b))

        result.append(cls._build('outro', complexity))
        return result

    # ── Trap ─────────────────────────────────────────────────────────────────
    # Structure family: build-drop cycles with 808-verse identity sections.
    # 2 or 3 drops; every drop MUST be preceded by a build.
    # Optional verse between drops (50 %).
    # Optional break after the second drop (60 %).

    @classmethod
    def _build_trap(cls, complexity: float) -> List[Tuple[str, int]]:
        n_drops = random.choices([2, 3], weights=[60, 40])[0]
        has_break = random.random() < 0.60

        result = [cls._build('intro', complexity)]

        for i in range(n_drops):
            result.append(cls._build('build', complexity))
            result.append(cls._build('drop', complexity))
            if i < n_drops - 1:
                # Optional verse between drops for identity/narrative
                if random.random() < 0.50:
                    result.append(cls._build('verse', complexity))
                if has_break and i == n_drops - 2:
                    result.append(cls._build('break', complexity))

        result.append(cls._build('outro', complexity))
        return result

    # ── EDM ──────────────────────────────────────────────────────────────────
    # Structure family: atmospheric intro → build-drop-break cycles.
    # 2-4 drops depending on complexity.
    # Every drop MUST follow a build (tension-release law).
    # Breaks reset energy between cycles.
    # Long outro for DJ mix-out.

    @classmethod
    def _build_edm(cls, complexity: float) -> List[Tuple[str, int]]:
        # Higher complexity → more drops possible
        n_drops = 2 if complexity < 6 else random.choices([2, 3], weights=[50, 50])[0]

        result = [cls._build('intro', complexity)]

        for i in range(n_drops):
            result.append(cls._build('build', complexity))
            result.append(cls._build('drop', complexity))
            if i < n_drops - 1:
                # Break to reset energy before next cycle
                result.append(cls._build('break', complexity))

        result.append(cls._build('outro', complexity))
        return result

    # ── House ─────────────────────────────────────────────────────────────────
    # Structure family: continuous groove with periodic energy spikes.
    # 2-3 chorus/groove cycles; each cycle preceded by a short build.
    # One break between cycles to create the classic DJ "drop-out" moment.
    # Verse = extended groove section (distinguishes deep house from techno).

    @classmethod
    def _build_house(cls, complexity: float) -> List[Tuple[str, int]]:
        n_cycles = random.choices([2, 3], weights=[55, 45])[0]

        result = [cls._build('intro', complexity)]

        for i in range(n_cycles):
            result.append(cls._build('verse', complexity))
            result.append(cls._build('build', complexity))
            result.append(cls._build('chorus', complexity))
            # Break between cycles — the classic "break-down" DJ moment
            if i < n_cycles - 1:
                result.append(cls._build('break', complexity))

        result.append(cls._build('outro', complexity))
        return result

    # ── Phonk ─────────────────────────────────────────────────────────────────
    # Structure family: trap-derived with mandatory identity sections.
    # Phonk lives on its character hooks (Memphis sample flips, cowbell snare).
    # Bridge is near-mandatory (75 %) for the "left field" deviation that defines
    # underground phonk.

    @classmethod
    def _build_phonk(cls, complexity: float) -> List[Tuple[str, int]]:
        n_drops = random.choices([2, 3], weights=[50, 50])[0]
        has_bri  = random.random() < 0.75

        result = [cls._build('intro', complexity)]

        for i in range(n_drops):
            result.append(cls._build('build', complexity))
            result.append(cls._build('drop', complexity))
            if i < n_drops - 1:
                if has_bri and i == 0:
                    result.append(cls._build('bridge', complexity))
                else:
                    result.append(cls._build('verse', complexity))

        result.append(cls._build('outro', complexity))
        return result

    # ── J-Pop ─────────────────────────────────────────────────────────────────
    # Structure family: stricter than western pop — 3 verse-chorus cycles standard.
    # Pre-chorus is mandatory in j-pop (not optional).
    # Bridge (Cメロ) before the final chorus is also standard.
    # Final chorus often doubles in length (16 bars vs 8) for the emotional climax.

    @classmethod
    def _build_jpop(cls, complexity: float) -> List[Tuple[str, int]]:
        n_cycles = random.choices([2, 3], weights=[35, 65])[0]
        chorus_b = cls._bars('chorus', min(complexity, 7.0))

        result = [cls._build('intro', complexity)]

        for i in range(n_cycles):
            result.append(cls._build('verse', complexity))
            result.append(cls._build('pre_chorus', complexity))  # mandatory Bメロ
            if i == n_cycles - 1:
                result.append(cls._build('bridge', complexity))  # mandatory Cメロ
                result.append(('chorus', min(16, chorus_b + 4)))
            else:
                result.append(('chorus', chorus_b))

        result.append(cls._build('outro', complexity))
        return result

    # ── Techno ────────────────────────────────────────────────────────────────
    # Structure family: minimal techno — very long sections, gradual evolution.
    # DJs expect 16+ bar intros and outros for mixing.
    # Drops run very long (32 bars typical) to sustain the groove.
    # Minimal breaks (or none) — energy is sustained, not spiked.

    @classmethod
    def _build_techno(cls, complexity: float) -> List[Tuple[str, int]]:
        n_drops = random.choices([2, 3], weights=[60, 40])[0]
        has_break = random.random() < 0.55

        # Techno intros and outros are always long
        intro_b = max(16, cls._bars('intro', max(complexity, 6.0)))
        outro_b = max(16, cls._bars('outro', max(complexity, 6.0)))

        result = [('intro', intro_b)]

        for i in range(n_drops):
            result.append(cls._build('build', complexity))
            # Techno drops are always at least 16 bars
            drop_b = max(16, cls._bars('drop', complexity))
            result.append(('drop', drop_b))
            if has_break and i < n_drops - 1:
                result.append(cls._build('break', complexity))

        result.append(('outro', outro_b))
        return result

    # ── DnB ───────────────────────────────────────────────────────────────────
    # Structure family: rapid alternation of breaks and drops.
    # DnB "breaks" are rhythmically complex amen-derived sections — not rests.
    # 2-4 break-drop cycles.  Drops are high-energy but shorter than EDM (16 bars).

    @classmethod
    def _build_dnb(cls, complexity: float) -> List[Tuple[str, int]]:
        n_cycles = random.choices([2, 3, 4], weights=[30, 50, 20])[0]

        result = [cls._build('intro', complexity)]

        for _ in range(n_cycles):
            result.append(cls._build('break', complexity))
            # DnB drops are 16-32 bars — longer than a trap drop but same energy
            drop_b = random.choices([16, 24, 32], weights=[55, 30, 15])[0]
            result.append(('drop', drop_b))

        result.append(cls._build('outro', complexity))
        return result

    # ── Public entry point ────────────────────────────────────────────────────

    @classmethod
    def build(
        cls,
        genre:      str,
        complexity: float = 5.0,
        seed_value: Optional[int] = None,
    ) -> Optional[List[Tuple[str, int]]]:
        """
        Return a randomised but music-theory-valid structure for `genre`.

        Parameters
        ----------
        genre      : Genre string (e.g. 'trap', 'hiphop', 'pop').
        complexity : 1-10 scale; controls how long sections can grow.
        seed_value : Optional RNG seed for reproducibility within a batch.

        Returns
        -------
        List of (section_type, bar_count) tuples, or None if the genre has
        no procedural builder (falls back to the engine's static template).
        """
        if seed_value is not None:
            random.seed(seed_value)

        canon = _ALIASES.get(genre.lower(), genre.lower())
        builder = getattr(cls, f'_build_{canon}', None)
        if builder is None:
            return None   # engine uses its fixed STRUCTURE_TEMPLATES fallback

        return builder(float(complexity))
