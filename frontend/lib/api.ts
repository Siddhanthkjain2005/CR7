export type Data = Record<string, any>;
export const workbookInputs:Data = {profile_id:'workbook_reference_profile',impulse_type:'Lightning',test_kv:1425,load_c_pf:850,divider_c_pf:500,stray_c_pf:150,l_uh:18.5,efficiency:.82,solver:'reference',model_mode:'hybrid',require_model_agreement:false,connection_mode:'series_marx_equivalent',layout_id:'default-layout',uncertainty_pct:5,monte_carlo_samples:32,max_components_per_network:24,include_base_c:false};
// Physical reference first. Parasitics are editable example inputs; stock remains unknown.
export const initialInputs:Data = {...workbookInputs,profile_id:'cpri_problem_brief_profile',load_c_pf:650,divider_c_pf:250,stray_c_pf:55,l_uh:12,efficiency:.83,solver:'circuit',model_mode:'physics',include_base_c:true};
export const CUSTOM_PROFILE_ID='custom_generator';
/** Blank ratings for a custom generator: every value must be supplied by the operator. */
export const blankCustomProfile:Data={name:'',source:'',max_stages:null,min_stages:2,stage_kv:null,stage_c_uf:null,energy_stage_kj:null,energy_total_kj:null,voltage_max_kv:null,base_c_pf:0};
export function profileInputs(values:Data,profileId:string):Data {
  const workbook=profileId==='workbook_reference_profile';
  const custom=profileId===CUSTOM_PROFILE_ID;
  return {...values,profile_id:profileId,solver:workbook?'reference':'circuit',model_mode:workbook?'hybrid':'physics',include_base_c:!workbook,require_model_agreement:false,inventory_override:null,calibration_id:null,confirm_reference_mismatch:false,custom_profile:custom?{...blankCustomProfile,...(values.custom_profile||{})}:null};
}
/** Missing custom-generator fields, in plain words (empty when complete). */
export function customProfileGaps(p:Data|null|undefined):string[]{
  if(!p)return ['ratings'];
  const need:[string,string][]=[['name','name'],['source','source of the ratings'],['max_stages','available stages'],['stage_kv','stage voltage rating'],['stage_c_uf','stage capacitance'],['energy_stage_kj','stage energy rating'],['energy_total_kj','total energy rating']];
  return need.filter(([k])=>p[k]===null||p[k]===undefined||p[k]===''||(typeof p[k]==='number'&&!(p[k]>0))).map(([,label])=>label);
}
/** A display profile for the custom generator, mirroring the backend record. */
export function customProfileView(p:Data|null|undefined):Data|null{
  if(!p)return null;
  return {id:CUSTOM_PROFILE_ID,name:p.name?`Custom generator — ${p.name}`:'Custom generator',source:p.source||'Operator-supplied ratings',kind:'custom_hardware',
    max_stages:p.max_stages,min_stages:p.min_stages??2,stage_kv:p.stage_kv,stage_c_uf:p.stage_c_uf,energy_stage_kj:p.energy_stage_kj,energy_total_kj:p.energy_total_kj,
    voltage_min_kv:1,voltage_max_kv:p.voltage_max_kv??(isNum(p.max_stages)&&isNum(p.stage_kv)?p.max_stages*p.stage_kv:null),base_c_pf:p.base_c_pf??0,
    units_per_value_per_stage:null,enabled:true,front_values:[],lightning_tail_values:[],switching_tail_values:[]};
}
export function solverInputs(values:Data,solver:string):Data {
  return {...values,solver,model_mode:solver==='circuit'||values.profile_id!=='workbook_reference_profile'?'physics':values.model_mode,require_model_agreement:solver==='reference'&&!!values.require_model_agreement};
}
export function apiUrl(path:string) { return `${typeof window !== 'undefined' && window.location.port==='3000' ? 'http://127.0.0.1:8000' : ''}${path}`; }
export async function api(path:string, options:RequestInit={}) {const res=await fetch(apiUrl(path),{...options,headers:{...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}),...options.headers}});if(!res.ok){let body;try{body=await res.json()}catch{throw new Error(`Service returned ${res.status}. Check the local backend.`)} const d=body.detail;throw new Error(typeof d==='string'?d:Array.isArray(d)?d.map((e:Data)=>`${e.loc?.slice(1).join('.')}: ${e.msg}`).join('; '):`Request failed (${res.status})`)}return res.json();}
export const post=(path:string,body:unknown)=>api(path,{method:'POST',body:JSON.stringify(body)});
export const fmt=(v:unknown,digits=2)=>typeof v==='number'&&Number.isFinite(v)?(Number(v.toFixed(digits))===0?0:v).toLocaleString('en-US',{maximumFractionDigits:digits,minimumFractionDigits:digits}):'—';
export const human=(s:string)=>s?.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());

/** True when a value is a finite number (zero included); null/undefined/NaN stay "missing". */
export const isNum=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v);

/** Signed, fixed-precision text such as "+1.25". Missing values stay an em dash. */
export function signed(v:unknown,digits=2){
  if(!isNum(v))return '—';
  const text=fmt(v,digits);
  return Number(v.toFixed(digits))>0?`+${text}`:text;
}

/** Order-independent serialization used to compare a draft request with the saved run inputs. */
export function stableKey(value:unknown):string{
  if(value===undefined)return 'null';
  if(value===null||typeof value!=='object')return JSON.stringify(value);
  if(Array.isArray(value))return `[${value.map(stableKey).join(',')}]`;
  const entries=Object.entries(value as Data).filter(([,v])=>v!==undefined).sort(([a],[b])=>a<b?-1:a>b?1:0);
  return `{${entries.map(([k,v])=>`${JSON.stringify(k)}:${stableKey(v)}`).join(',')}}`;
}

/** Normalizes optional request fields so that "absent" and null compare equal. */
export function requestKey(values:Data|null|undefined):string{
  if(!values)return '';
  const optional=['stage_min','stage_max','inventory_override','equipment_reference_kv','test_object_id','equipment_reference_source','calibration_id','custom_profile'];
  const normalized:Data={confirm_reference_mismatch:false,...values};
  optional.forEach(k=>{if(normalized[k]===undefined||normalized[k]==='')normalized[k]=null});
  return stableKey(normalized);
}

/** Deterministic timestamp text for saved records (rendered client-side only). */
export function stamp(iso:unknown){
  if(typeof iso!=='string')return 'Not recorded';
  const d=new Date(iso);
  if(Number.isNaN(d.getTime()))return 'Not recorded';
  return d.toLocaleString('en-GB',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'});
}

/** Relative age of a saved record; callers pass the current time explicitly. */
export function age(iso:unknown,now:number){
  if(typeof iso!=='string')return '';
  const t=new Date(iso).getTime();
  if(!Number.isFinite(t))return '';
  const s=Math.max(0,Math.round((now-t)/1000));
  if(s<45)return 'just now';
  const m=Math.round(s/60);
  if(m<60)return `${m} min ago`;
  const h=Math.round(m/60);
  if(h<36)return `${h} h ago`;
  return `${Math.round(h/24)} d ago`;
}

export const shortId=(id:unknown)=>typeof id==='string'?id.slice(0,8):'—';
