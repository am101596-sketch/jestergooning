"""Pure coordination logic. Provider offers are explicit, synthetic fixtures."""
from copy import deepcopy
from datetime import datetime
from itertools import product

CARES = [
    dict(id='garden', name='Garden Early Learning', opens='07:30', closes='18:00',
         weekly=220, deposit=180, min_age=2, max_age=5, pickup_minutes=35),
    dict(id='river', name='River Family Care', opens='07:00', closes='18:30',
         weekly=260, deposit=120, min_age=1, max_age=5, pickup_minutes=40),
    dict(id='sunrise', name='Sunrise Preschool', opens='08:30', closes='17:00',
         weekly=190, deposit=80, min_age=3, max_age=5, pickup_minutes=35),
]
RIDES = [
    dict(id='express', name='Express connection', departure='08:10', arrival='08:55', weekly=40),
    dict(id='flex', name='Earlier connection', departure='07:45', arrival='08:35', weekly=65),
]
DEFAULT_CASE = dict(name='Maya Chen', child_age=3, shift_start='09:00', shift_end='17:00',
                    weekly_budget=350, bridge_budget=250, county='San Francisco')


def minute(value):
    if not isinstance(value, str) or len(value) != 5:
        raise ValueError('Times must use HH:MM.')
    try:
        t = datetime.strptime(value, '%H:%M')
    except ValueError as exc:
        raise ValueError('Times must use HH:MM, between 00:00 and 23:59.') from exc
    return t.hour * 60 + t.minute


def validate_case(raw):
    if not isinstance(raw, dict):
        raise ValueError('Applicant details must be an object.')
    case = {k: raw.get(k, v) for k, v in DEFAULT_CASE.items()}
    for k in ['name', 'county']:
        if not isinstance(case[k], str) or not 1 <= len(case[k].strip()) <= 100:
            raise ValueError(f'{k} must be between 1 and 100 characters.')
        case[k] = case[k].strip()
    for k, low, high in [('child_age', 0, 17), ('weekly_budget', 0, 10000), ('bridge_budget', 0, 10000)]:
        if type(case[k]) is not int or not low <= case[k] <= high:
            raise ValueError(f'{k} must be a whole number between {low} and {high}.')
    if minute(case['shift_end']) <= minute(case['shift_start']):
        raise ValueError('This demo supports daytime shifts ending after they start.')
    if case['county'].lower() != 'san francisco':
        raise ValueError('The coordination demo currently covers San Francisco only. Research covers the nation.')
    return case


def solve(raw, policy=None, excluded=None):
    case = validate_case(raw)
    policy = policy or {'arrival_buffer_minutes': 0, 'version': 1}
    excluded = set(excluded or [])
    if excluded - {c['id'] for c in CARES}:
        raise ValueError('Unknown withdrawn provider.')
    candidates, rejected = [], []
    for care, ride in product(CARES, RIDES):
        reasons = []
        weekly = care['weekly'] + ride['weekly']
        buffer = policy['arrival_buffer_minutes']
        if care['id'] in excluded:
            reasons.append('Provider withdrew its demo offer.')
        if not care['min_age'] <= case['child_age'] <= care['max_age']:
            reasons.append('Child age is outside the provider offer.')
        if minute(care['opens']) + 10 > minute(ride['departure']):
            reasons.append('There is not enough time for drop-off before departure.')
        if minute(ride['arrival']) + buffer > minute(case['shift_start']):
            reasons.append(f'Arrival does not leave the required {buffer}-minute buffer.')
        if minute(case['shift_end']) + care['pickup_minutes'] > minute(care['closes']):
            reasons.append('Pickup would occur after childcare closes.')
        if weekly > case['weekly_budget']:
            reasons.append(f'Weekly cost exceeds the budget by ${weekly-case["weekly_budget"]}.')
        if care['deposit'] > case['bridge_budget']:
            reasons.append(f'Deposit needs ${care["deposit"]-case["bridge_budget"]} more bridge funding.')
        item = dict(care=deepcopy(care), ride=deepcopy(ride), weekly=weekly,
                    deposit=care['deposit'], reasons=reasons)
        (rejected if reasons else candidates).append(item)
    candidates.sort(key=lambda c: (c['weekly'], c['deposit'], c['care']['id']))
    return dict(case=case, feasible=bool(candidates), selected=candidates[0] if candidates else None,
                alternatives=candidates[1:], rejected=rejected, policy=deepcopy(policy),
                excluded=sorted(excluded), mode='simulation',
                explanation='Lowest weekly cost among offers meeting every explicit constraint.' if candidates
                else 'No complete plan meets the current constraints. No reservations or promises were made.')


# Fixed stress cases are independent of observed case records and never modified
# by the learning process. They test scheduling behavior, not real-world impact.
STRESS_CASES = (
    dict(id='standard', weekly_budget=350, shift_start='09:00', delay=15),
    dict(id='tight_budget', weekly_budget=300, shift_start='09:00', delay=15),
    dict(id='no_affordable_offer', weekly_budget=250, shift_start='09:00', delay=15),
    dict(id='later_shift', weekly_budget=350, shift_start='09:15', delay=15),
    dict(id='earlier_shift', weekly_budget=350, shift_start='08:30', delay=15),
)


def evaluate(policy):
    results = []
    for item in STRESS_CASES:
        case = dict(DEFAULT_CASE, weekly_budget=item['weekly_budget'], shift_start=item['shift_start'])
        plan = solve(case, policy)
        if not plan['feasible']:
            outcome = 'declined'
        else:
            actual_arrival = minute(plan['selected']['ride']['arrival']) + item['delay']
            outcome = 'on_time' if actual_arrival <= minute(case['shift_start']) else 'late'
        results.append(dict(id=item['id'], outcome=outcome,
                            selected=plan['selected']['ride']['id'] if plan['feasible'] else None))
    return dict(on_time=sum(r['outcome']=='on_time' for r in results),
                late=sum(r['outcome']=='late' for r in results),
                declined=sum(r['outcome']=='declined' for r in results), results=results)


def assess_policy(current, observed_delays):
    if not observed_delays:
        raise ValueError('Record a transport delay on a committed demo plan first.')
    baseline = evaluate(current)
    floor = current['arrival_buffer_minutes']
    buffers = sorted({d for d in observed_delays if d > floor}, reverse=True) or [floor]
    assessed = [(c, evaluate(c)) for c in (dict(current, arrival_buffer_minutes=b, version=current['version']+1)
                                           for b in buffers)]
    passes = lambda p: (p['late'] < baseline['late'] and p['on_time'] >= baseline['on_time'] and p['on_time'] > 0
                        and p['declined'] <= baseline['declined'])
    candidate, proposal = next((pair for pair in assessed if passes(pair[1])), assessed[0])
    promoted = passes(proposal)
    return dict(baseline=baseline, candidate=proposal, proposed_policy=candidate, promoted=promoted,
                reason='Fewer late arrivals, with no loss of on-time starts and no added declines.' if promoted else
                'No qualifying improvement on the fixed stress suite; current policy retained.',
                scope='Five synthetic stress scenarios. This is not evidence of real-world employment impact.')
