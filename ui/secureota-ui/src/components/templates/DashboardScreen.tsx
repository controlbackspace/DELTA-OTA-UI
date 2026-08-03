import * as React from "react";
import { ShieldCheck, Zap, Upload, Hash, Globe, Wallet, Users } from "lucide-react";
import { StatusPill } from "../atoms/StatusPill";
import { WorkflowStepButton } from "../molecules/WorkflowStepButton";
import { NodeConstraintsSidebar } from "../organisms/NodeConstraintsSidebar";
import { LedgerDeploymentsTable } from "../organisms/LedgerDeploymentsTable";
import { SystemLogsTerminal } from "../organisms/SystemsLogTerminal";
import { useFirmwarePipeline } from "../../features/firmware/useFirmwarePipeline";

export const DashboardScreen: React.FC = () => {
  const pipeline = useFirmwarePipeline();

  const allStepsComplete =
    pipeline.baseUploaded &&
    pipeline.targetUploaded &&
    pipeline.deltaGenerated &&
    pipeline.urlConfigured &&
    pipeline.walletConnected &&
    pipeline.approvalRequested;

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

        <div className="flex items-center gap-4 font-sans">
          <StatusPill color="emerald" label="Gateway Online" dot />
          <StatusPill color="cyan" label="Chain: Sepolia" dot />
          <button
            type="button"
            onClick={pipeline.simulateUpdate}
            disabled={!allStepsComplete || pipeline.updateState !== "idle"}
            className={`flex items-center gap-2 px-5 py-2 rounded border text-sm transition-all duration-200 ${
              allStepsComplete && pipeline.updateState === "idle"
                ? "border-cyan-500/70 bg-cyan-500/10 text-cyan-300 hover:bg-cyan-500/20 hover:border-cyan-400 cursor-pointer"
                : "border-slate-800 bg-slate-900/30 text-slate-600 cursor-not-allowed"
            }`}
          >
            <Zap className="w-4 h-4" />
            Deploy Test Update
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
                onClick={pipeline.handleConfigureUrl}
              />
              <WorkflowStepButton
                stepNumber={4}
                label="Connect Wallet"
                subLabel="MetaMask / Web3"
                icon={<Wallet className="w-3.5 h-3.5" />}
                isCompleted={pipeline.walletConnected}
                isLoading={pipeline.loadingStep === "wallet"}
                isActive={pipeline.urlConfigured && !pipeline.walletConnected}
                onClick={pipeline.handleConnectWallet}
              />
              <WorkflowStepButton
                stepNumber={5}
                label="Request Approval"
                subLabel="2-of-3 Multi-Sig"
                icon={<Users className="w-3.5 h-3.5" />}
                isCompleted={pipeline.approvalRequested}
                isLoading={pipeline.loadingStep === "approval"}
                isActive={pipeline.walletConnected && !pipeline.approvalRequested}
                isLast={true}
                onClick={pipeline.handleRequestApproval}
              />
            </div>
          </div>

          {/* Active On-Chain Deployments Table */}
          <LedgerDeploymentsTable
            releases={pipeline.releases}
            onExecuteKillSwitch={pipeline.handleExecuteKillSwitch}
            onApproveUpdate={pipeline.handleApproveUpdate}
          />

          {/* Terminal Execution Window */}
          <SystemLogsTerminal
            logs={pipeline.logs}
            isProcessing={pipeline.updateState !== "idle" && pipeline.updateState !== "success"}
            isComplete={pipeline.updateState === "success"}
          />
        </main>
      </div>
    </div>
  );
};
