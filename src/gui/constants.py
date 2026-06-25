GM_INSTRUMENTS = {
    0: "Acoustic Grand Piano", 1: "Bright Acoustic Piano", 2: "Electric Grand Piano",
    3: "Honky-tonk Piano", 4: "Electric Piano 1", 5: "Electric Piano 2",
    6: "Harpsichord", 7: "Clavinet", 8: "Celesta", 9: "Glockenspiel",
    10: "Music Box", 11: "Vibraphone", 12: "Marimba", 13: "Xylophone",
    14: "Tubular Bells", 15: "Dulcimer", 16: "Drawbar Organ", 17: "Percussive Organ",
    18: "Rock Organ", 19: "Church Organ", 20: "Reed Organ", 21: "Accordion",
    22: "Harmonica", 23: "Tango Accordion", 24: "Nylon Guitar", 25: "Steel Guitar",
    26: "Jazz Electric Guitar", 27: "Clean Electric Guitar", 28: "Muted Guitar",
    29: "Overdriven Guitar", 30: "Distortion Guitar", 31: "Guitar Harmonics",
    32: "Acoustic Bass", 33: "Finger Electric Bass", 34: "Pick Electric Bass",
    35: "Fretless Bass", 36: "Slap Bass 1", 37: "Slap Bass 2",
    38: "Synth Bass 1", 39: "Synth Bass 2", 40: "Violin", 41: "Viola",
    42: "Cello", 43: "Contrabass", 44: "Tremolo Strings", 45: "Pizzicato Strings",
    46: "Orchestral Harp", 47: "Timpani", 48: "String Ensemble 1",
    49: "String Ensemble 2", 50: "Synth Strings 1", 51: "Synth Strings 2",
    52: "Choir Aahs", 53: "Voice Oohs", 54: "Synth Voice", 55: "Orchestra Hit",
    56: "Trumpet", 57: "Trombone", 58: "Tuba", 59: "Muted Trumpet",
    60: "French Horn", 61: "Brass Section", 62: "Synth Brass 1", 63: "Synth Brass 2",
    64: "Soprano Sax", 65: "Alto Sax", 66: "Tenor Sax", 67: "Baritone Sax",
    68: "Oboe", 69: "English Horn", 70: "Bassoon", 71: "Clarinet",
    72: "Piccolo", 73: "Flute", 74: "Recorder", 75: "Pan Flute",
    76: "Blown Bottle", 77: "Shakuhachi", 78: "Whistle", 79: "Ocarina",
    80: "Square Lead", 81: "Sawtooth Lead", 82: "Calliope Lead", 83: "Chiff Lead",
    84: "Charang Lead", 85: "Voice Lead", 86: "Fifths Lead", 87: "Bass + Lead",
    88: "New Age Pad", 89: "Warm Pad", 90: "Polysynth Pad", 91: "Choir Pad",
    92: "Bowed Pad", 93: "Metallic Pad", 94: "Halo Pad", 95: "Sweep Pad",
    96: "Rain (FX)", 97: "Soundtrack (FX)", 98: "Crystal (FX)", 99: "Atmosphere (FX)",
    100: "Brightness (FX)", 101: "Goblins (FX)", 102: "Echoes (FX)", 103: "Sci-Fi (FX)",
    104: "Sitar", 105: "Banjo", 106: "Shamisen", 107: "Koto",
    108: "Kalimba", 109: "Bag Pipe", 110: "Fiddle", 111: "Shanai",
    112: "Tinkle Bell", 113: "Agogo", 114: "Steel Drums", 115: "Woodblock",
    116: "Taiko Drum", 117: "Melodic Tom", 118: "Synth Drum", 119: "Reverse Cymbal",
    120: "Guitar Fret Noise", 121: "Breath Noise", 122: "Seashore", 123: "Bird Tweet",
    124: "Telephone Ring", 125: "Helicopter", 126: "Applause", 127: "Gunshot",
}

DRUM_KITS = {
    0: "Standard Kit", 8: "Room Kit", 16: "Power Kit",
    24: "Electronic Kit", 25: "TR-808 Kit", 32: "Jazz Kit",
    40: "Brush Kit", 48: "Orchestra Kit", 56: "SFX Kit",
}

ROLE_INSTRUMENTS = {
    'bass': [32, 33, 34, 35, 36, 37, 38, 39, 43, 87],
    'chords': [0, 1, 2, 4, 5, 6, 16, 17, 18, 24, 25, 26, 27, 48, 49, 50, 52, 61, 62, 89],
    'lead': [40, 56, 64, 65, 66, 68, 71, 73, 80, 81, 82, 83, 84, 85, 86],
    'pad': [48, 49, 50, 51, 52, 53, 54, 88, 89, 90, 91, 92, 93, 94, 95, 97, 99],
    'arp': [8, 9, 10, 11, 12, 46, 80, 81, 98, 100, 104, 108, 114],
}

NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
QUALITIES = ['maj7', 'min7', '7', 'major', 'minor', 'sus4', 'sus2', 'dim7', 'aug']
