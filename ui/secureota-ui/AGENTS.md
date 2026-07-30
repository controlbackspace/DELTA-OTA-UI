# UI Project — Domain & Dev Conventions

## Architecture
- React 19 / TypeScript 6 / Vite 8 / Tailwind CSS v4
- Atomic design: `atoms/` → `molecules/` → `organisms/` → `templates/`
- Single feature hook: `useFirmwarePipeline.ts` (mock simulation)
- No routing yet (react-router installed but unused)
- No real Web3 integration (wagmi/viem not yet installed)

## Conventions
- Domain types inline in organism files (e.g. `LedgerRelease` in `LedgerDeploymentsTable.tsx`)
- Formal domain model types will be shared via the gateway control API (Option B)
- Pipeline steps must be sequential: Load → Delta → URL → Wallet → Approve

## Running
```bash
npm run dev     # Vite dev server
npm run build   # TypeScript check + production build
npm run lint    # oxlint
```

## Reminder
The UI is a **stateless presentation layer**. All domain authority lives in the Solidity contract and the Edge Gateway. The UI reads gateway cache state via REST; it mutates the system only through Web3 wallet signatures.
