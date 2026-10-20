'use strict';
// Remember window size/position between launches.
// The on-disk shape matches charta/shell/native_window.py WindowGeometry
// (x, y, width, height, maximized) so both shells can read the same file.
const fs = require('node:fs');
const path = require('node:path');

const DEFAULTS = { x: -1, y: -1, width: 1180, height: 780, maximized: false };
const MIN_W = 480;
const MIN_H = 360;

function isUsable(state) {
  return !!state && state.width >= MIN_W && state.height >= MIN_H;
}

function load(file) {
  try {
    const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
    const state = {
      x: Number.isFinite(raw.x) ? Math.trunc(raw.x) : DEFAULTS.x,
      y: Number.isFinite(raw.y) ? Math.trunc(raw.y) : DEFAULTS.y,
      width: Number.isFinite(raw.width) ? Math.trunc(raw.width) : DEFAULTS.width,
      height: Number.isFinite(raw.height) ? Math.trunc(raw.height) : DEFAULTS.height,
      maximized: Boolean(raw.maximized),
    };
    return isUsable(state) ? state : { ...DEFAULTS };
  } catch (err) {
    return { ...DEFAULTS }; // missing or corrupt: defaults, never a crash
  }
}

function save(file, bounds, maximized) {
  const state = {
    x: Math.trunc(bounds.x), y: Math.trunc(bounds.y),
    width: Math.trunc(bounds.width), height: Math.trunc(bounds.height),
    maximized: Boolean(maximized),
  };
  if (!isUsable(state)) return state; // never persist an unusable size
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify(state, null, 2), 'utf8');
  } catch (err) {
    /* a failed write must not take the app down */
  }
  return state;
}

module.exports = { DEFAULTS, isUsable, load, save };
