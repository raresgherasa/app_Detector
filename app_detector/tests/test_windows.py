"""Tests for the Windows scanner (mocked subprocess calls)."""

from unittest.mock import patch, MagicMock

from app_detector.platforms.windows import _scan_registry, _scan_choco


FAKE_REGISTRY_OUTPUT = (
    "Google Chrome\t131.0.6778.204\tGoogle LLC\n"
    "Visual Studio Code\t1.96.0\tMicrosoft Corporation\n"
    "7-Zip\t24.08\tIgor Pavlov\n"
)

FAKE_CHOCO_OUTPUT = (
    "Chocolatey v2.3.0\n"
    "7zip 24.08\n"
    "git 2.47.1\n"
    "nodejs 22.0.0\n"
    "3 packages installed.\n"
)


def _mock_run(output: str):
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = output
    return mock


def test_scan_registry():
    with patch("app_detector.platforms.windows.subprocess.run", return_value=_mock_run(FAKE_REGISTRY_OUTPUT)):
        apps = _scan_registry()
    assert len(apps) == 3
    assert apps[0].name == "Google Chrome"
    assert apps[0].source == "registry"
    assert apps[1].metadata["publisher"] == "Microsoft Corporation"


def test_scan_choco():
    with patch("app_detector.platforms.windows.subprocess.run", return_value=_mock_run(FAKE_CHOCO_OUTPUT)):
        apps = _scan_choco()
    # Should skip "Chocolatey v2.3.0" and "3 packages installed."
    assert len(apps) == 3
    assert apps[0].name == "7zip"
    assert apps[0].source == "choco"
