import React, { useState, useEffect } from "react";
import QRCode from "qrcode";
import {
  X,
  QrCode,
  Smartphone,
  Copy,
  Check,
  ExternalLink,
  Shield,
  Zap,
  Info,
  RefreshCw,
} from "lucide-react";
import { HARDHAT_AUTHORIZED_DEVS } from "../../contracts/deltaOta";

export interface WalletQrModalProps {
  isOpen: boolean;
  onClose: () => void;
  connectionUri?: string | null;
  onSelectDevAccount: (devIndex: number) => void;
  onConnectInjected: () => Promise<unknown>;
  contractAddress: string;
  onUpdateContractAddress: (addr: string) => void;
}

export const WalletQrModal: React.FC<WalletQrModalProps> = ({
  isOpen,
  onClose,
  connectionUri,
  onSelectDevAccount,
  onConnectInjected,
  contractAddress,
  onUpdateContractAddress,
}) => {
  const [qrDataUrl, setQrDataUrl] = useState<string>("");
  const [copied, setCopied] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<"qr" | "hardhat" | "config">("qr");
  const [injectedLoading, setInjectedLoading] = useState<boolean>(false);
  const [injectedError, setInjectedError] = useState<string | null>(null);

  // Generate simulated or real WalletConnect URI
  const effectiveUri =
    connectionUri ||
    `wc:7f9a2b4c-6d8e-4a1b-9c2d-3e4f5a6b7c8d@2?relay-protocol=irn&symKey=a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2&chainId=eip155:31337`;

  useEffect(() => {
    if (!isOpen) return;

    QRCode.toDataURL(effectiveUri, {
      width: 280,
      margin: 2,
      color: {
        dark: "#05080f",
        light: "#38bdf8", // Cyan-400 QR code
      },
    })
      .then((url) => setQrDataUrl(url))
      .catch((err) => console.error("QR Code Generation Error:", err));
  }, [isOpen, effectiveUri]);

  if (!isOpen) return null;

  const handleCopyUri = () => {
    void navigator.clipboard.writeText(effectiveUri);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleInjected = async () => {
    setInjectedLoading(true);
    setInjectedError(null);
    try {
      await onConnectInjected();
      onClose();
    } catch (err: unknown) {
      setInjectedError(err instanceof Error ? err.message : "Injected connection failed");
    } finally {
      setInjectedLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 font-mono">
      <div className="relative w-full max-w-lg rounded-xl border border-cyan-500/30 bg-[#070d18] shadow-2xl overflow-hidden flex flex-col max-h-[92vh]">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[#1a2a3a] bg-[#05080f]">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-cyan-950/60 border border-cyan-500/30 text-cyan-400">
              <QrCode className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-white font-sans flex items-center gap-2">
                Desktop Wallet Connection
                <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800/50">
                  Chain ID: 31337
                </span>
              </h2>
              <p className="text-xs text-slate-400 font-sans">
                MetaMask Mobile QR Code & Hardhat Localhost
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800/60 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-[#1a2a3a] bg-[#091222] px-6 text-xs font-sans">
          <button
            type="button"
            onClick={() => setActiveTab("qr")}
            className={`flex items-center gap-2 py-3 px-4 border-b-2 font-medium transition-colors ${
              activeTab === "qr"
                ? "border-cyan-400 text-cyan-300"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Smartphone className="w-3.5 h-3.5" />
            Mobile MetaMask QR
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("hardhat")}
            className={`flex items-center gap-2 py-3 px-4 border-b-2 font-medium transition-colors ${
              activeTab === "hardhat"
                ? "border-cyan-400 text-cyan-300"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Shield className="w-3.5 h-3.5" />
            Authorized Dev Signers
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("config")}
            className={`flex items-center gap-2 py-3 px-4 border-b-2 font-medium transition-colors ${
              activeTab === "config"
                ? "border-cyan-400 text-cyan-300"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Zap className="w-3.5 h-3.5" />
            Contract Config
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-4">
          {activeTab === "qr" && (
            <div className="flex flex-col items-center text-center space-y-4">
              {/* Instructions banner */}
              <div className="w-full flex items-start gap-2.5 p-3 rounded-lg bg-cyan-950/30 border border-cyan-800/40 text-left text-xs font-sans text-cyan-200">
                <Info className="w-4 h-4 shrink-0 mt-0.5 text-cyan-400" />
                <div>
                  Scan with <strong>MetaMask Mobile</strong> or your WalletConnect-compatible wallet. Ensure your mobile wallet RPC is configured to your machine's local IP (e.g. <code className="text-cyan-300">http://192.168.x.x:8545</code>).
                </div>
              </div>

              {/* QR Code Canvas Frame */}
              <div className="relative p-4 rounded-xl border-2 border-dashed border-cyan-500/40 bg-[#05080f] shadow-inner flex flex-col items-center justify-center">
                {qrDataUrl ? (
                  <img
                    src={qrDataUrl}
                    alt="WalletConnect QR Code"
                    className="w-56 h-56 rounded-lg shadow-md transition-transform hover:scale-102 duration-200"
                  />
                ) : (
                  <div className="w-56 h-56 flex items-center justify-center text-slate-500 text-xs">
                    <RefreshCw className="w-6 h-6 animate-spin text-cyan-400 mb-2" />
                    Generating QR code...
                  </div>
                )}
                <div className="absolute top-2 right-2 flex items-center gap-1.5 px-2 py-0.5 rounded bg-cyan-950/80 text-[10px] text-cyan-400 border border-cyan-700/40">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Live WC 2.0
                </div>
              </div>

              {/* Copy URI button */}
              <div className="w-full flex gap-2">
                <button
                  type="button"
                  onClick={handleCopyUri}
                  className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border border-slate-700 bg-slate-900/60 hover:bg-slate-800 text-xs text-slate-200 transition-all font-sans"
                >
                  {copied ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                      <span className="text-emerald-400">Connection URI Copied!</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5 text-slate-400" />
                      <span>Copy WalletConnect URI</span>
                    </>
                  )}
                </button>

                {/* Direct injected extension connect */}
                <button
                  type="button"
                  onClick={handleInjected}
                  disabled={injectedLoading}
                  className="flex items-center gap-1.5 px-4 py-2.5 rounded-lg border border-cyan-500/50 bg-cyan-950/40 hover:bg-cyan-900/40 text-xs text-cyan-300 transition-all font-sans"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  {injectedLoading ? "Connecting..." : "Use Browser Extension"}
                </button>
              </div>

              {injectedError && (
                <div className="text-[11px] text-rose-400 bg-rose-950/30 p-2 rounded border border-rose-900/50 w-full text-left">
                  {injectedError}
                </div>
              )}
            </div>
          )}

          {activeTab === "hardhat" && (
            <div className="space-y-4 text-xs">
              <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 text-slate-300 font-sans space-y-1">
                <p className="font-semibold text-white">2-of-3 Multi-Sig Authorized Developer Signers</p>
                <p className="text-slate-400 text-[11px]">
                  Pre-seeded in DeltaOTA constructor on Hardhat local node (<code className="text-cyan-400">127.0.0.1:8545</code>). Click to instantly connect and sign as that developer:
                </p>
              </div>

              <div className="space-y-2">
                {HARDHAT_AUTHORIZED_DEVS.map((addr, idx) => (
                  <div
                    key={addr}
                    className="flex items-center justify-between p-3 rounded-lg border border-[#1a2a3a] bg-[#05080f] hover:border-cyan-500/40 transition-colors"
                  >
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-2">
                        <span className="text-cyan-400 font-bold">Dev #{idx + 1}</span>
                        {idx === 0 && (
                          <span className="px-1.5 py-0.2 rounded text-[9px] bg-indigo-950 text-indigo-300 border border-indigo-800">
                            Proposer (Deployer)
                          </span>
                        )}
                        {idx > 0 && (
                          <span className="px-1.5 py-0.2 rounded text-[9px] bg-emerald-950 text-emerald-300 border border-emerald-800">
                            Threshold Approver
                          </span>
                        )}
                      </div>
                      <div className="text-slate-400 font-mono text-[11px]">{addr}</div>
                    </div>

                    <button
                      type="button"
                      onClick={() => {
                        onSelectDevAccount(idx);
                        onClose();
                      }}
                      className="px-3 py-1.5 rounded border border-cyan-500/50 bg-cyan-950/40 hover:bg-cyan-900/60 text-cyan-300 font-sans font-medium text-xs transition-all"
                    >
                      Connect Dev #{idx + 1}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === "config" && (
            <div className="space-y-4 text-xs font-sans">
              <div className="space-y-1.5">
                <label className="text-slate-300 font-medium">Deployed DeltaOTA Contract Address</label>
                <input
                  type="text"
                  value={contractAddress}
                  onChange={(e) => onUpdateContractAddress(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-[#1a2a3a] bg-[#05080f] font-mono text-cyan-300 text-xs focus:outline-none focus:border-cyan-500"
                  placeholder="0x5FbDB2315678afecb367f032d93F642f64180aa3"
                />
                <p className="text-[11px] text-slate-500">
                  Update this if you redeployed DeltaOTA to a new address using <code className="text-slate-400">npx hardhat run scripts/deploy.js</code>.
                </p>
              </div>

              <div className="p-3 rounded-lg bg-[#05080f] border border-[#1a2a3a] space-y-2 text-[11px]">
                <div className="text-slate-300 font-medium font-sans">Network Configuration:</div>
                <div className="grid grid-cols-2 gap-2 font-mono text-slate-400">
                  <div>Network: Hardhat Localhost</div>
                  <div>Chain ID: 31337</div>
                  <div>RPC URL: http://127.0.0.1:8545</div>
                  <div>Currency: ETH</div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3 border-t border-[#1a2a3a] bg-[#05080f] flex items-center justify-between text-xs text-slate-500 font-sans">
          <span>DeltaOTA Multi-Sig 2-of-3</span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded border border-slate-700 hover:bg-slate-800 text-slate-300 text-xs transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
