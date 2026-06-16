"""Tests for classification overrides, live-diff comparison, and config capture."""

from app_detector import compare as compare_mod
from app_detector import config_capture, overrides
from app_detector.models import AppEntry, Kind


def _app(pid, kind=Kind.TOOL, source="apt"):
    return AppEntry(name=pid, package_id=pid, kind=kind, source=source)


# ── overrides ─────────────────────────────────────────────────────────────────

def test_overrides_roundtrip_and_apply(tmp_path, monkeypatch):
    monkeypatch.setattr(overrides, "_path", lambda: tmp_path / "ov.json")
    overrides.set_kind("docker.io", Kind.TOOL)
    assert overrides.load() == {"docker.io": Kind.TOOL}

    apps = [_app("docker.io", Kind.APP), _app("firefox", Kind.APP)]
    changed = overrides.apply(apps)
    assert changed == 1
    assert apps[0].kind is Kind.TOOL and apps[1].kind is Kind.APP


def test_overrides_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(overrides, "_path", lambda: tmp_path / "ov.json")
    overrides.set_kind("foo", Kind.APP)
    assert overrides.clear("foo") is True
    assert overrides.clear("foo") is False
    assert overrides.load() == {}


def test_overrides_ignores_invalid_kind(tmp_path, monkeypatch):
    p = tmp_path / "ov.json"
    p.write_text('{"foo": "nonsense", "bar": "tool"}')
    monkeypatch.setattr(overrides, "_path", lambda: p)
    assert overrides.load() == {"bar": Kind.TOOL}


# ── compare (powers diff --live) ──────────────────────────────────────────────

def test_compare_by_canonical_identity():
    snapshot = [_app("firefox", source="apt"), _app("git"), _app("steam-installer")]
    # Live machine has firefox via winget id, plus an extra app, missing the rest.
    live = [_app("Mozilla.Firefox", source="winget"), _app("htop")]
    cmp = compare_mod.compare(snapshot, live)
    only_a = {a.package_id for a in cmp.only_a}
    only_b = {a.package_id for a in cmp.only_b}
    common = {a.package_id for a in cmp.common}
    assert only_a == {"git", "steam-installer"}   # in snapshot, missing live
    assert only_b == {"htop"}                       # extra on live machine
    assert common == {"firefox"}                    # matched across managers


# ── config capture handlers ───────────────────────────────────────────────────

def test_vscode_capture_parses_extension_list(monkeypatch):
    h = config_capture.VSCodeExtensions()
    monkeypatch.setattr(config_capture, "run",
                        lambda *a, **k: "ms-python.python\nesbenp.prettier-vscode\n")
    assert h.capture() == ["ms-python.python", "esbenp.prettier-vscode"]


def test_vscode_capture_empty_returns_none(monkeypatch):
    h = config_capture.VSCodeExtensions()
    monkeypatch.setattr(config_capture, "run", lambda *a, **k: "")
    assert h.capture() is None


def test_gitconfig_capture_parses_keyvalues(monkeypatch):
    h = config_capture.GitConfig()
    monkeypatch.setattr(config_capture, "run",
                        lambda *a, **k: "user.name=Ada\nuser.email=ada@x.io")
    assert h.capture() == {"user.name": "Ada", "user.email": "ada@x.io"}


def test_capture_all_skips_unavailable(monkeypatch):
    monkeypatch.setattr(config_capture.VSCodeExtensions, "is_available",
                        lambda self: True)
    monkeypatch.setattr(config_capture.VSCodeExtensions, "capture",
                        lambda self: ["ms-python.python"])
    monkeypatch.setattr(config_capture.GitConfig, "is_available",
                        lambda self: False)
    out = config_capture.capture_all()
    assert out == {"vscode_extensions": ["ms-python.python"]}
