"""원본 덤프 저장.

snapshots/raw/{run_id}/{account}/{region}/{service}.json

수집 시점에 필드를 골라 버리면 나중에 B가 "이 필드도 필요하다"고 할 때
AWS를 다시 호출해야 한다. 자격증명이 필요하고, 전 리전 순회는 수 분이 걸리며,
그 사이 리소스가 바뀌어 비교 기준선이 흔들린다.

그리고 원본 덤프 자체가 증적이다.
"이 시점에 AWS가 이렇게 응답했다"는 기록이 있어야 대장의 각 칸이 어디서 왔는지 추적된다.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

RAW_ROOT = Path("snapshots/raw")


class AwsJsonEncoder(json.JSONEncoder):
    """boto3는 datetime과 bytes를 그대로 준다. 원본을 버리지 않고 직렬화한다."""

    def default(self, o: Any) -> Any:
        if isinstance(o, (_dt.datetime, _dt.date)):
            return o.isoformat()
        if isinstance(o, bytes):
            return o.decode("utf-8", errors="replace")
        if isinstance(o, set):
            return sorted(o)
        return super().default(o)


def raw_path(run_id: str, account: str, region: str, service: str, root: Path | None = None) -> Path:
    return (root or RAW_ROOT) / run_id / account / region / f"{service}.json"


def write_raw(
    *,
    run_id: str,
    account: str,
    region: str,
    service: str,
    collected_at: str,
    source_api: list[str],
    is_global: bool,
    data: dict[str, Any],
    root: Path | None = None,
) -> Path:
    """서비스 한 개의 응답을 메타와 함께 저장한다."""
    path = raw_path(run_id, account, region, service, root)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "meta": {
            "run_id": run_id,
            "account_id": account,
            "region": region,
            "service": service,
            "collected_at": collected_at,
            "source_api": source_api,
            "is_global": is_global,
        },
        "data": data,
    }
    path.write_text(
        json.dumps(payload, cls=AwsJsonEncoder, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def write_run_manifest(
    *,
    run_id: str,
    account: str,
    account_alias: Any,
    regions: list[str],
    started_at: str,
    finished_at: str,
    files: list[str],
    stats: dict[str, Any],
    root: Path | None = None,
) -> Path:
    """실행 1회의 요약. extract가 무엇을 읽어야 하는지 여기서 안다."""
    path = (root or RAW_ROOT) / run_id / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "account_id": account,
        "account_alias": account_alias,
        "regions": regions,
        "started_at": started_at,
        "finished_at": finished_at,
        "files": files,
        "stats": stats,
    }
    path.write_text(
        json.dumps(payload, cls=AwsJsonEncoder, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
