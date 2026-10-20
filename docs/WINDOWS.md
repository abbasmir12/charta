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
ollama pull gemma4:e4b
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

Then prove the model answers, not just that the port is open:

```bat
python -m charta.cli testmodel
```

It sends `hello` to the configured model and prints the reply with a PASS/FAIL
status (`[OK] reachable`, `[OK] model`, `[OK] answer "..."`). A `[FAIL] model`
line names the ids the provider actually offers — set `[models] generation` to
one of them, or `ollama pull` it. Use `--prompt`/`--timeout` for a slower model
and `--json` when pasting the result back.

## 4b. Desktop app (Electron) — recommended

```bat
cd desktop
npm install
npm start
```

The shell starts `charta serve` on a free port, waits for `/api/health`, then shows
the UI in a real window (custom title bar, Mica, tray, remembered geometry). If it
cannot start it tells you why in a dialog and in the log. `npm run debug` restores
F5/Ctrl+R/F/P and DevTools; `npm run smoke` loads all 9 screens headlessly.

Use this in preference to `charta open` (pywebview), which remains a Node-free
fallback.

## 5. Right-click integration

```bat
python -m charta.cli install-shell
```

On Windows 11 the entry lives under **Show more options** (or Shift+F10). It
launches `charta open "<folder>"` without a console window (`pythonw.exe`), i.e.
the setup window for the folder you clicked — it does not start moving anything.
`uninstall-shell` removes it.

Once a folder is being watched, a second entry **"Being watched with Charta"**
appears on it. It is a per-folder verb whose `AppliesTo` (AQS) query matches that
folder's path exactly, so Explorer only shows it for folders the registry says
are watched. `charta watchd` / the in-app Watch controls add and remove these as
the watched list changes; `uninstall-shell` clears them all.

> Unverified on Windows: this box is Linux, so the `AppliesTo` matching is
> written to the documented AQS form and unit-tested as a guarded no-op, but not
> seen rendering in Explorer. Confirm on a Windows 11 machine (if the verb does
> not appear, `charta logs` and the registry key under
> `HKCU\Software\Classes\Directory\shell\ChartaWatched_*` are the place to look).

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

## 7b. "It closed by itself"

The app used to exit silently when the backend could not bind its port, and the
message died with the console window. Now:

- every run appends to `%APPDATA%\Charta\charta.log` (Electron adds
  `backend.log` next to it) — `python -m charta.cli logs` prints the tail;
- a busy port is recovered automatically (`port 8123 is already in use — using
  47123 instead`);
- if the native window dies within two seconds Charta falls back to your browser
  instead of quitting;
- `%APPDATA%\Charta\session.json` records the running instance, and `charta logs`
  says "Charta is still running" only when something actually answers on that port.

If it still exits, send me `python -m charta.cli logs --lines 120` plus the last
lines of `%APPDATA%\Charta\backend.log`.

## 8. Windows-specific notes

- Protected locations (`C:\Windows`, `Program Files`, `AppData`, drive roots, the
  profile root) are refused by the CLI **and** the web API.
- Charta never deletes: it moves and copies, journals every move to
  `.charta/journal.jsonl`, and `charta undo` reverses it.
- If SmartScreen warns about an unsigned Python entry, that is expected for a
  local script-based app.
- Long paths: enable *Long Paths* in Windows if you nest deeply; nothing in
  Charta patches around MAX_PATH.
