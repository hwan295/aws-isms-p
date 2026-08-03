"""모든 서비스 수집기가 지켜야 할 형식.

새 서비스를 추가할 때 이 파일을 복사 기준으로 삼는다.

required_actions를 클래스가 직접 선언하게 하는 이유(docs/design.md §5.7):
최소권한 IAM 정책을 코드에서 자동으로 뽑을 수 있고, 권한을 추가할 때
정책 문서와 코드가 어긋나지 않는다. 보안 도구가 고객 계정에 붙는 상황에서
ReadOnlyAccess를 요구하지 않는다는 점 자체가 설계 근거가 된다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

#: 상태 변경 호출을 나타내는 동사. 이 도구는 읽기 전용이다.
WRITE_VERBS = (
    "create", "delete", "modify", "put", "update", "attach", "detach",
    "start", "stop", "terminate", "run", "reboot", "associate", "disassociate",
    "authorize", "revoke", "enable", "disable", "register", "deregister",
    "add", "remove", "set", "restore", "copy", "import", "export", "tag", "untag",
)


class ServiceCollector(ABC):
    """AWS 서비스 하나를 담당하는 수집기.

    응답을 가공하지 않는다. 필드를 고르지 않는다. 그대로 반환한다.
    필드 선별은 extract 단계가 config/extract_map.yaml 선언에 따라 한다.
    """

    #: boto3 클라이언트 이름 ('ec2', 'rds', ...).
    #: None이면 수집기가 session으로 클라이언트를 직접 만든다 (여러 서비스를 묶는 경우).
    client_name: str | None
    #: 덤프 파일 이름. 기본은 client_name.
    service_name: str = ""
    #: 이 수집기가 재료를 대는 ISMS-P 자산유형 (안내서 11종 중)
    asset_types: tuple[str, ...] = ()
    #: 전역 서비스인가. True면 리전 루프 밖에서 1회만 호출한다.
    #: s3.list_buckets, iam, cloudfront, route53을 리전 루프에 넣으면
    #: 같은 자산이 리전 수만큼 중복된다.
    is_global: bool = False
    #: 이 수집기가 쓰는 IAM 액션. 최소권한 정책 생성의 재료.
    required_actions: tuple[str, ...] = ()

    @abstractmethod
    def collect(self, client: Any, *, region: str, session: Any) -> dict[str, Any]:
        """API를 전부 호출하고 {api_name: 응답} 을 그대로 반환한다.

        응답을 가공하지 마라. 필드를 고르지 마라.
        """

    @property
    def dump_name(self) -> str:
        return self.service_name or self.client_name or type(self).__name__.lower()

    @classmethod
    def write_actions(cls) -> list[str]:
        """선언된 액션 중 쓰기로 의심되는 것. 비어 있어야 정상이다."""
        found = []
        for action in cls.required_actions:
            verb = action.split(":", 1)[-1]
            lowered = verb[0].lower() + verb[1:] if verb else ""
            if lowered.startswith(WRITE_VERBS):
                found.append(action)
        return found
