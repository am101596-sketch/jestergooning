"""Seeded synthetic world; never derives operational labels from Census data."""
import math
import random
import argparse
import json
from pathlib import Path
from .engine import DEFAULT_CASE, minute, solve

DEFAULT_CONFIG = dict(cases=500, seed=42, delay_probability=0.35,
                      mean_delay_minutes=15, withdrawal_probability=0.10,
                      funding_failure_probability=0.05, baseline_buffer=0, candidate_buffer=15)
OUTCOMES = ('on_time', 'late', 'provider_withdrawal', 'funding_failure', 'declined')


def config(raw=None):
    raw = {} if raw is None else raw
    if not isinstance(raw, dict):
        raise ValueError('Simulation settings must be an object.')
    unknown = set(raw)-set(DEFAULT_CONFIG)
    if unknown:
        raise ValueError('Unknown simulation setting: '+', '.join(sorted(unknown)))
    c = dict(DEFAULT_CONFIG, **raw)
    for key, low, high in [('cases', 10, 5000), ('seed', 0, 2147483647),
                           ('mean_delay_minutes', 1, 60), ('baseline_buffer', 0, 60), ('candidate_buffer', 0, 60)]:
        if type(c[key]) is not int or not low <= c[key] <= high:
            raise ValueError(f'{key} must be an integer between {low} and {high}.')
    for key in ['delay_probability', 'withdrawal_probability', 'funding_failure_probability']:
        if type(c[key]) not in [int, float] or not math.isfinite(c[key]) or not 0 <= c[key] <= 1:
            raise ValueError(f'{key} must be a probability between 0 and 1.')
    return c


def applicant(rng, index):
    return dict(DEFAULT_CASE, name=f'Synthetic household {index+1}', child_age=rng.randint(1,5),
                weekly_budget=rng.randint(240,420), bridge_budget=rng.randint(100,280),
                shift_start=rng.choice(['08:45','09:00','09:15','09:30']),
                shift_end=rng.choice(['16:30','17:00','17:30']))


def shock(rng, c):
    # One independent shock per provider plus a common commute disturbance.
    # Each policy sees the same underlying world, including provider-specific draws.
    withdrawals={k:rng.random()<c['withdrawal_probability'] for k in ['garden','river','sunrise']}
    funding_failed=rng.random()<c['funding_failure_probability']
    delay=rng.expovariate(1/c['mean_delay_minutes']) if rng.random()<c['delay_probability'] else 0.0
    return dict(withdrawals=withdrawals, funding_failed=funding_failed, delay_minutes=delay)


def outcome(plan, disturbance):
    if not plan['feasible']:
        return 'declined'
    selected=plan['selected']
    if disturbance['withdrawals'][selected['care']['id']]:
        return 'provider_withdrawal'
    if disturbance['funding_failed']:
        return 'funding_failure'
    if minute(selected['ride']['arrival'])+disturbance['delay_minutes']>minute(plan['case']['shift_start']):
        return 'late'
    return 'on_time'


def simulate(raw=None):
    c=config(raw)
    rng=random.Random(c['seed'])
    tallies={name:dict.fromkeys(OUTCOMES,0) for name in ['baseline','candidate']}
    costs={name:[] for name in tallies}
    paired=dict(improved=0, worsened=0, unchanged=0)
    samples=[]
    deltas=[]
    for i in range(c['cases']):
        case=applicant(rng,i)
        disturbance=shock(rng,c)
        pair={}
        for name in tallies:
            plan=solve(case,dict(version=1,arrival_buffer_minutes=c[name+'_buffer']))
            result=outcome(plan,disturbance)
            tallies[name][result]+=1
            if plan['feasible']:
                costs[name].append(plan['selected']['weekly'])
            pair[name]=dict(outcome=result, care=plan['selected']['care']['id'] if plan['feasible'] else None,
                            ride=plan['selected']['ride']['id'] if plan['feasible'] else None)
        difference=int(pair['candidate']['outcome']=='on_time')-int(pair['baseline']['outcome']=='on_time')
        paired['improved' if difference>0 else 'worsened' if difference<0 else 'unchanged']+=1
        deltas.append(difference)
        if len(samples)<30:
            samples.append(dict(case=case,delay_minutes=round(disturbance['delay_minutes'],1),**pair))
    for name,t in tallies.items():
        t['on_time_rate']=t['on_time']/c['cases']
        t['feasible']=c['cases']-t['declined']
        t['mean_feasible_weekly_cost']=round(sum(costs[name])/len(costs[name]),2) if costs[name] else None
    mean=sum(deltas)/len(deltas)
    se=math.sqrt(sum((d-mean)**2 for d in deltas)/(len(deltas)-1)/len(deltas))
    return dict(config=c,**tallies,paired=paired,samples=samples,
                on_time_rate_difference=mean,
                paired_95pct_interval=[max(-1,mean-1.96*se),min(1,mean+1.96*se)],
                interval_scope='Approximate Monte Carlo uncertainty within this synthetic generator, not real-world uncertainty.',
                synthetic=True,
                assumptions=['Fixed demo childcare and transport offers; no capacity competition between households.',
                             'Independent provider withdrawal and funding failures; exponentially distributed delays when a delay occurs.',
                             'No automatic recovery inside a run; all cases receive one initial plan.',
                             'Same household and random disturbances for each policy; results do not change the active planning policy.'])


def labeled_rows(count, seed):
    """Training examples contain only pre-outcome plan/context features."""
    rng=random.Random(seed)
    rows=[]
    attempts=0
    while len(rows)<count:
        attempts+=1
        case=applicant(rng,attempts)
        c=dict(DEFAULT_CONFIG, delay_probability=rng.uniform(0.05,0.85),
               mean_delay_minutes=rng.randint(5,45), withdrawal_probability=rng.uniform(0,0.3),
               funding_failure_probability=rng.uniform(0,0.2))
        plan=solve(case,dict(version=1,arrival_buffer_minutes=rng.choice([0,5,15,25,30])))
        if not plan['feasible']:
            continue
        result=outcome(plan,shock(rng,c))
        rows.append(dict(id=f'{seed}:{attempts}', plan=plan, context=c, label=int(result=='on_time')))
    return rows


def main():
    parser=argparse.ArgumentParser(description='Compare two policies in a local synthetic coordination world')
    parser.add_argument('--cases',type=int,default=500)
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--baseline-buffer',type=int,default=0)
    parser.add_argument('--candidate-buffer',type=int,default=15)
    parser.add_argument('--output',type=Path,help='Optional JSON report path')
    args=parser.parse_args()
    result=simulate(dict(cases=args.cases,seed=args.seed,baseline_buffer=args.baseline_buffer,candidate_buffer=args.candidate_buffer))
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='samples'},indent=2))


if __name__=='__main__':main()
