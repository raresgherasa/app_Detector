"""Tests for Linux classification and signal parsing (with mocked commands)."""

from app_detector.models import Kind
from app_detector.scanners import linux


# ── classify() ───────────────────────────────────────────────────────────────

def test_classify_desktop_app_wins():
    assert linux.classify("firefox", "web", True) is Kind.APP


def test_classify_library_by_section():
    assert linux.classify("libssl3", "libs", False) is Kind.LIBRARY
    assert linux.classify("fonts-dejavu", "fonts", False) is Kind.LIBRARY


def test_classify_library_by_name():
    assert linux.classify("libfoo", "misc", False) is Kind.LIBRARY
    assert linux.classify("python3-requests", "python", False) is Kind.LIBRARY
    assert linux.classify("gcc-13", "devel", False) is Kind.TOOL  # not a lib pattern
    assert linux.classify("something-dev", "devel", False) is Kind.LIBRARY


def test_classify_tool_default():
    assert linux.classify("git", "vcs", False) is Kind.TOOL
    assert linux.classify("htop", "utils", False) is Kind.TOOL


def test_classify_locale_data_is_library():
    # Dictionaries / input-method tables are data, not tools the user runs.
    assert linux.classify("hunspell-en-gb", "text", False) is Kind.LIBRARY
    assert linux.classify("wbritish", "text", False) is Kind.LIBRARY
    assert linux.classify("ibus-table-cangjie3", "utils", False) is Kind.LIBRARY
    assert linux.classify("m17n-db", "utils", False) is Kind.LIBRARY


def test_classify_section_with_component_prefix():
    # apt sections can be "universe/libs"
    assert linux.classify("libx", "universe/libs", False) is Kind.LIBRARY


# ── manual / desktop set parsing (mock run) ──────────────────────────────────

def test_manual_set_parses(monkeypatch):
    monkeypatch.setattr(linux, "run", lambda *a, **k: "firefox\ngit\nhtop")
    assert linux._manual_set() == {"firefox", "git", "htop"}


def test_scan_dpkg_priority_excludes_base_system(monkeypatch):
    # apt-mark marks all three "manual", but Priority reveals the base ones.
    rows = "\n".join([
        # name  ver  size  section  priority  summary
        "git\t2.0\t100\tvcs\toptional\tVersion control",
        "grep\t3.0\t50\tutils\trequired\tGNU grep",
        "wget\t1.0\t40\tweb\tstandard\tretriever",
        "shim-signed\t1\t10\tadmin\toptional\tboot shim",  # excluded by prefix
    ])

    class _R:
        returncode = 0
        stdout = rows
    monkeypatch.setattr(linux, "_has", lambda _b: True)
    monkeypatch.setattr(linux.subprocess, "run", lambda *a, **k: _R())
    monkeypatch.setattr(linux, "_manual_set",
                        lambda: {"git", "grep", "wget", "shim-signed"})
    monkeypatch.setattr(linux, "_desktop_app_info", lambda: {})

    by_name = {e.package_id: e for e in linux._scan_dpkg()}
    assert "shim-signed" not in by_name              # boot infra dropped entirely
    assert by_name["git"].manual is True             # genuine user install
    assert by_name["grep"].manual is False           # required → base system
    assert by_name["wget"].manual is False           # standard → base system


def test_desktop_app_info_maps_pkg_to_friendly_name(monkeypatch):
    out = ("firefox: /usr/share/applications/firefox.desktop\n"
           "gimp, gimp-data: /usr/share/applications/gimp.desktop")
    monkeypatch.setattr(linux.os, "listdir",
                        lambda _p: ["firefox.desktop", "gimp.desktop"])
    monkeypatch.setattr(linux, "run", lambda *a, **k: out)
    monkeypatch.setattr(linux, "_read_desktop_entry", lambda p: {
        "/usr/share/applications/firefox.desktop": ("Firefox", "firefox", False),
        "/usr/share/applications/gimp.desktop":
            ("GNU Image Manipulation Program", "gimp", False),
    }[p])
    info = linux._desktop_app_info()
    # Each launcher maps to its first (owning) package, not data sub-packages.
    assert info == {"firefox": ("Firefox", "firefox"),
                    "gimp": ("GNU Image Manipulation Program", "gimp")}
    assert "gimp-data" not in info


def test_prettify_strips_suffix_and_titlecases():
    assert linux._prettify("google-chrome-stable") == "Google Chrome"
    assert linux._prettify("sublime-text") == "Sublime Text"
    assert linux._prettify("htop") == "Htop"


def test_flatpak_size_parsing():
    assert linux._parse_flatpak_size("1.2 GB") == int(1.2 * 1024**3)
    assert linux._parse_flatpak_size("500 MB") == 500 * 1024**2
    assert linux._parse_flatpak_size("") == 0


# ── catch-all desktop scanner (manually-installed apps) ──────────────────────

def test_install_root_opt_and_home(monkeypatch):
    monkeypatch.setattr(linux.os.path, "expanduser", lambda _p: "/home/u")
    # /opt install: collapse to the top-level product dir.
    assert linux._install_root("/opt/antigravity/antigravity %U") == "/opt/antigravity"
    # Home install with a quoted path + field codes.
    assert linux._install_root('"/home/u/Visual_Paradigm/bin/vp" %U') == \
        "/home/u/Visual_Paradigm"


def test_install_root_rejects_shared_and_generic_dirs(monkeypatch):
    monkeypatch.setattr(linux.os.path, "expanduser", lambda _p: "/home/u")
    assert linux._install_root("/usr/bin/foo") == ""          # shared bin
    assert linux._install_root("/home/u/.config/x/run") == "" # hidden dir
    assert linux._install_root("/home/u/Desktop/launch") == ""  # generic folder
    assert linux._install_root("") == ""


def test_xdg_dirs_skip_snap_sandbox(monkeypatch):
    monkeypatch.setattr(linux.os.path, "expanduser", lambda _p: "/home/u")
    monkeypatch.setenv("XDG_DATA_HOME", "/home/u/snap/code/9/.local/share")
    monkeypatch.setenv("XDG_DATA_DIRS", "/snap/code/9/usr/share:/usr/share")
    dirs = linux._xdg_app_dirs()
    # Canonical user dir is always present; snap sandbox dirs are dropped.
    assert "/home/u/.local/share/applications" in dirs
    assert not any("/snap/" in d for d in dirs)


def test_pm_relauncher_detected():
    # User copy of a snap launcher tweaked for the discrete GPU.
    assert linux._is_pm_relauncher(
        "env __NV_PRIME_RENDER_OFFLOAD=1 snap run launcher-ot-minecraft")
    assert linux._is_pm_relauncher("/snap/bin/foo %U")
    assert linux._is_pm_relauncher("flatpak run org.foo.Bar")
    # A genuine standalone binary is not a re-launcher.
    assert not linux._is_pm_relauncher("/opt/antigravity/antigravity %U")


def test_dpkg_owned_parses_stdout(monkeypatch):
    class _R:
        stdout = ("foo: /usr/share/applications/foo.desktop\n"
                  "bar, bar-data: /usr/share/applications/bar.desktop")
    monkeypatch.setattr(linux, "_has", lambda _b: True)
    monkeypatch.setattr(linux.subprocess, "run", lambda *a, **k: _R())
    owned = linux._dpkg_owned(["/usr/share/applications/foo.desktop",
                               "/usr/share/applications/bar.desktop",
                               "/home/u/.local/share/applications/orphan.desktop"])
    assert owned == {"/usr/share/applications/foo.desktop",
                     "/usr/share/applications/bar.desktop"}
