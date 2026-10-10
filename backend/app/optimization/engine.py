from pathlib import Path
from itertools import product
import json
import math
import numpy as np
from scipy.stats import qmc
from scipy.optimize import brentq
from ..schemas import OptimizeRequest, GeneratorProfile
from ..data.workbook_reference import predict
from ..physics.circuit import simulate, VERSION as CIRCUIT_VERSION
from ..physics.waveform_metrics import waveform_from_metrics
from ..physics.compliance import check, RULES
from ..ml.registry import infer
from .networks import nearest_networks
from .verification import verify_settings
from ..test_objects import validate_request
from ..evidence import recommendation_evidence
from ..physics.consistency import waveform_consistency

ROOT=Path(__file__).resolve().parents[3]
PROFILES=[GeneratorProfile.model_validate(p).model_dump() for p in json.loads((ROOT/'config/generator_profiles.json').read_text(encoding="utf-8"))]
METRIC_KEYS=('front_us','tail_us','crest_kv')
WEIGHTS=json.loads((ROOT/'config/optimization.json').read_text(encoding="utf-8"))

def profile_for(pid):
    for p in PROFILES:
        if p['id']==pid: return p
    raise ValueError('Unknown generator profile.')

CUSTOM_ID='custom_generator'

def custom_profile(req):
    """Profile record for operator-supplied hardware of the same supported topology."""
    c=req.custom_profile; inv=req.inventory_override
    tails=sorted({i.ohm for i in inv.tail})
    record={'id':CUSTOM_ID,'name':f'Custom generator — {c.name}','version':'custom-1','source':c.source,
        'kind':'custom_hardware','voltage_min_kv':c.voltage_min_kv,
        'voltage_max_kv':c.voltage_max_kv if c.voltage_max_kv is not None else c.max_stages*c.stage_kv,
        'min_stages':c.min_stages,'max_stages':c.max_stages,'stage_kv':c.stage_kv,'stage_c_uf':c.stage_c_uf,
        'energy_stage_kj':c.energy_stage_kj,'energy_total_kj':c.energy_total_kj,
        'energy_provenance':'Operator-supplied rating: '+c.source,
        'front_values':sorted({i.ohm for i in inv.front}),'lightning_tail_values':tails,'switching_tail_values':tails,
        'units_per_value_per_stage':None,'base_c_pf':c.base_c_pf,'enabled':True,
        'notes':['Operator-supplied ratings for a series Marx equivalent. Other circuit topologies are not supported.',
                 'Workbook residual ML is not validated for this hardware; circuit prediction only.']}
    return GeneratorProfile.model_validate(record).model_dump()

DISPLAY_ONLY=('name','notes')

def same_hardware(saved,current):
    """Profiles match when every rating and value matches; display names may change."""
    if not isinstance(saved,dict) or not isinstance(current,dict): return False
    strip=lambda p:{k:v for k,v in p.items() if k not in DISPLAY_ONLY}
    return strip(saved)==strip(current)

def resolve_profile(req):
    return custom_profile(req) if req.profile_id==CUSTOM_ID else profile_for(req.profile_id)

def stock_for(req,p):
    if req.inventory_override:
        def stock(items):
            if len({i.ohm for i in items})!=len(items): raise ValueError('Inventory contains duplicate resistance values; consolidate their counts.')
            if len(items)>15: raise ValueError('At most 15 distinct resistance values per inventory.')
            return {i.ohm:i.count_per_stage for i in items}
        return stock(req.inventory_override.front),stock(req.inventory_override.tail),req.inventory_override.provenance
    count=p['units_per_value_per_stage']
    if count is None: raise ValueError('This hardware source gives resistor values but no stock quantities. Enter an explicit inventory with counts and provenance.')
    tails=p['lightning_tail_values'] if req.impulse_type=='Lightning' else p['switching_tail_values']
    return {r:count for r in p['front_values']},{r:count for r in tails},p['source']

def physics(req,p,n,charge,rf,rt,include_waveform=False):
    stray=req.stray_c_pf+(p['base_c_pf'] or 0 if req.include_base_c else 0)
    if req.solver=='reference':
        return predict(n,charge,rf,rt,req.load_c_pf,req.divider_c_pf,stray,req.l_uh,req.efficiency,p['stage_c_uf'])
    # Effective generator parameters fitted from calibration shots (circuit only).
    fitted=p.get('effective_parameters') or {}
    return simulate(n,charge,rf,rt*fitted.get('tail_scale',1.),p['stage_c_uf'],
        req.load_c_pf+req.divider_c_pf+stray+fitted.get('extra_load_pf',0.),req.l_uh,
        req.efficiency*fitted.get('loss_scale',1.),req.impulse_type,include_waveform)

def parameter_scope_matches(record,req,p):
    scope=record.get('scope',{})
    return (same_hardware(scope.get('generator_profile'),p) and scope.get('impulse_type')==req.impulse_type
            and scope.get('layout_id')==req.layout_id and scope.get('include_base_c')==req.include_base_c
            and scope.get('physics_version')==CIRCUIT_VERSION and req.solver=='circuit')

def ml_row(req,settings,phys):
    return {'Impulse_Type':req.impulse_type,'Test_kV':req.test_kv,'Load_C_pF':req.load_c_pf,
       'Divider_C_pF':req.divider_c_pf,'Stray_C_pF':req.stray_c_pf,'L_uH':req.l_uh,'Efficiency':req.efficiency,
       'Stages':settings['stages'],'Charge_kV_Stage':settings['charge_kv_stage'],
       'Front_R_Stage':settings['front_r_stage'],'Tail_R_Stage':settings['tail_r_stage'],
       'Physics_FrontPeak_us':phys['front_us'],'Physics_Tail_us':phys['tail_us'],'Physics_Crest_kV':phys['crest_kv']}

def score_candidate(c):
    rows=c['compliance']['rows']; normalized=[abs(r['predicted']-r['target'])/((r['upper']-r['lower'])/2) for r in rows]
    agreement=c.get('model_agreement')
    if agreement and agreement['required']:
        other=c['circuit_crosscheck']['compliance']['rows']
        normalized=[max(value,abs(r['predicted']-r['target'])/((r['upper']-r['lower'])/2)) for value,r in zip(normalized,other)]
    count=c['front_network']['count_per_stage']+c['tail_network']['count_per_stage']
    terms={'front_deviation':normalized[0]*WEIGHTS['front_deviation'],'tail_deviation':normalized[1]*WEIGHTS['tail_deviation'],
       'crest_deviation':normalized[2]*WEIGHTS['crest_deviation'],'setup_complexity':WEIGHTS['component_count']*count*c['settings']['stages'],
       'ood_penalty':WEIGHTS['ood_penalty']*(1-c['ood']['trust_weight']),
       'operating_margin_penalty':WEIGHTS['stage_utilization_penalty']*c['settings']['stage_utilization'],
       'uncertainty_penalty':WEIGHTS['uncertainty_penalty']*sum(h/max(r['upper']-r['lower'],1e-9) for h,r in zip(c['uncertainty']['halfwidth'],rows))}
    c['score_breakdown']=terms; c['score']=sum(terms.values()); c['accuracy_cost']=sum(normalized)
    c['setup_component_count']=count*c['settings']['stages']
    return (not (agreement['both_nominal_pass'] if agreement and agreement['required'] else c['compliance']['nominal_pass']),c['score'])

def agreement_for(c):
    checks=[c['compliance'],c['circuit_crosscheck']['compliance']]
    q=c['settings']['charge_kv_stage']
    lower,upper=checks[0]['rows'][2]['lower'],checks[0]['rows'][2]['upper']
    gains=[c['physics']['crest_kv']/q,c['circuit_crosscheck']['crest_kv']/q]
    windows=[[lower/gain,upper/gain] for gain in gains]
    return {'required':True,'both_nominal_pass':all(x['nominal_pass'] for x in checks),
        'reference_nominal_pass':checks[0]['nominal_pass'],'circuit_nominal_pass':checks[1]['nominal_pass'],
        'worst_tolerance_fraction':max(abs(r['predicted']-r['target'])/((r['upper']-r['lower'])/2) for x in checks for r in x['rows']),
        'raw_crest_charge_windows':{'reference_kv_stage':windows[0],'circuit_kv_stage':windows[1],
            'overlap':max(w[0] for w in windows)<=min(w[1] for w in windows),
            'scope':'Raw-model charge ranges at this fixed resistor network, before stage/energy caps or local correction. Disjoint ranges cannot be repaired by charge adjustment alone.'},
        'scope':'Agreement of two unvalidated models at the same hardware settings; not measured accuracy or laboratory compliance.'}

def final_rank(c):
    agreement=c.get('model_agreement')
    if agreement and agreement['required']:
        return (not agreement['both_nominal_pass'],
            -(agreement.get('sampled_both_pass_pct',0)),not c['compliance']['robust_pass'],c['score'])
    return (not c['compliance']['nominal_pass'],not c['compliance']['robust_pass'],c['score'])

def optimize(req:OptimizeRequest,calibration=None,*,parameter_calibration=None,_benchmark_networks=None,_network_selector=None):
    p=resolve_profile(req)
    parameter_review=None
    if parameter_calibration is not None:
        if not parameter_scope_matches(parameter_calibration,req,p):
            raise ValueError('The fitted generator parameters belong to a different generator, impulse type, layout, base-capacitance choice or model version. No recommendation generated.')
        p={**p,'effective_parameters':{**parameter_calibration['parameters'],'calibration_id':parameter_calibration.get('id'),
            'shots':parameter_calibration['fit']['shots'],'source_type':parameter_calibration.get('source_type')}}
        parameter_review={'id':parameter_calibration.get('id'),'parameters':parameter_calibration['parameters'],
            'shots':parameter_calibration['fit']['shots'],'source_type':parameter_calibration.get('source_type'),
            'fit_residual_pct':parameter_calibration['fit']['residual_pct'],
            'note':'Circuit predictions use generator parameters fitted from calibration shots: extra loss, extra load-side capacitance and effective tail resistance. They apply to every setting of this generator, impulse type and layout.'}
    reference_review=validate_request(req,p)
    if reference_review['confirmation_required']:
        raise ValueError(reference_review['message'])
    if not p['enabled']: raise ValueError('Profile is incomplete. Verified capacitance, energy and inventory are required.')
    if not p['voltage_min_kv']<=req.test_kv<=p['voltage_max_kv']:
        raise ValueError(f"Requested {req.test_kv:g} kV is outside {p['voltage_min_kv']:g}–{p['voltage_max_kv']:g} kV for this profile. No recommendation generated.")
    front_stock,tail_stock,inventory_source=stock_for(req,p)
    if not any(front_stock.values()) or not any(tail_stock.values()):
        raise ValueError('No constructible network: front or tail inventory is empty.')
    rule=RULES[req.impulse_type]; min_n=max(p['min_stages'],req.stage_min or p['min_stages'])
    max_n=min(p['max_stages'],req.stage_max or p['max_stages'])
    if req.stage_min and req.stage_min>p['max_stages']: raise ValueError('Requested stage constraint exceeds profile capacity.')
    candidates=[]; rejected={'stage_voltage_or_energy':0,'nonfinite_or_invalid_waveform':0}; examined=0
    c2=(req.load_c_pf+req.divider_c_pf+req.stray_c_pf+((p['base_c_pf'] or 0) if req.include_base_c else 0))*1e-12
    for n in range(min_n,max_n+1):
        charge=req.test_kv/(req.efficiency*n)
        # Reference crest is n × charge × efficiency. In the circuit, passive
        # underdamped charge transfer may raise load crest above the initial
        # generator voltage, so this estimate cannot reject a circuit stage count.
        # Actual solved charge and both energy ratings are filtered below.
        if req.solver=='reference' and charge>p['stage_kv']:
            rejected['stage_voltage_or_energy']+=1; continue
        rf_target=math.sqrt(max(1e-18,(rule['front_target_us']/1e6/1.67)**2-2.5*req.l_uh*1e-6*c2))/c2/n
        if req.solver=='circuit':
            rf_target=rule['front_target_us']/1e6/(3.2*c2*n) if req.impulse_type=='Lightning' else rf_target*.25
        rt_target=rule['tail_target_us']/1e6/(.693*(p['stage_c_uf']*1e-6/n+c2))/n
        if req.solver=='circuit':
            # Continuous targeting only locates useful discrete stock networks.
            # These values are never emitted as constructible recommendations.
            # Iterate because front and tail resistors both influence both times.
            for _ in range(2):
                try:
                    rf_target=math.exp(brentq(lambda lr:physics(req,p,n,charge,math.exp(lr),rt_target)['front_us']-rule['front_target_us'],math.log(max(rf_target*.15,.01)),math.log(rf_target*5),xtol=1e-5))
                except ValueError: pass
                try:
                    rt_target=math.exp(brentq(lambda lr:physics(req,p,n,charge,rf_target,math.exp(lr))['tail_us']-rule['tail_target_us'],math.log(max(rt_target*.3,.01)),math.log(rt_target*3),xtol=1e-5))
                except ValueError: pass
        provider=_benchmark_networks or nearest_networks
        fronts=provider(front_stock,rf_target,req.max_components_per_network,5)
        tails=provider(tail_stock,rt_target,req.max_components_per_network,5)
        if _network_selector is not None:
            # Evaluation hook: an alternative shortlist (e.g. exhaustive or surrogate
            # screened) of constructible networks. Every pair is still circuit-solved.
            fronts,tails=_network_selector(req,p,n,charge,front_stock,tail_stock,rf_target,rt_target)
        if req.require_model_agreement and _benchmark_networks is None:
            # Broaden the shortlist around both the reference front and shorter
            # circuit front; every emitted value still comes from counted stock.
            def neighborhood(stock,target,factors):
                found={}
                for factor in factors:
                    for item in nearest_networks(stock,target*factor,req.max_components_per_network,5):
                        found[round(item['equivalent_ohm'],8)]=item
                return list(found.values())
            fronts=neighborhood(front_stock,rf_target,[.6,.7,.8,.9,1.])
            tails=neighborhood(tail_stock,rt_target,[.8,.9,1.,1.1])
        for fn,tn in product(fronts,tails):
            examined+=1; rf=fn['equivalent_ohm']; rt=tn['equivalent_ohm']; q=charge
            try:
                ph=physics(req,p,n,q,rf,rt)
                cross=None
                if req.require_model_agreement:
                    cross=simulate(n,q,rf,rt,p['stage_c_uf'],c2*1e12,req.l_uh,req.efficiency,req.impulse_type,False)
                    # Both models are linear in charge. Equalize their opposite
                    # crest errors, clipped to actual voltage/energy headroom.
                    cap=min(p['stage_kv'],math.sqrt(2*p['energy_stage_kj']*1000/(p['stage_c_uf']*1e-6))/1000,
                            math.sqrt(2*p['energy_total_kj']*1000/(n*p['stage_c_uf']*1e-6))/1000)
                    new_q=min(cap,q*2*req.test_kv/(ph['crest_kv']+cross['crest_kv']))
                    scale=new_q/q;q=new_q
                    ph={**ph,'crest_kv':ph['crest_kv']*scale}
                    cross={**cross,'crest_kv':cross['crest_kv']*scale}
                    cross['compliance']=check(req.impulse_type,req.test_kv,cross)
                if req.solver=='circuit':
                    # This fixed linear RLC system is homogeneous in its initial
                    # charge voltage: crest scales, while times, eigenvalues and
                    # normalized energy diagnostics do not. Avoid a second solve.
                    q*=req.test_kv/ph['crest_kv']
                    ph={**ph,'crest_kv':req.test_kv}
                energy=n*.5*p['stage_c_uf']*1e-6*(q*1000)**2/1000
                if q>p['stage_kv']+1e-9 or energy>p['energy_total_kj']+1e-9 or energy/n>p['energy_stage_kj']+1e-9:
                    rejected['stage_voltage_or_energy']+=1; continue
                if not all(math.isfinite(ph[k]) and ph[k]>0 for k in ['front_us','tail_us','crest_kv']): raise ValueError('Nonfinite metric')
                settings={'stages':n,'charge_kv_stage':q,'front_r_stage':rf,'tail_r_stage':rt,
                   'stage_utilization':q/p['stage_kv'],'stored_energy_kj':energy,
                   'voltage_margin_kv_stage':p['stage_kv']-q,'energy_margin_kj':p['energy_total_kj']-energy,
                   'energy_margin_pct':100*(1-energy/p['energy_total_kj'])}
                def network(item):
                    return {**item,'total_components':item['count_per_stage']*n,
                        'components':[{**i,'total_required':i['count_per_stage']*n,'available_per_stage':(front_stock if item is fn else tail_stock)[i['ohm']]} for i in item['components']]}
                candidate={'id':f'c{len(candidates)+1}','settings':settings,'front_network':network(fn),'tail_network':network(tn),'physics':ph}
                if cross is not None:candidate['circuit_crosscheck']=cross
                candidates.append(candidate)
            except (ValueError,ArithmeticError,np.linalg.LinAlgError): rejected['nonfinite_or_invalid_waveform']+=1
    if not candidates: raise ValueError('No settings satisfy stage-voltage, stored-energy and inventory constraints. Lower requested crest, change the verified inventory, or review the selected profile.')
    mode=req.model_mode if req.solver=='reference' and not req.include_base_c else 'physics'
    ml=infer([ml_row(req,c['settings'],c['physics']) for c in candidates],p['id'],mode)
    for c,m in zip(candidates,ml):
        c.update(m); c['calibration']=None
        if calibration and calibration_matches(calibration,req,c):
            bias=np.array(calibration['bias']); pred=np.array(c['prediction'])+bias
            c['prediction']=pred.tolist(); c['uncertainty']['lower']=(np.array(c['uncertainty']['lower'])+bias).tolist(); c['uncertainty']['upper']=(np.array(c['uncertainty']['upper'])+bias).tolist()
            c['calibration']={'id':calibration['id'],'bias':bias.tolist(),'source_type':calibration['source_type'],'method':'Local additive correction from one shot; not production model retraining'}
            c['uncertainty']['coverage_claim']=None; c['uncertainty']['method']+='; one-shot calibration unvalidated'
            c['ood']['lab_calibrated']=calibration['source_type']=='measured_lab'
        c['hybrid']=dict(zip(['front_us','tail_us','crest_kv'],c['prediction']))
        c['compliance']=check(req.impulse_type,req.test_kv,c['hybrid'],c['uncertainty'])
        if req.require_model_agreement:c['model_agreement']=agreement_for(c)
        score_candidate(c)
    candidates.sort(key=score_candidate)
    selected=candidates[:] if _benchmark_networks is not None else candidates[:20 if req.require_model_agreement else 10]
    calibrated=[c for c in candidates if c.get('calibration')]
    # Always compute the corrected original setting for the trial workflow, even
    # if a different setting is ranked above it after feedback.
    for c in calibrated:
        if not any(s['id']==c['id'] for s in selected): selected.append(c)
    for c in selected:
        robustness(req,p,c,mode,calibration)
        score_candidate(c)
    selected.sort(key=final_rank)
    benchmark_ranking=[{'settings':c['settings'],'score':c['score'],'accuracy_cost':c['accuracy_cost'],
                        'setup_component_count':c['setup_component_count'], 'rank_key':final_rank(c)} for c in selected] if _benchmark_networks is not None else None
    selected=selected[:5]
    calibration_review=None
    if calibration:
        if calibrated:
            cc=calibrated[0]
            calibration_review={'id':calibration['id'],'applied':True,'matched_candidates':len(calibrated),
                'source_type':calibration['source_type'],'settings':cc['settings'],'physics':cc['physics'],
                'corrected_prediction':cc['hybrid'],'correction':cc['calibration']['bias'],
                'compliance':cc['compliance'],'uncertainty':cc['uncertainty'],
                'retained_in_top_five':any(c['id']==cc['id'] for c in selected),
                'next_adjustment_note':'Compare the corrected original setting to the ranked alternatives. Correction is not extrapolated to different resistor networks.'}
        else:
            calibration_review={'id':calibration['id'],'applied':False,'matched_candidates':0,
                'reason':'No candidate matches the saved profile, model, layout, settings and 1% input scope. No calibration correction was applied.'}
    for rank,c in enumerate(selected,1):
        c['rank']=rank; s=c['settings']
        c['explanation']=[f"{s['stages']} stages keep charging at {s['charge_kv_stage']:.2f} kV/stage, below the {p['stage_kv']:g} kV limit.",
            f"Every resistor is counted: {c['setup_component_count']} total parts across front and tail networks.",
            f"Ranking combines tolerance-normalized waveform error, component count, uncertainty and operating margin. Score {c['score']:.3f}; lower is better.",
            f"ML trust weight {c['ood']['trust_weight']:.2f}; {c['ood']['state'].replace('_',' ')}. No laboratory accuracy claim."]
        if rank==1 and len(selected)>1:
            runner=selected[1]
            order='both nominal model checks, then sampled agreement, then interval containment' if req.require_model_agreement else 'nominal compliance, then interval containment'
            c['explanation'].append(f"Rank 1 versus rank 2: {order}, then weighted cost ({c['score']:.4f} versus {runner['score']:.4f}). This setup uses {c['setup_component_count']} parts versus {runner['setup_component_count']}; lower cost can trade waveform deviation against complexity and headroom.")
        if req.require_model_agreement:
            c['explanation'][2]=f"Agreement search minimizes the worse waveform deviation across the workbook and independent circuit, using the same counted hardware. Score {c['score']:.3f}."
            c['explanation'].append('Both nominal model checks and sampled agreement are ranked before interval containment and weighted cost. Neither model has laboratory validation.')
        if req.solver=='reference':
            try:
                c['waveform']={**waveform_from_metrics(*c['prediction'],req.impulse_type),
                    'label':'Shape reconstructed from predicted metrics'}
                c['physics_waveform']={**waveform_from_metrics(c['physics']['front_us'],c['physics']['tail_us'],c['physics']['crest_kv'],req.impulse_type),
                    'label':'Shape reconstructed from workbook-equation metrics'}
            except ValueError: c['waveform']=None; c['physics_waveform']=None
            circuit=simulate(s['stages'],s['charge_kv_stage'],s['front_r_stage'],s['tail_r_stage'],p['stage_c_uf'],c2*1e12,req.l_uh,req.efficiency,req.impulse_type)
            c['circuit_crosscheck']={**circuit,'compliance':check(req.impulse_type,req.test_kv,circuit)}
        else:
            circuit=physics(req,p,s['stages'],s['charge_kv_stage'],s['front_r_stage'],s['tail_r_stage'],True)
            c['waveform']=circuit['waveform']; c['physics_waveform']=circuit['waveform']; c['circuit_crosscheck']=None
            # Report the metrics of the final solve at the recommended charge, i.e. of
            # the plotted curve itself, instead of the search-time crest assignment.
            final={k:v for k,v in circuit.items() if k!='waveform'}
            delta=np.array([final[k]-c['physics'][k] for k in METRIC_KEYS])
            c['physics']=final
            c['prediction']=(np.array(c['prediction'])+delta).tolist()
            c['uncertainty']['lower']=(np.array(c['uncertainty']['lower'])+delta).tolist()
            c['uncertainty']['upper']=(np.array(c['uncertainty']['upper'])+delta).tolist()
            c['hybrid']=dict(zip(METRIC_KEYS,c['prediction']))
            c['compliance']=check(req.impulse_type,req.test_kv,c['hybrid'],c['uncertainty'])
        c['waveform_consistency']=waveform_consistency(c,req.impulse_type,req.test_kv)
        c['verification']=verify_settings(req,p,c,mode,calibration)
        c['evidence']=recommendation_evidence(c)
        c['pareto_optimal']=not any(other is not c and other['accuracy_cost']<=c['accuracy_cost'] and other['setup_component_count']<=c['setup_component_count'] and other['settings']['stage_utilization']<=s['stage_utilization'] and (other['accuracy_cost']<c['accuracy_cost'] or other['setup_component_count']<c['setup_component_count']) for other in selected)
    warnings=['Decision support only. Engineer verification and laboratory procedures remain required.',
              'All trained models use supplied synthetic data. No measured laboratory validation has been completed.']
    if mode=='experimental_v2': warnings.append('Experimental V2 candidate: Train cross-validation development evidence only. No V2 Hidden Test or laboratory evaluation. Frozen V1 remains the default model.')
    if req.require_model_agreement:
        warnings.append('Agreement search checks two unvalidated models, not measured accuracy. Uncertainty and support limits remain active.')
        if not selected[0]['model_agreement']['both_nominal_pass']:
            warnings.append('No settings satisfying both nominal model checks were found in this bounded search. Results are diagnostic alternatives.')
    if req.solver=='reference': warnings.append('Reference formulas assert crest = n × charge × efficiency. Curves reconstruct predicted metrics; the independent circuit cross-check can disagree.')
    if any(c['ood']['trust_weight']<1 for c in selected): warnings.append('Some hardware settings lie outside training support. Their correction is reduced or disabled and intervals have no calibrated coverage claim.')
    if not selected[0]['compliance']['nominal_pass']: warnings.append('No nominally compliant candidate was found in the bounded search. Listed settings are diagnostic alternatives, not recommended passes.')
    return {'profile':p,'rules':RULES,'inputs':req.model_dump(),'model_version':ml[0]['model_version'],
        'candidates':selected,'target_waveform':{**waveform_from_metrics(rule['front_target_us'],rule['tail_target_us'],req.test_kv,req.impulse_type),
            'label':'Target shape','note':'Double-exponential shape through the requested challenge targets; a reference, not a prediction.'},
        'search':{'evaluated':examined,'hardware_feasible':len(candidates),'rejected':rejected,
            'agreement_feasible':sum(c.get('model_agreement',{}).get('both_nominal_pass',False) for c in candidates) if req.require_model_agreement else None,
            'search_kind':'Bounded stock network search across five front and four tail target neighborhoods; raw workbook/circuit crest balancing; 20-candidate scenario shortlist, not global optimization.' if req.require_model_agreement else 'Bounded series DP + four-part series/parallel trees (six parts for small catalogs) and identical parallel banks; nearest five front/tail choices per stage, not exhaustive global optimization.'},
        'inventory_provenance':inventory_source,'warnings':warnings,'source_type':'model_prediction',
        'ranking_config':{**WEIGHTS,'ranking_order':['Both nominal model checks','Sampled agreement among shortlisted candidates','Reference interval containment','Weighted objective using worse model deviations']} if req.require_model_agreement else WEIGHTS,
        'calibration_review':calibration_review,'test_object_review':reference_review,
        'parameter_calibration_review':parameter_review,
        **({'benchmark_ranking':benchmark_ranking} if benchmark_ranking is not None else {})}

def calibration_matches(cal,req,c):
    scope=cal['scope']; s=c['settings']
    return (same_hardware(scope.get('generator_profile'),resolve_profile(req))
        and scope.get('physics_version','workbook-reference-v1' if req.solver=='reference' else 'lumped RLC Marx equivalent v1')==('workbook-reference-v1' if req.solver=='reference' else CIRCUIT_VERSION)
        and scope.get('rules_version')==RULES['version']
        and scope.get('front_topology')==c['front_network']['topology']
        and scope.get('tail_topology')==c['tail_network']['topology']
        and scope.get('model_version')==c['model_version']
        and scope.get('require_model_agreement',False)==req.require_model_agreement
        and all(scope.get(k)==getattr(req,k) for k in ['profile_id','impulse_type','layout_id','solver','model_mode','include_base_c'])
        and all(abs(scope[k]-getattr(req,k))<=max(abs(scope[k])*.01,1e-8) for k in ['test_kv','load_c_pf','divider_c_pf','stray_c_pf','l_uh','efficiency'])
        and all(abs(scope[k]-s[k])<1e-8 for k in ['stages','front_r_stage','tail_r_stage','charge_kv_stage']))

def robustness(req,p,c,mode,calibration=None):
    keys=['load_c_pf','divider_c_pf','stray_c_pf','l_uh']; s=c['settings']
    samples=qmc.LatinHypercube(d=4,seed=73).random(req.monte_carlo_samples)
    variations=[]; phys=[]; rows=[]
    for sample in samples:
        change={k:getattr(req,k)*(1+(2*u-1)*req.uncertainty_pct/100) for k,u in zip(keys,sample)}
        r=req.model_copy(update=change); ph=physics(r,p,s['stages'],s['charge_kv_stage'],s['front_r_stage'],s['tail_r_stage'])
        rows.append(ml_row(r,s,ph)); phys.append(ph); variations.append(r)
    predictions=infer(rows,p['id'],mode)
    calibrated_samples=[bool(c.get('calibration') and calibration and calibration_matches(calibration,r,c)) for r in variations]
    bias=np.array([c['calibration']['bias'] if matched else [0.,0.,0.] for matched in calibrated_samples])
    values=np.array([r['prediction'] for r in predictions])+bias
    lows=np.array([r['uncertainty']['lower'] for r in predictions])+bias
    highs=np.array([r['uncertainty']['upper'] for r in predictions])+bias
    c['uncertainty']['lower']=np.minimum(lows.min(axis=0),c['uncertainty']['lower']).tolist()
    c['uncertainty']['upper']=np.maximum(highs.max(axis=0),c['uncertainty']['upper']).tolist()
    if any(r['ood']['trust_weight']<1 for r in predictions):
        c['uncertainty']['coverage_claim']=None
        c['uncertainty']['method']='Combined scenario envelopes include unsupported settings; no calibrated coverage guarantee'
    if c.get('calibration'):
        c['uncertainty']['coverage_claim']=None
        c['uncertainty']['method']+='; one-shot correction applied only inside its saved 1% input scope'
    c['uncertainty']['halfwidth']=np.maximum(np.array(c['prediction'])-c['uncertainty']['lower'],np.array(c['uncertainty']['upper'])-c['prediction']).tolist()
    passed=[check(req.impulse_type,req.test_kv,dict(zip(['front_us','tail_us','crest_kv'],v)))['nominal_pass'] for v in values]
    if req.require_model_agreement:
        cross_pass=[]
        for r in variations:
            stray=r.stray_c_pf+((p['base_c_pf'] or 0) if r.include_base_c else 0)
            cross=simulate(s['stages'],s['charge_kv_stage'],s['front_r_stage'],s['tail_r_stage'],p['stage_c_uf'],
                           r.load_c_pf+r.divider_c_pf+stray,r.l_uh,r.efficiency,r.impulse_type,False)
            cross_pass.append(check(r.impulse_type,r.test_kv,cross)['nominal_pass'])
        c['model_agreement'].update(sampled_both_pass_pct=float(np.mean(np.array(passed)&np.array(cross_pass))*100),
            sampled_circuit_pass_pct=float(np.mean(cross_pass)*100),scenario_count=len(variations),
            scenario_note='Finite independent parasitic scenarios, not a calibrated probability or proof over continuous ranges.')
    c['compliance']=check(req.impulse_type,req.test_kv,c['hybrid'],c['uncertainty'])
    nominal=np.array([c['physics'][k] for k in ['front_us','tail_us','crest_kv']]); sensitivity={}
    for k in keys:
        r=req.model_copy(update={k:getattr(req,k)*1.05})
        ph=physics(r,p,s['stages'],s['charge_kv_stage'],s['front_r_stage'],s['tail_r_stage'])
        sensitivity[k]=float(np.max(abs(np.array([ph[x] for x in ['front_us','tail_us','crest_kv']])/nominal-1))*100)
    c['robustness']={'samples':len(samples),'seed':73,'method':'Latin hypercube; independent uniform parasitic ranges',
        'calibrated_scenarios':sum(calibrated_samples),
        'outside_calibration_scope_scenarios':len(samples)-sum(calibrated_samples) if c.get('calibration') else None,
        'uncertainty_pct':req.uncertainty_pct,'parameters':keys,'nominal_scenario_pass_pct':float(np.mean(passed)*100),
        'note':'Scenario fraction under stated assumptions, not probability of laboratory success. Intervals include finite sampled extremes; not a proof over continuous bounds.',
        'minimum':values.min(axis=0).tolist(),'maximum':values.max(axis=0).tolist(),
        'sensitivity_5pct':sensitivity,'most_sensitive_parameter':max(sensitivity,key=sensitivity.get)}
