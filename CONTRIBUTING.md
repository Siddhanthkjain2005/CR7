# Contributing

Read the [architecture](docs/architecture.md), [assumptions](docs/assumptions.md) and [documentation](docs/README.md) before engineering changes.

Preserve supplied sources, frozen weights and completed protocols/results. Keep CPRI and workbook profiles separate, and retain generated/measured provenance and unknown hardware facts. Unsupported ML corrections remain disabled. Do not tune against exposed test outcomes or overwrite completed evidence.

For backend changes, run `python -m pytest` and `python -m scripts.release_smoke`. For frontend changes, use the repository's build commands and rebuild `frontend/out`. Keep changes focused and document the resulting behavior and verification.
