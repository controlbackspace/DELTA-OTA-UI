"""Render the formal evidence report (SOP-REPORT.md) from a run directory.

The document is written for a review panel: purpose and scope, experimental
setup, then for each statement of the problem the research question, method,
findings, tables, observations and limitations, followed by a summary table,
the overall limitations and how to reproduce the results.

Rendering is separate from measuring, so `python -m sop report` can rebuild the
report from stored data. A statement that was not run is reported as such, and
SOP 5 is reserved for the implementation phase: the report never implies a
result it does not hold.
"""
from __future__ import annotations

import re

from .runlog import RunContext

THESIS_TITLE = "Securing Delta-OTA for Constrained IoT via OSCORE and Ledger-Anchored Release Governance"

SOP_QUESTIONS = {
    "SOP1": "What is the measurable impact of binary volumetric differencing on optimizing the firmware payload "
            "footprint and mitigating network bandwidth saturation for constrained Class 2 microcontrollers?",
    "SOP2": "What is the quantitative reduction in computational memory overhead and transmission latency achieved "
            "by integrating the OSCORE protocol compared to standard cryptographic handshakes in constrained networks?",
    "SOP3": "What is the deterministic reliability of utilizing ledger-anchored smart contracts to guarantee "
            "cryptographic authenticity and execute absolute payload revocation against compromised firmware updates?",
    "SOP4": "What is the measurable efficiency of offloading Web3 logic to a dedicated Edge Gateway in terms of "
            "preserving the physical memory envelope (SRAM) and processing cycles of the target node?",
    "SOP5": "What is the systemic performance of the synthesized Ledger Anchored Delta-OTA architecture across "
            "continuous hardware metrics (cryptographic execution time, memory allocation limits, and CoAP network "
            "latency) under automated multi-cycle testing?",
}

BASIS = {"measured": "Measured", "modelled": "Modelled", "cited": "Literature"}
BASIS_NOTE = {
    "measured": "observed on the stated system",
    "modelled": "computed from stated assumptions",
    "cited": "values from the cited specifications",
}

SOP5_TEXT = (
    "Statement 5 concerns the performance of the complete architecture over 60 automated test cycles on the target "
    "hardware. It is reserved for the implementation phase that follows approval of the proposed system and is not "
    "reported in this edition. The instrumentation developed for this report (host-timestamped serial capture and "
    "parsing, summary statistics with confidence intervals, the gateway status feed and the chain driver) is the "
    "basis on which that campaign will be run."
)

CLAIM_TAG = re.compile(r"^\[(measured|modelled|cited)([^\]]*)\]\s*(.*)$", re.IGNORECASE | re.DOTALL)


def _esc(v) -> str:
    return str(v).replace("|", "\\|").replace("\n", " ")


def _finding(text: str) -> str:
    """'[measured, real firmware] text' -> 'text (Measured; real firmware).'"""
    m = CLAIM_TAG.match(text.strip())
    if not m:
        return text.strip()
    basis = BASIS[m.group(1).lower()]
    detail = m.group(2).strip(" ,")
    body = m.group(3).strip()
    return f"{body} *({basis}{'; ' + detail if detail else ''}.)*"


class _Numbering:
    def __init__(self):
        self.n = 0

    def next(self) -> int:
        self.n += 1
        return self.n


def _table(t: dict, num: int) -> list[str]:
    head = "| " + " | ".join(_esc(c) for c in t["columns"]) + " |"
    sep = "|" + "|".join("---" for _ in t["columns"]) + "|"
    body = ["| " + " | ".join(_esc(c) for c in row) + " |" for row in t["rows"]]
    out = [f"**Table {num}.** {t['caption']} *({BASIS[t['kind']]})*", "", head, sep, *body]
    if t.get("note"):
        out += ["", f"*{t['note']}*"]
    return out + [""]


def _setup(ctx: RunContext, results: dict, nums: _Numbering) -> list[str]:
    meta = ctx.meta
    when = str(meta.get("started_utc", ""))[:19].replace("T", " ")
    pk = meta.get("packages") or {}
    lines = [
        "## 2. Experimental Setup",
        "",
        f"- **Date (UTC):** {when}",
        f"- **Software revision:** `{meta.get('git_commit')}`"
        + (" (with uncommitted changes)" if meta.get("git_dirty") else ""),
        f"- **Host:** {meta.get('platform')}; {meta.get('cpu_count')} logical CPUs; Python {meta.get('python')}",
        "- **Libraries:** " + ", ".join(f"{k} {v}" for k, v in pk.items() if v != "not installed"),
        f"- **Framing under evaluation:** OSCORE-style AEAD framing (`{meta.get('oscore_mode')}`)",
    ]
    for i in meta.get("inputs", []):
        lines.append(f"- **Input, {i['label']}:** `{i['path']}` ({i['bytes']:,} bytes; SHA-256 `{i['sha256']}`)")
    lines.append("")
    env = results.get("ENV")
    if env and env.get("tables"):
        for t in env["tables"]:
            lines += _table(t, nums.next())
    return lines


def _section(n: int, sop: str, r: dict | None, nums: _Numbering) -> list[str]:
    out = [f"### 3.{n} Statement of the Problem {n}", "", f"**Research question.** {SOP_QUESTIONS[sop]}", ""]
    if r is None:
        return out + ["*This statement was not evaluated in this run.*", ""]
    if r["status"] in ("skipped", "not-implemented"):
        return out + [f"*This statement could not be evaluated in this run: {r.get('reason') or 'not available'}.*", ""]
    if r["status"] == "failed":
        out += [f"*The evaluation did not complete: {r.get('reason') or 'see raw data'}.*", ""]
    if r.get("method"):
        out += [f"**Method.** {r['method']}", ""]
    if r.get("summary"):
        out += [f"**Principal result.** {r['summary']}", ""]
    if r["claims"]:
        out += ["**Findings.**", ""]
        out += [f"{i}. {_finding(c)}" for i, c in enumerate(r["claims"], 1)]
        out.append("")
    for t in r["tables"]:
        out += _table(t, nums.next())
    if r["notes"]:
        out += ["**Observations.**", ""]
        out += [f"- {x}" for x in r["notes"]]
        out.append("")
    if r.get("limitations"):
        out += ["**Limitations.**", ""]
        out += [f"- {x}" for x in r["limitations"]]
        out.append("")
    if r.get("not_performed"):
        out += ["**Not performed in this run.**", ""]
        out += [f"- {x}" for x in r["not_performed"]]
        out.append("")
    if r["files"]:
        out += ["*Data files:* " + ", ".join(f"`{f}`" for f in r["files"]), ""]
    return out


def render(ctx: RunContext) -> str:
    results = ctx.results
    nums = _Numbering()
    lines = [
        "# Experimental Evidence Report",
        "",
        f"**{THESIS_TITLE}**",
        "",
        "*Evidence for Statements of the Problem 1 to 4*",
        "",
        "## 1. Purpose and Scope",
        "",
        "This report presents the experimental evidence gathered for Statements of the Problem 1 to 4 of the study. "
        "Each result is classified by its basis: **Measured** (observed on the stated system), **Modelled** (computed "
        "from stated assumptions) or **Literature** (values taken from the cited specifications). Statement 5 "
        "(multi-cycle systemic performance) is reserved for the implementation phase and is described in Section 3.5.",
        "",
    ]
    lines += _setup(ctx, results, nums)

    lines += ["## 3. Results", ""]
    for n, sop in enumerate(("SOP1", "SOP2", "SOP3", "SOP4"), 1):
        lines += _section(n, sop, results.get(sop), nums)
    lines += ["### 3.5 Statement of the Problem 5", "", f"**Research question.** {SOP_QUESTIONS['SOP5']}", "", SOP5_TEXT, ""]

    # ---- 4. summary ------------------------------------------------------------
    rows = []
    for n, sop in enumerate(("SOP1", "SOP2", "SOP3", "SOP4"), 1):
        r = results.get(sop)
        if r is None:
            rows.append([f"SOP {n}", "Not evaluated in this run", "-"])
        elif r["status"] in ("skipped", "not-implemented"):
            rows.append([f"SOP {n}", f"Not evaluated: {r.get('reason') or 'not available'}", "-"])
        else:
            first = CLAIM_TAG.match(r["claims"][0]) if r["claims"] else None
            basis = BASIS[first.group(1).lower()] if first else "-"
            rows.append([f"SOP {n}", r.get("summary") or "See Section 3", basis])
    rows.append(["SOP 5", "Reserved for the implementation phase (60 automated cycles)", "-"])
    lines += ["## 4. Summary of Findings", "", "| Statement | Principal result | Basis |", "|---|---|---|"]
    lines += ["| " + " | ".join(_esc(c) for c in row) + " |" for row in rows]
    lines.append("")

    # ---- 5. limitations ------------------------------------------------------------
    lines += ["## 5. Limitations and Threats to Validity", ""]
    lines += [
        "- Modelled values (airtime, fleet-update time, handshake network cost, CPU cycles) follow from the stated "
        "assumptions and are lower bounds; they are not measurements of a deployed network.",
        "- Timings labelled gateway-host were taken on a general-purpose computer with hardware AES acceleration and "
        "are not timings of the target microcontroller.",
        "- Literature values are taken from the cited specifications and are approximate where the quantity depends "
        "on protocol parameters.",
    ]
    any_step = False
    for n, sop in enumerate(("SOP1", "SOP2", "SOP3", "SOP4"), 1):
        r = results.get(sop)
        if r:
            for x in r.get("limitations", []):
                lines.append(f"- *SOP {n}:* {x}")
                any_step = True
    if any_step:
        lines.append("")
    else:
        lines.append("")
    pending = [(n, x) for n, sop in enumerate(("SOP1", "SOP2", "SOP3", "SOP4"), 1)
               for x in (results.get(sop) or {}).get("not_performed", [])]
    if pending:
        lines += ["**Not performed in this run:**", ""]
        lines += [f"- *SOP {n}:* {x}" for n, x in pending]
        lines.append("")

    # ---- 6. reproducibility -----------------------------------------------------------
    lines += [
        "## 6. Reproducibility",
        "",
        "All results in this report were produced by the evidence runner included with the source code "
        "(`gateway/sop`). The runner records the software revision, library versions and the SHA-256 of every input "
        "file (Section 2); randomised trials use fixed seeds. The complete set of evaluations is run with "
        "`python -m sop all` (or `gateway\\sop-run.bat`); an individual statement is run with `python -m sop sop1` "
        "to `sop4`. Raw logs and tabular data are stored beside this report in the run directory and are listed "
        "under each statement above.",
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def write_report(ctx: RunContext) -> str:
    text = render(ctx)
    (ctx.dir / "SOP-REPORT.md").write_text(text, encoding="utf-8")
    return str(ctx.dir / "SOP-REPORT.md")
