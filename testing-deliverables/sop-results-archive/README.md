# Archive of the thesis data (full copy of `sop-results/`)

One archive in the current layout. It replaces the four earlier zips (their content is in this one; they remain recoverable from git history).

- `thesis-data-archive_2026-10-21.zip`: 951 files, 48,359 KiB, sha256 `4c2f4065b8ded7c8716ea0fc8dd4c435ae2c74cdd62fe450713cc51656a9ea44`
- Layout (see `sop-results/README.md` inside the archive): `01-raw-data/` (RUNS-INDEX.csv, tidy-csv/, runs/ pilots/ discarded/ with serial logs and packet captures),
  `02-interpretation/` (one markdown file per table, seven figures), `03-writing/` (the files the chapters are written from).
- Not included: the Chapter 4 and 5 draft, scratch work folders, local Hardhat node logs (public development accounts) and throwaway TLS private keys.
- The light copy that groupmates pull from git is `testing-deliverables/thesis-data-pack/` (no raw evidence); this archive is the full evidence.
- Firmware for the measurements: the firmware repository, tags `campaign-fw-1` and `baselines-fw-1`.
- Regenerate the generated files with `python -m sop.pack build` (see `03-writing/10_reproducibility.md`).
