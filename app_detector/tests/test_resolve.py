"""Tests for cross-manager restore resolution and canonical keys."""

from app_detector.models import AppEntry, Kind, canonical_key
from app_detector.platform_detect import PlatformInfo
from app_detector.resolve import resolve


def _app(package_id, source, **kw):
    return AppEntry(name=package_id, package_id=package_id, source=source, **kw)


def _info(family, managers):
    return PlatformInfo(family=family, available_managers=managers)


# ── canonical_key ─────────────────────────────────────────────────────────────

def test_canonical_strips_channel_suffix():
    assert canonical_key("google-chrome-stable") == "google-chrome"
    assert canonical_key("firefox") == "firefox"


def test_canonical_takes_vendor_id_tail():
    assert canonical_key("Mozilla.Firefox") == "firefox"
    assert canonical_key("Microsoft.VisualStudioCode") == "visualstudiocode"


def test_canonical_set_in_post_init():
    assert _app("google-chrome-stable", "apt").canonical == "google-chrome"


# ── resolve: exact (same manager present) ─────────────────────────────────────

def test_resolve_exact_when_source_manager_available():
    app = _app("firefox", "apt")
    resolved, conf = resolve(app, _info("linux", ["apt", "snap"]))
    assert conf == "exact" and resolved is app


# ── resolve: mapped via alias table ───────────────────────────────────────────

def test_resolve_maps_apt_to_winget():
    app = _app("firefox", "apt")
    resolved, conf = resolve(app, _info("windows", ["winget"]))
    assert conf == "mapped"
    assert resolved.source == "winget" and resolved.package_id == "Mozilla.Firefox"


def test_resolve_maps_winget_id_to_apt():
    app = _app("Mozilla.Firefox", "winget")
    resolved, conf = resolve(app, _info("linux", ["apt"]))
    assert conf == "mapped"
    assert resolved.source == "apt" and resolved.package_id == "firefox"


def test_resolve_prefers_apt_over_snap_on_linux():
    app = _app("Mozilla.Firefox", "winget")
    resolved, _ = resolve(app, _info("linux", ["snap", "apt", "flatpak"]))
    assert resolved.source == "apt"  # PLATFORM_SOURCES order wins


# ── resolve: guess for unknown but name-shareable packages ────────────────────

def test_resolve_guesses_plain_name():
    app = _app("ripgrep", "apt")  # not in ALIASES
    resolved, conf = resolve(app, _info("darwin", ["brew"]))
    assert conf == "guess"
    assert resolved.source == "brew-cask" and resolved.package_id == "ripgrep"


def test_resolve_unresolved_for_vendor_id_without_alias():
    app = _app("Acme.PrivateTool", "winget")  # dotted + no alias
    resolved, conf = resolve(app, _info("linux", ["apt"]))
    assert resolved is None and conf == "unresolved"


def test_resolve_unresolved_when_target_has_no_managers():
    app = _app("firefox", "apt")
    resolved, conf = resolve(app, _info("linux", []))
    assert resolved is None and conf == "unresolved"
