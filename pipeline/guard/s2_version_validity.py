"""
Guard Stage S2: Version Validity.

검사 항목:
  (1) Existence — 지정된 specifier 가 evidence_refs.known_versions 와 적어도 하나 매치하는가
  (2) Runtime compatibility — evidence_refs.runtime_compatibility 가 정의되어 있고
      specifier 가 incompatible 범위와 겹치면 차단

S3 (direct vulnerability) 와 분리: 여기서는 CVE 가 아닌
"버전이 존재하는가" + "런타임/빌드와 호환되는가" 만 본다.

evidence_refs 에 known_versions 가 없으면 existence check 는 SKIP.
runtime_compatibility 가 없으면 compatibility check 는 SKIP.
"""

import re

try:
    from packaging.specifiers import SpecifierSet, InvalidSpecifier
    from packaging.version import Version, InvalidVersion
    _HAS_PACKAGING = True
except ImportError:
    _HAS_PACKAGING = False


def _normalize(name: str) -> str:
    return name.lower().replace("-", "_")


def _snapshot_lookup(pkg: str, snapshot: dict) -> tuple[str | None, dict | None]:
    """정규화된 이름으로 snapshot lookup. (matched_key, entry) 반환."""
    pkg_n = _normalize(pkg)
    for key, entry in snapshot.items():
        if _normalize(key) == pkg_n:
            return key, entry
    return None, None


def _parse_spec(specifier_text: str | None) -> "SpecifierSet | None":
    if not _HAS_PACKAGING or not specifier_text:
        return None
    try:
        return SpecifierSet(specifier_text.replace(" ", ""))
    except InvalidSpecifier:
        return None


def _spec_from_new_line(new_line: str | None) -> "SpecifierSet | None":
    """`PyYAML>=5.1,<6.0` 같은 라인에서 specifier 추출."""
    if not new_line or not _HAS_PACKAGING:
        return None
    base = new_line.split(";", 1)[0].strip()
    m = re.match(r"^\s*[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?\s*", base)
    if not m:
        return None
    return _parse_spec(base[m.end():])


def _matches_any(spec: "SpecifierSet | None", versions: list[str]) -> list[str]:
    """spec 을 만족하는 known_versions 의 부분집합 반환."""
    if not _HAS_PACKAGING:
        return []
    matched = []
    for v in versions:
        try:
            if (spec is None) or (Version(v) in spec):
                matched.append(v)
        except InvalidVersion:
            continue
    return matched


def check(dep_changes: list[dict], evidence_refs: dict) -> list[dict]:
    """
    S2: 버전 유효성 검사.

    Returns:
        issues 목록. 각 issue:
        {
            "stage": "S2",
            "package": str,
            "risk_label": "version_nonexistent" | "version_build_incompatible",
            "severity": "high" | "critical",
            "reason": str,
            "evidence_source": str,
            "pr_time_preventable": True,
        }
    """
    if not _HAS_PACKAGING:
        return []

    snapshot = evidence_refs.get("pypi_packages", {})
    runtime_compat = evidence_refs.get("runtime_compatibility", []) or []
    issues = []

    for change in dep_changes:
        if change["change_type"] not in ("added", "modified"):
            continue
        pkg = change["package"]
        new_line = change.get("new_line") or ""
        spec = _spec_from_new_line(new_line)

        # ── (1) Existence ──────────────────────────────────────────────
        _, entry = _snapshot_lookup(pkg, snapshot)
        known_versions = (entry or {}).get("known_versions") or []
        if known_versions and spec is not None:
            matched = _matches_any(spec, known_versions)
            if not matched:
                issues.append({
                    "stage": "S2",
                    "package": pkg,
                    "risk_label": "version_nonexistent",
                    "severity": "critical",
                    "reason": (
                        f"Specifier '{new_line}' does not match any known PyPI "
                        f"version for '{pkg}' (known: {known_versions})."
                    ),
                    "evidence_source": "snapshot.known_versions",
                    "pr_time_preventable": True,
                })

        # ── (2) Runtime compatibility ──────────────────────────────────
        for adv in runtime_compat:
            adv_pkg = adv.get("package", "")
            if _normalize(adv_pkg) != _normalize(pkg):
                continue
            adv_range = adv.get("incompatible_versions") or adv.get("affected_versions")
            adv_spec = _parse_spec(adv_range)
            if adv_spec is None or spec is None:
                continue
            # spec 이 advisory 의 incompatible 범위와 겹치는지 보기 위해
            # known_versions(또는 advisory's matching versions)로 교차 확인
            test_versions = known_versions or _versions_from_range_hint(adv_range)
            overlap = [
                v for v in test_versions
                if _has_overlap(v, spec, adv_spec)
            ]
            if overlap:
                issues.append({
                    "stage": "S2",
                    "package": pkg,
                    "risk_label": adv.get("label") or "version_build_incompatible",
                    "severity": adv.get("severity", "HIGH").lower(),
                    "reason": (
                        f"Specifier '{new_line}' overlaps runtime-incompatible "
                        f"range '{adv_range}' for '{pkg}': "
                        f"{adv.get('reason', 'incompatible with target runtime')}"
                    ),
                    "evidence_source": "snapshot.runtime_compatibility",
                    "pr_time_preventable": True,
                })

    return issues


def _has_overlap(version_str: str, spec_a: "SpecifierSet", spec_b: "SpecifierSet") -> bool:
    try:
        v = Version(version_str)
    except InvalidVersion:
        return False
    return (v in spec_a) and (v in spec_b)


def _versions_from_range_hint(spec_text: str | None) -> list[str]:
    """advisory range만 있고 known_versions 가 없을 때 대표 점들로 polling."""
    # 간단한 휴리스틱: 0.0.0 ~ 99.99.99 중 정수 분포 일부만
    samples = []
    for major in range(0, 12):
        for minor in (0, 1, 5, 10):
            samples.append(f"{major}.{minor}.0")
    return samples
