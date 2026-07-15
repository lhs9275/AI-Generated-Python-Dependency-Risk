import csv, json, random
from collections import Counter
D='results/tse_gap_closure/data/'
labels={r['change_id']:r for r in csv.DictReader(open(D+'independent_labels.csv'))}
guard={json.loads(l)['change_id']:json.loads(l) for l in open(D+'guard_outputs.jsonl')}
changed={r['change_id']:r for r in csv.DictReader(open('results/major_revision/changed_rows_final.csv'))}
PRIMARY={'P1_NONEXISTENT_PACKAGE','P2_INVALID_VERSION_SPEC','P3_DIRECT_KNOWN_VULNERABILITY'}
def newlab(c): return changed[c]['new_label'] if c in changed else labels[c]['label_primary']
STAGES=['S1_existence','S1S2_version','S1S2S3_direct_evidence','S1S2S3_plus_license','B3_full_guard']
def blocked(cid,st): return str(guard[cid]['decisions'][st]).upper()=='BLOCK'

gated=[c for c in guard if labels.get(c,{}).get('change_type') in ('add','version_change')]
def lad(labelfn):
    prim=[c for c in gated if labelfn(c) in PRIMARY]; neg=[c for c in gated if labelfn(c)=='NONE']
    out={}
    for st in STAGES:
        pb=sum(1 for c in prim if blocked(c,st)); nb=sum(1 for c in neg if blocked(c,st))
        out[st]={'prim_block':pb,'prim_accept_pct':round((len(prim)-pb)/len(prim)*100,1),
                 'neg_block':nb,'neg_block_pct':round(nb/len(neg)*100,2)}
    return len(prim),len(neg),out

print("=== PER-STAGE LADDER (retained gate sample) ===")
for name,fn in [('ORIGINAL',lambda c:labels[c]['label_primary']),('CORRECTED',newlab)]:
    np_,nn,l=fn if False else lad(fn)
    print(f"\n{name}: primary={np_} primary-negative={nn}")
    for st in STAGES:
        s=l[st]; print(f"  {st:24} prim-accept {s['prim_accept_pct']:5}%  neg-block {s['neg_block']}/{nn}={s['neg_block_pct']}%")

# repo-clustered bootstrap CI for corrected prevalence (all 8752, not just gated)
allrows=[r for r in labels.values() if r['change_type'] in ('add','version_change')]
by_repo={}
for r in allrows: by_repo.setdefault(r['repo'],[]).append(r['change_id'])
repos=list(by_repo)
def is_risk(cid): return newlab(cid) in PRIMARY
random.seed(42)
B=2000; rates=[]
for _ in range(B):
    samp=[random.choice(repos) for _ in range(len(repos))]
    num=den=0
    for rp in samp:
        ids=by_repo[rp]; den+=len(ids); num+=sum(1 for c in ids if is_risk(c))
    rates.append(num/den*100 if den else 0)
rates.sort()
tot=sum(1 for r in allrows if is_risk(r['change_id']))
print(f"\n=== CORRECTED PREVALENCE ===\n{tot}/8752 = {tot/8752*100:.2f}%  repo-clustered 95% CI [{rates[int(0.025*B)]:.2f}, {rates[int(0.975*B)]:.2f}]  (removals-only sensitivity {(273)/8752*100:.2f}%)")
# family dominance
fam=Counter(newlab(c) for c in [r['change_id'] for r in allrows] if newlab(c) in PRIMARY)
print("family:",dict(fam),"-> P3 dominance",round(fam['P3_DIRECT_KNOWN_VULNERABILITY']/tot*100,1),"%")
