"""
100 Virtual Test Cases for App Detector
========================================
Tests 26–50: Windows scanner edge cases with imaginary system outputs.

Each test uses mocked subprocess/registry output representing imaginary
packages on a variety of Windows systems.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

from app_detector.platforms.windows import (
    _scan_registry,
    _scan_winget,
    _scan_choco,
    _map_registry_to_winget,
    WindowsDetector,
    WindowsInstaller,
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
# TEST 26: Windows 11 typical user — registry with many apps
# ═══════════════════════════════════════════════════════════════════════════

WIN11_REGISTRY = """\
Google Chrome\t131.0.6778.204\tGoogle LLC
Mozilla Firefox\t134.0\tMozilla Corporation
Microsoft Visual Studio Code\t1.96.0\tMicrosoft Corporation
Microsoft Edge\t131.0.2903.86\tMicrosoft Corporation
7-Zip\t24.08\tIgor Pavlov
Notepad++\t8.7.1\tNotepad++ Team
VLC media player\t3.0.21\tVideoLAN
Discord\t1.0.9164\tDiscord Inc.
Steam\t2.10.91.91\tValve Corporation
Spotify\t1.2.28.520\tSpotify AB
OBS Studio\t30.2.3\tOBS Project
GIMP 2.10.38\t2.10.38\tThe GIMP Team
Adobe Acrobat Reader DC\t24.005.20320\tAdobe Systems
Python 3.12.8 (64-bit)\t3.12.8\tPython Software Foundation
Node.js\t22.0.0\tNode.js Foundation
"""

def test_26_windows11_desktop():
    """TC26: Windows 11 desktop with 15 popular applications."""
    with patch("app_detector.platforms.windows.subprocess.run", return_value=_mock_run(WIN11_REGISTRY)):
        apps = _scan_registry()
    assert len(apps) == 15
    assert apps[0].name == "Google Chrome"
    assert apps[0].source == "registry"
    assert apps[0].metadata["publisher"] == "Google LLC"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 27: Registry with duplicate entries (HKLM + HKCU overlap)
# ═══════════════════════════════════════════════════════════════════════════

WIN_DUPES = """\
Python 3.12.8\t3.12.8\tPython Software Foundation
VS Code\t1.96.0\tMicrosoft
Python 3.12.8\t3.12.8\tPython Software Foundation
VS Code\t1.96.0\tMicrosoft
Unique App\t1.0.0\tUnique Publisher
"""

def test_27_registry_deduplication():
    """TC27: Registry returns same app from multiple hives — should dedup."""
    with patch("app_detector.platforms.windows.subprocess.run", return_value=_mock_run(WIN_DUPES)):
        apps = _scan_registry()
    assert len(apps) == 3  # deduped


# ═══════════════════════════════════════════════════════════════════════════
# TEST 28: Registry with missing publisher
# ═══════════════════════════════════════════════════════════════════════════

WIN_NO_PUB = """\
CoolTool\t2.1.0\t
OtherTool\t1.5\t
"""

def test_28_registry_no_publisher():
    """TC28: Registry entries without a publisher tab-field."""
    with patch("app_detector.platforms.windows.subprocess.run", return_value=_mock_run(WIN_NO_PUB)):
        apps = _scan_registry()
    assert len(apps) == 2
    assert apps[0].metadata == {}  # empty publisher not stored


# ═══════════════════════════════════════════════════════════════════════════
# TEST 29: Registry failure (PowerShell not available)
# ═══════════════════════════════════════════════════════════════════════════

def test_29_registry_powershell_fail():
    """TC29: PowerShell fails => scan_registry returns empty."""
    with patch("app_detector.platforms.windows.subprocess.run", return_value=_mock_run_fail()):
        apps = _scan_registry()
    assert apps == []


# ═══════════════════════════════════════════════════════════════════════════
# TEST 30: Registry with special characters in app names
# ═══════════════════════════════════════════════════════════════════════════

WIN_SPECIAL = """\
Résumé Builder Pro™\t3.0\tSpecial Corp.
C++ Build Tools (x64)\t14.42\tMicrosoft
日本語フォント Pack\t1.2.3\tFont Corp
App [Beta] v2\t2.0-beta\tBetaCo
"""

def test_30_registry_special_characters():
    """TC30: Registry apps with unicode, brackets, trademark symbols."""
    with patch("app_detector.platforms.windows.subprocess.run", return_value=_mock_run(WIN_SPECIAL)):
        apps = _scan_registry()
    assert len(apps) == 4
    assert "™" in apps[0].name
    assert "C++" in apps[1].name
    assert "日本語" in apps[2].name


# ═══════════════════════════════════════════════════════════════════════════
# TEST 31: winget list with various packages
# ═══════════════════════════════════════════════════════════════════════════

WINGET_LIST = """\
Name                       Id                         Version   Source
------------------------------------------------------------------------------------
Google Chrome              Google.Chrome               131.0     winget
Firefox                    Mozilla.Firefox             134.0     winget
Visual Studio Code         Microsoft.VisualStudioCode  1.96.0    winget
Git                        Git.Git                     2.47.1    winget
Python 3.12                Python.Python.3.12          3.12.8    winget
Node.js                    OpenJS.NodeJS               22.0.0    winget
Docker Desktop             Docker.DockerDesktop        4.36.0    winget
"""

def test_31_winget_list():
    """TC31: winget list with 7 typical developer tools."""
    with patch("app_detector.platforms.windows.subprocess.run", return_value=_mock_run(WINGET_LIST)):
        apps = _scan_winget()
    assert len(apps) >= 7
    assert any(a.source == "winget" for a in apps)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 32: winget empty output
# ═══════════════════════════════════════════════════════════════════════════

def test_32_winget_empty():
    """TC32: winget returns nothing (not installed or no apps)."""
    with patch("app_detector.platforms.windows.subprocess.run", return_value=_mock_run("")):
        apps = _scan_winget()
    assert apps == []


# ═══════════════════════════════════════════════════════════════════════════
# TEST 33: Chocolatey with many packages
# ═══════════════════════════════════════════════════════════════════════════

CHOCO_BIG = """\
Chocolatey v2.4.1
7zip 24.08
adobereader 2024.005.20320
autohotkey 2.0.18
bleachbit 4.6.2
cmake 3.31.2
curl 8.11.1
dotnet-sdk 9.0.100
ffmpeg 7.1
git 2.47.1
golang 1.23.4
gradle 8.11.1
jdk8 8.0.432
jq 1.7.1
make 4.4.1
maven 3.9.9
meld 3.21.4
nmap 7.95
putty 0.82
sysinternals 2024.12.12
20 packages installed.
"""

def test_33_choco_large_list():
    """TC33: Chocolatey with 20 developer + sysadmin packages."""
    with patch("app_detector.platforms.windows.subprocess.run", return_value=_mock_run(CHOCO_BIG)):
        apps = _scan_choco()
    assert len(apps) == 19
    assert apps[0].name == "7zip"
    assert apps[0].source == "choco"
    # "Chocolatey v2.4.1" header and "20 packages installed" footer skipped
    assert not any(a.name.lower() == "chocolatey" for a in apps)
    assert not any(a.name == "20" for a in apps)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 34: Chocolatey empty
# ═══════════════════════════════════════════════════════════════════════════

def test_34_choco_empty():
    """TC34: choco returns header only, no packages."""
    output = "Chocolatey v2.4.1\n0 packages installed.\n"
    with patch("app_detector.platforms.windows.subprocess.run", return_value=_mock_run(output)):
        apps = _scan_choco()
    assert apps == []


# ═══════════════════════════════════════════════════════════════════════════
# TEST 35: Registry-to-winget mapping
# ═══════════════════════════════════════════════════════════════════════════

def test_35_registry_winget_mapping():
    """TC35: Registry apps get remapped to winget IDs when names match."""
    reg_apps = [
        AppEntry(name="Google Chrome", package_id="Google Chrome", version="131.0", source="registry"),
        AppEntry(name="NoMatch App", package_id="NoMatch App", version="1.0", source="registry"),
    ]
    winget_apps = [
        AppEntry(name="Google Chrome", package_id="Google.Chrome", version="131.0", source="winget"),
    ]
    result = _map_registry_to_winget(reg_apps, winget_apps)
    assert result[0].package_id == "Google.Chrome"
    assert result[0].source == "winget"
    assert result[1].source == "registry"  # no match, stays as-is


# ═══════════════════════════════════════════════════════════════════════════
# TEST 36: Registry-to-winget case insensitive
# ═══════════════════════════════════════════════════════════════════════════

def test_36_registry_winget_case_insensitive():
    """TC36: Mapping works even when casing differs between registry/winget."""
    reg = [AppEntry(name="NOTEPAD++", package_id="NOTEPAD++", version="8.7", source="registry")]
    winget = [AppEntry(name="Notepad++", package_id="Notepad++.Notepad++", version="8.7", source="winget")]
    result = _map_registry_to_winget(reg, winget)
    assert result[0].package_id == "Notepad++.Notepad++"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 37: WindowsDetector full flow (registry + winget + choco)
# ═══════════════════════════════════════════════════════════════════════════

def test_37_windows_detector_full_flow():
    """TC37: Full WindowsDetector aggregation with all 3 sources."""
    reg_out = "Chrome\t131.0\tGoogle\nUnique-Reg\t1.0\tRegPub\n"
    winget_out = ""  # not matching format cleanly
    choco_out = "Chocolatey v2.4.1\nunique-choco 2.0\n1 packages installed.\n"

    call_count = {"n": 0}

    def fake_run(cmd, **kw):
        call_count["n"] += 1
        if "powershell" in cmd:
            return _mock_run(reg_out)
        if "winget" in cmd:
            return _mock_run(winget_out)
        if "choco" in cmd:
            return _mock_run(choco_out)
        return _mock_run_fail()

    with patch("app_detector.platforms.windows._has", return_value=True):
        with patch("app_detector.platforms.windows.subprocess.run", side_effect=fake_run):
            detector = WindowsDetector()
            apps = detector.scan()

    # Should have registry + choco unique entries
    assert len(apps) >= 3
    names = {a.name for a in apps}
    assert "Chrome" in names
    assert "Unique-Reg" in names
    assert "unique-choco" in names


# ═══════════════════════════════════════════════════════════════════════════
# TEST 38: WindowsInstaller winget latest
# ═══════════════════════════════════════════════════════════════════════════

def test_38_windows_installer_winget_latest():
    """TC38: winget install command for latest version."""
    app = AppEntry(name="Chrome", package_id="Google.Chrome", version="131.0", source="winget")
    installer = WindowsInstaller()
    with patch("app_detector.platforms.windows._has", return_value=True):
        cmd = installer.install_command(app)
    assert "winget" in cmd
    assert "--id" in cmd
    assert "Google.Chrome" in cmd
    assert "--version" not in cmd


# ═══════════════════════════════════════════════════════════════════════════
# TEST 39: WindowsInstaller winget pinned version
# ═══════════════════════════════════════════════════════════════════════════

def test_39_windows_installer_winget_pinned():
    """TC39: winget install with exact version."""
    app = AppEntry(
        name="Chrome", package_id="Google.Chrome", version="131.0",
        source="winget", target_version="same",
    )
    installer = WindowsInstaller()
    with patch("app_detector.platforms.windows._has", return_value=True):
        cmd = installer.install_command(app)
    assert "--version" in cmd
    assert "131.0" in cmd


# ═══════════════════════════════════════════════════════════════════════════
# TEST 40: WindowsInstaller choco
# ═══════════════════════════════════════════════════════════════════════════

def test_40_windows_installer_choco():
    """TC40: choco install command with -y flag."""
    app = AppEntry(name="git", package_id="git", version="2.47.1", source="choco")
    installer = WindowsInstaller()
    with patch("app_detector.platforms.windows._has", side_effect=lambda b: b == "choco"):
        cmd = installer.install_command(app)
    assert "choco" in cmd
    assert "-y" in cmd
    assert "git" in cmd


# ═══════════════════════════════════════════════════════════════════════════
# TEST 41: WindowsInstaller choco pinned version
# ═══════════════════════════════════════════════════════════════════════════

def test_41_windows_installer_choco_pinned():
    """TC41: choco install with --version flag."""
    app = AppEntry(
        name="git", package_id="git", version="2.47.1",
        source="choco", target_version="same",
    )
    installer = WindowsInstaller()
    with patch("app_detector.platforms.windows._has", side_effect=lambda b: b == "choco"):
        cmd = installer.install_command(app)
    assert "--version" in cmd
    assert "2.47.1" in cmd


# ═══════════════════════════════════════════════════════════════════════════
# TEST 42: WindowsInstaller fallback to winget when source is registry
# ═══════════════════════════════════════════════════════════════════════════

def test_42_windows_installer_registry_fallback():
    """TC42: Registry-sourced app falls back to winget if available."""
    app = AppEntry(name="SomeApp", package_id="SomeApp", version="1.0", source="registry")
    installer = WindowsInstaller()
    with patch("app_detector.platforms.windows._has", side_effect=lambda b: b == "winget"):
        cmd = installer.install_command(app)
    assert "winget" in cmd


# ═══════════════════════════════════════════════════════════════════════════
# TEST 43: WindowsInstaller no manager available
# ═══════════════════════════════════════════════════════════════════════════

def test_43_windows_installer_no_manager():
    """TC43: No package manager => echo fallback."""
    app = AppEntry(name="SomeApp", package_id="SomeApp", version="1.0", source="registry")
    installer = WindowsInstaller()
    with patch("app_detector.platforms.windows._has", return_value=False):
        cmd = installer.install_command(app)
    assert cmd[0] == "echo"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 44: WindowsDetector with only registry (no winget/choco)
# ═══════════════════════════════════════════════════════════════════════════

def test_44_windows_detector_registry_only():
    """TC44: Windows system without winget or choco installed."""
    reg_out = "Paint\t11.0\tMicrosoft\nCalc\t11.0\tMicrosoft\n"

    def fake_has(binary):
        return binary == "powershell"

    with patch("app_detector.platforms.windows._has", side_effect=fake_has):
        with patch("app_detector.platforms.windows.subprocess.run", return_value=_mock_run(reg_out)):
            detector = WindowsDetector()
            apps = detector.scan()

    assert len(apps) == 2
    assert all(a.source == "registry" for a in apps)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 45: Registry with very long app names
# ═══════════════════════════════════════════════════════════════════════════

def test_45_registry_long_names():
    """TC45: Registry apps with extremely long display names."""
    long_name = "A" * 256
    output = f"{long_name}\t1.0\tLongNamePublisher\n"
    with patch("app_detector.platforms.windows.subprocess.run", return_value=_mock_run(output)):
        apps = _scan_registry()
    assert len(apps) == 1
    assert len(apps[0].name) == 256


# ═══════════════════════════════════════════════════════════════════════════
# TEST 46: Choco with pre-release versions
# ═══════════════════════════════════════════════════════════════════════════

CHOCO_PRERELEASE = """\
Chocolatey v2.4.1
rust-nightly 1.83.0-nightly.20241201
flutter-beta 3.27.0-beta.1
terraform-rc 1.10.0-rc2
3 packages installed.
"""

def test_46_choco_prerelease_versions():
    """TC46: Chocolatey packages with pre-release version strings."""
    with patch("app_detector.platforms.windows.subprocess.run", return_value=_mock_run(CHOCO_PRERELEASE)):
        apps = _scan_choco()
    assert len(apps) == 3
    assert "nightly" in apps[0].version
    assert "beta" in apps[1].version
    assert "rc2" in apps[2].version


# ═══════════════════════════════════════════════════════════════════════════
# TEST 47: Registry with version-less entries
# ═══════════════════════════════════════════════════════════════════════════

WIN_NO_VER = """\
Mystery Driver\t\tOEM Vendor
Firmware Update Tool\t\tHardware Corp
"""

def test_47_registry_no_version():
    """TC47: Registry entries where version is empty."""
    with patch("app_detector.platforms.windows.subprocess.run", return_value=_mock_run(WIN_NO_VER)):
        apps = _scan_registry()
    assert len(apps) == 2
    assert apps[0].version == ""


# ═══════════════════════════════════════════════════════════════════════════
# TEST 48: WindowsInstaller.install simulated success
# ═══════════════════════════════════════════════════════════════════════════

def test_48_windows_install_success():
    """TC48: Simulated successful winget install."""
    app = AppEntry(name="Git", package_id="Git.Git", version="2.47.1", source="winget")
    installer = WindowsInstaller()
    with patch("app_detector.platforms.windows._has", return_value=True):
        with patch("app_detector.platforms.windows.subprocess.run", return_value=_mock_run("Successfully installed")):
            ok = installer.install(app)
    assert ok is True


# ═══════════════════════════════════════════════════════════════════════════
# TEST 49: WindowsInstaller.install simulated failure
# ═══════════════════════════════════════════════════════════════════════════

def test_49_windows_install_failure():
    """TC49: Simulated failed winget install."""
    app = AppEntry(name="BadPkg", package_id="Bad.Pkg", version="1.0", source="winget")
    installer = WindowsInstaller()
    with patch("app_detector.platforms.windows._has", return_value=True):
        with patch("app_detector.platforms.windows.subprocess.run", return_value=_mock_run_fail()):
            ok = installer.install(app)
    assert ok is False


# ═══════════════════════════════════════════════════════════════════════════
# TEST 50: Large registry stress test (200 entries)
# ═══════════════════════════════════════════════════════════════════════════

def test_50_registry_stress_test():
    """TC50: Stress test — 200 imaginary registry entries."""
    lines = [f"App-{i}\tv{i}.0.0\tPublisher-{i}" for i in range(200)]
    output = "\n".join(lines)
    with patch("app_detector.platforms.windows.subprocess.run", return_value=_mock_run(output)):
        apps = _scan_registry()
    assert len(apps) == 200
    assert apps[199].name == "App-199"
