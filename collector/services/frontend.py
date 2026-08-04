"""정보시스템(응용프로그램) — 외부 노출 경로의 출처.

안내서 자산 유형 '정보시스템(응용프로그램)'에 해당하는 AWS 자원은
ALB/NLB, CloudFront 배포, API Gateway다. 이 유형은 지금까지 수집기가 없어
0건이었고, 0건은 "자산이 없다"가 아니라 "안 봤다"였다.

**이 파일의 더 큰 목적은 exposure_path다.**
공인 IP가 없는 EC2도 ALB 뒤에 있으면 외부에 노출된다. 지금까지 exposure_path가
전 자산 OUT_OF_SCOPE였던 것은 그 앞단을 아무도 안 봤기 때문이다
(docs/contract.md §5-6). 리스너·타깃그룹·오리진을 함께 담아 두면
extract 2패스가 "이 자산이 무엇 뒤에 있는가"를 조인할 수 있다.

CloudFront는 전역 서비스라 별도 수집기로 뺐다. 리전 루프에 넣으면
같은 배포가 리전 수만큼 중복 등록된다(CLAUDE.md 구현 규칙 ②).

주의: list_distributions 응답에는 Origins가 없다(실측 확인).
오리진을 알려면 배포마다 get_distribution을 불러야 한다.
"""

from __future__ import annotations

from typing import Any

from ..base import ServiceCollector
from ..safe_call import is_status, safe_call
from ..session import paginate


class FrontendCollector(ServiceCollector):
    """리전 단위 프런트엔드 — ALB/NLB와 API Gateway."""

    client_name = None
    service_name = "frontend"
    asset_types = ("정보시스템(응용프로그램)",)
    is_global = False
    required_actions = (
        "elasticloadbalancing:DescribeLoadBalancers",
        "elasticloadbalancing:DescribeListeners",
        "elasticloadbalancing:DescribeTargetGroups",
        "elasticloadbalancing:DescribeTargetHealth",
        "elasticloadbalancing:DescribeTags",
        "apigateway:GET",
    )

    def collect(self, client: Any, *, region: str, session: Any) -> dict[str, Any]:
        data: dict[str, Any] = {}

        elb = session.client("elbv2", region)
        data["describe_load_balancers"] = paginate(
            elb, "describe_load_balancers", "LoadBalancers"
        )
        lb_arns = _values(data["describe_load_balancers"], "LoadBalancers", "LoadBalancerArn")

        # ELB 태그는 응답에 없고 별도 호출이다(S3와 같은 사정).
        # extract가 arn으로 찾아 쓰도록 arn별 dict로 담는다.
        data["tags"] = {
            arn: safe_call(lambda a=arn: elb.describe_tags(ResourceArns=[a]))
            for arn in lb_arns
        }

        # 리스너 — 프로토콜(HTTP/HTTPS)이 전송구간 암호화의 근거다.
        data["listeners"] = {
            arn: paginate(elb, "describe_listeners", "Listeners", LoadBalancerArn=arn)
            for arn in lb_arns
        }

        # 타깃그룹·타깃 — "이 ALB 뒤에 어느 인스턴스가 있는가"가 exposure_path의 재료다.
        data["describe_target_groups"] = paginate(
            elb, "describe_target_groups", "TargetGroups"
        )
        data["target_health"] = {
            arn: safe_call(lambda a=arn: elb.describe_target_health(TargetGroupArn=a))
            for arn in _values(
                data["describe_target_groups"], "TargetGroups", "TargetGroupArn"
            )
        }

        # API Gateway — v1(REST)과 v2(HTTP/WebSocket)는 별개 서비스이고 응답 모양도 다르다.
        data["get_rest_apis"] = paginate(session.client("apigateway", region), "get_rest_apis", "items")
        data["get_apis"] = paginate(session.client("apigatewayv2", region), "get_apis", "Items")

        return data


class CloudFrontCollector(ServiceCollector):
    """CloudFront 배포. 전역 서비스라 리전 루프 밖에서 1회만 돈다."""

    client_name = "cloudfront"
    asset_types = ("정보시스템(응용프로그램)",)
    is_global = True
    required_actions = (
        "cloudfront:ListDistributions",
        "cloudfront:GetDistribution",
        "cloudfront:ListTagsForResource",
    )

    def collect(self, client: Any, *, region: str, session: Any) -> dict[str, Any]:
        data: dict[str, Any] = {}
        # 목록이 DistributionList.Items에 중첩돼 있다. paginate가 마지막 조각(Items)으로 담는다.
        data["list_distributions"] = paginate(
            client, "list_distributions", "DistributionList.Items"
        )

        ids, arns = _distribution_refs(data["list_distributions"])

        # 목록 응답에 Origins가 없다. 오리진을 알아야 "이 S3 버킷이 CloudFront 뒤에 있다"를
        # 판정할 수 있으므로 배포마다 상세를 부른다.
        data["distributions"] = {
            did: safe_call(lambda d=did: client.get_distribution(Id=d)) for did in ids
        }
        data["tags"] = {
            arn: safe_call(lambda a=arn: client.list_tags_for_resource(Resource=a))
            for arn in arns
        }
        return data


def _values(response: Any, key: str, field: str) -> list[str]:
    """목록 응답에서 후속 조회용 값을 뽑는다. 실패한 응답이면 빈 목록."""
    if is_status(response) or not isinstance(response, dict):
        return []
    rows = response.get(key) or []
    return [r[field] for r in rows if isinstance(r, dict) and field in r]


def _distribution_refs(response: Any) -> tuple[list[str], list[str]]:
    """배포마다 상세·태그를 부르기 위한 Id와 ARN."""
    return (
        _values(response, "Items", "Id"),
        _values(response, "Items", "ARN"),
    )
