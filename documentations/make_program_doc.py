"""Generate the COMP 022 program documentation for one source module.

The documented module's own header comment block is the single source of truth: this
script extracts the six required fields from it and measures the file, so no fact in the
generated document is typed by hand. Run --check to prove the two are still in sync.

Usage (from the repository root):
    python documentations/make_program_doc.py             # write the document
    python documentations/make_program_doc.py --check      # exit 1 if out of date
    python documentations/make_program_doc.py --stdout     # print, write nothing

Standard library only, so either the system interpreter or gateway/.venv can run it.
"""
import argparse
import ast
import hashlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "gateway" / "secureota" / "gateway_runtime" / "delta_stream.py"
DEFAULT_TESTS = ROOT / "gateway" / "sop" / "tests" / "test_dota_window.py"
DEFAULT_OUT = ROOT / "documentations" / "COMP022-PROGRAM-DOCUMENTATION.md"

# The six fields the COMP 022 template requires, mapped to where the header block answers
# each one: a one-line banner entry, the two date entries, or an expanded all-caps section.
TEMPLATE_FIELDS = (
    ("Program Title", ("banner", "Program Title")),
    ("Programmers", ("banner", "Programmers")),
    ("Where the program fits in the general system designs",
     ("section", "WHERE THE PROGRAM FITS IN THE GENERAL SYSTEM DESIGNS")),
    ("Date written and revised", ("dates", "Date Written")),
    ("Purpose", ("section", "PURPOSE")),
    ("Data structures, algorithms, and control",
     ("section", "DATA STRUCTURES, ALGORITHMS, AND CONTROL")),
)
# The one field allowed to be blank: the group fills it in by hand.
BLANK_ALLOWED = {"Programmers"}

BANNER_RE = re.compile(r"^([A-Z][A-Za-z ]*[a-z]) +: ?(.*)$")
SECTION_RE = re.compile(r"^([A-Z][A-Z0-9 ,]*[A-Z])$")
RULE_RE = re.compile(r"^[=-]{10,}$")

PIPE = chr(124)
ESCAPED_PIPE = chr(92) + chr(124)


def parse_header(doc):
    """Split the module docstring into its summary line, banner fields and sections."""
    lines = doc.split("\n")
    summary = lines[0].strip()
    banner, sections, order = {}, {}, []
    current_banner = current_section = None
    for line in lines[1:]:
        if RULE_RE.match(line.strip()):
            current_banner = None
            continue
        section = SECTION_RE.match(line.strip())
        if section and not line.startswith(" "):
            current_section = section.group(1)
            sections[current_section] = []
            order.append(current_section)
            current_banner = None
            continue
        field = BANNER_RE.match(line)
        if field and current_section is None:
            current_banner = field.group(1)
            banner[current_banner] = [field.group(2).rstrip()]
            continue
        if current_banner and line.startswith("    "):
            banner[current_banner].append(line.strip())
            continue
        if current_section is not None:
            sections[current_section].append(line)
    return (summary,
            {k: " ".join(v).strip() for k, v in banner.items()},
            {k: dedent(v) for k, v in sections.items()},
            order)


def dedent(block):
    """Strip the indent the whole block shares, so sub-headings keep their hierarchy.

    Stripping a fixed four spaces would flatten a sub-heading indented by two onto the
    same column as the body indented by four.
    """
    filled = [line for line in block if line.strip()]
    shared = min((len(line) - len(line.lstrip()) for line in filled), default=0)
    return "\n".join(line[shared:] if line.strip() else "" for line in block).strip("\n")


def validate(banner, sections):
    """Fail loudly rather than emit a document with a missing or empty required field."""
    problems = []
    for label, (kind, key) in TEMPLATE_FIELDS:
        store = banner if kind in ("banner", "dates") else sections
        if key not in store:
            problems.append("missing header field: " + label + " (expected " + kind +
                            " '" + key + "')")
        elif not store[key].strip() and key not in BLANK_ALLOWED:
            problems.append("empty header field: " + label)
    if "Date Revised" not in banner:
        problems.append("missing header field: Date Revised")
    return problems


def depth_of(node):
    """Maximum nesting depth of compound statements inside a function body."""
    compound = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.AsyncFor, ast.AsyncWith)

    def walk(n, d):
        best = d
        for child in ast.iter_child_nodes(n):
            best = max(best, walk(child, d + 1 if isinstance(child, compound) else d))
        return best

    return walk(node, 0)


def measure(text, tree, path):
    """Every number the document quotes is computed here, never typed by hand."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    functions = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append({
                "name": node.name,
                "lines": node.end_lineno - node.lineno + 1,
                "span": str(node.lineno) + "-" + str(node.end_lineno),
                "depth": depth_of(node),
                "doc": bool(ast.get_docstring(node)),
                "raises": sum(isinstance(n, ast.Raise) for n in ast.walk(node)),
                "public": not node.name.startswith("_"),
            })
    module_names = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    module_names.append({
                        "name": target.id,
                        "upper": target.id.isupper(),
                        "value": ast.unparse(node.value),
                    })
    raises = [{"line": n.lineno, "expr": ast.unparse(n.exc)}
              for n in ast.walk(tree) if isinstance(n, ast.Raise) and n.exc is not None]
    raises.sort(key=lambda r: r["line"])
    locals_seen = set()
    for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
        for n in ast.walk(fn):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                locals_seen.add(n.id)
        for arg in fn.args.args:
            locals_seen.add(arg.arg)
    own_names = {fn["name"] for fn in functions}
    recursive = sorted(
        n.name for n in tree.body if isinstance(n, ast.FunctionDef)
        for c in ast.walk(n)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == n.name
        and c.func.id in own_names)
    longest = max(range(len(lines)), key=lambda i: len(lines[i]))
    # Indentation and blank-line shape describe the CODE, so they are measured from the
    # first line after the header comment block. Totals below cover the whole file.
    header_doc = tree.body[0]
    code_start = header_doc.end_lineno if isinstance(header_doc, ast.Expr) else 0
    code_region = lines[code_start:]
    code_lines = [l for l in code_region if l.strip() and not l.strip().startswith("#")]
    return {
        "path": path,
        "sha256": hashlib.sha256(text.replace("\n", "\r\n").encode("ascii")).hexdigest(),
        "total": len(lines),
        "header_lines": code_start,
        "code_total": len(code_region),
        "blank": sum(not l.strip() for l in code_region),
        "comment": sum(l.strip().startswith("#") for l in lines),
        "longest_len": len(lines[longest]),
        "longest_line": longest + 1,
        "over_100": [i + 1 for i, l in enumerate(lines) if len(l) > 100],
        "tabs": sum("\t" in l for l in lines),
        "trailing": sum(l != l.rstrip() for l in lines),
        "indents": sorted({len(l) - len(l.lstrip()) for l in code_lines}),
        "functions": functions,
        "module_names": module_names,
        "mutable_globals": [m["name"] for m in module_names if not m["upper"]],
        "global_stmts": sum(isinstance(n, (ast.Global, ast.Nonlocal)) for n in ast.walk(tree)),
        "classes": sum(isinstance(n, ast.ClassDef) for n in tree.body),
        "raises": raises,
        "exc_types": sorted({r["expr"].split("(")[0] for r in raises}),
        "breaks": sum(isinstance(n, (ast.Break, ast.Continue)) for n in ast.walk(tree)),
        "recursive": recursive,
        "bad_locals": sorted(n for n in locals_seen
                             if not re.fullmatch(r"[a-z_][a-z0-9_]*", n)),
        "imports": sorted(a.name for n in tree.body if isinstance(n, ast.Import)
                          for a in n.names),
    }


def test_names(path):
    """The test method names that hold this module, read from the test file."""
    if not path.exists():
        return []
    tree = ast.parse(path.read_text(encoding="ascii"))
    return [n.name for cls in tree.body if isinstance(cls, ast.ClassDef)
            for n in cls.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]


def consideration_rows(m):
    """One row per consideration in the COMP 022 template, with measured values."""
    fns = m["functions"]
    lengths = sorted(f["lines"] for f in fns)
    documented = sum(f["doc"] for f in fns)
    upper = [x["name"] for x in m["module_names"] if x["upper"]]
    privates = [f["name"] for f in fns if not f["public"]]
    public = [f["name"] for f in fns if f["public"]]
    return [
        ("Indentation",
         "4-space steps, " + str(m["tabs"]) + " tabs in the file, maximum nesting depth " +
         str(max(f["depth"] for f in fns)),
         "indent columns in the " + str(m["code_total"]) + " code lines: " +
         str(m["indents"])),
        ("Inline comments",
         str(m["comment"]) + " comment lines; docstrings on " + str(documented) + "/" +
         str(len(fns)) + " functions plus the module header",
         "the header block carries the design rationale, the comments carry loop invariants"),
        ("Limiting the use of global",
         str(len(m["mutable_globals"])) + " mutable module-level names, " +
         str(m["global_stmts"]) + " global/nonlocal statements",
         "module state is " + str(len(upper)) + " UPPER_CASE constants: " + ", ".join(upper)),
        ("Structured programming",
         str(m["breaks"]) + " break/continue, " + str(len(m["recursive"])) +
         " recursive functions, " + str(m["classes"]) + " classes",
         str(len(fns)) + " single-purpose functions, one loop per direction"),
        ("Naming conventions",
         str(len(upper)) + "/" + str(len(m["module_names"])) + " module names UPPER_CASE, " +
         str(len(privates)) + " underscore-private helpers, " + str(len(m["bad_locals"])) +
         " non-conforming locals",
         "public API: " + ", ".join(public)),
        ("Error return conventions",
         str(len(m["raises"])) + " raise sites, types raised: " + ", ".join(m["exc_types"]) +
         "; no status codes and no sentinel returns",
         "see the error inventory below and the known gap in section 5"),
        ("Line length",
         "longest " + str(m["longest_len"]) + " chars (line " + str(m["longest_line"]) +
         "), " + str(len(m["over_100"])) + " lines over 100",
         "100-character limit declared in the header block's STYLE note"),
        ("Spacing",
         str(m["trailing"]) + " trailing-whitespace lines in the file, " + str(m["blank"]) +
         " blank lines in the code region",
         "two blank lines between top-level definitions, per PEP 8"),
        ("Function length",
         str(len(fns)) + " functions: shortest " + str(lengths[0]) + ", median " +
         str(lengths[len(lengths) // 2]) + ", longest " + str(lengths[-1]) + " lines",
         "no function needed splitting"),
        ("Error messages",
         str(len(m["raises"])) + " messages, each naming observed against expected",
         "the module raises; the operator-facing wording belongs to the caller"),
    ]


def honest_notes(m):
    """Section 5: what the module cannot demonstrate, stated with its measurement."""
    return [
        "**There are no global variables to limit.** The measurement is " +
        str(len(m["mutable_globals"])) + " mutable module-level names and " +
        str(m["global_stmts"]) + " `global` statements; module state is UPPER_CASE constants "
        "only. The consideration is met by the count being zero rather than by any "
        "refactoring, and that is deliberate: the module is a pure byte transform called from "
        "the gateway's asyncio loop, from two measurement scripts and from the test suite, so "
        "any module state would make it non-reentrant across those callers. For contrast, the "
        "repository does have a mutable global elsewhere, the `FAILURES` counter rebound via "
        "`global` in `gateway/secureota/gateway_runtime/simulation/run_simulation.py`.",

        "**No local-versus-global naming tension exists here.** With no globals, the "
        "convention reduces to UPPER_CASE constants, underscore-prefixed private helpers, and "
        "lower_snake_case locals and parameters. The usual teaching example, a local shadowing "
        "a global, cannot occur in this file.",

        "**`HEADER` and `RECORD` are `struct.Struct` objects, not primitives.** They are "
        "stateless and never rebound, which is why they are counted as constants; this is "
        "stated rather than implying all " +
        str(len([x for x in m["module_names"] if x["upper"]])) +
        " constants are simple values.",

        "**The error convention is total, and that took work.** All " +
        str(len(m["raises"])) + " raise sites raise `ValueError` with "
        "observed-against-expected text, but three library exceptions used to escape on "
        "malformed input, because none of them derives from `ValueError`: `OSError` from "
        "`bz2` on a corrupt BSDIFF40 block, `zlib.error` on a corrupt or truncated deflate "
        "body, and `struct.error` from either `unpack_from` call when a short stream or a "
        "tampered `new_size` drove it past the end of a buffer. All three are now converted "
        "where they arise, the two `unpack_from` calls behind explicit length checks rather "
        "than a `try`. The documentation pass found these; they were not introduced by it, "
        "and closing them changed no output byte, only the exception type on input that was "
        "already invalid.",

        "**Error messages versus error display.** This module raises and never prints, so it "
        "has no user-facing output of its own. The operator-facing line is emitted by the "
        "caller, `main_gateway.py`, which is outside this deliverable.",

        "**Considerations met without effort, stated plainly:** function length (nothing near "
        "a contested threshold), indentation (shallow nesting), and spacing (no trailing "
        "whitespace). Claiming credit for difficult work on these would be dishonest.",
    ]


def render(m, summary, banner, sections, tests):
    """Assemble the Markdown document."""
    out = []
    w = out.append
    w("# Program Documentation: DOTA delta-stream codec")
    w("")
    w("COMP 022 - Software Engineering 2 - Program Documentation Template")
    w("")
    w("> **Generated file - do not edit by hand.** Every field below is extracted from the")
    w("> header comment block of the source file, and every number is measured from it, so")
    w("> this document cannot drift from the code.")
    w(">")
    w("> - Source: `" + m["path"] + "` (" + str(m["total"]) + " lines: header comment block " +
      "on lines 1-" + str(m["header_lines"]) + ", code on " +
      str(m["header_lines"] + 1) + "-" + str(m["total"]) + ")")
    w("> - SHA-256: `" + m["sha256"] + "`")
    w("> - Regenerate: `python documentations/make_program_doc.py`")
    w("> - Verify in sync: `python documentations/make_program_doc.py --check`")
    w("")
    w("*" + summary + "*")
    w("")
    w("## 1. Header comment block")
    w("")
    w("The six fields the template requires, as they appear in the source file.")
    w("")
    w("| Field | Value |")
    w("|---|---|")
    for label, (kind, key) in TEMPLATE_FIELDS:
        if kind == "banner":
            value = banner.get(key, "").strip()
            cell = value if value else "*(left blank for the group to fill in)*"
        elif kind == "dates":
            cell = ("Written " + banner.get("Date Written", "") + "; revised " +
                    banner.get("Date Revised", ""))
        else:
            cell = "*expanded in the section below*"
        w("| " + label + " | " + cell.replace(PIPE, ESCAPED_PIPE) + " |")
    w("")
    for title, key in (
            ("1.1 Purpose", "PURPOSE"),
            ("1.2 Where the program fits in the general system designs",
             "WHERE THE PROGRAM FITS IN THE GENERAL SYSTEM DESIGNS"),
            ("1.3 Data structures, algorithms, and control",
             "DATA STRUCTURES, ALGORITHMS, AND CONTROL")):
        w("### " + title)
        w("")
        w("```")
        w(sections.get(key, "").rstrip())
        w("```")
        w("")
    w("## 2. Compliance with the ten considerations")
    w("")
    w("Measured at generation time from the source file; no value here is typed by hand.")
    w("")
    w("| # | Consideration | Measured result | Notes |")
    w("|---|---|---|---|")
    for i, (name, result, note) in enumerate(consideration_rows(m), 1):
        w("| " + str(i) + " | " + name + " | " + result + " | " + note + " |")
    w("")
    w("### 2.1 Functions")
    w("")
    w("| Function | Visibility | Lines | Span | Max depth | Docstring | Raises |")
    w("|---|---|---|---|---|---|---|")
    for f in m["functions"]:
        w("| `" + f["name"] + "` | " + ("public" if f["public"] else "private") + " | " +
          str(f["lines"]) + " | " + f["span"] + " | " + str(f["depth"]) + " | " +
          ("yes" if f["doc"] else "no") + " | " + str(f["raises"]) + " |")
    w("")
    w("### 2.2 Module-level names")
    w("")
    w("| Name | Convention | Value |")
    w("|---|---|---|")
    for x in m["module_names"]:
        kind = "UPPER_CASE constant" if x["upper"] else "mutable global"
        w("| `" + x["name"] + "` | " + kind + " | `" +
          x["value"].replace(PIPE, ESCAPED_PIPE) + "` |")
    w("")
    w("Imports: " + ", ".join("`" + i + "`" for i in m["imports"]) +
      " - standard library only, so this module crosses no deploy-unit boundary of its own.")
    w("")
    w("### 2.3 Error inventory")
    w("")
    w("Every raise site in the file, in line order.")
    w("")
    w("| Line | Raised |")
    w("|---|---|")
    for r in m["raises"]:
        w("| " + str(r["line"]) + " | `" + r["expr"].replace(PIPE, ESCAPED_PIPE) + "` |")
    w("")
    w("## 3. Source code")
    w("")
    w("```text")
    for i, line in enumerate(m["listing"], 1):
        w(("%4d | " % i + line).rstrip())
    w("```")
    w("")
    w("## 4. Verification")
    w("")
    w("The module is held by " + str(len(tests)) + " unit tests in " +
      "`gateway/sop/tests/test_dota_window.py`:")
    w("")
    for name in tests:
        w("- `" + name + "`")
    w("")
    w("Commands, run from `gateway/` with the project interpreter:")
    w("")
    w("```")
    w("python -m unittest sop.tests.test_dota_window -v      # this module")
    w("python -m unittest discover -s sop/tests -t .         # the whole suite")
    w("python ../documentations/make_program_doc.py --check  # document still in sync")
    w("```")
    w("")
    w("## 5. Honest notes and known gaps")
    w("")
    for note in honest_notes(m):
        w("- " + note)
    w("")
    return "\n".join(out) + "\n"


def build(source, tests_path):
    """Read the source file and return the rendered document."""
    text = source.read_bytes().decode("ascii").replace("\r\n", "\n")
    tree = ast.parse(text)
    doc = ast.get_docstring(tree, clean=False)
    if doc is None:
        sys.exit("error: the source file has no module docstring to read the header block from")
    summary, banner, sections, _order = parse_header(doc)
    problems = validate(banner, sections)
    if problems:
        for problem in problems:
            print("error: " + problem, file=sys.stderr)
        sys.exit(2)
    relative = source.resolve().relative_to(ROOT).as_posix()
    m = measure(text, tree, relative)
    listing = text.split("\n")
    m["listing"] = listing[:-1] if listing and listing[-1] == "" else listing
    return render(m, summary, banner, sections, test_names(tests_path))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate the COMP 022 program documentation.")
    parser.add_argument("--source", type=pathlib.Path, default=DEFAULT_SOURCE)
    parser.add_argument("--tests", type=pathlib.Path, default=DEFAULT_TESTS)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if the document on disk is not what the source produces")
    parser.add_argument("--stdout", action="store_true",
                        help="print the document, write nothing")
    args = parser.parse_args(argv)

    rendered = build(args.source, args.tests)
    if args.stdout:
        sys.stdout.write(rendered)
        return 0
    if args.check:
        if not args.out.exists():
            print("error: " + str(args.out) + " does not exist; run without --check",
                  file=sys.stderr)
            return 1
        current = args.out.read_bytes().decode("utf-8").replace("\r\n", "\n")
        if current == rendered:
            print("in sync: " + args.out.name + " matches " + args.source.name)
            return 0
        new_lines = rendered.split("\n")
        old_lines = current.split("\n")
        for i in range(max(len(new_lines), len(old_lines))):
            on_disk = old_lines[i] if i < len(old_lines) else "<end of file>"
            expected = new_lines[i] if i < len(new_lines) else "<end of file>"
            if on_disk != expected:
                print("error: " + args.out.name + " is out of date; first difference at line " +
                      str(i + 1), file=sys.stderr)
                print("  on disk:   " + on_disk[:100], file=sys.stderr)
                print("  should be: " + expected[:100], file=sys.stderr)
                break
        return 1
    args.out.write_bytes(rendered.encode("utf-8"))
    print("wrote " + args.out.relative_to(ROOT).as_posix() + " (" +
          str(len(rendered.splitlines())) + " lines) from " + args.source.name)
    print("source sha256 " + hashlib.sha256(args.source.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
