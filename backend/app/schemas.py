from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

class TrialEvaluationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    trial_ids:list[str]=Field(min_length=3,max_length=100)

class SetupTransitionRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    baseline_run_id:str=Field(min_length=1,max_length=128)
    baseline_candidate_id:str=Field(min_length=1,max_length=128)

class SensitivityRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    parameter:Literal['front_r_stage','tail_r_stage','load_c_pf','divider_c_pf','stray_c_pf','l_uh']='load_c_pf'
    change_pct:float=Field(default=10,ge=-30,le=30)

class StockItem(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    ohm:float=Field(gt=0,le=1e7)
    count_per_stage:int=Field(ge=0,le=40)

class ParameterCalibrationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    trial_ids:list[str]=Field(min_length=1,max_length=10)

class CaptureReviewRequest(BaseModel):
    """A qualified reviewer's recorded decision on a saved capture (append-only)."""
    model_config=ConfigDict(extra='forbid')
    decision:Literal['accept_flags','exclude','reinstate']
    codes:list[str]=Field(default_factory=list,max_length=20)
    reviewer:str=Field(min_length=2,max_length=120)
    reason:str=Field(min_length=10,max_length=1000)

class InventoryOverride(BaseModel):
    front:list[StockItem]
    tail:list[StockItem]
    provenance:str=Field(min_length=3,max_length=300)

class CustomGeneratorProfile(BaseModel):
    """Complete hardware for a generator of the same series-Marx equivalent topology.

    Only validated ratings are accepted. Resistor values and counts come from the
    explicit inventory; no other circuit topology is implied.
    """
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    name:str=Field(min_length=2,max_length=80)
    source:str=Field(min_length=3,max_length=300)
    max_stages:int=Field(ge=2,le=30)
    min_stages:int=Field(default=2,ge=2,le=30)
    stage_kv:float=Field(gt=0,le=1000)
    stage_c_uf:float=Field(gt=0,le=100)
    energy_stage_kj:float=Field(gt=0,le=10000)
    energy_total_kj:float=Field(gt=0,le=100000)
    voltage_min_kv:float=Field(default=1,gt=0,le=10000)
    voltage_max_kv:float|None=Field(default=None,gt=0,le=10000)
    base_c_pf:float=Field(default=0,ge=0,le=100000)
    @model_validator(mode='after')
    def consistent_ratings(self):
        if self.min_stages>self.max_stages: raise ValueError('Custom generator minimum stages exceed maximum stages.')
        stored=.5*self.stage_c_uf*1e-6*(self.stage_kv*1000)**2/1000
        if self.energy_stage_kj>stored*1.000001:
            raise ValueError(f'Stage energy rating {self.energy_stage_kj:g} kJ exceeds 0.5·C·V² = {stored:.4g} kJ at the stated stage voltage and capacitance; check units.')
        if self.energy_total_kj>self.max_stages*self.energy_stage_kj*1.000001:
            raise ValueError('Total energy rating exceeds the number of stages times the stage rating.')
        if self.voltage_max_kv is not None and self.voltage_max_kv>self.max_stages*self.stage_kv*1.000001:
            raise ValueError('Maximum output voltage exceeds the erected charging voltage of all stages.')
        if self.voltage_max_kv is not None and self.voltage_min_kv>self.voltage_max_kv:
            raise ValueError('Custom generator minimum voltage exceeds its maximum voltage.')
        return self

class OptimizeRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    profile_id:str='workbook_reference_profile'
    impulse_type:Literal['Lightning','Switching']='Lightning'
    test_kv:float=Field(default=1425,gt=0,le=10000)
    load_c_pf:float=Field(default=850,gt=0,le=100000)
    divider_c_pf:float=Field(default=500,ge=0,le=100000)
    stray_c_pf:float=Field(default=150,ge=0,le=100000)
    l_uh:float=Field(default=18.5,ge=0,le=10000)
    efficiency:float=Field(default=.82,gt=.05,le=1)
    solver:Literal['reference','circuit']='reference'
    model_mode:Literal['hybrid','physics','experimental_v2']='hybrid'
    require_model_agreement:bool=False
    connection_mode:Literal['series_marx_equivalent']='series_marx_equivalent'
    layout_id:str=Field(default='default-layout',min_length=1,max_length=100)
    stage_min:int|None=Field(default=None,ge=2,le=30)
    stage_max:int|None=Field(default=None,ge=2,le=30)
    inventory_override:InventoryOverride|None=None
    max_components_per_network:int=Field(default=24,ge=1,le=40)
    include_base_c:bool=False
    uncertainty_pct:float=Field(default=5,ge=0,le=30)
    monte_carlo_samples:int=Field(default=32,ge=8,le=128)
    equipment_reference_kv:float|None=Field(default=None,gt=0,le=10000)
    test_object_id:str|None=Field(default=None,max_length=100)
    equipment_reference_source:str|None=Field(default=None,max_length=300)
    confirm_reference_mismatch:bool=False
    calibration_id:str|None=None
    custom_profile:CustomGeneratorProfile|None=None
    parameter_calibration_id:str|None=Field(default=None,max_length=64)
    @model_validator(mode='after')
    def ordered_stages(self):
        if self.parameter_calibration_id is not None:
            if self.solver!='circuit': raise ValueError('Fitted generator parameters apply to the circuit prediction only.')
            if self.calibration_id: raise ValueError('Use either fitted generator parameters or a one-shot metric correction, not both.')
        if self.profile_id=='custom_generator':
            if self.custom_profile is None: raise ValueError('A custom generator needs its complete hardware ratings.')
            if self.inventory_override is None: raise ValueError('A custom generator needs an explicit resistor inventory with counts and provenance.')
            if self.solver!='circuit' or self.model_mode!='physics':
                raise ValueError('A custom generator uses the circuit prediction; workbook residual ML is not validated for it.')
        elif self.custom_profile is not None:
            raise ValueError('Custom hardware ratings are only used with the custom generator profile.')
        if self.require_model_agreement and self.solver!='reference':
            raise ValueError('Agreement search uses the workbook reference and independent circuit together. Select the reference prediction engine.')
        if self.stage_min and self.stage_max and self.stage_min>self.stage_max:
            raise ValueError('Minimum stages must not exceed maximum stages.')
        if self.equipment_reference_kv and not self.equipment_reference_source:
            raise ValueError('Provide a source for the equipment reference voltage.')
        return self

class GeneratorProfile(BaseModel):
    model_config=ConfigDict(extra='allow',allow_inf_nan=False)
    id:str
    name:str
    version:str
    kind:Literal['synthetic_reference','specified_hardware','incomplete','custom_hardware']
    source:str
    voltage_min_kv:float|None=Field(default=None,gt=0)
    voltage_max_kv:float=Field(gt=0)
    min_stages:int|None=Field(default=None,ge=2)
    max_stages:int=Field(ge=2)
    stage_kv:float=Field(gt=0)
    stage_c_uf:float|None=Field(default=None,gt=0)
    energy_stage_kj:float|None=Field(default=None,gt=0)
    energy_total_kj:float|None=Field(default=None,gt=0)
    front_values:list[float]
    lightning_tail_values:list[float]
    switching_tail_values:list[float]
    units_per_value_per_stage:int|None=Field(default=None,ge=0)
    base_c_pf:float|None=Field(default=None,ge=0)
    enabled:bool
    @model_validator(mode='after')
    def consistent_profile(self):
        if any(v<=0 for v in self.front_values+self.lightning_tail_values+self.switching_tail_values):
            raise ValueError('Profile resistor values must be positive.')
        if self.min_stages is not None and self.min_stages>self.max_stages:
            raise ValueError('Invalid profile stage bounds.')
        if self.voltage_min_kv and self.voltage_min_kv>self.voltage_max_kv:
            raise ValueError('Invalid profile voltage bounds.')
        if self.enabled and any(getattr(self,k) is None for k in ['stage_c_uf','energy_stage_kj','energy_total_kj','min_stages','voltage_min_kv']):
            raise ValueError('Enabled profile must specify capacitance, energy and operating bounds.')
        return self

class SimulationSettings(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    stages:int=Field(ge=2,le=30,strict=True)
    charge_kv_stage:float=Field(gt=0,le=500)
    front_r_stage:float=Field(gt=0,le=1e8)
    tail_r_stage:float=Field(gt=0,le=1e8)

class SimulationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    inputs:OptimizeRequest
    settings:SimulationSettings

class MetricPrediction(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    front_us:float=Field(gt=0)
    tail_us:float=Field(gt=0)
    crest_kv:float=Field(gt=0)

class ComplianceRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    impulse_type:Literal['Lightning','Switching']
    test_kv:float=Field(gt=0)
    prediction:MetricPrediction
