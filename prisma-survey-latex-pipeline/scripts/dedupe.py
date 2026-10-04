"""Merge search output, deduplicate on DOI then normalized title, write corpus + evidence log.

  python dedupe.py --indir searches --outdir corpus
"""
import argparse
import ast
import csv
import glob
import json
import os
import re
import sys


def norm_title(t):
    t = re.sub(r"[^a-z0-9 ]+", " ", (t or "").lower())
    return re.sub(r"\s+", " ", t).strip()


def year_of(r):
    for key in ("published_date", "publication_date", "year", "date", "published"):
        v = str(r.get(key) or "")
        m = re.search(r"(19|20)\d{2}", v)
        if m:
            return m.group(0)
    return ""


def extra_of(r):
    e = r.get("extra", "")
    if isinstance(e, str):
        try:
            e = ast.literal_eval(e)
        except Exception:
            e = {}
    return e if isinstance(e, dict) else {}


def normalize(raw, src):
    e = extra_of(raw)
    doi = str(raw.get("doi") or raw.get("paper_id") or "").strip().lower()
    if not doi.startswith("10."):
        doi = str(raw.get("doi") or "").strip().lower()
    return {
        "title": re.sub(r"\s+", " ", str(raw.get("title") or "")).strip(),
        "title_norm": norm_title(raw.get("title")),
        "doi": doi,
        "year": year_of(raw),
        "source_primary": src,
        "sources": [src],
        "abstract": re.sub(r"<[^>]+>", " ", str(raw.get("abstract") or "")).strip(),
        "authors": str(raw.get("authors") or e.get("authors") or ""),
        "container": str(e.get("container_title") or raw.get("venue") or ""),
        "publisher": str(e.get("publisher") or ""),
        "type": str(e.get("crossref_type") or raw.get("categories") or ""),
        "url": str(raw.get("url") or ""),
        "citations": raw.get("citations", raw.get("citation_count", "")),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", required=True)
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(os.path.join(a.outdir, "evidence"), exist_ok=True)

    raws, seen_meta = [], {}
    skip = ("queries.json", "_summary.json")
    for path in sorted(glob.glob(os.path.join(a.indir, "*.json"))):
        if os.path.basename(path) in skip:
            continue
        src = os.path.basename(path).rsplit("_", 1)[0]
        try:
            rows = json.load(open(path, encoding="utf-8"))
        except Exception as exc:
            print("SKIP unreadable %s (%s)" % (path, exc))
            continue
        if not isinstance(rows, list):
            continue
        if any(isinstance(r, dict) and ("query" in r or "tool" in r) for r in rows[:1]):
            print("SKIP %s (looks like a query file, not search output)" % os.path.basename(path))
            continue
        seen_meta[src] = seen_meta.get(src, 0) + len(rows)
        for r in rows:
            if isinstance(r, dict) and (r.get("title") or r.get("name")):
                raws.append(normalize(r, src))

    by_doi, by_title, records = {}, {}, []
    dup_doi = dup_no_doi = 0
    collisions = []                      # same title, two different DOIs: distinct works do collide,
    for r in raws:                       # so those pairs are reported for a human, never auto-merged
        if not r["title_norm"]:
            continue
        kept = by_doi.get(r["doi"]) if r["doi"] else None
        if kept is None and not r["doi"]:
            kept = by_title.get(r["title_norm"])
        elif kept is None and r["doi"]:
            other = by_title.get(r["title_norm"])
            if other is not None and other["doi"] and other["doi"] != r["doi"]:
                collisions.append((r["title"][:150], other["doi"], r["doi"]))
        if kept is not None:
            dup_doi += 1 if (r["doi"] and by_doi.get(r["doi"]) is kept) else 0
            dup_no_doi += 1 if not r["doi"] else 0
            if r["source_primary"] not in kept["sources"]:
                kept["sources"].append(r["source_primary"])
            for f in ("abstract", "container", "publisher", "year", "url", "doi", "citations"):
                if not kept[f] and r[f]:
                    kept[f] = r[f]
            if kept["doi"]:
                by_doi.setdefault(kept["doi"], kept)
            continue
        records.append(r)
        if r["doi"]:
            by_doi[r["doi"]] = r
        by_title.setdefault(r["title_norm"], r)

    json.dump(records, open(os.path.join(a.outdir, "corpus_all.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    with open(os.path.join(a.outdir, "evidence", "dedup_log.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        w.writerow(["raw_records", len(raws)])
        w.writerow(["unique_records", len(records)])
        w.writerow(["duplicates_removed", len(raws) - len(records)])
        w.writerow(["duplicates_by_doi", dup_doi])
        w.writerow(["duplicates_merged_missing_doi", dup_no_doi])
        w.writerow(["title_collision_pairs", len(collisions)])
        for src, n in sorted(seen_meta.items()):
            w.writerow(["raw_from_" + src, n])
    with open(os.path.join(a.outdir, "evidence", "title_collisions.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["title", "doi_a", "doi_b"])
        w.writerows(collisions)

    print("per-source raw: " + ", ".join("%s=%d" % kv for kv in sorted(seen_meta.items())))
    print("raw %d -> unique %d -> duplicates removed %d"
          % (len(raws), len(records), len(raws) - len(records)))
    no_abs = sum(1 for r in records if len(r["abstract"]) < 40)
    print("unique records without a usable abstract: %d (cannot be abstract-screened)" % no_abs)
    print("wrote %s/corpus_all.json" % a.outdir)


if __name__ == "__main__":
    main()
