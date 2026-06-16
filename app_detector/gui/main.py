"""GUI entry point."""

from __future__ import annotations


def run_gui() -> None:
    from app_detector.gui.app import AppDetectorGUI
    AppDetectorGUI().mainloop()


if __name__ == "__main__":
    run_gui()
