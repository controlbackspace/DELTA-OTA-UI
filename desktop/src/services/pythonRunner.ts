import { spawn } from "node:child_process";
import type { ReleaseResult } from "../contracts/release";

export class PythonExecutionError extends Error {
  constructor(
    message: string,
    public readonly exitCode: number | null,
    public readonly stderr: string,
  ) {
    super(message);
    this.name = "PythonExecutionError";
  }
}

/** Hard cap on a single release-builder run (spawn hangs are otherwise silent). */
const RELEASE_BUILDER_TIMEOUT_MS = 120_000;

/** Owns the child-process lifecycle and stdout parsing for the Python release builder. */
export class PythonRunner {
  constructor(
    private readonly pythonExecutable: string,
    private readonly scriptPath: string,
    private readonly workingDirectory: string,
  ) {}

  async runReleaseBuilder(
    basePath: string,
    targetPath: string,
    versionTag: string,
  ): Promise<ReleaseResult> {
    const args = [this.scriptPath, basePath, targetPath, versionTag, "--json"];
    const { stdout, stderr, exitCode } = await this.spawnCapture(args);

    if (exitCode !== 0) {
      throw new PythonExecutionError(
        `Python exited with code ${exitCode}: ${stderr.trim() || "unknown error"}`,
        exitCode,
        stderr,
      );
    }
    return this.parseResult(stdout);
  }

  private spawnCapture(
    args: string[],
  ): Promise<{ stdout: string; stderr: string; exitCode: number | null }> {
    return new Promise((resolve, reject) => {
      const child = spawn(this.pythonExecutable, args, {
        cwd: this.workingDirectory,
        windowsHide: true,
        shell: false,
      });

      let stdout = "";
      let stderr = "";
      let settled = false;

      const finish = (fn: () => void) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        fn();
      };

      const timer = setTimeout(() => {
        finish(() => {
          child.kill();
          reject(
            new PythonExecutionError(
              "Release builder timed out after 120s (is the gateway venv intact?)",
              null,
              stderr,
            ),
          );
        });
      }, RELEASE_BUILDER_TIMEOUT_MS);
      timer.unref();

      child.stdout.on("data", (chunk: Buffer) => {
        stdout += chunk.toString("utf8");
      });
      child.stderr.on("data", (chunk: Buffer) => {
        stderr += chunk.toString("utf8");
      });
      child.on("error", (err) => {
        finish(() => {
          reject(
            new PythonExecutionError(`Failed to launch python: ${err.message}`, null, stderr),
          );
        });
      });
      child.on("close", (code) => {
        finish(() => {
          resolve({ stdout, stderr, exitCode: code });
        });
      });
    });
  }

  private parseResult(stdout: string): ReleaseResult {
    const jsonStart = stdout.indexOf("{");
    if (jsonStart === -1) {
      throw new PythonExecutionError("No JSON object found in python stdout", null, stdout);
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(stdout.slice(jsonStart));
    } catch (err) {
      throw new PythonExecutionError(
        `Invalid JSON in python stdout: ${(err as Error).message}`,
        null,
        stdout,
      );
    }
    return this.normalize(parsed as Partial<ReleaseResult>);
  }

  /** Pass-through: the CLI emits the real LAN download URL. No URL is ever
      synthesized here — an absent URL surfaces as "" so callers must cope. */
  private normalize(raw: Partial<ReleaseResult>): ReleaseResult {
    const versionTag = raw.version_tag ?? "v1.1";
    const goldenHash = raw.golden_hash ?? "";

    return {
      version_tag: versionTag,
      golden_hash: goldenHash,
      patch_size: raw.patch_size ?? 0,
      compression_ratio: raw.compression_ratio ?? 0,
      patch_url: raw.patch_url ?? "",
      ipfs_cid: raw.ipfs_cid ?? "",
      patch_path: raw.patch_path ?? "",
    };
  }
}
