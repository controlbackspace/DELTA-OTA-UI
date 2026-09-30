/**
 * Desktop runtime bridge (Electron).
 *
 * The renderer depends on this narrow interface — never on Electron internals.
 * In a plain browser (vite dev server without the Electron shell) the bridge is
 * absent and the pipeline falls back to its simulation mode.
 */

export interface ReleaseResult {
  version_tag: string;
  golden_hash: string;
  patch_size: number;
  compression_ratio: number;
  patch_url: string;
  ipfs_cid: string;
  patch_path: string;
}

export interface DesktopBridge {
  generatePatch(basePath: string, targetPath: string, versionTag: string): Promise<ReleaseResult>;
  pickBinary(): Promise<string | null>;
  getPathForFile(file: File): string;
  /** HTTPS tunnel RPC exported by demo-up.bat (null when unset). Optional:
   *  an older desktop build without this channel simply lacks it. */
  getPhoneRpcUrl?(): Promise<string | null>;
}

declare global {
  interface Window {
    desktopAPI?: DesktopBridge;
  }
}

export function getDesktopBridge(): DesktopBridge | null {
  return typeof window !== "undefined" ? (window.desktopAPI ?? null) : null;
}

export function deriveVersionTag(filename: string): string {
  const match = filename.match(/v?\d+(?:\.\d+)+/);
  return match ? match[0] : "v1.1";
}
