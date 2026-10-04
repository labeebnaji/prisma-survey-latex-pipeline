"""Resolve corpus DOIs through Crossref and audit references.bib against the truth.

  python verify_venues.py --corpus corpus/tierA.json --bib manuscript/references.bib

Evidence CSV is append-only and resumable: reruns only hit DOIs not already present. Once the CSV
exists, the bib audit runs offline against it. Column names from older runs are accepted via aliases,
and HTML entities in container titles are unescaped.

Flags printed:
  TITLE_DRIFT      corpus title vs resolver title disagree
  VENUE_MISMATCH   bib journal/booktitle not present in the resolved container
  AUTHOR_MISMATCH  no surname overlap between bib and resolver authors (needs an authors column)
  MOJIBAKE         cp1252 damage in a bib field
  NOT_INDEXED      a cited DOI Crossref answers as absent (grey literature must be declared)
  UNRESOLVED       a cited DOI no run has ever resolved -- unverified, not clean

A DOI the resolver returns nothing for is logged with status=error and retried on the next run; only
an explicit empty record is cached as not_found.
"""
import argparse
import ast
import csv
import difflib
import html
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_client import McpClient  # noqa: E402

ENTRY = re.compile(r"@(\w+)\{([^,]+),\s*(.*?)\n\}", re.S)
FIELD = re.compile(r"(\w+)\s*=\s*[{\"](.*?)[}\"]\s*,?\s*$", re.M | re.S)
DOI_ANY = re.compile(r"10\.\d{4,9}/[^\s\"'}]+", re.I)
BAD = re.compile(r"(a¢|Ã|ï¿½|Ð|ذ)")
TITLE_COLS = ("crossref_title", "resolved_title", "screen_title", "title")


def parse_bib(path):
    out = {}
    for m in ENTRY.finditer(open(path, encoding="utf-8", errors="replace").read()):
        fields = {f.lower(): re.sub(r"\s+", " ", v).strip("{}")
                  for f, v in FIELD.findall(m.group(3))}
        out[m.group(2).strip()] = {"type": m.group(1), **fields}
    return out


def bib_doi(fields):
    for name in ("doi", "url", "note", "ee"):
        hit = DOI_ANY.search(fields.get(name, ""))
        if hit:
            return hit.group(0).rstrip(".;").lower()
    return ""


def surnames(author_str):
    parts = re.split(r";|,| and ", author_str or "")
    return {re.sub(r"[^a-z]", "", p.strip().split()[-1].lower())
            for p in parts if len(p.strip().split()) > 1}


def load_evidence(path):
    resolved, not_found = {}, set()
    if not os.path.exists(path):
        return resolved, not_found
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            row = {k: (v or "") for k, v in row.items() if k}
            doi = row.get("doi", "").strip().lower()
            if not doi:
                continue
            title = html.unescape(next((row[c] for c in TITLE_COLS if row.get(c)), ""))
            if row.get("status") == "resolved" and title:
                resolved[doi] = {"title": title,
                                 "container": html.unescape(row.get("container", "")),
                                 "authors": row.get("authors", "")}
            elif row.get("status") == "not_found":
                not_found.add(doi)
            # status=error is a timeout or an empty resolver answer, not evidence of absence: those
            # DOIs stay out of both sets so the next run retries them.
    return resolved, not_found


def resolver_fields(j):
    """The resolver returns no top-level container: the venue lives inside extra['container_title']."""
    e = j.get("extra")
    if isinstance(e, str):
        try:
            e = ast.literal_eval(e)
        except (ValueError, SyntaxError):
            e = {}
    e = e if isinstance(e, dict) else {}
    title = re.sub(r"<[^>]+>", " ", str(j.get("title") or ""))
    ym = re.search(r"(19|20)\d{2}", str(j.get("published_date") or j.get("year") or ""))
    return {
        "title": re.sub(r"\s+", " ", title).strip(),
        "container": str(j.get("container") or j.get("venue") or e.get("container_title") or ""),
        "publisher": str(j.get("publisher") or e.get("publisher") or ""),
        "type": str(j.get("type") or e.get("crossref_type") or j.get("categories") or ""),
        "year": ym.group(0) if ym else "",
        "authors": str(j.get("authors") or ""),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--bib", required=True)
    ap.add_argument("--evidence", default="corpus/evidence/venue_resolution.csv")
    ap.add_argument("--tool", default="get_crossref_paper_by_doi")
    ap.add_argument("--limit", type=int, default=0, help="cap new DOI lookups this run")
    ap.add_argument("--no-network", action="store_true")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    os.makedirs(os.path.dirname(a.evidence) or ".", exist_ok=True)
    bib = parse_bib(a.bib)
    resolved, not_found = load_evidence(a.evidence)
    header_cols = []
    if os.path.exists(a.evidence):
        header_cols = [c.strip().lower() for c in
                       open(a.evidence, encoding="utf-8-sig").readline().split(",")]
    records = json.load(open(a.corpus, encoding="utf-8"))

    todo = []
    for r in records:
        doi = str(r.get("doi", "")).lower()
        if doi and doi not in resolved and doi not in not_found:
            todo.append((doi, r.get("title", "")))
    if a.limit:
        todo = todo[:a.limit]

    if todo and not a.no_network:
        c = McpClient()
        f = open(a.evidence, "a", newline="", encoding="utf-8")
        w = csv.writer(f)
        if not os.path.getsize(a.evidence):
            w.writerow(["doi", "crossref_title", "container", "publisher", "type", "year",
                        "authors", "status"])
        for i, (doi, title) in enumerate(todo, 1):
            j = {}
            for attempt in (1, 2):
                try:
                    j = json.loads(c.call(a.tool, {"doi": doi}, 60) or "{}")
                except Exception:
                    j = {}
                if j:
                    break
                time.sleep(1.5)          # an empty answer is usually a throttle, not an absent DOI
            rf = resolver_fields(j)
            ct = rf["title"][:220]
            cont = rf["container"][:160]
            auth = rf["authors"][:300]
            status = "resolved" if ct else ("error" if not j else "not_found")
            w.writerow([doi, ct, cont, rf["publisher"][:80], rf["type"][:40], rf["year"], auth,
                        status])
            f.flush()
            if ct:
                resolved[doi] = {"title": ct, "container": cont, "authors": auth}
            elif status == "not_found":
                not_found.add(doi)
            if title and ct and difflib.SequenceMatcher(
                    None, title.lower(), ct.lower()).ratio() < 0.72:
                print("TITLE_DRIFT  %s\n  corpus: %s\n  crossref: %s"
                      % (doi, title[:110], ct[:110]))
            if i % 25 == 0:
                print("resolved %d/%d" % (i, len(todo)), flush=True)
        f.close()
        c.close()
    else:
        print("skipping %d uncached DOIs (%s)"
              % (len(todo), "--no-network" if a.no_network else "limit"))

    if header_cols and "authors" not in header_cols:
        print("WARNING  evidence CSV has no 'authors' column: AUTHOR_MISMATCH checks are being "
              "skipped silently. Delete the CSV and re-resolve the DOIs before trusting the bib audit.")
    print("evidence rows resolved: %d   not in Crossref: %d   bib entries: %d"
          % (len(resolved), len(not_found), len(bib)))
    print("\n=== bib audit ===")
    flagged = 0
    audited = 0
    blind = 0
    for key, fld in sorted(bib.items()):
        doi = bib_doi(fld)
        truth = resolved.get(doi)
        if not truth:
            continue
        audited += 1
        stated = fld.get("journal") or fld.get("booktitle") or ""
        if stated and not truth["container"]:
            blind += 1
        elif stated:
            toks = [t for t in re.split(r"\s+", stated.lower()) if len(t) > 3][:2]
            if toks and not any(t in truth["container"].lower() for t in toks):
                print("VENUE_MISMATCH %s\n  bib: %r\n  crossref: %r  (%s)"
                      % (key, stated, truth["container"], doi))
                flagged += 1
        tf, rf = surnames(fld.get("author", "")), surnames(truth["authors"])
        if tf and rf and not (tf & rf):
            print("AUTHOR_MISMATCH %s\n  bib: %r\n  crossref: %r  (%s)"
                  % (key, fld.get("author"), truth["authors"], doi))
            flagged += 1
        if BAD.search(json.dumps(fld)):
            print("MOJIBAKE %s" % key)
            flagged += 1
    cited_unindexed = sorted({bib_doi(f) for f in bib.values()} & not_found)
    if cited_unindexed:
        print("NOT_INDEXED (declare as grey or fix the DOI): %s" % ", ".join(cited_unindexed[:12]))
    never = sorted({bib_doi(f) for f in bib.values() if bib_doi(f)} - set(resolved) - not_found)
    if never:
        print("UNRESOLVED (a bib DOI the corpus never carried, so Crossref was never asked -- these "
              "are unverified, not clean): %s" % ", ".join(never[:12]))
        flagged += len(never)
    if blind:
        print("venue check blind for %d audited entries: Crossref carries no container for them "
              "(preprints, datasets, grey reports). Check those venues by hand." % blind)
    print("bib entries audited against evidence: %d of %d" % (audited, len(bib)))
    if audited == 0:
        print("Nothing to audit: either no bib entry carries a DOI, or the DOIs they carry were never "
              "resolved into the evidence CSV. Add doi = {10.xxxx/...} to each entry and resolve the "
              "corpus with the same --evidence file before trusting this section.")
    print("Grey standards are cited by URL, not by DOI; say so in the methodology instead of leaving "
          "them unverified.")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
