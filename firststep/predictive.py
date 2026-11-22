"""Small, inspectable logistic model trained and evaluated entirely on-device."""
import argparse
import json
import math
import threading
from datetime import datetime, timezone
from pathlib import Path
from .engine import minute, solve, DEFAULT_CASE
from .simulator import DEFAULT_CONFIG, config, labeled_rows

ROOT=Path(__file__).resolve().parents[1]
FEATURES=['arrival_slack_minutes','log_arrival_slack','delay_probability',
          'mean_delay_minutes','withdrawal_probability','funding_failure_probability',
          'slack_to_mean_delay','delay_probability_x_slack_ratio']
TRAINING_LOCK=threading.Lock()


def features(plan,c):
    if not plan['feasible']:
        raise ValueError('Predictions require a feasible plan; declined cases are not scored.')
    slack=minute(plan['case']['shift_start'])-minute(plan['selected']['ride']['arrival'])
    ratio=min(12,slack/c['mean_delay_minutes'])
    return [slack,math.log1p(slack),c['delay_probability'],c['mean_delay_minutes'],
            c['withdrawal_probability'],c['funding_failure_probability'],ratio,c['delay_probability']*ratio]


def sigmoid(z):
    z=max(-35,min(35,z))
    return 1/(1+math.exp(-z))


def probability(model,values):
    z=model['intercept']+sum(w*(v-m)/s for w,v,m,s in zip(model['weights'],values,model['means'],model['scales']))
    return sigmoid(z)


def metrics(labels, probabilities):
    n=len(labels)
    brier=sum((p-y)**2 for y,p in zip(labels,probabilities))/n
    logloss=-sum(y*math.log(max(p,1e-12))+(1-y)*math.log(max(1-p,1e-12)) for y,p in zip(labels,probabilities))/n
    accuracy=sum((p>=0.5)==bool(y) for y,p in zip(labels,probabilities))/n
    # Rank-sum AUROC with average ranks for ties.
    pairs=sorted(zip(probabilities,labels))
    rank_sum=0.0
    i=0
    while i<n:
        j=i+1
        while j<n and pairs[j][0]==pairs[i][0]:j+=1
        rank_sum+=((i+1+j)/2)*sum(y for _,y in pairs[i:j])
        i=j
    positives=sum(labels)
    auc=(rank_sum-positives*(positives+1)/2)/(positives*(n-positives)) if 0<positives<n else None
    calibration=[]
    for k in range(10):
        group=[(y,p) for y,p in zip(labels,probabilities) if min(9,int(p*10))==k]
        if group:
            calibration.append(dict(lower=k/10,upper=(k+1)/10,count=len(group),
                                    predicted=sum(p for _,p in group)/len(group),observed=sum(y for y,_ in group)/len(group)))
    return dict(rows=n,positive_rate=positives/n,brier=brier,log_loss=logloss,accuracy=accuracy,auroc=auc,calibration=calibration)


def train(train_count=4000,test_count=1000,seed=20261122,epochs=180):
    if type(train_count) is not int or not 200<=train_count<=10000:
        raise ValueError('Training size must be between 200 and 10000 feasible plans.')
    if type(test_count) is not int or not 100<=test_count<=3000:
        raise ValueError('Test size must be between 100 and 3000 feasible plans.')
    if type(seed) is not int or not 0<=seed<=2147483645:
        raise ValueError('Seed must be an integer between 0 and 2147483645.')
    training=labeled_rows(train_count,seed)
    test=labeled_rows(test_count,seed+1)
    assert not {r['id'] for r in training}&{r['id'] for r in test}
    x=[features(r['plan'],r['context']) for r in training]
    y=[r['label'] for r in training]
    means=[sum(row[j] for row in x)/train_count for j in range(len(FEATURES))]
    scales=[max(1e-8,math.sqrt(sum((row[j]-means[j])**2 for row in x)/train_count)) for j in range(len(FEATURES))]
    normalized=[[(v-m)/s for v,m,s in zip(row,means,scales)] for row in x]
    prevalence=sum(y)/len(y)
    weights=[0.0]*len(FEATURES)
    intercept=math.log(max(prevalence,1e-6)/max(1-prevalence,1e-6))
    for _ in range(epochs):
        gradient=[0.0]*len(FEATURES)
        bias=0.0
        for values,label in zip(normalized,y):
            error=sigmoid(intercept+sum(w*v for w,v in zip(weights,values)))-label
            bias+=error
            for j,v in enumerate(values):gradient[j]+=error*v
        intercept-=0.2*bias/train_count
        weights=[w-0.2*(g/train_count+0.002*w) for w,g in zip(weights,gradient)]
    model=dict(schema_version=1,kind='logistic_regression',feature_names=FEATURES,weights=weights,
               intercept=intercept,means=means,scales=scales,synthetic_only=True,
               trained_at=datetime.now(timezone.utc).isoformat(),
               training=dict(train_rows=train_count,test_rows=test_count,train_seed=seed,test_seed=seed+1,
                             epochs=epochs,learning_rate=0.2,l2=0.002,training_positive_rate=prevalence),
               arrival_slack_range=[min(row[0] for row in x),max(row[0] for row in x)],
               target='On-time start conditional on a feasible synthetic plan and supplied risk assumptions.',
               domain=dict(delay_probability=[0.05,0.85],mean_delay_minutes=[5,45],
                           withdrawal_probability=[0,0.3],funding_failure_probability=[0,0.2]),
               limitations=['Trained only on generated outcomes, not real families or historical employment outcomes.',
                            'Evaluation uses a different seed from the same generator; it is not external validation.',
                            'Fixed provider offers, independent disruptions, and exponential delay assumptions.',
                            'Probabilities are conditional scenario estimates, not eligibility or allocation decisions.'])
    labels=[r['label'] for r in test]
    preds=[probability(model,features(r['plan'],r['context'])) for r in test]
    model['evaluation']=metrics(labels,preds)
    model['baseline_evaluation']=metrics(labels,[prevalence]*len(labels))
    model['evaluation']['brier_improvement_over_constant']=model['baseline_evaluation']['brier']-model['evaluation']['brier']
    return model


def load_model(path=None):
    path=Path(path) if path else ROOT/'data'/'model.json'
    if not path.exists():path=ROOT/'models'/'readiness-v1.json'
    if not path.exists():raise LookupError('No predictive model found. Train a model locally first.')
    model=json.loads(path.read_text())
    if model.get('feature_names')!=FEATURES or model.get('schema_version')!=1:
        raise ValueError('Unsupported predictive model artifact.')
    return model


def save_model(model,path):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    stage=path.with_suffix('.json.part')
    stage.write_text(json.dumps(model,indent=2),encoding='utf-8')
    stage.replace(path)


def predict(plan,raw_context=None,model=None):
    c=config(raw_context)
    if not plan['feasible']:
        return dict(probability=None,synthetic_only=True,reason='No feasible plan; model does not score declined cases.')
    model=model or load_model()
    outside=[k for k,(low,high) in model['domain'].items() if not low<=c[k]<=high]
    if outside:
        return dict(probability=None,synthetic_only=True,reason='Outside training ranges: '+', '.join(outside))
    values=features(plan,c)
    low,high=model['arrival_slack_range']
    if not low<=values[0]<=high:
        return dict(probability=None,synthetic_only=True,reason='Arrival slack is outside the model training range.')
    return dict(probability=probability(model,values),synthetic_only=True,
                context={k:c[k] for k in model['domain']},model_trained_at=model['trained_at'],
                reason='Conditional estimate from synthetic outcomes. It does not certify a real-world result.')


def main():
    parser=argparse.ArgumentParser(description='Train the FirstStep predictive model locally on synthetic outcomes')
    parser.add_argument('--train',type=int,default=4000)
    parser.add_argument('--test',type=int,default=1000)
    parser.add_argument('--seed',type=int,default=20261122)
    parser.add_argument('--output',type=Path,default=ROOT/'data'/'model.json')
    args=parser.parse_args()
    model=train(args.train,args.test,args.seed)
    save_model(model,args.output)
    print(json.dumps(dict(saved=str(args.output),evaluation=model['evaluation'],baseline=model['baseline_evaluation']),indent=2))


if __name__=='__main__':main()
