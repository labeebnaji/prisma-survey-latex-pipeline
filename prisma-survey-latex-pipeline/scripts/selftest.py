"""Offline conformance test for the pipeline scripts: no network, no LaTeX, no domain data.

  python selftest.py

Builds a throwaway project whose true counts are known in advance, runs dedupe, screening, the numeric
audit and the figure generator against it, and checks both directions of every gate: a clean project
must exit 0 and an audited defect must exit 1. Prints PASS or FAIL per check.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print("%-4s %s%s" % ("PASS" if ok else "FAIL", name, ("  <- " + detail) if detail else ""))


def run(script, *args, expect=None):
    p = subprocess.run([sys.executable, os.path.join(HERE, script)] + list(args),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if expect is not None and p.returncode != expect:
        check("%s exit %d" % (script, expect), False,
              "got %d: %s" % (p.returncode, (p.stdout + p.stderr)[-300:]))
    return p


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(text)


def hit(title, doi, abstract="", year="2024"):
    return {"title": title, "doi": doi, "abstract": abstract, "published_date": year,
            "extra": "{'container_title': 'Journal of Tests', 'crossref_type': 'article'}"}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = tempfile.mkdtemp(prefix="prisma-selftest-")
    try:
        build(root)
        verify(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    bad = [n for n, ok, _ in RESULTS if not ok]
    print("\n%d checks, %d failed" % (len(RESULTS), len(bad)))
    return 1 if bad else 0


def build(root):
    good_a = hit("Alpha Study of Widget Scaling", "10.1000/a.1",
                 "We evaluate widget scaling across three clusters and report throughput gains.")
    good_b = hit("Beta Survey of Widget Scaling", "10.1000/b.2",
                 "A survey that organises widget scaling literature into four families.")
    # Same work as good_a under a different DOI, plus one record with no DOI at all.
    dup = hit("Alpha Study of Widget Scaling!", "10.1000/a.1-v2",
              "We evaluate widget scaling across three clusters and report throughput gains.")
    nodoi = hit("Gamma Notes on Scaling Widgets", "",
                "Short note on scaling widgets in a single cluster.")
    off = hit("Widget Scaling in Culinary Arts", "10.1000/c.3", "Pasta, not software.")
    write(os.path.join(root, "searches", "crossref_S1.json"),
          json.dumps([good_a, good_b, dup, off]))
    write(os.path.join(root, "searches", "arxiv_S2.json"), json.dumps([good_b, nodoi]))
    write(os.path.join(root, "searches", "queries.json"),
          json.dumps([{"id": "S1", "tool": "search_crossref", "query": "widget scaling"}]))
    write(os.path.join(root, "protocol", "screening.json"), json.dumps({
        "pass1": {"any": ["widget"]},
        "tierA": {"any": ["survey", "study"], "and": [["scaling"]]},
        "tierB": {"any": ["widget"]},
        "tierC": {"any": ["note"]},
        "exclude": {"any": ["culinary"]},
    }, indent=1))


def tex(manuscript, claims):
    lines = ["\\documentclass{IEEEtran}", "\\begin{document}"] + claims + ["\\end{document}"]
    write(os.path.join(manuscript, "main.tex"), "\n".join(lines) + "\n")


def verify(root):
    ms = os.path.join(root, "manuscript")
    corpus = os.path.join(root, "corpus")

    p = run("dedupe.py", "--indir", os.path.join(root, "searches"), "--outdir", corpus, expect=0)
    records = json.load(open(os.path.join(corpus, "corpus_all.json"), encoding="utf-8"))
    check("queries.json never counted as a record", len(records) == 5, "unique=%d" % len(records))
    check("same DOI from a second source collapses",
          sum(1 for r in records if r["doi"] == "10.1000/b.2") == 1)
    check("merge records every contributing source",
          len(next(r for r in records if r["doi"] == "10.1000/b.2")["sources"]) == 2)
    lines = open(os.path.join(corpus, "evidence", "title_collisions.csv"),
                 encoding="utf-8").read().splitlines()
    check("same title under a different DOI is reported, not silently merged",
          len(lines) == 2 and "Alpha Study" in lines[1], lines[1] if len(lines) > 1 else "no pair")
    nodoi = [r for r in records if not r["doi"]]
    check("a record without a DOI still enters the corpus", len(nodoi) == 1)
    check("dedup evidence log written",
          os.path.exists(os.path.join(corpus, "evidence", "dedup_log.csv")))

    p = run("screen_tiers.py", "--corpus", os.path.join(corpus, "corpus_all.json"),
            "--rules", os.path.join(root, "protocol", "screening.json"), "--outdir", corpus,
            expect=0)
    summary = dict(l.rstrip().split(",") for l in
                   open(os.path.join(corpus, "evidence", "screening_summary.csv"),
                        encoding="utf-8").read().splitlines()[1:])
    check("exclude rule removed the off-topic record", summary.get("screen_excluded") == "1")
    check("funnel closes: pass1 = tiers + excluded + screened_out",
          int(summary["screen_pass1"]) == int(summary["screen_tierA"]) + int(summary["screen_tierB"])
          + int(summary["screen_tierC"]) + int(summary["screen_excluded"])
          + int(summary["screen_screened_out"]))

    run("number_audit.py", "--root", root, expect=0)  # no manuscript yet, so nothing to explain

    # A claim that matches the corpus must pass; a claim one record too large must fail.
    good = ["The corpus holds %d papers." % len(records),
            "We queried %d sources." % 2]
    tex(ms, good)
    p = run("number_audit.py", "--root", root, expect=0)
    check("clean claim accepted", "All asserted numbers trace" in p.stdout)

    tex(ms, good + ["An inflated corpus of 99 papers was analysed."])
    p = run("number_audit.py", "--root", root, expect=1)
    check("inflated count rejected", "UNEXPLAINED" in p.stdout and "99" in p.stdout)

    tex(ms, good + ["The matrix spans 6 dimensions."])
    p = run("number_audit.py", "--root", root, expect=0)
    check("coincidental value flagged as VALUE-ONLY, not silently passed",
          "VALUE-ONLY" in p.stdout)

    tex(ms, ["Work from 2024 onward was retained, covering %d papers." % len(records)])
    p = run("number_audit.py", "--root", root, expect=0)
    check("calendar year separated from counts", "year-shaped" in p.stdout)

    run("number_audit.py", "--root", root, expect=0)
    spec = os.path.join(root, "figures_src", "figures.json")
    write(spec, json.dumps({
        "prisma": {"boxes": [{"title": "Identification",
                              "lines": ["n = {dedup_raw_records}", "unique {screen_unique_in}"],
                              "side": ["Duplicates", "n = {dedup_duplicates_removed}"]},
                             {"title": "Screening", "lines": ["pass1 {screen_pass1}"]},
                             {"title": "Included", "lines": ["tierA {screen_tierA}"]}]},
        "bar": {"categories": ["A", "B", "C"], "values": ["{screen_tierA}", "{screen_tierB}",
                                                          "{screen_tierC}"]},
        "hexagon": {"center": "Framework", "domains": ["D1", "D2", "D3"]}}))
    outdir = os.path.join(root, "figures")
    p = run("make_figures.py", "--counts", os.path.join(corpus, "evidence", "corpus_counts.json"),
            "--spec", spec, "--outdir", outdir, expect=0)
    pdfs = [f for f in os.listdir(outdir) if f.endswith(".pdf")] if os.path.isdir(outdir) else []
    check("three figures drawn from audited counts", len(pdfs) == 3, ",".join(pdfs))

    write(spec + ".2", json.dumps({"bar": {"categories": ["A"], "values": ["{not_a_metric}"]}}))
    p = run("make_figures.py", "--counts", os.path.join(corpus, "evidence", "corpus_counts.json"),
            "--spec", spec + ".2", "--outdir", outdir, expect=1)
    check("unknown placeholder stops the drawing", "not_a_metric" in (p.stdout + p.stderr))


if __name__ == "__main__":
    sys.exit(main())
