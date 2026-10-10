from pathlib import Path
from datetime import datetime,timezone
import csv
import io
import json
import hashlib
import uuid
import html
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from .schemas import OptimizeRequest,SimulationRequest,ComplianceRequest,TrialEvaluationRequest,SetupTransitionRequest,SensitivityRequest
from .optimization.engine import optimize, profile_for, custom_profile, CUSTOM_ID, PROFILES, physics
from .physics.waveform_metrics import analyze,waveform_from_metrics
from .physics.compliance import check,RULES
from .data.workbook_reference import calculate
from .ml.reference_knn import WorkbookKNN
from .ml.registry import registry
from .ml.benchmark_scorecard import scorecard
from . import storage
from .reports import report_html
from .run_evidence import summarize_evidence
from .trial_quality import assess_waveform
from .decision_metrics import captured_limits, extracted_compliance
from .trial_provenance import validate_csv_provenance
from .trial_evaluation import evaluate_trials
from .setup_transition import plan_transition
from .transition_report import transition_report
from .sensitivity import compare_sensitivity
from .evidence import evidence_record, laboratory_summary, recommendation_evidence, validated_evaluation_ids, reviewed_calibration_origin, SOURCES
from .hardware_integrity import hardware_integrity
from .test_objects import catalog, validate_request
from .experiment_timeline import timeline

ROOT=Path(__file__).resolve().parents[2]
app=FastAPI(title='ImpulseTwin AI',version='1.0.0',description='Offline physics-guided impulse-generator decision support. No hardware control.',docs_url=None,redoc_url=None)
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:3000','http://127.0.0.1:3000','http://localhost:8000','http://127.0.0.1:8000'],allow_methods=['GET','POST'],allow_headers=['*'])

def saved(id,kind):
    try:return storage.get(id,kind)
    except KeyError:raise HTTPException(404,f'{kind} not found')

def resolve_profile(req):
    return custom_profile(req) if req.profile_id==CUSTOM_ID else profile_for(req.profile_id)

def selected_candidate(run,candidate_id=''):
    if not candidate_id:return run['candidates'][0]
    candidate=next((c for c in run['candidates'] if c['id']==candidate_id),None)
    if candidate is None:raise HTTPException(422,'The selected candidate does not belong to this run. Select a saved candidate before associating a waveform.')
    return candidate

def trial_correction(measured,candidate):
    keys=['front_us','tail_us','crest_kv']
    previous=candidate.get('calibration') or {}
    prior=np.array(previous.get('bias',[0.,0.,0.]),float)
    prediction=np.array([candidate['hybrid'][k] for k in keys])
    base=prediction-prior
    observed=np.array([measured[k] for k in keys])
    return (observed-base).tolist(),{
        'parent_calibration_id':previous.get('id'),'prior_applied_bias':prior.tolist(),
        'base_prediction':dict(zip(keys,base.tolist())),
        'method':'Replacement total correction relative to the original model: prior applied correction plus new observed residual.'}

@app.get('/api/health')
def health():
    try:registry()
    except (ValueError,OSError) as e:raise HTTPException(503,str(e))
    return {'status':'online','version':'1.0.0','mode':'local / offline capable','hardware_control':False}

@app.get('/docs',response_class=HTMLResponse,include_in_schema=False)
def offline_api_docs():
    schema=app.openapi()
    rows=''.join(f'<tr><td><b>{html.escape(method.upper())}</b></td><td><code>{html.escape(path)}</code></td><td>{html.escape(info.get("summary",""))}</td></tr>' for path,methods in schema['paths'].items() for method,info in methods.items())
    return '<!doctype html><html lang="en"><meta charset="utf-8"><title>ImpulseTwin API documentation</title><style>body{font:15px system-ui;max-width:1100px;margin:50px auto;color:#16303f;padding:20px}table{width:100%;border-collapse:collapse}td{padding:12px;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f8;padding:20px;font-size:12px}a{color:#087f8c}</style><h1>ImpulseTwin AI API</h1><p>Local API reference. All content on this page is available offline.</p><p><a href="/">Open engineering workspace</a> · <a href="/openapi.json">OpenAPI JSON</a></p><table>'+rows+'</table><h2>Request schemas</h2><pre>'+html.escape(json.dumps(schema.get('components',{}).get('schemas',{}),indent=2))+'</pre></html>'

@app.get('/api/source-status')
def source_status():
    manifest=json.loads((ROOT/'data/processed/manifest.json').read_text(encoding="utf-8"))
    workbook=ROOT/'data/source/Hybrid_Physics_ML_Impulse_Generator_Optimiser.xlsx'
    dataset=ROOT/'data/processed/synthetic_dataset.csv'
    _,meta=registry()
    return {'sources':[{'name':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (ROOT/'data/source').glob('*')],
        'manifest':manifest,'source_hash_matches_snapshot':hashlib.sha256(workbook.read_bytes()).hexdigest()==manifest['source_sha256'],
        'dataset_hash_matches_frozen_model':hashlib.sha256(dataset.read_bytes()).hexdigest()==meta['dataset_sha256'],
        'formula_parity':'golden case and all 1400 cached helper distances/weights verified',
        'published_metrics_parity':'UNRESOLVED: hardcoded table differs from formula-based Validation evaluation',
        'lab_validation':'pending actual measured data','source_reconciliation':'/api/documents/source_reconciliation',
        'standards':RULES,'qa':json.loads((ROOT/'artifacts/qa_summary.json').read_text(encoding="utf-8")) if (ROOT/'artifacts/qa_summary.json').exists() else None}

@app.get('/api/generator-profiles')
def profiles():return PROFILES

@app.get('/api/hardware-integrity')
def hardware_sources():return [hardware_integrity(p) for p in PROFILES]

@app.get('/api/test-objects')
def test_objects():return catalog()

@app.post('/api/test-objects/validate')
def validate_test_object(req:OptimizeRequest):
    try:return validate_request(req,resolve_profile(req))
    except ValueError as e:raise HTTPException(422,str(e))

@app.get('/api/experiment-timeline')
def experiment_timeline():return timeline()

@app.get('/api/search-quality')
def search_quality():
    path=ROOT/'artifacts/search_quality/summary.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'status':'PENDING','message':'Search quality benchmark pending.'}

@app.get('/api/laboratory-evidence')
def laboratory_evidence():
    return laboratory_summary(storage.list_records('trial',None),storage.list_records('calibration',None),storage.get,ROOT)

@app.get('/api/runs/{id}/judge')
def judge_run(id:str):
    run=saved(id,'run'); evaluations=storage.list_records('evaluation',None)
    calibration_views={}
    def origin_view(calibration_id):
        if calibration_id not in calibration_views:
            try:
                calibration=storage.get(calibration_id,'calibration')
                calibration_views[calibration_id]=reviewed_calibration_origin(calibration,storage.get,ROOT)
            except KeyError:
                calibration_views[calibration_id]={'source_type':'unknown','source_review':{
                    'status':'UNVERIFIABLE','message':'Original calibration audit record is missing.',
                    'audit_record_changed':False}}
        return calibration_views[calibration_id]
    candidates=[]
    for candidate in run['candidates']:
        ids=validated_evaluation_ids(run,candidate,evaluations,storage.get,ROOT)
        view={**candidate}
        if (candidate.get('calibration') or {}).get('id'):
            reviewed=origin_view(candidate['calibration']['id'])
            view['calibration']={**candidate['calibration'],'source_type':reviewed['source_type'],
                                 'source_review':reviewed['source_review']}
            view['ood']={**candidate.get('ood',{}),'lab_calibrated':reviewed['source_type']=='measured_lab'}
        candidates.append({**view,'evidence':recommendation_evidence(view,ids)})
    calibration_review=run.get('calibration_review')
    if calibration_review and calibration_review.get('id'):
        reviewed=origin_view(calibration_review['id'])
        calibration_review={**calibration_review,'source_type':reviewed['source_type'],
                            'source_review':reviewed['source_review']}
    alternatives=[]
    for label,key in [('Best waveform match',lambda c:c['accuracy_cost']),
                      ('Fewest components',lambda c:c['setup_component_count']),
                      ('Largest stage-voltage margin',lambda c:-c['settings']['voltage_margin_kv_stage'])]:
        candidate=min(candidates,key=key)
        existing=next((a for a in alternatives if a['candidate']['id']==candidate['id']),None)
        if existing:existing['labels'].append(label)
        else:alternatives.append({'labels':[label],'candidate':candidate})
    for candidate in candidates:
        if len(alternatives)>=3:break
        if not any(a['candidate']['id']==candidate['id'] for a in alternatives):
            alternatives.append({'labels':[f"Ranked alternative {candidate['rank']}"],'candidate':candidate})
    trials=[{**t,'evidence':evidence_record(t,run)} for t in storage.list_records('trial',None) if t['run_id']==id]
    return {**run,'candidates':candidates,'calibration_review':calibration_review,'alternatives':alternatives,'trials':trials,
            'alternative_scope':'Trade-offs among the returned shortlist; fewest components is not fewest changes from an existing setup. Nominal failures remain diagnostic.',
            'laboratory':laboratory_evidence()}

@app.get('/api/generator-profiles/{id}')
def profile(id:str):
    try:return profile_for(id)
    except ValueError as e:raise HTTPException(404,str(e))

@app.get('/api/reference')
def reference(impulse_type:str='Lightning'):
    if impulse_type not in ['Lightning','Switching']:raise HTTPException(422,'Unknown impulse type')
    c=calculate(impulse_type=impulse_type)
    q=pd.DataFrame([{'Impulse_Type':impulse_type,'Test_kV':1425,'Load_C_pF':850,'Divider_C_pF':500,'Stray_C_pF':150,'L_uH':18.5,'Efficiency':.82,'Front_R_Stage':c['front_r_stage'],'Tail_R_Stage':c['tail_r_stage']}])
    res,neighbors=WorkbookKNN().predict(q,True); values=np.array([c['front_us'],c['tail_us'],c['crest_kv']])+res[0]
    return {'physics':c,'hybrid':dict(zip(['front_us','tail_us','crest_kv'],values.tolist())),
        'correction':res[0].tolist(),'neighbors':neighbors[0],'kind':'exact workbook reference calculator; inventory unchecked',
        'golden_case_verified':impulse_type=='Lightning','published_validation_table_parity':False}

@app.post('/api/optimize')
def run_optimize(req:OptimizeRequest):
    try:
        cal=saved(req.calibration_id,'calibration') if req.calibration_id else None
        if cal:
            cal=reviewed_calibration_origin(cal,storage.get,ROOT)
            if cal['source_type']=='unknown':raise ValueError(cal['source_review']['message'])
        result=optimize(req,cal)
    except ValueError as e:raise HTTPException(422,str(e))
    id=uuid.uuid4().hex[:12]; result['run_id']=id
    return storage.put('run',id,result)

@app.post('/api/simulate')
def run_simulate(body:SimulationRequest):
    try:
        req=body.inputs; p=resolve_profile(req); s=body.settings.model_dump()
        n=s['stages']; q=s['charge_kv_stage']
        if not p['enabled'] or not p['min_stages']<=n<=p['max_stages'] or not 0<q<=p['stage_kv']:raise ValueError('Settings exceed profile ratings.')
        stage_energy_kj=.5*p['stage_c_uf']*1e-6*(q*1000)**2/1000
        if stage_energy_kj>p['energy_stage_kj'] or n*stage_energy_kj>p['energy_total_kj']:
            raise ValueError('Settings exceed the supplied stage or total energy rating.')
        return physics(req,p,n,q,s['front_r_stage'],s['tail_r_stage'],True)
    except (KeyError,TypeError,ValueError) as e:raise HTTPException(422,str(e))

@app.post('/api/compliance/check')
def run_compliance(body:ComplianceRequest):
    try:return {**check(body.impulse_type,body.test_kv,body.prediction.model_dump()),'scope':'Waveform-only check. Hardware feasibility must be evaluated by the optimizer.'}
    except (KeyError,ValueError,TypeError) as e:raise HTTPException(422,str(e))

@app.get('/api/models')
def models():
    _,meta=registry()
    result={**meta,'hidden_test':json.loads((ROOT/'artifacts/models/hidden_test_evaluation.json').read_text(encoding="utf-8"))}
    experiment=ROOT/'artifacts/experiments/v2/summary.json'
    if experiment.exists():
        result['experiment_v2']=json.loads(experiment.read_text(encoding="utf-8"))
    v3=ROOT/'artifacts/experiments/v3/summary.json'
    if v3.exists():
        study=json.loads(v3.read_text(encoding="utf-8"))
        result['experiment_v3']={k:study[k] for k in ['version','scope','macro_improvement_pct','promotion_eligible','decision','hidden_test_evaluated','elapsed_seconds']}
    v4=ROOT/'artifacts/experiments/v4/summary.json'
    if v4.exists():
        study=json.loads(v4.read_text(encoding="utf-8"))
        protocol=json.loads((v4.parent/'protocol.json').read_text(encoding="utf-8"))
        result['experiment_v4']={k:study[k] for k in ['version','scope','macro_improvement_pct','worst_target_improvement_pct','promotion_eligible','decision','hidden_test_evaluated','calibration_evaluated','validation_evaluated','elapsed_seconds','nested_cv']}
        result['experiment_v4']['candidate_count']=len(protocol['grid'])
        result['experiment_v4']['selected_pooled_fold_targets']=sum(s['blend']>0 for fold in study['fold_choices'] for target in fold for s in target['selection'].values())
    v5=ROOT/'artifacts/experiments/v5/summary.json'
    if v5.exists():
        study=json.loads(v5.read_text(encoding="utf-8"))
        result['experiment_v5']={k:study[k] for k in ['version','scope','macro_improvement_pct','control_macro_improvement_pct','improvement_vs_matched_control_pct','worst_target_improvement_pct','promotion_eligible','decision','hidden_test_evaluated','calibration_evaluated','validation_evaluated','elapsed_seconds','nested_cv']}
    result['benchmark_scorecard']=scorecard(result['hidden_test'],result.get('experiment_v2'))
    independent=ROOT/'artifacts/independent_simulation/v1/summary.json'
    if independent.exists():
        result['independent_circuit_verification']=json.loads(independent.read_text(encoding='utf-8'))
    return result

def saved_json(relative):
    path=ROOT/relative
    if not path.is_file():raise HTTPException(404,'This evaluation has not been recorded yet.')
    return json.loads(path.read_text(encoding='utf-8'))

@app.get('/api/evaluation-pack')
def evaluation_pack(records:bool=False):
    """Saved evaluation-pack results; reads the artifact, never re-runs the cases."""
    result=saved_json('artifacts/evaluation_pack/v1/results.json')
    return result if records else {k:v for k,v in result.items() if k!='records'}

@app.get('/api/verification/physics-audit')
def physics_audit():return saved_json('artifacts/physics_audit/v1/audit.json')

@app.get('/api/verification/surrogate')
def surrogate_study():
    summary=saved_json('artifacts/models/circuit_surrogate_v1/summary.json')
    protocol=saved_json('artifacts/models/circuit_surrogate_v1/protocol.json')
    manifest=saved_json('data/generated/circuit_dataset_v1/manifest.json')
    curve_path=ROOT/'data/generated/circuit_dataset_v1/learning_curve.json'
    return {'summary':summary,'protocol':protocol,'dataset':{k:manifest[k] for k in ['version','rows','configurations','circuit_model','split','summary','surrogate_warning','provenance_classes']},
            'learning_curve':json.loads(curve_path.read_text(encoding='utf-8')) if curve_path.is_file() else None}

@app.get('/api/verification/independent-circuit')
def independent_circuit_verification():
    path=ROOT/'artifacts/independent_simulation/v1/summary.json'
    if not path.is_file():raise HTTPException(404,'Independent circuit verification is not recorded.')
    return json.loads(path.read_text(encoding='utf-8'))

@app.get('/api/models/{id}/metrics')
def model_metrics(id:str):
    result=models()
    if id==result.get('experiment_v2',{}).get('version'):return result['experiment_v2']
    if id==result.get('experiment_v4',{}).get('version'):
        return json.loads((ROOT/'artifacts/experiments/v4/summary.json').read_text(encoding="utf-8"))
    if id==result.get('experiment_v5',{}).get('version'):
        return json.loads((ROOT/'artifacts/experiments/v5/summary.json').read_text(encoding="utf-8"))
    if id!=result['version']:raise HTTPException(404,'Unknown model version')
    return result

@app.post('/api/explain')
def explain(body:dict):
    run=saved(body.get('run_id',''),'run'); candidate=next((c for c in run['candidates'] if c['id']==body.get('candidate_id')),run['candidates'][0])
    return {k:candidate[k] for k in ['explanation','score_breakdown','physics','correction','hybrid','ood','robustness','front_network','tail_network']}

@app.get('/api/runs')
def runs():
    return [{'id':r['id'],'created_at':r['created_at'],'profile':r['profile']['name'],'inputs':r['inputs'],'status':r['candidates'][0]['compliance']['status'],'model_version':r['model_version'],'evidence':summarize_evidence(r)} for r in storage.list_records('run')]

@app.get('/api/runs/{id}')
def get_run(id:str):return saved(id,'run')

@app.post('/api/runs/{id}/candidates/{candidate_id}/sensitivity')
def sensitivity(id:str,candidate_id:str,request:SensitivityRequest):
    try: result=compare_sensitivity(saved(id,'run'),candidate_id,request)
    except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,f'Sensitivity preview failed: {e}')
    return storage.put('sensitivity',uuid.uuid4().hex[:12],result)

@app.get('/api/sensitivity/{id}/json')
def sensitivity_json(id:str):
    return Response(json.dumps(saved(id,'sensitivity'),indent=2),media_type='application/json',
                    headers={'Content-Disposition':f'attachment; filename="rlc_sensitivity_{id}.json"'})

@app.post('/api/runs/{id}/setup-transitions')
def setup_transitions(id:str,request:SetupTransitionRequest):
    target=saved(id,'run'); baseline=saved(request.baseline_run_id,'run')
    try: result=plan_transition(baseline,request.baseline_candidate_id,target)
    except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,f'Setup comparison failed: {e}')
    return storage.put('transition',uuid.uuid4().hex[:12],result)

@app.get('/api/setup-transitions/{id}/json')
def setup_transition_json(id:str):
    return Response(json.dumps(saved(id,'transition'),indent=2),media_type='application/json',
                    headers={'Content-Disposition':f'attachment; filename="setup_transition_{id}.json"'})

@app.get('/api/setup-transitions/{id}/report',response_class=HTMLResponse)
def setup_transition_report(id:str):return transition_report(saved(id,'transition'))

@app.get('/api/runs/{id}/report',response_class=HTMLResponse)
def report(id:str):return HTMLResponse(report_html(saved(id,'run')),headers={'Content-Disposition':f'inline; filename="ImpulseTwin-{id}.html"'})

@app.get('/api/runs/{id}/json')
def run_json(id:str):return Response(json.dumps(saved(id,'run'),indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="ImpulseTwin-{id}.json"'})

@app.get('/api/runs/{id}/demo-waveform')
def demo_waveform(id:str,candidate_id:str=''):
    run=saved(id,'run'); c=selected_candidate(run,candidate_id); pred=c['prediction']
    wave=waveform_from_metrics(pred[0]*1.045,pred[1]*.97,pred[2]*.985,run['inputs']['impulse_type'])
    stream=io.StringIO(); stream.write(f"# source_type=generated_stress_test; run_id={id}; candidate_id={c['id']}; time_unit=us; voltage_unit=kV; demo only, not measured lab data\n")
    writer=csv.writer(stream); writer.writerow(['time_us','voltage_kv']); writer.writerows(zip(wave['time_us'],wave['voltage_kv']))
    return Response(stream.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="generated_stress_test_trial.csv"'})

def predict_as_fired(run,candidate,as_fired):
    """Re-simulate the unchanged circuit at the settings actually fired.

    Uses the saved profile and request; no measured information enters the model.
    """
    from .physics.circuit import simulate as circuit_simulate
    inputs=run['inputs']; p=run['profile']; s=candidate['settings']
    settings={k:as_fired.get(k,s[k]) for k in ['stages','charge_kv_stage','front_r_stage','tail_r_stage']}
    circuit={k:as_fired.get(k,inputs[k]) for k in ['load_c_pf','divider_c_pf','stray_c_pf','l_uh']}
    if not p['min_stages']<=settings['stages']<=p['max_stages']:raise ValueError('As-fired stage count is outside the generator profile.')
    if min(settings['charge_kv_stage'],settings['front_r_stage'],settings['tail_r_stage'],circuit['load_c_pf'])<=0 or min(circuit['divider_c_pf'],circuit['stray_c_pf'],circuit['l_uh'])<0:
        raise ValueError('As-fired values must be positive.')
    total=circuit['load_c_pf']+circuit['divider_c_pf']+circuit['stray_c_pf']+((p.get('base_c_pf') or 0) if inputs.get('include_base_c') else 0)
    result=circuit_simulate(settings['stages'],settings['charge_kv_stage'],settings['front_r_stage'],settings['tail_r_stage'],
        p['stage_c_uf'],total,circuit['l_uh'],inputs['efficiency'],inputs['impulse_type'],True)
    return {'settings':settings,'circuit_inputs':circuit,'changed_fields':sorted(as_fired),
            'prediction':{k:result[k] for k in ['front_us','tail_us','crest_kv']},'waveform':result['waveform'],
            'model':result['diagnostics']['model'],
            'note':'Circuit prediction recomputed at the as-fired settings with the unchanged model and assumptions; no measured data was used.'}

@app.post('/api/trials/upload')
async def upload_trial(file:UploadFile=File(...),run_id:str=Form(...),candidate_id:str=Form(''),
    time_column:str=Form('time_us'),voltage_column:str=Form('voltage_kv'),time_unit:str=Form('us'),
    voltage_unit:str=Form('kV'),baseline_kv:float=Form(0),source_type:str=Form('generated_stress_test'),time_origin_us:float=Form(0),
    captured_at:str|None=Form(None),measurement_instrument:str|None=Form(None),operator_notes:str|None=Form(None),
    capture_purpose:str=Form('unspecified'),voltage_scale:float=Form(1.0),voltage_scale_source:str|None=Form(None),
    expected_polarity:str=Form('auto'),session_id:str|None=Form(None),shot_label:str|None=Form(None),
    as_fired_stages:int|None=Form(None),as_fired_charge_kv_stage:float|None=Form(None),
    as_fired_front_r_stage:float|None=Form(None),as_fired_tail_r_stage:float|None=Form(None),
    as_fired_load_c_pf:float|None=Form(None),as_fired_divider_c_pf:float|None=Form(None),
    as_fired_stray_c_pf:float|None=Form(None),as_fired_l_uh:float|None=Form(None)):
    run=saved(run_id,'run'); candidate=selected_candidate(run,candidate_id)
    if capture_purpose not in ('validation','calibration','unspecified'):
        raise HTTPException(422,'Capture purpose must be validation (independent check, never used for correction), calibration or unspecified.')
    if not (np.isfinite(voltage_scale) and voltage_scale>0):raise HTTPException(422,'Voltage scale factor must be a positive finite number.')
    if voltage_scale!=1 and not (voltage_scale_source or '').strip():
        raise HTTPException(422,'Give the source of the voltage scale factor (for example the divider calibration certificate).')
    if expected_polarity not in ('auto','positive','negative'):raise HTTPException(422,'Expected polarity must be auto, positive or negative.')
    as_fired={k:v for k,v in {'stages':as_fired_stages,'charge_kv_stage':as_fired_charge_kv_stage,
        'front_r_stage':as_fired_front_r_stage,'tail_r_stage':as_fired_tail_r_stage,'load_c_pf':as_fired_load_c_pf,
        'divider_c_pf':as_fired_divider_c_pf,'stray_c_pf':as_fired_stray_c_pf,'l_uh':as_fired_l_uh}.items() if v is not None}
    if source_type not in SOURCES:raise HTTPException(422,'Source type must identify synthetic benchmark, generated demo or measured laboratory data.')
    if source_type=='generated_demo':source_type='generated_stress_test'
    if captured_at:
        try:datetime.fromisoformat(captured_at.replace('Z','+00:00'))
        except ValueError:raise HTTPException(422,'Capture time must be an ISO 8601 timestamp or omitted.')
    content=await file.read(5_000_001)
    if len(content)>5_000_000:raise HTTPException(413,'CSV exceeds the 5 MB upload limit.')
    try:
        text=content.decode('utf-8-sig')
        provenance=validate_csv_provenance(text,run_id,candidate['id'],time_unit,voltage_unit)
        embedded=provenance['embedded_metadata'].get('source_type')
        if embedded is not None and embedded not in SOURCES:raise ValueError('Unknown embedded source type; provenance needs review.')
        if embedded in ('generated_stress_test','generated_demo'):source_type='generated_stress_test'
        elif embedded=='synthetic_benchmark':source_type='synthetic_benchmark'
        df=pd.read_csv(io.StringIO(text),comment='#')
        ts={'us':1,'µs':1,'ms':1000,'s':1e6,'ns':.001}[time_unit]
        vs={'kV':1,'V':.001,'MV':1000}[voltage_unit]*voltage_scale
        t=df[time_column].to_numpy(float)*ts; v=df[voltage_column].to_numpy(float)*vs
        measured=analyze(t,v,run['inputs']['impulse_type'],baseline_kv,time_origin_us)
        limits=captured_limits(run)
    except (UnicodeError,ValueError,KeyError,TypeError) as e:raise HTTPException(422,f'CSV validation failed: {e}')
    quality=assess_waveform(t,v,measured,impulse_type=run['inputs']['impulse_type'],rules=run.get('rules',{}))
    detected='positive' if measured['polarity']>0 else 'negative'
    if expected_polarity!='auto' and expected_polarity!=detected:
        quality={**quality,'calibration_allowed':False,'issues':[*quality['issues'],{'code':'polarity_mismatch','message':
            f'The capture is {detected} but the operator expected {expected_polarity}. Check divider polarity and channel wiring; the waveform was not flipped to hide this.'}]}
    try: as_fired_prediction=predict_as_fired(run,candidate,as_fired) if as_fired else None
    except (ValueError,KeyError) as e:raise HTTPException(422,f'As-fired settings could not be simulated: {e}')
    id=uuid.uuid4().hex[:12]; path=ROOT/'artifacts/trials'/f'{id}.csv'; path.parent.mkdir(exist_ok=True,parents=True); path.write_bytes(content)
    bias=[measured[k]-candidate['hybrid'][k] for k in ['front_us','tail_us','crest_kv']]
    calibration_bias,lineage=trial_correction(measured,candidate)
    result={'run_id':run_id,'candidate_id':candidate['id'],'source_type':source_type,'original_filename':file.filename,
        'raw_sha256':hashlib.sha256(content).hexdigest(),'raw_path':str(path.relative_to(ROOT)),
        'provenance':provenance,
        'processing':{'time_column':time_column,'voltage_column':voltage_column,'time_unit':time_unit,'voltage_unit':voltage_unit,'baseline_kv':baseline_kv,'time_origin_us':time_origin_us,'polarity':measured['polarity'],'steps':['Units converted without changing raw file','Explicit baseline subtracted only for analysis','Polarity normalized for metric extraction','Linear interpolation at crossings']},
        'measured':measured,'predicted':candidate['hybrid'],'physics':candidate['physics'],'bias':bias,
        'calibration_bias':calibration_bias,'calibration_lineage':lineage,
        'quality':quality,
        'waveform':{'time_us':t.tolist(),'voltage_kv':v.tolist(),'kind':source_type},
        'comparison_waveform':{'time_us':(t-time_origin_us).tolist(),
            'voltage_kv':((v-baseline_kv)*measured['polarity']).tolist(),'kind':source_type,
            'note':'Positive magnitude after explicit baseline subtraction; time relative to entered physical onset. Original samples and raw file retained separately.'},
        'compliance':extracted_compliance([measured[k] for k in ['front_us','tail_us','crest_kv']],limits,quality)}
    result.update(captured_at=captured_at,measurement_instrument=measurement_instrument,operator_notes=operator_notes,
        capture_purpose=capture_purpose,session_id=session_id,shot_label=shot_label,
        instrument={'voltage_scale':voltage_scale,'voltage_scale_source':voltage_scale_source,
                    'expected_polarity':expected_polarity,'detected_polarity':detected,'time_unit':time_unit,'voltage_unit':voltage_unit,
                    'onset_us':time_origin_us,'baseline_kv':baseline_kv},
        as_fired=as_fired_prediction)
    result['processing']['steps']=[*result['processing']['steps'],
        *([f'Voltage multiplied by stated scale factor {voltage_scale:g} ({voltage_scale_source})'] if voltage_scale!=1 else [])]
    result['evidence']=evidence_record({**result,'id':id,'created_at':datetime.now(timezone.utc).isoformat()},run)
    return storage.put('trial',id,result)

@app.get('/api/trials')
def trials():return storage.list_records('trial',50)

@app.post('/api/evaluations')
def evaluate(request:TrialEvaluationRequest):
    try: result=evaluate_trials(request.trial_ids,storage.get,ROOT)
    except (ValueError,KeyError,TypeError) as e:raise HTTPException(422,f'Accuracy review failed: {e}')
    return storage.put('evaluation',uuid.uuid4().hex[:12],result)

@app.get('/api/evaluations')
def evaluations():return storage.list_records('evaluation',50)

@app.get('/api/evaluations/{id}/json')
def evaluation_json(id:str):
    return Response(json.dumps(saved(id,'evaluation'),indent=2),media_type='application/json',
                    headers={'Content-Disposition':f'attachment; filename="accuracy_review_{id}.json"'})

@app.post('/api/trials/{id}/calibrate')
def calibrate(id:str):
    trial=saved(id,'trial'); run=saved(trial['run_id'],'run'); c=selected_candidate(run,trial['candidate_id'])
    if trial.get('capture_purpose')=='validation':
        raise HTTPException(422,'This capture was recorded for independent validation. Validation captures are never used to correct predictions; upload a separate calibration capture.')
    classified=evidence_record(trial,run)['source_type']
    if classified not in ('generated_demo','measured_lab'):
        raise HTTPException(422,'Only explicitly classified trial waveforms can create a local correction.')
    raw=(ROOT/trial['raw_path']).resolve()
    if not raw.is_relative_to(ROOT.resolve()) or not raw.is_file() or hashlib.sha256(raw.read_bytes()).hexdigest()!=trial['raw_sha256']:
        raise HTTPException(422,'Original trial CSV is missing or changed. Restore its original bytes before calibration.')
    wave=trial.get('waveform') or {}
    quality=assess_waveform(wave.get('time_us'),wave.get('voltage_kv'),trial['measured'],
                            impulse_type=run['inputs']['impulse_type'],rules=run.get('rules',{}))
    if not quality['calibration_allowed']:
        raise HTTPException(422,'Capture review required: '+' '.join(item['message'] for item in quality['issues']))
    total_bias,lineage=trial_correction(trial['measured'],c)
    if any(abs(b)>abs(p)*.3 for b,p in zip(trial['bias'],c['prediction'])):
        raise HTTPException(422,'The shot differs by more than 30%. Review units, setup and waveform before local calibration.')
    if any(abs(b)>abs(p)*.3 for b,p in zip(total_bias,lineage['base_prediction'].values())):
        raise HTTPException(422,'The total correction differs from the original model by more than 30%. Review units, setup and waveform before local calibration.')
    scope={**{k:run['inputs'][k] for k in ['profile_id','impulse_type','layout_id','solver','model_mode','include_base_c','test_kv','load_c_pf','divider_c_pf','stray_c_pf','l_uh','efficiency']},
        'model_version':run['model_version'],
        'physics_version':'workbook-reference-v1' if run['inputs']['solver']=='reference' else c['physics']['diagnostics']['model'],
        'require_model_agreement':run['inputs'].get('require_model_agreement',False),
        'generator_profile':run['profile'],'rules_version':run['rules']['version'],
        'front_topology':c['front_network']['topology'],'tail_topology':c['tail_network']['topology'],
        **{k:c['settings'][k] for k in ['stages','front_r_stage','tail_r_stage','charge_kv_stage']}}
    # Preserve the existing demo-calibration label after provenance downgrades;
    # historical operator labels must never turn a generated source into measured evidence.
    calibration_source='generated_stress_test' if classified=='generated_demo' else classified
    return storage.put('calibration',uuid.uuid4().hex[:12],{'trial_id':id,'source_type':calibration_source,
        'bias':total_bias,'scope':scope,'production_model_changed':False,
        'observed_residual':trial['bias'],'calibration_lineage':lineage,'quality':quality,
        'retraining_queue':'Stored for later engineer-reviewed retraining; no automatic training',
        'limitation':'Applies only to same profile, layout, solver and hardware settings with inputs within 1%. Reduced-voltage transfer to a higher-voltage shot is not inferred.'})

@app.get('/api/documents/{name}')
def document(name:str):
    paths={'source_reconciliation':ROOT/'docs/source_reconciliation.md','data_audit':ROOT/'reports/data_audit.html','assumptions':ROOT/'docs/assumptions.md','accuracy_v2_results':ROOT/'docs/accuracy_v2_results.md','accuracy_v4_results':ROOT/'docs/accuracy_v4_results.md','accuracy_v5_results':ROOT/'docs/accuracy_v5_results.md','judging_criteria':ROOT/'docs/judging_criteria_evidence.md','capture_resolution':ROOT/'docs/capture_resolution_review.md','independent_simulation_results':ROOT/'docs/independent_simulation_results.md','trusted_waveform_data_search':ROOT/'docs/trusted_waveform_data_search.md','physics_audit':ROOT/'docs/physics_audit.md','laboratory_validation_checklist':ROOT/'docs/laboratory_validation_checklist.md','accuracy_report':ROOT/'docs/accuracy_report.md'}
    p=paths.get(name)
    if p is None or not p.exists():raise HTTPException(404,'Document not found')
    return FileResponse(p,media_type='text/html' if p.suffix=='.html' else 'text/plain')

if (ROOT/'frontend/out').exists():app.mount('/',StaticFiles(directory=ROOT/'frontend/out',html=True),name='frontend')
