'use strict';
// Command-line arguments, read from this process or from another instance's
// command line (the 'second-instance' event). Kept separate from main.js so it
// can be unit-tested without Electron.
function argFrom(argv, name, fallback = '') {
  const list = argv || [];
  const hit = list.find((a) => a === `--${name}` || a.startsWith(`--${name}=`));
  if (!hit) return fallback;
  return hit.includes('=') ? hit.split('=').slice(1).join('=') : 'true';
}

const arg = (name, fallback = '') => argFrom(process.argv, name, fallback);

module.exports = { arg, argFrom };
