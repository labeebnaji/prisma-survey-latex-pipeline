# PRISMA 2020 reporting → LaTeX methodology section

The PRISMA 2020 statement is a **27-item checklist** plus a flow diagram. Numbering is stable across
the official PDF but not across secondary summaries, so download the checklist and cite item numbers
from it rather than from memory:

- `https://www.prisma-statement.org/prisma-2020-checklist` (checklist and explanation document)

Treat the item list below as a coverage checklist by name, not as authoritative item numbers.

## Section map

Write the Methods section with one subsection per group, in this order. The subsection titles are what
a reviewer greps for.

| Reporting element | Subsection to write | Must contain |
|---|---|---|
| Eligibility criteria | `Eligibility criteria` | numbered inclusion `I1..In` and exclusion `E1..En`, each testable |
| Information sources | `Information sources` | every database/index plus the query date for each |
| Search strategy | `Search strings` | the full boolean strings as executed, and a note that each was adapted to native syntax |
| Study record management | `Screening` | dedup method, key fields used, single- vs multi-reviewer |
| Selection process | `Screening` | pass 1 basis (title), pass 2 basis (abstract/full text) |
| Data collection process | `Data extraction schema` | the field list actually extracted |
| Data items | `Data extraction schema` | variables extracted and how conflicts were handled |
| Outcomes / effects measures | `Synthesis measures` | what was counted and the unit of analysis |
| Synthesis methods | `Synthesis` | how tiers feed the matrix; no meta-analysis claim without one |
| Reporting bias / certainty | `Quality appraisal` | the appraisal instrument used (e.g. MMAT) and how scores were used |
| Synthesis results | Results | the flow numbers as computed, tier counts, year and venue distributions |
| Limitations | `Limitations` | see the honesty list below |
| Registration / protocol | `Protocol` | registry name and ID, or the word "not registered" |
| Availability of materials | `Availability` | corpus JSON path or supplementary reference |

## Search strategy paragraph, worked

A run of the shipped example configs produced the figures used below. Write the paragraph once the audit
has fixed the numbers, never before.

```latex
\subsection{Information sources}
Searches were executed on nine bibliographic and preprint sources on 3 October 2026: Crossref,
OpenAlex, PubMed, EuropePMC, arXiv, Semantic Scholar, DOAJ, CORE and PubMed Central. Semantic
Scholar returned no usable records for these strings and is reported for transparency rather than
dropped. Grey literature was retrieved from the issuing body's own document channels and is anchored
in the corpus by direct citation rather than keyword discovery, because the indexed sources cover it
only partially.
```

Never quietly drop a zero-hit source. `corpus_counts.json` separates the three counts a methodology
sentence can mean: `search_sources_queried` (sources with a registered string), `search_sources`
(sources that returned at least one record) and `search_sources_empty`. Write the sentence with the
sense you mean, and name the empty sources instead of leaving them implied.

## Flow diagram numbers

Each box value must come from `corpus_counts.json`. The arithmetic must close at every stage:

```
identified (raw total)        search_raw_total, dedup_raw_records
  - duplicates removed        dedup_duplicates_removed, split into dedup_duplicates_by_doi and
                              dedup_duplicates_merged_missing_doi, plus dedup_title_collision_pairs
                              left for a human to adjudicate
  = unique records            corpus_all, screen_unique_in
  - excluded at screening     screen_pass1_excluded (= screen_excluded + screen_screened_out)
  = records screened          screen_pass1
  - set aside as context      screen_tierC
  = studies included          screen_included, screen_tierA
```

`screen_tierA + screen_tierB + screen_tierC + screen_excluded + screen_screened_out` must equal
`screen_pass1`; `screen_tiers.py` computes the difference and exits non-zero when it does not, so a box
can never be filled by eye.

Report the excluded figure at the stage where exclusion actually happened. "Reports not retrieved"
is a distinct PRISMA 2020 box and is not the same as "excluded".

If grey standards are added after the flow, show them as a separate "additional records identified
from other methods" row entering at screening, not folded into the database total.

## Honesty rules that decide acceptance

State plainly, do not imply:

- Single-reviewer screening means no inter-rater statistic. Say so; do not report a kappa you did not
  compute, and do not let the abstract imply a second reviewer existed.
- Rule-based tiering is not human assessment. Name the rule file.
- Records without abstracts were not abstract-screened. Give the count.
- Citation counts are snapshot values with a retrieval date.
- Grey standards are not peer reviewed; their authority is institutional, and that belongs in the
  quality appraisal subsection.

## Quality appraisal wording

```latex
A hybrid version of the Mixed Methods Appraisal Tool \cite{hong2018} was applied. Papers proposing
frameworks were scored on internal coherence, criterion atomicity, and evaluation transparency;
case studies on sample size, reproducibility, and reporting depth; grey standards on institutional
authority and update cadence. No record was excluded on quality grounds; quality was reported
alongside extracted fields.
```

If you did exclude on quality, change that last sentence — it is the one reviewers check against the
flow numbers.

## Numbers that must match everywhere

The abstract, the contribution list, the methodology, the results tables, and the figure must use the
same value for the same quantity. Run `number_audit.py` after any edit to the corpus or the tables;
the audit fails on any quantity it cannot trace to a file.
