## Unreleased

- utils/similarity/deck/validation/enrichment/eval added in focused commits
- API stability validated; fast test subset green; ruff clean
- CI: ruff + fast pytest; artifacts for evaluation report (optional)
- pre-commit: ruff, nbstripout
- Data: annotations + canonical test sets committed; large files excluded
- Frontend scaffold added (separate module); uv.lock for reproducibility

### Added
- Tests: small-set evaluation metrics (P@K/nDCG/MRR), LLM cache hit, PATHS invariants
- CI: GitHub Actions workflow running ruff + fast pytest; conditional artifact upload for `experiments/evaluation_report_latest.html`

### Changed
- Scripts: centralized experiment save/log paths via `PATHS.experiments`


