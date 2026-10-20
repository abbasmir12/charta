'use strict';
// Supervises the Python backend that actually does the work.
//
// The renderer only ever sees http://127.0.0.1:<port>, so the shell never needs
// privileged access to the user's files: contextIsolation and the Chromium
// sandbox stay on and nodeIntegration stays off.
const { spawn, spawnSync } = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const net = require('node:net');
const path = require('node:path');

const CANDIDATES = process.platform === 'win32'
  ? ['python', 'python3', 'py']
  : ['python3', 'python'];

function resolvePython(env = process.env) {
  const ordered = env.CHARTA_PYTHON ? [env.CHARTA_PYTHON, ...CANDIDATES] : CANDIDATES;
  for (const name of ordered) {
    const probe = spawnSync(name, ['-c', 'import sys;print(sys.version_info[:2])'], {
      encoding: 'utf8', timeout: 15000,
    });
    if (!probe.error && probe.status === 0) return name;
  }
  return '';
}

function findFreePort(host = '127.0.0.1') {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on('error', reject);
    server.listen(0, host, () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

function backendArgs(port, debug) {
  const args = ['-m', 'charta.cli', 'serve', '--port', String(port)];
  if (debug) args.push('--debug');
  return args;
}

function start(options) {
  const { python, port, debug, repoRoot, logFile, env = process.env } = options;
  fs.mkdirSync(path.dirname(logFile), { recursive: true });
  const out = fs.createWriteStream(logFile, { flags: 'a' });
  out.write(`\n--- electron backend: ${python} ${backendArgs(port, debug).join(' ')} ---\n`);
  const child = spawn(python, backendArgs(port, debug), {
    cwd: repoRoot,
    env: { ...env, PYTHONUNBUFFERED: '1', CHARTA_DEBUG: debug ? '1' : '' },
    windowsHide: true,
  });
  child.stdout.pipe(out);
  child.stderr.pipe(out);
  return child;
}

function waitForHealth(port, timeoutMs = 25000, host = '127.0.0.1') {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve) => {
    const attempt = () => {
      const req = http.get({ host, port, path: '/api/health', timeout: 1500 }, (res) => {
        res.resume();
        if (res.statusCode && res.statusCode < 500) return resolve(true);
        retry();
      });
      req.on('timeout', () => { req.destroy(); retry(); });
      req.on('error', retry);
    };
    const retry = () => (Date.now() > deadline ? resolve(false) : setTimeout(attempt, 250));
    attempt();
  });
}

function stop(child) {
  if (!child || child.killed || child.exitCode !== null) return;
  if (process.platform === 'win32') {
    // uvicorn spawns nothing, but kill the tree anyway so no orphan holds the port.
    spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true });
  } else {
    child.kill('SIGTERM');
  }
}

function getJson(port, reqPath, timeoutMs = 1500, host = '127.0.0.1') {
  return new Promise((resolve) => {
    const req = http.get({ host, port, path: reqPath, timeout: timeoutMs }, (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => { try { resolve(JSON.parse(body)); } catch (err) { resolve(null); } });
    });
    req.on('timeout', () => { req.destroy(); resolve(null); });
    req.on('error', () => resolve(null));
  });
}

function postJson(port, reqPath, timeoutMs = 1500, host = '127.0.0.1') {
  return new Promise((resolve) => {
    const req = http.request({ host, port, path: reqPath, method: 'POST', timeout: timeoutMs },
      (res) => { res.resume(); res.on('end', () => resolve(res.statusCode || 0)); });
    req.on('timeout', () => { req.destroy(); resolve(0); });
    req.on('error', () => resolve(0));
    req.end();
  });
}

// Watched folders for the tray menu. Never throws: a down backend is "nothing".
async function watchedFolders(port, host = '127.0.0.1') {
  const body = await getJson(port, '/api/watch/status', 1500, host);
  return (body && Array.isArray(body.folders)) ? body.folders : [];
}

function unwatch(port, folder, host = '127.0.0.1') {
  return postJson(port, `/api/unwatch?folder=${encodeURIComponent(folder)}`, 1500, host);
}

module.exports = {
  backendArgs, findFreePort, resolvePython, start, stop, unwatch, waitForHealth, watchedFolders,
};
