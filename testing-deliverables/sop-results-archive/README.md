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
