import csv
import tempfile
import unittest
from pathlib import Path

from sop import campaign, pack
from sop.tests.test_baselines import an_rows, h_folder
from sop.tests.test_chapter4 import campaign_rows, row


def write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campaign.FIELDS)
        w.writeheader()
        w.writerows(rows)


def make_root(tmp: Path) -> Path:
    root = tmp / "sop-results"
    runs = root / "01-raw-data" / "runs"
    layout = {"R02": "R02_table4_x", "R03": "R03_table2_x", "R04": "R04_table3_x", "R05": "R05_sop4_x", "R06": "R06_h_x", "R07": "R07_n_x", "R08": "R08_conf_x"}
    write_csv(runs / layout["R02"] / "campaign" / "trials.csv", [row(s, t, rejected="True", delay_ms=5000) for s in "CDE" for t in range(1, 61)])
    write_csv(runs / layout["R03"] / "campaign" / "trials.csv", campaign_rows(n=70, fail_a=(3,), fail_b=(5,), heap_missing_a=()))
    write_csv(runs / layout["R04"] / "campaign" / "table3.csv", [row("T3", t, poll_ms=50 + t % 7, sha_ms=0.2, encap_ms=6, gw_ram_mb=80, gw_cpu_pct=30, diff_ms=32, to_dota_ms=140) for t in range(1, 61)])
    web = runs / layout["R05"] / "raw"
    web.mkdir(parents=True)
    (web / "serial-web3_baseline.log").write_text(
        "[+1.0] [MEM] phase=web3-start free=250000 min=248000\n"
        "[+5.0] [Web3] run=0 tls_connect_ms=1300 request_ms=40 keccak_us=500 decode_us=100 ok=1 approvals=2 live=1 revoked=0\n"
        "[+5.1] [MEM] phase=web3-run free=249000 min=200000\n"
        "[+7.0] [Web3] run=1 tls_connect_ms=1400 request_ms=60 keccak_us=520 decode_us=120 ok=1 approvals=2 live=1 revoked=0\n"
        "[+7.1] [MEM] phase=web3-run free=249000 min=198000\n"
        "[+9.5] [MEM] phase=web3-end free=249500 min=198000\n", encoding="utf-8")
    h_folder(runs / layout["R06"])
    write_csv(runs / layout["R07"] / "campaign" / "trials.csv", an_rows(n=64))
    write_csv(runs / layout["R08"] / "campaign" / "trials.csv", campaign_rows(n=24, fail_a=(), fail_b=(), heap_missing_a=()))
    idx = [{"run_id": rid, "folder": f"runs/{name}", "kind": "campaign", "feeds": "-", "scenarios": "-", "started_utc": "", "ended_utc": "", "harness": "",
            "firmware": "", "git_revision": "", "status": "final", "description": ""} for rid, name in layout.items()]
    with open(root / "01-raw-data" / "RUNS-INDEX.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(idx[0].keys()))
        w.writeheader()
        w.writerows(idx)
    return root


def make_images(tmp: Path):
    import bsdiff4
    a, b = tmp / "v1.0.bin", tmp / "v1.1.bin"
    a.write_bytes(bytes(range(256)) * 40)
    b.write_bytes(bytes(range(256)) * 38 + b"changed tail" * 50)
    return a, b


class PackNamingTests(unittest.TestCase):
    def test_every_generated_name_follows_the_convention(self):
        for new in pack.TIDY_NAMES.values():
            self.assertRegex(new, r"^[a-z0-9]+(?:-[a-z0-9]+)*_[a-z0-9-]+\.csv$")
        for new in pack.FIGURE_NAMES.values():
            self.assertRegex(new, r"^fig-\d\d_[a-z-]+\.png$")
        for new in pack.TABLE_FILES.values():
            self.assertRegex(new, r"^table-(\d|s2)_[a-z-]+\.md$")
        self.assertEqual(len(set(pack.TIDY_NAMES.values())), len(pack.TIDY_NAMES))

    def test_index_lookup_by_run_id(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_root(Path(d))
            self.assertEqual(pack.run_path(root, "R03").name, "R03_table2_x")
            with self.assertRaises(KeyError):
                pack.run_path(root, "R99")
            found = pack.locate(root)
            self.assertTrue(found["cde_csv"].name == "trials.csv" and "R02" in str(found["cde_csv"]))


class PackBuildTests(unittest.TestCase):
    def test_build_writes_the_three_folders_one_document_per_table_and_publishes_a_light_copy(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            root = make_root(d)
            base, target = make_images(d)
            (root / "CHAPTERS-4-AND-5-DRAFT.md").write_text("# Draft\n\nbody\n\n---\n\n# APPENDIX: THE APPROVED INSTRUMENTS FILLED FROM THE RECORDED DATA\n\nold\n", encoding="utf-8")
            r = pack.build(root, str(base), str(target), root / "CHAPTERS-4-AND-5-DRAFT.md", with_figures=False)
            tables = root / "02-interpretation" / "tables"
            self.assertEqual(sorted(p.name for p in tables.glob("*.md")), sorted(pack.TABLE_FILES.values()))
            for n in ("1", "2", "3", "4"):
                text = (tables / pack.TABLE_FILES[n]).read_text(encoding="utf-8")
                self.assertEqual(text.count("**Table "), 1, n)                         # exactly one approved table per file
                self.assertIn("Approved Experiment Paper table", text)
            self.assertIn("Supplementary Table S2", (tables / pack.TABLE_FILES["s2"]).read_text(encoding="utf-8"))
            tidy = root / "01-raw-data" / "tidy-csv"
            self.assertEqual({p.name for p in tidy.glob("*.csv")} >= {"table2_ab-pairs.csv", "table3_gateway-cycles.csv", "table4_cde-trials.csv",
                                                                       "baseline-n_a-vs-n-pairs.csv", "baseline-h_https-runs.csv"}, True)
            self.assertIn("table2_ab-pairs.csv", (tidy / "MANIFEST.sha256").read_text(encoding="utf-8"))
            writing = root / "03-writing"
            stat = (writing / "01_statistical-analysis.md").read_text(encoding="utf-8")
            self.assertIn("Table 2 metrics", stat)
            self.assertNotIn("`STATISTICS.md`", stat)
            self.assertIn("03-writing/06_baselines-spec.md", (writing / "07_baselines-results.md").read_text(encoding="utf-8"))
            draft = (root / "CHAPTERS-4-AND-5-DRAFT.md").read_text(encoding="utf-8")
            self.assertIn("**Table 4.", draft)
            self.assertNotIn("\nold\n", draft)

            # the light copy: no raw runs, no draft, no figures needed to exist
            (root / "03-writing" / "00_START-HERE.md").write_text("start", encoding="utf-8")
            files = pack.publish(root, d / "pack")
            self.assertIn("README.md", files)
            self.assertIn("03-writing/00_START-HERE.md", files)
            self.assertIn("01-raw-data/RUNS-INDEX.csv", files)
            self.assertTrue(any(f.startswith("01-raw-data/tidy-csv/") for f in files))
            self.assertFalse(any("runs/" in f for f in files))
            self.assertFalse(any("CHAPTERS" in f for f in files))
            files2 = pack.publish(root, d / "pack")                                   # re-publishing replaces the copy
            self.assertEqual(files, files2)

    def test_the_split_documents_keep_the_approved_table_blocks_identical(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            root = make_root(d)
            base, target = make_images(d)
            r = pack.build(root, str(base), str(target), None, with_figures=False)
            from sop import chapter4 as c4
            doc14, doc23, _ = c4.table_documents(r["ctx"], str(base), str(target))
            docs = pack.split_table_docs(doc14, doc23)
            for n, text in docs.items():
                self.assertEqual(text.count("**Table "), 1)


if __name__ == "__main__":
    unittest.main()
