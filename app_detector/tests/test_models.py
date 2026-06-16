"""Tests for the core model, filter logic, and the live-filter engine."""

from app_detector.filtering import apply_filter, total_size
from app_detector.models import (
    AppEntry, Kind, ScanFilter, SizeTier, human_size,
)

MB = 1024 * 1024
GB = 1024 * MB


def _app(name, size, kind, manual):
    return AppEntry(name=name, package_id=name, kind=kind,
                    size_bytes=size, manual=manual)


def _dataset():
    return [
        _app("firefox", 250 * MB, Kind.APP, True),
        _app("git", 30 * MB, Kind.TOOL, True),
        _app("libssl3", 5 * MB, Kind.LIBRARY, False),
        _app("steam", 3 * GB, Kind.APP, True),
        _app("autodep", 12 * MB, Kind.TOOL, False),     # pulled-in dependency
    ]


def test_human_size():
    assert human_size(0) == "0 B"
    assert human_size(512) == "512 B"
    assert human_size(int(1.5 * GB)) == "1.5 GB"


def test_default_filter_hides_libs_and_deps():
    flt = ScanFilter()  # apps + tools, manual only
    view = apply_filter(_dataset(), flt)
    names = [a.name for a in view]
    assert "firefox" in names and "git" in names and "steam" in names
    assert "libssl3" not in names   # library hidden
    assert "autodep" not in names   # auto-installed dep hidden


def test_view_sorted_by_size_desc():
    view = apply_filter(_dataset(), ScanFilter())
    sizes = [a.size_bytes for a in view]
    assert sizes == sorted(sizes, reverse=True)
    assert view[0].name == "steam"


def test_size_tier_large_and_huge():
    large = apply_filter(_dataset(), ScanFilter(min_size_bytes=SizeTier.LARGE.value))
    assert [a.name for a in large] == ["steam", "firefox"]
    huge = apply_filter(_dataset(), ScanFilter(min_size_bytes=SizeTier.HUGE.value))
    assert [a.name for a in huge] == ["steam"]


def test_include_libraries_and_all_packages():
    flt = ScanFilter(kinds={Kind.APP, Kind.TOOL, Kind.LIBRARY}, manual_only=False)
    assert len(apply_filter(_dataset(), flt)) == 5


def test_filter_from_options():
    flt = ScanFilter.from_options(tier=SizeTier.LARGE)
    assert flt.min_size_bytes == SizeTier.LARGE.value
    assert flt.kinds == {Kind.APP, Kind.TOOL}
    assert flt.manual_only is True


def test_total_size():
    assert total_size(_dataset()) == 250 * MB + 30 * MB + 5 * MB + 3 * GB + 12 * MB


def test_entry_roundtrip_preserves_kind():
    a = _app("firefox", 250 * MB, Kind.APP, True)
    b = AppEntry.from_dict(a.to_dict())
    assert b.kind is Kind.APP and b.size_bytes == 250 * MB and b.manual is True
