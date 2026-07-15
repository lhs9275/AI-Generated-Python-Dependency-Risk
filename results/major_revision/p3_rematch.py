#!/usr/bin/env python3
"""Deterministic OSV affected-range P3 re-match (bidirectional). No new human labeling.
fixed=exclusive, last_affected=inclusive, introduced inclusive ('0'=-inf), PEP440."""
import csv, re, json, os, sys, time, urllib.request, hashlib
from datetime import datetime, timezone
from packaging.version import Version, InvalidVersion

D='results/tse_gap_closure/data/'
ARCH='results/major_revision/advisory_archive/'
os.makedirs(ARCH, exist_ok=True)

def norm(n): return re.sub(r'[-_.]+','-',str(n).strip().lower())
def parse_pin(r):
    s=str(r.get('new_spec') or '')
    m=re.search(r'==\s*([0-9][0-9A-Za-z.\-+!]*)',s)
    if m: return m.group(1)
    pv=r.get('pinned_version')
    if pv and str(pv).strip() not in ('','None'): return str(pv).strip()
    return None
def prtime(r):
    try: return datetime.fromisoformat(r['created_at'].replace('Z','+00:00'))
    except: return None

def osv_by_pkg(pkg):
    cp=ARCH+norm(pkg)+'.json'
    if os.path.exists(cp):
        return json.load(open(cp))
    body=json.dumps({"package":{"name":pkg,"ecosystem":"PyPI"}}).encode()
    for _ in range(3):
        try:
            req=urllib.request.Request("https://api.osv.dev/v1/query",data=body,headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=20) as r: d=json.load(r)
            json.dump(d,open(cp,'w')); time.sleep(0.03); return d
        except Exception: time.sleep(0.5)
    json.dump({"vulns":[]},open(cp,'w')); return {"vulns":[]}

def in_range(ver, vuln, pkgnorm):
    try: v=Version(ver)
    except InvalidVersion: return None
    for a in vuln.get('affected',[]):
        p=a.get('package',{})
        if p.get('ecosystem')!='PyPI' or norm(p.get('name',''))!=pkgnorm: continue
        if a.get('versions') and ver in a['versions']: return True
        for rng in a.get('ranges',[]):
            if rng.get('type') not in ('ECOSYSTEM','SEMVER'): continue
            intro='0'; fixed=None; last=None
            for ev in rng.get('events',[]):
                if 'introduced' in ev: intro=ev['introduced']
                if 'fixed' in ev: fixed=ev['fixed']
                if 'last_affected' in ev: last=ev['last_affected']
            try:
                lo=Version(intro) if intro!='0' else None
                if lo and v<lo: continue
                if fixed is not None and v>=Version(fixed): continue
                if last is not None and v>Version(last): continue
                return True
            except InvalidVersion: continue
    return False

def published(vuln):
    try: return datetime.fromisoformat(vuln.get('published','').replace('Z','+00:00'))
    except: return None

rows=[r for r in csv.DictReader(open(D+'independent_labels.csv')) if r['change_type'] in ('add','version_change')]
ledger=[]
n=0
for r in rows:
    ver=parse_pin(r); pkg=r['package_name']; pt=prtime(r)
    cur=r['label_primary']
    if not ver or not pt:
        continue
    n+=1
    d=osv_by_pkg(pkg)
    pkn=norm(pkg)
    covering=[]   # advisories whose range covers ver
    covering_prepr=[]
    for vuln in d.get('vulns',[]):
        c=in_range(ver,vuln,pkn)
        if c is True:
            covering.append(vuln['id'])
            pub=published(vuln)
            if pub and pub<=pt: covering_prepr.append(vuln['id'])
    det_p3 = len(covering_prepr)>0
    # classification vs current (P3 axis only; leave P1 out of scope, P2 stays P2)
    verdict='same'
    if cur=='P3_DIRECT_KNOWN_VULNERABILITY' and not det_p3: verdict='FP(P3->NONE)'
    elif cur=='NONE' and det_p3: verdict='FN(NONE->P3)'
    ledger.append({'change_id':r['change_id'],'package':pkg,'version':ver,'pr_time':r['created_at'],
                   'current':cur,'det_covering_prePR':';'.join(covering_prepr[:3]),
                   'det_covering_any':';'.join(covering[:3]),'det_p3':det_p3,'verdict':verdict})

with open('results/major_revision/p3_rematch_ledger.csv','w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(ledger[0].keys())); w.writeheader()
    for x in ledger: w.writerow(x)

from collections import Counter
vc=Counter(x['verdict'] for x in ledger)
print("evaluated pinned changes:",n)
print("verdicts:",dict(vc))
fp=[x for x in ledger if x['verdict'].startswith('FP')]
fn=[x for x in ledger if x['verdict'].startswith('FN')]
print(f"\nFP (P3->NONE): {len(fp)}")
print(f"FN (NONE->P3): {len(fn)}")
print("FP by package:",Counter(x['package'].lower() for x in fp).most_common(8))
print("FN by package:",Counter(x['package'].lower() for x in fn).most_common(8))
# corrected P3 count
cur_p3=sum(1 for r in rows if r['label_primary']=='P3_DIRECT_KNOWN_VULNERABILITY')
new_p3=cur_p3-len(fp)+len(fn)
print(f"\nP3: {cur_p3} -> {new_p3}  (total primary 328 -> {328-len(fp)+len(fn)})")
print(f"prevalence: 3.7% -> {(328-len(fp)+len(fn))/8752*100:.2f}%")
