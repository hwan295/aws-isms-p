"""값이 없을 때의 사유 8종과, 사유를 붙인 필드 값.

이 프로젝트에서 가장 중요한 설계다.
값이 없다는 사실만 넘기면 B가 판단할 수 없다. 왜 없는지를 함께 실어야 한다.

**"모른다"와 "없다"는 다르다.**
권한이 없어서 못 읽은 것, 조회가 실패한 것, 아예 안 불러본 것을
"설정 없음"으로 뭉개면 등급 제안이 통째로 틀린다.
"""

from __future__ import annotations

from typing import Any

#: 정상 수집됨
OK = None
#: 태그 미입력. 담당자가 태그 달면 다음 실행부터 자동
TAG_ABSENT = "TAG_ABSENT"
#: AWS 설정이 없음. 사실 자체가 정보이고 등급 근거가 된다
NOT_CONFIGURED = "NOT_CONFIGURED"
#: 권한 부족으로 조회 실패. 자산 부재가 아니다
PERMISSION_DENIED = "PERMISSION_DENIED"
#: API가 값을 안 줌
API_NULL = "API_NULL"
#: 이 자산유형에 개념 자체가 없음. 갭 리포트에 출력하지 않는다
NOT_APPLICABLE = "NOT_APPLICABLE"
#: 조회 자체가 실패. 자산 부재가 아니다
COLLECT_ERROR = "COLLECT_ERROR"
#: 개념은 있고 AWS도 아는데 이 도구가 아직 그 API를 안 부른다
OUT_OF_SCOPE = "OUT_OF_SCOPE"

ALL_REASONS = (
    TAG_ABSENT, NOT_CONFIGURED, PERMISSION_DENIED,
    API_NULL, NOT_APPLICABLE, COLLECT_ERROR, OUT_OF_SCOPE,
)

#: 갭 리포트에 출력하지 않는 사유. 개념이 없는 걸 "미확인"으로 세면 리포트가 무너진다.
SILENT_REASONS = (NOT_APPLICABLE,)

#: 자산이 없다는 뜻이 절대 아닌 사유. B가 절대 혼동하면 안 되는 것들.
NOT_ABSENCE_REASONS = (PERMISSION_DENIED, COLLECT_ERROR, OUT_OF_SCOPE)

_HINTS = {
    TAG_ABSENT: "{detail} 태그를 달면 다음 실행부터 자동 수집됩니다",
    PERMISSION_DENIED: "{detail} 권한이 필요합니다",
    OUT_OF_SCOPE: "{detail}",
    COLLECT_ERROR: "조회에 실패했습니다({detail}). 자산이 없다는 뜻이 아닙니다",
}


def value(val: Any) -> dict[str, Any]:
    """정상 수집된 값."""
    return {"value": val, "reason": OK}


def missing(reason: str, *, detail: str | None = None, hint: str | None = None) -> dict[str, Any]:
    """값이 없는 필드. 왜 없는지를 함께 싣는다."""
    out: dict[str, Any] = {"value": None, "reason": reason}
    if hint is None and detail and reason in _HINTS:
        hint = _HINTS[reason].format(detail=detail)
    if hint:
        out["hint"] = hint
    return out


def is_missing(field: Any) -> bool:
    return isinstance(field, dict) and field.get("value") is None and field.get("reason") is not None


def counts_as_gap(field: Any) -> bool:
    """갭 리포트에 한 줄로 나갈 결측인가."""
    return is_missing(field) and field["reason"] not in SILENT_REASONS
