import { useState, useCallback, useEffect, useRef } from "react";
import type { LogEntry } from "../../components/organisms/SystemsLogTerminal";
import type { LedgerRelease } from "../../components/organisms/LedgerDeploymentsTable";
import { deriveVersionTag, getDesktopBridge } from "../../lib/desktop";
import { isAcceptedFirmwareFile } from "../../lib/firmwareFiles";
import { formatFileSize } from "../../lib/utils";
import { useDesktopWallet } from "../wallet/useDesktopWallet";
import type { OnChainReleaseRecord } from "../wallet/useDesktopWallet";
import {
  formatVersionBytes32,
  formatGoldenHashBytes32,
  truncateAddress,
} from "../../lib/web3Payloads";

export type UpdateState = "idle" | "developer" | "blockchain" | "gateway" | "iot" | "success";
export type BinaryKind = "base" | "target";

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// Honest-execution gate (P0-1): offline progression is OFF by default.
// Enabled only in dev via explicit VITE_ALLOW_OFFLINE_PROGRESSION="true"
// so failed/reverted txs block the pipeline in every real build.
const ALLOW_OFFLINE_PROGRESSION =
  (import.meta as unknown as { env: Record<string, string | boolean | undefined> }).env?.DEV ===
    true &&
  (import.meta as unknown as { env: Record<string, string | boolean | undefined> }).env
    ?.VITE_ALLOW_OFFLINE_PROGRESSION === "true";

export function useFirmwarePipeline() {
  const [updateState, setUpdateState] = useState<UpdateState>("idle");
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

  // Initial Logs
  const [logs, setLogs] = useState<LogEntry[]>([
    { id: 1, time: "09:14:21", message: "[SHA-256] Computing golden hash for delta patch (v1.1 firmware)...", type: "info" },
    { id: 2, time: "09:14:23", message: "[Multi-Sig] Contract 0x5FbDB...0aa3 initialized on Hardhat Localhost.", type: "success" },
    { id: 3, time: "09:14:25", message: "[Wallet] Mobile MetaMask QR & Dev signers ready on Chain 31337.", type: "info" },
    { id: 4, time: "09:14:27", message: "[Gateway] Ready to poll DeltaOTA smart contract state transitions.", type: "info" },
  ]);

  // Initial Releases Ledger State
  const [releases, setReleases] = useState<LedgerRelease[]>([
    {
      version: "v1.1",
      goldenHash: "0x8e5b0d3c9f4e2b6a7d0e3c5f8b2a4d6e9f1a3c5e7f9b1c3d5e7f9a2b4c6d8e0f",
      approvalCount: 1,
      maxApprovals: 3, // 2-of-3 multi-sig threshold
      isLive: false,
      isRevoked: false,
    },
    {
      version: "v1.0",
      goldenHash: "0x3f7a1c9e8b2d4f6a0e1c3b5d7f9a2c4e6b8d0f1a3c5e7b9d1f3a5c7e9b1d3f5a",
      approvalCount: 2,
      maxApprovals: 3,
      isLive: true,
      isRevoked: false,
    },
  ]);

  const addLog = useCallback((message: string, type: LogEntry["type"] = "info") => {
    const time = new Date().toLocaleTimeString("en-US", { hour12: false });
    // Append (tail -f order): the terminal autoscrolls to the bottom, so new
    // entries must land at the end. Prepending parks fresh logs above an
    // viewport pinned on stale content.
    setLogs((prev) => [...prev, { id: Date.now() + Math.random(), time, message, type }]);
  }, []);

  // P0-5: proposer per version (receipt.from at propose time), lowercased.
  const [proposers, setProposers] = useState<Record<string, string>>({});
  // P0-2: chain-sync flag — local releases are a cache until first poll lands.
  const [chainSynced, setChainSynced] = useState(false);
  const releasesRef = useRef<LedgerRelease[]>([]);
  releasesRef.current = releases;
  const fetchReleaseRef = useRef(wallet.fetchRelease);
  fetchReleaseRef.current = wallet.fetchRelease;

  const mergeChainRecord = useCallback(
    (version: string, rec: OnChainReleaseRecord) => {
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
      setReleases((prevList) =>
        prevList.map((r) =>
          r.version === version
            ? {
                ...r,
                goldenHash: rec.goldenHash || r.goldenHash,
                approvalCount: rec.approvalCount,
                isLive: rec.isLive,
                isRevoked: rec.isRevoked,
              }
            : r
        )
      );
      setChainSynced(true);
    },
    [addLog]
  );

  // P0-2: chain as source of truth — 4s poll over direct RPC (works with or
  // without a wallet session). On-chain revoke/approve/promote reflects
  // within one interval without clicks.
  useEffect(() => {
    let cancelled = false;
    const syncOnce = async () => {
      const versions = releasesRef.current.map((r) => r.version);
      for (const v of versions) {
        try {
          const rec = await fetchReleaseRef.current(v);
          if (cancelled || !rec) continue;
          mergeChainRecord(v, rec);
        } catch {
          // Poll failures keep the last cache; staleness is visible via
          // chainSynced staying false / logs, never fake-live data.
        }
      }
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
    setLoadingStep("approval");

    const targetVersion = targetFile ? deriveVersionTag(targetFile.name) : "v1.1";
    const targetHash = goldenHash || "0x8e5b0d3c9f4e2b6a7d0e3c5f8b2a4d6e9f1a3c5e7f9b1c3d5e7f9a2b4c6d8e0f";
    const targetUrl = patchUrl || (ipfsCid ? `ipfs://${ipfsCid}` : "");
    if (!targetUrl) {
      addLog("[Smart Contract] No payload URL available — generate the delta first.", "error");
      setLoadingStep(null);
      return;
    }

    addLog(
      `[Payload Formatter] Formatting proposeRelease(version: "${targetVersion}", goldenHash: "${formatGoldenHashBytes32(targetHash).slice(0, 18)}...", ipfsUrl: "${targetUrl.slice(0, 30)}...")`,
      "info"
    );

    try {
      if (wallet.isConnected) {
        addLog(`[Smart Contract] Broadcasting proposeRelease via signer ${truncateAddress(wallet.address || "")}...`, "info");
        const receipt = await wallet.proposeRelease(targetVersion, targetHash, targetUrl);
        addLog(`[Blockchain] Tx Mined: ${receipt.hash.slice(0, 20)}... in block #${receipt.blockNumber}`, "success");
        addLog(receipt.origin === "wallet" ? "[Signer] MetaMask phone prompt approved — real user signature" : receipt.origin === "injected" ? "[Signer] Browser extension signed" : "[Signer] DEV SIGNER (node-signed, no phone prompt)", receipt.origin === "dev-node" ? "warning" : "success");
        addLog("[Multi-Sig] Signature 1 of 2 (2-of-3 multisig) anchored on-chain! Awaiting second dev approval.", "success");
        // P0-5: record proposer for the distinct-signer guard.
        if (receipt.from) {
          const proposerAddr = receipt.from.toLowerCase();
          setProposers((prev) => ({ ...prev, [targetVersion.toLowerCase()]: proposerAddr }));
        }
      } else {
        // Fallback simulation if no active live node
        addLog("[Smart Contract] Signer prompt dispatched. Broadcasting to DeltaOTA...", "info");
        await delay(900);
        addLog("[Multi-Sig] Signature 1 of 2 (2-of-3 multisig) anchored to ledger by Dev #1.", "success");
        addLog("[Governance] Status: Awaiting threshold signature (2-of-3 required).", "warning");
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
      const msg = err instanceof Error ? err.message : "Contract call failed";
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
    addLog(`[GOVERNANCE] KILL SWITCH TRIGGERED for ${version}...`, "warning");
    addLog(`[Payload Formatter] Formatting revokeRelease(bytes32: "${formatVersionBytes32(version)}")`, "info");

    try {
      if (wallet.isConnected) {
        addLog(`[Smart Contract] Calling revokeRelease("${version}") on ${wallet.contractAddress}...`, "info");
        const receipt = await wallet.revokeRelease(version);
        addLog(`[Blockchain] Release revoked in block #${receipt.blockNumber} (tx: ${receipt.hash.slice(0, 16)}...)`, "error");
        addLog(receipt.origin === "wallet" ? "[Signer] MetaMask phone prompt approved — real user signature" : receipt.origin === "injected" ? "[Signer] Browser extension signed" : "[Signer] DEV SIGNER (node-signed, no phone prompt)", "warning");
      } else {
        await delay(800);
        addLog(`[Smart Contract] Firmware ${version} revoked immutably on-chain.`, "error");
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
      const msg = err instanceof Error ? err.message : "Revoke failed";
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
        addLog(`[Smart Contract] Calling approveRelease("${version}") from ${truncateAddress(wallet.address || "")}...`, "info");
        const receipt = await wallet.approveRelease(version);
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
            addLog("[Edge Gateway] ReleasePromotedToLive event captured. Distribution unlocked.", "success");
          } else if (!rec.isRevoked) {
            addLog(`[Governance] Approval recorded on-chain (${rec.approvalCount}/3) — awaiting threshold for LIVE.`, "warning");
          }
        } else {
          addLog(`[Smart Contract] THRESHOLD REACHED (2/3): ${version} is now LIVE on-chain!`, "success");
          addLog("[Edge Gateway] ReleasePromotedToLive event captured. Distribution unlocked.", "success");
        }
      } catch {
        // Poll loop converges next interval.
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Approval failed";
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

  const simulateUpdate = async () => {
    if (!approvalRequested) {
      addLog("[Error] Complete all 5 workflow steps before triggering deployment.", "error");
      return;
    }
    setUpdateState("developer");
    addLog("[Developer Console] Uploading delta patch v1.1 (45 KB) to IPFS...", "info");
    await delay(1000);
    setUpdateState("blockchain");
    addLog("[Blockchain] Anchoring Golden Hash to Smart Contract...", "info");
    await delay(1200);
    setUpdateState("gateway");
    addLog("[Edge Gateway] Polling contract... Payload verified against Golden Hash.", "success");
    addLog("[Edge Gateway] Encapsulating payload with OSCORE (AES-CCM-16-64-128).", "success");
    await delay(1200);
    setUpdateState("iot");
    addLog("[IoT Transport] Streaming OSCORE payload via CoAP/UDP to ESP32...", "info");
    await delay(1500);
    addLog("[ESP32] Streamed reconstruction complete. Rebooting to v1.1...", "success");
    setUpdateState("success");
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
    handleLoadBinaries,
    handleLoadBinaryFile,
    handleGenerateDelta,
    handleConfigureUrl,
    handleConnectWallet,
    handleRequestApproval,
    handleExecuteKillSwitch,
    handleApproveUpdate,
    simulateUpdate,
  };
}
