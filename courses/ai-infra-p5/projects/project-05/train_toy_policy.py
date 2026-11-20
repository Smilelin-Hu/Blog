"""Run SFT -> reference-aware DPO -> grouped clipped policy-gradient updates.
A two-action categorical policy, NOT a language model or a GPU benchmark.
"""
from __future__ import annotations
import json, math, random
from pathlib import Path

def probs(logits):
    high=max(logits); values=[math.exp(x-high) for x in logits]; total=sum(values)
    return [x/total for x in values]

def main():
    logits=[0.0,0.0]; lr=0.1; stages=[]
    # Chosen action is 1. Cross entropy gradient for softmax classification.
    for _ in range(12):
        p=probs(logits)
        logits=[x-lr*(p[i]-(i==1)) for i,x in enumerate(logits)]
    ref=probs(logits); stages.append({'stage':'sft','chosen_probability':ref[1]})
    beta=0.5
    for _ in range(12):
        p=probs(logits)
        margin=math.log(p[1]/p[0])-math.log(ref[1]/ref[0])
        grad=-beta/(1+math.exp(beta*margin))
        logits[1]-=lr*grad; logits[0]+=lr*grad
    stages.append({'stage':'dpo','chosen_probability':probs(logits)[1], 'reference':ref})
    rng=random.Random(7); rows=[]
    for step in range(12):
        old=probs(logits)
        actions=rng.choices([0,1],weights=old,k=16)
        rewards=[float(a==1) for a in actions]
        mean=sum(rewards)/len(rewards); std=math.sqrt(sum((r-mean)**2 for r in rewards)/len(rewards))
        advantage=[0.0 if std==0 else (r-mean)/std for r in rewards]
        # Two inner updates expose the distinction between old and current probabilities.
        for _ in range(2):
            p=probs(logits); gradient=[0.0,0.0]
            for action,a in zip(actions,advantage):
                ratio=p[action]/old[action]
                clipped=(a>0 and ratio>1.2) or (a<0 and ratio<0.8)
                if not clipped:
                    for k in range(2):gradient[k]+=-a*ratio*((k==action)-p[k])/len(actions)
            logits=[x-lr*g for x,g in zip(logits,gradient)]
        rows.append({'step':step,'zero_variance':std==0,'reward_mean':mean})
    stages.append({'stage':'grouped_policy_gradient','chosen_probability':probs(logits)[1]})
    checks={'sft_updates_policy':stages[0]['chosen_probability']>0.5,
            'dpo_improves_fixed_pair':stages[1]['chosen_probability']>stages[0]['chosen_probability'],
            'finite_normalized':all(math.isfinite(x) for x in probs(logits)) and abs(sum(probs(logits))-1)<1e-12}
    report={'status':'passed' if all(checks.values()) else 'failed','checks':checks,'stages':stages,'rollout':rows,
            'boundary':'Two-action, one-step CPU policy; beta_KL=0; not full GRPO/DAPO, not LLM capability or GPU performance.'}
    out=Path(__file__).with_name('results');out.mkdir(exist_ok=True);(out/'toy_training.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    return 0 if all(checks.values()) else 1
if __name__=='__main__':raise SystemExit(main())
