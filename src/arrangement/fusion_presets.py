"""
Named genre-fusion presets, each combining two genres with a weighted blend ratio.

Presets are named after character archetypes to convey their musical personality.
"""

FUSION_PRESETS = {
    'cyber_ninja': {
        'genres': ['trap', 'techno'],
        'weights': [0.6, 0.4],
        'description': 'Fast, aggressive beats with electronic edge',
        'bpm_range': (140, 160),
    },
    'paladin': {
        'genres': ['cinematic', 'classical'],
        'weights': [0.5, 0.5],
        'description': 'Epic orchestral power and majesty',
        'bpm_range': (80, 110),
    },
    'anime_boss': {
        'genres': ['jpop', 'cinematic'],
        'weights': [0.7, 0.3],
        'description': 'J-Pop energy with epic orchestral moments',
        'bpm_range': (130, 150),
    },
    'lofi_samurai': {
        'genres': ['hiphop', 'jpop'],
        'weights': [0.65, 0.35],
        'description': 'Chill beats with Japanese melodic influence',
        'bpm_range': (75, 95),
    },
    'dark_mage': {
        'genres': ['phonk', 'cinematic'],
        'weights': [0.55, 0.45],
        'description': 'Dark, aggressive atmosphere with orchestral depth',
        'bpm_range': (130, 145),
    },
    'street_fighter': {
        'genres': ['trap', 'jpop'],
        'weights': [0.5, 0.5],
        'description': 'Hard-hitting beats with anime flair',
        'bpm_range': (140, 155),
    },
    'space_pirate': {
        'genres': ['techno', 'cinematic'],
        'weights': [0.6, 0.4],
        'description': 'Futuristic electronic with epic scope',
        'bpm_range': (125, 145),
    },
    'shadow_assassin': {
        'genres': ['phonk', 'trap'],
        'weights': [0.5, 0.5],
        'description': 'Dark, aggressive, maximum intensity',
        'bpm_range': (135, 160),
    },
    'healing_bard': {
        'genres': ['pop', 'classical'],
        'weights': [0.6, 0.4],
        'description': 'Uplifting melodies with orchestral warmth',
        'bpm_range': (100, 125),
    },
    'mech_pilot': {
        'genres': ['techno', 'jpop'],
        'weights': [0.55, 0.45],
        'description': 'High-energy electronic anime vibes',
        'bpm_range': (135, 155),
    },
    'drift_king': {
        'genres': ['phonk', 'hiphop'],
        'weights': [0.6, 0.4],
        'description': 'Aggressive cowbell-driven street racing energy',
        'bpm_range': (130, 150),
    },
    'final_boss': {
        'genres': ['cinematic', 'trap'],
        'weights': [0.5, 0.5],
        'description': 'Epic orchestral meets hard-hitting production',
        'bpm_range': (100, 140),
    },
}
