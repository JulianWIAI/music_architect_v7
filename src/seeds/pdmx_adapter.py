import json
import csv
from pathlib import Path


def pdmx_mapper(pdmx_json_path, output_root):
    with open(pdmx_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    song_id = Path(pdmx_json_path).stem
    song_dir = Path(output_root) / song_id
    song_dir.mkdir(parents=True, exist_ok=True)

    bpm = data.get('tempos', [{'qpm': 120}])[0].get('qpm', 120)
    metadata_key = "C major"

    with open(song_dir / f"{song_id}_time_data.csv", 'w', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['parameter', 'value'])
        writer.writerow(['bpm', round(bpm, 2)])
        writer.writerow(['key', metadata_key])
        writer.writerow(['duration', data.get('total_time', 120)])

    timeline = []
    for track in data.get('tracks', []):
        is_drums = track.get('is_drum', False)
        for note in track.get('notes', []):
            time = round(note['start_time'], 3)
            pitch = note['pitch']
            velocity = note['velocity']
            row = [time, 0, 0, 0, 0, 0, 0]
            if is_drums:
                if pitch in [35, 36]:
                    row[1] = velocity
                elif pitch in [38, 40]:
                    row[2] = velocity
                elif pitch in [42, 44, 46]:
                    row[3] = velocity
            else:
                if pitch < 40:
                    row[4] = velocity
                elif 40 <= pitch < 72:
                    row[5] = velocity
                else:
                    row[6] = velocity
            timeline.append(row)

    timeline.sort(key=lambda x: x[0])

    with open(song_dir / f"{song_id}_timeline.csv", 'w', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['time_seconds', 'kick', 'snare', 'hihat', 'bass', 'synth', 'pad'])
        writer.writerows(timeline)

    with open(song_dir / f"{song_id}_chords.csv", 'w', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['start_time', 'end_time', 'chord', 'root', 'quality'])
        writer.writerow([0, data.get('total_time', 120), 'C', 'C', 'major'])

    print(f"Converted {song_id}")
