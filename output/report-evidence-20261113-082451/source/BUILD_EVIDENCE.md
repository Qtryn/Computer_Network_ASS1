# Evidence-ready report source

Six genuine PNGs have been inserted into `evidence/` with the exact names required by `main.tex`. The original downloaded archive was not modified.

The separately extracted copy uses full-width screenshot figures and captions identifying the actual captures. It preserves highlighted technical limitations and distinguishes the previous audit's timings from the current screenshot rerun.

This machine had no pdfLaTeX installation on Windows or Ubuntu WSL. **No updated PDF has been compiled or visually checked.** To build in an existing TeX installation or Overleaf, select pdfLaTeX and run:

```text
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

Inspect all six figures at normal zoom, cross-references, and page layout after compilation. Keep the highlighted BBR/CUBIC, offline persistence, and lecturer-confirmation notes.

See `evidence/EVIDENCE_MANIFEST.md` for run dates, commit, environment, genuine originals, crop recipes, test logs, PCAP hash/frame numbers, manual authentication steps and validation. Full traceability material is retained in the repository under `docs/evidence/report-screenshots/`.
