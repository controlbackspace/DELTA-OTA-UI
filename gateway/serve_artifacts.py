"""Serve delta patches over plain HTTP on the LAN (stdlib only).

Makes make_release.py download URLs resolvable off-box: any host on the LAN
can curl the exact patch bytes the UI displays. Serves ONLY patch_*.bin and
gateway_status.json (the console tracker's live feed, CORS-enabled) —
directory listings, state files, encrypted frames, and block slices all 404,
and path traversal outside artifacts/ is rejected. No auth, no TLS — demo/
test tooling for trusted local networks only.

Run from anywhere:  python gateway/serve_artifacts.py [--port 8000]
"""
import argparse
import fnmatch
import functools
import http.server
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "secureota" / "gateway_runtime"))

from secureota.release_builder.core import ARTIFACT_HTTP_PORT, gateway_lan_ip
from gateway_config import status_path

# The only files ever served: release delta patches by filename convention,
# plus the gateway's live status (read by the console's deployment tracker;
# holds no secrets - the key appears only as a fingerprint).
PATCH_GLOB = "patch_*.bin"
STATUS_FILE_NAME = "gateway_status.json"


def _requested_name(raw_path: str) -> str:
    return Path(raw_path.split("?", 1)[0].split("#", 1)[0]).name


def _is_served(name: str) -> bool:
    return fnmatch.fnmatchcase(name, PATCH_GLOB) or name == STATUS_FILE_NAME


class PatchOnlyHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler narrowed to PATCH_GLOB + the status file
    (no listings, ever)."""

    server_version = "DeltaOTA-Artifacts/1.0"

    def end_headers(self):
        # The console renderer is a file:// page: it may read the status file
        # cross-origin (and must always get the live copy) and download a patch to
        # verify it against the ledger.
        name = _requested_name(self.path)
        if name == STATUS_FILE_NAME:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
        elif fnmatch.fnmatchcase(name, PATCH_GLOB):
            self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def list_directory(self, path):
        self.send_error(404, "Directory listings are disabled")
        return None

    def translate_path(self, path):
        # Resolve against artifacts/ and reject anything escaping it (..).
        artifact_dir = Path(self.directory).resolve()
        rel = path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        if Path(rel).name == STATUS_FILE_NAME:
            return str(status_path())   # the gateway's live feed lives outside artifacts/
        candidate = (artifact_dir / rel).resolve()
        try:
            candidate.relative_to(artifact_dir)
        except ValueError:
            return str(artifact_dir / "__forbidden__")
        return str(candidate)

    def do_GET(self):
        if not _is_served(_requested_name(self.path)):
            self.send_error(404, "Only delta patches are served here")
            return
        super().do_GET()

    def do_HEAD(self):
        if not _is_served(_requested_name(self.path)):
            self.send_error(404, "Only delta patches are served here")
            return
        super().do_HEAD()

    def log_message(self, *args):
        sys.stdout.write("[Artifacts] %s\n" % (args[1] if len(args) > 1 else args[0],))


def make_server(port: int = ARTIFACT_HTTP_PORT) -> http.server.ThreadingHTTPServer:
    # Same artifact dir the gateway writes gateway_status.json into (the packaged
    # exe sets DELTA_ARTIFACT_DIR next to itself; plain Python uses gateway/artifacts).
    env_dir = os.environ.get("DELTA_ARTIFACT_DIR")
    artifact_dir = Path(env_dir) if env_dir else Path(__file__).resolve().parent / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    handler = functools.partial(PatchOnlyHandler, directory=str(artifact_dir))
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), handler)
    print(f"[Artifacts] Serving {PATCH_GLOB} from {artifact_dir} at "
          f"http://{gateway_lan_ip()}:{port}/ (Ctrl+C to stop)")
    return server


def main():
    parser = argparse.ArgumentParser(description="Serve delta patches over HTTP.")
    parser.add_argument("--port", type=int, default=ARTIFACT_HTTP_PORT)
    args = parser.parse_args()

    server = make_server(args.port)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
