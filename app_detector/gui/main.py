import sys
from app_detector.gui.app import AppDetectorGUI

def run_gui():
    """Entry point for the GUI application."""
    app = AppDetectorGUI()
    app.mainloop()

if __name__ == "__main__":
    run_gui()
