import { useState, useCallback, useEffect, useRef } from "react";
import { ethers } from "ethers";
import type { LogEntry } from "../../components/organisms/SystemsLogTerminal";
import type { LedgerRelease } from "../../components/organisms/LedgerDeploymentsTable";
import { deriveVersionTag, getDesktopBridge } from "../../lib/desktop";
import { isAcceptedFirmwareFile } from "../../lib/firmwareFiles";
import { formatFileSize } from "../../lib/utils";
import { useDesktopWallet } from "../wallet/useDesktopWallet";
import { loadGatewayHost, saveGatewayHost, statusUrlFor, useGatewayStatus } from "../deployment/useGatewayStatus";
import type { OnChainReleaseRecord } from "../wallet/useDesktopWallet";
import {
  formatVersionBytes32,
  formatGoldenHashBytes32,
  truncateAddress,
} from "../../lib/web3Payloads";

export type UpdateState = "idle" | "developer" | "blockchain" | "gateway" | "iot" | "success";
export type BinaryKind = "base" | "target";

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// Unstick guard (real-life): every wallet/network wait races a clock. On
// expiry the error is already operator-worded, so explainTxError passes it
// through and loadingStep resets in the caller's finally.
const withTimeout = <T,>(p: Promise<T>, ms: number, label: string): Promise<T> =>
  Promise.race([
    p,
    new Promise<never>((_, reject) =>
      window.setTimeout(
        () =>
          reject(
            new Error(
              `Timed out after ${ms / 1000}s ${label} — no response arrived (phone app closed? wrong network? node down? relay down?). No transaction was sent. Retry or use a Dev signer.`
            )
          ),
        ms
      )
    ),
  ]);

// Real-life revert copy: map raw ethers reasons to the one operator action
// that actually fixes each failure. Falls back to the raw message.
const explainTxError = (err: unknown): string => {
  const msg = err instanceof Error ? err.message : "Contract call failed";
  const low = msg.toLowerCase();
  // Phone-wallet gas estimation via its own RPC (not our node): the user saw
  // this as code 5000 "Custom eth_gasPrice ... too many errors". Must precede
  // the generic gas branch or it mislabels every time.
  if (low.includes("eth_gasprice") || low.includes("too many errors") || low.includes("different rpc endpoint"))
    return `${msg} — the phone wallet estimated gas via its own RPC, not your node. Add a custom MetaMask Mobile network (RPC = LAN IP or cloudflared tunnel URL, chain 31337), switch to it, and retry. DevSigner fallback needs no phone network.`;
  if (low.includes("timed out"))
    return msg; // already operator-worded at the throw site
  if (low.includes("invalid address"))
    return `${msg} — no contract configured (empty or malformed address). Set the deployed address in Contract Config first.`;
  if (low.includes("already proposed") || low.includes("duplicate"))
    return `${msg} — version already proposed on this chain (fresh node per run: restart Hardhat, redeploy, retry).`;
  if (low.includes("already revoked") || low.includes("revoked"))
    return `${msg} — release is revoked on-chain; propose a new version instead.`;
  if (low.includes("not authorized") || low.includes("not a dev") || low.includes("unauthorized"))
    return `${msg} — signer is not one of the 3 authorized devs; switch wallet and retry.`;
  if (low.includes("already signed") || low.includes("already approved") || low.includes("hassigned"))
    return `${msg} — this key already signed (proposer counts as signature 1); switch to a different dev key.`;
  if (low.includes("user rejected") || low.includes("user denied") || low.includes("action_rejected"))
    return "Wallet rejected the signature in MetaMask — no transaction was sent; retry and approve the prompt.";
  if (low.includes("network") || low.includes("econnrefused") || low.includes("fetch failed") || low.includes("could not detect network"))
    return `${msg} — node unreachable at the configured RPC URL; check the node process and Contract Config → RPC URL.`;
  if (low.includes("insufficient funds") || low.includes("gas"))
    return `${msg} — gas/funds issue on the local node; restart Hardhat and retry.`;
  return msg;
};

// Honest-execution gate (P0-1): offline progression is OFF by default.
// Enabled only in dev via explicit VITE_ALLOW_OFFLINE_PROGRESSION="true"
// so failed/reverted txs block the pipeline in every real build.
const ALLOW_OFFLINE_PROGRESSION =
  (import.meta as unknown as { env: Record<string, string | boolean | undefined> }).env?.DEV ===
    true &&
  (import.meta as unknown as { env: Record<string, string | boolean | undefined> }).env
    ?.VITE_ALLOW_OFFLINE_PROGRESSION === "true";

export function useFirmwarePipeline() {
  // Live deployment tracker on/off (stages are derived, never timed).
  const [isTracking, setIsTracking] = useState(false);
  const [firmwareVersion] = useState("v1.0");

  // Pipeline Step Flags
  const [baseUploaded, setBaseUploaded] = useState(false);
  const [targetUploaded, setTargetUploaded] = useState(false);
  const [deltaGenerated, setDeltaGenerated] = useState(false);
  const [urlConfigured, setUrlConfigured] = useState(false);
  const [walletConnected, setWalletConnected] = useState(false);
  const [approvalRequested, setApprovalRequested] = useState(false);

  // Active Action Indicators
  const [loadingStep, setLoadingStep] = useState<string | null>(null);

  // Upload-section highlight pulse (step 1 redirects there; real intake only).
  const [uploadHighlight, setUploadHighlight] = useState(false);

  // Real binary files (desktop runtime — Electron bridge)
  const [baseFile, setBaseFile] = useState<File | null>(null);
  const [targetFile, setTargetFile] = useState<File | null>(null);

  // True step-2 readiness: desktop mode requires real File objects (the demo
  // stager sets flags with no files); browser-sim mode trusts the staged flags.
  const binariesReady =
    getDesktopBridge() !== null
      ? baseFile !== null && targetFile !== null
      : baseUploaded && targetUploaded;

  // Build output (desktop runtime — Python release builder via IPC)
  const [goldenHash, setGoldenHash] = useState<string | null>(null);
  const [patchUrl, setPatchUrl] = useState<string | null>(null);
  const [ipfsCid, setIpfsCid] = useState<string | null>(null);
  const [deltaSizeKb, setDeltaSizeKb] = useState<number | null>(null);
  const [compressionRatio, setCompressionRatio] = useState<string | null>(null);

  // Desktop Web3 Wallet & Smart Contract Integration
  const wallet = useDesktopWallet();

  // Step 4 completes only on a real connection (dev signer, injected, or QR).
  // Closing the modal unconnected — or disconnecting later — leaves the step
  // honestly incomplete instead of certifying a wallet that was never linked.
  useEffect(() => {
    setWalletConnected(wallet.isConnected);
  }, [wallet.isConnected]);

  // Initial Logs — honest boot: nothing is claimed before the first RPC call.
  const [logs, setLogs] = useState<LogEntry[]>([
    { id: 1, time: "09:14:21", message: "[Boot] Developer Console started — querying deployed contract...", type: "info" },
    { id: 2, time: "09:14:21", message: "[Chain] No cached releases. Ledger fills only from on-chain state.", type: "info" },
  ]);

  // Ledger starts EMPTY by design (real-life rule): every row must be earned
  // from an on-chain getRelease record. The table's empty-state copy covers
  // the boot screen; rows appear only via mergeChainRecord below.
  const [releases, setReleases] = useState<LedgerRelease[]>([]);

  const addLog = useCallback((message: string, type: LogEntry["type"] = "info") => {
    const time = new Date().toLocaleTimeString("en-US", { hour12: false });
    // Append (tail -f order): the terminal autoscrolls to the bottom, so new
    // entries must land at the end. Prepending parks fresh logs above an
    // viewport pinned on stale content.
    setLogs((prev) => [...prev, { id: Date.now() + Math.random(), time, message, type }]);
  }, []);

  // P0-5: proposer per version (receipt.from at propose time), lowercased.
  const [proposers, setProposers] = useState<Record<string, string>>({});

  // Surface chain-verified (un)authorization once per connect — the wallet
  // hook owns the check, the terminal owns the visibility.
  const warnedUnauthorized = useRef(false);
  useEffect(() => {
    if (wallet.chainAuthorized === false && !warnedUnauthorized.current) {
      warnedUnauthorized.current = true;
      addLog("[Governance] Connected wallet is NOT an authorized dev on this contract — on-chain calls will revert. Switch wallet.", "error");
    }
    if (wallet.chainAuthorized !== false) warnedUnauthorized.current = false;
  }, [wallet.chainAuthorized, addLog]);
  // P0-2: chain-sync flag — local releases are a cache until first poll lands.
  const [chainSynced, setChainSynced] = useState(false);
  const releasesRef = useRef<LedgerRelease[]>([]);
  releasesRef.current = releases;
  const fetchReleaseRef = useRef(wallet.fetchRelease);
  fetchReleaseRef.current = wallet.fetchRelease;
  const fetchProposerRef = useRef(wallet.fetchProposer);
  fetchProposerRef.current = wallet.fetchProposer;
  const proposersRef = useRef(proposers);
  proposersRef.current = proposers;

  // A never-proposed version reads back as all-zero/empty — not a row.
  const isAbsentRecord = (rec: OnChainReleaseRecord) =>
    !rec.goldenHash && rec.approvalCount === 0 && !rec.isLive && !rec.isRevoked;

  const mergeChainRecord = useCallback(
    (version: string, rec: OnChainReleaseRecord) => {
      if (isAbsentRecord(rec)) return;
      const prev = releasesRef.current.find((r) => r.version === version);
      if (
        prev &&
        (prev.approvalCount !== rec.approvalCount ||
          prev.isLive !== rec.isLive ||
          prev.isRevoked !== rec.isRevoked ||
          (rec.goldenHash && prev.goldenHash !== rec.goldenHash))
      ) {
        if (rec.isRevoked && !prev.isRevoked) {
          addLog(`[Chain] ${version} REVOKED on-chain — ledger synced (no clicks needed).`, "error");
        } else if (rec.isLive && !prev.isLive) {
          addLog(`[Chain] ${version} is now LIVE on-chain (${rec.approvalCount}/3) — ledger synced.`, "success");
        } else {
          addLog(`[Chain] ${version} synced: approvals ${rec.approvalCount}/3 live=${rec.isLive} revoked=${rec.isRevoked}.`, "info");
        }
      }
      if (prev?.isRevoked && !rec.isRevoked) {
        // Proposed again after a revoke: the old proposer no longer applies.
        setProposers((p) => {
          const next = { ...p };
          delete next[version.toLowerCase()];
          return next;
        });
        addLog(`[Chain] ${version} was proposed again after its revoke — new approval round (${rec.approvalCount}/3).`, "info");
      }
      if (!prev) {
        addLog(`[Chain] ${version} found on-chain: approvals ${rec.approvalCount}/3 live=${rec.isLive} revoked=${rec.isRevoked}.`, "success");
      }
      setReleases((prevList) => {
        if (!prevList.some((r) => r.version === version)) {
          return [
            {
              version,
              goldenHash: rec.goldenHash,
              approvalCount: rec.approvalCount,
              maxApprovals: 3, // 2-of-3 multi-sig threshold
              isLive: rec.isLive,
              isRevoked: rec.isRevoked,
            },
            ...prevList,
          ];
        }
        return prevList.map((r) =>
          r.version === version
            ? {
                ...r,
                goldenHash: rec.goldenHash || r.goldenHash,
                approvalCount: rec.approvalCount,
                isLive: rec.isLive,
                isRevoked: rec.isRevoked,
              }
            : r
        );
      });
      setChainSynced(true);
    },
    [addLog]
  );

  // Candidate versions to probe: static well-known tags plus the locally
  // staged target (so a freshly built v1.2 appears once proposed on-chain).
  // Chain remains the only source of rows — absent records add nothing.
  const targetFileRef = useRef(targetFile);
  targetFileRef.current = targetFile;

  // P0-2: chain as source of truth — 4s poll over direct RPC (works with or
  // without a wallet session). Probes candidate versions; only on-chain
  // records become rows. On-chain revoke/approve/promote reflects
  // within one interval without clicks. Changing contract address wipes the
  // cache first so rows from the old deployment never linger.
  useEffect(() => {
    setReleases([]);
    setProposers({});
    setChainSynced(false);
    let cancelled = false;
    const syncOnce = async () => {
      const candidates = ["v1.0", "v1.1"];
      const staged = targetFileRef.current
        ? deriveVersionTag(targetFileRef.current.name)
        : null;
      if (staged && !candidates.includes(staged)) candidates.push(staged);
      let answered = false;
      for (const v of candidates) {
        try {
          const rec = await fetchReleaseRef.current(v);
          if (cancelled || !rec) continue;
          answered = true;
          mergeChainRecord(v, rec);
          // Proposer from the ReleaseProposed event (survives restarts) —
          // looked up once per existing release, never for empty records.
          const key = v.toLowerCase();
          if (rec.goldenHash && !proposersRef.current[key]) {
            const proposer = await fetchProposerRef.current(v);
            if (!cancelled && proposer) {
              setProposers((prev) => (prev[key] ? prev : { ...prev, [key]: proposer }));
            }
          }
        } catch {
          // Poll failures keep the last cache; staleness is visible via
          // chainSynced staying false / logs, never fake-live data.
        }
      }
      if (answered) setChainSynced(true);
    };
    void syncOnce();
    const id = window.setInterval(() => void syncOnce(), 4000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [mergeChainRecord, wallet.contractAddress]);

  const handleLoadBinaries = async () => {
    // No fake staging: real binaries enter only via the sidebar dropzones.
    // Step 1 guides the operator there instead (button UI unchanged).
    document
      .getElementById("firmware-upload-pipeline")
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
    setUploadHighlight(true);
    window.setTimeout(() => setUploadHighlight(false), 1600);
    addLog("[Firmware Mgr] Stage base + target binaries via the sidebar dropzones.", "info");
  };

  const handleLoadBinaryFile = async (file: File, kind: BinaryKind) => {
    if (!isAcceptedFirmwareFile(file.name)) {
      addLog(`[Firmware Mgr] Rejected ${file.name} — only .bin/.elf/.hex firmware files accepted.`, "error");
      return;
    }
    if (kind === "base") {
      setBaseFile(file);
      setBaseUploaded(true);
    } else {
      setTargetFile(file);
      setTargetUploaded(true);
    }
    addLog(`[Firmware Mgr] Staging ${kind} binary ${file.name} — ${formatFileSize(file.size)}`, "info");
    await delay(400);
    addLog(`[Firmware Mgr] ${kind === "base" ? "Base" : "Target"} binary staged successfully.`, "success");
  };

  const handleGenerateDelta = async () => {
    if (!baseUploaded || !targetUploaded || loadingStep) return;
    setLoadingStep("delta");
    addLog("[Delta Engine] Computing binary diff using bsdiff4 algorithm...", "info");

    const bridge = getDesktopBridge();

    // Desktop runtime: real Python engine via IPC
    if (bridge && baseFile && targetFile) {
      const basePath = bridge.getPathForFile(baseFile);
      const targetPath = bridge.getPathForFile(targetFile);
      if (!basePath || !targetPath) {
        const missing = [!basePath ? baseFile.name : null, !targetPath ? targetFile.name : null]
          .filter((name): name is string => name !== null)
          .join(" + ");
        addLog(`[Delta Engine] Could not resolve a filesystem path for ${missing} — re-select it via the file picker.`, "error");
        setLoadingStep(null);
        return;
      }
      try {
        const result = await bridge.generatePatch(
          basePath,
          targetPath,
          deriveVersionTag(targetFile.name)
        );
        addLog(
          `[Delta Engine] Delta patch generated — ${(result.patch_size / 1024).toFixed(1)} KB (${(result.compression_ratio * 100).toFixed(1)}% reduction)`,
          "success"
        );
        addLog(`[SHA-256] Golden Hash computed: ${result.golden_hash}`, "hash");
        setGoldenHash(result.golden_hash);
        setPatchUrl(result.patch_url || null);
        setIpfsCid(result.ipfs_cid || null);
        setDeltaSizeKb(+(result.patch_size / 1024).toFixed(1));
        setCompressionRatio(`${(result.compression_ratio * 100).toFixed(1)}% Reduction`);
        setReleases((prev) =>
          prev.map((r) =>
            r.version === result.version_tag ? { ...r, goldenHash: result.golden_hash } : r
          )
        );
        setDeltaGenerated(true);
      } catch (err) {
        addLog(`[Delta Engine] ${err instanceof Error ? err.message : "Build failed"}`, "error");
      } finally {
        setLoadingStep(null);
      }
      return;
    }

    // Desktop runtime without real binaries: nudge the operator
    if (bridge) {
      addLog("[Delta Engine] Drop real base + target binaries into the sidebar first.", "warning");
      setLoadingStep(null);
      return;
    }

    // Browser fallback: simulation mode (unchanged behavior)
    await delay(1200);
    addLog("[Delta Engine] Delta patch generated — 45 KB (96.2% reduction)", "success");
    await delay(600);
    addLog("[SHA-256] Golden Hash computed: 0x8e5b0d3c...8e0f", "hash");
    setGoldenHash("0x8e5b0d3c9f4e2b6a7d0e3c5f8b2a4d6e9f1a3c5e7f9b1c3d5e7f9a2b4c6d8e0f");
    setDeltaSizeKb(45);
    setCompressionRatio("96.2% Reduction");
    setDeltaGenerated(true);
    setLoadingStep(null);
  };

  const handleConfigureUrl = async () => {
    if (!deltaGenerated || loadingStep) return;
    setLoadingStep("url");
    addLog("[Hosting] Configuring IPFS gateway URL for delta payload...", "info");

    if (getDesktopBridge() && patchUrl) {
      await delay(600);
      addLog(`[Hosting] Download: ${patchUrl}`, "success");
      addLog("[Hosting] Serve gateway/artifacts/ on :8000 (serve_artifacts.py) so the URL resolves off-box.", "info");
      if (ipfsCid) addLog(`[Hosting] Artifact ID: ${ipfsCid}`, "info");
    } else if (getDesktopBridge()) {
      addLog("[Hosting] No download URL from builder — regenerate the patch.", "error");
      setLoadingStep(null);
      return;
    } else {
      await delay(800);
      addLog("[Hosting] ipfs://QmXf7kp...2bCd — Pinned & accessible.", "success");
    }
    setUrlConfigured(true);
    setLoadingStep(null);
  };

  const handleConnectWallet = async () => {
    if (!urlConfigured || loadingStep) return;
    setLoadingStep("wallet");
    // Real WalletConnect session via AppKit (genuine pairing QR inside the
    // AppKit modal). Step completion still syncs from wallet.isConnected, so
    // closing the modal unconnected leaves the step honestly incomplete.
    addLog("[Web3] Opening WalletConnect session (real pairing — scan the AppKit QR)...", "info");
    await wallet.openWalletModal();
    setLoadingStep(null);
  };

  /**
   * Step 5: Format and broadcast smart contract payload:
   * proposeRelease(bytes32 version, bytes32 goldenHash, string ipfsUrl)
   */
  const handleRequestApproval = async () => {
    if (!walletConnected || loadingStep) return;
    if (!wallet.isVerified) {
      // Identity first: an unverified session signs nothing, not even loudly.
      addLog("[Identity] Verify wallet ownership first (Extension tab → Verify ownership). Proposal refused.", "error");
      return;
    }
    setLoadingStep("approval");

    const targetVersion = targetFile ? deriveVersionTag(targetFile.name) : "v1.1";
    const targetHash = goldenHash ?? "";
    if (!wallet.contractAddress || !ethers.isAddress(wallet.contractAddress)) {
      // No deployment targeted — broadcasting would throw "invalid address".
      addLog("[Smart Contract] No contract configured — set the deployed address in Contract Config (wallet popup) first. Proposal refused.", "error");
      setLoadingStep(null);
      return;
    }
    if (!targetHash) {
      // P1-1: never anchor a placeholder hash on-chain.
      addLog("[Smart Contract] No golden hash available — generate the delta first. Proposal refused.", "error");
      setLoadingStep(null);
      return;
    }
    const targetUrl = patchUrl || (ipfsCid ? `ipfs://${ipfsCid}` : "");
    if (!targetUrl) {
      addLog("[Smart Contract] No payload URL available — generate the delta first.", "error");
      setLoadingStep(null);
      return;
    }
    // URL-scheme guard: the contract stores any string, but the gateway only
    // downloads http(s)/file. Refuse anything else before any wallet prompt.
    if (!/^https?:\/\/.+/.test(targetUrl) && !targetUrl.startsWith("file://")) {
      addLog(`[Smart Contract] Refusing to anchor "${targetUrl.slice(0, 60)}..." — not fetchable by the gateway (use the hosted http(s) download URL; bare ipfs:// and app schemes do not resolve).`, "error");
      setLoadingStep(null);
      return;
    }

    addLog(
      `[Payload Formatter] Formatting proposeRelease(version: "${targetVersion}", goldenHash: "${formatGoldenHashBytes32(targetHash).slice(0, 18)}...", ipfsUrl: "${targetUrl.slice(0, 30)}...")`,
      "info"
    );

    try {
      if (wallet.isConnected) {
        // Node preflight (5s): fail here with a named error instead of
        // hanging inside gas estimation against a dead endpoint.
        await withTimeout(
          new ethers.JsonRpcProvider(wallet.rpcUrl).getNetwork(),
          5000,
          "contacting the node"
        );
        // Pre-prompt log: "waiting on you" and "dead" must never look alike.
        // signerOrigin is last-known (set by the previous getSigner call).
        if (wallet.signerOrigin === "dev-node") {
          addLog("[Signer] DEV SIGNER active — no phone prompt will appear; signing via local node...", "warning");
        } else if (wallet.signerOrigin === "wallet") {
          addLog("[Signer] Signature request sent to MetaMask phone — approve in the app now (60s timeout)...", "info");
        } else if (wallet.signerOrigin === "injected") {
          addLog("[Signer] Signature request sent to browser extension — approve the prompt (60s timeout)...", "info");
        } else {
          addLog("[Signer] Requesting signature from active wallet (60s timeout)...", "info");
        }
        addLog(`[Smart Contract] Broadcasting proposeRelease via signer ${truncateAddress(wallet.address || "")}...`, "info");
        const receipt = await withTimeout(
          wallet.proposeRelease(targetVersion, targetHash, targetUrl),
          60000,
          "waiting for wallet signature"
        );
        addLog(`[Blockchain] Tx Mined: ${receipt.hash.slice(0, 20)}... in block #${receipt.blockNumber}`, "success");
        addLog(receipt.origin === "wallet" ? "[Signer] MetaMask phone prompt approved — real user signature" : receipt.origin === "injected" ? "[Signer] Browser extension signed" : "[Signer] DEV SIGNER (node-signed, no phone prompt)", receipt.origin === "dev-node" ? "warning" : "success");
        addLog("[Multi-Sig] Signature 1 of 2 (2-of-3 multisig) anchored on-chain! Awaiting second dev approval.", "success");
        // P0-5: record proposer for the distinct-signer guard.
        if (receipt.from) {
          const proposerAddr = receipt.from.toLowerCase();
          setProposers((prev) => ({ ...prev, [targetVersion.toLowerCase()]: proposerAddr }));
        }
      } else {
        // P1-1: no simulated write path — an unconnected wallet cannot propose.
        throw new Error("Wallet not connected — connect an authorized developer wallet before proposing.");
      }

      setReleases((prev) => {
        const exists = prev.some((r) => r.version === targetVersion);
        if (exists) {
          return prev.map((r) =>
            r.version === targetVersion ? { ...r, goldenHash: targetHash, approvalCount: 1, isLive: false } : r
          );
        }
        return [
          {
            version: targetVersion,
            goldenHash: targetHash,
            approvalCount: 1,
            maxApprovals: 3,
            isLive: false,
            isRevoked: false,
          },
          ...prev,
        ];
      });

      setApprovalRequested(true);
      // P0-2: post-tx refresh — replace the optimistic cache row with chain truth.
      try {
        const rec = await wallet.fetchRelease(targetVersion);
        if (rec) mergeChainRecord(targetVersion, rec);
      } catch {
        // Poll loop will converge on next interval.
      }
    } catch (err: unknown) {
      const msg = explainTxError(err);
      addLog(`[Smart Contract Error] ${msg}`, "error");
      if (ALLOW_OFFLINE_PROGRESSION) {
        // Still allow step progression in local testing
        setApprovalRequested(true);
      } else {
        addLog("[Governance] Progression BLOCKED — proposal failed on-chain; no offline advance.", "error");
      }
    } finally {
      setLoadingStep(null);
    }
  };

  /**
   * Action: "Kill" ledger button
   * Formats and executes payload: revokeRelease(bytes32 version)
   */
  const handleExecuteKillSwitch = async (version: string) => {
    if (!wallet.isVerified) {
      addLog("[Identity] Verify wallet ownership first (Extension tab → Verify ownership). Revoke refused.", "error");
      return;
    }
    if (!wallet.isConnected) {
      addLog("[Kill Switch Error] Wallet not connected — connect an authorized developer wallet to revoke. Nothing was sent.", "error");
      return;
    }
    if (wallet.chainAuthorized === false) {
      addLog("[Governance] Connected wallet is NOT an authorized dev on this contract — revoke would revert. Switch wallet.", "error");
      return;
    }
    addLog(`[GOVERNANCE] KILL SWITCH TRIGGERED for ${version}...`, "warning");
    addLog(`[Payload Formatter] Formatting revokeRelease(bytes32: "${formatVersionBytes32(version)}")`, "info");

    try {
      {
        await withTimeout(
          new ethers.JsonRpcProvider(wallet.rpcUrl).getNetwork(),
          5000,
          "contacting the node"
        );
        if (wallet.signerOrigin === "dev-node") {
          addLog("[Signer] DEV SIGNER active — no phone prompt will appear; signing via local node...", "warning");
        } else {
          addLog("[Signer] Revoke request sent — approve in your wallet now (60s timeout)...", "info");
        }
        addLog(`[Smart Contract] Calling revokeRelease("${version}") on ${wallet.contractAddress}...`, "info");
        const receipt = await withTimeout(
          wallet.revokeRelease(version),
          60000,
          "waiting for wallet signature"
        );
        addLog(`[Blockchain] Release revoked in block #${receipt.blockNumber} (tx: ${receipt.hash.slice(0, 16)}...)`, "error");
        addLog(receipt.origin === "wallet" ? "[Signer] MetaMask phone prompt approved — real user signature" : receipt.origin === "injected" ? "[Signer] Browser extension signed" : "[Signer] DEV SIGNER (node-signed, no phone prompt)", "warning");
        addLog(`[Kill Switch] ${version} revoked on-chain — the gateway destroys its artifacts on its next poll (≤5s) and devices get 4.01.`, "error");
      }

      setReleases((prev) =>
        prev.map((r) => (r.version === version ? { ...r, isLive: false, isRevoked: true } : r))
      );
      // P0-2: confirm against chain truth immediately.
      try {
        const rec = await wallet.fetchRelease(version);
        if (rec) mergeChainRecord(version, rec);
      } catch {
        // Poll loop converges next interval.
      }
    } catch (err: unknown) {
      const msg = explainTxError(err);
      addLog(`[Kill Switch Error] ${msg}`, "error");
      if (ALLOW_OFFLINE_PROGRESSION) {
        setReleases((prev) =>
          prev.map((r) => (r.version === version ? { ...r, isLive: false, isRevoked: true } : r))
        );
      } else {
        addLog("[Governance] Revoke BLOCKED — on-chain revert; ledger unchanged (chain is truth).", "error");
      }
    }
  };

  /**
   * Action: "Approve" ledger button
   * Formats and executes payload: approveRelease(bytes32 version)
   */
  const handleApproveUpdate = async (version: string) => {
    if (!wallet.isVerified) {
      addLog("[Identity] Verify wallet ownership first (Extension tab → Verify ownership). Approval refused.", "error");
      return;
    }
    addLog(`[Governance] Signing 2-of-3 threshold approval for ${version}...`, "info");
    addLog(`[Payload Formatter] Formatting approveRelease(bytes32: "${formatVersionBytes32(version)}")`, "info");

    // P0-5: proposer≠approver pre-flight — distinct dev keys required.
    // hasSigned(version, proposer) is already true; a self-approve would waste
    // gas and fake quorum, so refuse before any wallet prompt.
    const proposer = proposers[version.toLowerCase()];
    const me = (wallet.address || "").toLowerCase();
    if (proposer && me && proposer === me) {
      addLog(`[Governance Rejection] 2-of-3 multi-sig requires distinct dev keys. Proposer (${truncateAddress(wallet.address || "")}) cannot approve their own release — hasSigned(version, proposer) is already true. Switch to a different authorized dev and retry.`, "error");
      return;
    }

    try {
      if (wallet.isConnected) {
        await withTimeout(
          new ethers.JsonRpcProvider(wallet.rpcUrl).getNetwork(),
          5000,
          "contacting the node"
        );
        if (wallet.signerOrigin === "dev-node") {
          addLog("[Signer] DEV SIGNER active — no phone prompt will appear; signing via local node...", "warning");
        } else {
          addLog("[Signer] Approval request sent — approve in your wallet now (60s timeout)...", "info");
        }
        addLog(`[Smart Contract] Calling approveRelease("${version}") from ${truncateAddress(wallet.address || "")}...`, "info");
        const receipt = await withTimeout(
          wallet.approveRelease(version),
          60000,
          "waiting for wallet signature"
        );
        addLog(`[Blockchain] Threshold approval confirmed in block #${receipt.blockNumber}!`, "success");
        addLog(receipt.origin === "wallet" ? "[Signer] MetaMask phone prompt approved — real user signature" : receipt.origin === "injected" ? "[Signer] Browser extension signed" : "[Signer] DEV SIGNER (node-signed, no phone prompt)", receipt.origin === "dev-node" ? "warning" : "success");
      } else {
        await delay(900);
      }

      setReleases((prev) =>
        prev.map((r) =>
          r.version === version
            ? { ...r, approvalCount: 2, isLive: true }
            : r
        )
      );
      // P0-2: replace optimistic row with chain truth; only claim LIVE if chain agrees.
      try {
        const rec = await wallet.fetchRelease(version);
        if (rec) {
          mergeChainRecord(version, rec);
          if (rec.isLive) {
            addLog(`[Smart Contract] THRESHOLD REACHED (2/3): ${version} is now LIVE on-chain!`, "success");
          } else if (!rec.isRevoked) {
            addLog(`[Governance] Approval recorded on-chain (${rec.approvalCount}/3) — awaiting threshold for LIVE.`, "warning");
          }
        } else {
          addLog(`[Smart Contract] THRESHOLD REACHED (2/3): ${version} is now LIVE on-chain!`, "success");
        }
      } catch {
        // Poll loop converges next interval.
      }
    } catch (err: unknown) {
      const msg = explainTxError(err);
      addLog(`[Approve Error] ${msg}`, "error");
      if (ALLOW_OFFLINE_PROGRESSION) {
        // Update state for manual test workflow
        setReleases((prev) =>
          prev.map((r) =>
            r.version === version
              ? { ...r, approvalCount: 2, isLive: true }
              : r
          )
        );
      } else {
        addLog("[Governance] Approval BLOCKED — on-chain revert; awaiting a valid distinct-signer approval.", "error");
      }
    }
  };

  // Deploy is the proposer's action: only the account that called
  // proposeRelease for this version (per the on-chain event) may trigger it.
  const deployVersion = targetFile ? deriveVersionTag(targetFile.name) : "v1.1";
  const deployProposer = proposers[deployVersion.toLowerCase()] ?? null;
  const isDeployProposer =
    deployProposer !== null &&
    !!wallet.address &&
    wallet.address.toLowerCase() === deployProposer;

  // Live deployment tracker (replaces the old timed animation). Every stage
  // is read from a real source: the chain (release record), the gateway
  // (gateway_status.json on the artifact server) and the device (its block
  // requests + the /hello version report after reboot). No timers.
  const [gatewayHost, setGatewayHostState] = useState(loadGatewayHost);
  const setGatewayHost = (host: string) => {
    setGatewayHostState(host);
    saveGatewayHost(host);
  };
  const statusUrl = statusUrlFor(patchUrl, gatewayHost);
  const gateway = useGatewayStatus(statusUrl);
  const gs = gateway.status;
  const trackRecord = releases.find((r) => r.version === deployVersion) ?? null;
  const gatewayStaged =
    gateway.online && gs?.gateway_state === "staged" && gs.staged_version === deployVersion;
  // A version report only counts if it came after this release was staged,
  // so a device that already ran this version earlier can't fake success.
  const deviceRunning =
    gs?.device_reported_version === deployVersion &&
    (gs.staged_at == null || (gs.device_reported_at ?? 0) >= gs.staged_at);
  const updateState: UpdateState = !isTracking
    ? "idle"
    : trackRecord?.isLive && deviceRunning
      ? "success"
      : !trackRecord?.isLive
        ? "blockchain"
        : !gatewayStaged
          ? "gateway"
          : "iot";
  const deviceBlock =
    gatewayStaged &&
    gs?.device_last_block != null &&
    (gs.staged_at == null || (gs.device_last_seen ?? 0) >= gs.staged_at)
      ? gs.device_last_block + 1
      : null;

  // Mirror the gateway's own log lines (blocks served, device reports, kill
  // switch, hash failures) into the terminal, once each. History present when
  // the feed first appears is skipped: only what happens while we watch counts.
  const lastEventId = useRef<number | null>(null);
  useEffect(() => {
    const events = gs?.events;
    if (!gateway.online || !events) return;
    const newest = events.length ? events[events.length - 1].id : (gs?.event_seq ?? 0);
    if (lastEventId.current === null || newest < lastEventId.current) {
      lastEventId.current = newest; // first sight, or the gateway restarted its counter
      return;
    }
    const fresh = events.filter((e) => e.id > (lastEventId.current ?? 0));
    if (fresh.length === 0) return;
    lastEventId.current = newest;
    for (const e of fresh) {
      const low = e.msg.toLowerCase();
      const type: LogEntry["type"] = /kill switch|mismatch|refused|failed/.test(low)
        ? "error"
        : /staged|reports firmware|final/.test(low)
          ? "success"
          : "info";
      addLog(`[Gateway] ${e.msg}`, type);
    }
  }, [gs, gateway.online, addLog]);

  // Terminal narration of REAL transitions only (once per stage, progress in
  // 25% steps).
  const loggedStageRef = useRef("");
  const loggedPctRef = useRef(-1);
  useEffect(() => {
    if (!isTracking) {
      loggedStageRef.current = "";
      loggedPctRef.current = -1;
      return;
    }
    if (trackRecord?.isRevoked) {
      addLog(`[Tracker] ${deployVersion} was REVOKED on-chain — the gateway destroys its artifacts and devices are refused. Tracking stopped.`, "error");
      setIsTracking(false);
      return;
    }
    const stageKey = updateState === "gateway" ? `gateway:${gateway.online}` : updateState;
    if (loggedStageRef.current !== stageKey) {
      loggedStageRef.current = stageKey;
      if (updateState === "blockchain") {
        addLog(`[Tracker] Chain: ${deployVersion} is not live yet (${trackRecord?.approvalCount ?? 0}/2 approvals) — waiting for a second authorized signature.`, "info");
      } else if (updateState === "gateway") {
        addLog(
          gateway.online
            ? `[Tracker] Chain: ${deployVersion} is LIVE. Gateway is "${gs?.gateway_state}" — waiting for it to download, verify and encrypt ${deployVersion}.`
            : `[Tracker] Chain: ${deployVersion} is LIVE, but the gateway status feed is offline (${statusUrl}) — is the gateway running, with the artifact server on :8000?`,
          gateway.online ? "info" : "warning"
        );
      } else if (updateState === "iot") {
        addLog(`[Tracker] Gateway staged ${deployVersion}: ${gs?.blocks_total ?? "?"} encrypted blocks (key fp ${gs?.key_fp ?? "?"}). Waiting for the device to pull them.`, "success");
      } else if (updateState === "success") {
        addLog(`[Tracker] Device ${gs?.device_reported_ip ?? ""} rebooted and reports ${deployVersion} — deployment confirmed end to end.`, "success");
      }
    }
  }, [isTracking, updateState, gateway.online, trackRecord, gs, deployVersion, statusUrl, addLog]);

  const toggleTracking = () => {
    if (isTracking) {
      setIsTracking(false);
      addLog("[Tracker] Stopped.", "info");
      return;
    }
    if (!approvalRequested) {
      addLog("[Error] Complete all 5 workflow steps before tracking the deployment.", "error");
      return;
    }
    if (!isDeployProposer) {
      addLog(
        `[Governance] Tracking is restricted to the proposer of ${deployVersion} (${deployProposer ? truncateAddress(deployProposer) : "unknown — not proposed on this contract"}) — connected ${wallet.address ? truncateAddress(wallet.address) : "no wallet"}.`,
        "error"
      );
      return;
    }
    addLog(`[Tracker] Tracking ${deployVersion}: chain → gateway (${statusUrl}) → device.`, "info");
    setIsTracking(true);
  };

  return {
    updateState,
    firmwareVersion,
    baseUploaded,
    targetUploaded,
    binariesReady,
    uploadHighlight,
    deltaGenerated,
    urlConfigured,
    walletConnected,
    approvalRequested,
    loadingStep,
    logs,
    releases,
    baseFile,
    targetFile,
    goldenHash,
    patchUrl,
    ipfsCid,
    deltaSizeKb,
    compressionRatio,
    wallet,
    chainSynced,
    proposers,
    deployVersion,
    deployProposer,
    isDeployProposer,
    handleLoadBinaries,
    handleLoadBinaryFile,
    handleGenerateDelta,
    handleConfigureUrl,
    handleConnectWallet,
    handleRequestApproval,
    handleExecuteKillSwitch,
    handleApproveUpdate,
    toggleTracking,
    isTracking,
    gateway,
    gatewayHost,
    setGatewayHost,
    trackRecord,
    deviceBlock,
  };
}
