"""Read-only self-check behind `charta doctor`.

On a fresh Windows machine the interesting failures are environmental (no
provider running, pywebview missing, DWM unavailable, shell entry never
installed), not logical. This reports them in plain language so a run can be
diagnosed from one pasted block instead of a traceback.

Nothing here writes to the user's folders.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import struct
import sys
from dataclasses import dataclass

from . import config as config_mod
from .config import AppConfig
from .llm import LLMClient
from .paths import is_protected
from .sensitive import detect


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    hint: str = ""
    required: bool = True


def _module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _icon_check() -> Check:
    from ..shell.native_window import ICON_PATH  # local import keeps startup light

    if not ICON_PATH.exists():
        return Check("icon", False, f"missing {ICON_PATH}", "run: python3 tools/make_icon.py")
    try:
        reserved, kind, count = struct.unpack("<HHH", ICON_PATH.read_bytes()[:6])
        ok = (reserved, kind) == (0, 1) and count >= 1
        return Check("icon", ok, f"{ICON_PATH.name}: {count} sizes",
                     "" if ok else "regenerate: python3 tools/make_icon.py")
    except (OSError, struct.error) as e:
        return Check("icon", False, f"unreadable: {e}", "run: python3 tools/make_icon.py")


def _windows_checks() -> list[Check]:
    from ..shell.native_window import dwm_available

    checks = [Check("dwm", dwm_available(), "dwmapi loadable (dark title bar + Mica)")]
    try:
        import winreg

        found = 0
        for key in (r"Software\Classes\Directory\shell\Charta",
                    r"Software\Classes\Directory\Background\shell\Charta"):
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key):
                    found += 1
            except FileNotFoundError:
                pass
        checks.append(Check("shell-entry", found == 2, f"{found}/2 Explorer entries installed",
                            "run: charta install-shell", required=False))
    except ImportError:  # pragma: no cover - non-Windows
        pass
    return checks


def run_checks(cfg: AppConfig | None = None, *, ping: bool = True) -> list[Check]:
    """Collect every check. Never raises; a failed check is a reported item."""
    cfg = cfg or AppConfig.load()
    checks: list[Check] = []

    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    checks.append(Check("python", sys.version_info >= (3, 11), f"{version} on {sys.platform}",
                        "Charta needs Python 3.11+" if sys.version_info < (3, 11) else ""))

    path = config_mod.config_path()
    checks.append(Check("config", path.exists(), str(path),
                        "create config.toml at the repo root (see config.toml.example)"))

    provider_ok = bool(cfg.llm_provider and cfg.llm_base_url and cfg.generation_model)
    if not provider_ok:
        checks.append(Check("provider", False, "provider/base_url/model not set",
                            "fill in [llm] and [models] in config.toml"))
    elif ping:
        reachable = LLMClient(cfg).ping(timeout=2.0)
        checks.append(Check("provider", reachable,
                            f"{cfg.llm_provider} @ {cfg.llm_base_url} ({cfg.generation_model})",
                            "" if reachable else "start it (Ollama: `ollama serve`) or set "
                                                 "CHARTA_BASE_URL to a reachable endpoint"))
    else:
        checks.append(Check("provider", True, f"{cfg.llm_provider} configured (not pinged)"))

    checks.append(_icon_check())
    has_webview = _module("webview")
    checks.append(Check("window-host", has_webview,
                        "pywebview installed — native window + DWM polish"
                        if has_webview else "pywebview not installed — `charta open` uses your browser",
                        "" if has_webview else "pip install pywebview", required=False))

    extras = {name: _module(name) for name in ("fitz", "docx", "faster_whisper")}
    checks.append(Check("extras", any(extras.values()),
                        ", ".join(f"{k}={'yes' if v else 'no'}" for k, v in extras.items()),
                        "optional: PyMuPDF (PDF text), python-docx, faster-whisper (voice)",
                        required=False))

    guard_ok = is_protected("C:\\Windows") and not is_protected(str(pathlib.Path.home() / "Documents"))
    checks.append(Check("safety-guard", guard_ok, "protected-path refusal + sensitive scan active",
                        "" if guard_ok else "paths.py guard is not behaving — do not move files"))
    checks.append(Check("sensitive-scan", detect("card 4111 1111 1111 1111").sensitive,
                        "card/password patterns detected", required=False))

    state = cfg.state_path()
    checks.append(Check("state-dir", state.parent.exists(),
                        f"{state} (window geometry)", f"create {state.parent}", required=False))

    if sys.platform == "win32":
        checks.extend(_windows_checks())
    return checks


def verdict(checks: list[Check]) -> bool:
    """Ready when every required check passed (optional ones are advisory)."""
    return all(c.ok for c in checks if c.required)


def format_report(checks: list[Check]) -> str:
    lines = ["Charta doctor", "=" * 13]
    for check in checks:
        mark = "OK  " if check.ok else ("WARN" if not check.required else "FAIL")
        lines.append(f"[{mark}] {check.name:14} {check.detail}")
        if not check.ok and check.hint:
            lines.append(f"       └─ {check.hint}")
    report = "\n".join(lines)
    ready = verdict(checks)
    tail = ("Ready: yes — try `charta open ./your-folder`."
            if ready else "Ready: no — fix the FAIL lines above (WARN lines are optional).")
    return f"{report}\n\n{tail}"


def report_json(checks: list[Check]) -> str:
    """Machine-readable form (handy when pasting a report back for triage)."""
    return json.dumps({"ready": verdict(checks),
                       "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail,
                                   "hint": c.hint, "required": c.required} for c in checks]},
                      indent=2)
