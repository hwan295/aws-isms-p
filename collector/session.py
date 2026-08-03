"""계정·리전 순회와 페이지네이션.

모든 서비스가 똑같이 필요한 일이라 한 곳에 모았다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterator

import boto3
from botocore.config import Config

from .safe_call import safe_call

log = logging.getLogger(__name__)

#: 순회 대상 리전. not-opted-in 리전은 호출해도 실패한다(docs/aws-facts.md §2).
USABLE_OPT_IN_STATUS = frozenset({"opt-in-not-required", "opted-in"})

#: 전역 서비스 수집을 매달 리전. AWS 전역 서비스의 표준 엔드포인트 리전.
GLOBAL_REGION = "us-east-1"


def new_run_id(now: datetime | None = None) -> str:
    """실행 단위 식별자.

    전 리전 순회는 수 분이 걸려 collected_at이 레코드마다 다르다.
    비교 기준선은 run_id로 잡는다(docs/design.md §5.6).
    """
    now = now or datetime.now(timezone.utc)
    return f"run-{now:%Y%m%d-%H%M}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_boto_config() -> Config:
    """스로틀링 재시도. 전 리전 순회는 호출량이 많아 adaptive가 필요하다."""
    return Config(retries={"max_attempts": 5, "mode": "adaptive"})


class CollectorSession:
    """자격증명 하나로 계정 1개를 수집한다.

    멀티계정(Organizations AssumeRole)은 프로토타입 범위 밖이지만,
    호출부는 계정 루프로 써두어 나중에 세션 생성만 끼워 넣으면 되게 한다.
    """

    def __init__(self, boto_session: boto3.Session | None = None):
        self.boto_session = boto_session or boto3.Session()
        self._config = make_boto_config()
        self._clients: dict[tuple[str, str], Any] = {}

    def client(self, service: str, region: str) -> Any:
        key = (service, region)
        if key not in self._clients:
            self._clients[key] = self.boto_session.client(
                service, region_name=region, config=self._config
            )
        return self._clients[key]

    def account_id(self) -> str:
        resp = self.client("sts", GLOBAL_REGION).get_caller_identity()
        return resp["Account"]

    def account_alias(self, region: str = GLOBAL_REGION) -> Any:
        """계정 별칭. 없으면 빈 리스트가 정상이다."""
        iam = self.client("iam", region)
        resp = safe_call(lambda: iam.list_account_aliases())
        if isinstance(resp, dict) and "__status__" in resp:
            return resp
        aliases = resp.get("AccountAliases", [])
        return aliases[0] if aliases else None

    def regions(self, only: tuple[str, ...] | None = None) -> list[str]:
        """활성 리전 목록.

        미사용 리전 방치가 자산 누락 1순위 원인이고, 결함사례 4가 지적하는 지점이다.
        기본값은 전 리전 순회다.
        """
        ec2 = self.client("ec2", self.boto_session.region_name or GLOBAL_REGION)
        # describe_regions에는 페이지네이터가 없다(docs/aws-facts.md §1).
        resp = ec2.describe_regions()
        names = [
            r["RegionName"]
            for r in resp["Regions"]
            if r.get("OptInStatus", "opt-in-not-required") in USABLE_OPT_IN_STATUS
        ]
        if only:
            requested = set(only)
            unknown = requested - set(names)
            if unknown:
                log.warning("요청한 리전이 활성 목록에 없다: %s", sorted(unknown))
            names = [n for n in names if n in requested]
        return sorted(names)


def paginate(client: Any, operation: str, result_key: str, **kwargs: Any) -> Any:
    """페이지네이션은 예외 없이.

    그냥 호출하면 자산이 많을 때 조용히 일부만 받는다.
    자산 목록 도구에서 가장 치명적이고 가장 늦게 발견되는 버그다.

    페이지네이터가 없는 API(describe_addresses, describe_regions)는 직접 호출한다.
    있는지 없는지는 can_paginate()에게 묻는다. 수집기가 외우지 않는다.
    """

    def _run() -> dict[str, Any]:
        if not client.can_paginate(operation):
            return getattr(client, operation)(**kwargs)

        paginator = client.get_paginator(operation)
        merged: list[Any] = []
        pages = 0
        for page in paginator.paginate(**kwargs):
            pages += 1
            merged.extend(page.get(result_key, []))
        return {result_key: merged, "__pages__": pages}

    return safe_call(_run)


def iter_service_regions(
    collectors: list[Any], regions: list[str]
) -> Iterator[tuple[Any, str]]:
    """수집기 × 리전 조합. 전역 서비스는 리전 루프 밖에서 1회만.

    s3.list_buckets, IAM, CloudFront, Route 53을 리전 루프 안에 넣으면
    같은 자산이 리전 수만큼 중복된다.
    """
    for collector in collectors:
        if collector.is_global:
            yield collector, GLOBAL_REGION
        else:
            for region in regions:
                yield collector, region
