"""
Guard Stage S5: License Policy.

검사 항목:
  evidence_refs.license_metadata[pkg].adjudicated_label 을 우선 사용.
  없으면 license_metadata[pkg].spdx 를 dependency_policy.yaml 의
  allowed_licenses / blocked_licenses 와 비교.

label hierarchy (연구계획서 9.4.1):
  allowed    -> PASS
  blocked    -> BLOCK (critical)
  ambiguous  -> WARN (policy.unknown_license_policy 가 'block' 이면 BLOCK)
  conflict   -> WARN (별도 manual-review 라벨)
  missing    -> WARN
"""


def _normalize(name: str) -> str:
    return name.lower().replace("-", "_")


def _lookup(pkg: str, license_metadata: dict) -> tuple[str | None, dict | None]:
    pkg_n = _normalize(pkg)
    for key, entry in license_metadata.items():
        if _normalize(key) == pkg_n:
            return key, entry
    return None, None


def _classify(entry: dict, policy: dict) -> tuple[str, str | None]:
    """
    license_metadata entry 를 (label, spdx) 로 정규화.
    label ∈ {"allowed","blocked","ambiguous","conflict","missing"}
    """
    if not entry:
        return "missing", None
    explicit = entry.get("adjudicated_label")
    spdx = entry.get("spdx")
    if explicit in ("allowed", "blocked", "ambiguous", "conflict"):
        return explicit, spdx
    if not spdx:
        return "missing", None
    allowed = set(policy.get("allowed_licenses", []) or [])
    blocked = set(policy.get("blocked_licenses", []) or [])
    if spdx in blocked:
        return "blocked", spdx
    if spdx in allowed:
        return "allowed", spdx
    # blocked 패밀리 prefix 매칭 (예: "GPL-2.0" 이 blocked_licenses 에 "GPL-2.0-only" 만 있을 때)
    for b in blocked:
        if spdx.startswith(b.split("-only")[0].split("-or-later")[0]):
            return "blocked", spdx
    return "ambiguous", spdx


def check(dep_changes: list[dict], evidence_refs: dict, policy: dict) -> list[dict]:
    """
    S5: License policy 검사.

    Returns:
        issues 목록. 각 issue:
        {
            "stage": "S5",
            "package": str,
            "risk_label": "license_blocked" | "license_ambiguous" | "license_missing" | "license_conflict",
            "severity": "critical" | "medium" | "warn",
            "reason": str,
            "evidence_source": "snapshot.license_metadata",
            "pr_time_preventable": True,
            "license_spdx": str | None,
            "license_label": str,
        }
    """
    license_metadata = evidence_refs.get("license_metadata", {}) or {}
    unknown_policy = (policy.get("unknown_license_policy") or "warn").lower()
    issues = []

    for change in dep_changes:
        if change["change_type"] not in ("added", "modified"):
            continue
        pkg = change["package"]
        _, entry = _lookup(pkg, license_metadata)
        label, spdx = _classify(entry, policy)

        if label == "allowed":
            continue

        if label == "blocked":
            issues.append({
                "stage": "S5",
                "package": pkg,
                "risk_label": "license_blocked",
                "severity": "critical",
                "reason": (
                    f"Package '{pkg}' license '{spdx}' is in the blocked list."
                ),
                "evidence_source": "snapshot.license_metadata",
                "pr_time_preventable": True,
                "license_spdx": spdx,
                "license_label": label,
            })
        elif label in ("ambiguous", "missing", "conflict"):
            severity = "critical" if unknown_policy == "block" else "warn"
            issues.append({
                "stage": "S5",
                "package": pkg,
                "risk_label": f"license_{label}",
                "severity": severity,
                "reason": (
                    f"Package '{pkg}' license is {label} (spdx={spdx}); "
                    f"policy.unknown_license_policy='{unknown_policy}'."
                ),
                "evidence_source": "snapshot.license_metadata",
                "pr_time_preventable": True,
                "license_spdx": spdx,
                "license_label": label,
            })

    return issues
