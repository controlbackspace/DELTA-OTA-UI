# Wallet Network Setup — MetaMask Mobile ↔ Hardhat via a fixed HTTPS URL

How the desktop console reaches a phone wallet for real on-chain signatures.
Scope: local Hardhat test chain only. `scripts/demo-up.bat` automates all of
this; the steps below explain what it does and the one-time setup.

## 0. How the phone reaches the chain

```
MetaMask (phone) --HTTPS--> Tailscale Funnel --> rpc_guard :8546 --> Hardhat :8545
                            https://<laptop>.<tailnet>.ts.net  (FIXED URL)
```

- **The node is never exposed directly.** Hardhat's dev accounts are
  unlocked, so a public node would let anyone send transactions *as*
  Dev1/2/3. `gateway/rpc_guard.py` forwards only wallet methods (reads, gas,
  `eth_sendRawTransaction`, i.e. signed on the phone). It refuses
  `eth_sendTransaction`, `eth_sign*`, `personal_*`, `eth_accounts` and
  `hardhat_*`/`evm_*`.
- **The desktop console is unchanged.** It uses `127.0.0.1:8545` directly.
- **Prerequisites:** laptop and phone online (Funnel *and* the WalletConnect
  relay need internet), and MetaMask Mobile with one Hardhat dev key imported.
  The contract only accepts Dev1/2/3.

## 1. One-time setup (Tailscale, laptop only)

1. Install: `winget install --id Tailscale.Tailscale`, then sign in
   (`tailscale up` opens the browser).
2. Enable Funnel once: run `tailscale funnel --bg 8546` by hand and approve
   the link it prints (it turns on HTTPS certificates + Funnel for your tailnet).
3. Read your fixed URL: `tailscale funnel status` →
   `https://<laptop>.<tailnet>.ts.net`. This is the permanent phone RPC.

The phone does **not** need Tailscale: Funnel URLs are public HTTPS.

## 2. MetaMask network (once — the URL never changes)

MetaMask → Settings → Networks → Add:

| Field            | Value                                     |
|------------------|-------------------------------------------|
| Network name     | Hardhat Localhost                         |
| RPC URL          | `https://<laptop>.<tailnet>.ts.net`       |
| Chain ID         | `31337`                                   |
| Currency symbol  | `ETH`                                     |
| Decimals         | `18`                                      |
| Block explorer   | (blank)                                   |

Each `demo-up` starts the guard, switches Funnel on and verifies chain 31337
over the public URL. `demo-down` switches Funnel off (the URL stays reserved).

## 3. Verify (the gate — 10 seconds)

```powershell
curl.exe -s -H "Content-Type: application/json" -X POST --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' https://<laptop>.<tailnet>.ts.net
```

Expect `"result":"0x7a69"` (31337). A node-signing call must be refused:
`"method":"eth_accounts"` → `-32601 not available on this public endpoint`.

**Fallback without Tailscale:** `demo-up` uses a cloudflared quick tunnel to
the guard instead (`winget install --id Cloudflare.cloudflared`). Its
`https://<random>.trycloudflare.com` URL changes every run, so update the
MetaMask RPC each time.

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
| "Could not fetch chain ID" on save                 | Funnel off / demo not up (Tailscale), or quick-tunnel URL rotated → run demo-up, check step 3 |
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

Run `scripts\demo-down.bat`: it closes the demo windows and runs
`tailscale funnel reset`, so nothing is publicly reachable between demos.
What persists is only the Tailscale login and the machine's `ts.net` name,
which is why the MetaMask RPC never needs re-pasting. To remove everything:
uninstall Tailscale, or delete the machine in the Tailscale admin console.
On the cloudflared fallback nothing persists at all.
