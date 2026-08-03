"""보안등급 제안 룰 엔진.

룰 내용은 config/grade_rules.yaml 에 있고 여기는 실행만 한다.
룰이 바뀌어도 이 파일은 안 고치는 게 목표.

지키는 원칙 두 가지.
  - 등급을 확정하려면 자산 속성 근거가 최소 1건 있어야 한다.
    통제 상태만 보고는 중요도를 못 정한다.
  - 통제 상태는 등급을 올리는 데만 쓴다. 백업을 끄면 중요도가 올라가는
    모순을 피하려면 내리는 쪽으로는 쓰면 안 된다.

grade_proposed 와 grade_confirmed 는 계약 v1.0 의 자산 레코드에 없다.
수집기는 판정 필드를 만들지 않고(meta.graded_by 에 명시) 여기서 붙인다.
"""
import yaml
from pathlib import Path

from . import resolve

ROOT = Path(__file__).resolve().parent.parent
GRADER_VERSION = "advisor-1.0.0"

ORDER = {"하": 1, "중": 2, "상": 3}
BY_ORDER = {v: k for k, v in ORDER.items()}
AXES = ("confidentiality", "integrity", "availability")

# 태그로 채우는 조직 정보. 비어 있으면 등급을 확정할 근거가 모자란다.
OWNERSHIP_FIELDS = [
    "owner_dept",
    "owner_manager",
    "owner_responsible",
    "usage",
    "service_name",
    "environment",
    "has_personal_info",
    "in_scope",
]


def load_rules(path=ROOT / "config/grade_rules.yaml"):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _same(actual, expected):
    if isinstance(actual, str) and isinstance(expected, str):
        return actual.casefold() == expected.casefold()
    # bool 과 정수를 섞지 않는다. True == 1 이 참이라 그냥 == 로 두면 오발화한다
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual is expected
    return actual == expected


def _fires(asset, when):
    """룰 조건 평가. 조건이 전부 맞아야 발화하고, 값이 리스트면 그중 하나면 된다.

    값을 못 읽은 필드(권한 부족·수집 범위 밖)는 어느 조건도 만족시키지 않는다.
    수집기가 그런 필드의 value 를 null 로 주기 때문에 자연히 걸러진다.
    """
    for path, expected in when.items():
        actual = resolve.value_of(asset, path)
        if isinstance(expected, list):
            if not any(_same(actual, e) for e in expected):
                return False
        elif not _same(actual, expected):
            return False
    return True


def _basis(rule):
    return {
        "type": rule["basis_type"],
        "statement": rule["statement"],
        "source": rule["source"],
        "evidence_field": rule.get("evidence_field"),
        "rule_id": rule["id"],
    }


def _axis_grade(asset, rules, axis):
    fired = [r for r in rules if r["axis"] == axis and _fires(asset, r["when"])]
    attribute = [r for r in fired if r["basis_type"] == "asset_attribute"]
    control = [r for r in fired if r["basis_type"] == "control_state"]

    if not attribute:
        # 자산 속성 근거가 없으면 등급을 억지로 채우지 않는다.
        # 발화한 통제 근거는 "여기까지는 확인했다"는 기록으로 남긴다.
        return {"level": None, "basis": [_basis(r) for r in control]}

    level = max(ORDER[r["level"]] for r in attribute)
    if control:
        level = max(level, max(ORDER[r["level"]] for r in control))
    return {"level": BY_ORDER[level], "basis": [_basis(r) for r in attribute + control]}


def _review_reasons(asset, axes):
    reasons = []

    missing = [f for f in OWNERSHIP_FIELDS if resolve.status(asset, f) == resolve.MISSING]
    if missing:
        reasons.append({
            "code": "missing_tag",
            "field": missing[0],
            "message": f"태그 {len(missing)}건 미입력 ({', '.join(missing)}) — 담당자가 태그를 달아야 등급이 확정된다",
        })

    unverified = [f for f in OWNERSHIP_FIELDS + ["infra_facts.backup_exists",
                                                 "infra_facts.encryption_at_rest",
                                                 "infra_facts.public_exposed"]
                  if resolve.status(asset, f) == resolve.UNVERIFIED]
    if unverified:
        reasons.append({
            "code": "unverified_access_denied",
            "field": unverified[0],
            "message": f"{len(unverified)}건을 권한 부족·조회 실패로 확인하지 못함 — 자산 부재가 아니며 재수집 대상",
        })

    scope = [f for f in ("os", "infra_facts.exposure_path", "infra_facts.encryption_in_transit")
             if resolve.status(asset, f) == resolve.OUT_OF_SCOPE]
    if scope:
        reasons.append({
            "code": "collector_out_of_scope",
            "field": scope[0],
            "message": f"수집기가 아직 부르지 않는 API 때문에 {len(scope)}건 미확인 ({', '.join(scope)})",
        })

    # 퍼블릭 노출은 등급 상향 근거가 아니다. 별지 제3호는 "조직 외부인이 접근
    # 가능한 정보를 담은 자산"을 오히려 기밀성 하로 본다. 의도한 공개인지
    # 통제 실패인지는 설정만 봐서 알 수 없으므로 사람에게 넘긴다.
    if resolve.value_of(asset, "infra_facts.public_exposed") is True:
        reasons.append({
            "code": "exposure_intent_unknown",
            "field": "infra_facts.public_exposed",
            "message": "설정상 외부에 노출되어 있으나 의도한 공개인지 통제 실패인지 확인 필요",
        })

    # 사유는 못 찾았는데 등급을 못 낸 축이 남았으면, 기계로 판정할 수 없는
    # 조건(손실 규모·중단 허용 시간)이 걸린 것으로 본다.
    if not reasons and any(axes[a]["level"] is None for a in AXES):
        blank = [a for a in AXES if axes[a]["level"] is None]
        reasons.append({
            "code": "impact_not_machine_checkable",
            "field": None,
            "message": f"{', '.join(blank)} 축은 업무 영향 판단이 필요해 도구가 등급을 내지 못함",
        })

    return reasons


def grade(asset, rules):
    """자산 레코드 1건에 grade_proposed 를 붙인다. 수집기 필드는 건드리지 않는다."""
    ruleset = rules["rules"]
    axes = {axis: _axis_grade(asset, ruleset, axis) for axis in AXES}

    levels = [ORDER[axes[a]["level"]] for a in AXES if axes[a]["level"]]
    reasons = _review_reasons(asset, axes)

    graded = dict(asset)
    graded["grade_proposed"] = {
        **axes,
        "overall": BY_ORDER[max(levels)] if levels else None,
        "needs_human_review": bool(reasons),
        "review_reasons": reasons,
        "ruleset_version": rules["ruleset_version"],
        "grader_version": GRADER_VERSION,
    }
    graded["grade_confirmed"] = None  # 도구는 이 칸을 쓰지 않는다
    return graded


def grade_snapshot(snapshot, rules=None):
    rules = rules or load_rules()
    types = {
        name: {**block, "assets": [grade(a, rules) for a in block["assets"]]}
        for name, block in snapshot["asset_types"].items()
    }
    return {**snapshot, "asset_types": types}
