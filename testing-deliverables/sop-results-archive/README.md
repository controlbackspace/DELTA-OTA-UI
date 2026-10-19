# SOP results archive (2026-10-19)

Compressed copy of the local, git-ignored `sop-results/` folder, for backup.

- `sop-results-2026-10-19.zip`: 428 files, sha256 `775ac0ee9e3969420b20c94b2c843d2f32d3542e29bc6c09e0eb3bfa88d0cf76`
- Contents: Table 1 and 4 data (`experiment-paper-tables/`), the 5-trial pilots, and the full Scenario A/B campaign
  (`campaign-AB-full-20261019T025653Z/campaign/trials.csv`, per-cycle serial logs and pcaps).
- Left out: scratch work folders (`work_cycles/`) and the local Hardhat node logs (they hold the public development
  accounts); the transaction numbers used in the tables are in the `trials.csv` files.
- Do not open `trials.csv` in a spreadsheet and save it: it rewrites the boolean columns (the analysis code tolerates TRUE/FALSE, but keep the original).
- Restore: unzip into a new, empty folder.

## Addition (2026-10-19): Table 3 run and the updated tables

- `sop-results-table3-and-tables-2026-10-19.zip`: 5 files, sha256 `6956eae5653dd23b8291c56af7b8be81fb7a40a7c56b80129db09ca35c0ec21d`
- Contents: the Table 3 run on the Raspberry Pi (`campaign-T3-full-20261019T080000Z/campaign/table3.csv`, with `table3.before-cycle6-rerun.csv`, and the raw gateway logs)
  and the updated table documents in `experiment-paper-tables/` (`TABLES-1-AND-4.md`, `TABLES-2-AND-3.md`, `README.md`).
- Not repeated here: the Scenario A/B campaign, the pilots and the Scenario C/D/E data, which are in `sop-results-2026-10-19.zip` above.

## Addition (2026-10-19, later): SOP 4 data and the Chapter 4 data pack

- `sop-results-sop4-and-data-pack-2026-10-19.zip`: 40 files, 422 KiB, sha256 `1ea82c47dd0c45f295fd1efbe976a6b87a8c2628c09c57628737498c78f59221`
- Contents: `sop4-supporting-data/` (the 60 on-device Web3 ledger checks, the two discarded attempts, `SOP4-SUMMARY.md`, CSVs, static footprint) and the data pack in
  `experiment-paper-tables/` (`README.md`, `SOP-MAP-AND-CLAIMS.md`, `DEFENSE-QA.md`, `STATISTICS.md`, `TABLES-1-AND-4.md`, `TABLES-2-AND-3.md`, `data/`, `figures/`).
  This supersedes the table documents of the earlier addition.
- Not included: the Chapter 4 and 5 draft, the local Hardhat node logs (public development accounts) and throwaway TLS private keys.
- Not repeated here: the Scenario A/B campaign, the pilots and the Scenario C/D/E data (`sop-results-2026-10-19.zip`), the Table 3 run (`sop-results-table3-and-tables-2026-10-19.zip`).
- Regenerate the statistics, tables and figures with `python -m sop.chapter4 ... --tables` and `python -m sop.figures ...` (commands in `experiment-paper-tables/README.md`).
