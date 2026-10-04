"""Check that every tool the pipeline needs is actually present."""
import glob
import os
import shutil
import subprocess
import sys

MIN_FREE = 500 * 1024 * 1024
WARN_FREE = 2 * 1024 ** 3


def find_latex():
    out = {}
    for tool in ("pdflatex", "bibtex", "pdfinfo"):
        path = shutil.which(tool)
        if not path:
            roots = [r"C:\Program Files\MiKTeX\miktex\bin\x64",
                     r"C:\Program Files\texlive\2024\bin\windows"]
            hits = []
            for root in roots:
                for ext in (".exe", ""):
                    cand = os.path.join(root, tool + ext)
                    if os.path.exists(cand):
                        hits.append(cand)
            path = hits[0] if hits else None
        out[tool] = path
    return out


def main():
    ok = True
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from mcp_client import find_exe
    exe = find_exe()
    print("paper-search-mcp :", exe if os.path.exists(exe) else "MISSING")
    ok &= os.path.exists(exe)

    for tool, path in find_latex().items():
        print("%-16s: %s" % (tool, path or "MISSING"))
        ok &= bool(path)

    try:
        import matplotlib  # noqa: F401
        print("matplotlib       : ok")
    except Exception as exc:
        print("matplotlib       : MISSING (%s)" % exc)
        ok = False

    free = shutil.disk_usage(os.getcwd()).free
    if free < MIN_FREE:
        print("free disk        : %.1f GB  <-- BELOW THE BUILD FLOOR" % (free / 1024 ** 3))
        ok = False
    elif free < WARN_FREE:
        print("free disk        : %.1f GB  (low: pdflatex writes aux+pdf, corpus JSON grows fast)"
              % (free / 1024 ** 3))
    else:
        print("free disk        : %.1f GB" % (free / 1024 ** 3))

    if len(sys.argv) > 1 and sys.argv[1] == "--probe":
        here = os.path.dirname(os.path.abspath(__file__))
        p = subprocess.run([sys.executable, os.path.join(here, "mcp_client.py"), "--list-tools"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        print("--- tools ---")
        print((p.stdout or p.stderr)[:1500])

    print("PREFLIGHT", "OK" if ok else "FAILED - fix the MISSING lines above first")
    return 0 if ok else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
