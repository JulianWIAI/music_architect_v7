"""
bdra_rules.py — BDRA combinatoric engine for Matrix 1 (Section B).

BDRA timbral axes
-----------------
B (Brightness 0-3) : spectral centroid proxy; each step ≈ +2 Bark-scale units.
    0 = sub/dark  (<200 Hz centroid)
    1 = warm      (200-800 Hz)
    2 = bright    (800 Hz-4 kHz)
    3 = sparkle   (>4 kHz, air shelf present)

D (Density 0-3) : simultaneous voice count / texture thickness.
    0 = sparse single sine   (mono-source, one partial)
    1 = single clear voice   (one source, full harmonics)
    2 = moderate texture     (~2-4 simultaneous voices / layers)
    3 = dense / layered      (>4 voices, wide unison, ensemble)

A (Attack 0-3) : envelope onset time.
    0 = instantaneous  (<5 ms — click, pluck, stab)
    1 = fast           (5-30 ms — piano, brass, short bow)
    2 = medium         (30-100 ms — slow bow, horn, clarinet)
    3 = slow swell     (>100 ms — pads, choir, string ensemble)

R (Register 0-3) : fundamental pitch register.
    0 = sub bass   (<80 Hz fundamental)
    1 = bass/lo-mid (80-250 Hz)
    2 = mid        (250 Hz-2 kHz)
    3 = treble/air (>2 kHz fundamental or primary content)

Music theory foundations
-------------------------
Matrix 1 derives valid BDRA ranges from five psychoacoustic principles:

  P1 — Sub-bass exclusivity (critical-band masking):
       Two sources whose fundamentals share the same critical band (Bark 0-2,
       i.e. both D0 R0) will sum incoherently, producing comb-filtering below
       80 Hz where the ear cannot separate pitch.  Maximum one D0 R0 active.

  P2 — Register monotonicity (spectral layering):
       Optimal energy placement requires each successive role to sit in a
       higher register: R_bass ≤ R_chords ≤ R_melody ≤ R_arp.
       Violations cause masking of the lower layer by the upper.

  P3 — Attack separation in shared register (transient crowding):
       Two voices at the same register (R) with the same attack speed (A)
       compete for the same onset moment.  Masking threshold rises ≥ 10 dB
       at the onset if |A_i − A_j| = 0 and R_i = R_j.
       Constraint: |A_i − A_j| ≥ 1 for any pair sharing R.

  P4 — Density budget (spectral mud threshold):
       Total simultaneous voice density Σ D across active tracks is bounded
       per branch.  Exceeding the budget raises the noise floor inside the
       300-3000 Hz band by ≈ 3 dB per D-unit over budget (ITU-R BS.1770
       loudness model approximation).
       Branch budgets (6 tracks, excluding kick):
         A: ≤ 8   (lean — 808 kick already anchors sub)
         B: ≤ 10  (moderate — acoustic kick leaves mid open)
         C: ≤ 12  (lush — slow kick invites dense D3 pads)

  P5 — Brightness contrast (lead voice cut-through):
       The melody voice must be perceptually brighter than the bass to sit
       above the harmonic root without EQ.  Constraint: B_melody > B_bass.
       Minimum safe headroom: +1 B step (≈ +4 dB perceived brightness).

Branch rules (kick BDRA → valid ranges for supporting tracks)
-------------------------------------------------------------
Branch A  kick B0 D0 A0 R0 — Pure sine / 808
    Bass   : B(0-2)  D(0-1)  A(0-1)  R(0-1)
    Chords : B(1-2)  D(1-2)  A(1-2)  R(2-2)
    Melody : B(2-3)  D(1-2)  A(0-1)  R(2-3)
    Arp    : B(3-3)  D(1-1)  A(0-1)  R(2-3)
    Pads   : B(1-2)  D(1-2)  A(3-3)  R(2-3)
    Stabs  : B(2-3)  D(1-2)  A(0-0)  R(2-2)

Branch B  kick B1 D2 A0 R1 — Acoustic / layered
    Bass   : B(0-2)  D(1-1)  A(0-2)  R(0-1)
    Chords : B(1-3)  D(1-2)  A(1-3)  R(2-2)
    Melody : B(2-3)  D(1-2)  A(0-2)  R(2-3)
    Arp    : B(3-3)  D(1-1)  A(0-1)  R(2-3)
    Pads   : B(1-2)  D(2-3)  A(3-3)  R(2-3)
    Stabs  : B(2-3)  D(2-2)  A(0-0)  R(2-2)

Branch C  kick B0 D1 A3 R0 — Sub-boom / soft taiko
    Bass   : B(0-1)  D(1-1)  A(0-0)  R(0-1)   ← A=0 mandatory (P3: slow kick)
    Chords : B(1-2)  D(2-3)  A(3-3)  R(2-2)   ← D3 allowed (P4 budget still safe)
    Melody : B(2-3)  D(1-2)  A(1-2)  R(2-3)
    Arp    : B(3-3)  D(1-1)  A(0-0)  R(2-3)   ← A=0 mandatory (P3: restores grid)
    Pads   : B(1-2)  D(2-3)  A(3-3)  R(2-3)
    Stabs  : B(1-3)  D(1-2)  A(0-0)  R(2-2)
"""

from __future__ import annotations
import json
import pathlib
from typing import Dict, List, Optional, Tuple

# ── Kick branch definitions ───────────────────────────────────────────────────

KICK_BRANCHES: List[Dict] = [
    {'branch': 'A', 'code': 'B0 D0 A0 R0', 'desc': 'Pure sine / 808'},
    {'branch': 'B', 'code': 'B1 D2 A0 R1', 'desc': 'Acoustic / layered'},
    {'branch': 'C', 'code': 'B0 D1 A3 R0', 'desc': 'Sub-boom / taiko'},
]

# ── Branch rules: (min, max) inclusive per dimension per track ────────────────

BRANCH_RULES: Dict[str, Dict[str, Dict[str, Tuple[int, int]]]] = {
    'A': {
        'bass':   {'B': (0, 2), 'D': (0, 1), 'A': (0, 1), 'R': (0, 1)},
        'chords': {'B': (1, 2), 'D': (1, 2), 'A': (1, 2), 'R': (2, 2)},
        'melody': {'B': (2, 3), 'D': (1, 2), 'A': (0, 1), 'R': (2, 3)},
        'arp':    {'B': (3, 3), 'D': (1, 1), 'A': (0, 1), 'R': (2, 3)},
        'pads':   {'B': (1, 2), 'D': (1, 2), 'A': (3, 3), 'R': (2, 3)},
        'stabs':  {'B': (2, 3), 'D': (1, 2), 'A': (0, 0), 'R': (2, 2)},
    },
    'B': {
        'bass':   {'B': (0, 2), 'D': (1, 1), 'A': (0, 2), 'R': (0, 1)},
        'chords': {'B': (1, 3), 'D': (1, 2), 'A': (1, 3), 'R': (2, 2)},
        'melody': {'B': (2, 3), 'D': (1, 2), 'A': (0, 2), 'R': (2, 3)},
        'arp':    {'B': (3, 3), 'D': (1, 1), 'A': (0, 1), 'R': (2, 3)},
        'pads':   {'B': (1, 2), 'D': (2, 3), 'A': (3, 3), 'R': (2, 3)},
        'stabs':  {'B': (2, 3), 'D': (2, 2), 'A': (0, 0), 'R': (2, 2)},
    },
    'C': {
        'bass':   {'B': (0, 1), 'D': (1, 1), 'A': (0, 0), 'R': (0, 1)},
        'chords': {'B': (1, 2), 'D': (2, 3), 'A': (3, 3), 'R': (2, 2)},
        'melody': {'B': (2, 3), 'D': (1, 2), 'A': (1, 2), 'R': (2, 3)},
        'arp':    {'B': (3, 3), 'D': (1, 1), 'A': (0, 0), 'R': (2, 3)},
        'pads':   {'B': (1, 2), 'D': (2, 3), 'A': (3, 3), 'R': (2, 3)},
        'stabs':  {'B': (1, 3), 'D': (1, 2), 'A': (0, 0), 'R': (2, 2)},
    },
}

_DENSITY_BUDGET: Dict[str, int] = {'A': 8, 'B': 10, 'C': 12}

# Ordered roles for register monotonicity check (P2)
_REGISTER_ORDER = ['bass', 'chords', 'melody', 'arp']


# ── Core helpers ──────────────────────────────────────────────────────────────

def parse_bdra(code: str) -> Dict[str, int]:
    """Parse 'B1 D2 A0 R3' → {'B': 1, 'D': 2, 'A': 0, 'R': 3}."""
    return {p[0]: int(p[1]) for p in code.split()}


def in_range(code: str, rules: Dict[str, Tuple[int, int]]) -> bool:
    """Return True if every BDRA dimension of *code* falls within *rules*."""
    if not rules:
        return True
    v = parse_bdra(code)
    return all(lo <= v.get(d, 0) <= hi for d, (lo, hi) in rules.items())


def compatible_branches(track: str, code: str) -> List[str]:
    """Which branches (A/B/C) accept this instrument on this track?"""
    return [
        kb['branch'] for kb in KICK_BRANCHES
        if in_range(code, BRANCH_RULES[kb['branch']].get(track, {}))
    ]


def filter_instruments(branch: str, track: str, instruments: List[dict]) -> List[dict]:
    """Return only instruments compatible with *branch* + *track* branch rules."""
    rules = BRANCH_RULES.get(branch, {}).get(track, {})
    return [i for i in instruments if in_range(i['code'], rules)]


# ── Music theory validator ────────────────────────────────────────────────────

class ValidationResult:
    """Scored validation report for a complete instrument selection."""

    def __init__(self) -> None:
        self.score: int = 100
        self.violations: List[str] = []
        self.warnings: List[str] = []

    def deduct(self, points: int, msg: str) -> None:
        self.score = max(0, self.score - points)
        self.violations.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def label(self) -> str:
        if self.score >= 90:
            return 'EXCELLENT'
        if self.score >= 70:
            return 'GOOD'
        if self.score >= 50:
            return 'ACCEPTABLE'
        return 'WARNING'


def validate_selection(branch: str, selection: Dict[str, str]) -> ValidationResult:
    """
    Validate a complete instrument selection against the five music theory
    principles (P1-P5) and the branch rules.

    Parameters
    ----------
    branch    : 'A', 'B', or 'C'
    selection : {track_key: bdra_code_string}
                e.g. {'bass': 'B1 D1 A0 R1', 'chords': 'B1 D2 A3 R2', ...}

    Returns
    -------
    ValidationResult with score (0-100) and violation messages.
    """
    r = ValidationResult()
    parsed = {track: parse_bdra(code) for track, code in selection.items()}

    # ── Branch rule compliance ─────────────────────────────────────────────
    for track, code in selection.items():
        rules = BRANCH_RULES.get(branch, {}).get(track, {})
        if rules and not in_range(code, rules):
            v = parsed[track]
            failing = [
                f"{d}={v[d]} outside [{lo},{hi}]"
                for d, (lo, hi) in rules.items()
                if not (lo <= v.get(d, 0) <= hi)
            ]
            r.deduct(15, f"P0 {track.upper()}: outside Branch {branch} range — {', '.join(failing)}")

    # ── P1 — Sub-bass exclusivity ──────────────────────────────────────────
    sub_bass_tracks = [t for t, v in parsed.items() if v.get('D') == 0 and v.get('R') == 0]
    if len(sub_bass_tracks) > 1:
        r.deduct(20, f"P1 Sub-bass: {', '.join(sub_bass_tracks)} both claim D0 R0 "
                     f"— critical-band masking below 80 Hz")

    # ── P2 — Register monotonicity ─────────────────────────────────────────
    prev_r, prev_t = -1, ''
    for track in _REGISTER_ORDER:
        if track not in parsed:
            continue
        cur_r = parsed[track].get('R', 0)
        if prev_r > cur_r:
            r.deduct(10, f"P2 Register: {prev_t.upper()} R={prev_r} > {track.upper()} R={cur_r} "
                         f"— upper layer masks lower (spectral inversion)")
        prev_r, prev_t = cur_r, track

    # ── P3 — Attack separation in shared register ──────────────────────────
    tracks = list(parsed.keys())
    for i in range(len(tracks)):
        for j in range(i + 1, len(tracks)):
            ti, tj = tracks[i], tracks[j]
            vi, vj = parsed[ti], parsed[tj]
            if vi.get('R') == vj.get('R') and vi.get('A') == vj.get('A'):
                r.deduct(10, f"P3 Attack: {ti.upper()} + {tj.upper()} share "
                             f"R={vi['R']} A={vi['A']} — transient crowding at onset")

    # ── P4 — Density budget ────────────────────────────────────────────────
    budget = _DENSITY_BUDGET.get(branch, 10)
    total_d = sum(v.get('D', 0) for v in parsed.values())
    if total_d > budget:
        over = total_d - budget
        r.deduct(min(15, over * 5), f"P4 Density: Σ D={total_d} exceeds Branch {branch} budget "
                                     f"({budget}) by {over} — spectral mud risk in 300-3000 Hz band")

    # ── P5 — Brightness contrast ───────────────────────────────────────────
    if 'bass' in parsed and 'melody' in parsed:
        b_bass   = parsed['bass'].get('B', 0)
        b_melody = parsed['melody'].get('B', 0)
        if b_melody <= b_bass:
            r.deduct(15, f"P5 Brightness: melody B={b_melody} ≤ bass B={b_bass} "
                         f"— lead voice will not cut through without EQ")
        elif b_melody - b_bass == 1:
            r.warn(f"P5 Brightness: melody B={b_melody}, bass B={b_bass} — "
                   f"1-step margin; consider a shelving EQ at 4 kHz to secure separation")

    return r


# ── Data loader ───────────────────────────────────────────────────────────────

def best_selection(
    branch: str,
    catalogue: Dict[str, List[dict]],
    seed: Optional[Dict[str, dict]] = None,
) -> Dict[str, dict]:
    """
    Return the {track: instrument_dict} combination that maximises the BDRA
    validation score for *branch*.

    Parameters
    ----------
    branch    : 'A', 'B', or 'C'
    catalogue : full instrument catalogue {track: [inst_dict, …]}
    seed      : optional starting instruments {track: inst_dict}.
                Seeded instruments are placed first in each track's candidate
                list so the optimizer tries to keep them where possible — it
                only replaces a seeded pick when a swap raises the score.
                Instruments not in the catalogue are included as candidates so
                palette picks outside bdra_instruments.json are still evaluated.

    Algorithm: coordinate descent.
      1. Start every track from its seeded instrument (or first valid catalogue
         entry when no seed is supplied).
      2. For each track, try every candidate; keep whichever raises the overall
         score most.  Repeat until a full pass changes nothing.

    Typically converges to 100/100 in one or two passes.
    Returns {} if the catalogue has no valid instruments for any track.
    """
    valid: Dict[str, List[dict]] = {
        track: filter_instruments(branch, track, catalogue.get(track, []))
        for track in BRANCH_RULES.get(branch, {})
    }

    # Build candidate lists: seeded instrument first, then catalogue alternatives.
    # Including the seed even when it is not in the catalogue lets the optimizer
    # evaluate palette-specific instruments that live outside bdra_instruments.json.
    candidates: Dict[str, List[dict]] = {}
    for track, insts in valid.items():
        if seed and track in seed:
            seed_inst = seed[track]
            already_present = any(i['code'] == seed_inst['code'] for i in insts)
            # Prepend seed so it is the first candidate tried (= default start)
            candidates[track] = ([seed_inst] if not already_present else []) + insts
        else:
            candidates[track] = insts

    # Start from first candidate per track (= seed if supplied, else catalogue[0])
    selection: Dict[str, dict] = {
        track: cands[0] for track, cands in candidates.items() if cands
    }
    if not selection:
        return selection

    def _score(sel: Dict[str, dict]) -> int:
        return validate_selection(branch, {t: i['code'] for t, i in sel.items()}).score

    for _ in range(4):      # 4 passes is always enough; usually converges in ≤ 2
        improved = False
        for track, cands in candidates.items():
            if not cands or track not in selection:
                continue
            best_inst  = selection[track]
            best_score = _score(selection)
            if best_score == 100:
                break       # already perfect — skip remaining tracks in pass
            for inst in cands:
                trial = {**selection, track: inst}
                s = _score(trial)
                if s > best_score:
                    best_score = s
                    best_inst  = inst
                    if s == 100:
                        break
            if best_inst is not selection[track]:
                selection[track] = best_inst
                improved = True
        if not improved:
            break

    return selection


def load_instruments() -> Dict[str, List[dict]]:
    """Load curated BDRA instrument catalogue from bdra_instruments.json."""
    path = (pathlib.Path(__file__).parent.parent.parent
            / 'data' / 'production_guide' / 'json' / 'bdra_instruments.json')
    return json.loads(path.read_text(encoding='utf-8'))
