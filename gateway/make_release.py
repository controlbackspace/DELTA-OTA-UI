import argparse
import os
from secureota.release_builder.core import build_release

def main():
    # 1. Initialize argparse
    parser = argparse.ArgumentParser(description="Generate Delta-OTA patch and metadata.")
    
    # 2. Add your three required arguments: base_file, target_file, and version_tag
    parser.add_argument("base_file", help="Path to the base binary file.")
    parser.add_argument("target_file", help="Path to the target binary file.")
    parser.add_argument("version_tag", help="Version tag for the release.")
    
    args = parser.parse_args()
    print(f"Building release for {args.version_tag}...")
    
    # 3. Open and read the base_file and target_file into memory using "rb" mode
    with open(args.base_file, "rb") as f:
        base_bytes = f.read()
    with open(args.target_file, "rb") as f:
        target_bytes = f.read()
        
    # 4. Call your build_release function and unpack the tuple
    metadata, patch_bytes = build_release(base_bytes, target_bytes, args.version_tag)
    
    # 5. Define the output path
    output_filename = f"patch_{args.version_tag}.bin"
    os.makedirs("artifacts", exist_ok=True)
    output_path = os.path.join("artifacts", output_filename)
    
    # 6. Write the patch_bytes to the output_path using "wb" mode
    with open(output_path, "wb") as f:
        f.write(patch_bytes)
        
    # 7. Print the results clearly to the terminal
    print("\n--- Release Metadata ---")
    print(f"Golden Hash: {metadata.golden_hash}")
    print(f"Patch Size: {metadata.patch_size} bytes")
    print(f"Compression Ratio: {metadata.compression_ratio}")
    print(f"Patch saved to: {output_path}")

if __name__ == "__main__":
    main()
