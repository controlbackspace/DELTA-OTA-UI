"""Serve delta patches over plain HTTP on the LAN (stdlib only).

Makes make_release.py download URLs resolvable off-box: any host on the LAN
can curl the exact patch bytes the UI displays. Serves ONLY patch_*.bin —
directory listings, state files, encrypted frames, and block slices all 404,
and path traversal outside artifacts/ is rejected. No auth, no TLS — demo/
test tooling for trusted local networks only.

Run from anywhere:  python gateway/serve_artifacts.py [--port 8000]
"""
import argparse
import fnmatch
import functools
import http.server
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from secureota.release_builder.core import ARTIFACT_HTTP_PORT, gateway_lan_ip

# The only files ever served: release delta patches by filename convention.
PATCH_GLOB = "patch_*.bin"


class PatchOnlyHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler narrowed to PATCH_GLOB (no listings, ever)."""

    server_version = "DeltaOTA-Artifacts/1.0"

    def list_directory(self, path):
        self.send_error(404, "Directory listings are disabled")
        return None

    def translate_path(self, path):
        # Resolve against artifacts/ and reject anything escaping it (..).
        artifact_dir = Path(self.directory).resolve()
        rel = path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        candidate = (artifact_dir / rel).resolve()
        try:
            candidate.relative_to(artifact_dir)
        except ValueError:
            return str(artifact_dir / "__forbidden__")
        return str(candidate)

    def do_GET(self):
        name = Path(self.path.split("?", 1)[0].split("#", 1)[0]).name
        if not fnmatch.fnmatchcase(name, PATCH_GLOB):
            self.send_error(404, "Only delta patches are served here")
            return
        super().do_GET()

    def do_HEAD(self):
        name = Path(self.path.split("?", 1)[0].split("#", 1)[0]).name
        if not fnmatch.fnmatchcase(name, PATCH_GLOB):
            self.send_error(404, "Only delta patches are served here")
            return
        super().do_HEAD()

    def log_message(self, *args):
        sys.stdout.write("[Artifacts] %s\n" % (args[1] if len(args) > 1 else args[0],))


def main():
    parser = argparse.ArgumentParser(description="Serve delta patches over HTTP.")
    parser.add_argument("--port", type=int, default=ARTIFACT_HTTP_PORT)
    args = parser.parse_args()

    artifact_dir = Path(__file__).resolve().parent / "artifacts"
    artifact_dir.mkdir(exist_ok=True)

    handler = functools.partial(PatchOnlyHandler, directory=str(artifact_dir))
    server = http.server.ThreadingHTTPServer(("0.0.0.0", args.port), handler)

    print(f"[Artifacts] Serving {PATCH_GLOB} from {artifact_dir} at "
          f"http://{gateway_lan_ip()}:{args.port}/ (Ctrl+C to stop)")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
