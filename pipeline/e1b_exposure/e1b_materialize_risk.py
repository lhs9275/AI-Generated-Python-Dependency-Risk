#!/usr/bin/env python3
"""e1b_materialize_risk -- did the labeled PR-time risk MATERIALIZE later? (E1b step 2/3)

For every change the guard-independent labeler marked primary-risky (P1/P2/P3),
query the CURRENT public state (PyPI now, OSV now) and decide whether the risk
that was visible at PR time actually became real:

  P1 NONEXISTENT_PACKAGE -- the name was absent at PR time. Did it get registered
     since, and is it flagged malicious? realized = name now exists AND/OR an OSV
     `MAL-` (malicious-package) advisory exists for it (typosquat/slopsquat
     materialized). A name that is still absent is an unrealized (but still risky)
     hallucination.
  P2 INVALID_VERSION_SPEC -- the pinned version did not exist at PR time. Does it
     exist now? realized = still absent (a permanently broken/unsatisfiable pin)
     OR now present but yanked.
  P3 DIRECT_KNOWN_VULNERABILITY -- an advisory covered the pinned version. Confirm
     it is still present in OSV now, and record the EARLIEST advisory disclosure
     date so step 3 can compute lead-time vs the PR date (supports the honest
     "evidence-limited floor": P3 cases whose advisory was disclosed only AFTER
     the PR are exactly the ones PR-time public evidence could not have caught).

This deliberately uses CURRENT evidence for the OUTCOME, while the guard decision
(step 3) uses the PR-time FROZEN evidence -- the temporal separation is the point.

Inputs: the patch records (for package/version) joined with the labeler output
(for label_primary). Pure stdlib. Responses cached for resume + offline re-run.

Example:
  python pipeline/e1b_exposure/e1b_materialize_risk.py \
    --patches results/tse_gap_closure/data/dependency_change_patches.jsonl \
    --labels  results/tse_gap_closure/data/labels_A.jsonl \
    --output  results/e1b_exposure/risk_realized.jsonl
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request


def load_records(path):
    """Yield dicts from a .csv or .jsonl file (auto-detect by extension)."""
    if path.lower().endswith(".csv"):
        with open(path, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                yield row
    else:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)

PYPI = "https://pypi.org/pypi/{name}/json"
OSV = "https://api.osv.dev/v1/query"
PRIMARY = {"P1_NONEXISTENT_PACKAGE": "P1",
           "P2_INVALID_VERSION_SPEC": "P2",
           "P3_DIRECT_KNOWN_VULNERABILITY": "P3"}


def log(m):
    print(m, file=sys.stderr, flush=True)


def http(url, data=None, cache=None, key=None):
    """GET (or POST if data) with simple disk cache. Returns parsed json or None."""
    if cache is not None and key in cache:
        return cache[key]
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body)
    req.add_header("User-Agent", "asg-e1b-exposure")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    out = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                out = json.loads(r.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                out = {"__404__": True}
                break
            if e.code in (403, 429) or 500 <= e.code < 600:
                time.sleep(3 * (attempt + 1))
                continue
            break
        except (urllib.error.URLError, TimeoutError, OSError):
            # OSError covers http.client.RemoteDisconnected / ConnectionResetError
            time.sleep(3 * (attempt + 1))
    if cache is not None and key is not None:
        cache[key] = out
    return out


def pin_version(patch):
    """Best-effort exact pinned version for the change."""
    v = patch.get("version_pin")
    if v:
        return str(v).strip()
    spec = patch.get("specifier_raw") or ""
    m = re.search(r"==\s*([0-9][\w.\-+!]*)", spec)
    return m.group(1) if m else None


def pypi_state(name, cache):
    d = http(PYPI.format(name=name), cache=cache, key=("pypi", name.lower()))
    if not d or d.get("__404__"):
        return {"exists": False, "versions": []}
    return {"exists": True, "versions": list((d.get("releases") or {}).keys()),
            "yanked": {v: all(f.get("yanked") for f in (files or [{}]))
                       for v, files in (d.get("releases") or {}).items() if files}}


def osv_vulns(name, version, cache):
    body = {"package": {"name": name, "ecosystem": "PyPI"}}
    if version:
        body["version"] = version
    d = http(OSV, data=body, cache=cache, key=("osv", name.lower(), version or ""))
    if not d or d.get("__404__"):
        return []
    return d.get("vulns") or []


def earliest_pub(vulns):
    dates = [v.get("published") for v in vulns if v.get("published")]
    return min(dates) if dates else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patches", default="results/tse_gap_closure/data/dependency_change_patches.jsonl")
    ap.add_argument("--labels", required=True, help="labeler_A jsonl with change_id + label_primary")
    ap.add_argument("--output", default="results/e1b_exposure/risk_realized.jsonl")
    ap.add_argument("--cache", default="results/e1b_exposure/_materialize_cache.json")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    label = {}
    for o in load_records(args.labels):
        lp = o.get("label_primary", "NONE")
        if lp in PRIMARY:
            label[o["change_id"]] = PRIMARY[lp]

    cache = {}
    if os.path.exists(args.cache):
        try:
            cache = {tuple(k.split("\x1f")): v for k, v in json.load(open(args.cache)).items()}
        except Exception:
            cache = {}

    done = set()
    if os.path.exists(args.output):
        for line in open(args.output, encoding="utf-8"):
            try:
                done.add(json.loads(line)["change_id"])
            except Exception:
                pass

    risky = []
    with open(args.patches, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            p = json.loads(line)
            cid = p.get("change_id")
            if cid in label and cid not in done:
                risky.append(p)
    if args.limit:
        risky = risky[:args.limit]
    log(f"risky changes to materialize: {len(risky)} (already done {len(done)})")

    with open(args.output, "a", encoding="utf-8") as out:
        for i, p in enumerate(risky, 1):
            cid = p["change_id"]
            rtype = label[cid]
            name = p.get("normalized_package_name") or p.get("package_name") or ""
            ver = pin_version(p)
            rec = {"change_id": cid, "pr_id": p.get("pr_id"), "risk_type": rtype,
                   "package": name, "version": ver, "pr_created_at": p.get("created_at")}
            if rtype == "P1":
                st = pypi_state(name, cache)
                mal = [v for v in osv_vulns(name, None, cache)
                       if any(str(a).startswith("MAL-") for a in
                              ([v.get("id")] + (v.get("aliases") or [])))]
                rec.update({"now_exists": st["exists"], "malicious_advisory": bool(mal),
                            "realized": bool(st["exists"] or mal),
                            "realization_kind": ("malicious_registration" if mal else
                                                 "name_registered" if st["exists"] else "still_absent")})
            elif rtype == "P2":
                st = pypi_state(name, cache)
                present = ver in st["versions"] if ver else False
                yanked = bool(st.get("yanked", {}).get(ver)) if ver else False
                rec.update({"now_exists": st["exists"], "version_present_now": present,
                            "version_yanked": yanked,
                            "realized": bool((not present) or yanked),
                            "realization_kind": ("yanked" if yanked else
                                                 "still_invalid" if not present else "resolved")})
            else:  # P3
                vulns = osv_vulns(name, ver, cache)
                pub = earliest_pub(vulns)
                rec.update({"advisory_present_now": bool(vulns),
                            "n_advisories": len(vulns),
                            "earliest_disclosure": pub,
                            "advisory_ids": [v.get("id") for v in vulns][:8],
                            "realized": bool(vulns),
                            "realization_kind": "advisory_confirmed" if vulns else "no_advisory_now"})
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            if i % 25 == 0:
                log(f"  {i}/{len(risky)}")
                json.dump({"\x1f".join(map(str, k)): v for k, v in cache.items()},
                          open(args.cache, "w"))

    json.dump({"\x1f".join(map(str, k)): v for k, v in cache.items()}, open(args.cache, "w"))
    log(f"done -> {args.output}")


if __name__ == "__main__":
    main()
