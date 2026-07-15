#!/usr/bin/env python3
"""Tightening pass: dup-alias/unbounded handling, FP never-vs-temporal split,
FN bounded-provenance test, 404-version P3 flag. Deterministic, offline (uses archive)."""
import csv, re, json, os
from datetime import datetime
from packaging.version import Version, InvalidVersion
D='results/tse_gap_closure/data/'; ARCH='results/major_revision/advisory_archive/'
def norm(n): return re.sub(r'[-_.]+','-',str(n).strip().lower())
def parse_pin(r):
    m=re.search(r'==\s*([0-9][0-9A-Za-z.\-+!]*)',str(r.get('new_spec') or ''))
    if m: return m.group(1)
    pv=r.get('pinned_version')
    return str(pv).strip() if pv and str(pv).strip() not in('','None') else None
def prtime(r):
    try: return datetime.fromisoformat(r['created_at'].replace('Z','+00:00'))
    except: return None
def pub(v):
    try: return datetime.fromisoformat(v.get('published','').replace('Z','+00:00'))
    except: return None
def load_osv(pkg):
    p=ARCH+norm(pkg)+'.json'
    return json.load(open(p)) if os.path.exists(p) else {'vulns':[]}

def range_verdict(ver, vuln, pkn):
    """Returns (covers: True/False, bounded: bool) for this vuln vs ver."""
    try: v=Version(ver)
    except InvalidVersion: return (None, None)
    if vuln.get('withdrawn'): return (False, True)
    covers=False; bounded=False; any_pypi=False
    for a in vuln.get('affected',[]):
        p=a.get('package',{})
        if p.get('ecosystem')!='PyPI' or norm(p.get('name',''))!=pkn: continue
        any_pypi=True
        vers=a.get('versions') or []
        if vers: bounded=True
        if ver in vers: covers=True
        for rng in a.get('ranges',[]):
            if rng.get('type') not in ('ECOSYSTEM','SEMVER'): continue
            intro='0'; fixed=None; last=None
            for ev in rng.get('events',[]):
                if 'introduced' in ev: intro=ev['introduced']
                if 'fixed' in ev: fixed=ev['fixed']
                if 'last_affected' in ev: last=ev['last_affected']
            if fixed is not None or last is not None: bounded=True
            try:
                lo=Version(intro) if intro!='0' else None
                if lo and v<lo: continue
                if fixed is not None and v>=Version(fixed): continue
                if last is not None and v>Version(last): continue
                covers=True
            except InvalidVersion: continue
    return (covers, bounded)

def aliases(v): return set([v.get('id')]+list(v.get('aliases') or []))

def covering_advisories(ver, pkg, pt):
    """Return list of (id, covers_prePR) after dup-alias/unbounded reconciliation."""
    d=load_osv(pkg); pkn=norm(pkg)
    recs=[]
    for vuln in d.get('vulns',[]):
        cov,bnd=range_verdict(ver,vuln,pkn)
        recs.append({'id':vuln['id'],'al':aliases(vuln),'cov':cov,'bnd':bnd,'pub':pub(vuln),'wd':bool(vuln.get('withdrawn'))})
    # dup-alias reconciliation: within an alias group, a BOUNDED record that EXCLUDES overrides an unbounded that includes
    out=[]
    for r in recs:
        if r['cov'] is not True or r['wd']: continue
        if not r['bnd']:
            # unbounded include: check for aliased bounded sibling excluding this version
            sib_excl=any((s['al']&r['al']) and s['bnd'] and s['cov'] is False for s in recs)
            if sib_excl:
                continue  # datasette-class: trust bounded authoritative record
        prepr = r['pub'] is not None and pt is not None and r['pub']<=pt
        out.append((r['id'],prepr))
    return out

rows=[r for r in csv.DictReader(open(D+'independent_labels.csv')) if r['change_type'] in ('add','version_change')]
# reload ledger verdicts
led={r['change_id']:r for r in csv.DictReader(open('results/major_revision/p3_rematch_ledger.csv'))}

fp=[]; fn=[]
for r in rows:
    ver=parse_pin(r); pt=prtime(r); cur=r['label_primary']
    if not ver or not pt: continue
    cov=covering_advisories(ver,r['package_name'],pt)
    any_cov=len(cov)>0
    prepr=[c for c in cov if c[1]]
    det_p3=len(prepr)>0
    if cur=='P3_DIRECT_KNOWN_VULNERABILITY' and not det_p3:
        fp.append((r['change_id'],r['package_name'],ver,'temporal' if any_cov else 'never-covered'))
    if cur=='NONE' and det_p3:
        fn.append((r['change_id'],r['package_name'],ver,';'.join(c[0] for c in prepr[:2])))

from collections import Counter
print("=== TIGHTENED ===")
print(f"FP (P3->NONE): {len(fp)}  |  never-covered={sum(1 for x in fp if x[3]=='never-covered')}  temporal={sum(1 for x in fp if x[3]=='temporal')}")
print("  FP by pkg:",Counter(x[1].lower() for x in fp).most_common(8))
print(f"FN (NONE->P3) after dup-alias fix: {len(fn)}")
for x in fn: print(f"    {x[1]} {x[2]}  via {x[3]}")
# 404-version check among current same-P3
same_p3=[r for r in rows if r['label_primary']=='P3_DIRECT_KNOWN_VULNERABILITY' and led.get(r['change_id'],{}).get('verdict')=='same']
val404=[r for r in same_p3 if str(r.get('valid_version_at_pr_time','')).lower()=='false']
print(f"\ncurrent valid-P3 (same): {len(same_p3)} ; of which valid_version_at_pr_time==False (should be P2): {len(val404)}")
cur_p3=sum(1 for r in rows if r['label_primary']=='P3_DIRECT_KNOWN_VULNERABILITY')
newp3=cur_p3-len(fp)+len(fn)
tot=328-len(fp)+len(fn)
print(f"\nP3: {cur_p3} -> {newp3}   total primary 328 -> {tot}   prevalence -> {tot/8752*100:.2f}%")
print(f"FP-only lower bound: {(328-len(fp))/8752*100:.2f}%  ({328-len(fp)}/8752)")
