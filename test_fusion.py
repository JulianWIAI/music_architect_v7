"""
Quick test script for Cross-Genre Fusion
Run this from your project folder: python test_fusion.py
"""

from composition_engine import CompositionEngine, CompositionConfig
from genre_fusion import FusionConfig, FUSION_PRESETS

# Initialize engine
print("Loading engine...")
engine = CompositionEngine("seeds")
engine.load_seeds()

print("\n" + "="*50)
print("  FUSION TEST")
print("="*50)

# Test 1: Preset fusion - Cyber Ninja (trap + techno)
print("\n🥷 Testing CYBER_NINJA preset (trap + techno)...")
config = CompositionConfig()
config.fusion = FusionConfig.from_preset('cyber_ninja')
config.complexity = 7

composition = engine.compose(config)
output_path = engine.export_midi(composition, "fusion_cyber_ninja.mid")
print(f"   ✓ Exported: {output_path}")
print(f"   BPM: {composition['config']['bpm']}")
print(f"   Key: {composition['config']['key']}")

# Test 2: Custom fusion - jpop + cinematic
print("\n🎌 Testing CUSTOM fusion (70% jpop + 30% cinematic)...")
config2 = CompositionConfig()
config2.fusion = FusionConfig.custom('jpop', 'cinematic', 0.7)
config2.complexity = 6

composition2 = engine.compose(config2)
output_path2 = engine.export_midi(composition2, "fusion_jpop_cinematic.mid")
print(f"   ✓ Exported: {output_path2}")
print(f"   BPM: {composition2['config']['bpm']}")
print(f"   Key: {composition2['config']['key']}")

# Test 3: Final Boss preset
print("\n👾 Testing FINAL_BOSS preset (cinematic + trap)...")
config3 = CompositionConfig()
config3.fusion = FusionConfig.from_preset('final_boss')
config3.complexity = 8

composition3 = engine.compose(config3)
output_path3 = engine.export_midi(composition3, "fusion_final_boss.mid")
print(f"   ✓ Exported: {output_path3}")
print(f"   BPM: {composition3['config']['bpm']}")
print(f"   Key: {composition3['config']['key']}")

print("\n" + "="*50)
print("  ALL FUSION TESTS COMPLETE!")
print("="*50)
print("\nGenerated files:")
print("  - fusion_cyber_ninja.mid")
print("  - fusion_jpop_cinematic.mid")
print("  - fusion_final_boss.mid")
print("\nOpen these in your DAW to hear the fusion results!")
