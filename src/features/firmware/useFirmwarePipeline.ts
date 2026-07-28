import { useState, useCallback } from "react";
import type { LogEntry } from "../../components/organisms/SystemsLogTerminal";
import type { LedgerRelease } from "../../components/organisms/LedgerDeploymentsTable";

export type UpdateState = "idle" | "developer" | "blockchain" | "gateway" | "iot" | "success";

export function useFirmwarePipeline() {
  const [updateState, setUpdateState] = useState<UpdateState>("idle");
  const [firmwareVersion] = useState("v1.0");
  
  // Pipeline Step Flags
  const [baseUploaded, setBaseUploaded] = useState(true);
  const [targetUploaded, setTargetUploaded] = useState(true);
  const [deltaGenerated, setDeltaGenerated] = useState(false);
  const [urlConfigured, setUrlConfigured] = useState(false);
  const [walletConnected, setWalletConnected] = useState(false);
  const [approvalRequested, setApprovalRequested] = useState(false);
  
  // Active Action Indicators
  const [loadingStep, setLoadingStep] = useState<string | null>(null);

  // Initial Logs
  const [logs, setLogs] = useState<LogEntry[]>([
    { id: 1, time: "09:14:21", message: "[SHA-256] Computing golden hash for delta patch (v1.1 firmware)...", type: "info" },
    { id: 2, time: "09:14:22", message: "[SHA-256] 0x7f4a9c2b8e3d1a5f6c9e2b4d8a1c3e5f7a9b2c4d6e8f1a3c5e7f9b1c3d5e7f9a", type: "hash" },
  ]);

  // Initial On-Chain Releases (Solidity struct model)
  const [releases, setReleases] = useState<LedgerRelease[]>([
    {
      version: "v1.0",
      goldenHash: "0x7f4a9c2b8e3d1a5f6c9e2b4d8a1c3e5f7a9b2c4d6e8f1a3c5e7f9b1c3d5e7f9a",
      approvalCount: 3,
      maxApprovals: 3,
      isLive: true,
      isRevoked: false,
    },
    {
      version: "v1.1",
      goldenHash: "0x8e5b0d3c9f4e2b6a7d0e3c5f8b2a4d6e9f1a3c5e7f9b1c3d5e7f9a2b4c6d8e0f",
      approvalCount: 2,
      maxApprovals: 3,
      isLive: false,
      isRevoked: false,
    },
  ]);

  const addLog = useCallback((message: string, type: LogEntry["type"] = "info") => {
    setLogs((prev) => [
      ...prev,
      {
        id: Date.now() + Math.random(),
        time: new Date().toLocaleTimeString([], { hour12: false }),
        message,
        type,
      },
    ]);
  }, []);

  const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

  // Pipeline Actions
  const handleLoadBinaries = async () => {
    if (loadingStep || (baseUploaded && targetUploaded)) return;
    setLoadingStep("binaries");
    addLog("[Firmware Mgr] Staging baseline binary v1.0 — 1.2 MB", "info");
    await delay(800);
    addLog("[Firmware Mgr] Staging target binary v1.1 — 1.25 MB", "info");
    await delay(800);
    addLog("[Firmware Mgr] Both firmware binaries staged successfully.", "success");
    setBaseUploaded(true);
    setTargetUploaded(true);
    setLoadingStep(null);
  };

  const handleGenerateDelta = async () => {
    if (!baseUploaded || !targetUploaded || loadingStep) return;
    setLoadingStep("delta");
    addLog("[Delta Engine] Computing binary diff using bsdiff4 algorithm...", "info");
    await delay(1200);
    addLog("[Delta Engine] Delta patch generated — 45 KB (96.2% reduction)", "success");
    await delay(600);
    addLog("[SHA-256] Golden Hash computed: 0x8e5b0d3c...8e0f", "hash");
    setDeltaGenerated(true);
    setLoadingStep(null);
  };

  const handleConfigureUrl = async () => {
    if (!deltaGenerated || loadingStep) return;
    setLoadingStep("url");
    addLog("[Hosting] Configuring IPFS gateway URL for delta payload...", "info");
    await delay(800);
    addLog("[Hosting] ipfs://QmXf7kp...2bCd — Pinned & accessible.", "success");
    setUrlConfigured(true);
    setLoadingStep(null);
  };

  const handleConnectWallet = async () => {
    if (!urlConfigured || loadingStep) return;
    setLoadingStep("wallet");
    addLog("[Web3] Connecting to Injected Provider (Sepolia)...", "info");
    await delay(1000);
    addLog("[Web3] Wallet 0x742d35Cc...0bEb9 Authenticated.", "success");
    setWalletConnected(true);
    setLoadingStep(null);
  };

  const handleRequestApproval = async () => {
    if (!walletConnected || loadingStep) return;
    setLoadingStep("approval");
    addLog("[Smart Contract] Broadcasting proposal to governance contract...", "info");
    await delay(1000);
    addLog("[Multi-Sig] Signature 1/3 anchored to ledger.", "success");
    await delay(800);
    addLog("[Multi-Sig] Signature 2/3 anchored to ledger.", "success");
    addLog("[Governance] Status: Awaiting final threshold approval.", "warning");
    setApprovalRequested(true);
    setLoadingStep(null);
  };

  const handleExecuteKillSwitch = async (version: string) => {
    addLog(`[GOVERNANCE] KILL SWITCH ACTIVATED for ${version}...`, "warning");
    await delay(800);
    setReleases((prev) =>
      prev.map((r) => (r.version === version ? { ...r, isLive: false, isRevoked: true } : r))
    );
    addLog(`[Smart Contract] Firmware ${version} revoked immutably on-chain.`, "error");
  };

  const handleApproveUpdate = async (version: string) => {
    addLog(`[Governance] Signing threshold approval for ${version}...`, "info");
    await delay(1000);
    setReleases((prev) =>
      prev.map((r) =>
        r.version === version
          ? { ...r, approvalCount: 3, isLive: true }
          : r
      )
    );
    addLog(`[Smart Contract] THRESHOLD REACHED (3/3): ${version} is now LIVE.`, "success");
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
    deltaGenerated,
    urlConfigured,
    walletConnected,
    approvalRequested,
    loadingStep,
    logs,
    releases,
    handleLoadBinaries,
    handleGenerateDelta,
    handleConfigureUrl,
    handleConnectWallet,
    handleRequestApproval,
    handleExecuteKillSwitch,
    handleApproveUpdate,
    simulateUpdate,
    setBaseUploaded,
    setTargetUploaded,
  };
}
