"""A run directory, its metadata, and the per-SOP results the report is built from."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import platform
import subprocess
from dataclasses import asdict, dataclass, field
from importlib import metadata as importlib_metadata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_ROOT = REPO_ROOT / "sop-results"

# Where the numbers come from. Shown next to every table in the report.
KINDS = ("measured", "modelled", "cited")
STATUSES = ("ok", "skipped", "failed", "not-implemented")


@dataclass
class Table:
    caption: str
    columns: list[str]
    rows: list[list]
    kind: str = "measured"          # measured | modelled | cited
    note: str = ""


@dataclass
class StepResult:
    sop: str                        # "SOP1" ... "SOP5" or "ENV"
    title: str
    status: str = "ok"
    mode: str = "offline"           # offline | hw
    reason: str = ""                # why skipped / failed / not implemented
    method: str = ""                # formal description of how the result was obtained
    summary: str = ""               # one-sentence principal result (for the summary table)
    tables: list[Table] = field(default_factory=list)
    claims: list[str] = field(default_factory=list)          # findings; "[measured, detail] text"
    notes: list[str] = field(default_factory=list)           # observations
    limitations: list[str] = field(default_factory=list)     # scope limits / threats to validity
    not_performed: list[str] = field(default_factory=list)   # parts that did not run in this run, with the reason
    files: list[str] = field(default_factory=list)   # paths relative to the run dir
    data: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"bad status {self.status!r}")
        for t in self.tables:
            if t.kind not in KINDS:
                raise ValueError(f"bad table kind {t.kind!r}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _version(pkg: str) -> str:
    try:
        return importlib_metadata.version(pkg)
    except importlib_metadata.PackageNotFoundError:
        return "not installed"


def collect_meta() -> dict:
    return {
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git("rev-parse", "--short", "HEAD") or "unknown",
        "git_dirty": bool(_git("status", "--porcelain")),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu": platform.processor() or "unknown",
        "cpu_count": os.cpu_count(),
        "packages": {p: _version(p) for p in ("bsdiff4", "cryptography", "aiocoap", "web3", "pyserial")},
        "inputs": [],               # steps append {label, path, bytes, sha256}
        "oscore_mode": "emulated",  # set by the SOP2 step once real OSCORE exists
    }


class RunContext:
    """Owns one run directory. Steps call save() with their StepResult; the
    aggregate results.json is what `report` renders, so steps can be run in
    separate sessions against the same --run directory."""

    def __init__(self, run_dir: Path):
        self.dir = Path(run_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.meta = self._load("meta.json") or collect_meta()
        raw = self._load("results.json") or {}
        self.results: dict[str, dict] = raw

    # -- creation ---------------------------------------------------------
    @classmethod
    def new(cls, root: Path | None = None) -> "RunContext":
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return cls((root or DEFAULT_RESULTS_ROOT) / stamp)

    @classmethod
    def latest(cls, root: Path | None = None) -> "RunContext | None":
        base = root or DEFAULT_RESULTS_ROOT
        runs = sorted(p for p in base.glob("*") if p.is_dir()) if base.is_dir() else []
        return cls(runs[-1]) if runs else None

    # -- io ---------------------------------------------------------------
    def _load(self, name: str):
        p = self.dir / name
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
        return None

    def sub(self, name: str) -> Path:
        d = self.dir / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_json(self, rel: str, obj) -> str:
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
        return rel.replace("\\", "/")

    def write_csv(self, rel: str, columns: list[str], rows: list[list]) -> str:
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(columns)
            w.writerows(rows)
        return rel.replace("\\", "/")

    def add_input(self, label: str, path: Path) -> None:
        self.meta["inputs"] = [i for i in self.meta["inputs"] if i["path"] != str(path)]
        self.meta["inputs"].append(
            {"label": label, "path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
        )

    def save(self, result: StepResult) -> None:
        self.results[result.sop] = asdict(result)
        self.write_json("results.json", self.results)
        self.write_json("meta.json", self.meta)
