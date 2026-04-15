"""Tests for the Manifest class."""

import json
import tempfile
from pathlib import Path

from app_detector.core.manifest import Manifest
from app_detector.models.app_entry import AppEntry


def _sample_app(**overrides) -> AppEntry:
    defaults = dict(
        name="TestApp",
        package_id="testapp",
        version="1.0.0",
        source="apt",
    )
    defaults.update(overrides)
    return AppEntry(**defaults)


# ── Round-trip serialisation ────────────────────────────────────────────────

def test_manifest_json_roundtrip():
    apps = [_sample_app(), _sample_app(name="Other", package_id="other")]
    m = Manifest.create(apps, _fake_platform())
    text = m.to_json()
    m2 = Manifest.from_json(text)

    assert len(m2.apps) == 2
    assert m2.apps[0].name == "TestApp"
    assert m2.schema_version == m.schema_version


def test_manifest_file_roundtrip(tmp_path: Path):
    apps = [_sample_app()]
    m = Manifest.create(apps, _fake_platform())
    out = tmp_path / "test.json"
    m.save(out)
    m2 = Manifest.load(out)
    assert m2.apps[0].package_id == "testapp"


# ── Merge ───────────────────────────────────────────────────────────────────

def test_manifest_merge_deduplicates():
    a = Manifest.create([_sample_app()], _fake_platform())
    b = Manifest.create(
        [_sample_app(), _sample_app(name="New", package_id="new")],
        _fake_platform(),
    )
    merged = Manifest.merge(a, b)
    assert len(merged.apps) == 2  # testapp + new, no duplicate


def test_manifest_merge_keeps_all_unique():
    a = Manifest.create([_sample_app(package_id="a")], _fake_platform())
    b = Manifest.create([_sample_app(package_id="b")], _fake_platform())
    merged = Manifest.merge(a, b)
    assert len(merged.apps) == 2


# ── Schema validation ──────────────────────────────────────────────────────

def test_from_dict_missing_fields():
    data = {"apps": [{"name": "X", "package_id": "x", "version": "1", "source": "apt"}]}
    m = Manifest.from_dict(data)
    assert len(m.apps) == 1
    assert m.schema_version == "1.0"


# ── Selected apps ──────────────────────────────────────────────────────────

def test_selected_apps():
    apps = [
        _sample_app(is_selected=True),
        _sample_app(name="Skip", package_id="skip", is_selected=False),
    ]
    m = Manifest.create(apps, _fake_platform())
    assert len(m.selected_apps) == 1


# ── Helper ──────────────────────────────────────────────────────────────────

def _fake_platform():
    from app_detector.utils.platform_detect import PlatformInfo
    return PlatformInfo(family="linux", distro="TestOS 1.0", hostname="test")
