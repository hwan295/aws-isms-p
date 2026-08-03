"""RDS — 데이터(DBMS).

태그 필드명이 EC2와 다르다. RDS는 TagList다(docs/aws-facts.md §7).
통일은 extract 단계에서 한다. 여기서는 응답 그대로 둔다.
"""

from __future__ import annotations

from typing import Any

from ..base import ServiceCollector
from ..session import paginate


class RdsCollector(ServiceCollector):
    client_name = "rds"
    asset_types = ("데이터(DBMS)",)
    is_global = False
    required_actions = (
        "rds:DescribeDBInstances",
        "rds:DescribeDBClusters",
    )

    def collect(self, client: Any, *, region: str, session: Any) -> dict[str, Any]:
        return {
            "describe_db_instances": paginate(
                client, "describe_db_instances", "DBInstances"
            ),
            "describe_db_clusters": paginate(
                client, "describe_db_clusters", "DBClusters"
            ),
        }
