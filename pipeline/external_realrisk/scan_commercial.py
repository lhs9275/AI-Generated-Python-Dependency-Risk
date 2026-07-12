#!/usr/bin/env python3
"""Live commercial-scanner diagnostic on the risk-inclusive external corpus.

Runs Snyk and/or Socket against each `manifests_after/<id>.txt` (a requirements
pin) and scores BLOCK / detect against the corpus ground truth (S1/S2/S3 risky,
NEG normal), producing a table directly comparable to the frozen pip-audit
negative-control (Table V).

IMPORTANT — this is a *current-SaaS, non-frozen, diagnostic* comparison, exactly
analogous to the paper's anachronistic live pip-audit cell: Socket/Snyk are
closed, continuously-updated services and CANNOT be frozen against the
2026-05-22 snapshot. Results must be reported with that caveat; they are a
scope diagnostic, not a reproducible frozen comparator.

Auth: Snyk needs `snyk auth` or SNYK_TOKEN; Socket needs SOCKET_SECURITY_API_KEY.
Both require a free account (user-side credential, like the Zenodo DOI step).

Preflight-only (no tokens needed) to see what it WOULD run:
  python -m pipeline.external_realrisk.scan_commercial --preflight

Full run (after providing tokens):
  python -m pipeline.external_realrisk.scan_commercial \
      --corpus data/external_realrisk_py \
      --out results/external_realrisk_py/commercial_scan.json
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

FAMILY_OF = {"S1": "S1", "S2": "S2", "S3": "S3", "NEG": "NEG"}

# Inter-call delay for Socket to stay under the free-tier per-window rate limit
# (a burst of 107 unthrottled calls returns HTTP 429). Overridable via --socket-throttle.
SOCKET_THROTTLE_S = 2.0


def family_of(manifest_name):
    pre = manifest_name.split("-", 1)[0].split("_", 1)[0]
    return FAMILY_OF.get(pre, "NEG" if manifest_name.startswith("NEG") else "UNK")


def added_pin(before_path, after_path):
    """The single dependency the patch added (after - before)."""
    b = set(Path(before_path).read_text().splitlines()) if before_path.exists() else set()
    for ln in Path(after_path).read_text().splitlines():
        s = ln.strip()
        if s and not s.startswith("#") and ln not in b:
            return s
    return None


def have(cmd):
    return shutil.which(cmd) is not None


def preflight(corpus):
    after = sorted((corpus / "manifests_after").glob("*.txt"))
    fam = defaultdict(int)
    for m in after:
        fam[family_of(m.name)] += 1
    print("== external-realrisk commercial-scan preflight ==")
    print(f"manifests_after: {len(after)} files  families: {dict(fam)}")
    print(f"  expected: S1=20 S2=12 S3=20 NEG=55  (risky=52, normal=55)")
    tools = {
        "snyk": (have("snyk"), bool(os.getenv("SNYK_TOKEN"))),
        "socket": (have("socket"), bool(os.getenv("SOCKET_SECURITY_API_KEY"))),
    }
    print("\ntool readiness (cli_installed, token_set):")
    for t, (cli, tok) in tools.items():
        print(f"  {t:8s} cli={cli}  token={tok}  -> {'READY' if cli and tok else 'BLOCKED'}")
    if not all(cli and tok for cli, tok in tools.values()):
        print("\nTO ENABLE (user-side, one-time):")
        print("  npm i -g snyk @socketsecurity/cli")
        print("  snyk auth                 # or export SNYK_TOKEN=<token from app.snyk.io>")
        print("  export SOCKET_SECURITY_API_KEY=<key from socket.dev account>")
        print("  python -m pipeline.external_realrisk.scan_commercial \\")
        print("      --out results/external_realrisk_py/commercial_scan.json")
    return tools


def run_snyk(manifest):
    """Return ('block'|'pass'|'error', raw). snyk test blocks only on a known
    vulnerability in a resolvable inventory -> structurally cannot represent
    non-existent (S1) or invalid-version (S2) pins (they fail resolution)."""
    try:
        p = subprocess.run(
            ["snyk", "test", f"--file={manifest}", "--json",
             "--package-manager=pip"],
            capture_output=True, text=True, timeout=120)
    except Exception as e:
        return "error", str(e)
    out = (p.stdout or "") + (p.stderr or "")
    try:
        j = json.loads(p.stdout)
        n = j.get("uniqueCount", len(j.get("vulnerabilities", [])))
        return ("block" if n and n > 0 else "pass"), out[:500]
    except Exception:
        low = out.lower()
        if "could not" in low or "failed to resolve" in low or "not found" in low:
            return "error", out[:500]   # unresolvable -> scope miss, not a block
        return "pass", out[:500]


# Supply-chain alert types / severities that warrant a PR-time block. Socket
# emits informational alerts on clean packages too, so a bare bool(alerts) would
# false-positive on NEG; we gate on risk-bearing types or high/critical severity.
RISK_ALERT_TYPES = {
    "malware", "gptMalware", "gptSecurity", "gptAnomaly", "typosquat",
    "didYouMean", "knownVulnerability", "criticalCVE", "cve", "mildCVE",
    "potentialVulnerability", "installScripts", "shellAccess", "obfuscatedCode",
    "nonexistentPackage", "missingDependency", "deprecated", "unmaintained",
}


SOCKET_CACHE_DIR = None   # set in main(); per-name disk cache to avoid re-spending quota


def _cache_path(name):
    if not SOCKET_CACHE_DIR:
        return None
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    return SOCKET_CACHE_DIR / f"{safe}.json"


def _socket_call(name):
    """One `socket package score`, disk-cached by name. NO in-call retry on 429.

    Socket's free-tier limiter is a token bucket: bursts drain it and every call
    then returns HTTP 429 (which does NOT cost quota). Retrying in-call just wastes
    wall-clock and re-penalizes the token, so on 429 we return immediately and let
    the inter-call throttle refill the bucket; the disk cache makes the run
    resumable, so 429'd names are simply re-attempted on the next pass. Only
    definitive answers (ok=true or 404 not-found) are cached."""
    cp = _cache_path(name)
    if cp and cp.exists():
        try:
            return {**json.loads(cp.read_text()), "_cached": True}
        except Exception:
            pass
    try:
        p = subprocess.run(["socket", "package", "score", "pypi", name, "--json"],
                           capture_output=True, text=True, timeout=120)
    except Exception as e:
        return {"ok": False, "error": f"subprocess:{e}"}
    try:
        j = json.loads(p.stdout)
    except Exception:
        return {"ok": False, "error": "parse",
                "raw": ((p.stdout or "") + (p.stderr or ""))[:300]}
    data = j.get("data") if isinstance(j.get("data"), dict) else {}
    code = data.get("code")
    if cp and (j.get("ok") is True or code == 404):
        cp.parent.mkdir(parents=True, exist_ok=True)
        cp.write_text(json.dumps(j))
    return j


def run_socket(pin):
    """Return ('block'|'pass'|'error', raw_dict). Socket's supply-chain intel can
    flag malware/typosquat/known-vuln names that vuln scanners miss -> the
    interesting differentiator vs Snyk/pip-audit. Scored at PACKAGE-NAME level
    (Socket's product); version-existence (S2) is out of scope, like pip-audit."""
    if not pin:
        return "error", {"reason": "no_pin"}
    name = pin.replace("==", "@").split(";")[0].strip()
    name = name.split("@", 1)[0].strip()
    if not name:
        return "error", {"reason": "no_name"}
    j = _socket_call(name)
    cached = bool(j.get("_cached"))
    data = j.get("data") if isinstance(j.get("data"), dict) else {}
    if j.get("ok") is False:
        code = data.get("code")
        if code == 404:   # name not resolvable on PyPI/Socket -> non-existent risk
            return "block", {"reason": "not_found", "code": 404, "_cached": cached}
        return "error", {"reason": j.get("error") or j.get("cause") or "api_error",
                         "code": code, "_cached": cached}
    self_ = data.get("self") or {}
    sc = self_.get("score") or {}
    alerts = self_.get("alerts") or []
    alert_info = [{"type": a.get("type"), "severity": a.get("severity")}
                  for a in alerts if isinstance(a, dict)]
    risk_alerts = [a for a in alert_info
                   if a["type"] in RISK_ALERT_TYPES
                   or a["severity"] in ("high", "critical")]
    raw = {"supplyChain": sc.get("supplyChain"), "vulnerability": sc.get("vulnerability"),
           "overall": sc.get("overall"), "alerts": alert_info, "risk_alerts": risk_alerts,
           "_cached": cached}
    return ("block" if risk_alerts else "pass"), raw


def score(corpus, tools, families=None, neg_cap=None):
    after_dir = corpus / "manifests_after"
    before_dir = corpus / "manifests_before"
    rows, agg = [], defaultdict(lambda: defaultdict(int))
    neg_seen = 0
    for m in sorted(after_dir.glob("*.txt")):
        fam = family_of(m.name)
        if families and fam not in families:
            continue
        if fam == "NEG" and neg_cap is not None:
            if neg_seen >= neg_cap:
                continue
            neg_seen += 1
        risky = fam in ("S1", "S2", "S3")
        pin = added_pin(before_dir / m.name, m)
        rec = {"manifest": m.name, "family": fam, "risky": risky, "pin": pin}
        for t, (cli, tok) in tools.items():
            if not (cli and tok):
                continue
            if t == "socket":
                import time
                verdict, raw = run_socket(pin)
                if not raw.get("_cached"):
                    time.sleep(SOCKET_THROTTLE_S)   # stay under free-tier rate limit
            else:
                verdict, raw = run_snyk(m)
            rec[t] = verdict
            rec[f"{t}_raw"] = raw
            blocked = verdict == "block"
            agg[t]["err"] += (verdict == "error")
            if risky:
                agg[t]["risk_n"] += 1
                agg[t]["risk_block"] += blocked
                agg[t][f"{fam}_n"] += 1
                agg[t][f"{fam}_block"] += blocked
            else:
                agg[t]["norm_n"] += 1
                agg[t]["norm_block"] += blocked
        rows.append(rec)
    summ = {}
    for t, a in agg.items():
        rn, nn = a["risk_n"], a["norm_n"]
        tp, fp = a["risk_block"], a["norm_block"]
        summ[t] = {
            "block_recall": round(tp / rn, 4) if rn else None,
            "false_block_rate": round(fp / nn, 4) if nn else None,
            "precision": round(tp / (tp + fp), 4) if (tp + fp) else None,
            **{f"{f}_recall": (round(a[f"{f}_block"] / a[f"{f}_n"], 4)
                               if a.get(f"{f}_n") else None) for f in ("S1", "S2", "S3")},
            "n_risk": rn, "n_normal": nn, "n_error": a.get("err", 0),
        }
    return rows, summ


def main():
    global SOCKET_THROTTLE_S, SOCKET_CACHE_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="data/external_realrisk_py")
    ap.add_argument("--out", default="results/external_realrisk_py/commercial_scan.json")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--socket-throttle", type=float, default=SOCKET_THROTTLE_S,
                    help="seconds to sleep between Socket calls (free-tier rate limit)")
    ap.add_argument("--socket-cache", default="results/external_realrisk_py/socket_cache",
                    help="per-name disk cache dir (resume without re-spending quota)")
    ap.add_argument("--families", default=None,
                    help="comma list to restrict scan, e.g. S1,S3,NEG (default: all)")
    ap.add_argument("--neg-cap", type=int, default=None,
                    help="max NEG manifests to scan (quota budgeting)")
    a = ap.parse_args()
    SOCKET_THROTTLE_S = a.socket_throttle
    SOCKET_CACHE_DIR = Path(a.socket_cache) if a.socket_cache else None
    families = set(a.families.split(",")) if a.families else None
    corpus = Path(a.corpus)

    tools = preflight(corpus)
    if a.preflight:
        return
    if not any(cli and tok for cli, tok in tools.values()):
        print("\nno tool READY; aborting full run. See setup steps above.", file=sys.stderr)
        sys.exit(2)

    rows, summ = score(corpus, tools, families=families, neg_cap=a.neg_cap)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "caveat": "current-SaaS non-frozen diagnostic; analogous to live pip-audit cell",
        "summary": summ, "per_manifest": rows}, indent=2))
    print(json.dumps(summ, indent=2))


if __name__ == "__main__":
    main()
