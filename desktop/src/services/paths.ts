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

// NOTE: the accepted list mirrors ui/secureota-ui/src/lib/firmwareFiles.ts
// (separate runtimes cannot share the module). Keep both lists in sync.
const FIRMWARE_EXTENSIONS = [".bin", ".elf", ".hex"];

/** assertReadableBinary plus firmware-type enforcement for patch inputs. */
export function assertFirmwareBinary(filePath: string): void {
  assertReadableBinary(filePath);
  if (!FIRMWARE_EXTENSIONS.some((ext) => filePath.toLowerCase().endsWith(ext))) {
    throw new Error(`Unsupported firmware type: ${filePath} (expected .bin/.elf/.hex)`);
  }
}
