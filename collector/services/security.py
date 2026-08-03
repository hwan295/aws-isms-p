"""보안시스템 — 결함사례 1 대응의 절반.

안내서 자산 유형표는 "보안시스템: 침입차단시스템, 침입탐지시스템, 침입방지시스템,
개인정보유출방지시스템 등"을 명시적으로 요구한다.

**나머지 절반은 이 파일이 절대 채울 수 없다.** 출력물 보안·문서암호화(DRM)·USB 매체제어는
온프레미스 엔드포인트 솔루션이고 AWS API 대상이 아니다. 그건 config/manual_items.yaml이 담당한다.

여러 AWS 서비스를 한 덤프로 묶기 때문에 client_name이 None이고 클라이언트를 직접 만든다.

미활성 상태가 값이 아니라 예외로 오는 API가 둘 있다(docs/aws-facts.md §9).
그때의 NOT_CONFIGURED는 그 자체가 "그 통제가 없다"는 증적이다.
"""

from __future__ import annotations

from typing import Any

from ..base import ServiceCollector
from ..safe_call import is_status, safe_call
from ..session import paginate


class SecurityCollector(ServiceCollector):
    client_name = None
    service_name = "security"
    asset_types = ("보안시스템",)
    is_global = False
    required_actions = (
        "wafv2:ListWebACLs",
        "guardduty:ListDetectors",
        "guardduty:GetDetector",
        "kms:ListKeys",
        "kms:DescribeKey",
        "acm:ListCertificates",
        "cloudtrail:DescribeTrails",
        "cloudtrail:GetTrailStatus",
        "config:DescribeConfigurationRecorders",
        "config:DescribeConfigurationRecorderStatus",
        "securityhub:DescribeHub",
        "secretsmanager:ListSecrets",
        "macie2:GetMacieSession",
        "network-firewall:ListFirewalls",
        "inspector2:BatchGetAccountStatus",
        "shield:DescribeSubscription",
    )

    def collect(self, client: Any, *, region: str, session: Any) -> dict[str, Any]:
        c = lambda name: session.client(name, region)  # noqa: E731

        data: dict[str, Any] = {}

        # 침입차단(웹) — list_web_acls에는 페이지네이터가 없다. Scope는 필수 인자.
        wafv2 = c("wafv2")
        data["list_web_acls"] = safe_call(lambda: wafv2.list_web_acls(Scope="REGIONAL"))

        # 침입탐지
        guardduty = c("guardduty")
        data["list_detectors"] = paginate(guardduty, "list_detectors", "DetectorIds")
        data["detectors"] = {
            did: safe_call(lambda d=did: guardduty.get_detector(DetectorId=d))
            for did in _ids(data["list_detectors"], "DetectorIds")
        }

        # 침입방지
        data["list_firewalls"] = paginate(c("network-firewall"), "list_firewalls", "Firewalls")

        # 암호키 — 고객관리형(CUSTOMER)만 자산으로 등재한다. AWS 관리형은 계정 부속이다.
        kms = c("kms")
        data["list_keys"] = paginate(kms, "list_keys", "Keys")
        data["keys"] = {
            kid: safe_call(lambda k=kid: kms.describe_key(KeyId=k))
            for kid in _ids(data["list_keys"], "Keys", field="KeyId")
        }

        data["list_certificates"] = paginate(
            c("acm"), "list_certificates", "CertificateSummaryList"
        )

        # 감사로그
        cloudtrail = c("cloudtrail")
        data["describe_trails"] = safe_call(lambda: cloudtrail.describe_trails())
        data["trail_status"] = {
            name: safe_call(lambda n=name: cloudtrail.get_trail_status(Name=n))
            for name in _ids(data["describe_trails"], "trailList", field="Name")
        }

        config = c("config")
        data["describe_configuration_recorders"] = safe_call(
            lambda: config.describe_configuration_recorders()
        )
        data["describe_configuration_recorder_status"] = safe_call(
            lambda: config.describe_configuration_recorder_status()
        )

        # 통합 관제 — 미활성 시 예외를 던진다. 그게 "없다"는 증적이다.
        securityhub = c("securityhub")
        data["describe_hub"] = safe_call(
            lambda: securityhub.describe_hub(),
            absent_errors=("InvalidAccessException", "ResourceNotFoundException"),
        )

        data["list_secrets"] = paginate(c("secretsmanager"), "list_secrets", "SecretList")

        # 개인정보 탐지 — S3 한정이다. 엔드포인트·메일·웹 DLP는 여전히 수기 대상.
        data["get_macie_session"] = safe_call(
            lambda: c("macie2").get_macie_session(),
            absent_errors=("AccessDeniedException", "ResourceNotFoundException"),
        )

        data["batch_get_account_status"] = safe_call(
            lambda: c("inspector2").batch_get_account_status()
        )

        # DDoS 방어 — 미구독 시 예외
        data["describe_subscription"] = safe_call(
            lambda: c("shield").describe_subscription(),
            absent_errors=("ResourceNotFoundException",),
        )

        return data


def _ids(response: Any, key: str, field: str | None = None) -> list[str]:
    """목록 응답에서 후속 조회용 식별자를 뽑는다. 실패한 응답이면 빈 목록."""
    if is_status(response) or not isinstance(response, dict):
        return []
    rows = response.get(key) or []
    if field is None:
        return [r for r in rows if isinstance(r, str)]
    return [r[field] for r in rows if isinstance(r, dict) and field in r]
