"""Tests for the Linux scanner (mocked subprocess calls)."""

from unittest.mock import patch, MagicMock

from app_detector.platforms.linux import (
    _scan_dpkg,
    _scan_snap,
    _scan_flatpak,
    _scan_pacman,
    LinuxDetector,
)


FAKE_DPKG_OUTPUT = (
    "firefox\t128.0.3-0ubuntu1\tMozilla Firefox web browser\n"
    "vim\t2:9.1.0-1ubuntu1\tVi IMproved - enhanced vi editor\n"
    "curl\t8.5.0-2ubuntu1\tcommand line tool for transferring data\n"
)

FAKE_SNAP_OUTPUT = (
    "Name               Version          Rev    Tracking       Publisher\n"
    "core22             20240301         1380   latest/stable  canonical✓\n"
    "firefox            128.0            4336   latest/stable  mozilla✓\n"
    "code               1.96.0           178    latest/stable  vscode✓\n"
)

FAKE_FLATPAK_OUTPUT = (
    "org.gimp.GIMP\t2.10.36\tGIMP\n"
    "org.videolan.VLC\t3.0.20\tVLC\n"
)

FAKE_PACMAN_OUTPUT = (
    "linux 6.8.9.arch1-1\n"
    "vim 9.1.0-1\n"
)


def _mock_run(output: str):
    """Create a mock subprocess.run that returns *output*."""
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = output
    return mock


def test_scan_dpkg():
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run(FAKE_DPKG_OUTPUT)):
        apps = _scan_dpkg()
    assert len(apps) == 3
    assert apps[0].name == "firefox"
    assert apps[0].source == "apt"
    assert apps[0].version == "128.0.3-0ubuntu1"
    assert apps[2].metadata["description"] == "command line tool for transferring data"


def test_scan_snap():
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run(FAKE_SNAP_OUTPUT)):
        apps = _scan_snap()
    assert len(apps) == 3
    assert apps[1].name == "firefox"
    assert apps[1].source == "snap"


def test_scan_flatpak():
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run(FAKE_FLATPAK_OUTPUT)):
        apps = _scan_flatpak()
    assert len(apps) == 2
    assert apps[0].package_id == "org.gimp.GIMP"
    assert apps[0].source == "flatpak"


def test_scan_pacman():
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run(FAKE_PACMAN_OUTPUT)):
        apps = _scan_pacman()
    assert len(apps) == 2
    assert apps[0].name == "linux"
    assert apps[0].version == "6.8.9.arch1-1"
    assert apps[0].source == "pacman"
