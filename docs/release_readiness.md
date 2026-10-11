# Local setup and release readiness

No deployment is performed. Frozen artifacts are committed; do not retrain to start the app. Python 3.12 and Node 22+ are the documented runtime targets. Node is needed only for frontend work/builds.

## Windows PowerShell

```powershell
git clone https://github.com/Siddhanthkjain2005/Impulse.git
cd Impulse
py -3.12 -m venv .venv
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm.cmd ci
$env:NEXT_TELEMETRY_DISABLED = '1'
npm.cmd run build -- --webpack
cd ..
.\.venv\Scripts\python.exe scripts/verify_release.py
.\.venv\Scripts\python.exe scripts/dev.py
```

## macOS and Linux

```sh
git clone https://github.com/Siddhanthkjain2005/Impulse.git
cd Impulse
python3.12 -m venv .venv
export PYTHONUTF8=1
.venv/bin/python -m pip install -r requirements.txt
cd frontend
npm ci
NEXT_TELEMETRY_DISABLED=1 npm run build -- --webpack
cd ..
.venv/bin/python scripts/verify_release.py
.venv/bin/python scripts/dev.py
```

Open `http://127.0.0.1:8000/judge/`. Setup needs internet for packages; normal inference uses local models/data/assets. `Ctrl+C` stops the server. Port 8000 must be free. `IMPULSETWIN_DB` can select an isolated SQLite path. Model absence produces a clear restore-artifacts message, never a request to retrain on the exposed Hidden Test.

The existing Makefile and Mac double-click launcher remain convenience paths. macOS/Linux were **NOT TESTED in this hardening**. The earlier release recorded fresh Python/npm installations; this pass reuses those dependencies because the dependency files are unchanged. Windows passes 263 tests, typecheck/build, 23 local static assets and a fresh-database external-network-denied smoke. Desktop/mobile browser review also passes. A second physical laptop and actual disconnected-network/browser rehearsal remain **NOT TESTED**.

The 6 October baseline initially terminated with a native pandas/access violation; the unchanged isolated checkout passed 237 tests with native threads bounded to one. Final tests passed 263 with two existing warnings and two pytest-cache permission warnings. The crash's root cause is unproven. `dev.py`, the verifier and audit scripts now default OMP/OpenBLAS/MKL/NumExpr threads to one before numerical imports; explicit caller overrides remain supported. Browser review found a pre-existing host/browser locale mismatch in number hints; deterministic formatting, a repeated typecheck/build and a fresh-origin console check resolve it. See [Optimization report](validation/optimization_report.md) and `artifacts/hardening/` for retained before/after evidence.

## Verifier

`python scripts/verify_release.py` writes `artifacts/release_readiness.json` and `.md`, with retained text/XML logs under `artifacts/release_checks/`. Each check is **PASS**, **FAIL** or **NOT TESTED**; overall **PARTIAL** means no failures but some checks not executed. `--quick` explicitly marks tests/typecheck/build untested rather than recycling old results.

Checks include required models/pages, protected source/data/model/experiment SHA-256 values, valid profiles/catalog/weights, frozen registry references, backend tests, frontend typecheck/build, remote/missing static assets, and a separate fresh SQLite process that denies external socket/DNS connections while exercising inference and local routes/assets. This process-level network denial does not establish a physically disconnected-browser rehearsal.

`config/release_integrity.json` freezes 45 original source/data/model/experiment files from base commit `cd8add626343f57dc1884f50fa760ecdd6869b72`. The attached workbook/PDF exactly matched those originals. No hidden-test output or V1–V5 evidence was changed.

## Portability findings from the baseline

Initial Windows checkout converted text to CRLF, invalidating historical scientific hashes. Restoring exact Git bytes and `.gitattributes` LF rules prevents this. UTF-8 runtime configuration reads prevent profile/topology text from differing from saved calibration scopes. The normalized baseline produced 197/198 passing tests.

The remaining V5 integrity test assumed slash-separated paths and an untracked macOS `.DS_Store` entry. Its comparisons now normalize path separators and exclude only that Finder metadata. Numerical recomputation assertions use `rtol=1e-12`, `atol=1e-14` for platform floating-point summation differences (~4e-16); exact frozen hashes and sample/fold identities remain required. No useful test was removed and no historical artifact or experiment runner was rewritten.

Dependency versions are pinned as before, but Python transitive dependencies are not fully locked. The preserved original release ZIP and historic QA reports describe earlier builds; use the branch source, its rebuilt `frontend/out`, and the new readiness report for this change. Repackage explicitly if a new distributable ZIP is needed.
