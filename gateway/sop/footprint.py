"""Build firmware environments with PlatformIO and read their footprint.

Reuses gateway/secureota/class2/measure_engine.py for the symbol-attributed
engine size and the link-map groups (it is a script, not a package, so it is
loaded by path).
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .runlog import REPO_ROOT

CLASS2_RAM_BYTES = 50 * 1024       # RFC 7228 Class 2: ~50 KiB RAM
CLASS2_FLASH_BYTES = 250 * 1024    # ~250 KiB flash
CLASS2_DIR = REPO_ROOT / "gateway" / "secureota" / "class2"

RAM_RE = re.compile(r"RAM:\s+\[[= ]*\]\s+([\d.]+)%\s+\(used (\d+) bytes from (\d+) bytes\)")
FLASH_RE = re.compile(r"Flash:\s+\[[= ]*\]\s+([\d.]+)%\s+\(used (\d+) bytes from (\d+) bytes\)")


def find_pio() -> str | None:
    on_path = shutil.which("pio")
    if on_path:
        return on_path
    exe = "pio.exe" if sys.platform == "win32" else "pio"
    sub = "Scripts" if sys.platform == "win32" else "bin"
    p = Path.home() / ".platformio" / "penv" / sub / exe
    return str(p) if p.is_file() else None


def find_project(hint: str | None = None) -> Path | None:
    """The PlatformIO firmware project (the folder holding platformio.ini)."""
    cands = []
    if hint:
        cands.append(Path(hint))
    if os.environ.get("DELTA_FIRMWARE_DIR"):
        cands.append(Path(os.environ["DELTA_FIRMWARE_DIR"]))
    cands.append(Path.home() / "Documents" / "PlatformIO" / "Projects" / "Thesis")
    return next((c for c in cands if (c / "platformio.ini").is_file()), None)


def parse_pio_summary(text: str) -> dict:
    """RAM/Flash lines of a successful `pio run` -> byte counts."""
    r, f = RAM_RE.search(text), FLASH_RE.search(text)
    if not (r and f):
        raise ValueError("no RAM/Flash summary in the PlatformIO output")
    return {"ram_used": int(r.group(2)), "ram_total": int(r.group(3)),
            "flash_used": int(f.group(2)), "flash_total": int(f.group(3))}


@dataclass
class BuildResult:
    env: str
    ok: bool
    build_dir: Path
    error: str = ""
    ram_used: int = 0
    ram_total: int = 0
    flash_used: int = 0
    flash_total: int = 0


def build_env(project: Path, env: str, log_path: Path, pio: str | None = None,
              extra_env: dict | None = None, timeout: int = 900, run=subprocess.run) -> BuildResult:
    pio = pio or find_pio()
    build_dir = project / ".pio" / "build" / env
    if not pio:
        return BuildResult(env, False, build_dir, "PlatformIO (pio) not found")
    environ = dict(os.environ, **(extra_env or {}))
    try:
        proc = run([pio, "run", "-e", env], cwd=project, env=environ, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return BuildResult(env, False, build_dir, f"could not run pio: {e}")
    text = (proc.stdout or "") + (proc.stderr or "")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(text, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        tail = " ".join(text.strip().splitlines()[-3:])
        return BuildResult(env, False, build_dir, f"pio run failed: {tail[:240]}")
    try:
        return BuildResult(env, True, build_dir, **parse_pio_summary(text))
    except ValueError as e:
        return BuildResult(env, False, build_dir, str(e))


def _load_measure_engine():
    spec = importlib.util.spec_from_file_location("measure_engine", CLASS2_DIR / "measure_engine.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def engine_symbols(build_dir: Path) -> dict | None:
    """Symbol-attributed size of the DeltaOTAEngine in a factory build, or None
    when the Xtensa `nm` is not installed (non-Windows path in measure_engine)."""
    me = _load_measure_engine()
    elf = build_dir / "firmware.elf"
    if not (me.NM.is_file() and elf.is_file()):
        return None
    eng = me.stage1_nm(elf)["engine"]
    return {"flash": eng["flash"], "ram": eng["ram"], "symbols": eng["symbols"]}


def map_groups(build_dir: Path) -> dict | None:
    me = _load_measure_engine()
    m = build_dir / "firmware.map"
    return me.stage2_map(m) if m.is_file() else None


def top_ram_symbols(build_dir: Path, n: int = 8) -> list[tuple[str, int]] | None:
    """The n largest static-RAM symbols of a build (demangled), or None without `nm`.
    This is what the engine-only attribution misses: any big global that is not a
    DeltaOTAEngine member (e.g. the DOTA decoder instance)."""
    me = _load_measure_engine()
    elf = build_dir / "firmware.elf"
    if not (me.NM.is_file() and elf.is_file()):
        return None
    out = subprocess.run([str(me.NM), "-C", "--print-size", "--size-sort", str(elf)],
                         capture_output=True, text=True, check=True).stdout
    syms = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        try:
            addr, size = int(parts[0], 16), int(parts[1], 16)
        except ValueError:
            continue
        if size and me.is_ram(addr):
            syms.append((parts[3], size))
    return sorted(syms, key=lambda s: -s[1])[:n]


def group_delta(a: dict, b: dict) -> list[list]:
    """Per link-map group: b minus a, largest flash growth first (a = control, b = bigger build)."""
    rows = []
    for label in b:
        fa, fb = a.get(label, {"flash": 0, "ram": 0}), b[label]
        d_flash, d_ram = fb["flash"] - fa["flash"], fb["ram"] - fa["ram"]
        if d_flash or d_ram:
            rows.append([label, d_flash, d_ram])
    return sorted(rows, key=lambda r: -r[1])
