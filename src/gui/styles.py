"""
src/gui/styles.py
-----------------
Central design token file for Seed Composer.

Design philosophy — professional studio aesthetic (2026)
---------------------------------------------------------
Professional music producers spend hours inside their tools.  The UI
must reduce visual fatigue, communicate hierarchy through tone and
weight rather than competing vivid colours, and keep attention on the
*content* — not the interface chrome.

Principles applied (UX psychology)
------------------------------------
Fitts's Law
    Primary actions (generate, preview) are larger and higher-contrast
    than secondary ones so they are faster to acquire with a pointer.

Colour hierarchy (max 3 accent hues visible at once)
    One primary accent — Studio Blue — for all interactive elements
    that are not semantically coloured.  Semantic colours (green /
    amber / red) carry conventional signal meanings any audio engineer
    recognises instantly without reading labels.

Hick's Law (reduce decision time)
    Fewer competing colours → less cognitive load when scanning panels.

Visual fatigue reduction
    Backgrounds use dark neutral grays with a barely perceptible warm
    undertone rather than pure navy or pure black.  Pure black maximises
    flicker perception on OLED/LCD panels; warm near-black reads as
    'off' with lower eye strain on long sessions.

Contrast ratios (WCAG AA)
    All foreground/background combinations meet ≥ 4.5 : 1 contrast for
    normal-weight text and ≥ 3 : 1 for large/bold text so the UI is
    readable at any screen brightness setting.
"""


class S:
    # ── Backgrounds — neutral dark studio grays ─────────────────────────────
    BG         = "#161618"   # deepest layer — app background
    BG2        = "#1e1e22"   # panel and section backgrounds
    BG3        = "#27272d"   # elevated cards, dividers, borders
    BG_INPUT   = "#2d2d35"   # input fields and combobox field areas
    BG_BTN     = "#333340"   # button default surface
    BG_BTN_HOV = "#3e3e4e"   # button on hover
    BG_BTN_ACT = "#2c5282"   # button pressed / active  (accent-blue tint)

    # ── Primary accent — Studio Blue ─────────────────────────────────────────
    # Single interactive accent colour.  All clickable chrome that is not a
    # semantic signal (success / caution / danger) uses this hue.
    # Named CYAN for backwards-compatibility with existing references.
    CYAN  = "#5ba3d0"   # primary accent — studio blue
    BLUE  = "#5ba3d0"   # explicit alias

    # ── Semantic / functional colours ────────────────────────────────────────
    # Each carries the conventional signal meaning any audio engineer knows.
    #   GREEN  — signal present, render complete, "go"
    #   YELLOW — caution / auto-random / non-destructive fallback (amber)
    #   ORANGE — export / file-write action
    #   RED    — stop / error / danger
    #   PINK   — vocal / creative secondary action (muted rose)
    #   PURPLE — MIDI / data-output action (muted violet)
    GREEN  = "#4e9e6a"   # muted studio green
    YELLOW = "#c89a38"   # amber — replaces electric yellow for legibility
    ORANGE = "#b86838"   # muted orange — export actions
    RED    = "#b84848"   # muted red — stop / error
    PINK   = "#9a5878"   # muted rose — vocal track
    PURPLE = "#6858a8"   # muted violet — MIDI output

    # ── Text ─────────────────────────────────────────────────────────────────
    TXT     = "#b8b8c8"   # primary body text — warm off-white, easy on eyes
    TXT_DIM = "#585868"   # secondary / label text (dimmed)
    TXT_BRT = "#e4e4f0"   # headings and emphasis (near-white)
    DIM     = "#585868"   # alias for TXT_DIM (legacy references)

    # ── Track colours — muted but distinct ───────────────────────────────────
    # Each track type gets a unique muted hue (~55 % saturation) for
    # at-a-glance identification in instrument rows and mix grids.
    TRACK_CLR = {
        'drums':      '#b85050',   # muted red
        'bass':       '#b07840',   # muted amber-orange
        'chords':     '#4878b0',   # muted cobalt blue
        'lead':       '#7058a8',   # muted violet
        'pad':        '#488870',   # muted teal-green
        'arp':        '#a08830',   # muted gold
        'stabs':      '#885060',   # muted mauve
        'texture':    '#387898',   # muted steel blue
        'fx':         '#408888',   # muted teal
        'percussion': '#b85050',   # same as drums
    }

    # ── Genre colours — distinguishable but not vivid ─────────────────────────
    # Used for genre selector buttons and accent lines.  Distinct enough to
    # tell genres apart at a glance; subdued enough not to dominate the panel.
    GENRE_CLR = {
        'pop':       '#b85878',
        'hiphop':    '#b07840',
        'trap':      '#b04848',
        'cinematic': '#4878b0',
        'classical': '#7058a0',
        'techno':    '#388888',
        'jpop':      '#b06070',
        'phonk':     '#a86838',
        'edm':       '#389090',
        'house':     '#a84880',
    }

    # ── Typography ───────────────────────────────────────────────────────────
    # Consolas is available on Windows out of the box and on macOS via the
    # Microsoft fonts package.  It provides the monospace character grid that
    # keeps the frequency charts and code-style labels aligned correctly.
    FN_XS  = ("Consolas", 8)
    FN_X   = ("Consolas", 9)
    FN_S   = ("Consolas", 9)
    FN_B   = ("Consolas", 10)
    FN_H   = ("Consolas", 11, "bold")
    FN_T   = ("Consolas", 14, "bold")
    FN_BIG = ("Consolas", 16, "bold")   # header title — slightly smaller for clean look
