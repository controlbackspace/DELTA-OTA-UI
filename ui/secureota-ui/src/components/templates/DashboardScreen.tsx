import * as React from "react";
import { ShieldCheck, Zap, Upload, Hash, Globe, Wallet, Users, QrCode } from "lucide-react";
import { StatusPill } from "../atoms/StatusPill";
import { WorkflowStepButton } from "../molecules/WorkflowStepButton";
import { NodeConstraintsSidebar } from "../organisms/NodeConstraintsSidebar";
import { LedgerDeploymentsTable } from "../organisms/LedgerDeploymentsTable";
import { SystemLogsTerminal } from "../organisms/SystemsLogTerminal";
import { WalletQrModal } from "../organisms/WalletQrModal";
import { DeploymentTracker } from "../organisms/DeploymentTracker";
import { useFirmwarePipeline } from "../../features/firmware/useFirmwarePipeline";
import { truncateAddress } from "../../lib/web3Payloads";

export const DashboardScreen: React.FC = () => {
  const pipeline = useFirmwarePipeline();

  const allStepsComplete =
    pipeline.baseUploaded &&
    pipeline.targetUploaded &&
    pipeline.deltaGenerated &&
    pipeline.urlConfigured &&
    pipeline.walletConnected &&
    pipeline.approvalRequested;

  // Tracking is the proposer's action (on-chain ReleaseProposed event);
  // stopping an active tracker is always allowed.
  const canTrack = pipeline.isTracking || (allStepsComplete && pipeline.isDeployProposer);
  const trackBlockedReason =
    !pipeline.isTracking && allStepsComplete && !pipeline.isDeployProposer
      ? pipeline.deployProposer
        ? `Only the proposer of ${pipeline.deployVersion} (${truncateAddress(pipeline.deployProposer)}) can track this release`
        : `${pipeline.deployVersion} has no on-chain proposer yet — propose it first`
      : undefined;

  return (
    <div className="h-screen bg-[#05080f] text-slate-300 flex flex-col overflow-hidden font-mono">
      {/* Top Header */}
      <header className="shrink-0 flex items-center justify-between px-6 py-4 border-b border-[#1a2a3a] bg-[#070d18]">
        <div className="flex items-center gap-4">
          <div className="flex gap-2">
            <span className="w-3 h-3 rounded-full bg-rose-500" />
            <span className="w-3 h-3 rounded-full bg-amber-400" />
            <span className="w-3 h-3 rounded-full bg-emerald-400" />
          </div>
          <div className="w-px h-5 bg-slate-700" />
          <ShieldCheck className="w-5 h-5 text-cyan-400" />
          <span className="text-base text-white font-medium font-sans">
            Blockchain-Secured IoT Firmware Console
          </span>
          <span className="text-sm text-slate-600 font-sans">Thesis Prototype</span>
        </div>

        <div className="flex items-center gap-3 font-sans">
          {/* Real liveness: gateway heartbeat in gateway_status.json (< 20 s old). */}
          <StatusPill
            color={pipeline.gateway.online ? "emerald" : "rose"}
            label={pipeline.gateway.online ? "Gateway Online" : "Gateway Offline"}
            dot
          />
          <StatusPill color="cyan" label="Chain: 31337 (Local)" dot />

          {/* Connected Wallet Badge / modal trigger. Modal opens on the
              extension-first tab; pairing starts there or via step 4. */}
          <button
            type="button"
            onClick={() => pipeline.wallet.openCustomQrModal()}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-cyan-800/60 bg-cyan-950/30 hover:bg-cyan-950/60 text-cyan-300 text-xs transition-colors"
          >
            <QrCode className="w-3.5 h-3.5 text-cyan-400" />
            <span>
              {pipeline.wallet.isConnected && pipeline.wallet.address
                ? truncateAddress(pipeline.wallet.address)
                : "Connect Wallet"}
            </span>
            {pipeline.wallet.isConnected && (
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
            )}
          </button>

          <button
            type="button"
            onClick={pipeline.toggleTracking}
            disabled={!canTrack}
            title={trackBlockedReason}
            className={`flex items-center gap-2 px-5 py-2 rounded border text-sm transition-all duration-200 ${
              canTrack
                ? "border-cyan-500/70 bg-cyan-500/10 text-cyan-300 hover:bg-cyan-500/20 hover:border-cyan-400 cursor-pointer"
                : "border-slate-800 bg-slate-900/30 text-slate-600 cursor-not-allowed"
            }`}
          >
            <Zap className="w-4 h-4" />
            {pipeline.isTracking ? "Stop Tracking" : "Track Deployment"}
          </button>
        </div>
      </header>

      {/* Main Grid View */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar Organism */}
        <NodeConstraintsSidebar
          firmwareVersion={pipeline.firmwareVersion}
          ramFreeKb={120}
          ramTotalKb={1024}
          otaUsedKb={900}
          otaTotalKb={1536}
          baseUploaded={pipeline.baseUploaded}
          targetUploaded={pipeline.targetUploaded}
          deltaGenerated={pipeline.deltaGenerated}
          goldenHash={pipeline.goldenHash}
          deltaSizeKb={pipeline.deltaSizeKb}
          compressionRatio={pipeline.compressionRatio}
          baseFile={pipeline.baseFile}
          targetFile={pipeline.targetFile}
          onUploadBase={(file) => pipeline.handleLoadBinaryFile(file, "base")}
          onUploadTarget={(file) => pipeline.handleLoadBinaryFile(file, "target")}
          highlightUpload={pipeline.uploadHighlight}
        />

        {/* Center Main Stage */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Workflow Step Bar */}
          <div className="p-6 border-b border-[#1a2a3a] bg-[#060c18] shrink-0">
            <div className="flex items-stretch gap-2">
              <WorkflowStepButton
                stepNumber={1}
                label="Load Binaries"
                subLabel="v1.0 + v1.1"
                icon={<Upload className="w-3.5 h-3.5" />}
                isCompleted={pipeline.baseUploaded && pipeline.targetUploaded}
                isLoading={pipeline.loadingStep === "binaries"}
                isDisabled={pipeline.loadingStep !== null && pipeline.loadingStep !== "binaries"}
                onClick={pipeline.handleLoadBinaries}
              />
              <WorkflowStepButton
                stepNumber={2}
                label="Generate Delta"
                subLabel="bsdiff4 + SHA-256"
                icon={<Hash className="w-3.5 h-3.5" />}
                isCompleted={pipeline.deltaGenerated}
                isLoading={pipeline.loadingStep === "delta"}
                isActive={pipeline.baseUploaded && pipeline.targetUploaded && !pipeline.deltaGenerated}
                isDisabled={!pipeline.binariesReady}
                onClick={pipeline.handleGenerateDelta}
              />
              <WorkflowStepButton
                stepNumber={3}
                label="Configure URL"
                subLabel="IPFS Gateway"
                icon={<Globe className="w-3.5 h-3.5" />}
                isCompleted={pipeline.urlConfigured}
                isLoading={pipeline.loadingStep === "url"}
                isActive={pipeline.deltaGenerated && !pipeline.urlConfigured}
                isDisabled={!pipeline.deltaGenerated}
                onClick={pipeline.handleConfigureUrl}
              />
              <WorkflowStepButton
                stepNumber={4}
                label="Connect Wallet"
                subLabel={
                  pipeline.walletConnected
                    ? `Chain ${pipeline.wallet.chainId ?? "?"}`
                    : "Phone QR"
                }
                icon={<Wallet className="w-3.5 h-3.5" />}
                isCompleted={pipeline.walletConnected}
                isLoading={pipeline.loadingStep === "wallet"}
                isActive={pipeline.urlConfigured && !pipeline.walletConnected}
                isDisabled={!pipeline.urlConfigured}
                onClick={pipeline.handleConnectWallet}
              />
              <WorkflowStepButton
                stepNumber={5}
                label="Sign & Propose"
                subLabel={
                  !pipeline.walletConnected
                    ? "Connect a wallet first"
                    : !pipeline.wallet.isVerified
                      ? "Verify ownership first"
                      : pipeline.wallet.chainId !== null && pipeline.wallet.chainId !== 31337
                        ? `Wrong chain (${pipeline.wallet.chainId})`
                        : "DeltaOTA Multi-Sig"
                }
                icon={<Users className="w-3.5 h-3.5" />}
                isCompleted={pipeline.approvalRequested}
                isLoading={pipeline.loadingStep === "approval"}
                isActive={pipeline.walletConnected && !pipeline.approvalRequested}
                isDisabled={
                  !pipeline.walletConnected ||
                  !pipeline.wallet.isVerified ||
                  (pipeline.wallet.chainId !== null && pipeline.wallet.chainId !== 31337)
                }
                isLast={true}
                onClick={pipeline.handleRequestApproval}
              />
            </div>
          </div>

          {/* Live chain -> gateway -> device tracker (real data only) */}
          {pipeline.isTracking && (
            <DeploymentTracker
              version={pipeline.deployVersion}
              stage={pipeline.updateState}
              record={pipeline.trackRecord}
              gatewayOnline={pipeline.gateway.online}
              status={pipeline.gateway.status}
              deviceBlock={pipeline.deviceBlock}
            />
          )}

          {/* Active On-Chain Deployments Table */}
          <LedgerDeploymentsTable
            releases={pipeline.releases}
            onExecuteKillSwitch={pipeline.handleExecuteKillSwitch}
            onApproveUpdate={pipeline.handleApproveUpdate}
            proposerByVersion={pipeline.proposers}
            connectedAddress={pipeline.wallet.address}
          />

          {/* Terminal Execution Window */}
          <SystemLogsTerminal
            logs={pipeline.logs}
            isProcessing={pipeline.updateState !== "idle" && pipeline.updateState !== "success"}
            isComplete={pipeline.updateState === "success"}
          />
        </main>
      </div>

      {/* WalletConnect Mobile QR Code & Hardhat Local Signer Modal */}
      <WalletQrModal
        isOpen={pipeline.wallet.isQrModalOpen}
        onClose={pipeline.wallet.closeCustomQrModal}
        connectionUri={pipeline.wallet.connectionUri}
        connectedAddress={pipeline.wallet.address}
        connectedChainId={pipeline.wallet.chainId}
        isVerified={pipeline.wallet.isVerified}
        onVerifyIdentity={() => pipeline.wallet.verifyIdentity()}
        onSelectDevAccount={pipeline.wallet.connectDevAccount}
        onDisconnect={pipeline.wallet.disconnect}
        contractAddress={pipeline.wallet.contractAddress}
        onUpdateContractAddress={pipeline.wallet.updateContractAddress}
        rpcUrl={pipeline.wallet.rpcUrl}
        onUpdateRpcUrl={pipeline.wallet.updateRpcUrl}
        phoneRpcUrl={pipeline.wallet.phoneRpcUrl}
        onUpdatePhoneRpcUrl={pipeline.wallet.updatePhoneRpcUrl}
        onOpenWalletConnect={() => void pipeline.wallet.openWalletModal()}
        statusMessage={pipeline.wallet.statusMessage}
      />
    </div>
  );
};
