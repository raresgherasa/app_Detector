"""The GUI restore worker is wired to resolution + verification + config replay.

The worker normally marshals every UI update through ``self.after`` on the Tk
thread; here a stub runs callbacks inline so the logic is testable headlessly
(no window, no real installs, no real git writes).
"""

import app_detector.gui.app as gui
from app_detector.gui.app import AppDetectorGUI
from app_detector.manifest import Manifest
from app_detector.models import AppEntry, Kind
from app_detector.platform_detect import PlatformInfo


class _FakeInstaller:
    def __init__(self, present):
        self.present = present
        self.streamed: list[str] = []

    def install_command(self, app):
        return ["echo", app.package_id]

    def install_streamed(self, app, on_line):
        self.streamed.append(f"{app.source}:{app.package_id}")
        on_line(f"$ {app.package_id}\n")
        return app.package_id != "code"        # pretend 'code' fails

    def is_installed(self, app):
        return self.present.get(app.package_id)  # None when absent → unknown


class _FakeConsole:
    def __init__(self):
        self.text = ""

    def write(self, t):
        self.text += t

    def set_status(self, t):
        pass


class _FakeSelf:
    """Stand-in for the window: runs after() callbacks inline."""

    def after(self, _ms, fn, *a):
        fn(*a)

    def _restore_done(self, ok, total, console):
        self.done = (ok, total)


def _winget(name, pid):
    return AppEntry(name=name, package_id=pid, source="winget", kind=Kind.APP)


def test_gui_worker_resolves_verifies_and_replays(monkeypatch):
    monkeypatch.setattr(gui, "platform_info",
                        PlatformInfo(family="linux",
                                         available_managers=["apt"]))
    inst = _FakeInstaller(present={"firefox": True, "code": False})
    monkeypatch.setattr(gui, "get_installer", lambda: inst)

    replayed = {}
    monkeypatch.setattr(gui.config_capture, "restore_all",
                        lambda cfg, on_line=None: replayed.update(cfg) or {})

    selected = [
        _winget("Firefox", "Mozilla.Firefox"),          # → apt firefox (verified)
        _winget("VS Code", "Microsoft.VisualStudioCode"),  # → apt code (fails)
        _winget("Acme", "Acme.PrivateTool"),            # no alias → skipped
    ]
    fs = _FakeSelf()
    fs.loaded_manifest = Manifest(configs={"git_config": {"user.name": "Ada"}})
    console = _FakeConsole()

    AppDetectorGUI._restore_worker(fs, selected, console)

    # Cross-manager resolution: winget ids became apt package ids.
    assert inst.streamed == ["apt:firefox", "apt:code"]
    # Unresolvable app skipped, not installed.
    assert "skipped" in console.text and "Acme" in console.text
    # Verification: firefox verified ok, code failed → 1 of 2.
    assert fs.done == (1, 2)
    assert "installed & verified" in console.text
    # Config replay fired with the manifest's captured config.
    assert replayed == {"git_config": {"user.name": "Ada"}}


def test_gui_worker_unknown_verification_trusts_exit_code(monkeypatch):
    monkeypatch.setattr(gui, "platform_info",
                        PlatformInfo(family="linux",
                                         available_managers=["apt"]))
    inst = _FakeInstaller(present={})        # is_installed → None for everything
    monkeypatch.setattr(gui, "get_installer", lambda: inst)
    monkeypatch.setattr(gui.config_capture, "restore_all",
                        lambda cfg, on_line=None: {})

    fs = _FakeSelf()
    fs.loaded_manifest = None                # no configs to replay
    console = _FakeConsole()
    AppDetectorGUI._restore_worker(
        fs, [AppEntry(name="git", package_id="git", source="apt", kind=Kind.TOOL)],
        console)
    # Can't verify → trust the (successful) exit code.
    assert fs.done == (1, 1)
