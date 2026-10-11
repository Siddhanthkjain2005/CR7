# Reproducible submission package

Use the [main branch](https://github.com/Siddhanthkjain2005/CR7/tree/main) for the complete application. The repository includes the prepared interface, supplied sources, frozen models, completed evidence and team presentation.

After installing the dependencies from the [quick start](../README.md#run-locally), run:

```bash
python -m scripts.release_smoke
python -m scripts.package_release
```

The packager creates `release/ImpulseTwin_AI_Local_PoC.zip` and a SHA-256 file manifest. Generated distribution files are local outputs and are excluded from Git. Installed dependencies, private working notes and live uploaded-trial histories are excluded.

The [presentation](https://github.com/Siddhanthkjain2005/CR7/tree/main/presentations) and [demonstration guide](../docs/demo_walkthrough.md) are the submission entry points. Historical software and scientific checks remain in `artifacts/`; their stated scope is unchanged.
