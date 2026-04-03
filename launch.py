"""
◢ SEED COMPOSER — LAUNCHER ◣
Run this to start the GUI.
"""
import subprocess, sys, os

def check():
    for pkg in ['midiutil', 'MIDIUtil']:
        try:
            __import__('midiutil'); print("  ✓ midiutil"); return
        except ImportError: pass
    print("  Installing midiutil...")
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'MIDIUtil', '-q'])
    
    try:
        __import__('pygame'); print("  ✓ pygame (audio preview)")
    except ImportError:
        print("  ○ pygame not installed (optional — for audio preview)")
        print("    pip install pygame")

if __name__ == "__main__":
    print("◢ SEED COMPOSER — CHECKING DEPS ◣")
    check()
    print("◢ LAUNCHING ◣")
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    from gui_composer import main
    main()
