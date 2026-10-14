'use strict';
// Charta's desktop shell.
//
// Responsibilities: start/stop the Python backend, host the local UI in a real
// window with native chrome (dark title bar, Mica, tray, remembered geometry),
// and keep the browser's own shortcuts out of a desktop app. It never touches
// the user's files — the backend owns that, with its own safety rules.
const fs = require('node:fs');
const path = require('node:path');
const { app, BrowserWindow, Tray, Menu, dialog, ipcMain, nativeImage, nativeTheme, shell } = require('electron');

const backend = require('./lib/backend');
const paths = require('./lib/paths');
const windowState = require('./lib/window-state');

const APP_ID = 'Charta.FolderWatcher';
const TITLE = 'Charta';
const BG = '#0B0D12';
const ROUTES = ['/', '/overview', '/review', '/outputs', '/gaps', '/ask', '/activity', '/settings', '/styleguide'];

const arg = (name, fallback = '') => {
  const hit = process.argv.find((a) => a === `--${name}` || a.startsWith(`--${name}=`));
  if (!hit) return fallback;
  return hit.includes('=') ? hit.split('=').slice(1).join('=') : 'true';
};

const DEBUG = process.argv.includes('--debug');
const SMOKE = process.argv.includes('--smoke');
// `--shots` alone writes to docs/screenshots; `--shots=<dir>` chooses another.
const SHOTS_ARG = arg('shots');
const SHOTS = SHOTS_ARG === '' ? '' : (SHOTS_ARG === 'true' ? path.join(paths.repoRoot(), 'docs', 'screenshots') : SHOTS_ARG);
const FOLDER = arg('folder');
const PORT_ARG = Number(arg('port', '0')) || 0;

let win = null;
let tray = null;
let child = null;
let quitting = false;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function stateFile() {
  return paths.windowStateFile();
}

function windowOptions(bounds, mica) {
  const base = {
    title: TITLE,
    width: bounds.width,
    height: bounds.height,
    x: bounds.x >= 0 ? bounds.x : undefined,
    y: bounds.y >= 0 ? bounds.y : undefined,
    minWidth: 480,
    minHeight: 360,
    show: false,
    backgroundColor: BG,
    autoHideMenuBar: true,
    icon: fs.existsSync(paths.iconPath()) ? paths.iconPath() : undefined,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true, // required by Electron's security checklist
      nodeIntegration: false,
      sandbox: true,
      devTools: DEBUG,
      spellcheck: false,
    },
  };
  if (process.platform === 'win32' || process.platform === 'linux') {
    base.titleBarStyle = 'hidden';
    base.titleBarOverlay = { color: BG, symbolColor: '#E8EAF0', height: 40 };
  } else {
    base.titleBarStyle = 'hiddenInset';
  }
  if (mica && process.platform === 'win32') base.backgroundMaterial = 'mica'; // Win11 only
  return base;
}

function createWindow(bounds, url) {
  let options = windowOptions(bounds, true);
  let created;
  try {
    created = new BrowserWindow(options);
  } catch (err) {
    // Older Windows builds reject backgroundMaterial; keep the window either way.
    log(`backgroundMaterial unavailable (${err.message}); retrying without Mica`);
    options = windowOptions(bounds, false);
    created = new BrowserWindow(options);
  }
  win = created;
  if (bounds.maximized) win.maximize();

  win.once('ready-to-show', () => win.show()); // no white flash before first paint
  hardenNavigation(win);
  if (!DEBUG) blockBrowserKeys(win);
  trackGeometry(win);
  win.on('close', (event) => {
    saveGeometry(win);
    // A tray icon means this is a background app: closing the window hides it
    // instead of quitting (and taking the watcher down with it).
    if (!quitting && tray) {
      event.preventDefault();
      win.hide();
      tray.setToolTip(`${TITLE} — still watching; right-click the tray icon to quit`);
    }
  });
  win.on('closed', () => { win = null; });
  win.loadURL(url);
  return win;
}

function hardenNavigation(target) {
  // Local content only: anything else opens in the real browser, never in-process.
  target.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  target.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith('http://127.0.0.1')) event.preventDefault();
  });
}

function blockBrowserKeys(target) {
  target.webContents.on('before-input-event', (event, input) => {
    if (input.type !== 'keyDown') return;
    const key = (input.key || '').toLowerCase();
    const mod = input.control || input.meta;
    const blocked = key === 'f5' || key === 'f12'
      || (mod && !input.shift && ['r', 'f', 'p'].includes(key))
      || (mod && input.shift && ['i', 'j', 'c'].includes(key));
    if (blocked) event.preventDefault();
  });
}

let saveTimer = null;
function trackGeometry(target) {
  const schedule = () => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => saveGeometry(target), 500);
  };
  target.on('resize', schedule);
  target.on('move', schedule);
}

function saveGeometry(target) {
  if (!target || target.isDestroyed()) return;
  const bounds = target.isMaximized() ? target.getNormalBounds() : target.getBounds();
  windowState.save(stateFile(), bounds, target.isMaximized());
}

function log(message) {
  const line = `${new Date().toISOString()} [electron] ${message}\n`;
  process.stdout.write(line);
  try {
    fs.appendFileSync(path.join(paths.stateDir(), 'charta.log'), line);
  } catch (err) { /* logging must never break the app */ }
}

function applyTheme(target, theme) {
  nativeTheme.themeSource = theme === 'light' ? 'light' : 'dark';
  if (process.platform === 'win32' || process.platform === 'linux') {
    try {
      target.setTitleBarOverlay({
        color: theme === 'light' ? '#FFFFFF' : BG,
        symbolColor: theme === 'light' ? '#141824' : '#E8EAF0',
        height: 40,
      });
    } catch (err) { /* older Electron: title bar simply keeps its initial colors */ }
  }
}

function focusOrCreate(url) {
  if (win) {
    if (win.isMinimized()) win.restore();
    win.show();
    win.focus();
    return;
  }
  createWindow(windowState.load(stateFile()), url);
}

function createTray(url) {
  const icon = paths.iconPath();
  if (!fs.existsSync(icon)) return;
  tray = new Tray(nativeImage.createFromPath(icon));
  tray.setToolTip(TITLE);
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Open Charta', click: () => focusOrCreate(url) },
    { label: 'Review proposals', click: () => navigate('/review') },
    { label: 'Ask the folder', click: () => navigate('/ask') },
    { type: 'separator' },
    { label: 'Quit', click: () => { quitting = true; app.quit(); } },
  ]));
  tray.on('click', () => focusOrCreate(url));
}

function navigate(route) {
  if (!win) return;
  win.show();
  win.webContents.loadURL(`${baseUrl()}${route}${folderQuery()}`);
}

let backendPort = 0;
const baseUrl = () => `http://127.0.0.1:${backendPort}`;
const folderQuery = () => (FOLDER ? `?folder=${encodeURIComponent(FOLDER)}` : '');

async function boot() {
  const python = backend.resolvePython();
  if (!python) {
    dialog.showErrorBox(`${TITLE} needs Python`,
      'Charta could not find Python 3.11+ on PATH.\n\n'
      + 'Install it from python.org (tick "Add python.exe to PATH"), then start Charta again.\n'
      + 'Set CHARTA_PYTHON to point at a specific interpreter.');
    return 1;
  }
  backendPort = PORT_ARG || await backend.findFreePort();
  const logFile = path.join(paths.stateDir(), 'backend.log');
  child = backend.start({ python, port: backendPort, debug: DEBUG, repoRoot: paths.repoRoot(), logFile });
  child.on('exit', (code) => {
    if (!quitting) {
      log(`backend exited with code ${code}`);
      dialog.showErrorBox(`${TITLE} backend stopped`,
        `The local engine exited (code ${code}).\n\nLog: ${logFile}`);
      quitting = true;
      app.quit();
    }
  });
  log(`backend ${python} on port ${backendPort} (debug=${DEBUG})`);
  if (!(await backend.waitForHealth(backendPort))) {
    dialog.showErrorBox(`${TITLE} could not start`,
      `No response from ${baseUrl()}/api/health.\n\nLog: ${logFile}`);
    return 1;
  }
  log('backend healthy');
  return 0;
}

async function runRoutes(mode) {
  const out = [];
  for (const route of ROUTES) {
    const url = `${baseUrl()}${route}${folderQuery()}`;
    const errors = [];
    // Single-argument listener: Electron 35+ deprecated the (event, level, message)
    // form, and this shell pins a modern Electron.
    const onConsole = (event) => {
      const text = String((event && event.message) || '');
      const level = event && event.level;
      if (String(level).includes('error') || level === 3) errors.push(text);
    };
    win.webContents.on('console-message', onConsole);
    try {
      await win.loadURL(url);
      await sleep(450); // let skeletons settle before capturing
      if (mode === 'shots') {
        const image = await win.webContents.capturePage();
        const file = path.join(SHOTS, `electron-${route.replace(/[^a-z0-9]+/gi, '') || 'setup'}.png`);
        fs.mkdirSync(SHOTS, { recursive: true });
        fs.writeFileSync(file, image.toPNG());
        out.push(`${route} -> ${path.relative(process.cwd(), file)}`);
      } else {
        out.push(`${route} ${errors.length ? `CONSOLE_ERRORS ${errors.join(' | ')}` : 'ok'}`);
      }
    } catch (err) {
      out.push(`${route} FAILED ${err.message}`);
    } finally {
      win.webContents.removeListener('console-message', onConsole);
    }
  }
  return out;
}

async function main() {
  const lock = app.requestSingleInstanceLock();
  if (!lock) { app.quit(); return 0; }
  app.on('second-instance', () => {
    if (win) { if (win.isMinimized()) win.restore(); win.show(); win.focus(); }
  });

  await app.whenReady();
  app.setAppUserModelId(APP_ID); // one taskbar entry, not "electron.exe"
  nativeTheme.themeSource = 'dark';
  if (await boot() !== 0) { app.quit(); return 1; }

  const bounds = windowState.load(stateFile());
  const url = `${baseUrl()}/${folderQuery()}`;
  createWindow(bounds, url);
  if (!SMOKE && !SHOTS) createTray(url);

  app.on('window-all-closed', () => { quitting = true; app.quit(); });
  app.on('before-quit', () => { quitting = true; saveGeometry(win); backend.stop(child); });
  ipcMain.on('charta:theme', (event, theme) => {
    if (win && event.sender === win.webContents) applyTheme(win, theme);
  });
  ipcMain.on('charta:notify', (event, message) => {
    if (tray && message) tray.setToolTip(`${TITLE} — ${message}`);
  });

  if (SMOKE || SHOTS) {
    await new Promise((resolve) => win.webContents.once('did-finish-load', resolve));
    const results = await runRoutes(SMOKE ? 'smoke' : 'shots');
    results.forEach((line) => console.log(line));
    const failed = results.filter((r) => /FAILED|CONSOLE_ERRORS/.test(r));
    console.log(failed.length ? `FAIL ${failed.length}/${results.length}` : `OK ${results.length} routes`);
    quitting = true; backend.stop(child); app.exit(failed.length ? 1 : 0);
    return failed.length ? 1 : 0;
  }
  return 0;
}

main().catch((err) => {
  log(`fatal: ${err && err.stack ? err.stack : err}`);
  dialog.showErrorBox(`${TITLE} failed to start`, String(err && err.message ? err.message : err));
  quitting = true;
  backend.stop(child);
  app.exit(1);
});
