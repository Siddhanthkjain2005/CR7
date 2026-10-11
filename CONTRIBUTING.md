# Contributing

Start from [`codex/assembly-twin`](https://github.com/Siddhanthkjain2005/CR7/tree/codex/assembly-twin). Read its [engineering instructions](https://github.com/Siddhanthkjain2005/CR7/blob/codex/assembly-twin/AGENTS.md) and [documentation](docs/README.md) before scientific changes.

## Development

Follow the [Python 3.12 quick start](README.md#run-locally). For frontend changes, use Node.js 22:

```bash
cd frontend
npm ci
npm run typecheck
npm run test:unit
npm run build -- --webpack
cd ..
python scripts/dev.py
```

The prepared app serves `frontend/out`; rebuild it after frontend source edits.

## Relevant checks

For engineering/backend changes:

```bash
python -m pytest
python -m scripts.release_smoke
```

The smoke check uses an isolated database and blocks external network access. The broader release verifier writes artifacts; review those before committing. Documentation changes need content/link checks rather than new scientific reruns.

## Scientific records

Preserve supplied sources, frozen weights and completed protocols/results. Do not tune against an exposed test or overwrite its result. New studies belong in separately versioned records with their scope declared before scoring.

Keep CPRI/workbook profiles separate, and preserve stock provenance, generated/measured distinctions, prediction-basis labels and unknown hardware facts. Do not transfer workbook residual ML into unsupported circuit/CPRI settings. Numerical agreement is not physical accuracy.

## Issues and pull requests

Include branch/commit, reproduction steps, expected/observed behavior and relevant checks. Identify capture origin. Public issues must not contain credentials or private lab files.

Keep changes focused and describe their resulting behavior. UI changes should name the workflows checked; numerical changes should include the reproduced defect and preservation evidence. Update relevant setup/behavior documentation.
