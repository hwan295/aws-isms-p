"""컨테이너 이미지와 가상 데스크톱 — 0건이던 유형을 채운다.

**ECR은 가상자원이다.** CLAUDE.md 확정 사항이 자산유형 11종을 정의하면서
가상자원을 "AMI·컨테이너 이미지·스냅샷"으로 명시했다.

**자산 단위는 리포지토리로 잡는다.** 이미지를 낱개로 등재하면 EBS 스냅샷 2339건과
같은 문제가 난다 — CI가 커밋마다 이미지를 밀어 올려 수천 건이 쌓이는데 대장에
그걸 한 줄씩 나열하면 목록이 무용지물이 된다. 조직 태그가 붙는 단위도 리포지토리다.
이미지 목록은 raw 덤프에 그대로 남으므로, 낱개 등재가 필요해지면 재추출로 바꿀 수 있다.

**소프트웨어 유형은 여전히 0건이다.** 그 유형을 채우려면 서버에 설치된 소프트웨어를
알아야 하고 그건 ssm.list_inventory_entries인데, moto가 SSM Inventory를 구현하지
않는다(backup.list_protected_resources와 같은 사정, docs/aws-facts.md §4).
0건을 "없다"가 아니라 "확인하지 않았다"로 내보내는 것이 현재의 정답이다.

WorkSpaces는 PC 유형이다. 온프레미스 단말은 영원히 수기이므로
이 수집기가 채우는 것은 PC 자산의 일부일 뿐이다.
"""

from __future__ import annotations

from typing import Any

from ..base import ServiceCollector
from ..safe_call import is_status, safe_call
from ..session import paginate


class EcrCollector(ServiceCollector):
    client_name = "ecr"
    asset_types = ("가상자원",)
    is_global = False
    required_actions = (
        "ecr:DescribeRepositories",
        "ecr:DescribeImages",
        "ecr:ListTagsForResource",
    )

    def collect(self, client: Any, *, region: str, session: Any) -> dict[str, Any]:
        data: dict[str, Any] = {}
        data["describe_repositories"] = paginate(
            client, "describe_repositories", "repositories"
        )

        # 자산 하나당 여러 응답을 묶어 담는다(S3의 buckets와 같은 모양).
        # 태그가 응답에 없고 별도 호출이라 이 구조가 필요하다.
        data["repositories"] = {
            r["repositoryName"]: {
                "tags": safe_call(
                    lambda a=r["repositoryArn"]: client.list_tags_for_resource(
                        resourceArn=a)
                ),
                "images": paginate(
                    client, "describe_images", "imageDetails",
                    repositoryName=r["repositoryName"],
                ),
            }
            for r in _rows(data["describe_repositories"], "repositories")
            if "repositoryName" in r and "repositoryArn" in r
        }
        return data


class WorkspacesCollector(ServiceCollector):
    client_name = "workspaces"
    asset_types = ("PC",)
    is_global = False
    required_actions = (
        "workspaces:DescribeWorkspaces",
        "workspaces:DescribeWorkspaceDirectories",
        "workspaces:DescribeTags",
    )

    def collect(self, client: Any, *, region: str, session: Any) -> dict[str, Any]:
        data: dict[str, Any] = {}
        data["describe_workspaces"] = paginate(
            client, "describe_workspaces", "Workspaces"
        )
        data["describe_workspace_directories"] = paginate(
            client, "describe_workspace_directories", "Directories"
        )
        # 태그가 응답에 없고 자산마다 별도 호출이다. ECR·ELB와 같은 모양으로 담는다.
        data["workspaces"] = {
            w["WorkspaceId"]: {
                "tags": safe_call(
                    lambda i=w["WorkspaceId"]: client.describe_tags(ResourceId=i)
                ),
            }
            for w in _rows(data["describe_workspaces"], "Workspaces")
            if "WorkspaceId" in w
        }
        return data


def _rows(response: Any, key: str) -> list[dict]:
    if is_status(response) or not isinstance(response, dict):
        return []
    rows = response.get(key)
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
