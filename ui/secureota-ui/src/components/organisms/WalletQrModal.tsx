import React, { useState, useEffect } from "react";
import QRCode from "qrcode";
import { ethers } from "ethers";
import {
  X,
  QrCode,
  Smartphone,
  Copy,
  Check,
  Shield,
  Zap,
  Info,
  RefreshCw,
} from "lucide-react";
import { HARDHAT_AUTHORIZED_DEVS } from "../../contracts/deltaOta";
import { isValidEthereumAddress } from "../../lib/web3Payloads";
import { StatusPill } from "../atoms/StatusPill";
import { DevSignerCard } from "../molecules/DevSignerCard";
import { isHttpsLoopback } from "../../features/wallet/useDesktopWallet";

// P0-4: packaged app is always a prod build — dev signers only in dev.
const isDevBuild =
  (import.meta as unknown as { env: Record<string, string | boolean | undefined> }).env?.DEV ===
  true;

export interface WalletQrModalProps {
  isOpen: boolean;
  onClose: () => void;
  connectionUri?: string | null;
  connectedAddress?: string | null;
  connectedChainId?: number | null;
  isVerified?: boolean;
  onVerifyIdentity: () => Promise<unknown>;
  onSelectDevAccount: (devIndex: number) => void;
  onDisconnect: () => void;
  onOpenWalletConnect: () => void;
  contractAddress: string;
  onUpdateContractAddress: (addr: string) => void;
  rpcUrl: string;
  onUpdateRpcUrl: (url: string) => void;
  phoneRpcUrl: string;
  onUpdatePhoneRpcUrl: (url: string) => void;
  statusMessage?: string | null;
  /** False when this console reads a REMOTE node (Funnel/LAN): the node-side
   *  dev accounts cannot sign there, so authors use their own wallet. */
  devSignerAvailable?: boolean;
}

export const WalletQrModal: React.FC<WalletQrModalProps> = ({
  isOpen,
  onClose,
  connectionUri,
  connectedAddress,
  connectedChainId = null,
  isVerified = false,
  onVerifyIdentity,
  onSelectDevAccount,
  onDisconnect,
  onOpenWalletConnect,
  contractAddress,
  onUpdateContractAddress,
  rpcUrl,
  onUpdateRpcUrl,
  phoneRpcUrl,
  onUpdatePhoneRpcUrl,
  statusMessage,
  devSignerAvailable = true,
}) => {
  const devSigners = isDevBuild && devSignerAvailable;
  const [qrDataUrl, setQrDataUrl] = useState<string>("");
  const [copied, setCopied] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<"qr" | "hardhat" | "config">("qr");
  // P0-3: draft + explicit save so garbage is rejected loudly, never persisted.
  const [draftAddress, setDraftAddress] = useState<string>(contractAddress);
  const [addressError, setAddressError] = useState<string | null>(null);
  const [draftRpcUrl, setDraftRpcUrl] = useState<string>(rpcUrl);
  const [rpcError, setRpcError] = useState<string | null>(null);
  const [draftPhoneRpcUrl, setDraftPhoneRpcUrl] = useState<string>(phoneRpcUrl);
  const [phoneRpcError, setPhoneRpcError] = useState<string | null>(null);
  const [verifyLoading, setVerifyLoading] = useState<boolean>(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  // P0-4: production has no dev tab — force back to QR if it was selected.
  const effectiveTab = !devSigners && activeTab === "hardhat" ? "qr" : activeTab;
  // Live chain pill: desired 31337 is the fallback; a known-wrong chain warns.
  const chainOk = connectedChainId === null || connectedChainId === 31337;
  const draftValid = isValidEthereumAddress(draftAddress.trim());

  // A QR is rendered ONLY from a live session URI. There is deliberately no
  // fallback URI: a fabricated code pairs with nothing and hangs both ends.
  const effectiveUri = connectionUri ?? null;

  useEffect(() => {
    if (!isOpen || !effectiveUri) {
      setQrDataUrl("");
      return;
    }

    QRCode.toDataURL(effectiveUri, {
      width: 280,
      margin: 2,
      color: {
        dark: "#05080f",
        light: "#38bdf8", // Cyan-400 QR code
      },
    })
      .then((url: string) => setQrDataUrl(url))
      .catch((err: unknown) => console.error("QR Code Generation Error:", err));
  }, [isOpen, effectiveUri]);

  useEffect(() => {
    if (isOpen) {
      setDraftAddress(contractAddress);
      setAddressError(null);
      setDraftRpcUrl(rpcUrl);
      setRpcError(null);
      setDraftPhoneRpcUrl(phoneRpcUrl);
      setPhoneRpcError(null);
    }
  }, [isOpen, contractAddress, rpcUrl, phoneRpcUrl]);

  const handleSaveAddress = () => {
    const clean = draftAddress.trim();
    if (!clean || !isValidEthereumAddress(clean)) {
      setAddressError(
        `Invalid address — expected 0x + 40 hex chars. Got "${draftAddress}". Nothing saved.`
      );
      return;
    }
    // P0-3: confirm dialog shows the full address before persisting.
    const ok = window.confirm(
      `Save contract address?\n\n${clean}\n\nAll propose/approve/revoke calls will target this address.`
    );
    if (!ok) return;
    setAddressError(null);
    onUpdateContractAddress(clean);
    // Stale-address check (real-life): warn when no contract lives at the
    // saved address on the configured RPC — the old address stays in the
    // failure copy so the operator knows what is still active.
    void (async () => {
      try {
        const provider = new ethers.JsonRpcProvider(rpcUrl);
        const code = await provider.getCode(clean);
        if (code === "0x") {
          setAddressError(
            `Saved, but no contract code at ${clean} on ${rpcUrl} — deploy first (npx hardhat run scripts/deploy.js). Calls will fail until then.`
          );
        }
      } catch {
        setAddressError(
          `Saved, but ${rpcUrl} is unreachable — cannot verify contract code. Check the node and RPC URL.`
        );
      }
    })();
  };

  const handleSaveRpcUrl = () => {
    const clean = draftRpcUrl.trim().replace(/\/+$/, "");
    if (!clean || !/^https?:\/\/[^/]+(:\d+)?$/.test(clean)) {
      setRpcError(
        `Invalid RPC URL — expected http(s)://host[:port]. Got "${draftRpcUrl}". Nothing saved.`
      );
      return;
    }
    if (isHttpsLoopback(clean)) {
      setRpcError(
        `The local Hardhat node speaks plain http — use http://${clean.slice("https://".length)}. The https tunnel URL belongs in Phone RPC below. Nothing saved.`
      );
      return;
    }
    setRpcError(null);
    onUpdateRpcUrl(clean);
  };

  const handleSavePhoneRpcUrl = () => {
    const clean = draftPhoneRpcUrl.trim().replace(/\/+$/, "");
    if (!/^https:\/\/[^/\s]+$/.test(clean)) {
      setPhoneRpcError(
        `Invalid phone RPC — MetaMask Mobile needs https://host (the tunnel URL). Got "${draftPhoneRpcUrl}". Nothing saved.`
      );
      return;
    }
    setPhoneRpcError(null);
    onUpdatePhoneRpcUrl(clean);
  };

  if (!isOpen) return null;

  const handleCopyUri = () => {
    if (!effectiveUri) return;
    void navigator.clipboard.writeText(effectiveUri);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Challenge-response ownership proof: the connected address is a claim
  // until the key holder signs the login challenge. Typing an address alone
  // never verifies — this prompt is the verification.
  const handleVerify = async () => {
    setVerifyLoading(true);
    setVerifyError(null);
    try {
      await onVerifyIdentity();
    } catch (err: unknown) {
      setVerifyError(err instanceof Error ? err.message : "Identity verification failed");
    } finally {
      setVerifyLoading(false);
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
                {chainOk ? (
                  <StatusPill color="cyan" label={`Chain ID: ${connectedChainId ?? 31337}`} dot />
                ) : (
                  <StatusPill color="amber" label={`Chain ID: ${connectedChainId} — switch to 31337`} dot />
                )}
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

        {/* Tab Navigation — phone QR first, dev signers (dev builds), config. */}
        <div className="flex border-b border-[#1a2a3a] bg-[#091222] px-6 text-xs font-sans">
          <button
            type="button"
            onClick={() => setActiveTab("qr")}
            className={`flex items-center gap-2 py-3 px-4 border-b-2 font-medium transition-colors ${
              effectiveTab === "qr"
                ? "border-cyan-400 text-cyan-300"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Smartphone className="w-3.5 h-3.5" />
            Mobile MetaMask QR
          </button>
          {devSigners && (
          <button
            type="button"
            onClick={() => setActiveTab("hardhat")}
            className={`flex items-center gap-2 py-3 px-4 border-b-2 font-medium transition-colors ${
              effectiveTab === "hardhat"
                ? "border-cyan-400 text-cyan-300"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Shield className="w-3.5 h-3.5" />
            Authorized Dev Signers
          </button>
          )}
          <button
            type="button"
            onClick={() => setActiveTab("config")}
            className={`flex items-center gap-2 py-3 px-4 border-b-2 font-medium transition-colors ${
              effectiveTab === "config"
                ? "border-cyan-400 text-cyan-300"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Zap className="w-3.5 h-3.5" />
            Contract Config
          </button>
        </div>

        {/* Modal Body — single vertical rhythm (space-y-5); sections never
            share a tighter gap than the outer scale. */}
        <div className="px-6 py-5 overflow-y-auto flex-1 space-y-5">
          {effectiveTab === "qr" && (
            <div className="flex flex-col items-center text-center space-y-5">
              {/* Identity panel — the connected address is a claim until the
                  key holder signs the login challenge (works for phone and
                  dev sessions alike). Signing stays locked while unverified. */}
              {connectedAddress && (
                <div className="w-full p-4 rounded-lg bg-emerald-950/20 border border-emerald-800/40 space-y-2 text-left">
                  <div className="flex items-center gap-2">
                    {isVerified ? (
                      <StatusPill color="emerald" label="Verified owner" dot />
                    ) : (
                      <StatusPill color="amber" label="Unverified" dot />
                    )}
                    <code className="text-xs text-emerald-300 font-mono">{connectedAddress}</code>
                  </div>
                  {!chainOk && (
                    <p className="text-[11px] font-sans text-amber-300">
                      Wrong network — switch to Hardhat Localhost (chain 31337). Sign &amp; Propose stays disabled until then.
                    </p>
                  )}
                  {!isVerified ? (
                    <div className="space-y-2">
                      <button
                        type="button"
                        onClick={handleVerify}
                        disabled={verifyLoading}
                        className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg border border-emerald-500/50 bg-emerald-950/40 hover:bg-emerald-900/40 text-sm text-emerald-200 transition-all font-sans disabled:opacity-50"
                      >
                        <Shield className="w-4 h-4" />
                        {verifyLoading ? "Signing challenge..." : "Verify ownership"}
                      </button>
                      <p className="text-[11px] font-sans text-slate-500">
                        Proves key possession: approve the challenge in your wallet, then the app checks on-chain authorization. Typing an address alone never verifies.
                      </p>
                    </div>
                  ) : (
                    <p className="text-[11px] font-sans text-emerald-400">
                      Ownership proven by challenge signature + on-chain authorization. Signing unlocked.
                    </p>
                  )}
                  {verifyError && (
                    <div className="text-[11px] font-sans text-rose-400 bg-rose-950/30 p-2 rounded border border-rose-900/50 w-full text-left">
                      {verifyError}
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={onDisconnect}
                    className="px-4 py-2 rounded-lg border border-slate-700 hover:bg-slate-800 text-slate-300 text-xs transition-colors font-sans"
                  >
                    Disconnect
                  </button>
                </div>
              )}
              {/* Instructions banner */}
              <div className="w-full flex items-start gap-2.5 p-3 rounded-lg bg-cyan-950/30 border border-cyan-800/40 text-left text-xs font-sans text-cyan-200">
                <Info className="w-4 h-4 shrink-0 mt-0.5 text-cyan-400" />
                <div>
                  Scan with <strong>MetaMask Mobile</strong> or your WalletConnect-compatible wallet. The phone reaches the node only through the HTTPS tunnel ({phoneRpcUrl ? <code className="text-cyan-300">{phoneRpcUrl}</code> : <span className="text-amber-300">not set — Contract Config → Phone RPC</span>}); a LAN <code className="text-cyan-300">http://</code> address is rejected by MetaMask Mobile.
                </div>
              </div>

              {/* QR Code frame — fixed reserve so the modal never jumps when
                  the code renders; caption row below (never overlaid). */}
              {effectiveUri ? (
                <>
                  <div className="relative p-5 rounded-xl border-2 border-dashed border-cyan-500/40 bg-[#05080f] shadow-inner flex flex-col items-center justify-center min-h-[280px] min-w-[264px]">
                    {qrDataUrl ? (
                      <>
                        <img
                          src={qrDataUrl}
                          alt="WalletConnect QR Code"
                          className="w-56 h-56 rounded-lg shadow-md transition-transform hover:scale-102 duration-200"
                        />
                        <p className="mt-3 text-[11px] font-sans text-emerald-400">Live WC 2.0 session — scan within 60s</p>
                      </>
                    ) : (
                      <div className="w-56 h-56 flex flex-col items-center justify-center text-slate-500 text-xs">
                        <RefreshCw className="w-6 h-6 animate-spin text-cyan-400 mb-2" />
                        Generating QR code...
                      </div>
                    )}
                  </div>

                  {/* Copy URI */}
                  <div className="w-full flex gap-3">
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
                  </div>
                </>
              ) : (
                <div className="w-full p-4 rounded-lg bg-amber-950/30 border border-amber-900/50 text-left space-y-3">
                  <div className="flex items-center gap-2">
                    <StatusPill color="amber" label="No session" />
                    <span className="text-xs text-amber-300 font-sans font-medium">
                      No active WalletConnect session.
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 font-sans">
                    {statusMessage ||
                      "Start a real pairing session first — a QR appears here only for a live session."}{" "}
                    {devSigners && "Dev signers (next tab) need no session at all."}
                  </p>
                  <button
                    type="button"
                    onClick={onOpenWalletConnect}
                    className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-cyan-500/50 bg-cyan-950/40 hover:bg-cyan-900/40 text-xs text-cyan-300 transition-all font-sans"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    Open WalletConnect
                  </button>
                </div>
              )}
            </div>
          )}

          {effectiveTab === "hardhat" && devSigners && (
            <div className="space-y-4 text-xs">
              <div className="p-3 rounded-lg bg-slate-900/80 border border-slate-800 text-slate-300 font-sans space-y-1">
                <p className="font-semibold text-white">2-of-3 Multi-Sig Authorized Developer Signers</p>
                <p className="text-slate-400 text-[11px]">
                  Pre-seeded in DeltaOTA constructor on Hardhat local node (<code className="text-cyan-400">127.0.0.1:8545</code>). Click to connect and sign as that developer:
                </p>
              </div>

              <div className="space-y-2">
                {HARDHAT_AUTHORIZED_DEVS.map((addr, idx) => (
                  <DevSignerCard
                    key={addr}
                    devIndex={idx}
                    address={addr}
                    isProposer={idx === 0}
                    isConnected={connectedAddress?.toLowerCase() === addr.toLowerCase()}
                    onSelect={() => {
                      onSelectDevAccount(idx);
                      onClose();
                    }}
                  />
                ))}
              </div>
            </div>
          )}

          {effectiveTab === "config" && (
            <div className="space-y-4 text-xs font-sans">
              <div className="space-y-1.5">
                <label className="text-slate-300 font-medium">Deployed DeltaOTA Contract Address</label>
                <input
                  type="text"
                  value={draftAddress}
                  onChange={(e) => setDraftAddress(e.target.value)}
                  className={`w-full px-3 py-2 rounded-lg border bg-[#05080f] font-mono text-xs focus:outline-none ${
                    draftAddress.trim() && !draftValid
                      ? "border-rose-500 text-rose-300"
                      : "border-[#1a2a3a] text-cyan-300 focus:border-cyan-500"
                  }`}
                />
                {draftAddress.trim() && !draftValid && (
                  <p className="text-[11px] text-rose-400">
                    Invalid address — expected 0x + 40 hex chars. Nothing is saved until valid.
                  </p>
                )}
                {addressError && (
                  <p className="text-[11px] text-rose-400 bg-rose-950/30 p-2 rounded border border-rose-900/50">
                    {addressError}
                  </p>
                )}
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleSaveAddress}
                    className="px-4 py-2 rounded-lg border border-cyan-500/50 bg-cyan-950/40 hover:bg-cyan-900/40 text-cyan-300 transition-all"
                  >
                    Save address
                  </button>
                  <span className="text-[11px] text-slate-500">
                    Current: <code className="text-cyan-300">{contractAddress}</code>
                  </span>
                </div>
                <p className="text-[11px] text-slate-500">
                  Update this if you redeployed DeltaOTA to a new address using <code className="text-slate-400">npx hardhat run scripts/deploy.js</code>.
                </p>
              </div>

              <div className="space-y-1.5">
                <label className="text-slate-300 font-medium">Node RPC Endpoint</label>
                <input
                  type="text"
                  value={draftRpcUrl}
                  onChange={(e) => setDraftRpcUrl(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-[#1a2a3a] bg-[#05080f] font-mono text-xs text-cyan-300 focus:outline-none focus:border-cyan-500"
                />
                {rpcError && (
                  <p className="text-[11px] text-rose-400 bg-rose-950/30 p-2 rounded border border-rose-900/50">
                    {rpcError}
                  </p>
                )}
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleSaveRpcUrl}
                    className="px-4 py-2 rounded-lg border border-cyan-500/50 bg-cyan-950/40 hover:bg-cyan-900/40 text-cyan-300 transition-all"
                  >
                    Save RPC URL
                  </button>
                  <span className="text-[11px] text-slate-500">
                    Current: <code className="text-cyan-300">{rpcUrl}</code>
                  </span>
                </div>
                <p className="text-[11px] text-slate-500">
                  Point at the presenting machine (e.g. <code className="text-slate-400">http://192.168.x.x:8545</code>) when this laptop is not the chain host.
                </p>
              </div>

              <div className="space-y-1.5">
                <label className="text-slate-300 font-medium">Phone RPC (HTTPS tunnel)</label>
                <input
                  type="text"
                  value={draftPhoneRpcUrl}
                  onChange={(e) => setDraftPhoneRpcUrl(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-[#1a2a3a] bg-[#05080f] font-mono text-xs text-cyan-300 focus:outline-none focus:border-cyan-500"
                />
                {phoneRpcError && (
                  <p className="text-[11px] text-rose-400 bg-rose-950/30 p-2 rounded border border-rose-900/50">
                    {phoneRpcError}
                  </p>
                )}
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleSavePhoneRpcUrl}
                    className="px-4 py-2 rounded-lg border border-cyan-500/50 bg-cyan-950/40 hover:bg-cyan-900/40 text-cyan-300 transition-all"
                  >
                    Save phone RPC
                  </button>
                  <span className="text-[11px] text-slate-500">
                    Current: <code className="text-cyan-300">{phoneRpcUrl || "not set"}</code>
                  </span>
                </div>
                <p className="text-[11px] text-slate-500">
                  Given to MetaMask Mobile when it lacks chain 31337. <code className="text-slate-400">demo-up.bat</code> fills this automatically; the hostname changes every run.
                </p>
              </div>

              <div className="p-3 rounded-lg bg-[#05080f] border border-[#1a2a3a] space-y-2 text-[11px]">
                <div className="text-slate-300 font-medium font-sans">Network Configuration:</div>
                <div className="grid grid-cols-2 gap-2 font-mono text-slate-400">
                  <div>Network: Hardhat Localhost</div>
                  <div>Chain ID: 31337</div>
                  <div className="col-span-2">RPC URL: {rpcUrl}</div>
                  <div className="col-span-2">Phone RPC: {phoneRpcUrl || "not set"}</div>
                  <div>Currency: ETH</div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer — status takes remaining width with full-text tooltip */}
        <div className="px-6 py-3 border-t border-[#1a2a3a] bg-[#05080f] flex items-center justify-between gap-4 text-xs text-slate-500 font-sans">
          <span className="min-w-0 flex-1 truncate" title={statusMessage ?? "DeltaOTA Multi-Sig 2-of-3"}>{statusMessage ?? "DeltaOTA Multi-Sig 2-of-3"}</span>
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
