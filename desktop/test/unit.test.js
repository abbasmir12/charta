'use strict';
// Runs with `npm test` (node --test) — no Electron needed, so the shell's logic
// is verified even on a machine without a display.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const backend = require('../lib/backend');
const paths = require('../lib/paths');
const windowState = require('../lib/window-state');

function tmpFile() {
  return path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'charta-state-')), 'window.json');
}

test('state dir mirrors the Python side per platform', () => {
  assert.equal(paths.stateDir({ APPDATA: 'C:\\Users\\me\\AppData\\Roaming' }, 'win32'), path.join('C:\\Users\\me\\AppData\\Roaming', 'Charta'));
  assert.equal(paths.stateDir({ XDG_CONFIG_HOME: '/tmp/xdg' }, 'linux', '/home/me'), '/tmp/xdg/charta');
  assert.equal(paths.stateDir({}, 'linux', '/home/me'), path.join('/home/me', '.config', 'charta'));
  assert.equal(paths.stateDir({ CHARTA_STATE_DIR: '/custom' }, 'linux', '/home/me'), '/custom');
});

test('window state falls back to defaults when missing or corrupt', () => {
  const file = tmpFile();
  assert.deepEqual(windowState.load(file), windowState.DEFAULTS);
  fs.writeFileSync(file, '{ not json');
  assert.deepEqual(windowState.load(file), windowState.DEFAULTS);
  fs.writeFileSync(file, JSON.stringify({ x: 1, y: 2, width: 10, height: 10, maximized: true }));
  assert.equal(windowState.load(file).width, windowState.DEFAULTS.width); // unusable size
});

test('window state round-trips bounds and refuses unusable ones', () => {
  const file = tmpFile();
  const saved = windowState.save(file, { x: 120, y: 64, width: 1440, height: 900 }, true);
  assert.deepEqual(saved, { x: 120, y: 64, width: 1440, height: 900, maximized: true });
  assert.deepEqual(windowState.load(file), saved);
  windowState.save(file, { x: 0, y: 0, width: 5, height: 5 }, false);
  assert.deepEqual(windowState.load(file), saved); // unchanged: too small to use
  assert.equal(windowState.isUsable({ width: 480, height: 360 }), true);
  assert.equal(windowState.isUsable({ width: 479, height: 800 }), false);
});

test('backend args target the CLI server with an explicit port', () => {
  assert.deepEqual(backend.backendArgs(8123, false), ['-m', 'charta.cli', 'serve', '--port', '8123']);
  assert.deepEqual(backend.backendArgs(9, true), ['-m', 'charta.cli', 'serve', '--port', '9', '--debug']);
});

test('python resolution finds a real interpreter', () => {
  const python = backend.resolvePython();
  assert.notEqual(python, '', 'expected python on PATH (or set CHARTA_PYTHON)');
});

test('findFreePort returns a bindable port', async () => {
  const port = await backend.findFreePort();
  assert.ok(port > 0);
  await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.on('error', reject);
    server.listen(port, '127.0.0.1', () => server.close(resolve));
  });
});

test('watchedFolders reads the registry and unwatch posts', async () => {
  const http = require('node:http');
  const seen = [];
  const server = http.createServer((req, res) => {
    seen.push(`${req.method} ${req.url}`);
    if (req.url.startsWith('/api/watch/status')) {
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({ folders: ['/a', '/b'] }));
    } else {
      res.end('{}');
    }
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  try {
    assert.deepEqual(await backend.watchedFolders(port), ['/a', '/b']);
    await backend.unwatch(port, '/a');
    assert.ok(seen.some((s) => s.startsWith('POST /api/unwatch')));
  } finally {
    server.close();
  }
});

test('watchedFolders is empty when the backend is unreachable', async () => {
  assert.deepEqual(await backend.watchedFolders(1), []);
});

test('arguments can be read from another instance command line', () => {
  const { argFrom } = require('../lib/args');
  assert.equal(argFrom(['electron', '.', '--folder=D:\\My Docs', '--port=8123'], 'folder'), 'D:\\My Docs');
  assert.equal(argFrom(['electron', '.'], 'folder', ''), '');
  assert.equal(argFrom(['electron', '.', '--folder'], 'folder'), 'true');
});
