"""AWS 호출 결과를 네 가지 상태로 구분해 기록하는 래퍼.

이 구분이 이 프로젝트 전체에서 제일 중요하다.

    정상 응답    → 응답 그대로
    설정이 없음  → {"__status__": "NOT_CONFIGURED", ...}
    권한이 없음  → {"__status__": "PERMISSION_DENIED", ...}
    조회 실패    → {"__status__": "COLLECT_ERROR", ...}

권한 부족을 설정 부재로 처리하면 등급 제안이 통째로 틀린다.
권한이 없어서 암호화 설정을 못 읽었는데 "미암호화"로 기록하면 기밀성 등급이 잘못 나온다.
조회 실패도 마찬가지로 "설정 없음"이 아니다. 자산 부재로 오인되면 안 된다.

S3의 get_bucket_* 계열은 설정이 없을 때 값이 아니라 예외를 던진다.
그런데 일부는 예외가 아니라 빈 응답을 준다(docs/aws-facts.md §3).
예외와 빈 응답을 모두 "미설정"이라는 값으로 정규화하는 게 이 파일의 역할이다.
"""

from __future__ import annotations

from typing import Any, Callable

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
)

NOT_CONFIGURED = "NOT_CONFIGURED"
PERMISSION_DENIED = "PERMISSION_DENIED"
COLLECT_ERROR = "COLLECT_ERROR"

#: 권한 부족을 뜻하는 에러 코드. 서비스마다 이름이 달라 완전 일치로는 못 잡는다.
_PERMISSION_CODES = frozenset(
    {
        "AccessDenied",
        "AccessDeniedException",
        "UnauthorizedOperation",
        "AuthorizationError",
        "AuthFailure",
        "Forbidden",
        "MissingAuthenticationToken",
        "OptInRequired",
        "SubscriptionRequiredException",
    }
)


def is_permission_error(code: str) -> bool:
    """권한 부족 에러인가.

    서비스별로 AccessDenied / AccessDeniedException / ...Exception 접미사가 제각각이라
    완전 일치와 부분 일치를 함께 본다.
    """
    if code in _PERMISSION_CODES:
        return True
    return "AccessDenied" in code or "NotAuthorized" in code


def status(kind: str, *, error_code: str | None = None, detail: str | None = None) -> dict[str, Any]:
    """상태 표지 dict. 원본 덤프에 값 대신 들어간다."""
    out: dict[str, Any] = {"__status__": kind}
    if error_code is not None:
        out["error_code"] = error_code
    if detail is not None:
        out["detail"] = detail
    return out


def is_status(value: Any, kind: str | None = None) -> bool:
    """이 값이 상태 표지인가. extract 단계에서 값과 상태를 가르는 데 쓴다."""
    if not isinstance(value, dict) or "__status__" not in value:
        return False
    return kind is None or value["__status__"] == kind


def safe_call(
    fn: Callable[[], Any],
    *,
    absent_errors: tuple[str, ...] = (),
    absent_when: Callable[[Any], bool] | None = None,
) -> Any:
    """AWS 호출 한 건을 감싼다.

    absent_errors
        이 에러 코드가 나오면 "설정 없음"이다. **추측해서 채우지 말 것.**
        docs/aws-facts.md §3에 실측으로 확인한 코드만 들어 있다.
    absent_when
        예외가 아니라 빈 응답으로 "설정 없음"을 알리는 API를 위한 판정식.
        get_bucket_versioning은 Status 키가 없는 정상 응답을 준다.
    """
    try:
        response = fn()
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        message = exc.response.get("Error", {}).get("Message", "")
        if code in absent_errors:
            return status(NOT_CONFIGURED, error_code=code)
        if is_permission_error(code):
            return status(PERMISSION_DENIED, error_code=code, detail=message)
        # 알 수 없는 에러. 여기서 raise하면 전 리전 순회가 통째로 죽는다.
        # 서비스가 없는 리전·스로틀링·moto 미구현이 전부 이 경로로 온다.
        return status(COLLECT_ERROR, error_code=code, detail=message)
    except EndpointConnectionError as exc:
        # 해당 리전에 그 서비스 엔드포인트가 없는 경우. 전 리전 순회의 상시 조건이다.
        return status(COLLECT_ERROR, error_code="EndpointConnectionError", detail=str(exc))
    except BotoCoreError as exc:
        return status(COLLECT_ERROR, error_code=type(exc).__name__, detail=str(exc))

    if absent_when is not None and absent_when(response):
        return status(NOT_CONFIGURED, error_code="EMPTY_RESPONSE")
    return response
