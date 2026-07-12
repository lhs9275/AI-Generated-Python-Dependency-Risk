"""Emit the four naturalistic-validation LaTeX tables (IEEEtran + booktabs).

Reads only the analysis CSVs + JSON summaries, so re-running after the scanner
column is merged regenerates every table with the final numbers.
"""

import argparse
import csv
import json
from pathlib import Path

from statsmodels.stats.proportion import proportion_confint

PRETTY = {
    "B0_no_gate": "B0 (no gate)",
    "B1_scanner_fail_open": "B1 (scanner, fail-open)",
    "B1b_scanner_fail_closed": "B1b (scanner, fail-closed)",
    "S1_existence": "S1 (existence)",
    "S1S2_version": "S1+S2 (+version)",
    "S1S2S3_direct_evidence": "S1+S2+S3 (direct evidence)",
    "S1S2S3_plus_license": "S1+S2+S3+license",
    "B3_full_guard": "B3 (full guard)",
}
ORDER = list(PRETTY)


def _pct_ci(k, n):
    if not n:
        return "--"
    lo, hi = proportion_confint(k, n, alpha=0.05, method="wilson")
    return f"{100*k/n:.1f}\\% ({k}/{n}) [{100*lo:.1f}--{100*hi:.1f}]"


def _load_csv(p):
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def t_main(adir, meta):
    rows = {r["variant"]: r for r in _load_csv(adir / "naturalistic_validation_summary.csv")}
    n_risky = meta["n_primary_risky"]
    n_safe = meta["n_safe"]
    body = []
    for v in ORDER:
        r = rows.get(v)
        if not r:
            continue
        pra = int(round(float(r["primary_risky_acceptance_rate"]) * n_risky)) if r["primary_risky_acceptance_rate"] else 0
        sb = int(r["safe_block_count"])
        body.append(f"    {PRETTY[v]} & {r['blocked']} & {_pct_ci(pra, n_risky)} & {_pct_ci(sb, n_safe)} \\\\")
    return r"""\begin{table}[t]
  \centering
  \caption{Naturalistic validation: gate-ladder outcomes over %d independently labeled
    AI-assisted dependency changes (%d PRs, %d repositories). Primary-risky
    acceptance = a P1/P2/P3 change \emph{not} blocked; safe-block = an independently
    \emph{safe} change blocked. Wilson 95\%% CI in brackets.}
  \label{tab:nat-validation}
  \setlength{\tabcolsep}{3pt}
  \resizebox{\columnwidth}{!}{%%
\begin{tabular}{l r l l}
    \toprule
    Gate variant & Blocked & Primary-risky accept.\ & Safe-block \\
    \midrule
%s
    \bottomrule
  \end{tabular}
}
\end{table}
""" % (meta["n_analysis_population_add_or_versionchange"], meta["n_prs"], meta["n_repos"],
       "\n".join(body))


def t_labeling(adir, meta, agree, log):
    pd = agree["final_primary_dist"]
    gd = agree.get("final_primary_grade_dist", {})
    sd = agree["final_secondary_dist"]
    rows = [
        ("Screened PRs (GitHub search + AIDev pool)", f"{log['n_pr_pool']}"),
        ("Included dependency-changing AI PRs", f"{log['n_included_prs']}"),
        ("Repositories / tool families", f"{log['n_included_repos']} / {log['n_tool_families']}"),
        ("Dependency changes (labelable)", f"{agree['n_changes']}"),
        ("Time-aligned evidence recoverable", f"{100*log.get('pr_time_recoverable_frac',1):.1f}\\%"),
        ("Primary-label Cohen's $\\kappa$ (2 labelers)", f"{agree['primary_kappa']}"),
        ("Primary-label agreement", f"{100*agree['primary_agreement_rate']:.2f}\\%"),
        ("Adjudicated disagreements", f"{agree['n_adjudicated']}"),
        ("\\midrule P1 nonexistent package",
         f"{pd.get('P1_NONEXISTENT_PACKAGE',0)} ({gd.get('high_created_after_pr',0)} created-after-PR, {gd.get('medium_404_now',0)} 404-now)"),
        ("P2 invalid version spec",
         f"{pd.get('P2_INVALID_VERSION_SPEC',0)} ({gd.get('strong_absent_now',0)} absent-now, {gd.get('conditional_released_after_pr',0)} post-PR-release)"),
        ("P3 direct known vulnerability (PR-time)", f"{pd.get('P3_DIRECT_KNOWN_VULNERABILITY',0)}"),
        ("\\midrule S4 license-policy (secondary)", f"{sd.get('S4_LICENSE_POLICY_CONFLICT',0)}"),
        ("S7 metadata-missing (secondary)", f"{sd.get('S7_METADATA_MISSING',0)}"),
    ]
    body = []
    for k, v in rows:
        if k.startswith("\\midrule"):
            body.append("    \\midrule")
            k = k.replace("\\midrule ", "")
        body.append(f"    {k} & {v} \\\\")
    return r"""\begin{table}[t]
  \centering
  \caption{Independent (guard-free) labeling protocol and outcome. Two
    separately implemented labelers (deterministic PR-time evidence vs.\ live
    PyPI/OSV re-query) fixed labels before any guard ran; disagreements were
    adjudicated against the exact-timestamp record.}
  \label{tab:nat-labeling}
  \setlength{\tabcolsep}{4pt}
  \resizebox{\columnwidth}{!}{%%
\begin{tabular}{l r}
    \toprule
    Quantity & Value \\
    \midrule
%s
    \bottomrule
  \end{tabular}
}
\end{table}
""" % "\n".join(body)


def t_scope(adir):
    rows = {r["primary_label"]: r for r in _load_csv(adir / "scanner_scope_mismatch.csv")}
    label_names = {
        "P1_NONEXISTENT_PACKAGE": "P1 nonexistent package",
        "P2_INVALID_VERSION_SPEC": "P2 invalid version spec",
        "P3_DIRECT_KNOWN_VULNERABILITY": "P3 direct known vuln.\\ (PR-time)",
    }
    body = []
    for k in ["P1_NONEXISTENT_PACKAGE", "P2_INVALID_VERSION_SPEC", "P3_DIRECT_KNOWN_VULNERABILITY"]:
        r = rows.get(k)
        if not r:
            continue
        body.append(f"    {label_names[k]} & {r['n']} & {r['scanner_blocked']} & "
                    f"{r['direct_gate_blocked']} & {r['scanner_missed_but_gate_caught']} \\\\")
    return r"""\begin{table}[t]
  \centering
  \caption{Scanner-scope mismatch on independently labeled primary risks. An
    off-the-shelf vulnerability scanner (pip-audit, fail-open) cannot represent a
    nonexistent package or an invalid version pin; the minimal direct-public-evidence
    gate (S1+S2+S3) blocks them. ``Missed but caught'' = scanner accepted, gate blocked.}
  \label{tab:nat-scope}
  \setlength{\tabcolsep}{4pt}
  \resizebox{\columnwidth}{!}{%%
\begin{tabular}{l r r r r}
    \toprule
    Primary risk & $n$ & Scanner & Direct gate & Missed/caught \\
    \midrule
%s
    \bottomrule
  \end{tabular}
}
\end{table}
""" % "\n".join(body)


def t_minimal(adir):
    rows = _load_csv(adir / "minimal_gate_comparison.csv")
    summ = {r["variant"]: r for r in _load_csv(adir / "naturalistic_validation_summary.csv")}
    body = []
    for r in rows:
        v = r["rung"]
        s = summ.get(v, {})
        sbr = s.get("safe_block_rate") or "0"
        prar = s.get("primary_risky_acceptance_rate") or "1.0"
        body.append(f"    {PRETTY.get(v, v)} & {r['cumulative_blocked']} & "
                    f"+{r['marginal_new_blocks']} & {100*float(r['marginal_frac_of_total']):.2f}\\% & "
                    f"{100*float(sbr):.2f}\\% & {100*float(prar):.1f}\\% \\\\")
    return r"""\begin{table}[t]
  \centering
  \caption{Minimal-gate ladder: marginal blocking contribution of each rung over
    the naturalistic corpus. Most preventable primary risk is reached by the
    direct-public-evidence core (S1+S2+S3); the license rung adds the largest
    block volume but it is overwhelmingly safe-PR friction (rising safe-block rate),
    supporting its treatment as a secondary warning.}
  \label{tab:nat-minimal}
  \setlength{\tabcolsep}{3pt}
  \resizebox{\columnwidth}{!}{%%
\begin{tabular}{l r r r r r}
    \toprule
    Rung & Cum.\ blk & Marg. & Marg.\ \%% & Safe-blk & Prim.\ acc. \\
    \midrule
%s
    \bottomrule
  \end{tabular}
}
\end{table}
""" % "\n".join(body)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--analysis", default="outputs/tse_gap_closure/analysis")
    ap.add_argument("--data", default="outputs/tse_gap_closure/data")
    ap.add_argument("--out", default="outputs/tse_gap_closure/tables")
    args = ap.parse_args()
    adir = Path(args.analysis)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads((adir / "paired_stats.json").read_text())
    agree = json.loads((Path(args.data) / "labeling_agreement.json").read_text())
    log = json.loads((Path(args.data) / "collection_log.json").read_text())

    (out / "table_naturalistic_validation.tex").write_text(t_main(adir, meta))
    (out / "table_independent_labeling.tex").write_text(t_labeling(adir, meta, agree, log))
    (out / "table_scope_mismatch.tex").write_text(t_scope(adir))
    (out / "table_minimal_gate.tex").write_text(t_minimal(adir))
    print(f"wrote 4 tables -> {out}")


if __name__ == "__main__":
    main()
