import sys
import os

def launch_tui_session():
    """Launches the Vartalap Textual TUI session directly."""
    os.execvp(sys.executable, [sys.executable, "-m", "vartalap.tui"])

if __name__ == "__main__":
    launch_tui_session()
