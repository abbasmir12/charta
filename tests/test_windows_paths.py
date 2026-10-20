"""Windows seams that must be right the first time — testable without Windows.

These cover the defects that would only surface on a real Windows box: an
unquoted Explorer command, a truncated 64-bit handle, kwargs an older pywebview
rejects, and a doctor report that lies about readiness.
"""
from __future__ import annotations

import pathlib

from charta.core.config import AppConfig
from charta.core.doctor import Check, format_report, report_json, run_checks, verdict
from charta.shell import desktop, windows_registry
from charta.shell.windows_registry import KEYS, _launcher, right_click_command


def test_explorer_command_quotes_everything():
    """`C:\\Program Files\\...` must survive; %1/%V stay inside quotes."""
    launcher = '"C:\\Program Files\\Python\\Scripts\\charta.exe"'
    cmd = right_click_command("%1", launcher)
    assert cmd == '"C:\\Program Files\\Python\\Scripts\\charta.exe" open "%1"'
    assert right_click_command("%V", launcher).endswith('open "%V"')


def test_explorer_command_covers_both_registry_entries():
    assert any("Background" in key for key in KEYS)
    assert any("Background" not in key for key in KEYS)


def test_watched_query_targets_the_exact_folder():
    from charta.shell.windows_registry import watched_query

    assert watched_query(r"C:\Users\me\Receipts") == 'System.ItemPathDisplay:"C:\\Users\\me\\Receipts"'
    assert watched_query("C:\\Users\\me\\Receipts\\") == 'System.ItemPathDisplay:"C:\\Users\\me\\Receipts"'


def test_watched_verb_is_stable_unique_and_key_safe():
    from charta.shell.windows_registry import WATCH_PREFIX, watched_verb

    name = watched_verb(r"C:\one")
    assert name.startswith(WATCH_PREFIX)
    assert name == watched_verb(r"C:\one")
    assert name != watched_verb(r"C:\two")
    assert " " not in watched_verb(r"C:\My Documents")  # valid as a registry key


def test_watch_markers_are_guarded_noops_off_windows():
    import sys

    from charta.shell import windows_registry as wr

    if sys.platform != "win32":
        assert wr.mark_watched(r"C:\x") == ""
        assert wr.sync_watched([r"C:\x"]) == 0
        wr.unmark_watched(r"C:\x")  # must never raise


def test_launcher_prefers_a_windowless_interpreter(monkeypatch, tmp_path):
    """A console launcher flashes a black window from Explorer; pythonw avoids it."""
    exe = tmp_path / "python.exe"
    exe.write_text("")
    (tmp_path / "pythonw.exe").write_text("")
    monkeypatch.setattr(windows_registry.sys, "executable", str(exe))
    launch = _launcher()
    assert launch.startswith(f'"{tmp_path / "pythonw.exe"}"')
    assert "from charta.cli import main" in launch


def test_launcher_is_quoted_and_cwd_independent():
    launch = _launcher()
    assert launch.startswith('"')  # spaces in the interpreter path must not split it
    assert launch.count('"') % 2 == 0  # balanced quoting, or the shell entry breaks
    assert "-m charta.cli" not in launch  # that form needs the repo as cwd
    root = str(pathlib.Path(__file__).resolve().parent.parent)
    if "-c " in launch:  # no console script installed in this environment
        assert root in launch and "from charta.cli import main" in launch


def test_pywebview_kwargs_are_filtered_to_the_signature():
    def older_create_window(title, url, width, height):
        pass

    kwargs = {"title": "Charta", "url": "http://x", "width": 100, "height": 50,
              "maximized": True, "background_color": "#0B0D12", "min_size": (480, 360)}
    assert desktop.supported_kwargs(older_create_window, kwargs) == {
        "title": "Charta", "url": "http://x", "width": 100, "height": 50}

    def newer_create_window(title, url, **rest):
        pass

    assert desktop.supported_kwargs(newer_create_window, kwargs) == kwargs


def test_window_kwargs_center_unsaved_window_on_the_os():
    geo = desktop.WindowGeometry(x=-1, y=-1, width=1280, height=800)
    kwargs = desktop.window_kwargs(geo, "Charta", "http://127.0.0.1:8123/")
    assert kwargs["x"] is None and kwargs["y"] is None  # -1 = "let Windows place it"
    saved = desktop.window_kwargs(desktop.WindowGeometry(x=10, y=20), "Charta", "u")
    assert (saved["x"], saved["y"]) == (10, 20)


def test_doctor_reports_readiness_without_raising(monkeypatch):
    monkeypatch.setenv("CHARTA_BASE_URL", "http://127.0.0.1:9/v1")  # closed port
    checks = run_checks(AppConfig.load())
    names = {c.name for c in checks}
    assert {"python", "config", "provider", "icon", "safety-guard"} <= names
    provider = next(c for c in checks if c.name == "provider")
    assert provider.ok is False  # nothing is listening on port 9
    assert "CHARTA_BASE_URL" in provider.hint or "ollama" in provider.hint.lower()
    assert next(c for c in checks if c.name == "safety-guard").ok is True
    assert next(c for c in checks if c.name == "icon").ok is True
    # optional gaps (e.g. no pywebview here) must not make the machine "not ready"
    assert verdict(checks) is False  # the provider genuinely is unreachable here
    assert verdict([c for c in checks if c.required and c.name != "provider"]) is True
    assert "Charta doctor" in format_report(checks)
    assert '"ready"' in report_json(checks)


def test_doctor_verdict_fails_only_on_required_checks():
    assert verdict([Check("a", True, "ok")]) is True
    assert verdict([Check("a", False, "bad")]) is False
    assert verdict([Check("opt", False, "missing", required=False)]) is True
    assert verdict([Check("opt", False, "missing", required=False), Check("req", False, "bad")]) is False
