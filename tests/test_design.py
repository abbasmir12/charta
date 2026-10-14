"""Design-system checks that need no browser.

"Looks professional" is not testable, but these are: WCAG contrast on the real
palette, a spacing scale that stays on the 4px grid, a type scale that never
inverts, and — the check that catches real bugs — every `var(--token)` used by a
stylesheet being defined in tokens.css.
"""
from __future__ import annotations

import pathlib
import re

import pytest

STATIC = pathlib.Path(__file__).resolve().parent.parent / "charta" / "web" / "static"
TOKENS_CSS = STATIC / "tokens.css"
APP_CSS = STATIC / "app.css"

AA_NORMAL = 4.5   # WCAG 2.2 AA, body text
AA_NON_TEXT = 3.0  # WCAG 2.2 non-text contrast (accents, borders, glyphs)


def _block(css: str, selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{(.*?)\}}", css, re.S)
    return match.group(1) if match else ""


def _vars(block: str) -> dict[str, str]:
    return {name: value.strip() for name, value in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", block)}


@pytest.fixture(scope="module")
def css() -> str:
    return TOKENS_CSS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dark(css: str) -> dict[str, str]:
    return _vars(_block(css, ":root"))


@pytest.fixture(scope="module")
def light(css: str) -> dict[str, str]:
    return _vars(_block(css, '[data-theme="light"]'))


@pytest.fixture(scope="module")
def app_css() -> str:
    return APP_CSS.read_text(encoding="utf-8")


def _rgb(value: str) -> tuple[float, float, float]:
    value = value.strip()
    if value.startswith("#"):
        digits = value[1:]
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        return (int(digits[0:2], 16) / 255, int(digits[2:4], 16) / 255, int(digits[4:6], 16) / 255)
    parts = [float(p) for p in re.findall(r"[\d.]+", value)]
    if len(parts) < 3:
        raise ValueError(f"cannot parse colour: {value!r}")
    scale = 1.0 if max(parts[:3]) <= 1 else 255.0
    return (parts[0] / scale, parts[1] / scale, parts[2] / scale)


def _luminance(value: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in _rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(foreground: str, background: str) -> float:
    a, b = _luminance(foreground), _luminance(background)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("surface", ["bg", "surface", "raised", "sunken"])
@pytest.mark.parametrize("ink", ["text", "muted"])
def test_text_meets_wcag_aa_on_every_surface(theme, surface, ink, dark, light):
    palette = dark if theme == "dark" else light
    key = f"--{surface}" if f"--{surface}" in palette else f"--{ink}"
    ratio = contrast(palette[f"--{ink}"], palette[key])
    assert ratio >= AA_NORMAL, (
        f"{theme}: --{ink} on --{surface} is {ratio:.2f}:1 (needs {AA_NORMAL}:1)")


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("accent", ["accent1", "accent2", "success", "warning", "danger", "info"])
def test_semantic_colours_stay_readable(theme, accent, dark, light):
    palette = dark if theme == "dark" else light
    ratio = contrast(palette[f"--{accent}"], palette["--surface"])
    assert ratio >= AA_NON_TEXT, f"{theme}: --{accent} on --surface is {ratio:.2f}:1"


def test_text_outranks_muted_for_hierarchy(dark):
    """Muted ink must be visibly quieter than body ink, or there is no hierarchy."""
    assert contrast(dark["--text"], dark["--surface"]) > contrast(dark["--muted"], dark["--surface"])


def test_spacing_scale_is_on_the_4px_grid(dark):
    steps = [dark[f"--s{i}"] for i in range(1, 8)]
    values = [int(re.match(r"(\d+)px", s).group(1)) for s in steps]  # type: ignore[union-attr]
    assert all(v % 4 == 0 for v in values), values
    assert values == sorted(values) and len(set(values)) == len(values), values


def test_type_scale_is_strictly_increasing(dark):
    sizes = [int(re.match(r"(\d+)px", dark[k]).group(1))  # type: ignore[union-attr]
             for k in ["--fs-caption", "--fs-label", "--fs-sm", "--fs-body",
                       "--fs-subtitle", "--fs-title", "--fs-display"]]
    assert sizes == sorted(sizes) and len(set(sizes)) == len(sizes), sizes
    assert sizes[0] >= 11 and sizes[-1] <= 40, sizes


def test_every_token_used_is_defined(css, app_css):
    """An undefined var() silently renders as nothing — the classic design-system bug.

    Definitions may live in any rule, not just :root: component-local properties
    like `.ring{--pct:0}` are legitimate and are set per element from Python.
    """
    defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", css)) | set(re.findall(r"(--[a-z0-9-]+)\s*:", app_css))
    used = set(re.findall(r"var\((--[a-z0-9-]+)", app_css + css))
    assert not (used - defined), f"undefined tokens: {sorted(used - defined)}"


def test_chrome_is_not_selectable_but_content_is(css):
    assert re.search(r"body\s*\{[^}]*user-select:\s*none", css, re.S)
    assert re.search(r"\.content[^{]*\{[^}]*user-select:\s*text", css, re.S)


def test_accessibility_scaffolding_is_present(css, app_css):
    assert ":focus-visible" in css, "focus ring must be visible for keyboard users"
    assert "prefers-reduced-motion" in css, "motion must respect the OS setting"
    assert "scrollbar-width:thin" in css or "scrollbar-width: thin" in css
    assert "overscroll-behavior:none" in css or "overscroll-behavior: none" in css
    assert "backdrop-filter" in css and "@supports not" in css, "glass needs a solid fallback"
