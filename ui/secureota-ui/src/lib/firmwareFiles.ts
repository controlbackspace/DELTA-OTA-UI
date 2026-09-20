/**
 * Accepted IoT firmware upload types — single source of truth for the
 * dropzone accept attribute, hook-level validation, and user-facing messages.
 *
 * NOTE: the desktop main process mirrors this list in
 * desktop/src/services/paths.ts (assertFirmwareBinary) because the two
 * runtimes cannot share modules. Keep both lists in sync.
 *
 * Extension (not MIME) is authoritative: firmware binaries report generic or
 * empty MIME types, so sniffing is unreliable. bsdiff itself is
 * format-agnostic — this list is a policy gate, not a technical limit.
 */
export const FIRMWARE_EXTENSIONS = [".bin", ".elf", ".hex"] as const;

export type FirmwareExtension = (typeof FIRMWARE_EXTENSIONS)[number];

/** Case-insensitive extension check against FIRMWARE_EXTENSIONS. */
export function isAcceptedFirmwareFile(filename: string): boolean {
  const lower = filename.toLowerCase();
  return FIRMWARE_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

/** Value for <input type="file" accept="...">. */
export const FIRMWARE_ACCEPT_ATTR = FIRMWARE_EXTENSIONS.join(",");

/** Human-readable list for labels and error messages. */
export const FIRMWARE_ACCEPT_LABEL = ".bin / .elf / .hex";
