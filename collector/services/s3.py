"""S3 — 정보(전자적)·저장장치.

두 가지 함정이 있다.

1. list_buckets만 전역이고, get_bucket_* 은 **버킷별 리전 클라이언트**로 불러야 한다.
   다른 리전 클라이언트로 부르면 일부 호출이 실패한다.
2. 설정이 없을 때의 신호가 두 갈래다 — 예외를 던지는 것과 빈 응답을 주는 것.
   실측 표는 docs/aws-facts.md §3.
"""

from __future__ import annotations

from typing import Any

from ..base import ServiceCollector
from ..safe_call import safe_call
from ..session import paginate

#: 설정 없음을 뜻하는 에러 코드. 추측이 아니라 실측으로 채웠다(docs/aws-facts.md §3).
#: NoSuchBucketPolicy는 moto에서는 안 나오지만 실계정에서 나온다. 둘 다 대비한다.
_ABSENT = {
    "get_bucket_encryption": ("ServerSideEncryptionConfigurationNotFoundError",),
    "get_bucket_policy_status": ("NoSuchBucketPolicy",),
    "get_public_access_block": ("NoSuchPublicAccessBlockConfiguration",),
    "get_bucket_tagging": ("NoSuchTagSet",),
    "get_object_lock_configuration": ("ObjectLockConfigurationNotFoundError",),
}


class S3Collector(ServiceCollector):
    client_name = "s3"
    asset_types = ("정보",)
    #: list_buckets가 전역이라 이 수집기는 리전 루프 밖에서 1회만 돈다.
    is_global = True
    required_actions = (
        "s3:ListAllMyBuckets",
        "s3:GetBucketLocation",
        "s3:GetEncryptionConfiguration",
        "s3:GetBucketPolicyStatus",
        "s3:GetBucketPublicAccessBlock",
        "s3:GetBucketVersioning",
        "s3:GetBucketLogging",
        "s3:GetBucketTagging",
        "s3:GetBucketObjectLockConfiguration",
    )

    def collect(self, client: Any, *, region: str, session: Any) -> dict[str, Any]:
        listed = paginate(client, "list_buckets", "Buckets")
        result: dict[str, Any] = {"list_buckets": listed}

        if not isinstance(listed, dict) or "Buckets" not in listed:
            # list_buckets 자체가 실패했다. 버킷별 조회는 의미가 없다.
            result["buckets"] = {}
            return result

        per_bucket: dict[str, Any] = {}
        for bucket in listed["Buckets"]:
            name = bucket["Name"]
            per_bucket[name] = self._collect_bucket(client, name, session)
        result["buckets"] = per_bucket
        return result

    def _collect_bucket(self, global_client: Any, name: str, session: Any) -> dict[str, Any]:
        location = safe_call(lambda: global_client.get_bucket_location(Bucket=name))
        bucket_region = _region_of(location)

        # 버킷별 리전 클라이언트. 전역 클라이언트로 부르면 일부 호출이 실패한다.
        client = (
            session.client("s3", bucket_region) if bucket_region else global_client
        )

        return {
            "get_bucket_location": location,
            "get_bucket_encryption": safe_call(
                lambda: client.get_bucket_encryption(Bucket=name),
                absent_errors=_ABSENT["get_bucket_encryption"],
            ),
            "get_bucket_policy_status": safe_call(
                lambda: client.get_bucket_policy_status(Bucket=name),
                absent_errors=_ABSENT["get_bucket_policy_status"],
                # moto는 예외 대신 {'PolicyStatus': {}} 를 준다.
                absent_when=lambda r: not r.get("PolicyStatus"),
            ),
            "get_public_access_block": safe_call(
                lambda: client.get_public_access_block(Bucket=name),
                absent_errors=_ABSENT["get_public_access_block"],
            ),
            # 버전관리·로깅은 미설정 시 예외가 아니라 키 없는 정상 응답이 온다.
            "get_bucket_versioning": safe_call(
                lambda: client.get_bucket_versioning(Bucket=name),
                absent_when=lambda r: "Status" not in r,
            ),
            "get_bucket_logging": safe_call(
                lambda: client.get_bucket_logging(Bucket=name),
                absent_when=lambda r: "LoggingEnabled" not in r,
            ),
            "get_bucket_tagging": safe_call(
                lambda: client.get_bucket_tagging(Bucket=name),
                absent_errors=_ABSENT["get_bucket_tagging"],
            ),
            "get_object_lock_configuration": safe_call(
                lambda: client.get_object_lock_configuration(Bucket=name),
                absent_errors=_ABSENT["get_object_lock_configuration"],
            ),
        }


def _region_of(location_response: Any) -> str | None:
    """get_bucket_location 응답에서 리전을 꺼낸다.

    us-east-1 버킷은 LocationConstraint가 None으로 온다. 이건 미설정이 아니라 값이다.
    """
    if not isinstance(location_response, dict) or "__status__" in location_response:
        return None
    if "LocationConstraint" not in location_response:
        return None
    return location_response["LocationConstraint"] or "us-east-1"
