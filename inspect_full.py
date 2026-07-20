"""
inspect_full.py — Deep MIDI analysis using channel-based track identification.

Channel map (consistent across all versions):
  ch 9        = drums (GM standard)
  ch 0        = bass
  ch 1        = melody
  ch 2        = pad / chords 2
  ch 3        = chords (dense)
  ch 4        = arp / lead
  ch 5        = lead 2 / pad 2
  ch 6        = omni layer
  ch 7        = FX

Reports per batch-run per genre:
  Drums   : unique kick patterns, snare locked %, kick density
  Melody  : pitch range, unique pitch classes, note count
  Chords  : note density, low-register %
  Bass    : pitch range, avg pitch
  Arp     : note count, presence %
"""
import mido
import statistics
from pathlib import Path
from collections import Counter

DRUM_CH   = 9
CH_BASS   = 0   # 03_Bass
CH_MELODY = 1   # 04_Melody
CH_CHORDS = 2   # 05_Chords
CH_ARP    = 4   # 07_Arp

KICK_NOTES  = {35, 36}
SNARE_NOTES = {38, 40}
HIHAT_NOTES = {42, 44, 46}


def parse_midi(path):
    try:
        mid = mido.MidiFile(str(path))
        tpb  = mid.ticks_per_beat
        step = tpb // 4   # 16th note

        drums   = {"kick": [], "snare": [], "hihat": []}
        pitched = {ch: [] for ch in (CH_BASS, CH_MELODY, CH_CHORDS, CH_ARP, 3)}

        for track in mid.tracks:
            abs_tick = 0
            for msg in track:
                abs_tick += msg.time
                if msg.type != "note_on" or msg.velocity == 0:
                    continue
                ch = getattr(msg, "channel", None)
                if ch is None:
                    continue
                if ch == DRUM_CH:
                    si = (abs_tick // step) % 16
                    if msg.note in KICK_NOTES:   drums["kick"].append(si)
                    elif msg.note in SNARE_NOTES: drums["snare"].append(si)
                    elif msg.note in HIHAT_NOTES: drums["hihat"].append(si)
                elif ch in pitched:
                    pitched[ch].append(msg.note)

        return step, drums, pitched
    except Exception:
        return None, None, None


def drum_fingerprint(drums):
    return (frozenset(drums["kick"]), frozenset(drums["snare"]))


def snare_locked(drums):
    s = set(drums["snare"])
    return s in ({4, 12}, {4, 8, 12}, {4, 12, 0})


def kick_density(drums):
    return len(set(drums["kick"]))


def pitched_stats(notes, label=""):
    if not notes:
        return {"count": 0, "range": 0, "unique_pcs": 0, "avg_pitch": 0}
    pcs = set(p % 12 for p in notes)
    return {
        "count":      len(notes),
        "range":      max(notes) - min(notes),
        "unique_pcs": len(pcs),
        "avg_pitch":  round(statistics.mean(notes), 1),
        "min":        min(notes),
        "max":        max(notes),
    }


def low_register_pct(notes, threshold=48):
    if not notes:
        return 0.0
    return round(sum(1 for p in notes if p < threshold) / len(notes) * 100, 1)


def analyse_batch(batch_path, label, sample=20):
    base = Path(batch_path)
    if not base.exists():
        print(f"\n[SKIP] {label} — path not found: {base}")
        return None

    genres = sorted(p for p in base.iterdir() if p.is_dir())
    if not genres:
        print(f"\n[SKIP] {label} — no genre subdirs")
        return None

    print(f"\n{'='*74}")
    print(f"  {label}")
    print(f"{'='*74}")

    agg = {
        "drum_unique": 0, "drum_total": 0, "snare_lock": 0,
        "kick_dens": [], "mel_range": [], "mel_pcs": [],
        "bass_range": [], "bass_avg": [], "arp_count": [],
        "chord_low": [],
    }

    for genre_dir in genres:
        genre = genre_dir.name
        track_dirs = sorted(p for p in genre_dir.iterdir() if p.is_dir())[:sample]

        fps, snare_locks = [], 0
        kick_dens, mel_ranges, mel_pcs = [], [], []
        bass_ranges, bass_avgs, arp_counts, chord_lows = [], [], [], []

        for td in track_dirs:
            mids = list(td.glob("*.mid"))
            if not mids:
                continue
            step, drums, pitched = parse_midi(mids[0])
            if drums is None:
                continue

            fps.append(drum_fingerprint(drums))
            if snare_locked(drums): snare_locks += 1
            kick_dens.append(kick_density(drums))

            mel  = pitched_stats(pitched.get(CH_MELODY, []))
            bass = pitched_stats(pitched.get(CH_BASS, []))
            chd  = pitched.get(CH_CHORDS, [])
            arp  = pitched.get(CH_ARP, [])

            if mel["count"] > 0:
                mel_ranges.append(mel["range"])
                mel_pcs.append(mel["unique_pcs"])
            if bass["count"] > 0:
                bass_ranges.append(bass["range"])
                bass_avgs.append(bass["avg_pitch"])
            chord_lows.append(low_register_pct(chd))
            arp_counts.append(len(arp))

        n      = len(fps)
        uniq   = len(set(fps))
        slk    = round(snare_locks / max(n, 1) * 100)
        avg_kd = round(statistics.mean(kick_dens), 1) if kick_dens else 0
        avg_mr = round(statistics.mean(mel_ranges), 1) if mel_ranges else 0
        avg_mp = round(statistics.mean(mel_pcs), 1) if mel_pcs else 0
        avg_br = round(statistics.mean(bass_ranges), 1) if bass_ranges else 0
        avg_ba = round(statistics.mean(bass_avgs), 1) if bass_avgs else 0
        avg_ar = round(statistics.mean(arp_counts), 0) if arp_counts else 0
        avg_cl = round(statistics.mean(chord_lows), 1) if chord_lows else 0

        # Snare pattern breakdown
        snare_ctr = Counter(tuple(sorted(set(drums["snare"]))) for _, drums, _ in
                            [(None, {"kick": [], "snare": [], "hihat": []}, None)])
        # Simple: count from fps list isn't available here, just print the snare lock %

        print(f"\n  [{genre.upper()}]")
        print(f"    Drums  : {uniq}/{n} unique kick patterns  |  snare-2&4-locked: {slk}%  |  avg kick density: {avg_kd}/16")
        print(f"    Melody : range {avg_mr} semitones  |  avg {avg_mp} unique pitch classes  |  (ch1)")
        print(f"    Bass   : range {avg_br} st  |  avg pitch {avg_ba} (ch0)")
        print(f"    Chords : low-register (< C3): {avg_cl}%  (ch3)")
        print(f"    Arp    : avg {int(avg_ar)} notes/track  (ch4)")

        agg["drum_unique"] += uniq
        agg["drum_total"]  += n
        agg["snare_lock"]  += snare_locks
        agg["kick_dens"].extend(kick_dens)
        agg["mel_range"].extend(mel_ranges)
        agg["mel_pcs"].extend(mel_pcs)
        agg["bass_range"].extend(bass_ranges)
        agg["bass_avg"].extend(bass_avgs)
        agg["arp_count"].extend(arp_counts)
        agg["chord_low"].extend(chord_lows)

    print(f"\n  {'-'*60}")
    print(f"  TOTALS — {label}")
    pct = round(agg["drum_unique"] / max(agg["drum_total"], 1) * 100)
    slk = round(agg["snare_lock"] / max(agg["drum_total"], 1) * 100)
    print(f"    Drum uniqueness  : {agg['drum_unique']}/{agg['drum_total']} ({pct}%)")
    print(f"    Snare 2&4 locked : {slk}% of tracks")
    print(f"    Avg kick density : {round(statistics.mean(agg['kick_dens']),1)}/16" if agg['kick_dens'] else "    Avg kick density : n/a")
    print(f"    Avg melody range : {round(statistics.mean(agg['mel_range']),1)} semitones" if agg['mel_range'] else "    Avg melody range : n/a")
    print(f"    Avg unique PCs   : {round(statistics.mean(agg['mel_pcs']),1)}/12" if agg['mel_pcs'] else "    Avg unique PCs   : n/a")
    print(f"    Avg bass range   : {round(statistics.mean(agg['bass_range']),1)} semitones" if agg['bass_range'] else "    Avg bass range   : n/a")
    print(f"    Avg chord low %  : {round(statistics.mean(agg['chord_low']),1)}%" if agg['chord_low'] else "    Avg chord low %  : n/a")
    print(f"    Avg arp notes    : {round(statistics.mean(agg['arp_count']),0)}" if agg['arp_count'] else "    Avg arp notes    : n/a")
    return agg


# ── Run ──────────────────────────────────────────────────────────────────────

BACKUP  = r"c:\Users\julia\PycharmProjects\MUSIC_ARCHITECT_V7\generation Backup\Generation4"
CURRENT = r"c:\Users\julia\PycharmProjects\MUSIC_ARCHITECT_V7"

batches = [
    (f"{BACKUP}\\batch_output",        "BACKUP  v4-Gen1  (batch_output)"),
    (f"{BACKUP}\\batch_gen2",          "BACKUP  v4-Gen2  (batch_gen2)"),
    (f"{BACKUP}\\vault\\batch_gen3",   "BACKUP  v4-Gen3  (vault/batch_gen3)"),
    (f"{CURRENT}\\Generation3",        "CURRENT v7-Gen3  (no vocal mask)"),
    (f"{CURRENT}\\vocals_generation_3","CURRENT v7-Gen3  (vocal mask ON)"),
]

all_agg = []
for path, label in batches:
    agg = analyse_batch(path, label, sample=20)
    if agg:
        all_agg.append((label, agg))

# ── Cross-run summary ─────────────────────────────────────────────────────────
print(f"\n\n{'='*74}")
print("  CROSS-RUN SUMMARY")
print(f"{'='*74}")
print(f"  {'Run':<40} {'Drum%':>6}  {'Snare%':>7}  {'KickD':>6}  {'MelR':>5}  {'PCs':>4}  {'BassR':>6}  {'Arp':>5}")
print(f"  {'-'*72}")
for label, a in all_agg:
    short = label[:40]
    pct   = round(a['drum_unique'] / max(a['drum_total'], 1) * 100)
    slk   = round(a['snare_lock']  / max(a['drum_total'], 1) * 100)
    kd    = round(statistics.mean(a['kick_dens']), 1)    if a['kick_dens']  else 0
    mr    = round(statistics.mean(a['mel_range']), 1)    if a['mel_range']  else 0
    mp    = round(statistics.mean(a['mel_pcs']), 1)      if a['mel_pcs']    else 0
    br    = round(statistics.mean(a['bass_range']), 1)   if a['bass_range'] else 0
    ar    = round(statistics.mean(a['arp_count']), 0)    if a['arp_count']  else 0
    print(f"  {short:<40} {pct:>5}%  {slk:>6}%  {kd:>6}  {mr:>5}  {mp:>4}  {br:>6}  {ar:>5}")
