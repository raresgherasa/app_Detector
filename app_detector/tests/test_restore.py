"""Tests for restore planning, verification, and the report."""

from app_detector import restore as restore_mod
from app_detector.models import AppEntry, Kind
from app_detector.platform_detect import PlatformInfo
from app_detector.scanners.base import Installer


def _app(pid, source="apt"):
    return AppEntry(name=pid, package_id=pid, source=source, kind=Kind.APP)


class _FakeInstaller(Installer):
    """Records installs; verification driven by a name→presence map."""

    def __init__(self, install_ok=True, present=None):
        self.install_ok = install_ok
        self.present = present or {}
        self.installed: list[str] = []

    def install_command(self, app):
        return ["echo", app.package_id]

    def install(self, app, silent=True):
        self.installed.append(app.package_id)
        return self.install_ok

    def is_installed(self, app):
        return self.present.get(app.package_id)


def _linux(managers=("apt",)):
    return PlatformInfo(family="linux", available_managers=list(managers))


def test_plan_splits_resolvable_and_unresolved():
    apps = [_app("firefox", "apt"), _app("Acme.PrivateTool", "winget")]
    resolvable, unresolved = restore_mod.plan(apps, _linux())
    assert [r[0].package_id for r in resolvable] == ["firefox"]
    assert [a.package_id for a in unresolved] == ["Acme.PrivateTool"]


def test_run_verified_success():
    inst = _FakeInstaller(install_ok=True, present={"firefox": True})
    report = restore_mod.run(inst, [_app("firefox")], _linux())
    assert len(report.ok) == 1 and not report.failed
    assert inst.installed == ["firefox"]


def test_run_install_ok_but_not_present_is_failure():
    # Package manager exits 0 but the app isn't actually there → caught.
    inst = _FakeInstaller(install_ok=True, present={"firefox": False})
    report = restore_mod.run(inst, [_app("firefox")], _linux())
    assert report.failed and not report.ok
    assert report.failed[0].installed is True
    assert report.failed[0].verified is False


def test_run_unknown_verification_trusts_exit_code():
    inst = _FakeInstaller(install_ok=True, present={})  # is_installed → None
    report = restore_mod.run(inst, [_app("firefox")], _linux())
    assert report.ok and report.ok[0].verified is None


def test_run_no_verify_skips_check():
    inst = _FakeInstaller(install_ok=False)
    report = restore_mod.run(inst, [_app("firefox")], _linux(), verify=False)
    assert report.failed  # install_ok False → failed, verification never consulted


def test_run_emits_events():
    inst = _FakeInstaller(present={"firefox": True})
    seen = []
    restore_mod.run(inst, [_app("firefox")], _linux(),
                    on_event=lambda stage, app: seen.append((stage, app.package_id)))
    assert seen == [("installing", "firefox"), ("ok", "firefox")]
