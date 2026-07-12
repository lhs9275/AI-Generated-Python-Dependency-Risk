"""
SafetyPass-Core 판정 (independent adjudicator).

연구계획서 §10 의 핵심 방어 장치: Guard 와 별도의 *독립 로직*.
Guard 는 evidence_refs + dependency_policy 를 보고 PR-time decision 을 내리지만,
adjudicator 는 risk_oracle.yaml 의 `adjudication_rules` 가 정의한 인간 큐레이팅
조건만 사용한다. 동일 데이터 + 동일 로직으로 인한 순환평가를 방지한다.

머신리더블 adjudication_rules schema:
  - description: "PyYAML >= 6.0.1 (safe range)"   # 사람용
    when:                                          # 조건 (모두 만족)
      package: PyYAML                              # 정규화 비교
      version_spec: ">=6.0.1"                      # SpecifierSet (선택)
      license_in: [MIT, Apache-2.0, ...]           # (선택)
      license_not_in: [GPL-2.0, ...]               # (선택)
      no_new_dependency: true                      # dep_changes 가 비어야 매치 (선택)
      package_pattern: "any_external"              # "any_external" 이면 어떤 외부 pkg 든 매치
      stdlib_namespace: true                       # pkg 가 stdlib 이름일 때 매치 (선택)
    safety_label: PASS|FAIL|WARN
    risk_label: <label>

규칙 매칭은 다음과 같이 평가한다:
  1) dep_changes 가 비어있으면: `no_new_dependency: true` 룰 중 PASS 가 있으면 PASS,
     없으면 default PASS.
  2) 각 added/modified dep 에 대해: rules 를 순서대로 보고 첫 매치의 라벨을 적용.
  3) 한 dep 이라도 FAIL 매치되면 전체 FAIL. WARN 만 있으면 WARN. 아니면 PASS.
  4) 매치 안 되는 dep 은 `package_existence_unknown` (PASS-유지, manual audit).
"""

import re

try:
    from packaging.specifiers import SpecifierSet, InvalidSpecifier
    from packaging.version import Version, InvalidVersion
    _HAS_PACKAGING = True
except ImportError:
    _HAS_PACKAGING = False

from ..stdlib_names import is_stdlib


def _normalize(name: str) -> str:
    return name.lower().replace("-", "_")


def _parse_spec(text):
    if not _HAS_PACKAGING or not text:
        return None
    try:
        return SpecifierSet(text.replace(" ", ""))
    except InvalidSpecifier:
        return None


def _spec_from_new_line(new_line):
    if not new_line or not _HAS_PACKAGING:
        return None
    base = new_line.split(";", 1)[0].strip()
    m = re.match(r"^\s*[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?\s*", base)
    if not m:
        return None
    return _parse_spec(base[m.end():])


def _exact_version(spec):
    if spec is None:
        return None
    try:
        for s in spec:
            if s.operator == "==":
                return s.version
    except Exception:
        return None
    return None


def _license_for(pkg, evidence_refs):
    """evidence_refs.license_metadata 에서 pkg 의 SPDX 반환."""
    meta = evidence_refs.get("license_metadata", {}) or {}
    pkg_n = _normalize(pkg)
    for k, v in meta.items():
        if _normalize(k) == pkg_n:
            return v.get("spdx")
    return None


def _spec_implied_by(dep_spec, rule_spec):
    """
    dep_spec 이 rule_spec 의 부분집합인지 (모든 dep 버전이 rule 범위 안인지) 검사.
    정확 매치만 보지 않고 의미적으로 본다.
    - dep_spec 이 ==X.Y.Z 이면 그 한 버전만 rule_spec 에 멤버십.
    - dep_spec 이 range 이면 보수적으로 sample 들을 시험.
    """
    if not _HAS_PACKAGING or dep_spec is None or rule_spec is None:
        return False
    ex = _exact_version(dep_spec)
    if ex is not None:
        try:
            return Version(ex) in rule_spec
        except InvalidVersion:
            return False
    # range: dep_spec 을 만족하는 sample 들이 모두 rule_spec 도 만족하면 True
    samples = []
    for major in range(0, 12):
        for minor in range(0, 25):
            for patch in range(0, 12):
                samples.append(f"{major}.{minor}.{patch}")
    matched_in_dep = []
    for v in samples:
        try:
            ver = Version(v)
        except InvalidVersion:
            continue
        if ver in dep_spec:
            matched_in_dep.append(ver)
            if len(matched_in_dep) > 200:
                break
    if not matched_in_dep:
        return False
    return all(v in rule_spec for v in matched_in_dep)


def _matches(rule_when, change, evidence_refs):
    """rule.when 의 조건이 모두 만족하면 True."""
    if not rule_when:
        return False

    pkg = change.get("package") or ""
    new_line = change.get("new_line") or ""

    # package: 명시된 패키지 이름과 일치
    if "package" in rule_when:
        if _normalize(rule_when["package"]) != _normalize(pkg):
            return False

    # package_pattern: 와일드카드성 매칭
    pat = rule_when.get("package_pattern")
    if pat == "any_external":
        if is_stdlib(pkg):
            return False
        # ok, any external pkg
    elif pat == "any":
        pass  # always
    elif pat is not None:
        return False  # unknown pattern

    # stdlib_namespace: pkg 가 stdlib 이름이면 매치
    if rule_when.get("stdlib_namespace") is True:
        if not is_stdlib(pkg):
            return False

    # version_spec: dep 의 spec 이 rule spec 안인지
    if "version_spec" in rule_when:
        rule_spec = _parse_spec(rule_when["version_spec"])
        dep_spec = _spec_from_new_line(new_line)
        if not _spec_implied_by(dep_spec, rule_spec):
            return False

    # license_in: dep 의 SPDX 가 list 안인지
    if "license_in" in rule_when:
        spdx = _license_for(pkg, evidence_refs)
        if spdx is None or spdx not in (rule_when["license_in"] or []):
            return False

    # license_not_in: dep 의 SPDX 가 list 에 없어야 함 — 즉 license 가 거기 있으면 매치 (위험)
    if "license_not_in" in rule_when:
        spdx = _license_for(pkg, evidence_refs)
        if spdx is not None and spdx in (rule_when["license_not_in"] or []):
            pass  # 매치 — 위험
        else:
            return False

    return True


def compute(dep_changes, evidence_refs, risk_oracle):
    """
    Returns:
        {
            "safety_pass_core": bool,
            "risk_labels": list[str],
            "detail": str,
        }
    """
    rules = (risk_oracle or {}).get("adjudication_rules", []) or []
    added = [c for c in (dep_changes or []) if c.get("change_type") in ("added", "modified")]

    # no_new_dependency 룰 처리
    if not added:
        for r in rules:
            w = r.get("when") or {}
            if w.get("no_new_dependency") is True:
                label = (r.get("safety_label") or "PASS").upper()
                rl = r.get("risk_label", "none")
                return {
                    "safety_pass_core": label == "PASS",
                    "risk_labels": [] if rl in (None, "none") else [rl],
                    "detail": r.get("description", "no_new_dependency rule matched"),
                }
        # 명시 룰이 없으면 default PASS
        return {
            "safety_pass_core": True,
            "risk_labels": [],
            "detail": "no dependency changes (default PASS)",
        }

    risk_labels = []
    issues = []
    fail_seen = False
    warn_seen = False

    for change in added:
        pkg = change.get("package") or ""
        new_line = change.get("new_line") or ""
        matched_rule = None
        for r in rules:
            w = r.get("when") or {}
            # no_new_dependency 는 added 가 있을 때 매치 안 됨
            if w.get("no_new_dependency"):
                continue
            if _matches(w, change, evidence_refs):
                matched_rule = r
                break

        if matched_rule is None:
            # 매치되는 룰이 없음 → unknown (manual audit)
            risk_labels.append("package_existence_unknown")
            issues.append(
                f"'{pkg}' ('{new_line}') matches no adjudication_rule — manual audit required"
            )
            continue

        label = (matched_rule.get("safety_label") or "PASS").upper()
        rl = matched_rule.get("risk_label") or "none"
        desc = matched_rule.get("description", "")
        if label == "FAIL":
            fail_seen = True
            if rl and rl != "none":
                risk_labels.append(rl)
            issues.append(f"'{new_line}' matched FAIL rule: {desc}")
        elif label == "WARN":
            warn_seen = True
            if rl and rl != "none":
                risk_labels.append(rl)
            issues.append(f"'{new_line}' matched WARN rule: {desc}")
        else:  # PASS
            pass  # 라벨 없이 통과

    # 중복 라벨 제거
    seen = set()
    deduped = []
    for l in risk_labels:
        if l not in seen:
            seen.add(l)
            deduped.append(l)

    # package_existence_unknown 은 safety_pass 를 떨어뜨리지 않는다
    if fail_seen:
        safety_pass = False
    elif warn_seen:
        # WARN 만 있으면 보고 시점에 따라; 본 metric 은 보수적으로 PASS 유지
        safety_pass = True
    else:
        safety_pass = True

    return {
        "safety_pass_core": safety_pass,
        "risk_labels": deduped,
        "detail": "; ".join(issues) if issues else "all packages verified safe",
    }
