/**
 * Electron smoke test: verifies the sandboxed preload actually exposes
 * window.desktopAPI to the renderer (catches preload require() regressions).
 * Usage: npx electron scripts/preload-smoke.cjs
 */
const { app, BrowserWindow } = require("electron");
const path = require("node:path");

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "..", "dist", "preload.js"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });

  await win.loadURL("data:text/html,<html><body>smoke</body></html>");

  const api = await win.webContents.executeJavaScript(
    "(window.desktopAPI ? { generatePatch: typeof window.desktopAPI.generatePatch, pickBinary: typeof window.desktopAPI.pickBinary, getPathForFile: typeof window.desktopAPI.getPathForFile } : null)",
  );

  const ok =
    api !== null &&
    api.generatePatch === "function" &&
    api.pickBinary === "function" &&
    api.getPathForFile === "function";

  console.log(ok ? "PRELOAD SMOKE OK" : `PRELOAD SMOKE FAILED: ${JSON.stringify(api)}`);
  app.exit(ok ? 0 : 1);
});
