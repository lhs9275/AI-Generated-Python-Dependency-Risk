#!/usr/bin/env python3
"""Socket *shallow* batch diagnostic on the risk-inclusive external corpus.

`socket package score` (deep) costs 100 quota units PER package call, so a
93-package sweep is infeasible on the free tier. `socket package shallow` costs
100 units PER CALL regardless of how many packages are passed, and returns each
package's own (non-transitive) supply-chain alerts -- which is exactly the unit
of analysis here (we evaluate the single pinned package a PR added, not its
transitive closure). So the whole corpus is scored in ONE batched call.

We query version-pinned purls (pkg:pypi/<name>@<version>) so that version-
specific findings and non-existent version pins (S2) are represented, and treat
a purl Socket cannot resolve as a non-existent / supply-chain block (the S1
typosquat/malware and S2 invalid-version cases).

IMPORTANT -- current-SaaS, non-frozen, diagnostic (June 2026), exactly analogous
to the paper's anachronistic live pip-audit cell. Not a frozen comparator.

Run (needs SOCKET_SECURITY_API_KEY and ~100 quota units available):
  python -m pipeline.external_realrisk.scan_socket_shallow \
      --out results/external_realrisk_py/socket_shallow.json
"""
import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from pipeline.external_realrisk.scan_commercial import family_of, added_pin

# Alert types that represent a genuine PR-time supply-chain block signal (as
# opposed to benign capability/info alerts like hasNativeCode, filesystemAccess).
RISK_TYPES = {
    "malware", "gptMalware", "gptSecurity", "gptAnomaly", "typosquat",
    "didYouMean", "knownVulnerability", "criticalCVE", "cve", "mildCVE",
    "potentialVulnerability", "obfuscatedCode", "shellAccessRisk",
    "suspiciousString", "trojan", "telemetry", "deprecated", "missingAuthor",
    "unmaintained", "nonpermissiveLicense", "explicitlyUnknownLicense",
}
RISK_SEVERITIES = {"high", "critical"}


def parse_pin(pin):
    """('name','version') from an added requirement pin like 'boto3==1.43.36'."""
    if not pin:
        return None, None
    s = pin.split(";")[0].strip()
    if "==" in s:
        n, v = s.split("==", 1)
        return n.strip(), v.strip()
    return s.replace(" ", ""), None


def gather(corpus):
    """unique purls + bookkeeping: name->family(s), purl->(name,family)."""
    ad, bd = corpus / "manifests_after", corpus / "manifests_before"
    items = []   # (manifest, family, name, version, purl)
    for m in sorted(ad.glob("*.txt")):
        fam = family_of(m.name)
        name, ver = parse_pin(added_pin(bd / m.name, m))
        if not name:
            continue
        purl = f"pkg:pypi/{name}" + (f"@{ver}" if ver else "")
        items.append({"manifest": m.name, "family": fam, "name": name,
                      "version": ver, "purl": purl})
    return items


def socket_shallow(purls):
    """One batched `socket package shallow` call. Returns parsed list or raises."""
    cmd = ["socket", "package", "shallow", *purls, "--json"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    j = json.loads(p.stdout)
    if not j.get("ok"):
        raise RuntimeError(f"socket shallow failed: {str(j)[:300]}")
    return j.get("data") or []


# Vulnerability-bearing alert types (vs benign capability/heuristic alerts such
# as filesystemAccess, urlStrings, usesEval, gptAnomaly, hasNativeCode).
VULN_TYPES = {"cve", "mildCVE", "mediumCVE", "criticalCVE", "knownVulnerability",
              "malware", "gptMalware", "typosquat"}


def policy_verdicts(entry):
    """Map one shallow entry to BLOCK/PASS under several PR-time policies.

    Socket scores at the package level and emits an `action` recommendation per
    alert (ignore < monitor < warn < error) plus a `notFound` alert when it has
    no indexed record of the pinned package@version. The policies differ in what
    they treat as a *blocking* signal:
      native      : Socket's own gate -- action in {warn,error}. (out-of-box)
      diagnostic  : notFound OR any high/critical-severity alert. (existence +
                    severity, the analog of our S1/S2/S3 gate)
      diagnostic_v: notFound OR (vulnerability-type alert at high/critical sev).
                    (excludes high-sev *capability* alerts like obfuscatedFile)
    """
    alerts = entry.get("alerts") or []
    types = {a.get("type") for a in alerts if isinstance(a, dict)}
    sevs = {a.get("severity") for a in alerts if isinstance(a, dict)}
    acts = {a.get("action") for a in alerts if isinstance(a, dict)}
    nf = "notFound" in types
    hi = bool(sevs & RISK_SEVERITIES)
    vuln_hi = bool(types & VULN_TYPES) and hi
    return {
        "native": ("error" in acts or "warn" in acts),
        "diagnostic": (nf or hi),
        "diagnostic_v": (nf or vuln_hi),
    }, {"notFound": nf, "high_or_crit": hi, "vuln_high": vuln_hi,
        "actions": sorted(a for a in acts if a)}


# back-compat single-verdict helper (primary policy = diagnostic)
def classify(entry):
    v, _ = policy_verdicts(entry)
    return ("block" if v["diagnostic"] else "pass"), []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="data/external_realrisk_py")
    ap.add_argument("--out", default="results/external_realrisk_py/socket_shallow.json")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the purls/cost plan without calling Socket")
    a = ap.parse_args()
    corpus = Path(a.corpus)

    items = gather(corpus)
    purls = sorted({it["purl"] for it in items})
    fam_count = defaultdict(int)
    for it in items:
        fam_count[it["family"]] += 1
    print(f"manifests: {len(items)}  unique purls: {len(purls)}  "
          f"families: {dict(fam_count)}")
    print(f"cost: ONE shallow call = 100 quota units (flat, regardless of count)")
    if a.dry_run:
        for p in purls[:8]:
            print("  ", p)
        print("  ...")
        return

    # Cache the raw batched response so the expensive (100-unit) call is made at
    # most once; a re-run (e.g. after fixing aggregation) reuses it for free.
    raw_path = Path(a.out).with_name("socket_shallow_raw.json")
    if raw_path.exists():
        data = json.loads(raw_path.read_text())
        print(f"[reusing cached raw response: {raw_path} ({len(data)} entries)]")
    else:
        data = socket_shallow(purls)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(json.dumps(data, indent=2))
        print(f"[saved raw response: {raw_path} ({len(data)} entries)]")
    # index returned entries by purl and by name@version and by name
    by_purl, by_nv, by_name = {}, {}, {}
    for e in data:
        nm, ver = e.get("name"), e.get("version")
        if nm:
            by_name.setdefault(nm, e)
            if ver:
                by_nv[f"{nm}@{ver}"] = e
        purl = e.get("purl") or e.get("id")
        if purl:
            by_purl[purl] = e

    POLICIES = ["native", "diagnostic", "diagnostic_v"]
    rows = []
    agg = {p: defaultdict(int) for p in POLICIES}
    for it in items:
        fam, nm, ver = it["family"], it["name"], it["version"]
        e = (by_nv.get(f"{nm}@{ver}") if ver else None) or by_name.get(nm)
        if e is None:                       # purl unresolvable == notFound == SC risk
            verdicts = {p: True for p in POLICIES}
            evidence = {"resolved": False, "notFound": True}
        else:
            verdicts, evidence = policy_verdicts(e)
            evidence["resolved"] = True
        risky = fam in ("S1", "S2", "S3")
        rows.append({**it, "resolved": e is not None,
                     "verdicts": verdicts, "evidence": evidence})
        for p in POLICIES:
            blocked = bool(verdicts[p])
            if risky:
                agg[p]["risk_n"] += 1; agg[p]["risk_block"] += blocked
                agg[p][f"{fam}_n"] += 1; agg[p][f"{fam}_block"] += blocked
            else:
                agg[p]["norm_n"] += 1; agg[p]["norm_block"] += blocked

    def summarize(a):
        rn, nn = a["risk_n"], a["norm_n"]
        tp, fp = a["risk_block"], a["norm_block"]
        return {
            "block_recall": round(tp / rn, 4) if rn else None,
            "false_block_rate": round(fp / nn, 4) if nn else None,
            "precision": round(tp / (tp + fp), 4) if (tp + fp) else None,
            **{f"{f}_recall": (round(a[f"{f}_block"] / a[f"{f}_n"], 4)
                               if a.get(f"{f}_n") else None) for f in ("S1", "S2", "S3")},
            **{f"{f}_block": a.get(f"{f}_block", 0) for f in ("S1", "S2", "S3")},
            **{f"{f}_n": a.get(f"{f}_n", 0) for f in ("S1", "S2", "S3")},
            "n_risk": rn, "n_normal": nn,
        }

    summ = {p: summarize(agg[p]) for p in POLICIES}
    summ["_meta"] = {
        "n_resolved": sum(1 for r in rows if r["resolved"]),
        "n_unresolved": sum(1 for r in rows if not r["resolved"]),
        "policy_defs": {
            "native": "Socket's own gate: alert action in {warn,error}",
            "diagnostic": "notFound OR any high/critical-severity alert",
            "diagnostic_v": "notFound OR (vulnerability-type alert at high/critical severity)",
        },
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "method": "socket package shallow (batched, version-pinned purls)",
        "caveat": "current-SaaS non-frozen diagnostic (June 2026); "
                  "shallow = package-own alerts, not transitive; "
                  "analogous to live pip-audit cell",
        "summary": summ,
        "raw_count": len(data),
        "per_manifest": rows}, indent=2))
    print(json.dumps(summ, indent=2))


if __name__ == "__main__":
    main()
