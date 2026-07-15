import csv, json
import numpy as np
from collections import Counter
D='results/tse_gap_closure/data/'
labels={r['change_id']:r for r in csv.DictReader(open(D+'independent_labels.csv'))}
guard={json.loads(l)['change_id']:json.loads(l) for l in open(D+'guard_outputs.jsonl')}
changed={r['change_id']:r for r in csv.DictReader(open('results/major_revision/changed_rows_final.csv'))}
PRIMARY={'P1_NONEXISTENT_PACKAGE','P2_INVALID_VERSION_SPEC','P3_DIRECT_KNOWN_VULNERABILITY'}
def newlab(c): return changed[c]['new_label'] if c in changed else labels[c]['label_primary']
allrows=[r for r in labels.values() if r['change_type'] in ('add','version_change')]
ids=[r['change_id'] for r in allrows]

# --- canonical-style CI: numpy default_rng(42), 60k, percentile, PR & repo clustered ---
def clustered_ci(keyfield):
    clusters={}
    for r in allrows: clusters.setdefault(r[keyfield],[]).append(1 if newlab(r['change_id']) in PRIMARY else 0)
    keys=list(clusters); arrs=[np.array(clusters[k]) for k in keys]
    rng=np.random.default_rng(42); B=60000; n=len(keys); rates=np.empty(B)
    sums=np.array([a.sum() for a in arrs]); lens=np.array([len(a) for a in arrs])
    for i in range(B):
        idx=rng.integers(0,n,n); rates[i]=sums[idx].sum()/lens[idx].sum()*100
    return round(float(np.percentile(rates,2.5)),2), round(float(np.percentile(rates,97.5)),2)
pr_lo,pr_hi=clustered_ci('pr_id'); repo_lo,repo_hi=clustered_ci('repo')

tot=sum(1 for r in allrows if newlab(r['change_id']) in PRIMARY)
print(f"prevalence {tot}/8752={tot/8752*100:.2f}%  PR-clustered [{pr_lo},{pr_hi}]  repo-clustered [{repo_lo},{repo_hi}]")

# --- per-tool (tool_evidence field) ---
tool={}
for r in allrows:
    t=r.get('tool_evidence','?').split(',')[0].strip() or '?'
    tool.setdefault(t,[0,0]); tool[t][1]+=1
    if newlab(r['change_id']) in PRIMARY: tool[t][0]+=1
print("\nper-tool (risk/total):")
s=0
for t,(a,b) in sorted(tool.items(),key=lambda x:-x[1][0]): 
    if a>0: print(f"  {t}: {a}/{b}"); s+=a
print("  sum risk:",s,"(=total primary", tot,")")

# --- merged subset ---
merged=[r for r in allrows if str(r.get('merged_at','')).strip() not in ('','None')]
mrisk=sum(1 for r in merged if newlab(r['change_id']) in PRIMARY)
mp3=sum(1 for r in merged if newlab(r['change_id'])=='P3_DIRECT_KNOWN_VULNERABILITY')
mp1=sum(1 for r in merged if newlab(r['change_id'])=='P1_NONEXISTENT_PACKAGE')
print(f"\nmerged subset: {mrisk}/{len(merged)}={mrisk/len(merged)*100:.2f}%  (P3 {mp3}, P1 {mp1})")

# --- PR-level ---
prrisk=set(); prall=set()
for r in allrows:
    prall.add(r['pr_id'])
    if newlab(r['change_id']) in PRIMARY: prrisk.add(r['pr_id'])
print(f"PR-level: {len(prrisk)}/{len(prall)} PRs contain >=1 primary risk = {len(prrisk)/len(prall)*100:.1f}%")

# --- 31 S3-block decomposition (of 45 FP BLOCK) ---
fp=[c for c in changed if changed[c]['verdict'].startswith('FP')]
s3block=[c for c in fp if str(guard[c]['decisions']['S1S2S3_direct_evidence']).upper()=='BLOCK']
dec=Counter('never-covered' if changed[c]['verdict']=='FP_never_covered' else 'post-PR-temporal' for c in s3block)
print(f"\n31 S3-block FP decomposition: {dict(dec)}")
# additional matrix numbers
print("\nmatrix-derived: block-only accept 112/278={:.1f}%  block precision 166/337={:.1f}%  flagged 271/522={:.1f}%  primary-neg burden 251/4670={:.2f}%".format(112/278*100,166/337*100,271/522*100,251/4670*100))
json.dump({'PR_CI':[pr_lo,pr_hi],'repo_CI':[repo_lo,repo_hi],'merged':[mrisk,len(merged)],'PR_level':[len(prrisk),len(prall)],
  's3block_decomp':dict(dec),'per_tool_sum':s},open('results/major_revision/phase5_complete.json','w'),indent=1)
