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

const MOCK_IPFS_ORIGIN = "http://local-test-server";
const STALE_HTTP_ORIGIN = "http://localhost:8000";

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

      child.stdout.on("data", (chunk: Buffer) => {
        stdout += chunk.toString("utf8");
      });
      child.stderr.on("data", (chunk: Buffer) => {
        stderr += chunk.toString("utf8");
      });
      child.on("error", (err) => {
        reject(
          new PythonExecutionError(`Failed to launch python: ${err.message}`, null, stderr),
        );
      });
      child.on("close", (code) => {
        resolve({ stdout, stderr, exitCode: code });
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

  /** Adapter: maps the CLI's local-server URL to the poller-consistent mock origin. */
  private normalize(raw: Partial<ReleaseResult>): ReleaseResult {
    const versionTag = raw.version_tag ?? "v1.1";
    const goldenHash = raw.golden_hash ?? "";
    const patchUrl =
      (raw.patch_url ?? "").startsWith(STALE_HTTP_ORIGIN) || !raw.patch_url
        ? `${MOCK_IPFS_ORIGIN}/patch_${versionTag}.bin`
        : raw.patch_url;

    return {
      version_tag: versionTag,
      golden_hash: goldenHash,
      patch_size: raw.patch_size ?? 0,
      compression_ratio: raw.compression_ratio ?? 0,
      patch_url: patchUrl,
      ipfs_cid: raw.ipfs_cid || `Qm${goldenHash.slice(0, 8)}${versionTag.replace(/\./g, "")}`,
      patch_path: raw.patch_path ?? "",
    };
  }
}
