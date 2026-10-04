# PRISMA Survey → LaTeX Pipeline

A Qoder Skill that turns a systematic-review topic into a compiled IEEE-format LaTeX survey through
ten scripted steps. Search execution, de-duplication, screening, DOI verification, numeric provenance,
figure generation and the PDF build are all performed by scripts, so every count printed in the
manuscript is reproducible from the corpus files on disk.

The writing stays human. The pipeline owns the evidence.

## Requirements

| Requirement | Detail |
|---|---|
| Qoder | Any version that loads user Skills from `~/.qoder/skills` |
| Python | 3.9 or newer, on PATH as `python` |
| Python package | `matplotlib` (vector figure output only; no TeX packages needed for the figures) |
| Bibliographic MCP CLI | `paper-search-mcp` installed and reachable. The Skill locates it under `%APPDATA%\Python\*\Scripts\` or on PATH; set `PAPER_SEARCH_MCP` to force a specific binary. The Skill does not install it |
| LaTeX | `pdflatex`, `bibtex`, `pdfinfo` on PATH, or a standard MiKTeX / TeX Live installation the scripts can find |
| Disk | 500 MB free on the drive holding the manuscript; below that a build aborts mid-run and leaves corrupt `.aux` files |
| Network | Required for steps 2, 6 and 9. `WebFetch` on PDF URLs is unreliable here; the workflow uses `WebSearch` plus local download instead |

Run `python scripts/preflight.py` after installation to check all of it in one pass.

## Installation

Copy the `prisma-survey-latex-pipeline` folder into the user Skills directory and restart the session:

```
Windows   %USERPROFILE%\.qoder\skills\prisma-survey-latex-pipeline
macOS     $HOME/.qoder/skills/prisma-survey-latex-pipeline
Linux     $HOME/.qoder/skills/prisma-survey-latex-pipeline
```

The folder name must match the `name` field in `SKILL.md`.

## What it does

```
0  mcp_client.py --list-tools      real tool names and argument spelling, never assumed
1  protocol/                       PRISMA protocol and boolean strings written before any search
2  run_searches.py                 one JSON file per query, resumable, zero-hit sources reported
3  dedupe.py                       DOI then normalised title, evidence log written
4  screen_tiers.py                 title pass, abstract pass, tiers A/B/C from an external rules file,
                                  funnel closure checked before anything is counted
5  number_audit.py                 every quantity in the .tex files matched against computed counts;
                                  unexplained numbers exit non-zero
6  novelty check                   nearest competitor surveys, scored and classified
7  grey-literature anchoring       standards and vendor documents recorded with URL, version, dates
8  LaTeX scaffold                  split manuscript, preamble patterns that survive IEEEtran
9  verify_venues.py                DOI resolution into append-only evidence, then bib audit for wrong
                                  venue, wrong author, mojibake, absent and never-resolved DOIs
   reconcile_cites.py              cite keys against bib keys
10 make_figures.py + build.py      figures drawn from the audited counts file, then pdflatex/bibtex
                                  with a log scan and page count
```

## Using it in a session

Ask for a PRISMA survey in the topic domain and the Skill drives the steps. To run the scripts
directly, from a project directory laid out as in `SKILL.md`:

```
python scripts/preflight.py
python scripts/run_searches.py   --config searches/queries.json --outdir searches
python scripts/dedupe.py         --indir searches --outdir corpus
python scripts/screen_tiers.py   --corpus corpus/corpus_all.json --rules protocol/screening.json --outdir corpus
python scripts/number_audit.py   --root . --manuscript manuscript --corpus corpus
python scripts/verify_venues.py  --corpus corpus/tierA.json --bib manuscript/references.bib
python scripts/reconcile_cites.py --manuscript manuscript
python scripts/make_figures.py   --counts corpus/evidence/corpus_counts.json --spec figures_src/figures.json --outdir figures
python scripts/build.py          --manuscript manuscript --main main.tex
```

`examples/` holds a complete, runnable set of the three configuration files for a worked topic
(llm clinical hallucination detection): twelve queries over nine sources, the screening rule set, and
a three-figure spec. Copy them, replace the vocabulary, and the pipeline is otherwise unchanged.

## Guarantees the scripts enforce

- A number in the manuscript that no file produces fails the audit. Coincidental matches are labelled
  separately from provenance matches, and calendar years are reported apart from counts.
- De-duplication keys on DOI, then on title only where a record carries no DOI. Identical titles under
  two different DOIs are written to `corpus/evidence/title_collisions.csv` for one human decision
  instead of being merged silently.
- Screening rules are data, not code, and every tier decision is logged with the terms that caused it,
  so a decision can be replayed. The stage funnel is checked for arithmetic closure before any count is
  usable.
- Venue truth is read from the resolver's `extra` block, where the container actually lives. A resolver
  that returns nothing is logged as an error and retried, never cached as "not indexed".
- Figures are generated from the same counts file the audit validated, so prose and diagram cannot
  drift apart.
- The build is only reported as passing when the LaTeX log contains no undefined citation, undefined
  reference or undefined control sequence.

## Verifying an installation

```
python scripts/selftest.py
```

Fourteen offline checks run against a throwaway project in a temporary directory: no network access, no
LaTeX, no domain data. Each gate is tested in both directions, so a clean project must exit 0 and a
planted defect must exit 1. Run it after editing any script.

## Scope

This Skill performs search execution, corpus bookkeeping, citation verification, numeric provenance,
figures and building. Structure, argumentation and reviewer simulation belong to the `academic-paper`,
`academic-paper-reviewer`, `deep-research` and `academic-pipeline` Skills, which can call this one as
their evidence layer. It is not for short narrative reviews or non-LaTeX deliverables.

## Repository layout

```
prisma-survey-latex-pipeline/
  SKILL.md                 trigger description and the ten-step procedure
  scripts/                 eleven executables, stdlib plus matplotlib only
  references/              PRISMA 2020 reporting mapping, IEEE LaTeX patterns
  examples/                runnable query, screening and figure specifications
```

## License

MIT. See `LICENSE`.

## Contact

Questions and corrections: labeebderhem@gmail.com
