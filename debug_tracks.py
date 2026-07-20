import mido
from pathlib import Path

paths = [
    ("Current Gen3/pop",    Path("Generation3/pop")),
    ("Backup Gen1/pop",     Path("generation Backup/Generation4/batch_output/pop")),
    ("Backup vault/gen3",   Path("generation Backup/Generation4/vault/batch_gen3")),
]

for label, base in paths:
    if not base.exists():
        print(f"\n[SKIP] {label} not found")
        continue
    # find first midi
    mid_file = next(base.rglob("*.mid"), None)
    if not mid_file:
        print(f"\n[SKIP] No midi in {label}")
        continue
    mid = mido.MidiFile(str(mid_file))
    print(f"\n=== {label}  |  type={mid.type}  tpb={mid.ticks_per_beat}  ===")
    print(f"    file: {mid_file}")
    for i, t in enumerate(mid.tracks):
        name   = next((m.name for m in t if m.type == "track_name"), "(no name)")
        notes  = [m for m in t if m.type == "note_on" and m.velocity > 0]
        chs    = set(getattr(m, "channel", None) for m in notes)
        chs.discard(None)
        pits   = [m.note for m in notes]
        prange = f"{min(pits)}-{max(pits)}" if pits else "n/a"
        print(f"  [{i}] \"{name}\"  notes={len(notes)}  ch={sorted(chs)}  pitch={prange}")
