'use strict';
// State directory resolution. Must match charta/core/config.py:default_state_dir()
// exactly, so the Electron shell and the Python backend share window.json and
// charta.log instead of scattering state in two places.
const os = require('node:os');
const path = require('node:path');

function stateDir(env = process.env, platform = process.platform, home = os.homedir()) {
  if (env.CHARTA_STATE_DIR) return env.CHARTA_STATE_DIR;
  if (platform === 'win32') return path.join(env.APPDATA || home, 'Charta');
  return env.XDG_CONFIG_HOME
    ? path.join(env.XDG_CONFIG_HOME, 'charta')
    : path.join(home, '.config', 'charta');
}

function windowStateFile(env, platform, home) {
  return path.join(stateDir(env, platform, home), 'window.json');
}

function repoRoot() {
  return path.resolve(__dirname, '..', '..');
}

function iconPath() {
  return path.join(repoRoot(), 'charta', 'assets', 'charta.ico');
}

module.exports = { iconPath, repoRoot, stateDir, windowStateFile };
