"""Two-pass screening and tiering driven by an external rules file.

  python screen_tiers.py --corpus corpus/corpus_all.json \
                         --rules protocol/screening.json --outdir corpus

Rules file format (see examples/screening.json for a complete, runnable instance):
{
  "pass1":   {"any": ["zero trust"]},
  "tierA":   {"any": ["maturity model"], "and": [["cloud", "kubernetes"]]},
  "tierB":   {"any": ["zero trust"]},
  "tierC":   {"any": ["microsegmentation"]},
  "exclude": {"any": ["blockchain-based supply chain finance"]}
}
"any" means at least one term must appear in the text. "and" means every element must hold, where a
bare string must appear literally and a nested list is one group satisfied by any of its terms. The
domain vocabulary is yours; no term in this script encodes any topic.
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import Counter


def hits(text, terms):
    return [t for t in terms if t.lower() in text]


def matches(text, rule):
    if not rule:
        return False, []
    matched = hits(text, rule.get("any", []))
    if rule.get("any") and not matched:
        return False, []
    for term in rule.get("and", []):
        if isinstance(term, list):
            # A nested list is one required group: at least one of its terms must appear.
            group = hits(text, term)
            if not group:
                return False, []
            matched += group
        elif term.lower() not in text:
            return False, []
    return True, matched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--rules", required=True)
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(os.path.join(a.outdir, "evidence"), exist_ok=True)
    records = json.load(open(a.corpus, encoding="utf-8"))
    rules = json.load(open(a.rules, encoding="utf-8"))

    pass1, no_abs = [], []
    for r in records:
        ok, _ = matches(r["title"].lower(), rules.get("pass1"))
        if not ok:
            continue
        pass1.append(r)
        if len(r.get("abstract", "")) < 40:
            no_abs.append(r)

    tiers, decisions = {"A": [], "B": [], "C": []}, []
    for r in pass1:
        text = (r["title"] + " " + r.get("abstract", "")).lower()
        is_excluded, ex_terms = matches(text, rules.get("exclude"))
        if is_excluded:
            decisions.append([r.get("doi", ""), r["title"][:120], "EXCLUDED", ";".join(ex_terms)])
            continue
        assigned = None
        for tier in ("A", "B", "C"):
            ok, m = matches(text, rules.get("tier" + tier))
            if ok:
                tiers[tier].append(r)
                assigned = tier
                decisions.append([r.get("doi", ""), r["title"][:120], "tier" + tier, ";".join(m)])
                break
        if not assigned:
            decisions.append([r.get("doi", ""), r["title"][:120], "screened_out", ""])

    for tier, rows in tiers.items():
        json.dump(rows, open(os.path.join(a.outdir, "tier%s.json" % tier), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    json.dump(pass1, open(os.path.join(a.outdir, "screened_pass1.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    with open(os.path.join(a.outdir, "evidence", "tiering_decisions.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["doi", "title", "decision", "matched_terms"])
        w.writerows(decisions)

    # The funnel has to be readable by the numeric audit and the figure generator; a number that
    # only exists on stdout gets retyped by hand and drifts.
    summary = {
        "unique_in": len(records),
        "pass1": len(pass1),
        "tierA": len(tiers["A"]),
        "tierB": len(tiers["B"]),
        "tierC": len(tiers["C"]),
        "excluded": sum(1 for d in decisions if d[2] == "EXCLUDED"),
        "screened_out": sum(1 for d in decisions if d[2] == "screened_out"),
        "no_abstract": len(no_abs),
    }
    summary["pass1_excluded"] = summary["pass1"] - summary["tierA"] - summary["tierB"] - summary["tierC"]
    summary["included"] = summary["tierA"] + summary["tierB"] + summary["tierC"]
    with open(os.path.join(a.outdir, "evidence", "screening_summary.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for k, v in summary.items():
            w.writerow(["screen_" + k, v])
    if summary["pass1_excluded"] != summary["excluded"] + summary["screened_out"]:
        print("WARNING  funnel does not close: pass1 - tiers = %d but excluded + screened_out = %d"
              % (summary["pass1_excluded"], summary["excluded"] + summary["screened_out"]))
        return 1

    print("unique %d -> title pass1 %d -> tierA %d / tierB %d / tierC %d / screened_out %d"
          % (len(records), len(pass1), len(tiers["A"]), len(tiers["B"]), len(tiers["C"]),
             sum(1 for d in decisions if d[2] == "screened_out")))
    print("excluded by exclude-rule: %d" % sum(1 for d in decisions if d[2] == "EXCLUDED"))
    print("pass-1 records with no usable abstract: %d  (declare as a limitation)" % len(no_abs))
    for tier in ("A", "B", "C"):
        print("  tier%s years: %s" % (tier, dict(sorted(Counter(r["year"] for r in tiers[tier]).items()))))
    print("Freeze these rules before writing any count into the manuscript.")


if __name__ == "__main__":
    sys.exit(main())
