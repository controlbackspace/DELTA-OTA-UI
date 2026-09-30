# Wallet Network Setup — MetaMask Mobile ↔ Hardhat via Quick Tunnel

How the desktop console reaches a phone wallet for real on-chain signatures.
Scope: local Hardhat test chain only. No code changes required — this is pure
runtime plumbing (one terminal + one MetaMask screen).

## 0. Prerequisites (all must hold)

- Hardhat node running: `npx hardhat node` (plain localhost bind is fine —
  the tunnel terminates locally, so `--hostname 0.0.0.0` and firewall rules
  are NOT needed on this path).
- Laptop + phone on Wi-Fi **with internet** (tunnel endpoint *and*
  WalletConnect relay both require it — offline = use the DevSigner fallback).
- MetaMask Mobile installed, with one Hardhat dev private key imported
  (Account #0 prints in the node output; the DeltaOTA contract only accepts
  Dev1/2/3 — any other account reverts on `onlyAuthorized`).
- `cloudflared` installed (`winget install --id Cloudflare.cloudflared`).

## 1. Start the quick tunnel (every session)

```powershell
cloudflared tunnel --url http://127.0.0.1:8545
```

Copy the `https://<random>.trycloudflare.com` URL it prints. **Keep this
terminal open** — closing it kills the endpoint. The hostname **rotates on
every restart**: a saved URL from a previous session is dead on arrival.

## 2. Add / refresh the MetaMask network (every tunnel restart)

MetaMask → Settings → Networks → Add (or edit the existing entry):

| Field            | Value                                |
|------------------|--------------------------------------|
| Network name     | Hardhat Localhost                    |
| RPC URL          | the `https://…trycloudflare.com` URL |
| Chain ID         | `31337`                              |
| Currency symbol  | `ETH`                                |
| Decimals         | `18`                                 |
| Block explorer   | (blank)                              |

Re-paste the RPC URL whenever step 1 is re-run — stale URL is failure #1.

## 3. Verify before opening the app (the gate — 10 seconds)

```powershell
curl.exe -s -H "Content-Type: application/json" -X POST --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' https://<your-tunnel-url>
```

Expect `"result":"0x7a69"` (31337). This proves tunnel + cert + chain in one
shot, independent of wallets, QR, or app code. Do not proceed on any other
result — everything downstream assumes this line.

## 4. Pair and transact (in the desktop app)

1. Wallet step (or header badge) → QR modal → scan with MetaMask Mobile →
   approve the connection → address badge shows the imported dev account.
2. Click propose → **phone prompt must appear** → approve → receipt hash +
   block in the terminal. Repeat for approve and revoke.
3. Negative test: switch MetaMask to any unimported account → propose →
   expect the clean `onlyAuthorized` revert (proves the signature is
   authoritative, not decorative).

## 5. Failure table (in probability order)

| Symptom                                            | Cause → fix                                              |
|----------------------------------------------------|----------------------------------------------------------|
| "Could not fetch chain ID" on save                 | Tunnel closed or URL rotated → redo steps 1–2            |
| QR scans but pairs forever                         | No internet on either end, or relay blocked → check both |
| Prompt never arrives, terminal shows DEV SIGNER    | No live session — the app fell back to node signing; re-pair |
| `onlyAuthorized` revert on a dev account           | Wrong account selected in MetaMask → switch to Dev1/2/3  |
| `Switch MetaMask to Hardhat Localhost` in terminal | Phone wallet sits on another chain → switch networks     |
| No QR rendered, amber "No session" panel           | Correct behavior when unpaired — use Retry (never a fake code) |
| "no phone RPC is set" after pairing                | Phone lacks chain 31337 and the app has no tunnel URL → Contract Config → Phone RPC, re-scan |
| Pairs, but every tx fails / balance never loads    | Phone's 31337 entry still holds an old tunnel URL — the app never overwrites an existing entry → redo step 2 |
| "Restored phone session did not answer" on launch  | Phone app closed/asleep during the 15s relay ping → open MetaMask, re-scan |

Pairing note: the session proposal also offers Sepolia as an anchor, so
MetaMask always has a chain it can approve; the app then steers the phone to
31337 (adding it with the Phone RPC when missing). Signing is refused on any
chain other than 31337. `demo-up.bat` pre-fills the Phone RPC with the
current tunnel URL; on a manual bring-up, paste it in Contract Config.

## 6. Cleanup

Close the tunnel terminal when done. Nothing persists: no service, no DNS,
no config. Next session starts again at step 1.
