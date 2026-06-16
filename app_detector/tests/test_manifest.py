"""Tests for manifest save/load/merge round-trips (schema 2.0)."""

from app_detector.manifest import SCHEMA_VERSION, Manifest
from app_detector.models import AppEntry, Kind, ScanFilter
from app_detector.platform_detect import PlatformInfo

MB = 1024 * 1024


def _apps():
    return [
        AppEntry("firefox", "firefox", "120.0", "apt", 250 * MB, Kind.APP, True),
        AppEntry("git", "git", "2.43", "apt", 30 * MB, Kind.TOOL, True),
    ]


def _info():
    return PlatformInfo("linux", "Ubuntu 24.04", "box", ["apt", "snap"])


def test_create_records_schema_filter_and_os():
    m = Manifest.create(_apps(), _info(), ScanFilter().to_dict())
    assert m.schema_version == SCHEMA_VERSION
    assert m.source_os["distro"] == "Ubuntu 24.04"
    assert m.filter["manual_only"] is True


def test_json_roundtrip_preserves_fields():
    m = Manifest.create(_apps(), _info(), ScanFilter().to_dict())
    m2 = Manifest.from_json(m.to_json())
    assert len(m2.apps) == 2
    a = m2.apps[0]
    assert a.name == "firefox" and a.kind is Kind.APP and a.size_bytes == 250 * MB


def test_file_roundtrip(tmp_path):
    m = Manifest.create(_apps(), _info())
    path = tmp_path / "snap.json"
    m.save(path)
    loaded = Manifest.load(path)
    assert [a.package_id for a in loaded.apps] == ["firefox", "git"]


def test_merge_dedups_by_id_and_source():
    a = Manifest.create(_apps(), _info())
    extra = _apps() + [AppEntry("vlc", "vlc", "3.0", "snap", 90 * MB, Kind.APP, True)]
    b = Manifest.create(extra, _info())
    merged = Manifest.merge(a, b)
    ids = sorted(x.package_id for x in merged.apps)
    assert ids == ["firefox", "git", "vlc"]
