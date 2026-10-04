# IEEE-format LaTeX scaffold

## File split

`main.tex` owns the preamble, front matter, and the inclusion chain. Everything else is `\input`:

```latex
\documentclass[journal]{IEEEtran}
\usepackage{cite}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{graphicx}
\usepackage{textcomp}
\usepackage{xcolor}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{url}
\usepackage[hidelinks]{hyperref}

% Symbols the matrix legend needs. Neither IEEEtran nor textcomp defines these.
\newcommand{\textoc}{\ensuremath{\circ}}
```

Load `cite` before `hyperref`. Loading `hyperref` first makes `\cite` produce doubled brackets.

Body order: `\begin{document}` + title/author block + `\IEEEtitleabstractindextext{...}`, then the
introduction, prior-work section, and methodology written in `main.tex`, then at the end:

```latex
\input{sections}
\input{appendix}

\bibliographystyle{IEEEtran}
\bibliography{references}

\end{document}
```

Do not paste `sections.tex` into `main.tex`. A single 1000-line file cannot be diffed, and a partial
edit forces a full re-read. `\input` paths omit the extension.

## Front-matter macros that break across template versions

- `\IEEEpubid{...}` and `\IEEEpubidadjcol` moved between `IEEEtran` versions; if it errors, comment
  the line and record the deviation.
- `\IEEEminalystext` does not exist in most installs. Use a footnote or an early paragraph instead.
- `\IEEEtitleabstractindextext{...}` requires `\IEEEpeerreviewmaketitle` after it for the two-column
  page-1 layout to render correctly.

## Wide tables

Coverage matrices are the reason builds stall. Patterns that work:

```latex
\begin{table*}[t]
\centering
\caption{Cross-instrument matrix}
\label{tab:matrix}
\footnotesize
\begin{tabular}{@{}p{0.30\textwidth}ccccccc@{}}
\toprule
Dimension & A & B & C & D & E & F & G \\
\midrule
Text that wraps inside the fixed column & \textbullet & \textoc & -- & n/a & \textbullet & \textoc & \textbullet \\
\bottomrule
\end{tabular}
\end{table*}
```

- `table*` spans both columns; `table` does not.
- Use `p{0.30\textwidth}` for the row label instead of `\small` or `\resizebox` hacks.
- `booktabs` rules (`\toprule`, `\midrule`, `\bottomrule`) - vertical bars in `IEEEtran` tables fight
  the column grid.
- More than 10 columns: switch to `longtable` and let it break across pages; do not rotate the page.
- Legend characters must be defined symbols. `--` for absent, `n/a` for not applicable,
  `\textbullet` explicit, `\textoc` implicit.
- A row count is a citable quantity. Count body rows with a script before writing "the matrix has N
  dimensions".

## Per-level rubric tables

```latex
\begin{tabular}{@{}p{0.07\textwidth}p{0.85\textwidth}@{}}
\toprule
C1 & Each level is defined by observable properties, not by stated intent. \\
C2 & A level assignment cites at least one artefact per domain. \\
\bottomrule
\end{tabular}
```

Keep one table per domain with its own `\label`; the total sub-criteria count is then the sum of those
table row counts, which the numeric audit can verify.

## Figures

Vector output only:

```latex
\begin{figure}[t]
\centering
\includegraphics[width=\columnwidth]{../figures/prisma_flow.pdf}
\caption{PRISMA 2020 flow.}
\label{fig:prisma}
\end{figure}
```

`\graphicx` resolves paths relative to the file being compiled (`main.tex`), not the `\input` file.
If a figure is missing, pdflatex emits `File '...' not found` and the PDF still builds with a blank
box - which is why `build.py` scans for that explicitly.

## Build

`pdflatex` once, `bibtex`, `pdflatex` twice more. Anything else leaves stale citations. Use
`-interaction=nonstopmode -halt-on-error` so the run stops with a readable `!` line rather than
waiting on a prompt that nobody sees.

Before trusting a build:

- `pdfinfo main.pdf` for the page count.
- grep the log for `Citation ... undefined`, `Reference ... undefined`, `Undefined control sequence`.
- a page count that changes without prose changes usually means a float moved, not new content.

## Encoding

Write all `.tex` and `.bib` files as UTF-8 without BOM. `inputenc` is unnecessary under modern
pdfLaTeX for most Latin text, but if non-Latin scripts appear, declare the correct `fontenc`/`newfontface`
pair and verify `grep -nP '[\x{2013}\x{2014}]'` to find stray en dashes that came from a cp1252
round-trip.
