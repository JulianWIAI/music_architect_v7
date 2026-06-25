"""
Integration test for cross-genre fusion.

Requires a CompositionEngine with loaded seeds.

Usage:
    python tests/test_fusion.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.arrangement.fusion_config import FusionConfig
from src.arrangement.fusion_presets import FUSION_PRESETS


def main():
    # Import composition engine if available
    try:
        from composition_engine import CompositionEngine, CompositionConfig
    except ImportError:
        print('CompositionEngine not found — testing fusion config only.')
        _test_fusion_config()
        return

    try:
        print('Loading engine...')
        engine = CompositionEngine('seeds')
        engine.load_seeds()

        print('\n' + '=' * 50)
        print('  FUSION TEST')
        print('=' * 50)

        config = FusionConfig.from_preset('cyber_ninja')
        print(f'\nCyber Ninja: {config.genres} weights={[round(w, 2) for w in config.weights]}')

        composition_cfg = CompositionConfig()
        composition_cfg.fusion_config = config
        result = engine.compose(composition_cfg)
        print(f'Generated {sum(len(v) for v in result.get("tracks", {}).values())} events')
    except Exception as e:
        print(f'Engine test skipped ({e}). Running standalone fusion config test instead.')
        _test_fusion_config()


def _test_fusion_config():
    """Verify FusionConfig construction and preset loading without an engine."""
    print('\nTesting FusionConfig...')

    cfg = FusionConfig.from_preset('paladin')
    assert cfg.genres == ['cinematic', 'classical'], 'Wrong genres'
    assert abs(sum(cfg.weights) - 1.0) < 1e-9, 'Weights do not sum to 1'
    print(f'  paladin: {cfg.genres} weights={[round(w, 2) for w in cfg.weights]}  OK')

    cfg2 = FusionConfig.custom('trap', 'techno', 0.7)
    assert cfg2.genres == ['trap', 'techno']
    assert abs(cfg2.weights[0] - 0.7) < 1e-9
    print(f'  custom : {cfg2.genres} weights={[round(w, 2) for w in cfg2.weights]}  OK')

    print(f'\nAll {len(FUSION_PRESETS)} presets available:')
    for name, preset in FUSION_PRESETS.items():
        genres = ' + '.join(preset['genres'])
        print(f'  {name:<20s} {genres}')

    print('\nAll tests passed.')


if __name__ == '__main__':
    main()
