"""AWS Backup — 무결성 등급의 근거.

무결성 판정은 스냅샷 개수가 아니라 list_protected_resources()로 한다.
"스냅샷 3건 존재"는 심사에서 반박당하지만
"백업 계획 daily-prd에 포함되어 최종 보호 시각 ○○"는 통과한다
(docs/design.md §D, docs/field-mapping.md §5).

주의: list_protected_resources는 moto 미구현이다(docs/aws-facts.md §4).
safe_call이 COLLECT_ERROR로 받아내므로 순회가 죽지는 않지만,
이 API의 응답 구조 검증은 botocore Stubber 테스트가 담당한다.
"""

from __future__ import annotations

from typing import Any

from ..base import ServiceCollector
from ..session import paginate


class BackupCollector(ServiceCollector):
    client_name = "backup"
    asset_types = ("정보", "데이터(DBMS)", "서버")
    is_global = False
    required_actions = (
        "backup:ListProtectedResources",
        "backup:ListBackupPlans",
    )

    def collect(self, client: Any, *, region: str, session: Any) -> dict[str, Any]:
        return {
            "list_protected_resources": paginate(
                client, "list_protected_resources", "Results"
            ),
            "list_backup_plans": paginate(
                client, "list_backup_plans", "BackupPlansList"
            ),
        }
