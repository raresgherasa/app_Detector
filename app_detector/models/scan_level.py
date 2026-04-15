"""
Scan Levels
"""

from enum import Enum, auto

class ScanLevel(Enum):
    ESSENTIAL = auto()      # Level 1: Desktop GUI apps only
    DEVELOPMENT = auto()    # Level 2: Desktop apps + dev tools (git, python, etc)
    COMPREHENSIVE = auto()  # Level 3: All packages (including libs, dependencies)
