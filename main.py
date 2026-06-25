"""
Music Architect — entry point.

Run this file to launch the application:
    python main.py
"""

import subprocess
import sys
import os


def _check_dependencies():
    """Install required packages if they are missing."""
    required = [('midiutil', 'MIDIUtil'), ('mido', 'mido')]
    for module_name, pip_name in required:
        try:
            __import__(module_name)
            print(f'  {module_name} OK')
        except ImportError:
            print(f'  Installing {pip_name}...')
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', pip_name, '-q'])

    try:
        __import__('pygame')
        print('  pygame OK (audio preview enabled)')
    except ImportError:
        print('  pygame not installed (optional — pip install pygame)')


def main():
    print('Music Architect — checking dependencies...')
    _check_dependencies()

    print('Launching...')
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    try:
        from src.gui.app import main as gui_main
        gui_main()
    except ImportError:
        print('GUI not found. Run the MIDI generator directly:')
        print('  python -m music_architect_v5.main --genre trap --seed 42 --bars 32 --output out.mid')


if __name__ == '__main__':
    main()
