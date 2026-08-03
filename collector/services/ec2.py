"""EC2 — 서버 / 정보(전자적)·저장장치 / 네트워크장비 / 가상자원.

응답을 가공하지 않는다. 필드를 고르지 않는다.
"""

from __future__ import annotations

from typing import Any

from ..base import ServiceCollector
from ..safe_call import safe_call
from ..session import paginate


class Ec2Collector(ServiceCollector):
    client_name = "ec2"
    asset_types = ("서버", "정보", "네트워크장비", "가상자원")
    is_global = False
    required_actions = (
        "ec2:DescribeInstances",
        "ec2:DescribeAddresses",
        "ec2:DescribeVolumes",
        "ec2:DescribeSnapshots",
        "ec2:DescribeImages",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
    )

    def collect(self, client: Any, *, region: str, session: Any) -> dict[str, Any]:
        return {
            "describe_instances": paginate(client, "describe_instances", "Reservations"),
            # describe_addresses에는 페이지네이터가 없다. paginate()가 알아서 직접 호출한다.
            "describe_addresses": safe_call(lambda: client.describe_addresses()),
            "describe_volumes": paginate(client, "describe_volumes", "Volumes"),
            # OwnerIds/Owners를 생략하면 공개 스냅샷·이미지 수만 건이 딸려온다.
            # moto에서는 필터가 안 먹어 차이가 안 보이지만 실계정에서 터진다.
            "describe_snapshots": paginate(
                client, "describe_snapshots", "Snapshots", OwnerIds=["self"]
            ),
            "describe_images": paginate(
                client, "describe_images", "Images", Owners=["self"]
            ),
            "describe_security_groups": paginate(
                client, "describe_security_groups", "SecurityGroups"
            ),
            "describe_vpcs": paginate(client, "describe_vpcs", "Vpcs"),
            "describe_subnets": paginate(client, "describe_subnets", "Subnets"),
        }
