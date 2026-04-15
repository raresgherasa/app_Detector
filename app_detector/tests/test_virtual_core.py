"""
100 Virtual Test Cases for App Detector
========================================
Tests 76–100: Core utilities, Manifest, platform detection, and AppEntry logic.
"""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from app_detector.models.app_entry import AppEntry
from app_detector.utils.platform_detect import detect_platform, PlatformInfo
from app_detector.core.manifest import Manifest, SCHEMA_VERSION


# ═══════════════════════════════════════════════════════════════════════════
# TEST 76-80: AppEntry Data Model Logic
# ═══════════════════════════════════════════════════════════════════════════

def test_76_app_entry_defaults():
    """TC76: AppEntry uses proper defaults when minimal info provided."""
    app = AppEntry(name="Test", package_id="test", version="1", source="apt")
    assert app.category == "uncategorised"
    assert app.is_selected is True
    assert app.target_version == "latest"
    assert app.metadata == {}


def test_77_app_entry_display_name():
    """TC77: AppEntry display_name formatting."""
    app = AppEntry(name="Foo", package_id="foo", version="1.0", source="apt")
    assert app.display_name == "Foo 1.0 (apt)"


def test_78_app_entry_str_checked():
    """TC78: AppEntry string formatting when checked."""
    app = AppEntry(name="Bar", package_id="b", version="2", source="snap", is_selected=True)
    assert str(app).startswith("✅")


def test_79_app_entry_str_unchecked():
    """TC79: AppEntry string formatting when unchecked."""
    app = AppEntry(name="Bar", package_id="b", version="2", source="snap", is_selected=False)
    assert str(app).startswith("☐")


def test_80_app_entry_dict_roundtrip():
    """TC80: AppEntry to_dict and from_dict symmetry."""
    app = AppEntry(name="Baz", package_id="baz", version="3", source="dnf", target_version="same")
    d = app.to_dict()
    assert d["name"] == "Baz"
    assert d["target_version"] == "same"
    app2 = AppEntry.from_dict(d)
    assert app2.name == app.name
    assert app2.target_version == app.target_version


# ═══════════════════════════════════════════════════════════════════════════
# TEST 81-85: Platform Detection
# ═══════════════════════════════════════════════════════════════════════════

def test_81_detect_linux():
    """TC81: detect_platform handling linux platform."""
    with patch("platform.system", return_value="Linux"):
        with patch("app_detector.utils.platform_detect._detect_linux_distro", return_value="Ubuntu 22.04 TITLE"):
            with patch("app_detector.utils.platform_detect._detect_available_managers_linux", return_value=["apt", "snap"]):
                info = detect_platform()
    assert info.family == "linux"
    assert info.distro == "Ubuntu 22.04 TITLE"
    assert "apt" in info.available_managers


def test_82_detect_windows():
    """TC82: detect_platform handling windows platform."""
    with patch("platform.system", return_value="Windows"):
        with patch("platform.release", return_value="11"):
            with patch("platform.version", return_value="22000"):
                with patch("app_detector.utils.platform_detect._detect_available_managers_windows", return_value=["winget"]):
                    info = detect_platform()
    assert info.family == "windows"
    assert "Windows 11" in info.distro
    assert info.available_managers == ["winget"]


def test_83_detect_macos():
    """TC83: detect_platform handling macos structure."""
    with patch("platform.system", return_value="Darwin"):
        with patch("platform.mac_ver", return_value=("14.0", "", "")):
            with patch("app_detector.utils.platform_detect._detect_available_managers_macos", return_value=["brew"]):
                info = detect_platform()
    assert info.family == "darwin"
    assert "macOS 14.0" in info.distro
    assert info.available_managers == ["brew"]


def test_84_detect_unknown_os():
    """TC84: detect_platform handles an exotic/unknown OS like FreeBSD gracefully."""
    with patch("platform.system", return_value="FreeBSD"):
        info = detect_platform()
    assert info.family == "freebsd"
    assert info.distro == "unknown"


def test_85_detect_linux_distro_fallback():
    """TC85: Distro detection falls back to 'Linux' if /etc/os-release is missing."""
    with patch("app_detector.utils.platform_detect.open", side_effect=FileNotFoundError):
        from app_detector.utils.platform_detect import _detect_linux_distro
        assert _detect_linux_distro() == "Linux"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 86-95: Manifest Parsing & Manipulation
# ═══════════════════════════════════════════════════════════════════════════

def _sample_info():
    return PlatformInfo(family="linux", distro="ImaginaryOS")


def test_86_manifest_creation_sets_timestamp():
    """TC86: Manifest.create populates the created_at timestamp."""
    m = Manifest.create([], _sample_info())
    assert m.created_at != ""
    assert "T" in m.created_at


def test_87_manifest_summary():
    """TC87: Manifest.summary produces correct output string."""
    app = AppEntry(name="Test", package_id="test", version="1", source="apt", is_selected=True)
    m = Manifest.create([app], _sample_info())
    assert "1 apps from ImaginaryOS (1 selected)" in m.summary


def test_88_manifest_loads_legacy_schema():
    """TC88: Manifest handles missing schema fields nicely."""
    data = {"apps": []}  # completely missing metadata
    m = Manifest.from_dict(data)
    assert m.schema_version == SCHEMA_VERSION  # should fall back to current
    assert m.apps == []


def test_89_manifest_merge_handles_empty():
    """TC89: Manifest.merge with an empty manifest."""
    a = Manifest.create([AppEntry("1", "1", "1", "apt")], _sample_info())
    b = Manifest.create([], _sample_info())
    m = Manifest.merge(a, b)
    assert len(m.apps) == 1


def test_90_manifest_merge_cross_os():
    """TC90: Manifest.merge keeps the source_os from the first argument."""
    a = Manifest.create([], PlatformInfo("linux", "LinuxDistro"))
    b = Manifest.create([], PlatformInfo("windows", "WinDistro"))
    m = Manifest.merge(a, b)
    assert m.source_os["family"] == "linux"


def test_91_manifest_to_json_ascii_safe():
    """TC91: to_json uses ensure_ascii=False for unicode support."""
    app = AppEntry(name="日本語", package_id="jp", version="1", source="apt")
    m = Manifest.create([app], _sample_info())
    json_str = m.to_json()
    assert "日本語" in json_str  # Not escaped to \uXXXX


def test_92_manifest_load_bad_json(tmp_path):
    """TC92: Loading invalid json file raises JSONDecodeError."""
    p = tmp_path / "bad.json"
    p.write_text("{ broken }")
    with pytest.raises(json.JSONDecodeError):
        Manifest.load(p)


def test_93_manifest_selected_apps_filter():
    """TC93: Manifest.selected_apps filters out unchecked entries."""
    a1 = AppEntry("1", "1", "1", "apt", is_selected=True)
    a2 = AppEntry("2", "2", "2", "apt", is_selected=False)
    m = Manifest.create([a1, a2], _sample_info())
    assert len(m.selected_apps) == 1
    assert m.selected_apps[0].package_id == "1"


def test_94_manifest_merge_keeps_first_duplicate():
    """TC94: If duplicates exist, the one from the first manifest is kept."""
    a1 = AppEntry("A", "a", "1", "apt", target_version="latest")
    a2 = AppEntry("A", "a", "2", "apt", target_version="same")
    m = Manifest.merge(
        Manifest.create([a1], _sample_info()),
        Manifest.create([a2], _sample_info()),
    )
    assert len(m.apps) == 1
    assert m.apps[0].target_version == "latest"


def test_95_manifest_merge_different_sources():
    """TC95: Same package ID but different source (e.g. apt vs snap) are kept separate."""
    a1 = AppEntry("App", "app", "1", "apt")
    a2 = AppEntry("App", "app", "1", "snap")
    m = Manifest.merge(
        Manifest.create([a1], _sample_info()),
        Manifest.create([a2], _sample_info()),
    )
    assert len(m.apps) == 2


# ═══════════════════════════════════════════════════════════════════════════
# TEST 96-100: Edge Cases & Subprocess Errors
# ═══════════════════════════════════════════════════════════════════════════

def test_96_subprocess_timeout_linux_dpkg():
    """TC96: Subprocess timeout properly caught and returns None/empty list."""
    import subprocess
    from app_detector.platforms.linux import _scan_dpkg
    with patch("app_detector.platforms.linux.subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 10)):
        apps = _scan_dpkg()
    assert apps == []


def test_97_subprocess_filenotfound_mac_system_profiler():
    """TC97: FileNotFoundError (binary missing despite _has returning True) caught."""
    from app_detector.platforms.macos import _scan_system_profiler
    with patch("app_detector.platforms.macos.subprocess.run", side_effect=FileNotFoundError):
        apps = _scan_system_profiler()
    assert apps == []


def test_98_linux_installer_subprocess_timeout():
    """TC98: Installer handles timeout during installation gracefully, returns False."""
    import subprocess
    from app_detector.platforms.linux import LinuxInstaller
    installer = LinuxInstaller()
    app = AppEntry("App", "app", "1", "apt")
    with patch("app_detector.platforms.linux.subprocess.run", side_effect=subprocess.TimeoutExpired("apt", 300)):
        ok = installer.install(app)
    assert ok is False


def test_99_linux_installer_filenotfound():
    """TC99: Installer handles FileNotFoundError gracefully, returns False."""
    from app_detector.platforms.linux import LinuxInstaller
    installer = LinuxInstaller()
    app = AppEntry("App", "app", "1", "apt")
    with patch("app_detector.platforms.linux.subprocess.run", side_effect=FileNotFoundError):
        ok = installer.install(app)
    assert ok is False


def test_100_core_bases():
    """TC100: Test abstract bases directly."""
    from app_detector.core.detector import AppDetector
    from app_detector.core.installer import AppInstaller
    # Trying to instantiate abstract child classes without overriding methods
    # should raise TypeError.
    class BadDetector(AppDetector): pass
    class BadInstaller(AppInstaller): pass

    with pytest.raises(TypeError):
        BadDetector()

    with pytest.raises(TypeError):
        BadInstaller()
