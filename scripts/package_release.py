"""Package a reproducible submission, retaining evidence and excluding live trial/history data."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def package():
    if not (ROOT/'frontend/out/index.html').exists(): raise SystemExit('Build the frontend before packaging.')
    qa=ROOT/'artifacts/qa_summary.json'
    if not qa.exists() or not json.loads(qa.read_text()).get('backend_tests_passed'):
        raise SystemExit('Record successful QA before packaging.')
    directories=['backend','config','data','docs','reports','scripts','tests','frontend/app','frontend/components','frontend/lib','frontend/out','artifacts/models','artifacts/experiments','artifacts/qa','presentations','.github']
    singles=['README.md','CONTRIBUTING.md','Makefile','requirements.txt','requirements-experiments.txt','pytest.ini','Start_ImpulseTwin.command','Dockerfile','.dockerignore','.gitignore',
        'frontend/package.json','frontend/package-lock.json','frontend/tsconfig.json','frontend/next.config.ts','frontend/postcss.config.mjs','frontend/next-env.d.ts',
        'artifacts/reference_workbook_snapshot.json','artifacts/data_audit.json','artifacts/stress_test_summary.json','artifacts/demo_artifact_manifest.json','artifacts/qa_summary.json']
    files={p for d in directories for p in (ROOT/d).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.name!='.DS_Store' and 'prompt' not in p.stem.lower() and p.name not in {'AGENTS.md','HANDOFF.md','PROJECT_STATE.md'} and p.suffix not in {'.sqlite3','.db'} and not any(part in {'trials','diagnostics'} for part in p.relative_to(ROOT).parts)}
    files.update(ROOT/p for p in singles if (ROOT/p).exists())
    out=ROOT/'release';out.mkdir(exist_ok=True)
    manifest={'name':'ImpulseTwin AI submission','version':'1.0.0','ready_by':'2026-10-10',
        'cloud_deployment':'Deployment is independent of this reproducible local package',
        'omitted':'Installed dependency folders, live SQLite histories and raw uploaded trials are excluded. Executed QA and the demo UI capture are included.',
        'files':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    with zipfile.ZipFile(out/'ImpulseTwin_AI_Local_PoC.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(files):z.write(p,str(Path('ImpulseTwin_AI')/p.relative_to(ROOT)))
        z.write(out/'manifest.json','ImpulseTwin_AI/RELEASE_MANIFEST.json')
    print(f"Packaged {len(files)} files; {(out/'ImpulseTwin_AI_Local_PoC.zip').stat().st_size/1e6:.1f} MB")

if __name__=='__main__':package()
