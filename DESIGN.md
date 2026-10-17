# DESIGN.md — Charta visual source of truth

> Any UI change must follow this file. Source of truth page: `/styleguide`.
> Personality: calm, professional, quietly premium. Native Windows 11 × Linear
> × Notion: light-first dim-white canvas, hairline borders, one calm indigo
> accent, generous spacing, nothing decorative for its own sake.
> Promise: "your messy folder quietly sorts itself, and you stay in control"
> — always show what the AI is doing; nothing moves without approval.

## 1. Tokens (`web/static/tokens.css`, CSS variables)

- Themes: `light` (default, dim white) + `dark`. The OS choice is honoured
  until the user picks one; the toggle is persisted in `localStorage`
  (`charta-theme`). `:root` holds the dark palette; `[data-theme="light"]`
  overrides every token, so both themes are contrast-checked independently.
- Dim white (light): `--bg:#F4F4F2; --surface:#FFFFFF; --raised:#F1F1EF;
  --sunken:#EBEBE8; --border:rgba(24,24,28,0.10); --text:#1A1B1F;
  --muted:#5B5F6B;`
- Dark: `--bg:#0C0D10; --surface:#141519; --raised:#1B1D22; --sunken:#0F1013;`
  `--border:rgba(255,255,255,0.08); --text:#EDEEF2; --muted:#9BA1AE;`
- Accent: one calm indigo — `#4F46E5` (light) / `#818CF8` (dark), with a
  darker `--accent2` for links. **No gradient.** Used sparingly: primary
  buttons, focus rings, active nav, icon accents, logo mark.
- Semantics: light `--success:#047857; --warning:#B45309; --danger:#B91C1C;
  --info:#1D4ED8;` with brighter dark-theme values. Always pair colour with an
  icon/label (never colour alone).
- Radius: cards 12px, inputs/buttons 8px, chips 999px.
- Spacing: 4px scale (4,8,12,16,24,32,48) — `--s1..--s7`, never a raw pixel.
- Shadows: soft, neutral, layered elevation — never a coloured glow.
- Glass: `backdrop-filter: blur(20px)` only on the command palette/modals;
  solid fallback via `@supports not (backdrop-filter: blur(1px))`.
- Typography: Windows-first system stack (Segoe UI Variable → system-ui) with
  Cascadia Code/ui-monospace for paths, JSON and logs. No CDN, no bundled fonts.
  Scale: 11,12,13,14,16,20,28px.
- Icons: Lucide, inlined SVGs from `web/icons.py` (`icon(name, size)`),
  1.75px stroke, `currentColor`. No emoji/unicode glyphs in the chrome.
- Motion: 150–250ms ease-out micro; 420ms entrance with a 40ms stagger.
  `prefers-reduced-motion`: animation/transition disabled.

## 2. Component rules

- Buttons: `.btn` + `.btn-primary` (gradient), `.btn-ghost`, `.btn-danger`
  (never "delete" — undo/dismiss only). Focus-visible gradient ring.
- Cards: `.card` (surface, 12px, border, shadow). Proposal cards include
  thumb/icon, orig → dest arrow, confidence meter, 1-sentence reason,
  sensitive badge, Approve/Reject/Edit.
- Chips/pills: mode pill (Suggest=green, Auto=amber), status dots
  (idle/scanning/needs-review), citation chips.
- Inputs: 8px radius, border, focus ring. Textarea auto-grows.
- Toasts: bottom-right, Undo button 8s, `role=status` announce.
- Skeletons: shimmer blocks for every list; never blank screens.
- Empty states: icon + headline + next action (no illustrations).
- Tables: sticky headers, sortable/filterable, mono paths.

## 3. Layout

- Sidebar (collapsible): watched folders (status dot) + Overview, Review,
  Outputs, Gaps, Ask, Activity, Settings.
- Topbar: folder name+path (mono), mode pill, Ctrl+K hint, theme toggle,
  "100% local" indicator with tooltip.
- Main: max-width 1200px, generous whitespace, responsive ≥900px.
- Command palette (Ctrl+K): fuzzy actions (Approve all, Undo, Ask,
  Open in Explorer, Switch folder, Edit charter).

## 4. Screen specs (summary — full spec in prompt)

1. Setup (640×520, centered): path chip, "What is this folder for?",
   autogrow textarea + rotating placeholder, round mic (hold/Space,
   waveform+pulse, streams to textarea), 3 preset chips, "Create charter"
   → staged shimmer progress → charter cards + Raw Markdown toggle +
   Suggest-default toggle + Start watching.
2. Overview: hero stats (tracked / review / gaps / activity), "thinking"
   strip (file + progress + step), cards (review/gaps/outputs/activity).
3. Review: proposal cards + bulk bar + J/K/A/R/E/Z keyboard + legend +
   before/after tree preview (animated) + fly-to-folder on approve +
   Undo toast.
4. Outputs: tabs; receipts grid (sort/filter/edit/export xlsx-csv,
   open-source links); notes md + subject sidebar; flashcards flip +
   review mode.
5. Gaps: checklist (green present / amber dashed missing + note),
   progress ring, "Mark as not needed" / "I'll add it".
6. Ask: chat + mic, streaming, citation chips → drawer preview w/
   highlight; calm "couldn't find" state; starter questions from charter.
7. Activity: timeline (what/file/why/when), Undo per row + "since…",
   filters.
8. Settings: model select + health, voice (Local default; ElevenLabs
   "Cloud: audio leaves your device" off), safety, theme, Privacy panel
   ("all local", "no delete button").

## 5. Trust/safety, states, a11y, perf

- Persistent "100% local" indicator. No delete button anywhere.
  Protected-folder refusal = friendly full-screen, not dump.
- SSE live updates; hover/focus/active everywhere; gradient focus ring.
- A11y: keyboard everywhere, ARIA, AA contrast, SR announcements.
- Perf: no build step (vanilla/Alpine-local), first paint <1s localhost.
- Native polish (all implemented; Windows visuals unverified, see STATUS):
  - dark DWM titlebar + Mica + solid fallback + rounded corners →
    `charta/shell/native_window.py`
  - AppUserModelID, window/taskbar .ico, remembered geometry → same module,
    icon generated by `tools/make_icon.py` (`charta/assets/charta.ico`)
  - no ctx-menu / F5 / Ctrl+R / Ctrl+F / Ctrl+P / F12 / DevTools unless
    `--debug` (or `CHARTA_DEBUG=1`) → `static/app.js`, flag injected by `web/app.py`
  - `user-select:none` on chrome, text selectable in `.content`;
    `overscroll:none`; thin themed scrollbars → `static/tokens.css`
  - custom dropdowns (`.dd`, no native `<select>`) and custom folder picker
    (`/api/fs/list`, folders only, protected paths flagged) → `static/app.js`,
    `web/app.py`, `core/fsbrowse.py`
  - protected-folder refusal is a friendly full-screen page at `/protected`

## 5b. Design system as implemented

Tokens live in `static/tokens.css`; `static/app.css` only composes them.

- Type scale: 11/12/13/14/16/20/28 px, line-height 1.5 body, 1.25 headings,
  `-0.011em` tracking at >= 20px.
- Space scale: `--s1..--s7` = 4/8/12/16/24/32/48 px. Never a raw pixel value.
- Elevation `--sh1/2/3`, focus `--ring`, motion `--t-fast/base/slow` + `--ease`.
- Both themes are contrast-checked (WCAG AA 4.5:1 text, 3:1 accents) by
  `tests/test_design.py`, which also fails on any `var(--token)` that is not
  defined and on a spacing scale that leaves the 4px grid.
- Icons come from `charta/web/icons.py` (`icons.svg`), regenerated from
  lucide-static by `tools/fetch_icons.py`; the renderer reads the same bodies
  from `window.__ICONS__`, so JS-built markup keeps one icon language.
- Clickable chips and sort headers carry a >= 24px hit area (WCAG 2.2 SC 2.5.8),
  enforced by `tools/ui_check.py` in a real browser.
- Shell: one `.appbar` serves as an ordinary header in a browser and as the
  draggable Electron title bar (`html[data-shell="electron"]`), 40px tall to
  match `titleBarOverlay.height`; `desktop/main.js`'s `CHROME` colours mirror
  these tokens so the native title bar never flashes a mismatched theme.

## 6. Signature moments (demo video)

mic pulse+waveform → charter cards fade in → files fly into tree →
gaps ring fills → cited answer streams with chips.
