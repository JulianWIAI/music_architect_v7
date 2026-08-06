"""
gradual_de_orchestration.py — GradualDeOrchestrationProtocol for staggered outro wind-down.

Music Theory Basis
------------------
The outro is not simply a fade-out — it is the mirror image of the intro, and its
design principles are equally grounded in centuries of compositional practice.

The Reverse Principle
    In the intro, instruments enter one by one until the full arrangement is heard.
    In the outro, instruments exit one by one in the REVERSE ORDER of their entry.
    This creates a large-scale arch form (ABA or arch form) where the listener is
    returned to the same sonic world that opened the song.

    Music theory grounding:
      Ternary form (ABA): The oldest and most universal formal principle in Western
          music. The B section (verse/chorus body) is framed by two A sections
          (intro/outro). The outro returns to the intro's sparse instrumentation.
      Recapitulation: Sonata form (Haydn, Mozart, Beethoven) always closes with a
          recapitulation where earlier material returns. The orchestral texture at
          the end mirrors the exposition's opening texture.
      DJ mixing: Professional DJs strip the outro to its single identifying element
          (the "naked" loop) before mixing the next track. The last element heard
          is always the one that best represents the track's identity.

Genre-Specific Exit Orders (reverse of intro entry orders)
----------------------------------------------------------
  POP     : Pad layer exits (25 %) → hi-hat exits (50 %) → kick (75 %) → hook/bass last
  TRAP    : Kick exits (25 %)      → chord pad (50 %)    → hi-hat (75 %) → 808 bass last
  HIP-HOP : Pad exits (25 %)       → hi-hat (50 %)       → kick (75 %)   → bass sub last
  HOUSE   : Hi-hat exits (25 %)    → bass (50 %)         → kick (75 %)   → atmospheric pad last
  EDM     : Kick exits (25 %)      → sub-bass (50 %)     → hi-hat (50 %) → sweep pad last

The exit velocity fade
----------------------
Unlike a hard cut, each element undergoes a two-stage velocity fade before its exit:

  Stage 1 — Global outro fade: ALL active elements diminish from 100 % to
      exit_vel_end (40 %) linearly across the outro.  This gives the entire
      section a sense of winding down, like the energy draining from the room.

  Stage 2 — Pre-exit fade: Each element additionally fades to near-silence over
      fade_bars bars BEFORE its scheduled exit threshold.  This prevents the
      jarring "sudden stop" that sounds amateurish and mimics how professional
      producers automate track levels in their DAWs.

The combination of these two stages — a global fade AND a per-element pre-exit fade —
is what separates a professional fade-out from the generic all-at-once dimming that
plagues most algorithmic composition systems.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


# ── Genre exit schedules ──────────────────────────────────────────────────────
# Each value is the build_frac at which the element COMPLETELY EXITS.
# 1.00 = element plays to the very last bar (only global fade applied).
# 0.25 = element exits after the first quarter of the outro.
#
# Exit orders are derived from the REVERSE of GradualOrchestrationProtocol entry
# orders, implementing the Reverse Principle described above.

_GENRE_OUTRO_SCHEDULES: Dict[str, Dict[str, float]] = {
    # Pop: hook/piano opens → bass enters → kick+hat enter → pad last in.
    # Reverse: pad exits first → hat → kick → bass/hook last (returns to opening texture)
    'pop': {
        'pad_layer_exit':   0.25,
        'drums_hat_exit':   0.50,
        'drums_kick_exit':  0.75,
        'bass_exit':        1.00,  # bass remains; fades via global outro fade only
    },
    # Trap: 808 opens → hat → pad → kick last in.
    # Reverse: kick exits first → pad → hat → 808 last (genre identity element stays)
    'trap': {
        'drums_kick_exit':  0.25,
        'pad_layer_exit':   0.50,
        'drums_hat_exit':   0.75,
        'bass_exit':        1.00,  # 808 sub is the genre signature — last to leave
    },
    # Hip-hop: atmosphere opens → bass → kick+snare → arp/pad last in.
    # Reverse: pad/arp first → hat → kick → bass last
    'hiphop': {
        'pad_layer_exit':   0.25,
        'drums_hat_exit':   0.50,
        'drums_kick_exit':  0.75,
        'bass_exit':        1.00,
    },
    # House: atmospheric pad opens → kick → bass → hat last in.
    # Reverse: hat exits first → bass → kick → pad last (returns to atmospheric opening)
    'house': {
        'drums_hat_exit':   0.25,
        'bass_exit':        0.50,
        'drums_kick_exit':  0.75,
        'pad_layer_exit':   1.00,  # atmospheric pad (opened the track) is last
    },
    # EDM: atmospheric sweep opens → arp → sub-bass → kick last in.
    # Reverse: kick exits first → sub-bass+hat → pad last
    'edm': {
        'drums_kick_exit':  0.25,
        'bass_exit':        0.50,
        'drums_hat_exit':   0.50,
        'pad_layer_exit':   1.00,  # sweep/atmosphere plays to end
    },
}

# Fallback when genre has no specific schedule
_DEFAULT_OUTRO_SCHEDULE: Dict[str, float] = {
    'pad_layer_exit':   0.25,
    'drums_hat_exit':   0.50,
    'drums_kick_exit':  0.75,
    'bass_exit':        1.00,
}

# Genre alias normalisation (mirrors other modules)
_ALIASES: Dict[str, str] = {
    'jpop':    'pop',
    'cinematic': 'pop',   # cinematic follows a similar arch to pop
    'techno':  'edm',
    'dnb':     'edm',
    'ambient': 'house',
    'hip-hop': 'hiphop',
    'hip_hop': 'hiphop',
    'phonk':   'trap',
}


@dataclass
class OutroLayerPlan:
    """
    Output of GradualDeOrchestrationProtocol.build().

    Exit threshold fields are build_frac values (fraction of outro elapsed) at which
    each track makes its final exit.  A value of 1.00 means the track plays through
    the entire outro section, fading via the global velocity curve only.

    The two-stage velocity model:
      global fade  — applied to all active elements; diminishes from 1.0 to exit_vel_end
      pre-exit fade — applied per-element over fade_bars before its exit_threshold;
                      fades the element from its current level to near-silence
    """

    # ── Exit thresholds ───────────────────────────────────────────────────────
    bass_exit:        float   # fraction of outro at which bass fully exits
    drums_kick_exit:  float   # fraction at which kick + snare fully exit
    drums_hat_exit:   float   # fraction at which hi-hat fully exits
    pad_layer_exit:   float   # fraction at which secondary pad layer fully exits

    # ── Velocity fade parameters ──────────────────────────────────────────────
    exit_vel_end:  float = 0.40   # minimum velocity multiplier at outro end
    fade_bars:     int   = 2      # bars over which element pre-exit fade occurs

    def velocity_mult(
        self,
        build_frac:      float,
        exit_threshold:  float,
        section_bars:    int,
    ) -> float:
        """
        Return a combined velocity multiplier in [0.0, 1.0] for one element.

        Parameters
        ----------
        build_frac      : Fraction of the outro section elapsed (0.0 = first bar,
                          approaches 1.0 at last bar).  Computed as
                          `local_bar / max(1, section_bars)` in the generator.
        exit_threshold  : The build_frac at which this element completely exits.
        section_bars    : Total number of bars in the outro section.

        Returns
        -------
        0.0  — element has passed its exit threshold; generate no notes.
        >0.0 — active; scale velocity by this multiplier before emitting notes.

        The result combines:
          Stage 1: global fade  (all elements → exit_vel_end over the outro)
          Stage 2: pre-exit fade (per-element → 0 over fade_bars before exit)
        """
        if build_frac >= exit_threshold:
            return 0.0

        # Stage 1 — Global outro fade: applies uniformly to all active elements.
        # Linearly diminishes from 1.0 at build_frac=0 to exit_vel_end at build_frac=1.
        global_fade = 1.0 - (1.0 - self.exit_vel_end) * build_frac

        # Stage 2 — Pre-exit fade: only for elements that leave before outro end.
        # Ramps the element from its current level to near-silence over fade_bars.
        if exit_threshold < 1.0 and section_bars > 0:
            fade_window = self.fade_bars / float(section_bars)
            fade_start  = max(0.0, exit_threshold - fade_window)
            if build_frac >= fade_start:
                fade_progress = (build_frac - fade_start) / max(0.001, fade_window)
                fade_progress = min(1.0, fade_progress)
                # Multiply global fade by a linear fade-to-zero over the window
                return global_fade * (1.0 - fade_progress)

        return global_fade


class GradualDeOrchestrationProtocol:
    """
    Builds an OutroLayerPlan for a given genre.

    All methods are class-level — no instance required.  Stateless and safe for
    concurrent MIDI generation workers.
    """

    @classmethod
    def build(cls, genre: str, section_bars: int) -> OutroLayerPlan:
        """
        Return an OutroLayerPlan for the given genre.

        Parameters
        ----------
        genre        : Genre string from CompositionConfig (e.g. 'trap', 'pop').
        section_bars : Total number of bars in the outro section.

        Returns
        -------
        OutroLayerPlan with music-theory-backed exit thresholds.
        """
        canon    = _ALIASES.get(genre.lower(), genre.lower())
        schedule = _GENRE_OUTRO_SCHEDULES.get(canon, _DEFAULT_OUTRO_SCHEDULE)

        return OutroLayerPlan(
            bass_exit        = schedule['bass_exit'],
            drums_kick_exit  = schedule['drums_kick_exit'],
            drums_hat_exit   = schedule['drums_hat_exit'],
            pad_layer_exit   = schedule['pad_layer_exit'],
        )
