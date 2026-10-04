"""Generate survey figures from the audited counts file - never from typed literals.

  python make_figures.py --counts corpus/evidence/corpus_counts.json \
                         --spec figures_src/figures.json --outdir figures

figures.json:
{
  "prisma": {
    "out": "prisma_flow.pdf",
    "boxes": [
      {"title": "Identification", "lines": ["Records identified from {search_sources} sources",
                                             "(n = {search_raw_total})"],
       "side": ["Records excluded", "(n = {screen_pass1_excluded})"]}
    ]
  },
  "bar": {"out": "levels_bar.pdf", "title": "Screening outcome by tier",
           "categories": ["Tier A", "Tier B"], "values": ["{screen_tierA}", "{screen_tierB}"],
           "ylabel": "studies"},
  "hexagon": {"out": "framework_hexagon.pdf", "center": "Reference framework",
               "domains": ["D1 Subject and credential", "D2 Policy and enforcement"]}
}
"""
import argparse
import json
import math
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

PLACEHOLDER = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def fmt(value):
    return "{:,}".format(value) if isinstance(value, int) and value >= 1000 else str(value)


def resolve(text, counts):
    return PLACEHOLDER.sub(lambda m: fmt(counts.get(m.group(1), "??%s??" % m.group(1))), str(text))


def prisma(spec, counts, outdir):
    boxes = spec["boxes"]
    W, H = 7.5, 2.0 + 2.1 * len(boxes)
    fig, ax = plt.subplots(figsize=(W, H))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 14)
    ax.axis("off")
    n = len(boxes)
    ys = [12.6 - i * (11.2 / max(1, n - 1)) for i in range(n)] if n > 1 else [7.0]

    def box(x, y, w, h, lines, fc="#f5f5f5"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.05,rounding_size=0.12",
                                    linewidth=1.0, edgecolor="black", facecolor=fc))
        ax.text(x + w / 2.0, y + h / 2.0, "\n".join(lines), ha="center", va="center", fontsize=7.6)

    def arrow(x1, y1, x2, y2):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=11,
                                     linewidth=1.0, color="black"))

    for i, b in enumerate(boxes):
        y = ys[i]
        title = resolve(b.get("title", ""), counts)
        lines = ([title] if title else []) + [resolve(l, counts) for l in b.get("lines", [])]
        box(0.3, y - 0.9, 6.6, 1.5, lines)
        if b.get("side"):
            box(7.3, y - 0.9, 2.4, 1.5, [resolve(s, counts) for s in b["side"]], fc="#ffffff")
            arrow(6.9, y - 0.15, 7.3, y - 0.15)
        if i + 1 < n:
            arrow(3.6, y - 0.9, 3.6, ys[i + 1] + 0.6)
    fig.tight_layout()
    path = os.path.join(outdir, spec.get("out", "prisma_flow.pdf"))
    fig.savefig(path)
    plt.close(fig)
    return path


def bar(spec, counts, outdir):
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    cats = [resolve(c, counts) for c in spec["categories"]]
    vals = [float(resolve(v, counts).replace(",", "")) for v in spec["values"]]
    ax.bar(range(len(cats)), vals, color="#5b2a86", width=0.62)
    ax.set_xticks(range(len(cats)))
    ax.set_xticklabels(cats, fontsize=8)
    for i, v in enumerate(vals):
        ax.text(i, v, " %g" % v, va="bottom", ha="center", fontsize=8)
    ax.set_ylabel(spec.get("ylabel", ""))
    ax.set_title(spec.get("title", ""))
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.tight_layout()
    path = os.path.join(outdir, spec.get("out", "levels_bar.pdf"))
    fig.savefig(path)
    plt.close(fig)
    return path


def hexagon(spec, counts, outdir):
    fig, ax = plt.subplots(figsize=(6.0, 5.2))
    ax.set_xlim(-1.6, 1.6)
    ax.set_ylim(-1.45, 1.45)
    ax.axis("off")
    doms = [resolve(d, counts) for d in spec["domains"]]
    center = resolve(spec.get("center", ""), counts)
    ax.add_patch(FancyBboxPatch((-0.62, -0.22), 1.24, 0.44,
                                boxstyle="round,pad=0.03,rounding_size=0.08",
                                edgecolor="black", facecolor="#efe6f7", linewidth=1.1))
    ax.text(0, 0, center, ha="center", va="center", fontsize=8.5)
    pts = []
    for i, d in enumerate(doms):
        ang = math.pi / 2 - 2 * math.pi * i / len(doms)
        x, y = math.cos(ang), math.sin(ang) * 0.9
        pts.append((x, y))
        ax.add_patch(FancyBboxPatch((x - 0.52, y - 0.19), 1.04, 0.38,
                                    boxstyle="round,pad=0.02,rounding_size=0.07",
                                    edgecolor="black", facecolor="#f7f7f7", linewidth=0.9))
        ax.text(x, y, d, ha="center", va="center", fontsize=7.0)
        ax.plot([0, x], [0, y], color="#5b2a86", linewidth=0.9, zorder=0)
    for i in range(len(pts)):
        ax.plot([pts[i][0], pts[(i + 1) % len(pts)][0]],
                [pts[i][1], pts[(i + 1) % len(pts)][1]], color="black", linewidth=0.5)
    fig.tight_layout()
    path = os.path.join(outdir, spec.get("out", "framework_hexagon.pdf"))
    fig.savefig(path)
    plt.close(fig)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--counts", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    counts = json.load(open(a.counts, encoding="utf-8"))
    spec = json.load(open(a.spec, encoding="utf-8"))
    wanted = set(PLACEHOLDER.findall(json.dumps(spec)))
    unknown = sorted(k for k in wanted if k not in counts)
    if unknown:
        sys.exit("spec placeholders not present in %s: %s\n"
                 "Run number_audit.py first, or fix the metric name."
                 % (a.counts, ", ".join(unknown)))
    os.makedirs(a.outdir, exist_ok=True)
    made = []
    if "prisma" in spec:
        made.append(prisma(spec["prisma"], counts, a.outdir))
    if "bar" in spec:
        made.append(bar(spec["bar"], counts, a.outdir))
    if "hexagon" in spec:
        made.append(hexagon(spec["hexagon"], counts, a.outdir))
    for p in made:
        print("wrote %s" % p)
    print("Numbers came from %s; if the corpus changed, rerun number_audit then regenerate." % a.counts)


if __name__ == "__main__":
    main()
