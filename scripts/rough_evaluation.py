"""Frozen Rough development cases and report gates; no simulator imports."""
from __future__ import annotations
import hashlib,json,math,random

FAMILIES=('random','slope_up','slope_down','blocks')
CASE_SEEDS={'nominal':2026091981,'bounded_v1':2026091982}
GEOMETRY_SEED=2026091980


def make_cases(family,level,profile):
    if family not in FAMILIES or level not in range(3) or profile not in CASE_SEEDS:raise ValueError('Unregistered Rough cases')
    rng=random.Random(CASE_SEEDS[profile]+100*level+10*FAMILIES.index(family))
    cases=[]
    for i in range(100):
        kind='traverse' if i<60 else 'stand' if i<80 else 'turn'
        # Positive terrain x makes slope_up/down unambiguous; reverse turns are balanced.
        cases.append(dict(index=i,family=family,level=level,kind=kind,
                          start_y=rng.uniform(-.10,.10),initial_yaw=rng.uniform(-.025,.025),
                          leg_offset=[rng.uniform(-.015,.015) for _ in range(12)],
                          vx=rng.uniform(.20,.24) if kind=='traverse' else .30,
                          yaw=(1 if i%2 else -1)*rng.uniform(.20,.30) if kind=='turn' else 0.,
                          approach_seconds=12.,minimum_route_m=3.,corridor_y=[-.9,.9],corridor_x=[-.6,5.4]))
    return cases


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def wilson(success,total):
    z=1.959963984540054;p=success/total;den=1+z*z/total
    center=(p+z*z/(2*total))/den;half=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return [center-half,center+half]


def summarize(cases,results,threshold=.95):
    if len(cases)!=100 or len(results)!=100 or [r['index'] for r in results]!=[c['index'] for c in cases] or [c['index'] for c in cases]!=list(range(100)):
        raise ValueError('Incomplete Rough report')
    if any(r['measurement_steps'] <= 0 or len(r['squared_error_sum']) != 3 or any(not math.isfinite(v) or v < 0 for v in r['squared_error_sum']) for r in results):
        raise ValueError('Invalid Rough measurement rows')
    by={}
    for kind in ('traverse','stand','turn'):
        rows=[r for c,r in zip(cases,results) if c['kind']==kind]
        good=sum(r['success'] for r in rows)
        rms=[math.sqrt(sum(r['squared_error_sum'][i] for r in rows)/sum(r['measurement_steps'] for r in rows)) for i in range(3)]
        by[kind]=dict(episodes=len(rows),success=good,success_fraction=good/len(rows),wilson95=wilson(good,len(rows)),
                      pooled_rms_vx_vy_yaw=rms,passed=good/len(rows)>=threshold and all(v<=lim for v,lim in zip(rms,(.25,.25,.30))))
    return dict(by_kind=by,threshold=threshold,passed=all(r['passed'] for r in by.values()),
                success=sum(r['success'] for r in results),episodes=100)


def flat_regression(candidate,parent):
    from run_reference_transfer import summary_pass
    if not summary_pass(candidate) or not summary_pass(parent):return False
    if candidate['no_fall_count']<parent['no_fall_count']-2:return False
    for name,p in parent['by_scenario'].items():
        values=candidate['by_scenario'][name]['pooled_rms_vx_vy_yaw']
        if any(c>b+max(.1*b,.01) for c,b in zip(values,p['pooled_rms_vx_vy_yaw'])):return False
    return True
