"""
Heuristic genre classifier.

Scores a song across eight genre categories by combining BPM, instrumentation
densities, syncopation, harmonic complexity, time signature, and duration.
"""


def classify_genre(time_data: dict, stats: dict) -> str:
    """
    Return the most likely genre label for a song given its time-data and stats.

    Parameters
    ----------
    time_data : dict  — output of csv_parser.parse_time_data_csv
    stats     : dict  — output of csv_parser.compute_timeline_stats
    """
    bpm = time_data.get('bpm', 120)
    time_sig = time_data.get('time_signature', '4/4')
    syncopation = time_data.get('syncopation_score', 0.5)
    duration = time_data.get('duration', 180)

    kick_d = stats.get('kick_density', 0)
    hihat_d = stats.get('hihat_density', 0)
    bass_d = stats.get('bass_density', 0)
    synth_d = stats.get('synth_density', 0)
    pad_d = stats.get('pad_density', 0)
    harm = stats.get('harmonic_ratio_avg', 0.5)
    chord_v = stats.get('chord_variety', 5)

    sc = {k: 0 for k in ['pop', 'hiphop', 'trap', 'cinematic', 'classical', 'techno', 'jpop', 'phonk']}

    # BPM scoring
    if 60 <= bpm <= 90:
        sc['hiphop'] += 3; sc['cinematic'] += 2
    elif 90 < bpm <= 115:
        sc['pop'] += 2; sc['hiphop'] += 2; sc['jpop'] += 1
    elif 115 < bpm <= 135:
        sc['pop'] += 3; sc['jpop'] += 2
    elif 135 < bpm <= 155:
        sc['trap'] += 3; sc['phonk'] += 3; sc['techno'] += 2
    elif bpm > 155:
        sc['techno'] += 4; sc['phonk'] += 2

    # Instrumentation scoring
    if pad_d > 0.15:
        sc['cinematic'] += 3; sc['classical'] += 2
    if synth_d > 0.1:
        sc['techno'] += 2; sc['jpop'] += 1
    if hihat_d > 0.05:
        sc['trap'] += 3; sc['phonk'] += 2
    if kick_d > 0.08:
        sc['techno'] += 2
    if bass_d > 0.2:
        sc['hiphop'] += 2; sc['trap'] += 1

    # Feel scoring
    if syncopation > 0.7:
        sc['hiphop'] += 2
    if syncopation < 0.3:
        sc['classical'] += 2; sc['cinematic'] += 1

    # Harmony scoring
    if harm > 0.8:
        sc['classical'] += 2; sc['cinematic'] += 2
    elif harm < 0.5:
        sc['trap'] += 2; sc['phonk'] += 2

    # Time signature
    if time_sig in ('3/4', '6/8'):
        sc['classical'] += 3; sc['cinematic'] += 2

    # Chord variety
    if chord_v > 8:
        sc['jpop'] += 2; sc['classical'] += 1
    elif chord_v < 4:
        sc['trap'] += 2; sc['phonk'] += 2; sc['techno'] += 1

    # Duration
    if duration > 300:
        sc['cinematic'] += 2; sc['classical'] += 2

    return max(sc, key=sc.get)
