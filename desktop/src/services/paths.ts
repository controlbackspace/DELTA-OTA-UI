import { existsSync, statSync } from "node:fs";
import path from "node:path";

/** Pure path-resolution helpers — no side effects, easy to unit test. */

export function resolveMakeReleaseScript(gatewayDir: string): string {
  return path.join(gatewayDir, "make_release.py");
}

export function resolveBundledRendererFile(distBaseDir: string): string {
  return path.join(distBaseDir, "renderer", "index.html");
}

export function assertReadableBinary(filePath: string): void {
  if (!filePath) {
    throw new Error("No file path provided");
  }
  if (!existsSync(filePath)) {
    throw new Error(`File does not exist: ${filePath}`);
  }
  if (!statSync(filePath).isFile()) {
    throw new Error(`Not a regular file: ${filePath}`);
  }
}
