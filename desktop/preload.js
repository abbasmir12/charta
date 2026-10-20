'use strict';
// The only bridge between the renderer and the shell.
// Deliberately tiny: no filesystem, no node, no ipcRenderer passthrough — the
// renderer talks to the Python backend over HTTP like it does in a browser.
const { contextBridge, ipcRenderer } = require('electron');

// Lets the CSS switch to desktop chrome (draggable title bar) without a flash of
// the browser layout. Set as early as possible; DOMContentLoaded is the backstop.
const markShell = () => {
  if (document.documentElement) document.documentElement.dataset.shell = 'electron';
};
markShell();
document.addEventListener('DOMContentLoaded', markShell);

contextBridge.exposeInMainWorld('charta', {
  desktop: true,
  platform: process.platform,
  versions: { electron: process.versions.electron, chrome: process.versions.chrome },
  // Keep the native title bar in sync with the in-app theme toggle.
  setTheme: (theme) => ipcRenderer.send('charta:theme', String(theme || 'dark')),
  notify: (message) => ipcRenderer.send('charta:notify', String(message || '')),
});
