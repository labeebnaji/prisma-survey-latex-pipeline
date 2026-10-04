"""Numeric provenance audit: every quantity asserted in the manuscript must be computable.

  python number_audit.py --root . --manuscript manuscript --corpus corpus

Writes <corpus>/evidence/corpus_counts.json and exits non-zero if any asserted number has no
computed source. Pass --allowlist protocol/manual_counts.json to admit hand-curated counts; the file
maps the number to a source label, e.g. {"32": {"source": "core subset table, tab:core32"}}. The
allowed number is still reported so a reviewer can check the label against the table.
"""
import argparse
import csv
import glob
import json
import os
import re
import sys
from collections import defaultdict

NOUNS = r"(papers|records|references|sources|queries|dimensions|cases|sub-criteria|criteria|" \
        r"models|instruments|tensions|domains|levels|stages|strategies|duplicates|venues|excluded|retained)"

# Metric names that can legitimately carry each noun. A number that matches a computed value whose
# name has nothing to do with the noun is a coincidence, not a provenance, and is reported as such.
NOUN_METRIC = {
    "papers": ("corpus", "tier", "screened", "included", "auditable", "pass1"),
    "records": ("raw", "corpus", "records", "screen", "pass1", "dedup", "tier"),
    "references": ("venue", "bib", "reference"),
    "sources": ("sources",),
    "queries": ("quer",),
    "dimensions": ("dimension", "tabrows"),
    "cases": ("case", "tabrows"),
    "sub-criteria": ("criter", "tabrows"),
    "criteria": ("criter", "tabrows"),
    "models": ("model", "tabrows"),
    "instruments": ("instrument", "tabrows"),
    "tensions": ("tension", "tabrows"),
    "domains": ("domain", "tabrows"),
    "levels": ("level", "tabrows"),
    "stages": ("stage", "tabrows"),
    "strategies": ("strateg", "tabrows"),
    "duplicates": ("duplic",),
    "venues": ("venue",),
    "excluded": ("exclud", "screen"),
    "retained": ("tier", "included", "retain", "pass"),
}

# A count can be separated from its noun by a short adjective run ("1146 unique papers"), so the gap
# is bounded at three words rather than assumed to be zero.
QTY = re.compile(r"(?<![\w.,{])(\d{1,3}(?:,\d{3})+|\d{1,6})\s+(?:\w+\s+){0,3}?(" + NOUNS + r")\b", re.I)
ROW = re.compile(r"^\s*(?:[A-Za-z0-9@\\\\].*?)&.*?\\\\\s*$", re.M)


def norm_num(raw):
    return int(raw.replace(",", ""))


def json_len(path):
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    return len(d) if isinstance(d, list) else None


def csv_rows(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return max(0, sum(1 for _ in f) - 1)
    except Exception:
        return None


def compute_metrics(root, manuscript, corpus):
    m = {}
    searches = os.path.join(root, "searches")
    if os.path.isdir(searches):
        per_src, total, files = defaultdict(int), 0, 0
        for p in glob.glob(os.path.join(searches, "*.json")):
            if os.path.basename(p) in ("queries.json", "_summary.json"):
                continue
            n = json_len(p)
            if n is None:
                continue
            files += 1
            src = os.path.basename(p).rsplit("_", 1)[0]
            per_src[src] += n
            total += n
        m["search_raw_total"] = total
        m["search_query_files"] = files
        # A source that returned nothing was queried but cannot be claimed as a corpus source.
        m["search_sources_queried"] = len(per_src)
        m["search_sources"] = sum(1 for n in per_src.values() if n > 0)
        zero = sorted(src for src, n in per_src.items() if n == 0)
        if zero:
            m["search_sources_empty"] = len(zero)
            print("sources queried but empty (must be disclosed, not counted): %s" % ", ".join(zero))
        for src, n in per_src.items():
            m["raw_from_" + src] = n
    for name in ("corpus_all", "screened_pass1", "tierA", "tierB", "tierC"):
        p = os.path.join(corpus, name + ".json")
        if os.path.exists(p):
            m[name] = json_len(p)
    ev = os.path.join(corpus, "evidence")
    if os.path.isdir(ev):
        for name in ("venue_resolution", "tiering_decisions"):
            p = os.path.join(ev, name + ".csv")
            if os.path.exists(p):
                m[name + "_rows"] = csv_rows(p)
        dl = os.path.join(ev, "dedup_log.csv")
        if os.path.exists(dl):
            for row in csv.DictReader(open(dl, encoding="utf-8")):
                try:
                    m["dedup_" + row["metric"]] = int(row["value"])
                except Exception:
                    pass
        ss = os.path.join(ev, "screening_summary.csv")
        if os.path.exists(ss):
            for row in csv.DictReader(open(ss, encoding="utf-8")):
                try:
                    m[row["metric"]] = int(row["value"])
                except Exception:
                    pass
    m.update(tex_table_counts(manuscript))
    return {k: v for k, v in m.items() if v is not None}


def tex_table_counts(manuscript):
    """Row counts per labeled LaTeX table, so curated counts have a source too."""
    out = {}
    tex = os.path.join(manuscript, "main.tex")
    if not os.path.exists(tex):
        return out
    text = open(tex, encoding="utf-8", errors="replace").read()
    for extra in glob.glob(os.path.join(manuscript, "*.tex")):
        if extra != tex:
            text += "\n" + open(extra, encoding="utf-8", errors="replace").read()
    for block in re.split(r"\\begin\{(?:table\*?|longtable)\}", text)[1:]:
        label = re.search(r"\\label\{([^}]+)\}", block)
        body = block.split(r"\end{")[0].split(r"\bottomrule")[0]
        rows = sum(len(ROW.findall(chunk)) for chunk in body.split(r"\midrule"))
        if label:
            out["tabrows_" + label.group(1)] = rows
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--manuscript", default="manuscript")
    ap.add_argument("--corpus", default="corpus")
    ap.add_argument("--allowlist", default="protocol/manual_counts.json")
    a = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    manuscript = os.path.join(a.root, a.manuscript)
    corpus = os.path.join(a.root, a.corpus)
    metrics = compute_metrics(a.root, manuscript, corpus)
    allow_path = os.path.join(a.root, a.allowlist)
    if os.path.exists(allow_path):
        for name, entry in json.load(open(allow_path, encoding="utf-8")).items():
            metrics[name] = int(entry["value"] if isinstance(entry, dict) else entry)

    values = defaultdict(list)
    for k, v in metrics.items():
        values[v].append(k)

    claims = defaultdict(list)
    for p in sorted(glob.glob(os.path.join(manuscript, "*.tex"))):
        text = open(p, encoding="utf-8", errors="replace").read()
        text = text.replace("{,}", "").replace("\\,", "")
        for i, line in enumerate(text.splitlines(), 1):
            for m in QTY.finditer(line):
                try:
                    n = norm_num(m.group(1))
                except ValueError:
                    continue
                claims[(n, m.group(2).lower())].append("%s:%d" % (os.path.basename(p), i))

    os.makedirs(os.path.join(corpus, "evidence"), exist_ok=True)
    json.dump(metrics, open(os.path.join(corpus, "evidence", "corpus_counts.json"), "w",
                            encoding="utf-8"), indent=1, sort_keys=True)

    print("=== COMPUTED ===")
    for k, v in sorted(metrics.items()):
        print("  %-28s %s" % (k, v))
    print("\n=== ASSERTED IN MANUSCRIPT (%d distinct) ===" % len(claims))
    unexplained = []
    coincidences = []
    years = []
    for (n, noun), locs in sorted(claims.items()):
        fits = [m for m in values.get(n, [])
                if any(f in m for f in NOUN_METRIC.get(noun, (noun,)))]
        if fits:
            status = "explained:" + ",".join(fits[:2])
        elif 1900 <= n <= 2099:
            status = "year-shaped"
            years.append((n, noun, locs))
        elif values.get(n):
            status = "VALUE-ONLY"
            coincidences.append((n, noun, locs, values[n]))
        else:
            status = "UNEXPLAINED"
            unexplained.append((n, noun, locs))
        print("  %-6s %-14s %-34s %s" % (n, noun, status[:34], ", ".join(locs[:3])))
    print("\nwrote %s" % os.path.join(corpus, "evidence", "corpus_counts.json"))

    if years:
        print("\n%d claims look like calendar years, not corpus counts (read them, then reword the "
              "sentence if the noun really is a count):" % len(years))
        for n, noun, locs in years:
            print("  %s %s  (%s)" % (n, noun, ", ".join(locs[:3])))

    if coincidences:
        print("\n%d claims equal some computed value by number alone, but the metric name does not fit "
              "the noun -- read the sentence and confirm the pairing is real:" % len(coincidences))
        for n, noun, locs, names in coincidences:
            print("  %s %s  (%s)  matches only: %s" % (n, noun, ", ".join(locs[:3]), ", ".join(names[:3])))
    if unexplained:
        print("\n%d asserted numbers have no computed source:" % len(unexplained))
        for n, noun, locs in unexplained:
            print("  %s %s  (%s)" % (n, noun, ", ".join(locs[:3])))
        print("Either recompute from the corpus, add a LaTeX table row count, or record the number in "
              "protocol/manual_counts.json with a justification.")
        return 1
    print("All asserted numbers trace to a computed source.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
