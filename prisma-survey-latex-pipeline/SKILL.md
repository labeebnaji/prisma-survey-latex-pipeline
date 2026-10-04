---
name: prisma-survey-latex-pipeline
description: Executable pipeline that turns a systematic-review topic into a built IEEE-format LaTeX survey. Runs boolean search strings over bibliographic sources through paper-search-mcp, deduplicates under explicit UTF-8, screens title/abstract into tier A/B/C with an external rules file, resolves every DOI against Crossref to catch wrong author or venue bib entries, audits every quantity asserted in the manuscript against real corpus file counts, generates PRISMA 2020 figures from those audited counts, reconciles cite keys against references.bib, and builds with pdflatex/bibtex plus a log scan. Ships runnable example query, screening and figure specs for a different topic. Use when producing or repairing a PRISMA-style LaTeX survey, when methodology numbers must be provably derived from the corpus, or when search/screening/build steps keep failing. Not for short narrative reviews, non-LaTeX deliverables, or prose drafting (use academic-paper or literature-review for those).
---

# PRISMA Survey → LaTeX Pipeline

## Overview

Ten deterministic steps from a review topic to a compiled PDF. Every number that appears in the
manuscript must be produced by a script, never recalled. The scripts in `scripts/` are the pipeline;
the prose is yours. The domain vocabulary lives in config files, never in code.

## Scope boundary

- This skill owns: search execution, corpus bookkeeping, citation verification, numeric provenance,
  figures, LaTeX build.
- This skill does not own: argumentation structure, writing quality, reviewer personas. Hand those to
  `academic-paper` or `literature-review` after step 5 and before step 8. `deep-research` and
  `academic-pipeline` own research planning and the review-revise loop; this skill is the executable
  bookkeeping layer they can call, and it never rewrites a protocol decision they made.

## Prerequisites

Check all of these before step 1. A missing one causes a late, confusing failure.

1. Bibliographic MCP CLI exists. `scripts/mcp_client.py` finds it by globbing
   `%APPDATA%\Python\*\Scripts\paper-search-mcp.exe` (`%APPDATA%` already contains `Roaming`), then
   checks PATH. Force a specific binary with `PAPER_SEARCH_MCP`. This skill assumes the CLI is already
   installed; it does not install it.
2. `pdflatex`, `bibtex`, `pdfinfo` available. `preflight.py` and `build.py` check PATH, then the usual
   MiKTeX and TeX Live install directories.
3. Python 3 with `matplotlib`.
4. **At least 500 MB free on the drive holding the manuscript**; `build.py` refuses below that and
   `preflight.py` warns under 2 GB. A full drive aborts pdflatex mid-run and leaves corrupted aux files.
5. Network reachable. Note that some hosts block WebFetch on PDF URLs; step 7 works around that.

Run `python scripts/preflight.py` to verify 1-4 in one pass.

## Project layout

Create this layout in the working directory and keep it stable; scripts assume it.

```
survey/                # topic shortname
  protocol/            # PRISMA_protocol.md, search_strings.md, screening.json, manual_counts.json
  searches/            # <source>_<id>.json, one file per executed query, plus queries.json
  corpus/              # corpus_all.json, screened_pass1.json, tierA|B|C.json
    evidence/          # dedup_log.csv, tiering_decisions.csv, screening_summary.csv,
                       # venue_resolution.csv, corpus_counts.json
  manuscript/          # main.tex, sections.tex, appendix.tex, references.bib
  figures/             # prisma_flow.pdf, tier_bar.pdf
  figures_src/         # the generating spec, committed for reproducibility
  review/round1/       # audit findings, one file per review line
  tmp/                 # scratch; safe to delete
```

The `--corpus` and `--outdir` arguments must point at the same directory in steps 3-5, otherwise the
audit cannot see the evidence files the screening wrote.

## Step 0 - Enumerate real tool names

Do not assume the MCP tool names or argument spelling. List them first:

```
python scripts/mcp_client.py --list-tools
```

`max_results` is the limit parameter for every `search_*` tool; passing `limit` fails. Confirm
`get_<source>_paper_by_doi` and `read_<source>_paper` variants exist before relying on them.

## Step 1 - Protocol and search strings

Write `protocol/PRISMA_protocol.md` before any search: RQs, inclusion/exclusion rules, information
sources with the query date, screening passes, extraction schema, quality appraisal tool. Write
`protocol/search_strings.md` with 5-8 boolean strings (S1..Sn) covering the distinct facets of the
topic, then a per-source adaptation of each (syntax differs).

Register the protocol if the target venue asks for it; state "pending" honestly rather than claiming a
registration that does not exist.

## Step 2 - Execute the searches

Author a query file, then run it. `examples/queries.json` is a complete twelve-query, nine-source
instance for a different topic; copy its shape and replace the strings.

```
# searches/queries.json
[{"id": "S1", "tool": "search_crossref",
  "query": "hallucination detection clinical text large language model", "max_results": 150}]

python scripts/run_searches.py --config searches/queries.json --outdir searches
```

`run_searches.py` writes one JSON file per query and prints a per-source record table. **Keep sources
that return zero in the table** - a silent empty source is the difference between "8 sources queried"
and an honest methodology section. In practice preprint and aggregator sources often return 0 while
Crossref/PMC/OpenAlex dominate; that is a finding to report, not a bug to hide.

Re-run cost is real: rate limits and 429s happen. The script skips files that already exist, so resume
is safe. Keep `queries.json` inside `searches/`; `dedupe.py` and `number_audit.py` recognise and ignore
it so query definitions are never counted as records.

## Step 3 - Deduplicate

```
python scripts/dedupe.py --indir searches --outdir corpus
```

Key on DOI, then on title only for records that carry no DOI. Writes `corpus/corpus_all.json`,
`corpus/evidence/dedup_log.csv` and `corpus/evidence/title_collisions.csv`, and prints
`raw -> unique -> dropped`. Identical titles under two different DOIs are **not** auto-merged: distinct
works do collide on title (the session found 68 such pairs, preprint-plus-journal and genuinely
different papers mixed together), so each pair is listed for one human decision and the count is kept as
`dedup_title_collision_pairs` for the methodology to state.

Always open files with `encoding='utf-8'`; Windows defaults to cp1256 or cp1252 and silently mojibakes
titles containing an en dash, a trademark sign, or Cyrillic/Arabic. When printing such titles to the
console, reconfigure stdout to UTF-8.

Adjudicate `title_collisions.csv` before step 4: a merged or split pair changes every downstream count.
Records arriving without a DOI are common (arXiv, CORE, aggregators); they dedup on title alone, so a
renamed preprint survives as a second record. Report that limit rather than claiming a DOI-level dedup
you did not perform.

## Step 4 - Two-pass screening and tiering

Pass 1 title, pass 2 abstract, then tier by your own rules. Rules live in a config file so they are
auditable and not invented inside the code. `examples/screening.json` is a complete instance.

```
# protocol/screening.json
{"pass1":   {"any": ["zero trust"]},
 "tierA":   {"any": ["maturity model"], "and": [["cloud", "kubernetes"]]},
 "tierB":   {"any": ["zero trust"]},
 "tierC":   {"any": ["microsegmentation"]},
 "exclude": {"any": ["blockchain-based supply chain finance"]}}

python scripts/screen_tiers.py --corpus corpus/corpus_all.json --rules protocol/screening.json --outdir corpus
```

`any` needs one term; every element of `and` must hold, where a nested list is one group satisfied by
any of its terms. A bare string list under `and` requires all of them, which usually selects nothing.

The step also writes `corpus/evidence/screening_summary.csv` (`screen_pass1`, `screen_tierA`,
`screen_pass1_excluded`, `screen_included`, `screen_no_abstract`) and exits 1 when the funnel does
not close, so the PRISMA diagram is never redrawn from numbers read off the console. Records lacking an
abstract cannot be screened on abstract; report them as a limitation. `tiering_decisions.csv` keeps the
matched terms per record so a reviewer can replay any decision.

Do **not** tune keyword rules until the tier counts match a number you already wrote down. That is how a
corpus quietly gains 65 duplicate records. Fix the rules, then recompute the manuscript numbers in
step 5.

## Step 5 - Numeric audit (mandatory, blocking)

```
python scripts/number_audit.py --root . --manuscript manuscript --corpus corpus
```

It extracts every asserted quantity from the `.tex` files (`N papers`, `N records`, `N dimensions`,
`N cases`, and the same noun up to three words later, as in "1146 unique papers") with file:line,
prints the real counts computed from each JSON/CSV in the project, and writes
`corpus/evidence/corpus_counts.json`. Exit code is non-zero when an asserted number has no computed
counterpart.

Statuses the script prints, and what each one means:

- `explained:<metric>` - the number equals a computed metric whose name fits the noun.
- `VALUE-ONLY` - the number equals some metric but the metric name does not fit the noun, so the match
  may be coincidence. Read the sentence.
- `year-shaped` - a 1900-2099 number that reads as a date. Listed separately and not blocking; reword
  the sentence if the noun really is a count.
- `UNEXPLAINED` - blocking.

Rules:

- No number enters the manuscript before this step passes.
- Counts of things you curated by hand (dimensions in a matrix, sub-criteria in a rubric, cases
  validated) come from table row counts, not memory. The audit emits each labelled table's body-row
  count as `tabrows_<label>`, so "42 dimensions" is checked against `tabrows_tab:fullmatrix`.
- A number with no table to count is declared in `protocol/manual_counts.json` as
  `{"included_total": {"value": 34, "source": "core set, tab:core34"}}`. The name then becomes a metric
  the figures can reference, and the claim still prints, so a reviewer sees the label.
- `search_sources` counts only sources that returned records; `search_sources_queried` and
  `search_sources_empty` carry the rest. Prose that says "N sources" must say which sense it means.
- When the corpus changes at any later step, re-run this before the next build.
- Every derived figure reads `corpus_counts.json` (step 10) so prose and figure cannot disagree.

## Step 6 - Novelty check against competitors

Competitor surveys are the usual reason a contribution claim collapses. For each claimed contribution,
find the nearest 10-15 competing papers and fetch their abstracts (Crossref abstracts are often present
even when the venue page is paywalled):

```
python scripts/mcp_client.py '{"tool":"get_crossref_paper_by_doi","args":{"doi":"10.1007/s10922-021-00956-4"}}'
```

Score overlap per competitor and classify FATAL / SERIOUS / MANAGEABLE, writing
`review/round1/R02_novelty.md`. A FATAL finding means rewriting the contribution list in step 8, not
adding a citation.

Strip JATS/XML tags from abstracts before reading, and treat "no abstract in Crossref" as a signal to
try OpenAlex or the venue HTML page, not as evidence the paper is irrelevant.

## Step 7 - Grey literature anchoring

Standards and vendor models (government, standards bodies, vendors) are usually not indexed well by
Crossref or OpenAlex. Anchor them by direct retrieval of the canonical document channel.

- Use `WebSearch` for the HTML landing page, then read the page. Keep queries under 100 characters or
  the tool rejects them.
- Do **not** use `WebFetch` on PDF URLs: it fails on binary payloads, returns 403 for many vendor and
  IEEE endpoints, and rate-limits with queue errors. If a PDF must be read, download it and read the
  local file.
- Record each grey item as: official URL, version, publication date, retrieval date, and the exact
  section carrying the claim. Write to `protocol/grey_standards_canonical.md`.
- State in the methodology that grey sources were anchored by direct citation rather than keyword
  discovery, otherwise the PRISMA flow diagram misrepresents the corpus.

## Step 8 - LaTeX scaffold

Split the manuscript; do not paste everything into `main.tex`:

```
manuscript/main.tex      preamble + abstract + intro + related + methodology + \input{sections} +
                         \input{appendix} + bibliographystyle + bibliography + \end{document}
manuscript/sections.tex  results, taxonomy, framework, validation, discussion, limitations
manuscript/appendix.tex  full matrices, per-domain rubrics, query strings
manuscript/references.bib
```

Preamble gotchas that cost real build cycles (see `references/ieee-cst-latex.md`):

- Symbols such as `\textoc` are **not** defined by IEEEtran or `textcomp`. Declare
  `\newcommand{\textoc}{\ensuremath{\circ}}` before first use, or use `\textbullet`, `--`, and `n/a`
  only.
- `\usepackage{cite}` before `hyperref`; `longtable`, `booktabs`, `array` for wide matrices;
  `p{0.34\textwidth}` columns instead of `\small` hacks.
- `IEEEpubid` and `\IEEEminalystext` are version-sensitive; if a template macro errors, comment it and
  note the deviation rather than fighting it.
- In Python regexes over LaTeX text, `\caption` and `\cite` are invalid escapes in non-raw strings - use
  raw strings or `re.escape`.

Every reference entry must be verified against step 9 output before it is cited: wrong author lists and
wrong venues survive proofreading because they look plausible.

## Step 9 - Citation integrity

Two scripts, both blocking:

```
python scripts/verify_venues.py --corpus corpus/tierA.json --bib manuscript/references.bib
python scripts/reconcile_cites.py --manuscript manuscript
```

`verify_venues.py` resolves each corpus DOI through Crossref into an append-only evidence CSV, then
audits `references.bib` against it. Flags: `TITLE_DRIFT`, `VENUE_MISMATCH`, `AUTHOR_MISMATCH`,
`MOJIBAKE`, `NOT_INDEXED`, `UNRESOLVED`. Exit code 1 if the bib is not clean.

Two facts about the resolver shape the whole step:

- The venue is **not** a top-level field. It sits in `extra` as `container_title`, alongside `publisher`
  and `crossref_type`, and `extra` is a Python repr string. Reading a nonexistent `container` key yields
  an empty column and a venue audit that silently passes everything.
- An empty answer means "no reply", not "not indexed". Such DOIs are logged `status=error` and retried on
  the next run; only an explicit empty record is cached as `not_found`. `--limit N` caps new lookups per
  run (rate limits are real) and `--no-network` replays the cached CSV.

Coverage depends on the bib itself: an entry is auditable only if a `doi`, `url`, `note` or `ee` field
contains a `10.xxxx/...` string. The script prints `bib entries audited against evidence: N of M` - if N
is far below M, add DOI fields rather than trusting the pass. A bib DOI the corpus never carried is
reported as `UNRESOLVED` and fails, because unverified is not the same as clean. Entries whose resolved
record has no container (preprints, datasets) are counted as venue-blind and listed, never passed off as
verified. Author checks need an `authors` column; the script warns when the evidence CSV predates it and
tells you to re-resolve instead of skipping quietly.

`reconcile_cites.py` prints `MISSING in bib` and `UNUSED in bib` for every cite key. Fix both lists to
empty before building.

## Step 10 - Figures and build

Figures must be generated, never hand-edited, and must read the audited counts.
`examples/figures.json` is a complete three-figure spec using only metrics these scripts emit.

```
python scripts/make_figures.py --counts corpus/evidence/corpus_counts.json --spec figures_src/figures.json --outdir figures
python scripts/build.py --manuscript manuscript --main main.tex
```

`make_figures.py` draws the PRISMA 2020 flow (identification, deduplication, screening, eligibility,
included), a category bar chart, and a domain ring from the spec file, all as vector PDFs. Every
`{metric}` placeholder must exist in the counts file; the script lists unknown names and exits instead of
drawing a figure containing a literal `{tierX}`. `build.py` runs pdflatex, bibtex, pdflatex, pdflatex
with `-halt-on-error`, then scans the `.log` for undefined citation, undefined reference, undefined
control sequence, and LaTeX error lines, and reports the `pdfinfo` page count. Non-zero exit means the
PDF is not deliverable.

Keep the spec in `figures_src/` and the output in `figures/`; regenerate rather than patching.

## Verification

The pipeline is done only when all hold:

1. `number_audit.py` exits 0, no claim is left `VALUE-ONLY` unread, and its `corpus_counts.json` is the
   source of the figure numbers.
2. `reconcile_cites.py` prints empty MISSING and UNUSED lists.
3. `verify_venues.py` reports no `UNRESOLVED` and no `NOT_INDEXED` among cited entries, or each is
   declared grey in the methodology.
4. `build.py` exits 0 with no undefined citation or reference lines in the log.
5. The abstract, the contribution list, and the methodology use identical counts.
6. The PRISMA diagram boxes sum consistently, using the `screen_*` metrics rather than typed literals.

## Known failure catalog

| Symptom | Cause | Fix |
|---|---|---|
| Search returns 0 for a source that should have hits | Wrong arg name (`limit`), or unsupported source | `--list-tools`, use `max_results`, drop the source from the query file |
| Tier counts drift between runs | Keyword rules edited after numbers were written | Freeze rules in `screening.json`, rerun step 5 |
| Corpus number too large | Duplicate records from DOI-less variants (v1/v2, preprint plus journal) | Dedup on normalized DOI then title |
| `UnicodeDecodeError` or garbled titles | Windows default codepage cp1256 or cp1252 | `encoding='utf-8'` on every open, reconfigure stdout |
| `bad escape \c` in Python | `\caption` in a non-raw regex pattern | raw strings or `re.escape` |
| `! Undefined control sequence. \textoc` | Macro assumed to exist | `\newcommand` in preamble |
| pdflatex aborts, aux files half-written | Disk full | Check free space in preflight, clean aux and rebuild |
| Venue audit passes on obviously wrong journals | Resolver venue read from a top-level key that does not exist | Parse the `extra` repr for `container_title` |
| A valid DOI permanently marked not in Crossref | One empty resolver answer cached as absence | `status=error` rows retry; delete the row and rerun |
| Screening rule matches nothing though the terms are right | `and` list means all-of, not any-of | Nest the alternatives as one group |
| WebFetch 403, binary, or queue error | PDF or paywalled endpoint | `WebSearch` the HTML page, or download then read locally |
| WebSearch rejected | Query over 100 characters | Shorten the query |
| 10+ parallel review agents all fail | Concurrency pressure | Batches of 6 or fewer, and do the critical audits inline |
| Bib entry plausible but wrong | Never resolved against a DOI | Step 9 is blocking, not optional |

## Resources

- `examples/queries.json` - twelve-query, nine-source search file for a worked topic.
- `examples/screening.json` - complete pass1/tierA/B/C/exclude rule set using the nested-group syntax.
- `examples/figures.json` - PRISMA flow, tier bar and domain ring spec referencing only emitted metrics.
- `scripts/preflight.py` - checks MCP CLI, LaTeX binaries, matplotlib, free disk.
- `scripts/mcp_client.py` - JSON-RPC stdio client for paper-search-mcp; `--list-tools` or one JSON query.
- `scripts/run_searches.py` - executes a query file into `searches/`, resumable.
- `scripts/dedupe.py` - DOI-then-title dedup with evidence log.
- `scripts/screen_tiers.py` - config-driven two-pass screening, tiering and funnel closure check.
- `scripts/number_audit.py` - asserted quantities vs computed corpus counts, with metric provenance.
- `scripts/verify_venues.py` - DOI to Crossref venue/author audit against `references.bib`.
- `scripts/reconcile_cites.py` - cite keys vs bib keys.
- `scripts/make_figures.py` - PRISMA flow, bar and domain ring figures from audited counts.
- `scripts/build.py` - pdflatex/bibtex passes, log scan, page count.
- `scripts/selftest.py` - fourteen offline checks on a throwaway project; no network, no LaTeX. Run it
  after editing any script: it asserts both directions of each gate, that a clean claim passes and that
  an inflated count, a silent collision and an unknown figure placeholder fail.
- `references/ieee-cst-latex.md` - preamble, file split, table and figure patterns.
- `references/prisma-reporting.md` - PRISMA 2020 items mapped to methodology subsections.
