"""
FusionConfig — configuration dataclass for a cross-genre fusion session.

Stores the genre list and blend weights. Weights are automatically normalised
to sum to 1.0 on construction.
"""

from dataclasses import dataclass, field
from typing import List

from src.arrangement.fusion_presets import FUSION_PRESETS


@dataclass
class FusionConfig:
    """Defines which genres to blend and how much weight each receives."""

    genres: List[str]
    weights: List[float]
    blend_mode: str = 'weighted'

    def __post_init__(self):
        total = sum(self.weights)
        if total > 0:
            self.weights = [w / total for w in self.weights]

    @classmethod
    def from_preset(cls, preset_name: str) -> 'FusionConfig':
        """Create a FusionConfig from a named preset."""
        if preset_name not in FUSION_PRESETS:
            raise ValueError(f'Unknown preset: {preset_name}')
        preset = FUSION_PRESETS[preset_name]
        return cls(genres=preset['genres'], weights=preset['weights'])

    @classmethod
    def custom(cls, genre1: str, genre2: str, ratio: float = 0.5) -> 'FusionConfig':
        """Create a two-genre custom fusion with a given blend ratio."""
        return cls(genres=[genre1, genre2], weights=[ratio, 1.0 - ratio])
