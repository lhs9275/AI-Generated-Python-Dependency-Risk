#!/usr/bin/env python3
"""Tightening v2: CVE-alias reconciliation using WELL-FORMED bounded ranges only
(fixed/last_affected). A corrupted versions-list or unbounded introduced-only range
does NOT count as authoritative. If any aliased record's well-formed bounded range
EXCLUDES the version, the version is not affected by that CVE group."""
import csv, re, json, os
from datetime import datetime
from packaging.version import Version, InvalidVersion
D='results/tse_gap_closure/data/'; ARCH='results/major_revision/advisory_archive/'
def norm(n): return re.sub(r'[-_.]+','-',str(n).strip().lower())
def parse_pin(r):
    m=re.search(r'==\s*([0-9][0-9A-Za-z.\-+!]*)',str(r.get('new_spec') or ''))
    if m: return m.group(1)
    pv=r.get('pinned_version'); return str(pv).strip() if pv and str(pv).strip() not in('','None') else None
def prtime(r):
    try: return datetime.fromisoformat(r['created_at'].replace('Z','+00:00'))
    except: return None
def pub(v):
    try: return datetime.fromisoformat(v.get('published','').replace('Z','+00:00'))
    except: return None
def load_osv(pkg):
    p=ARCH+norm(pkg)+'.json'; return json.load(open(p)) if os.path.exists(p) else {'vulns':[]}
def cve_key(v):
    for a in [v.get('id')]+list(v.get('aliases') or []):
        if a.startswith('CVE-'): return a
    return v.get('id')

def record_verdict(ver, vuln, pkn):
    """Return (covers_wellformed, excludes_wellformed, covers_loose).
    wellformed = a range carrying fixed or last_affected. loose = unbounded range or versions-list."""
    try: v=Version(ver)
    except InvalidVersion: return (False,False,False)
    if vuln.get('withdrawn'): return (False,True,False)  # treat withdrawn as not-affected
    cov_wf=exc_wf=cov_loose=False
    for a in vuln.get('affected',[]):
        p=a.get('package',{})
        if p.get('ecosystem')!='PyPI' or norm(p.get('name',''))!=pkn: continue
        if ver in (a.get('versions') or []): cov_loose=True
        for rng in a.get('ranges',[]):
            if rng.get('type') not in ('ECOSYSTEM','SEMVER'): continue
            intro='0'; fixed=None; last=None
            for ev in rng.get('events',[]):
                if 'introduced' in ev: intro=ev['introduced']
                if 'fixed' in ev: fixed=ev['fixed']
                if 'last_affected' in ev: last=ev['last_affected']
            # validate bound tokens as PEP440; a commit-hash fixed => not well-formed
            def V(x):
                try: return Version(x)
                except InvalidVersion: return None
            lo=V(intro) if intro!='0' else None
            hi=V(fixed) if fixed is not None else None
            la=V(last) if last is not None else None
            wellformed = (fixed is not None and hi is not None) or (last is not None and la is not None)
            try: below_lo = (lo is not None and v<lo)
            except: below_lo=False
            inrange = (not below_lo) and (hi is None or v<hi) and (la is None or v<=la)
            if wellformed:
                if inrange: cov_wf=True
                else: exc_wf=True
            else:
                # unbounded / commit-fixed => loose coverage only
                if not below_lo and hi is None and la is None: cov_loose=True
    return (cov_wf, exc_wf, cov_loose)

def covering_prePR(ver, pkg, pt):
    d=load_osv(pkg); pkn=norm(pkg)
    groups={}
    for vuln in d.get('vulns',[]):
        cw,ew,cl=record_verdict(ver,vuln,pkn)
        k=cve_key(vuln)
        g=groups.setdefault(k,{'cw':False,'ew':False,'cl':False,'ids':[],'pubs':[]})
        g['cw']|=cw; g['ew']|=ew; g['cl']|=cl
        if cw or cl: g['ids'].append(vuln['id']); g['pubs'].append(pub(vuln))
    hits=[]
    for k,g in groups.items():
        affected = g['cw'] or (g['cl'] and not g['ew'])   # loose counts only if no well-formed exclusion
        if affected and (g['cw'] or g['cl']):
            p=[x for x in g['pubs'] if x is not None]
            prepr = any(x<=pt for x in p) if (p and pt) else False
            hits.append((k, prepr))
    return hits

rows=[r for r in csv.DictReader(open(D+'independent_labels.csv')) if r['change_type'] in ('add','version_change')]
fp=[]; fn=[]
for r in rows:
    ver=parse_pin(r); pt=prtime(r); cur=r['label_primary']
    if not ver or not pt: continue
    hits=covering_prePR(ver,r['package_name'],pt)
    any_cov=len(hits)>0
    det_p3=any(h[1] for h in hits)
    if cur=='P3_DIRECT_KNOWN_VULNERABILITY' and not det_p3:
        fp.append((r['package_name'],ver,'temporal' if any_cov else 'never-covered'))
    if cur=='NONE' and det_p3:
        fn.append((r['package_name'],ver,';'.join(h[0] for h in hits if h[1])[:60]))
from collections import Counter
print(f"FP={len(fp)} (never={sum(1 for x in fp if x[2]=='never-covered')}, temporal={sum(1 for x in fp if x[2]=='temporal')})")
print(f"FN={len(fn)}:")
for x in fn: print("   ",x[0],x[1],'via',x[2])
cur_p3=264; newp3=cur_p3-len(fp)+len(fn); tot=328-len(fp)+len(fn)
print(f"\nP3 264->{newp3}  total 328->{tot}  prevalence {tot/8752*100:.2f}%")
print(f"range: lower(FP only) {(328-len(fp))/8752*100:.2f}% .. upper {tot/8752*100:.2f}%")
