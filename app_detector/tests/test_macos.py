"""Tests for the macOS scanner (mocked subprocess calls)."""

import json
from unittest.mock import patch, MagicMock

from app_detector.platforms.macos import _scan_system_profiler, _scan_brew_formulae, _scan_brew_casks


FAKE_SP_JSON = json.dumps({
    "SPApplicationsDataType": [
        {"_name": "Safari", "version": "18.2", "path": "/Applications/Safari.app"},
        {"_name": "Xcode", "version": "16.0", "path": "/Applications/Xcode.app"},
    ]
})

FAKE_BREW_FORMULA = "python@3.12 3.12.8\nnode 22.0.0\nwget 1.24.5\n"
FAKE_BREW_CASK = "firefox 128.0\nvisual-studio-code 1.96.0\n"


def _mock_run(output: str):
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = output
    return mock


def test_scan_system_profiler():
    with patch("app_detector.platforms.macos.subprocess.run", return_value=_mock_run(FAKE_SP_JSON)):
        apps = _scan_system_profiler()
    assert len(apps) == 2
    assert apps[0].name == "Safari"
    assert apps[0].source == "system"


def test_scan_brew_formulae():
    with patch("app_detector.platforms.macos.subprocess.run", return_value=_mock_run(FAKE_BREW_FORMULA)):
        apps = _scan_brew_formulae()
    assert len(apps) == 3
    assert apps[0].name == "python@3.12"
    assert apps[0].source == "brew"


def test_scan_brew_casks():
    with patch("app_detector.platforms.macos.subprocess.run", return_value=_mock_run(FAKE_BREW_CASK)):
        apps = _scan_brew_casks()
    assert len(apps) == 2
    assert apps[0].name == "firefox"
    assert apps[0].source == "brew-cask"
