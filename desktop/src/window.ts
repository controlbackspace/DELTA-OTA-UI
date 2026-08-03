import { BrowserWindow } from "electron";

export interface WindowOptions {
  preloadPath: string;
  rendererUrl: string | null;
  rendererFile: string;
}

/** Single responsibility: window construction. No IPC, no business logic. */
export function createMainWindow(options: WindowOptions): BrowserWindow {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    title: "Blockchain-Secured IoT Firmware Console",
    backgroundColor: "#05080f",
    webPreferences: {
      preload: options.preloadPath,
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
    },
  });

  if (options.rendererUrl) {
    void win.loadURL(options.rendererUrl);
  } else {
    void win.loadFile(options.rendererFile);
  }
  return win;
}
