"""npm re-verify via OSV server-side /query{version} (authoritative semver) + published<=PR temporal."""
import json, urllib.request, time, os
from datetime import datetime
ARCH='results/major_revision/npm_qcache/'; os.makedirs(ARCH,exist_ok=True)
PRT={}
for _l in open('results/aidev_npm_sample.jsonl'):
    _d=json.loads(_l); _u=_d.get('html_url'); _c=_d.get('created_at')
    if _u and _c: PRT[_u]=_c
def prtime(r):
    c=PRT.get(r.get('pr'))
    if c:
        try: return datetime.fromisoformat(c.replace('Z','+00:00'))
        except: return None
    return None
def qkey(n,v): 
    import re; return re.sub(r'[^a-z0-9._@-]','_',(n+'@@'+str(v)).lower().replace('/','__'))
def osv_qv(name,ver):
    cp=ARCH+qkey(name,ver)+'.json'
    if os.path.exists(cp): return json.load(open(cp))
    body=json.dumps({"package":{"name":name,"ecosystem":"npm"},"version":str(ver)}).encode()
    for _ in range(3):
        try:
            req=urllib.request.Request("https://api.osv.dev/v1/query",data=body,headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=20) as r: d=json.load(r)
            out=[{'id':v['id'],'published':v.get('published')} for v in d.get('vulns',[])]
            json.dump(out,open(cp,'w')); time.sleep(0.02); return out
        except Exception: time.sleep(0.4)
    json.dump([],open(cp,'w')); return []
def pub(s):
    try: return datetime.fromisoformat(str(s).replace('Z','+00:00'))
    except: return None

recs=[json.loads(l) for l in open('results/npm_risk_labels.jsonl')]
fp=[];fn=[]
for r in recs:
    name=r.get('name'); ver=r.get('resolved') or r.get('version'); pt=prtime(r)
    cur=r.get('label') or r.get('label_primary') or 'NONE'
    if not name or not ver: continue
    advs=osv_qv(name,ver)  # OSV server-side: advisories affecting THIS version (any time)
    det_prepr = any((pub(a['published']) and pt and pub(a['published'])<=pt) for a in advs)
    if cur=='F3' and not det_prepr: fp.append((name,ver))
    if cur=='NONE' and det_prepr: fn.append((name,ver))
from collections import Counter
cur_f3=sum(1 for r in recs if (r.get('label') or r.get('label_primary'))=='F3')
cur_risk=sum(1 for r in recs if (r.get('label') or r.get('label_primary')) in ('F1','F2','F3'))
new_risk=cur_risk-len(fp)+len(fn)
print(f"npm F3 FP: {len(fp)} {[x[0] for x in fp]}")
print(f"npm F3 FN: {len(fn)} {[(x[0],x[1]) for x in fn][:10]}")
print(f"npm F3 {cur_f3}->{cur_f3-len(fp)+len(fn)}  total risk {cur_risk}->{new_risk}  prevalence {cur_risk/len(recs)*100:.2f}%->{new_risk/len(recs)*100:.2f}%")
json.dump({'fp':fp,'fn':fn,'cur_risk':cur_risk,'new_risk':new_risk,'method':'OSV /query{version} server-side'},open('results/major_revision/npm_rematch2.json','w'),indent=1)
