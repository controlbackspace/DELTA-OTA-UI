/**
 * Packaged-layout smoke test (plain Node): locates the gateway via
 * PythonLocator as an installed app would, then runs the release builder
 * end-to-end through PythonRunner. Requires: desktop/dist compiled and a venv
 * created in the target resources/gateway (as setup-gateway.bat would do).
 * Usage: node scripts/package-smoke.cjs <resourcesPath> <baseBin> <targetBin>
 */
const path = require("node:path");
const fs = require("node:fs");
const { PythonLocator } = require("../dist/services/pythonLocator");
const { PythonRunner } = require("../dist/services/pythonRunner");
const { resolveMakeReleaseScript } = require("../dist/services/paths");

const resourcesPath = path.resolve(process.argv[2]);
const baseBin = path.resolve(process.argv[3]);
const targetBin = path.resolve(process.argv[4]);

const locator = new PythonLocator(
  { isPackaged: true, getAppPath: () => path.join(resourcesPath, "app.asar") },
  resourcesPath,
);
const runtime = locator.locate();
console.log(`[pkg-smoke] gatewayDir: ${runtime.gatewayDir}`);
console.log(`[pkg-smoke] python:    ${runtime.pythonExecutable}`);

const script = resolveMakeReleaseScript(runtime.gatewayDir);
if (!fs.existsSync(script)) {
  console.error("[pkg-smoke] FAILED: make_release.py not found in resources/gateway");
  process.exit(1);
}

const runner = new PythonRunner(runtime.pythonExecutable, script, runtime.gatewayDir);
runner
  .runReleaseBuilder(baseBin, targetBin, "pkgtest")
  .then((result) => {
    console.log(`[pkg-smoke] OK: version=${result.version_tag} hash=${result.golden_hash.slice(0, 8)} url=${result.patch_url}`);
    process.exit(result.version_tag === "pkgtest" ? 0 : 1);
  })
  .catch((error) => {
    console.error(`[pkg-smoke] FAILED: ${error.message}`);
    process.exit(1);
  });
