# DESIGN.md — Charta visual source of truth

> Any UI change must follow this file. Source of truth page: `/styleguide`.
> **Direction: "ink & paper".** The subject is a folder that keeps a written
> charter — an archive desk. So: cool dim-white paper, true near-black ink for
> solid actions, one restrained ink-blue accent reserved for selection/focus/
> links, hairline rules and spacing instead of boxes, and the Windows system
> typeface. Restraint over decoration; one bold element (the ink action) and
> everything else quiet.
>
> This file was rebuilt against four design skills: Anthropic `frontend-design`,
> the `frontend-ui-ux` doctrine, `ui-visual-composition` and
> `information-architecture-navigation`. Their named "AI tells" are banned here
> (see §7).

## 1. Tokens (`web/static/tokens.css`)

- Themes: `light` (default) + `dark`, both contrast-checked independently.
  OS choice is honoured until the user picks one; persisted in `localStorage`
  (`charta-theme`). `:root` owns the spacing/type scales and the dark palette;
  `[data-theme="light"]` overrides every colour.
- Paper (light): `--bg:#F2F3F3` (cool dim white), `--surface:#FFFFFF`,
  `--raised:#ECEEEE`, `--sunken:#E8EAEA`, `--border:rgba(20,24,26,.09)`,
  `--text:#16191B` (true ink), `--muted:#5C6266`, `--faint:#8A9094`.
- Dark: `--bg:#0E1012`, `--surface:#15181B`, `--raised:#1D2124`,
  `--sunken:#101214`, `--text:#ECEEEF`, `--muted:#9AA1A6`.
- Accent = **one ink blue**, used *only* for selection, focus and links:
  `--accent1:#1F5FA9` / `#77ADE8` (dark). Not a brand fill.
- Solid action = **true ink**, inverted per theme: `--solid:#1B1E21` with
  `--solid-fg:#F5F6F6` (light) / `--solid:#EDEFF0` (dark). Primary buttons,
  user chat bubbles and toasts use this; it never collides with semantics.
- Semantics are their own system: `--success/--warning/--danger/--info`,
  re-valued in each theme. Always paired with an icon or label, never colour
  alone.
- Radius is a scale, not one value: `--r-card:10px`, `--r-in:6px`,
  `--r-xs:4px`, `--r-chip:999px`.
- Elevation (`--sh1/2/3`) is reserved for **floating layers only** (menus,
  palette, picker, toast, dropdowns). Cards are flat + hairline.
- Type: Windows-first system stack (Segoe UI Variable → system-ui) — a
  considered choice for a Windows-first, content-heavy tool. Cascadia/Consolas
  for paths, JSON and logs. No CDN, no bundled fonts.
  Scale 11/12/13/14/16/20/28; body 1.55 line-height.
- Icons: Lucide, inlined SVGs from `web/icons.py` (`icon(name, size)`),
  1.75px stroke, `currentColor`. No emoji.
- Motion: 140–360ms ease-out, feedback for actions; `prefers-reduced-motion`
  disables it globally. No scattered per-card hover lifts.

## 2. Structure rules (the important part)

- **Hierarchy in grayscale first.** Order, grouping, size, weight, spacing and
  hairline rules carry the structure; colour is added last and sparingly.
- **Ruled sections, not card soup.** A page is a stack of `<section
  class="section">` blocks separated by a top hairline (`.section-head` +
  `.section-note` + optional `.section-actions`). A green `--accent-soft` box
  on everything is banned.
- **Grouped navigation rail.** Sidebar groups: `Work` (Folders, Overview, Files,
  Review, Outputs, Gaps, Ask), `Records` (Activity, History), then a
  `rail-foot` (Settings, New charter). Group labels are sentence-case 12px muted
  — never tracked ALL-CAPS. Active item = filled `--raised` row + accent icon.
- **One folder control.** The watched folder is switched from the toolbar
  breadcrumb (or the command palette); it is not repeated three times.
- **Contextual toolbar (40px).** Brand · breadcrumb (folder / section) · live
  status (`#thinking`) · Search (opens the palette) · local-or-cloud status ·
  theme toggle. No pill soup; no middle-dot meta strings. In Electron it is
  the draggable title bar (`titleBarOverlay.height = 40`).
- **Stats are one ruled strip** (`.stat-strip`), not four floating boxes.
- **Facts are a `<dl class="facts">`**, not `a · b · c` meta lines.
- Content reads top-down: `page_head` (h1 + subtitle + primary action, closed
  by a hairline) → stat strip → sections.

## 3. Components (`web/static/app.css` composes tokens only)

- Buttons: `.btn` (quiet surface), `.btn-primary` (solid ink), `.btn-ghost`,
  `.btn-danger`; `.btn-icon` 32px. Focus-visible = 2px accent outline + ring.
- Cards: `.card` (surface, hairline, 10px) — used only where content is
  genuinely card-shaped (proposal, output grid, a single grouped list).
- Proposal card: thumb, `src → dest`, confidence meter, one-sentence reason,
  sensitive badge, Approve/Reject/Why.
- Chips/badges: `.chip`, `button.chip` (≥28px hit area), `pill-suggest`
  (neutral), `pill-auto` (amber), `badge-sensitive`.
- Inputs: 6px radius, focus ring. Textarea auto-grows.
- Tables: sticky header, sentence-case labels, hover row, mono paths.
- Log list: `.log .row-item` (hairline-separated activity rows).
- Empty/loading/error states everywhere (icon + headline + next action;
  skeleton shimmer, never a blank screen).
- Toasts: bottom-right, solid ink, Undo 8s, `role=status`.

## 4. Layout

- Sidebar 252px (groups above), toolbar 40px, main `max-width:1120px`.
- Layout holds at 900px (verified). Below 820px the rail overlays and the
  stat strip drops to two columns.
- Command palette (Ctrl/⌘K, or `/`): fuzzy actions (Approve all, Undo, Ask,
  Rebuild outputs, Settings).

## 5. Screen specs (summary — full spec in prompt)

1. Setup (680px): path chip + Choose folder, "What is this folder for?",
   autogrow textarea + rotating placeholder, mic (hold/Space, waveform),
   3 preset chips, Mode dropdown, path field, "Create charter" → staged
   progress → charter card.
1b. Folders (app-level): stat strip (folders watched, files in them, waiting
   for review, gaps), then one card per folder — name, path, purpose, mode
   chip, state chip (Watching / Paused), a facts list, actions (Open, Files,
   Ask, Scan now, Stop watching / Resume watching) and an inline ask box.
   Paused folders keep their analysis and are listed apart from watched ones.
1c. Files: one table of every file in the folder (path, kind, size, index
   state, why) with a reader panel that shows the extracted text, PDF pages
   or a vision summary. Per file: Read, Edit (the old version is kept as
   `<name>.charta-old`) and "Move to trash" — a reversible move, never a
   delete. A ruled "In Charta's trash" section lists what was set aside, with
   "Bring back" on each row.
2. Overview: ruled stat strip, then ruled sections (Needs your review /
   Missing items / Latest outputs) with the mode chip and actions.
3. Review: proposal cards + legend + J/K/A/R/E/Z keyboard + Undo; ruled
   "Proposed structure" tree preview.
4. Outputs: tabs; receipts grid (sort/filter/export), notes, flashcards,
   data table.
5. Gaps: ruled checklist (found / missing + note), progress ring.
6. Ask: chat + mic, streaming, citation chips, calm "couldn't find" state.
7. Activity: ruled log (`what / file / why / when`), Undo per row.
7b. History: the folder's own git trail (`.charta/git`) — one row per commit
   with date, short sha, message and the files it touched. Every index, move,
   edit, trash and rebuild is a commit, so the user can see exactly what
   changed and why, and `git log` works in their own terminal too.
8. Settings: ruled sections with `.facts` — provider+health, voice, window,
   privacy ("all local", "no delete button").

## 6. Trust/safety, states, a11y, perf

- Persistent "100% local" status in the toolbar. No delete button anywhere:
  the Files page offers "Move to trash" (a reversible move into
  `.charta/trash/`, with "Bring back"), never a destructive delete.
  Protected-folder refusal = friendly full-screen, never an error dump.
- SSE live status in `#thinking`; hover/focus/active everywhere; visible focus.
- A11y: keyboard everywhere, ARIA, AA contrast (gated by `tests/test_design.py`),
  ≥24px hit targets (gated by `tools/ui_check.py`), SR announcements.
- Perf: no build step (vanilla JS); first paint <1s on localhost.
- Electron chrome colours mirror the tokens (`desktop/main.js` `CHROME`) so the
  native title bar never flashes a mismatched theme.

## 7. Banned "AI tells" (from the design skills)

Never ship: cream+serif+terracotta; near-black + acid-green; tracked ALL-CAPS
eyebrow labels; middle-dot meta strings ("A · B · C" or "Suggest · …");
"WORD — fragment" em-dash labels; a monospace face for generic small labels
(paths/IDs only); "→" appended to link/button text; one border-radius and one
soft shadow on every card; gradient washes as decoration; numbered markers on
non-sequential content; per-card hover lifts; generic filler copy.

## 8. Signature moments (demo video)

mic pulse+waveform → charter card fades in → files fly into the tree →
gaps ring fills → cited answer streams with chips.
