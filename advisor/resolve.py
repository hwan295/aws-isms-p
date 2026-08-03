"""필드 판독 — 계약 v1.0.

수집기가 필드마다 {value, reason} 을 실어 보내므로 "왜 비었는지"를 이쪽에서
추론할 필요가 없다. 사유 코드를 우리 조치 단위로 옮기기만 한다.

    수집기 reason          우리 판독        조치
    ────────────────────────────────────────────────────────────
    null                   present          없음
    TAG_ABSENT             missing          태그를 단다
    NOT_CONFIGURED         not_set          AWS 설정이 없다는 사실 (등급 근거)
    API_NULL               api_null         API가 값을 안 준다
    NOT_APPLICABLE         not_applicable   개념이 없다. 갭 아님
    PERMISSION_DENIED      unverified       권한을 열고 재수집
    COLLECT_ERROR          unverified       재수집
    OUT_OF_SCOPE           out_of_scope     수집기가 아직 그 API를 안 부름

뒤의 셋(unverified, out_of_scope)은 "모른다"이지 "없다"가 아니다. 자산 부재나
통제 미비로 세면 등급이 통째로 틀린다. 계약 §5가 금지하는 해석이다.
"""

PRESENT = "present"
MISSING = "missing"
NOT_SET = "not_set"
API_NULL = "api_null"
NOT_APPLICABLE = "not_applicable"
UNVERIFIED = "unverified"
OUT_OF_SCOPE = "out_of_scope"

BY_REASON = {
    "TAG_ABSENT": MISSING,
    "NOT_CONFIGURED": NOT_SET,
    "API_NULL": API_NULL,
    "NOT_APPLICABLE": NOT_APPLICABLE,
    "PERMISSION_DENIED": UNVERIFIED,
    "COLLECT_ERROR": UNVERIFIED,
    "OUT_OF_SCOPE": OUT_OF_SCOPE,
}

# 자산이 없다는 뜻이 아닌 판독. 갭으로도 통제 미비로도 세지 않는다.
NOT_ABSENCE = (UNVERIFIED, OUT_OF_SCOPE)

_ABSENT = object()


def dig(asset, path):
    """점 표기 경로로 노드를 꺼낸다. infra_facts.backup_exists 처럼 두 단계까지."""
    node = asset
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return _ABSENT
        node = node[key]
    return node


def status(asset, path):
    node = dig(asset, path)
    if node is _ABSENT:
        return NOT_APPLICABLE
    # region·asset_id 처럼 사유가 안 붙는 평범한 값
    if not isinstance(node, dict) or "value" not in node:
        return PRESENT if node not in (None, "", [], {}) else MISSING
    if node["reason"] is None:
        return PRESENT
    return BY_REASON.get(node["reason"], MISSING)


def value_of(asset, path):
    node = dig(asset, path)
    if node is _ABSENT:
        return None
    if not isinstance(node, dict) or "value" not in node:
        return node
    return node["value"]


def hint_of(asset, path):
    node = dig(asset, path)
    return node.get("hint") if isinstance(node, dict) else None


def reason_of(asset, path):
    node = dig(asset, path)
    return node.get("reason") if isinstance(node, dict) and "value" in node else None


def assets_of(snapshot):
    """자산유형별로 묶인 구조를 평면 목록으로 편다."""
    return [a for block in snapshot["asset_types"].values() for a in block["assets"]]
