# DESIGN.md — Charta visual source of truth

> Any UI change must follow this file. Source of truth page: `/styleguide`.
> Personality: calm, premium, a little magical. Native Windows 11 × Linear ×
> Raycast: dark-first, glassy, fast, restrained glow, never cluttered.
> Promise: "your messy folder quietly sorts itself, and you stay in control"
> — always show what the AI is doing; nothing moves without approval.

## 1. Tokens (`web/static/tokens.css`, CSS variables)

- Themes: `dark` (default) + `light`, follow OS (`prefers-color-scheme`),
  manual toggle persisted in `localStorage` (`charta-theme`).
- Dark: `--bg:#0B0D12; --surface:#12151C; --raised:#181C25;`
  `--border:rgba(255,255,255,0.08); --text:#E8EAF0; --muted:#8B93A7;`
- Light: `--bg:#F6F7F9; --surface:#FFFFFF; --raised:#EEF1F6;`
  `--border:rgba(10,15,30,0.10); --text:#141824; --muted:#5B6478;`
- Accent gradient: `#7C5CFF → #22D3EE`. Sparingly: primary buttons,
  focus rings, active states, mic pulse, logo mark.
- Semantics: `--success:#34D399; --warning:#FBBF24; --danger:#F87171;
  --info:#60A5FA;` Always pair color with icon/label (never color alone).
- Radius: cards 12px, inputs/buttons 8px, chips 999px.
- Spacing: 4px scale (4,8,12,16,24,32,48).
- Shadows: soft layered + 1px inner highlight on glass.
- Glass: `backdrop-filter: blur(16px)` only on sidebar, palette, modals;
  solid fallback via `@supports not (backdrop-filter: blur(1px))`.
- Typography: Inter (UI) + JetBrains Mono (paths/JSON/logs), bundled in
  `/static/fonts/` (no CDN), system fallback.
  Scale: 12,14,16,20,28,40px.
- Icons: Lucide, inlined SVG, 1.5px stroke.
- Motion: 150–250ms ease-out micro; 400–600ms signature.
  `prefers-reduced-motion`: fades only (disable fly/tree/pulse).

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
- Native polish: dark DWM titlebar via ctypes, Mica w/ fallback,
  no ctx-menu/F5/Ctrl+R/Ctrl+F/Ctrl+P/DevTools unless `--debug`,
  `user-select:none` chrome only, `overscroll:none`, thin scrollbars,
  multi-size .ico + AppUserModelID, remember geometry, custom
  dropdowns/folder picker.

## 6. Signature moments (demo video)

mic pulse+waveform → charter cards fade in → files fly into tree →
gaps ring fills → cited answer streams with chips.
