"""The Electron shell handoff: discovery, argv, and the `charta open` view choice.

These run without a display — they assert that Python finds the desktop app and
launches it correctly, which is the part `charta open` owns. The window itself is
covered by `npm run smoke` under a real Electron.
"""
from __future__ import annotations

import pathlib
import time

import pytest

from charta.core import applog
from charta.core.config import AppConfig
from charta.shell import desktop, electron


@pytest.fixture
def app_dir(tmp_path) -> pathlib.Path:
    """A minimal Electron app: main.js plus a packaged executable."""
    (tmp_path / "main.js").write_text("// entry\n")
    (tmp_path / "Charta.exe").write_text("")
    return tmp_path


def test_desktop_dir_prefers_the_env_override(monkeypatch, app_dir):
    monkeypatch.setenv("CHARTA_DESKTOP", str(app_dir))
    assert electron.desktop_dir() == app_dir
    assert electron.available()


def test_desktop_dir_is_none_without_an_entry_point(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARTA_DESKTOP", str(tmp_path))  # no main.js
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(electron, "REPO_DESKTOP", tmp_path / "missing")
    assert electron.desktop_dir() is None
    assert electron.available() is False


def test_command_uses_the_packaged_binary_without_a_script_argument(app_dir):
    argv = electron.command(port=8123, folder=r"C:\Users\me\My Folder",
                            debug=True, app=app_dir)
    assert argv is not None
    assert pathlib.Path(argv[0]).name in ("Charta.exe", "Charta")
    # A packaged app is not `electron .`, so no "." is passed.
    assert "." not in argv[1:]
    assert "--port=8123" in argv
    assert "--folder=C:\\Users\\me\\My Folder" in argv and argv[-1] == "--debug"


def test_command_prefers_the_real_electron_binary_over_the_shim(app_dir, monkeypatch):
    shim = app_dir / "node_modules" / ".bin" / "electron"
    shim.parent.mkdir(parents=True)
    shim.write_text("#!/bin/sh\n")  # .cmd-style shim: not runnable by CreateProcess
    real = app_dir / "node_modules" / "electron" / "dist" / "electron"
    real.parent.mkdir(parents=True)
    real.write_text("")
    (app_dir / "Charta.exe").unlink()
    assert electron.electron_bin(app_dir) == str(real)
    argv = electron.command(port=1, app=app_dir)
    assert argv is not None and argv[0] == str(real) and argv[1] == "."


def test_command_is_none_when_electron_binary_is_missing(app_dir):
    """A present shell folder without Electron means fall back, never npx-hang."""
    (app_dir / "Charta.exe").unlink()
    assert electron.command(port=9, app=app_dir) is None
    hint = electron.install_hint(app_dir)
    assert "npm install" in hint and "node_modules" in hint


def test_run_opens_electron_without_starting_a_second_backend(monkeypatch, tmp_path, capsys):
    """The shell owns the backend; the launcher must not bind the port itself."""
    app_dir = tmp_path / "desktop"
    app_dir.mkdir()
    (app_dir / "main.js").write_text("// entry\n")
    (app_dir / "Charta.exe").write_text("")
    monkeypatch.setenv("CHARTA_DESKTOP", str(app_dir))
    monkeypatch.setenv("CHARTA_STATE_DIR", str(tmp_path / "state"))

    launched: dict = {}

    class FakeChild:
        pid = 4242

        def poll(self):
            # After the first poll, say the window stayed up
            if FakeChild.calls > 0:
                return 0
            FakeChild.calls += 1
            return None

    FakeChild.calls = 0
    child = FakeChild()

    def fake_launch(port, folder="", debug=False, app=None, log_file=None):
        launched.update(port=port, folder=folder, app=app)
        return child

    def explode(*_args, **_kwargs):
        raise AssertionError("desktop.run() must not start uvicorn in Electron mode")

    monkeypatch.setattr(electron, "launch", fake_launch)
    monkeypatch.setattr(desktop, "wait_ready", lambda *a, **k: True)
    monkeypatch.setattr(desktop, "health_ok", lambda *a, **k: True)
    monkeypatch.setattr(desktop, "_serve_in_thread", explode)

    cfg = AppConfig(state_dir=str(tmp_path / "state"), port=0)
    out = desktop.run(cfg, str(tmp_path / "watched"))
    assert out == 0
    assert launched["port"] > 0 and launched["folder"] == str(tmp_path / "watched")
    assert "Opening the Charta window" in capsys.readouterr().out
    # The session records the window, not a hidden in-process server.
    assert applog.read_session(cfg) == {}  # cleared on exit


def test_run_falls_back_to_the_browser_when_the_window_dies_instantly(monkeypatch, tmp_path, capsys):
    app_dir = tmp_path / "desktop"
    app_dir.mkdir()
    (app_dir / "main.js").write_text("// entry\n")
    (app_dir / "Charta.exe").write_text("")
    monkeypatch.setenv("CHARTA_DESKTOP", str(app_dir))
    monkeypatch.setenv("CHARTA_STATE_DIR", str(tmp_path / "state"))

    class Dead:
        pid = 1

        def poll(self):
            return 3  # crashed before the window ever appeared

    monkeypatch.setattr(electron, "launch", lambda **kw: Dead())
    monkeypatch.setattr(desktop, "wait_ready", lambda *a, **k: False)
    monkeypatch.setattr(desktop, "health_ok", lambda *a, **k: False)
    monkeypatch.setattr(desktop, "_serve_in_thread", lambda *a, **k: None)
    monkeypatch.setattr(desktop.webbrowser, "open", lambda url, *a, **k: opened.append(url))
    opened: list[str] = []
    monkeypatch.setattr(desktop, "_keep_alive", lambda: 0)

    cfg = AppConfig(state_dir=str(tmp_path / "state"), port=0)
    assert desktop.run(cfg) == 0  # the browser kept the UI alive
    assert opened and opened[0].startswith("http://127.0.0.1:")
    assert "closed before it was ready" in capsys.readouterr().out


def test_run_skips_electron_when_the_browser_was_requested(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARTA_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(electron, "desktop_dir", lambda: pathlib.Path("/nope"))
    started: list[str] = []
    monkeypatch.setattr(desktop, "_serve_in_thread", lambda *a, **k: started.append("uvicorn"))
    monkeypatch.setattr(desktop, "wait_ready", lambda *a, **k: True)
    monkeypatch.setattr(desktop.webbrowser, "open", lambda *a, **k: None)
    monkeypatch.setattr(desktop, "_keep_alive", lambda: 0)

    cfg = AppConfig(state_dir=str(tmp_path / "state"), port=0)
    assert desktop.run(cfg, browser_only=True) == 0
    assert started == ["uvicorn"]  # browser mode keeps the in-process server


def test_launch_sets_up_a_process_group(monkeypatch, app_dir, tmp_path):
    seen: dict = {}

    class FakePopen:
        def __init__(self, argv, **kwargs):
            seen["argv"], seen["kwargs"] = argv, kwargs

    monkeypatch.setattr(electron.subprocess, "Popen", FakePopen)
    child = electron.launch(port=8123, folder=str(tmp_path), app=app_dir)
    assert isinstance(child, FakePopen)
    assert seen["kwargs"]["cwd"] == str(app_dir)
    # The shell must spawn the launcher's own interpreter, not PATH's `python`.
    assert seen["kwargs"]["env"]["CHARTA_PYTHON"] == electron.sys.executable
    if electron.sys.platform == "win32":
        assert "creationflags" in seen["kwargs"]
    else:
        assert seen["kwargs"]["start_new_session"] is True


def test_launch_returns_none_when_there_is_no_app(monkeypatch):
    monkeypatch.setattr(electron, "desktop_dir", lambda: None)
    assert electron.launch(port=8123) is None


def test_electron_module_is_reachable_from_the_cli():
    """`charta open` is the Explorer entry point, so it must know the shell."""
    from charta import cli

    parser = cli.build_parser()
    args = parser.parse_args(["open", "."])
    assert args.browser is False and args.fn is cli.cmd_open


def test_wait_ready_timeout_is_bounded(monkeypatch):
    """A dead port must return False quickly instead of hanging the launcher."""
    started = time.time()
    assert desktop.wait_ready("127.0.0.1", 1, timeout=0.4) is False
    assert time.time() - started < 5

def test_the_desktop_shell_knows_every_screen_the_server_serves():
    """The Electron window renders the server's pages, so both must know the
    same routes — otherwise the smoke run and the screenshots miss a screen."""
    from charta.web.app import NAV_ITEMS

    source = (electron.REPO_DESKTOP / "main.js").read_text(encoding="utf-8")
    for item in NAV_ITEMS:
        assert f"/{item}" in source, f"main.js does not know the /{item} screen"
