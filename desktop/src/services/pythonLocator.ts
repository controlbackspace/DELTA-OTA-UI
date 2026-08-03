import { existsSync } from "node:fs";
import path from "node:path";

export interface GatewayRuntime {
  gatewayDir: string;
  pythonExecutable: string;
  packaged: boolean;
}

export interface ElectronApp {
  isPackaged: boolean;
  getAppPath(): string;
}

/**
 * Locates the gateway runtime (Python venv + release-builder sources) for both
 * layouts: dev (repo checkout) and packaged (installed app, resources/gateway).
 * Environment overrides exist for testing and exotic setups.
 */
export class PythonLocator {
  constructor(
    private readonly app: ElectronApp,
    private readonly resourcesPath: string | undefined = process.resourcesPath,
  ) {}

  locate(): GatewayRuntime {
    const packaged = this.app.isPackaged;

    const gatewayDir = process.env.SECUREOTA_GATEWAY_DIR
      ? path.resolve(process.env.SECUREOTA_GATEWAY_DIR)
      : packaged
        ? path.join(this.resourcesPath ?? "", "gateway")
        : path.join(path.dirname(this.app.getAppPath()), "gateway");

    const venvPython = path.join(gatewayDir, ".venv", "Scripts", "python.exe");
    const pythonExecutable =
      process.env.SECUREOTA_PYTHON ?? (existsSync(venvPython) ? venvPython : "python");

    return { gatewayDir, pythonExecutable, packaged };
  }
}
