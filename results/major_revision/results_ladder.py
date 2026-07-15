#!/usr/bin/env python3
"""Full corrected tab:natural ladder with ABSOLUTE counts for every variant.
Blocked/Marginal columns are label-independent (frozen gate) and reproduce the
original; acceptance and primary-negative-block rates are recomputed under the
corrected labels."""
import csv, json, os
BASE=os.path.dirname(os.path.abspath(__file__))
D=os.path.join(BASE,'..','tse_gap_closure','data')
labels={r['change_id']:r for r in csv.DictReader(open(os.path.join(D,'independent_labels.csv')))}
guard={json.loads(l)['change_id']:json.loads(l) for l in open(os.path.join(D,'guard_outputs.jsonl'))}
changed={r['change_id']:r for r in csv.DictReader(open(os.path.join(BASE,'changed_rows_final.csv')))}
PRIMARY={'P1_NONEXISTENT_PACKAGE','P2_INVALID_VERSION_SPEC','P3_DIRECT_KNOWN_VULNERABILITY'}
def newlab(c): return changed[c]['new_label'] if c in changed else labels[c]['label_primary']
def orig(c): return labels[c]['label_primary']
VARIANTS=['B0_no_gate','B1_scanner_fail_open','B1b_scanner_fail_closed','S1_existence',
          'S1S2_version','S1S2S3_direct_evidence','S1S2S3_plus_license','B3_full_guard']
def blocked(cid,st): return str(guard[cid]['decisions'][st]).upper()=='BLOCK'
gated=[c for c in guard if labels.get(c,{}).get('change_type') in ('add','version_change')]

def ladder(labelfn):
    prim=[c for c in gated if labelfn(c) in PRIMARY]; neg=[c for c in gated if labelfn(c)=='NONE']
    rows={}
    for st in VARIANTS:
        tot_block=sum(1 for c in gated if blocked(c,st))
        pb=sum(1 for c in prim if blocked(c,st)); nb=sum(1 for c in neg if blocked(c,st))
        rows[st]={'blocked':tot_block,'P':len(prim),'N':len(neg),
                  'prim_accept_k':len(prim)-pb,'prim_accept_pct':round((len(prim)-pb)/len(prim)*100,1),
                  'neg_block_k':nb,'neg_block_pct':round(nb/len(neg)*100,2)}
    return len(prim),len(neg),rows

for name,fn in [('CORRECTED',newlab)]:
    P,N,rows=ladder(fn)
    print(f"{name}: primary={P} primary-negative={N} total_retained={len(gated)}")
    prev=0
    for st in VARIANTS:
        r=rows[st]; marg=r['blocked']-prev if st.startswith(('S','B3')) else None
        prev=r['blocked'] if st.startswith(('S','B3','B0')) else prev
        print(f"  {st:26} blocked={r['blocked']:4} accept={r['prim_accept_k']}/{P}={r['prim_accept_pct']}%  negBLOCK={r['neg_block_k']}/{N}={r['neg_block_pct']}%")

# B3 full matrix (BLOCK/WARN/PASS) under corrected labels
def dec(c,st): return str(guard[c]['decisions'][st]).upper()
prim=[c for c in gated if newlab(c) in PRIMARY]; neg=[c for c in gated if newlab(c)=='NONE']
from collections import Counter
pm=Counter(dec(c,'B3_full_guard') for c in prim); nm=Counter(dec(c,'B3_full_guard') for c in neg)
print("\nB3 primary  :",dict(pm))
print("B3 primary-neg:",dict(nm))
# construct-conditioned shares
tot_block=pm['BLOCK']+nm['BLOCK']; tot_bw=pm['BLOCK']+pm['WARN']+nm['BLOCK']+nm['WARN']
print(f"block-share prim/all = {pm['BLOCK']}/{tot_block} = {pm['BLOCK']/tot_block*100:.1f}%")
print(f"block-or-warn prim/all = {pm['BLOCK']+pm['WARN']}/{tot_bw} = {(pm['BLOCK']+pm['WARN'])/tot_bw*100:.1f}%")
print(f"neg intervention = {nm['BLOCK']+nm['WARN']}/{N} = {(nm['BLOCK']+nm['WARN'])/N*100:.2f}%")
print(f"detection block-or-warn = {pm['BLOCK']+pm['WARN']}/{P} = {(pm['BLOCK']+pm['WARN'])/P*100:.1f}%")
print(f"block-only recall = {pm['BLOCK']}/{P} = {pm['BLOCK']/P*100:.1f}%")
print(f"PASS residual = {pm['PASS']}/{P} = {pm['PASS']/P*100:.1f}%")
