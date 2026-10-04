"""Build the manuscript and fail loudly if citations, references, or symbols are broken.

  python build.py --manuscript manuscript --main main.tex

Sequence: pdflatex -> bibtex -> pdflatex -> pdflatex, then scan the log and report the page count.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

MIN_FREE = 500 * 1024 * 1024
ERRORS = (
    r"! LaTeX Error",
    r"! Undefined control sequence",
    r"! Package .* Error",
    r"Citation .* undefined",
    r"Reference .* undefined",
    r"There were undefined references",
    r"No \\string\\bibdata",
    r"I couldn't open (database|file)",
)


def run(cmd, cwd):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return p


def tool(name):
    path = shutil.which(name)
    if path:
        return path
    for root in (r"C:\Program Files\MiKTeX\miktex\bin\x64",
                 r"C:\Program Files\texlive\2024\bin\windows"):
        cand = os.path.join(root, name + ".exe")
        if os.path.exists(cand):
            return cand
    sys.exit("%s not found - run scripts/preflight.py" % name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manuscript", required=True)
    ap.add_argument("--main", default="main.tex")
    ap.add_argument("--keep-aux", action="store_true")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    cwd = os.path.abspath(a.manuscript)
    if not os.path.exists(os.path.join(cwd, a.main)):
        sys.exit("no %s in %s" % (a.main, cwd))
    free = shutil.disk_usage(cwd).free
    if free < MIN_FREE:
        sys.exit("only %.0f MB free on this drive - pdflatex will die mid-run. Clean up first."
                 % (free / 1024 ** 2))

    pdf, base = a.main[:-4], a.main[:-4]
    for step, cmd in (("pdflatex", [tool("pdflatex"), "-interaction=nonstopmode", "-halt-on-error", a.main]),
                      ("bibtex", [tool("bibtex"), base]),
                      ("pdflatex", [tool("pdflatex"), "-interaction=nonstopmode", "-halt-on-error", a.main]),
                      ("pdflatex", [tool("pdflatex"), "-interaction=nonstopmode", "-halt-on-error", a.main])):
        p = run(cmd, cwd)
        if p.returncode != 0:
            tail = (p.stdout or "") + (p.stderr or "")
            print("%s FAILED (exit %d)" % (step, p.returncode))
            print("\n".join(line for line in tail.splitlines() if line.startswith("!"))[:2000])
            return 1
        print("%s ok" % step)

    log = open(os.path.join(cwd, pdf + ".log"), encoding="utf-8", errors="replace").read()
    hits = []
    for pat in ERRORS:
        hits += [m.group(0) for m in re.finditer(pat, log)]
    missing_files = re.findall(r"(!  LaTeX Warning: File `(.+?)' not found.)", log)
    print("\n=== log scan ===")
    if hits:
        for h in sorted(set(hits))[:40]:
            print("  " + h)
    else:
        print("  clean")
    for _, name in missing_files:
        print("  MISSING FILE: %s" % name)

    try:
        info = run([tool("pdfinfo"), pdf + ".pdf"], cwd).stdout
        pages = re.search(r"Pages:\s+(\d+)", info)
        print("PDF pages: %s" % (pages.group(1) if pages else "?"))
    except Exception as exc:
        print("pdfinfo failed: %s" % exc)

    if not a.keep_aux:
        for ext in (".blg", ".out"):
            p = os.path.join(cwd, pdf + ext)
            if os.path.exists(p):
                os.remove(p)
    if hits:
        print("\nBUILD NOT DELIVERABLE - fix the log findings above.")
        return 1
    print("\nBUILD OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
