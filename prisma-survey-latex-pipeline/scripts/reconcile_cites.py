"""Cite-key reconciliation across a split manuscript.

  python reconcile_cites.py --manuscript manuscript

Checks every \\cite/\\citep/\\citet/\\citeauthor key against references.bib, and prints the two lists
that must be empty before building. Also flags duplicate bib keys, which produce silent last-wins
bibliography entries.
"""
import argparse
import glob
import os
import re
import sys
from collections import Counter

CITE = re.compile(r"\\cite[tpae]?\*?(?:\[[^\]]*\])?\{([^}]+)\}")
KEY = re.compile(r"@\w+\{\s*([^,\s]+)\s*,")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manuscript", required=True)
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    bib_path = os.path.join(a.manuscript, "references.bib")
    if not os.path.exists(bib_path):
        sys.exit("no references.bib in " + a.manuscript)
    bib_text = open(bib_path, encoding="utf-8", errors="replace").read()
    keys = KEY.findall(bib_text)
    bib_keys = set(keys)
    dups = sorted(k for k, n in Counter(keys).items() if n > 1)

    cited, where = set(), {}
    for path in sorted(glob.glob(os.path.join(a.manuscript, "*.tex"))):
        text = open(path, encoding="utf-8", errors="replace").read()
        for m in CITE.finditer(text):
            for k in m.group(1).split(","):
                k = k.strip()
                if k:
                    cited.add(k)
                    where.setdefault(k, os.path.basename(path))

    missing = sorted(cited - bib_keys)
    unused = sorted(bib_keys - cited)
    print("cited keys: %d   bib entries: %d" % (len(cited), len(bib_keys)))
    print("MISSING in bib (%d): %s" % (len(missing), ", ".join(missing) or "none"))
    print("UNUSED in bib (%d): %s" % (len(unused), ", ".join(unused) or "none"))
    if dups:
        print("DUPLICATE bib keys (%d): %s" % (len(dups), ", ".join(dups)))
    if missing:
        print("\nfirst occurrence of each missing key:")
        for k in missing[:25]:
            print("  %s  <- %s" % (k, where.get(k, "?")))
    ok = not missing and not dups
    print("\nRECONCILE", "OK" if ok and not unused else ("OK" if ok else "FAILED"))
    print("UNUSED entries are harmless to the PDF but should be deleted before submission.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
