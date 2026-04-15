"""
100 Virtual Test Cases for App Detector
========================================
Tests 1–25: Linux scanner edge cases with imaginary system outputs.

Each test uses mocked subprocess output representing imaginary packages
that would appear on various Linux distributions.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock, PropertyMock

from app_detector.platforms.linux import (
    _scan_dpkg,
    _scan_rpm,
    _scan_snap,
    _scan_flatpak,
    _scan_pacman,
    LinuxDetector,
    LinuxInstaller,
)
from app_detector.models.app_entry import AppEntry


# ── Helpers ─────────────────────────────────────────────────────────────────

def _mock_run(output: str):
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = output
    return mock


def _mock_run_fail():
    mock = MagicMock()
    mock.returncode = 1
    mock.stdout = ""
    mock.stderr = "command failed"
    return mock


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: Ubuntu-like system with many common desktop apps
# ═══════════════════════════════════════════════════════════════════════════

UBUNTU_DPKG = """\
firefox\t128.0.3-0ubuntu1\tMozilla Firefox web browser
thunderbird\t115.12.0-0ubuntu1\tMozilla Thunderbird email client
libreoffice-writer\t1:24.8.4-0ubuntu1\toffice productivity suite -- word processor
libreoffice-calc\t1:24.8.4-0ubuntu1\toffice productivity suite -- spreadsheet
vlc\t3.0.21-1build1\tMultimedia player and streamer
gimp\t2.10.38-1ubuntu1\tGNU Image Manipulation Program
inkscape\t1.4-1ubuntu1\tVector-based drawing program
blender\t4.2.0-1build1\t3D creation suite
audacity\t3.6.4-1ubuntu1\tFree, cross-platform, audio editor
obs-studio\t30.2.0-1ubuntu1\tOpen Broadcaster Software
steam\t1:1.0.0.81-1ubuntu1\tValve's Steam digital software delivery system
code\t1.96.0-1734607680\tMicrosoft Visual Studio Code
docker-ce\t5:27.4.0-1~ubuntu.24.04~noble\tDocker: the open-source application container engine
git\t1:2.45.2-1ubuntu1\tfast, scalable, distributed revision control system
python3\t3.12.3-0ubuntu2\tinteractive high-level object-oriented language
"""

def test_01_ubuntu_desktop_system():
    """TC01: Full Ubuntu desktop with 15 common packages."""
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run(UBUNTU_DPKG)):
        apps = _scan_dpkg()
    assert len(apps) == 15
    assert apps[0].name == "firefox"
    assert apps[0].source == "apt"
    assert apps[0].version == "128.0.3-0ubuntu1"
    assert apps[12].name == "docker-ce"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: dpkg package with no description field
# ═══════════════════════════════════════════════════════════════════════════

DPKG_NO_DESC = """\
libzstd1\t1.5.6-1\t
libxml2\t2.12.7-1build1\t
"""

def test_02_dpkg_packages_without_descriptions():
    """TC02: dpkg entries with empty description tab-field."""
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run(DPKG_NO_DESC)):
        apps = _scan_dpkg()
    assert len(apps) == 2
    assert apps[0].metadata.get("description", "") == ""


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: dpkg with unicode / special characters in descriptions
# ═══════════════════════════════════════════════════════════════════════════

DPKG_UNICODE = """\
fonts-noto-cjk\t1:20230817+repack1-3\tNo Tofu font families — CJK (Chinese/Japanese/Korean)
matériel-design\t2.0.1-1\tMatériel icons — design toolkit (àéîö)
"""

def test_03_dpkg_unicode_descriptions():
    """TC03: dpkg packages with unicode chars in names/descriptions."""
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run(DPKG_UNICODE)):
        apps = _scan_dpkg()
    assert len(apps) == 2
    assert "CJK" in apps[0].metadata["description"]
    assert apps[1].name == "matériel-design"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: dpkg completely empty output
# ═══════════════════════════════════════════════════════════════════════════

def test_04_dpkg_empty_output():
    """TC04: dpkg returns empty string (fresh minimal install)."""
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run("")):
        apps = _scan_dpkg()
    assert apps == []


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5: dpkg command fails entirely
# ═══════════════════════════════════════════════════════════════════════════

def test_05_dpkg_command_failure():
    """TC05: dpkg-query returns non-zero exit code."""
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run_fail()):
        apps = _scan_dpkg()
    assert apps == []


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6: dpkg with very long version strings
# ═══════════════════════════════════════════════════════════════════════════

DPKG_LONG_VERSIONS = """\
linux-image-6.8.0-45-generic\t6.8.0-45.45~24.04.1+really6.8.0-45.45\tLinux kernel image
nvidia-driver-560\t560.35.03-0ubuntu1~24.04.2+really560.35.03-0ubuntu1\tNVIDIA driver metapackage
"""

def test_06_dpkg_long_complex_versions():
    """TC06: Packages with long, complex epoch+version strings."""
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run(DPKG_LONG_VERSIONS)):
        apps = _scan_dpkg()
    assert len(apps) == 2
    assert "really" in apps[0].version


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7: Fedora-like RPM system
# ═══════════════════════════════════════════════════════════════════════════

RPM_FEDORA = """\
kernel\t6.10.12\tThe Linux kernel
dnf\t4.21.0\tPackage manager forked from Yum
gnome-shell\t47.2\tWindow management and application launching for GNOME
firefox\t132.0\tMozilla Firefox Web browser
podman\t5.3.1\tManage Pods, Containers and Container Images
cockpit\t328\tWeb Console for Linux servers
flatpak\t1.14.10\tApplication deployment framework
rpm-build\t4.20.0\tScripts for building RPM packages
golang\t1.23.4\tThe Go Programming Language
rust\t1.82.0\tThe Rust Programming Language
"""

def test_07_fedora_rpm_system():
    """TC07: Fedora system with kernel, gnome, dev tools via rpm."""
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run(RPM_FEDORA)):
        with patch("app_detector.platforms.linux._has", return_value=True):
            apps = _scan_rpm()
    assert len(apps) == 10
    assert apps[0].name == "kernel"
    assert apps[4].name == "podman"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 8: RPM with empty output
# ═══════════════════════════════════════════════════════════════════════════

def test_08_rpm_empty_output():
    """TC08: rpm returns nothing (no RPM packages installed)."""
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run("")):
        apps = _scan_rpm()
    assert apps == []


# ═══════════════════════════════════════════════════════════════════════════
# TEST 9: Arch Linux pacman system
# ═══════════════════════════════════════════════════════════════════════════

PACMAN_ARCH = """\
linux 6.12.4.arch1-1
base 3-2
systemd 256.7-1
networkmanager 1.50.0-1
firefox 133.0-1
neovim 0.10.3-1
kitty 0.37.0-1
zsh 5.9-5
yay 12.4.2-1
hyprland 0.45.0-2
waybar 0.11.0-4
pipewire 1:1.2.7-1
mesa 24.3.1-1
vulkan-radeon 24.3.1-1
steam 1.0.0.81-1
"""

def test_09_arch_linux_pacman():
    """TC09: Arch Linux with desktop + gaming packages from pacman."""
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run(PACMAN_ARCH)):
        apps = _scan_pacman()
    assert len(apps) == 15
    assert apps[0].name == "linux"
    assert apps[0].source == "pacman"
    assert apps[9].name == "hyprland"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 10: Pacman with single-word entries (no version)
# ═══════════════════════════════════════════════════════════════════════════

PACMAN_BAD = """\
orphan-pkg
normal-pkg 1.0
"""

def test_10_pacman_malformed_lines():
    """TC10: pacman output with a line missing the version field."""
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run(PACMAN_BAD)):
        apps = _scan_pacman()
    assert len(apps) == 1  # only the valid line
    assert apps[0].name == "normal-pkg"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 11: Large snap list with channels
# ═══════════════════════════════════════════════════════════════════════════

SNAP_LARGE = """\
Name               Version          Rev    Tracking       Publisher
core22             20240301         1380   latest/stable  canonical✓
firefox            134.0            4480   latest/stable  mozilla✓
thunderbird        128.5.0          600    latest/stable  canonical✓
chromium           131.0.6778.204   2900   latest/stable  nicholaschoi
spotify            1.2.28.520       78     latest/stable  spotify✓
slack              4.41.105         200    latest/stable  slack✓
discord            0.0.75           44     latest/stable  snapcrafters
signal-desktop     7.34.0           980    latest/stable  signalmessenger✓
telegram-desktop   5.8.3            7150   latest/stable  nicholaschoi
vlc                3.0.21           3700   latest/stable  videolan✓
obs-studio         30.2.3           1500   latest/stable  snapcrafters
gimp               2.10.38          500    latest/stable  snapcrafters
blender            4.2.4            5000   latest/stable  blenderfoundation✓
krita              5.2.6            300    latest/stable  krita✓
"""

def test_11_snap_large_list():
    """TC11: snap list with 14 popular desktop applications + core."""
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run(SNAP_LARGE)):
        apps = _scan_snap()
    assert len(apps) == 14
    assert apps[0].name == "core22"
    assert apps[1].name == "firefox"
    assert apps[1].source == "snap"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 12: Snap with only header (no packages)
# ═══════════════════════════════════════════════════════════════════════════

SNAP_HEADER_ONLY = "Name               Version          Rev    Tracking       Publisher\n"

def test_12_snap_header_only():
    """TC12: snap list output has header but no actual packages."""
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run(SNAP_HEADER_ONLY)):
        apps = _scan_snap()
    assert apps == []


# ═══════════════════════════════════════════════════════════════════════════
# TEST 13: Flatpak with diverse app IDs
# ═══════════════════════════════════════════════════════════════════════════

FLATPAK_DIVERSE = """\
org.gimp.GIMP\t2.10.38\tGIMP
org.kde.kdenlive\t24.08.3\tKdenlive
com.github.tchx84.Flatseal\t2.3.0\tFlatseal
org.mozilla.firefox\t134.0\tFirefox
com.valvesoftware.Steam\t1.0.0.81\tSteam
io.github.nickvision.cavalier\t2024.12.0\tCavalier
org.videolan.VLC\t3.0.21\tVLC media player
com.spotify.Client\t1.2.28\tSpotify
org.signal.Signal\t7.34.0\tSignal
com.discordapp.Discord\t0.0.75\tDiscord
org.keepassxc.KeePassXC\t2.7.9\tKeePassXC
org.telegram.desktop\t5.8.3\tTelegram Desktop
"""

def test_13_flatpak_diverse_apps():
    """TC13: 12 diverse flatpak apps with reverse-DNS identifiers."""
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run(FLATPAK_DIVERSE)):
        apps = _scan_flatpak()
    assert len(apps) == 12
    assert apps[0].package_id == "org.gimp.GIMP"
    assert apps[4].name == "Steam"
    assert apps[4].source == "flatpak"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 14: Flatpak with no version column
# ═══════════════════════════════════════════════════════════════════════════

FLATPAK_NO_VER = """\
org.gnome.Calculator\t\tCalculator
org.gnome.TextEditor\t\tText Editor
"""

def test_14_flatpak_missing_versions():
    """TC14: flatpak apps where version field is empty."""
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run(FLATPAK_NO_VER)):
        apps = _scan_flatpak()
    assert len(apps) == 2
    assert apps[0].version == ""


# ═══════════════════════════════════════════════════════════════════════════
# TEST 15: LinuxDetector aggregation (dpkg + snap present, no others)
# ═══════════════════════════════════════════════════════════════════════════

def test_15_linux_detector_aggregation():
    """TC15: LinuxDetector combines dpkg + snap, skips unavailable managers."""
    dpkg_data = "vim\t9.1.0-1\tVi IMproved\n"
    snap_data = "Name  Version  Rev  Tracking  Publisher\ncode  1.96.0   178  latest    vscode✓\n"

    def fake_has(binary):
        return binary in ("dpkg", "dpkg-query", "snap")

    def fake_run(cmd, **kw):
        if "dpkg-query" in cmd:
            return _mock_run(dpkg_data)
        if "snap" in cmd:
            return _mock_run(snap_data)
        return _mock_run_fail()

    with patch("app_detector.platforms.linux._has", side_effect=fake_has):
        with patch("app_detector.platforms.linux.subprocess.run", side_effect=fake_run):
            detector = LinuxDetector()
            apps = detector.scan()

    assert len(apps) == 2
    sources = {a.source for a in apps}
    assert sources == {"apt", "snap"}


# ═══════════════════════════════════════════════════════════════════════════
# TEST 16: LinuxDetector with NO managers available
# ═══════════════════════════════════════════════════════════════════════════

def test_16_linux_detector_no_managers():
    """TC16: System where no package manager binary is found."""
    with patch("app_detector.platforms.linux._has", return_value=False):
        detector = LinuxDetector()
        apps = detector.scan()
    assert apps == []


# ═══════════════════════════════════════════════════════════════════════════
# TEST 17: LinuxInstaller generates correct apt commands
# ═══════════════════════════════════════════════════════════════════════════

def test_17_linux_installer_apt_latest():
    """TC17: Install command for apt package targeting latest."""
    app = AppEntry(name="firefox", package_id="firefox", version="128.0", source="apt", target_version="latest")
    installer = LinuxInstaller()
    cmd = installer.install_command(app)
    assert cmd == ["sudo", "apt", "install", "-y", "firefox"]


def test_18_linux_installer_apt_same_version():
    """TC18: Install command for apt with pinned version."""
    app = AppEntry(name="firefox", package_id="firefox", version="128.0", source="apt", target_version="same")
    installer = LinuxInstaller()
    cmd = installer.install_command(app)
    assert cmd == ["sudo", "apt", "install", "-y", "firefox=128.0"]


# ═══════════════════════════════════════════════════════════════════════════
# TEST 19: LinuxInstaller snap with channel
# ═══════════════════════════════════════════════════════════════════════════

def test_19_linux_installer_snap_with_channel():
    """TC19: snap install command includes --channel from metadata."""
    app = AppEntry(
        name="code", package_id="code", version="1.96.0", source="snap",
        target_version="latest", metadata={"channel": "latest/stable"},
    )
    installer = LinuxInstaller()
    cmd = installer.install_command(app)
    assert "--channel" in cmd
    assert "latest/stable" in cmd


# ═══════════════════════════════════════════════════════════════════════════
# TEST 20: LinuxInstaller flatpak
# ═══════════════════════════════════════════════════════════════════════════

def test_20_linux_installer_flatpak():
    """TC20: flatpak install command for a GIMP entry."""
    app = AppEntry(name="GIMP", package_id="org.gimp.GIMP", version="2.10.38", source="flatpak")
    installer = LinuxInstaller()
    cmd = installer.install_command(app)
    assert cmd == ["flatpak", "install", "-y", "org.gimp.GIMP"]


# ═══════════════════════════════════════════════════════════════════════════
# TEST 21: LinuxInstaller dnf with version
# ═══════════════════════════════════════════════════════════════════════════

def test_21_linux_installer_dnf_pinned():
    """TC21: dnf install with pinned version string."""
    app = AppEntry(name="golang", package_id="golang", version="1.23.4", source="dnf", target_version="same")
    installer = LinuxInstaller()
    cmd = installer.install_command(app)
    assert cmd == ["sudo", "dnf", "install", "-y", "golang-1.23.4"]


# ═══════════════════════════════════════════════════════════════════════════
# TEST 22: LinuxInstaller pacman
# ═══════════════════════════════════════════════════════════════════════════

def test_22_linux_installer_pacman():
    """TC22: pacman install command (no version pinning)."""
    app = AppEntry(name="neovim", package_id="neovim", version="0.10.3", source="pacman")
    installer = LinuxInstaller()
    cmd = installer.install_command(app)
    assert cmd == ["sudo", "pacman", "-S", "--noconfirm", "neovim"]


# ═══════════════════════════════════════════════════════════════════════════
# TEST 23: LinuxInstaller unknown source
# ═══════════════════════════════════════════════════════════════════════════

def test_23_linux_installer_unknown_source():
    """TC23: Installer returns echo fallback for unknown source."""
    app = AppEntry(name="mystery", package_id="mystery", version="1.0", source="alien-manager")
    installer = LinuxInstaller()
    cmd = installer.install_command(app)
    assert cmd[0] == "echo"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 24: dpkg with 500+ imaginary packages (stress test)
# ═══════════════════════════════════════════════════════════════════════════

def test_24_dpkg_large_output():
    """TC24: Stress test — 500 imaginary dpkg packages."""
    lines = [f"pkg-{i}\t{i}.0.0-1\tImaginary package {i}" for i in range(500)]
    output = "\n".join(lines)
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run(output)):
        apps = _scan_dpkg()
    assert len(apps) == 500
    assert apps[499].name == "pkg-499"
    assert apps[0].version == "0.0.0-1"


# ═══════════════════════════════════════════════════════════════════════════
# TEST 25: LinuxInstaller.install success path
# ═══════════════════════════════════════════════════════════════════════════

def test_25_linux_installer_install_success():
    """TC25: Simulated successful install of a package."""
    app = AppEntry(name="cowsay", package_id="cowsay", version="3.03+dfsg2-8", source="apt")
    installer = LinuxInstaller()
    with patch("app_detector.platforms.linux.subprocess.run", return_value=_mock_run("done")):
        result = installer.install(app, silent=True)
    assert result is True
