"""Lumped Marx equivalent: generator C shunted by Rt, series Rf/L into load C."""
import numpy as np
from scipy.linalg import eig
from scipy.optimize import brentq
from .waveform_metrics import analyze

VERSION = 'lumped RLC Marx equivalent v2.1'

def simulate(stages,charge_kv_stage,front_r_stage,tail_r_stage,stage_c_uf,
             total_c_pf,l_uh,efficiency,impulse_type='Lightning',include_waveform=True):
    cg=stage_c_uf*1e-6/stages; cl=total_c_pf*1e-12; rf=front_r_stage*stages; rt=tail_r_stage*stages
    if min(cg,cl,rf,rt,charge_kv_stage,efficiency)<=0 or l_uh<0: raise ValueError('Nonphysical circuit inputs.')
    initial=stages*charge_kv_stage*efficiency
    # The absolute small-L shortcut is valid only when the branch inductive
    # time L/Rf is negligible relative to charge transfer Rf*Cseries. Keeping
    # the dimensionless ratio prevents silently suppressing tiny-L oscillations
    # when a caller supplies a very small (but positive) front resistance.
    series_c=cg*cl/(cg+cl)
    inductive_ratio=l_uh*1e-6/(rf*rf*series_c)
    use_inductance=l_uh>1e-8 or (l_uh>0 and inductive_ratio>1e-8)
    if use_inductance:
        l=l_uh*1e-6
        a=np.array([[-1/(rt*cg),-1/cg,0],[1/l,-rf/l,-1/l],[0,1/cl,0]],float)
        z=np.array([initial,0.,0.]); out_index=2
    else:
        a=np.array([[-(1/rt+1/rf)/cg,1/(rf*cg)],[1/(rf*cl),-1/(rf*cl)]])
        z=np.array([initial,0.]); out_index=1
    if out_index==1:
        # Exact RC modes. Compute the slow decay as product/fast decay rather
        # than subtracting nearly equal large values; eig can lose this mode
        # when Rf << Rt. These are the same nodal equations, not a new topology.
        decay_sum=(1/rt+1/rf)/cg+1/(rf*cl)
        decay_product=1/(rt*rf*cg*cl)
        beta=(decay_sum+np.sqrt(decay_sum*decay_sum-4*decay_product))/2
        alpha=decay_product/beta
        eigen=np.array([-alpha,-beta])
        vectors=np.array([[1-rf*cl*alpha,1-rf*cl*beta],[1.,1.]])
    else:
        eigen,vectors=eig(a)
    resolved=np.isfinite(eigen).all() and np.all(eigen.real<0)
    if resolved and out_index==2:
        # A stable-looking eig result can still lose the slow pole when the
        # passive circuit spans many orders of magnitude. Verify every pole
        # against the independently formed nodal characteristic polynomial.
        # Scaling the polynomial avoids comparing the slow-pole error with the
        # much larger fast matrix entries, which would hide a wrong tail.
        g=1/(rt*cg); r=rf/l
        scale=max(float(np.max(np.abs(eigen))),g,r)
        x=eigen/scale; gs=g/scale; rs=r/scale
        ls=1/l/scale; cgs=1/cg/scale; cls=1/cl/scale
        terms=np.array([x**3,(gs+rs)*x*x,
                        (ls*(cgs+cls)+gs*rs)*x,
                        np.full_like(x,gs*ls*cls)])
        denominator=np.sum(np.abs(terms),axis=0)
        residual=np.abs(np.sum(terms,axis=0))/denominator
        resolved=np.isfinite(residual).all() and np.all(residual<=1e-8)
    if not resolved:
        raise ValueError('Could not resolve finite stable decay modes of the passive equivalent circuit. Review extreme circuit ratios; no waveform result returned.')
    coefficients=np.linalg.solve(vectors,z)
    slow=1/min(-eigen.real); fast=max(rf*cl,np.sqrt(l_uh*1e-6*cl),1e-10)
    t=np.unique(np.r_[np.linspace(0,min(20*fast,slow),550),np.geomspace(max(fast*.001,1e-12),12*slow,650)])
    if out_index==1:
        # This two-mode RC impulse has one analytic interior crest. Include it
        # even when its time is far below the plotting grid's first sample.
        analytic_peak_time=np.log(beta/alpha)/(beta-alpha)
        t=np.unique(np.r_[t,analytic_peak_time])
    v=np.real((vectors[out_index,:]*coefficients)@np.exp(eigen[:,None]*t[None,:]))
    def root_tolerance(left,right):
        # A fixed femtosecond tolerance is too coarse for arbitrarily fast
        # valid circuits. Ordinary microsecond impulses retain the old cap.
        return min(1e-15,max(np.finfo(float).tiny,(right-left)*1e-8))
    peak=int(np.searchsorted(t,analytic_peak_time)) if out_index==1 else int(np.argmax(v))
    if out_index==2 and 0<peak<len(t)-1:
        derivative=lambda x:float(np.real(np.sum(vectors[out_index,:]*coefficients*eigen*np.exp(eigen*x))))
        try:
            tp=brentq(derivative,t[peak-1],t[peak+1],xtol=root_tolerance(t[peak-1],t[peak+1]))
            t=np.unique(np.r_[t,tp]); v=np.real((vectors[out_index,:]*coefficients)@np.exp(eigen[:,None]*t[None,:]))
        except ValueError as exc:
            raise ValueError('Could not resolve a continuous interior circuit crest; no waveform result returned.') from exc
    v[0]=0.; result=analyze(t*1e6,v,impulse_type)
    # The modal solution is continuous: refine threshold times on that solution
    # rather than accepting the plotting-grid interpolation as the final metric.
    # Uploaded sampled waveforms still use the separate interpolation analyzer.
    def voltage(time):
        return float(np.real(np.sum(vectors[out_index,:]*coefficients*np.exp(eigen*time))))
    peak=int(np.searchsorted(t,analytic_peak_time)) if out_index==1 else int(np.argmax(v))
    crest=float(v[peak]); t_peak_seconds=float(t[peak])
    def exact_crossing(fraction,rising):
        level=crest*fraction
        first,last=(0,peak) if rising else (peak,len(t)-1)
        a,b=v[first:last],v[first+1:last+1]
        matches=(a<=level)&(b>=level) if rising else (a>=level)&(b<=level)
        index=int(np.flatnonzero(matches)[0])+first
        return brentq(lambda time:voltage(time)-level,t[index],t[index+1],xtol=root_tolerance(t[index],t[index+1]))*1e6
    t30=exact_crossing(.3,True);t90=exact_crossing(.9,True);t50=exact_crossing(.5,False)
    virtual=t30-.5*(t90-t30)
    # Put the refined 30/90/50% points on the returned curve itself, so metrics
    # re-extracted from the displayed samples reproduce the reported metrics.
    t=np.unique(np.r_[t,np.array([t30,t90,t50])*1e-6])
    v=np.real((vectors[out_index,:]*coefficients)@np.exp(eigen[:,None]*t[None,:])); v[0]=0.
    peak=int(np.searchsorted(t,t_peak_seconds))
    result.update(crest_kv=crest,peak_time_us=float(t[peak]*1e6),
        t30_us=t30,t90_us=t90,t50_us=t50,virtual_origin_us=virtual,
        front_us=1.67*(t90-t30) if impulse_type=='Lightning' else float(t[peak]*1e6),
        tail_us=t50-virtual if impulse_type=='Lightning' else t50)
    states=np.real(vectors@(coefficients[:,None]*np.exp(eigen[:,None]*t[None,:])))
    stored=.5*cg*(states[0]*1000)**2+.5*cl*(states[out_index]*1000)**2
    if out_index==2: stored+=.5*l*(states[1]*1000)**2
    initial_energy=.5*cg*(initial*1000)**2
    energy_ratios=stored/initial_energy
    result['diagnostics']={'model':VERSION,'metric_extraction':'Continuous modal peak and bracketed 30/90/50% root refinement; plot samples are not the final crossing metrics.',
        'damping_ratio':float(rf/2*np.sqrt(cl/(l_uh*1e-6))) if l_uh>0 else None,
        'damping_ratio_definition':'Rf_total/2 sqrt(Cl/L): load-branch second-order approximation, not the damping ratio of the coupled Cg/Rt/Rf/L/Cl model; undefined for L=0.',
        'inductance_model':'full RLC' if use_inductance else ('zero-inductance RC' if l_uh==0 else 'negligible-inductance RC approximation'),
        'eigenvalues_per_second':[{'real':float(e.real),'imaginary':float(e.imag)} for e in eigen],
        'efficiency_convention':'One voltage factor applied to erected initial voltage; includes assumed spark/connection loss.',
        'limitations':'No spark-gap dynamics, distributed capacitances, electromagnetic fields or pulse-rating model. Needs lab validation.',
        'maximum_energy_ratio':float(energy_ratios.max()),
        'maximum_energy_increase_ratio':float(max(0,np.diff(energy_ratios).max()))}
    if include_waveform: result['waveform']={'time_us':(t*1e6).tolist(),'voltage_kv':v.tolist(),'kind':'equivalent_circuit',
        'label':'Circuit prediction','metric_points_included':True,
        'note':'Samples of the lumped-circuit solution, including the refined crest and 30/90/50% crossing points used for the reported metrics.'}
    return result
