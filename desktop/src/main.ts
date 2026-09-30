import { app, BrowserWindow, dialog, ipcMain } from "electron";
import { existsSync } from "node:fs";
import path from "node:path";
import { IPC_CHANNELS } from "./contracts/ipc";
import type { GeneratePatchRequest } from "./contracts/release";
import { PythonLocator } from "./services/pythonLocator";
import {
  assertFirmwareBinary,
  resolveBundledRendererFile,
  resolveMakeReleaseScript,
} from "./services/paths";
import { PythonRunner } from "./services/pythonRunner";
import { createMainWindow } from "./window";

/** Composition root: builds dependencies, wires IPC, owns app lifecycle. */

function buildPythonRunner(): PythonRunner {
  const runtime = new PythonLocator(app).locate();
  const script = resolveMakeReleaseScript(runtime.gatewayDir);

  if (!existsSync(script)) {
    throw new Error(
      `Release builder not found: ${script}` +
        (runtime.packaged
          ? "\n\nReinstall the app, or restore the resources\\gateway folder."
          : "\n\nThe gateway/ folder is required (clone the full repo)."),
    );
  }

  return new PythonRunner(runtime.pythonExecutable, script, runtime.gatewayDir);
}

function registerIpcHandlers(runner: PythonRunner): void {
  ipcMain.handle(IPC_CHANNELS.generatePatch, async (_event, request: GeneratePatchRequest) => {
    assertFirmwareBinary(request.basePath);
    assertFirmwareBinary(request.targetPath);
    return runner.runReleaseBuilder(request.basePath, request.targetPath, request.versionTag);
  });

  ipcMain.handle(IPC_CHANNELS.pickBinary, async () => {
    const result = await dialog.showOpenDialog({
      title: "Select firmware binary",
      filters: [{ name: "IoT firmware (.bin/.elf/.hex)", extensions: ["bin", "elf", "hex"] }],
      properties: ["openFile"],
    });
    return result.canceled || result.filePaths.length === 0 ? null : result.filePaths[0];
  });

  // Phone-reachable RPC (the HTTPS tunnel URL demo-up.bat exports). MetaMask
  // Mobile only accepts HTTPS, so anything else is treated as unset.
  ipcMain.handle(IPC_CHANNELS.phoneRpcUrl, async () => {
    const url = (process.env.DELTA_PHONE_RPC_URL ?? "").trim().replace(/\/+$/, "");
    return /^https:\/\/[^/\s]+$/.test(url) ? url : null;
  });
}

app.whenReady().then(() => {
  try {
    registerIpcHandlers(buildPythonRunner());
  } catch (error) {
    dialog.showErrorBox("SecureOTA gateway unavailable", (error as Error).message);
    app.quit();
    return;
  }

  const preloadPath = path.join(__dirname, "preload.js");
  const rendererUrl = process.env.VITE_DEV_SERVER_URL ?? null;
  const rendererFile = resolveBundledRendererFile(__dirname);

  if (!rendererUrl && !existsSync(rendererFile)) {
    dialog.showErrorBox(
      "Renderer not found",
      "The bundled UI is missing.\n\nRun `npm run build:app` inside the desktop/ folder first.",
    );
    app.quit();
    return;
  }

  createMainWindow({ preloadPath, rendererUrl, rendererFile });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow({ preloadPath, rendererUrl, rendererFile });
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
