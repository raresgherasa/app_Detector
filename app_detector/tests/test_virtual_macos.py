"""
100 Virtual Test Cases for App Detector
========================================
Tests 51–75: macOS scanner and installer edge cases with imaginary system outputs.

Each test uses mocked subprocess/JSON output representing imaginary
applications on various macOS systems.
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch, MagicMock

from app_detector.platforms.macos import (
    _scan_system_profiler,
    _scan_brew_formulae,
    _scan_brew_casks,
    _scan_applications_dir,
    MacOSDetector,
    MacOSInstaller,
)
from app_detector.models.app_entry import AppEntry


def _mock_run(output: str):
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = output
    return mock


def _mock_run_fail():
    mock = MagicMock()
    mock.returncode = 1
    mock.stdout = ""
    return mock


# ═══════════════════════════════════════════════════════════════════════════
# TEST 51: system_profiler with standard macOS apps
# ═══════════════════════════════════════════════════════════════════════════

SP_JSON = {
    "SPApplicationsDataType": [
        {"_name": "Safari", "version": "18.2", "path": "/Applications/Safari.app"},
        {"_name": "Mail", "version": "16.0", "path": "/Applications/Mail.app"},
        {"_name": "Messages", "version": "14.0", "path": "/Applications/Messages.app"},
        {"_name": "Terminal", "version": "2.14", "path": "/System/Applications/Utilities/Terminal.app"},
        {"_name": "Xcode", "version": "16.1", "path": "/Applications/Xcode.app"},
        {"_name": "Final Cut Pro", "version": "10.8.1", "path": "/Applications/Final Cut Pro.app"},
        {"_name": "Pages", "version": "14.2", "path": "/Applications/Pages.app"},
    ]
}

def test_51_macos_system_profiler_standard():
    """TC51: macOS system_profiler output with 7 standard Apple apps."""
    out = json.dumps(SP_JSON)
    with patch("app_detector.platforms.macos.subprocess.run", return_value=_mock_run(out)):
        apps = _scan_system_profiler()
    assert len(apps) == 7
    assert apps[0].name == "Safari"
    assert apps[0].source == "system"
    assert apps[3].name == "Terminal"
    assert "Terminal.app" in apps[3].metadata["path"]


# ═══════════════════════════════════════════════════════════════════════════
# TEST 52: system_profiler missing name field
# ═══════════════════════════════════════════════════════════════════════════

SP_NO_NAME = {
    "SPApplicationsDataType": [
        {"version": "1.0", "path": "/Applications/NoName.app"},
        {"_name": "GoodApp", "version": "2.0"},
    ]
}

def test_52_system_profiler_missing_name():
    """TC52: system_profiler ignores entries missing the '_name' field."""
    out = json.dumps(SP_NO_NAME)
    with patch("app_detector.platforms.macos.subprocess.run", return_value=_mock_run(out)):
        apps = _scan_system_profiler()
    assert len(apps) == 1
    assert apps[0].name == "GoodApp"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 53: system_profiler invalid JSON output
# ═══════════════════════════════════════════════════════════════════════════

def test_53_system_profiler_invalid_json():
    """TC53: system_profiler returns broken JSON."""
    with patch("app_detector.platforms.macos.subprocess.run", return_value=_mock_run("{ broken json : }")):
        apps = _scan_system_profiler()
    assert apps == []


# ═══════════════════════════════════════════════════════════════════════════
# TEST 54: Homebrew formulae
# ═══════════════════════════════════════════════════════════════════════════

BREW_FORMULAE = """\
bat 0.24.0
curl 8.11.1
ffmpeg 7.1
gh 2.64.0
imagemagick 7.1.1-43
jq 1.7.1
node 23.5.0
python@3.12 3.12.8
ripgrep 14.1.1
tmux 3.5a
wget 1.25.0
"""

def test_54_brew_formulae():
    """TC54: brew list --formula with 11 common CLI tools."""
    with patch("app_detector.platforms.macos.subprocess.run", return_value=_mock_run(BREW_FORMULAE)):
        apps = _scan_brew_formulae()
    assert len(apps) == 11
    assert apps[0].name == "bat"
    assert apps[0].source == "brew"
    assert apps[7].name == "python@3.12"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 55: Homebrew formulae empty
# ═══════════════════════════════════════════════════════════════════════════

def test_55_brew_formulae_empty():
    """TC55: brew formula returns empty string."""
    with patch("app_detector.platforms.macos.subprocess.run", return_value=_mock_run("")):
        apps = _scan_brew_formulae()
    assert apps == []


# ═══════════════════════════════════════════════════════════════════════════
# TEST 56: Homebrew casks
# ═══════════════════════════════════════════════════════════════════════════

BREW_CASKS = """\
1password 8.10.36
alfred 5.5.1
discord 0.0.315
docker 4.37.1
firefox 134.0
google-chrome 132.0.6834.83
iterm2 3.5.11
notion 3.16.0
postman 11.20.0
raycast 1.88.2
slack 4.41.105
spotify 1.2.54.403
visual-studio-code 1.96.0
vlc 3.0.21
zoom 6.3.3
"""

def test_56_brew_casks():
    """TC56: brew list --cask with 15 common GUI applications."""
    with patch("app_detector.platforms.macos.subprocess.run", return_value=_mock_run(BREW_CASKS)):
        apps = _scan_brew_casks()
    assert len(apps) == 15
    assert apps[0].name == "1password"
    assert apps[0].source == "brew-cask"
    assert apps[12].name == "visual-studio-code"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 57: Applications directory flat scanning — finds unknown apps
# ═══════════════════════════════════════════════════════════════════════════

def test_57_applications_dir_scanner():
    """TC57: Scan /Applications using local directory mock."""
    fake_apps = ["CoolApp.app", "AnotherApp.app", "hidden_file.txt"]
    
    with patch("app_detector.platforms.macos.os.path.isdir", return_value=True):
        with patch("app_detector.platforms.macos.os.listdir", return_value=fake_apps):
            apps = _scan_applications_dir()
            
    assert len(apps) == 2
    assert apps[0].name == "CoolApp"
    assert apps[0].source == "applications-dir"
    assert apps[1].name == "AnotherApp"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 58: Applications directory missing
# ═══════════════════════════════════════════════════════════════════════════

def test_58_applications_dir_missing():
    """TC58: /Applications directory does not exist (unlikely, but handled)."""
    with patch("app_detector.platforms.macos.os.path.isdir", return_value=False):
        apps = _scan_applications_dir()
    assert apps == []


# ═══════════════════════════════════════════════════════════════════════════
# TEST 59: MacOSDetector integration — full aggregation
# ═══════════════════════════════════════════════════════════════════════════

def test_59_macos_detector_full():
    """TC59: MacOSDetector combines SP, Brew, and /Applications."""
    # 1 SP App
    sp_json = json.dumps({"SPApplicationsDataType": [{"_name": "SystemApp", "version": "1.0"}]})
    # 1 Brew Formula
    brew_f = "node 22\n"
    # 1 Brew Cask
    brew_c = "vlc 3.0\n"
    # directory -> returns "SystemApp.app" and "NewApp.app"
    dir_apps = ["SystemApp.app", "NewApp.app", "Random.txt"]

    call_count = {"n": 0}
    def fake_run(cmd, **kw):
        call_count["n"] += 1
        if "SPApplicationsDataType" in cmd:
            return _mock_run(sp_json)
        if "--formula" in cmd:
            return _mock_run(brew_f)
        if "--cask" in cmd:
            return _mock_run(brew_c)
        return _mock_run_fail()

    with patch("app_detector.platforms.macos._has", return_value=True):
        with patch("app_detector.platforms.macos.subprocess.run", side_effect=fake_run):
            with patch("app_detector.platforms.macos.os.path.isdir", return_value=True):
                with patch("app_detector.platforms.macos.os.listdir", return_value=dir_apps):
                    detector = MacOSDetector()
                    apps = detector.scan()

    # SystemApp (system), node (brew), vlc (brew-cask), NewApp (dir)
    # Note: SystemApp shouldn't be added twice because the dir scanner dedups
    assert len(apps) == 4
    names = {a.name for a in apps}
    assert names == {"SystemApp", "node", "vlc", "NewApp"}


# ═══════════════════════════════════════════════════════════════════════════
# TEST 60: MacOSDetector without Homebrew
# ═══════════════════════════════════════════════════════════════════════════

def test_60_macos_detector_no_brew():
    """TC60: System without Homebrew installed."""
    sp_json = json.dumps({"SPApplicationsDataType": [{"_name": "Safari", "version": "1.0"}]})
    
    with patch("app_detector.platforms.macos._has", return_value=False):
        with patch("app_detector.platforms.macos.subprocess.run", return_value=_mock_run(sp_json)):
            with patch("app_detector.platforms.macos.os.path.isdir", return_value=False):
                detector = MacOSDetector()
                apps = detector.scan()
                
    assert len(apps) == 1
    assert apps[0].name == "Safari"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 61: MacOSInstaller brew formula
# ═══════════════════════════════════════════════════════════════════════════

def test_61_macos_installer_brew():
    """TC61: brew formula install command."""
    app = AppEntry(name="wget", package_id="wget", version="1.0", source="brew")
    installer = MacOSInstaller()
    with patch("app_detector.platforms.macos._has", return_value=True):
        cmd = installer.install_command(app)
    assert cmd == ["brew", "install", "wget"]


# ═══════════════════════════════════════════════════════════════════════════
# TEST 62: MacOSInstaller brew formula exact version
# ═══════════════════════════════════════════════════════════════════════════

def test_62_macos_installer_brew_pinned():
    """TC62: brew formula install command with pinned version."""
    app = AppEntry(name="wget", package_id="wget", version="1.25.0", source="brew", target_version="same")
    installer = MacOSInstaller()
    with patch("app_detector.platforms.macos._has", return_value=True):
        cmd = installer.install_command(app)
    assert cmd == ["brew", "install", "wget@1.25.0"]


# ═══════════════════════════════════════════════════════════════════════════
# TEST 63: MacOSInstaller brew cask
# ═══════════════════════════════════════════════════════════════════════════

def test_63_macos_installer_cask():
    """TC63: brew cask install command."""
    app = AppEntry(name="vlc", package_id="vlc", version="3.0", source="brew-cask")
    installer = MacOSInstaller()
    with patch("app_detector.platforms.macos._has", return_value=True):
        cmd = installer.install_command(app)
    assert cmd == ["brew", "install", "--cask", "vlc"]


# ═══════════════════════════════════════════════════════════════════════════
# TEST 64: MacOSInstaller mas (Mac App Store)
# ═══════════════════════════════════════════════════════════════════════════

def test_64_macos_installer_mas():
    """TC64: mas install command."""
    app = AppEntry(name="Xcode", package_id="497799835", version="16.0", source="mas")
    installer = MacOSInstaller()
    with patch("app_detector.platforms.macos._has", side_effect=lambda x: x == "mas"):
        cmd = installer.install_command(app)
    assert cmd == ["mas", "install", "497799835"]


# ═══════════════════════════════════════════════════════════════════════════
# TEST 65: MacOSInstaller fallback to cask
# ═══════════════════════════════════════════════════════════════════════════

def test_65_macos_installer_fallback_cask():
    """TC65: Unknown sources (like system/directory apps) default to brew cask."""
    app = AppEntry(name="Discord", package_id="discord", version="1.0", source="applications-dir")
    installer = MacOSInstaller()
    with patch("app_detector.platforms.macos._has", return_value=True):
        cmd = installer.install_command(app)
    assert cmd == ["brew", "install", "--cask", "discord"]


# ═══════════════════════════════════════════════════════════════════════════
# TEST 66: system_profiler stress test
# ═══════════════════════════════════════════════════════════════════════════

def test_66_macos_system_profiler_stress():
    """TC66: Stress test 300 apps from system_profiler."""
    data = {"SPApplicationsDataType": []}
    for i in range(300):
        data["SPApplicationsDataType"].append({
            "_name": f"App{i}", "version": f"1.{i}", "path": f"/Apps/App{i}.app"
        })
    with patch("app_detector.platforms.macos.subprocess.run", return_value=_mock_run(json.dumps(data))):
        apps = _scan_system_profiler()
    assert len(apps) == 300
    assert apps[299].name == "App299"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 67: MacOSInstaller.install success
# ═══════════════════════════════════════════════════════════════════════════

def test_67_macos_installer_success():
    """TC67: Simulated successful brew install."""
    app = AppEntry(name="git", package_id="git", version="1.0", source="brew")
    installer = MacOSInstaller()
    with patch("app_detector.platforms.macos.subprocess.run", return_value=_mock_run("success")):
        ok = installer.install(app)
    assert ok is True


# ═══════════════════════════════════════════════════════════════════════════
# TEST 68: MacOSInstaller.install failure
# ═══════════════════════════════════════════════════════════════════════════

def test_68_macos_installer_failure():
    """TC68: Simulated failed brew install."""
    app = AppEntry(name="git", package_id="git", version="1.0", source="brew")
    installer = MacOSInstaller()
    with patch("app_detector.platforms.macos.subprocess.run", return_value=_mock_run_fail()):
        ok = installer.install(app)
    assert ok is False


# ═══════════════════════════════════════════════════════════════════════════
# TEST 69: brew formula output with varying spaces
# ═══════════════════════════════════════════════════════════════════════════

BREW_WEIRD_SPACES = "bat    0.24.0\npython@3.11   3.11.10\n"

def test_69_brew_formula_weird_spacing():
    """TC69: brew formula handles weird whitespaces."""
    with patch("app_detector.platforms.macos.subprocess.run", return_value=_mock_run(BREW_WEIRD_SPACES)):
        apps = _scan_brew_formulae()
    assert len(apps) == 2
    assert apps[0].name == "bat"
    assert apps[1].name == "python@3.11"
    assert apps[1].version == "3.11.10"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 70: Applications dir ignores non-.app bundles
# ═══════════════════════════════════════════════════════════════════════════

def test_70_applications_ignores_other_files():
    """TC70: Applications scanner ignores .txt, .md, .dmg files."""
    fake_apps = ["Valid.app", "setup.dmg", "README.md", "Icon\r"]
    with patch("app_detector.platforms.macos.os.path.isdir", return_value=True):
        with patch("app_detector.platforms.macos.os.listdir", return_value=fake_apps):
            apps = _scan_applications_dir()
    assert len(apps) == 1
    assert apps[0].name == "Valid"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 71: system_profiler deep nested structures
# ═══════════════════════════════════════════════════════════════════════════

SP_NESTED = {
    "SPApplicationsDataType": [
        {"_name": "App", "version": "1.0", "info": {"inner": "data", "deep": {"key": "val"}}}
    ]
}

def test_71_system_profiler_nested_metadata():
    """TC71: system_profiler ignores extra nested JSON to avoid bloat."""
    with patch("app_detector.platforms.macos.subprocess.run", return_value=_mock_run(json.dumps(SP_NESTED))):
        apps = _scan_system_profiler()
    assert len(apps) == 1
    assert apps[0].name == "App"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 72: brew list timeout
# ═══════════════════════════════════════════════════════════════════════════

def test_72_brew_list_timeout():
    """TC72: brew list command times out."""
    import subprocess
    def fake_timeout(*a, **kw):
        raise subprocess.TimeoutExpired("brew", 30)

    with patch("app_detector.platforms.macos.subprocess.run", side_effect=fake_timeout):
        apps = _scan_brew_formulae()
    assert apps == []


# ═══════════════════════════════════════════════════════════════════════════
# TEST 73: MacOSInstaller mas unavailable
# ═══════════════════════════════════════════════════════════════════════════

def test_73_macos_mas_fallback():
    """TC73: App sourced from MAS, but mas CLI isn't installed => fall back to brew cask."""
    app = AppEntry(name="Xcode", package_id="Xcode", version="16.0", source="mas")
    installer = MacOSInstaller()
    with patch("app_detector.platforms.macos._has", return_value=False):
        cmd = installer.install_command(app)
    assert cmd == ["brew", "install", "--cask", "Xcode"]


# ═══════════════════════════════════════════════════════════════════════════
# TEST 74: system_profiler missing version
# ═══════════════════════════════════════════════════════════════════════════

SP_NO_VER = {"SPApplicationsDataType": [{"_name": "App_without_version"}]}

def test_74_system_profiler_missing_version():
    """TC74: system_profiler assigns 'unknown' to apps without a version string."""
    with patch("app_detector.platforms.macos.subprocess.run", return_value=_mock_run(json.dumps(SP_NO_VER))):
        apps = _scan_system_profiler()
    assert len(apps) == 1
    assert apps[0].version == "unknown"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 75: MacOSDetector empty run
# ═══════════════════════════════════════════════════════════════════════════

def test_75_macos_detector_completely_empty():
    """TC75: MacOSDetector when everything fails or returns nothing."""
    with patch("app_detector.platforms.macos._has", return_value=False):
        with patch("app_detector.platforms.macos.subprocess.run", return_value=_mock_run("")):
            with patch("app_detector.platforms.macos.os.path.isdir", return_value=False):
                detector = MacOSDetector()
                apps = detector.scan()
    assert apps == []
