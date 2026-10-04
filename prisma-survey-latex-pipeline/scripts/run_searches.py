"""Run a query file against the bibliographic MCP and persist one JSON file per query.

  python run_searches.py --config searches/queries.json --outdir searches

queries.json is a list of:
  {"id": "S1", "tool": "search_crossref", "query": "...", "max_results": 200}

Existing output files are skipped, so an interrupted run resumes for free.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_client import McpClient, decode_stream  # noqa: E402


def source_of(tool):
    return tool.replace("search_", "") or tool


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between calls")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(a.outdir, exist_ok=True)
    queries = json.load(open(a.config, encoding="utf-8"))

    c = McpClient()
    counts, total = {}, 0
    for q in queries:
        out = os.path.join(a.outdir, "%s_%s.json" % (source_of(q["tool"]), q["id"]))
        if os.path.exists(out) and not a.force:
            n = len(json.load(open(out, encoding="utf-8")))
        else:
            args = {k: v for k, v in q.items() if k not in ("id", "tool")}
            text = c.call(q["tool"], args, q.get("timeout", 180)) or ""
            if text.startswith("MCP_ERROR"):
                print("ERROR  %s/%s: %s" % (source_of(q["tool"]), q["id"], text[:300]))
                continue
            recs = decode_stream(text)
            json.dump(recs, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            n = len(recs)
            time.sleep(a.pause)
        counts.setdefault(source_of(q["tool"]), [0, 0])
        counts[source_of(q["tool"])][0] += 1
        counts[source_of(q["tool"])][1] += n
        total += n
        print("%-12s %-4s %5d records" % (source_of(q["tool"]), q["id"], n), flush=True)
    c.close()

    print("\n%-12s %6s %8s" % ("source", "queries", "records"))
    for src, (nq, nr) in sorted(counts.items()):
        flag = "   <-- returned nothing" if nr == 0 else ""
        print("%-12s %6d %8d%s" % (src, nq, nr, flag))
    print("TOTAL raw records: %d across %d sources" % (total, len(counts)))
    print("Sources returning zero must be disclosed in the methodology, not dropped.")


if __name__ == "__main__":
    main()
