"""Physics/unit regressions based on nodal equations, not fitted observations."""
import numpy as np
import pytest
from scipy.optimize import brentq

from backend.app.physics import circuit
from backend.app.physics.circuit import simulate
from backend.app.physics.compliance import check


def analytic_rc_metrics(front_r_stage, impulse):
    # Independently solve the zero-L two-capacitor voltage equation. The load
    # starts discharged; initial dVl/dt = V0 / (Rf * Cl).
    n=11; cg=.125e-6/n; cl=1500e-12
    rf=front_r_stage*n; rt=520*n; initial=n*180*.83
    trace=(1/rt+1/rf)/cg+1/(rf*cl)
    determinant=1/(rt*rf*cg*cl)
    fast=(trace+np.sqrt(trace**2-4*determinant))/2
    slow=determinant/fast
    peak_time=np.log(fast/slow)/(fast-slow)
    coefficient=initial/(rf*cl*(fast-slow))
    voltage=lambda t:coefficient*(np.exp(-slow*t)-np.exp(-fast*t))
    crest=voltage(peak_time)
    # Dimensionless brackets isolate the very fast rising limb from the slow
    # tail. These roots do not use the production time grid or tolerance rule.
    rising=lambda fraction:brentq(lambda x:voltage(x/fast)/crest-fraction,
                                 0,peak_time*fast,xtol=1e-12)/fast
    t30,t90=rising(.3),rising(.9)
    half=brentq(lambda x:voltage(x/slow)/crest-.5,
                peak_time*slow,20,xtol=1e-12)/slow
    virtual=t30-.5*(t90-t30)
    return np.array([1.67*(t90-t30) if impulse=='Lightning' else peak_time,
                     half-virtual if impulse=='Lightning' else half,crest])*[1e6,1e6,1]


@pytest.mark.parametrize('impulse',['Lightning','Switching'])
@pytest.mark.parametrize('front_r_stage',[30,1e-8])
def test_zero_inductance_matches_analytic_two_capacitor_voltage(impulse,front_r_stage):
    result=simulate(11,180,front_r_stage,520,.125,1500,0,.83,impulse,False)
    np.testing.assert_allclose([result[k] for k in ['front_us','tail_us','crest_kv']],
                               analytic_rc_metrics(front_r_stage,impulse),rtol=2e-7)
    assert result['diagnostics']['damping_ratio'] is None


def test_cpri_matched_lightning_golden_and_charging_energy_units():
    n=11; charge=181.9; efficiency=.83
    result=simulate(n,charge,30,520,.125,650+250+55+545,12,efficiency,'Lightning',False)
    adjusted=charge*1425/result['crest_kv']
    result=simulate(n,adjusted,30,520,.125,1500,12,efficiency,'Lightning',False)
    assert adjusted==pytest.approx(181.90279,rel=1e-6)
    assert result['front_us']==pytest.approx(1.18678,abs=.001)
    assert result['tail_us']==pytest.approx(53.74353,abs=.005)
    assert result['crest_kv']==pytest.approx(1425,rel=2e-7)
    assert check('Lightning',1425,result)['nominal_pass']
    # Stages charge in parallel, then erect in series. Charging-bank energy
    # uses charge voltage before assumed losses; the erected initial energy
    # includes the square of the one voltage-efficiency factor.
    charging=n*.5*.125e-6*(adjusted*1000)**2/1000
    erected=.5*(.125e-6/n)*(n*adjusted*1000)**2/1000
    post_loss=.5*(.125e-6/n)*(n*adjusted*efficiency*1000)**2/1000
    assert charging==pytest.approx(22.74843,rel=1e-6)
    assert erected==pytest.approx(charging,rel=1e-14)
    assert post_loss==pytest.approx(charging*efficiency**2,rel=1e-14)
    assert .5*.125e-6*(200*1000)**2/1000==pytest.approx(2.5)
    assert 12*2.5==30


@pytest.mark.parametrize('factor',[.001,1000])
def test_dimensionally_similar_circuit_preserves_voltage_and_time(factor):
    args=dict(stages=11,charge_kv_stage=181.9,front_r_stage=30,tail_r_stage=520,
              stage_c_uf=.125,total_c_pf=1500,l_uh=12,efficiency=.83,include_waveform=False)
    original=simulate(**args)
    scaled=simulate(**{**args,'front_r_stage':30/factor,'tail_r_stage':520/factor,
                      'stage_c_uf':.125*factor,'total_c_pf':1500*factor,'l_uh':12/factor})
    # C -> kC, L -> L/k and R -> R/k preserve every voltage-time differential
    # equation after branch current -> kI. This checks all SI conversions.
    np.testing.assert_allclose([scaled[k] for k in ['front_us','tail_us','crest_kv']],
                               [original[k] for k in ['front_us','tail_us','crest_kv']],rtol=2e-7)


@pytest.mark.parametrize('impulse,front,tail',[('Lightning',465,520),('Switching',30,22000)])
def test_wrong_cpri_front_resistor_still_fails_timing(impulse,front,tail):
    result=simulate(11,181.9,front,tail,.125,1500,12,.83,impulse,False)
    compliance=check(impulse,1425,result)
    assert not compliance['rows'][0]['pass']
    assert not compliance['nominal_pass']


def test_tiny_inductance_is_retained_when_front_resistance_makes_it_significant():
    # Both sides of the former absolute L cutoff describe nearly the same
    # underdamped passive circuit. A zero-L shortcut halved the crest before.
    low=simulate(11,180,1e-6,520,.125,1500,1e-8,.83,'Lightning',False)
    high=simulate(11,180,1e-6,520,.125,1500,1.0001e-8,.83,'Lightning',False)
    np.testing.assert_allclose([low[k] for k in ['front_us','tail_us','crest_kv']],
                               [high[k] for k in ['front_us','tail_us','crest_kv']],rtol=1e-4)
    assert low['crest_kv']>2800
    assert low['diagnostics']['inductance_model']=='full RLC'
    assert low['diagnostics']['maximum_energy_ratio']<=1+1e-8


def independent_extreme_rlc_solution():
    # Solve the physical voltage ODE, without a matrix eigendecomposition.
    # Its slow root is bracketed after scaling by the discharge RC time;
    # deflation then recovers the two fast roots without subtractive loss.
    cg=.125e-6/2; cl=.001e-12; rf=60.; rt=2e8; l=1.01e-14
    initial=2*180*.83; g=1/(rt*cg)
    rc=rt*(cg+cl)+rf*cl
    quadratic=(rf*cl+l*cl*g)/g/rc**2
    cubic=l*cl/g/rc**3
    slow=brentq(lambda x:1-x+quadratic*x*x-cubic*x*x*x,
                 .5,1.5,xtol=1e-14)/rc
    pair=g/(l*cl)/slow; remaining=g+rf/l-slow
    fast=(remaining+np.sqrt(remaining**2-4*pair))/2
    middle=pair/fast
    poles=-np.array([slow,middle,fast])
    residues=np.array([initial/(l*cl)/np.prod(poles[i]-np.delete(poles,i))
                       for i in range(3)])
    # Residues sum to zero. Subtract the fastest exponential explicitly so
    # the initial-voltage cancellation cannot contaminate the reference.
    voltage=lambda t:np.sum(residues[:2]*(np.exp(poles[:2]*t)-np.exp(poles[2]*t)))
    derivative=lambda x:np.sum(residues*poles*np.exp(poles*x/middle))/middle
    peak=brentq(derivative,1,100,xtol=1e-12)/middle
    crest=voltage(peak)
    half=brentq(lambda x:voltage(x/slow)/crest-.5,
                peak*slow,20,xtol=1e-12)/slow
    return poles, np.array([peak*1e6,half*1e6,crest])


def test_extreme_decay_is_independently_correct_or_reports_numeric_limitation():
    # LAPACK platforms differ in whether they resolve this 17-order pole
    # separation. Either an accurate result or an explicit limitation is valid;
    # finite negative eigenvalues alone cannot establish numerical accuracy.
    _,expected=independent_extreme_rlc_solution()
    try:
        result=simulate(2,180,30,1e8,.125,.001,1.01e-8,.83,'Switching',False)
    except ValueError as exc:
        assert 'resolve' in str(exc) and 'stable decay' in str(exc)
    else:
        np.testing.assert_allclose([result[k] for k in ['front_us','tail_us','crest_kv']],
                                   expected,rtol=2e-7)


def test_inaccurate_stable_slow_pole_reports_numeric_limitation(monkeypatch):
    original=circuit.eig
    def inaccurate_modes(a):
        poles,vectors=original(a)
        poles[np.argmin(np.abs(poles))]*=1.75
        return poles,vectors
    monkeypatch.setattr(circuit,'eig',inaccurate_modes)
    with pytest.raises(ValueError,match='resolve.*stable decay'):
        simulate(2,180,30,1e8,.125,.001,1.01e-8,.83,'Switching',False)


def test_independently_resolved_extreme_modes_are_accepted(monkeypatch):
    poles,expected=independent_extreme_rlc_solution()
    cl=.001e-12; rf=60.; l=1.01e-14
    # Independent modal vectors follow Vl'=I/Cl and Vg=Vl+Rf*I+L*I'.
    vectors=np.array([1+rf*cl*poles+l*cl*poles*poles,cl*poles,np.ones(3)])
    monkeypatch.setattr(circuit,'eig',lambda a:(poles,vectors))
    result=simulate(2,180,30,1e8,.125,.001,1.01e-8,.83,'Switching',False)
    np.testing.assert_allclose([result[k] for k in ['front_us','tail_us','crest_kv']],
                               expected,rtol=2e-7)
