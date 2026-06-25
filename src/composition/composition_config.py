from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple


@dataclass
class CompositionConfig:
    genre: str = 'pop'
    bpm: Optional[float] = None
    starting_chord: Optional[str] = None
    key: Optional[str] = None
    complexity: int = 5
    duration_bars: int = 0
    fusion: Optional[Any] = None
    mutation: float = 0.0

    tracks: Dict[str, dict] = field(default_factory=lambda: {
        'drums': {'enabled': True, 'volume': 0.85, 'instrument': None},
        'bass': {'enabled': True, 'volume': 0.8, 'instrument': None},
        'chords': {'enabled': True, 'volume': 0.7, 'instrument': None},
        'lead': {'enabled': True, 'volume': 0.75, 'instrument': None},
        'pad': {'enabled': True, 'volume': 0.6, 'instrument': None},
        'arp': {'enabled': False, 'volume': 0.5, 'instrument': None},
    })

    humanize_amount: float = 0.6
    swing: float = 0.0
    seed_value: Optional[int] = None
    structure_override: Optional[List[Tuple[str, int]]] = None
    tension_multiplier: float = 0.0
