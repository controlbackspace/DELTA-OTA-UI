# SOP results archive (2026-10-19)

Compressed copy of the local, git-ignored `sop-results/` folder, for backup.

- `sop-results-2026-10-19.zip`: 428 files, sha256 `775ac0ee9e3969420b20c94b2c843d2f32d3542e29bc6c09e0eb3bfa88d0cf76`
- Contents: Table 1 and 4 data (`experiment-paper-tables/`), the 5-trial pilots, and the full Scenario A/B campaign
  (`campaign-AB-full-20261019T025653Z/campaign/trials.csv`, per-cycle serial logs and pcaps).
- Left out: scratch work folders (`work_cycles/`) and the local Hardhat node logs (they hold the public development
  accounts); the transaction numbers used in the tables are in the `trials.csv` files.
- Do not open `trials.csv` in a spreadsheet and save it: it rewrites the boolean columns (the analysis code tolerates TRUE/FALSE, but keep the original).
- Restore: unzip into a new, empty folder.
