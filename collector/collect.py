"""collect 명령 — AWS 응답을 손대지 않고 통째로 덤프한다."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .dump import write_raw, write_run_manifest
from .registry import discover
from .safe_call import COLLECT_ERROR, NOT_CONFIGURED, PERMISSION_DENIED
from .session import CollectorSession, iter_service_regions, new_run_id, utc_now_iso

log = logging.getLogger(__name__)

_STATUS_KINDS = (NOT_CONFIGURED, PERMISSION_DENIED, COLLECT_ERROR)


def count_statuses(node: Any, counter: dict[str, int]) -> None:
    """덤프 안의 상태 표지를 센다. 담당자에게 보여줄 요약의 재료."""
    if isinstance(node, dict):
        kind = node.get("__status__")
        if kind in _STATUS_KINDS:
            counter[kind] = counter.get(kind, 0) + 1
            return
        for value in node.values():
            count_statuses(value, counter)
    elif isinstance(node, list):
        for value in node:
            count_statuses(value, counter)


def run_collect(
    *,
    session: CollectorSession | None = None,
    regions: tuple[str, ...] | None = None,
    run_id: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    session = session or CollectorSession()
    run_id = run_id or new_run_id()
    started_at = utc_now_iso()

    account = session.account_id()
    alias = session.account_alias()
    region_list = session.regions(only=regions)
    collectors = discover()

    log.info("run_id=%s account=%s regions=%d services=%d",
             run_id, account, len(region_list), len(collectors))

    files: list[str] = []
    status_counter: dict[str, int] = {}

    for collector, region in iter_service_regions(collectors, region_list):
        # client_name이 None인 수집기는 여러 서비스를 묶는다. 클라이언트를 직접 만든다.
        client = session.client(collector.client_name, region) if collector.client_name else None
        collected_at = utc_now_iso()
        data = collector.collect(client, region=region, session=session)
        count_statuses(data, status_counter)

        path = write_raw(
            run_id=run_id,
            account=account,
            region=region,
            service=collector.dump_name,
            collected_at=collected_at,
            source_api=list(collector.required_actions),
            is_global=collector.is_global,
            data=data,
            root=root,
        )
        files.append(str(path))
        log.debug("wrote %s", path)

    finished_at = utc_now_iso()
    stats = {
        "services": len(collectors),
        "regions": len(region_list),
        "files": len(files),
        **{k: status_counter.get(k, 0) for k in _STATUS_KINDS},
    }
    manifest = write_run_manifest(
        run_id=run_id,
        account=account,
        account_alias=alias,
        regions=region_list,
        started_at=started_at,
        finished_at=finished_at,
        files=files,
        stats=stats,
        root=root,
    )

    return {
        "run_id": run_id,
        "account_id": account,
        "account_alias": alias,
        "regions": region_list,
        "files": files,
        "manifest": str(manifest),
        "stats": stats,
    }


def print_summary(result: dict[str, Any]) -> None:
    stats = result["stats"]
    print()
    print(f"  run_id      {result['run_id']}")
    print(f"  계정         {result['account_id']}"
          + (f" ({result['account_alias']})" if result.get("account_alias") else ""))
    print(f"  리전         {stats['regions']}개")
    print(f"  서비스       {stats['services']}개")
    print(f"  덤프 파일    {stats['files']}개  →  {Path(result['manifest']).parent}")
    print()
    print("  [수집 중 만난 상태]")
    print(f"    NOT_CONFIGURED     {stats[NOT_CONFIGURED]:5d}  설정이 없음 (사실 자체가 정보)")
    print(f"    PERMISSION_DENIED  {stats[PERMISSION_DENIED]:5d}  권한 부족 — 자산 부재 아님")
    print(f"    COLLECT_ERROR      {stats[COLLECT_ERROR]:5d}  조회 실패 — 자산 부재 아님")
    print()
