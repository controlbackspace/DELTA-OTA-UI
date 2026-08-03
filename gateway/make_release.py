import argparse
import json
import os
import re
import sys

from secureota.release_builder.core import build_release

TAG_RE = re.compile(r"[^A-Za-z0-9._-]")


def sanitize_version_tag(version_tag: str) -> str:
    """Guard against path traversal / odd characters leaking into filenames."""
    return TAG_RE.sub("_", version_tag)


def main():
    # 1. Initialize argparse
    parser = argparse.ArgumentParser(description="Generate Delta-OTA patch and metadata.")
    
    # 2. Add your three required arguments: base_file, target_file, and version_tag
    parser.add_argument("base_file", help="Path to the base binary file.")
    parser.add_argument("target_file", help="Path to the target binary file.")
    parser.add_argument("version_tag", help="Version tag for the release.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON metadata to stdout only (warnings go to stderr).",
    )
    
    args = parser.parse_args()

    version_tag = sanitize_version_tag(args.version_tag)
    if version_tag != args.version_tag:
        print(
            f"WARNING: version_tag sanitized to {version_tag!r}",
            file=sys.stderr,
        )
    if not version_tag:
        print("ERROR: version_tag is empty after sanitization.", file=sys.stderr)
        sys.exit(1)

    if not args.json:
        print(f"Building release for {version_tag}...")
    
    # 3. Open and read the base_file and target_file into memory using "rb" mode
    with open(args.base_file, "rb") as f:
        base_bytes = f.read()
    with open(args.target_file, "rb") as f:
        target_bytes = f.read()
        
    # 4. Call your build_release function and unpack the tuple
    metadata, patch_bytes = build_release(base_bytes, target_bytes, version_tag)
    
    # 5. Define the output path
    output_filename = f"patch_{version_tag}.bin"
    os.makedirs("artifacts", exist_ok=True)
    output_path = os.path.abspath(os.path.join("artifacts", output_filename))
    
    # 6. Write the patch_bytes to the output_path using "wb" mode
    with open(output_path, "wb") as f:
        f.write(patch_bytes)

    if args.json:
        # 7a. Machine-readable output: single JSON object on stdout
        print(json.dumps({
            "version_tag": metadata.version_tag,
            "golden_hash": metadata.golden_hash,
            "patch_size": metadata.patch_size,
            "compression_ratio": metadata.compression_ratio,
            "patch_url": metadata.patch_url,
            "patch_path": output_path,
        }))
        return

    # 7b. Human-readable output for terminal use
    print("\n--- Release Metadata ---")
    print(f"Golden Hash: {metadata.golden_hash}")
    print(f"Patch Size: {metadata.patch_size} bytes")
    print(f"Compression Ratio: {metadata.compression_ratio}")
    print(f"Patch saved to: {output_path}")

if __name__ == "__main__":
    main()
