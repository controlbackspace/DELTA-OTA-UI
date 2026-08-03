/**
 * Builds the renderer (Vite) and bundles the output into dist/renderer/ so the
 * desktop app is self-contained: one artifact, loaded from disk (file://).
 */
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const desktopDir = path.resolve(__dirname, "..");
const uiDir = path.resolve(desktopDir, "..", "ui", "secureota-ui");
const uiDist = path.join(uiDir, "dist");
const rendererOut = path.join(desktopDir, "dist", "renderer");

const npmCmd = process.platform === "win32" ? "npm.cmd" : "npm";

if (!fs.existsSync(uiDir)) {
  console.error(`[bundle-renderer] UI project not found: ${uiDir}`);
  process.exit(1);
}

const result = spawnSync(npmCmd, ["run", "build"], {
  cwd: uiDir,
  stdio: "inherit",
  shell: process.platform === "win32",
});

if (result.status !== 0) {
  console.error("[bundle-renderer] Vite build failed; aborting bundle step.");
  process.exit(result.status ?? 1);
}

if (!fs.existsSync(path.join(uiDist, "index.html"))) {
  console.error(`[bundle-renderer] No build output at ${uiDist}`);
  process.exit(1);
}

fs.rmSync(rendererOut, { recursive: true, force: true });
fs.cpSync(uiDist, rendererOut, { recursive: true });

console.log(`[bundle-renderer] Renderer bundled -> ${rendererOut}`);
