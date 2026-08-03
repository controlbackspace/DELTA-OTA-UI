export interface GeneratePatchRequest {
  basePath: string;
  targetPath: string;
  versionTag: string;
}

export interface ReleaseResult {
  version_tag: string;
  golden_hash: string;
  patch_size: number;
  compression_ratio: number;
  patch_url: string;
  ipfs_cid: string;
  patch_path: string;
}
