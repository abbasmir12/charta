#!/usr/bin/env python3
"""Drive the real UI in Chromium: measure it, then screenshot it.

Static checks (tests/test_design.py) prove the palette and tokens; this proves the
rendered result: one h1 per screen, no horizontal overflow, targets big enough to
click, chrome not selectable, content selectable, no console errors.

    python3 tools/ui_check.py [--out docs/screenshots] [--keep]

Requires: pip install playwright && python -m playwright install chromium
"""
from __future__ import annotations

import argparse
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent

METRICS = """() => {
  const visible = (e) => e.offsetParent !== null;
  const targets = [...document.querySelectorAll('button,a.btn,a,input,textarea,[role=tab]')].filter(visible);
  const rect = (e) => e.getBoundingClientRect();    return {
    title: document.title,
    h1: [...document.querySelectorAll('h1')].map(h => (h.textContent || '').trim()),
    h1Overflowing: [...document.querySelectorAll('h1')]
      .filter(h => rect(h).right > document.documentElement.clientWidth + 1).length,
    overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    smallTargets: targets.filter(e => rect(e).height > 0 && rect(e).height < 24)
      .map(e => ((e.textContent || e.getAttribute('aria-label') || e.tagName).trim().slice(0, 28)
                 + ' @' + rect(e).height.toFixed(0) + 'px')),
    bodySelect: getComputedStyle(document.body).userSelect,
    contentSelect: getComputedStyle(document.querySelector('.content') || document.body).userSelect,
    appbar: (() => { const b = document.querySelector('.appbar'); return b ? getComputedStyle(b).display : 'missing'; })(),
    hasLive: !!document.getElementById('thinking'),
  };
}"""

ROUTES = ["/", "/overview", "/review", "/outputs", "/gaps", "/ask", "/activity", "/settings", "/styleguide"]

# DESIGN.md promises the layout holds down to 900px wide, so measure there too.
PASSES = [("desktop", 1280, 800, ("dark", "light")), ("narrow", 900, 700, ("dark",))]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def demo_folder() -> pathlib.Path:
    """A folder with a charter and content, so screens are not empty."""
    sys.path.insert(0, str(ROOT))
    from charta.core.charter import preset_charter, save_charter

    folder = pathlib.Path(tempfile.mkdtemp(prefix="charta-ui-demo-"))
    charter = preset_charter("freelancer")
    charter.expected = ["electricity bill for each month (Jan..Dec)"]
    save_charter(folder, charter)
    (folder / "invoice_edf_2026-03-15.txt").write_text("date: 2026-03-15\ntotal: $42.00\nvendor: EDF\n")
    (folder / "receipt_rent_2026-03-01.txt").write_text("date: 2026-03-01\ntotal: $900.00\nvendor: Rent\n")
    (folder / "statement_2026-02.pdf.txt").write_text("statement total 120.00\n")
    return folder


def wait_for_health(url: str, timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=1.5) as resp:
                if resp.status < 500:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.25)
    return False


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Visual/layout check for the Charta UI")
    parser.add_argument("--out", default=str(ROOT / "docs" / "screenshots"))
    parser.add_argument("--keep", action="store_true", help="leave the server running")
    args = parser.parse_args(argv[1:])

    from playwright.sync_api import sync_playwright

    folder = demo_folder()
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [sys.executable, "-m", "charta.cli", "serve", "--port", str(port)],
        cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    try:
        if not wait_for_health(url):
            print(f"server did not start on {url}")
            return 1
        screens = 0
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for label, width, height, themes in PASSES:
                for theme in themes:
                    page = browser.new_page(viewport={"width": width, "height": height})
                    errors: list[str] = []
                    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.goto(url, wait_until="domcontentloaded")
                    page.evaluate("t => { localStorage.setItem('charta-theme', t); }", theme)
                    for route in ROUTES:
                        errors.clear()
                        page.goto(f"{url}{route}?folder={folder}", wait_until="networkidle")
                        page.wait_for_timeout(250)
                        m = page.evaluate(METRICS)
                        slug = route.strip("/") or "setup"
                        suffix = f"-{theme}" if label == "desktop" else f"-{label}-{theme}"
                        page.screenshot(path=str(out_dir / f"{slug}{suffix}.png"))
                        screens += 1
                        checks = {
                            "one h1": len(m["h1"]) == 1,
                            "h1 fits": m["h1Overflowing"] == 0,
                            "no h-overflow": m["overflowX"] <= 1,
                            "targets >=24px": not m["smallTargets"],
                            "appbar shown": m["appbar"] == "flex",
                            "live strip": m["hasLive"],
                            "no console errors": not errors,
                        }
                        if route == "/":
                            checks["chrome not selectable"] = m["bodySelect"] == "none"
                            checks["content selectable"] = m["contentSelect"] in ("text", "auto")
                        for name, ok in checks.items():
                            if ok:
                                continue
                            detail = ""
                            if name == "targets >=24px":
                                detail = f" {m['smallTargets']}"
                            if name == "no console errors":
                                detail = f" {errors[:2]}"
                            if name in ("one h1", "h1 fits"):
                                detail = f" {m['h1']}"
                            failures.append(f"{label}/{theme} {route}: {name}{detail}")
                        print(f"{label:7} {theme:5} {route:11} h1={len(m['h1'])} "
                              f"overflow={m['overflowX']} small={len(m['smallTargets'])} "
                              f"errors={len(errors)}")
                    page.close()
            browser.close()
    finally:
        if not args.keep:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()

    print(f"\nscreenshots: {out_dir}")
    if failures:
        print(f"FAIL ({len(failures)})")
        for line in failures:
            print(f"  - {line}")
        return 1
    print(f"OK — {screens} screens verified (desktop 1280px dark+light, narrow 900px dark)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
