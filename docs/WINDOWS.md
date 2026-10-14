# Running Charta on Windows

Charta is Windows-first, but every run so far has happened on Linux. This is the
runbook for the first real Windows run, plus exactly what to check while you are
there. The native window code (DWM dark title bar, Mica, taskbar icon, geometry)
is written and unit-tested as a guarded no-op on other platforms — **its visuals
have never actually been seen on Windows.**

## 1. Prerequisites

- Python 3.11+ (`py -3 --version`). If you install from python.org, tick
  *Add python.exe to PATH*.
- A model provider. Easiest local option: [Ollama](https://ollama.com/download).
  Or skip it entirely and point at a cloud endpoint (step 3b).

## 2. Install

```bat
git clone <your-repo> charta
cd charta
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pywebview        :: native window (optional; without it we use your browser)
```

`pip install -e ".[native]"` does both in one step if you prefer an editable install.

## 3. Provider

3a. Local (default):

```bat
ollama serve
ollama pull gemma3:4b
ollama pull nomic-embed-text
```

3b. Or any OpenAI-compatible endpoint — no code change:

```bat
set CHARTA_BASE_URL=https://api.openai.com/v1
set CHARTA_API_KEY=sk-...
set CHARTA_MODEL=gpt-4o-mini
```

## 4. Check the machine before you run anything

```bat
python -m charta.cli doctor
```

Every `[FAIL]` line blocks you; `[WARN]` lines are optional. Expected on a good
setup: `provider OK`, `icon charta.ico: 7 sizes`, `safety-guard OK`. If the window
host line warns, `charta open` still works — it opens your browser instead.

Paste the report back (`--json` for machine-readable) if something is off.

## 5. Right-click integration

```bat
python -m charta.cli install-shell
```

On Windows 11 the entry lives under **Show more options** (or Shift+F10). It
launches `charta open "<folder>"`, i.e. the setup window for the folder you
clicked — it does not start moving anything. `uninstall-shell` removes it.

## 6. Run

```bat
python -m charta.cli open "%USERPROFILE%\Documents\Receipts"
```

Then, in the window:

1. Type or hold the mic button and describe the folder.
2. Pick **Suggest** (default) or **Auto** in the custom dropdown.
3. **Create charter** → charter cards → **Start watching**.
4. Drop a PDF or receipt into the folder and check **Review**.

## 7. What to verify in the window (the polish checklist)

| Look | Expected | If it fails |
| --- | --- | --- |
| Title bar | dark, matching the app | pre-Win10-2004: attribute 19 fallback; report `dwm` from doctor |
| Backdrop | Mica blur (Win11 22H2+) | falls back to a solid caption color automatically; `[app] mica = false` skips the attempt |
| Corners | rounded | — |
| Taskbar / alt-tab icon | the violet ◈ mark, several sizes | regenerate with `python tools\make_icon.py` |
| Taskbar grouping | one "Charta" entry, not "python.exe" | AppUserModelID; check doctor's `dwm`/log line |
| Close and reopen | same size **and** position | `%APPDATA%\Charta\window.json` should update on close |
| Right-click inside the app | no browser context menu | development escape hatch: `charta open --debug` |
| F5 / Ctrl+R / Ctrl+F / Ctrl+P / F12 | do nothing | same `--debug` escape hatch |
| Selecting text | drag selects only inside the content area | — |
| Folder picker | custom modal, folders only, protected folders flagged | — |
| `C:\Windows` as a folder | friendly refusal screen, HTTP 403 | never an error dump |

`charta open --debug` also prints a `native window polish: {...}` line on load with
a per-feature pass/fail — that line is the fastest way to see which DWM call the
OS rejected.

## 8. Windows-specific notes

- Protected locations (`C:\Windows`, `Program Files`, `AppData`, drive roots, the
  profile root) are refused by the CLI **and** the web API.
- Charta never deletes: it moves and copies, journals every move to
  `.charta/journal.jsonl`, and `charta undo` reverses it.
- If SmartScreen warns about an unsigned Python entry, that is expected for a
  local script-based app.
- Long paths: enable *Long Paths* in Windows if you nest deeply; nothing in
  Charta patches around MAX_PATH.
