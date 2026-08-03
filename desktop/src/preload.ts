import { contextBridge, ipcRenderer, webUtils } from "electron";
import type { GeneratePatchRequest, ReleaseResult } from "./contracts/release";

// Sandboxed preloads cannot require() local modules, so channel names are
// inlined here. They MUST match desktop/src/contracts/ipc.ts (authoritative).
const IPC_CHANNELS = {
  generatePatch: "patch:generate",
  pickBinary: "dialog:pick-bin",
} as const;

/** The only surface exposed to the renderer — narrow, explicit, no Node access. */
const desktopApi = {
  generatePatch: (request: GeneratePatchRequest): Promise<ReleaseResult> =>
    ipcRenderer.invoke(IPC_CHANNELS.generatePatch, request),
  pickBinary: (): Promise<string | null> => ipcRenderer.invoke(IPC_CHANNELS.pickBinary),
  getPathForFile: (file: File): string => webUtils.getPathForFile(file),
};

contextBridge.exposeInMainWorld("desktopAPI", desktopApi);
