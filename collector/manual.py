"""수집 불가 항목을 담당자 작업 지시로 바꾼다.

이 도구는 자동화가 목적이지만 동시에 담당자의 부담을 줄이는 것도 목적이다.
②를 빼면 이 도구는 그냥 리소스 덤프 도구가 된다.

두 가지를 assets.json에 더한다.
  (a) 자산유형별 manual_required — 요구항목 중 AWS로 안 채워지는 것
  (b) manual_todo — 담당자별 작업 지시 요약

affected_assets 숫자가 붙어야 담당자가 우선순위를 정할 수 있다.
"태그 하나 달면 62건이 해결된다"와 "1건짜리 수기 등재"는 노력 대비 효과가 완전히 다르다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from . import reasons as R

CONFIG_DIR = Path("config")


def load_manual_items(config_dir: Path | None = None) -> dict:
    path = (config_dir or CONFIG_DIR) / "manual_items.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["items"]


# --------------------------------------------------------------------------
# (a) 자산유형별 미수집 요구항목
# --------------------------------------------------------------------------

def _field_shortfall(assets: list[dict], field: str) -> tuple[int, int, list[str]]:
    """그 필드가 결측인 자산 수 / 전체 / 샘플 asset_id.

    NOT_APPLICABLE은 결측으로 세지 않는다. 개념이 없는 걸 '미확인'으로 세면
    리포트가 "S3 버킷 IP 미확인" 같은 행으로 채워진다.
    """
    # asset_id·region 같은 식별 필드는 {value, reason} 형태가 아니라 스칼라다.
    # 항상 채워져 있으므로 결측 계산에서 빠진다.
    relevant = [
        a for a in assets
        if isinstance(a.get(field), dict) and a[field].get("reason") != R.NOT_APPLICABLE
    ]
    missing = [a for a in relevant if R.counts_as_gap(a[field])]
    return len(missing), len(relevant), [a["asset_id"] for a in missing[:3]]


def _ref_for_field(manual_items: dict, field: str | None) -> str | None:
    """그 필드를 채우는 방법을 아는 manual_item을 찾는다.

    required_items마다 manual_ref를 손으로 달지 않아도 되게 한다.
    이게 없으면 "관리 부서명 → 담당: 미지정, 조치: 수기 확인 필요" 같은
    빈 안내가 나가는데, 그건 이 도구가 없애려던 바로 그 빈 칸이다.
    """
    if not field:
        return None
    for key, meta in manual_items.items():
        if field in (meta.get("fields") or []):
            return key
    return None


def build_manual_required(
    asset_types: dict, manual_items: dict
) -> dict[str, list[dict]]:
    """요구항목을 훑어 담당자가 채워야 할 것을 자동 계산한다.

    요구항목은 세 형태다.
      field    — 그 계약 필드가 채워지면 충족. 전부 결측이면 미충족
      presence — 그 resource_type 자산이 1건 이상 있으면 충족 (보안시스템)
      field: null — AWS로 못 채우는 항목. 무조건 수기
    """
    out: dict[str, list[dict]] = {}

    for type_name, block in asset_types.items():
        assets = block["assets"]
        rows: list[dict] = []

        for item in block.get("isms_required_items", []):
            ref = item.get("manual_ref") or _ref_for_field(manual_items, item.get("field"))
            manual = manual_items.get(ref, {}) if ref else {}

            if "presence" in item:
                wanted = set(item["presence"])
                found = [a for a in assets if a["resource_type"] in wanted]
                if found:
                    continue  # 그 통제가 존재한다
                rows.append(_row(item, manual, collected_count=0, total=0,
                                 note="AWS 수집 결과 0건" if wanted else "AWS API 대상 아님"))
                continue

            field = item.get("field")
            if field is None:
                rows.append(_row(item, manual, collected_count=0, total=len(assets)))
                continue

            missing_count, total, samples = _field_shortfall(assets, field)
            if total == 0 or missing_count == 0:
                continue
            if missing_count < total:
                # 일부만 비어 있다. 요구항목 미충족은 아니고 todo로 집계된다.
                continue
            rows.append(_row(item, manual, collected_count=0, total=total,
                             samples=samples, note=f"{total}건 전부 미입력"))

        out[type_name] = rows
    return out


def _row(item: dict, manual: dict, *, collected_count: int, total: int,
         samples: list[str] | None = None, note: str | None = None) -> dict:
    return {
        "item_name": item["name"],
        "collected_count": collected_count,
        "asset_count": total,
        "reason": manual.get("reason", "AWS API로 수집할 수 없는 항목"),
        "evidence": manual.get("evidence"),
        "owner": manual.get("owner", "미지정"),
        "action": manual.get("action", "수기 확인 필요"),
        "examples": manual.get("examples"),
        "auto_after_fix": manual.get("auto_after_fix", False),
        "manual_ref": item.get("manual_ref"),
        "sample_asset_ids": samples or [],
        "note": note or manual.get("note"),
    }


# --------------------------------------------------------------------------
# (b) 담당자별 작업 지시
# --------------------------------------------------------------------------

def build_manual_todo(asset_types: dict, manual_items: dict) -> dict:
    """담당자별로 무엇을 몇 건 해야 하는지.

    태그로 해결되는 것과 영원히 수기인 것을 반드시 갈라 놓는다.
    앞엣것은 한 번 투자하면 끝, 뒤엣것은 계속 드는 비용이다.
    """
    all_assets = [a for block in asset_types.values() for a in block["assets"]]
    total = len(all_assets)

    by_owner: dict[str, list[dict]] = {}
    permission_blocked: list[dict] = []
    tasks = 0

    for key, meta in manual_items.items():
        fields = meta.get("fields") or []
        if fields:
            entry = _tag_task(key, meta, fields, all_assets, total)
            if entry is None:
                continue
        else:
            entry = _manual_task(key, meta, asset_types)
            if entry is None:
                continue
        by_owner.setdefault(meta.get("owner", "미지정"), []).append(entry)
        tasks += 1

    # 권한 부족·조회 실패는 자산 부재가 아니다. 절대 섞지 않는다.
    for field_name, reason, count, samples, hint in _blocked_fields(all_assets):
        permission_blocked.append({
            "field": field_name,
            "reason": reason,
            "affected_assets": count,
            "sample_asset_ids": samples,
            # 왜 못 읽었는지까지 실어야 담당자가 권한 문제인지 도구 문제인지 안다
            "detail": hint,
            "note": "자산이 없다는 뜻이 아니다. 권한 부여 또는 재수집으로 해결한다",
        })

    auto_after_fix = sum(
        1 for rows in by_owner.values() for r in rows if r["auto_after_fix"]
    )
    return {
        "summary": {
            "total": tasks,
            "auto_after_fix": auto_after_fix,
            "permanent": tasks - auto_after_fix,
            "total_assets": total,
        },
        "by_owner": by_owner,
        "blocked": permission_blocked,
    }


def _applies(asset: dict, condition: dict | None) -> bool:
    """조건부 필수 규칙.

    HandlePI=Y일 때만 PIItems가 필수이고, InScope=N일 때만 ScopeReason이 필수다
    (docs/field-mapping.md §2.1). 조건을 안 보면 개인정보를 안 다루는 자산까지
    "개인정보 항목 미입력"으로 세어 숫자가 부풀고 우선순위가 뒤집힌다.

    조건 필드 자체가 미입력이면 필수 여부를 알 수 없으므로 세지 않는다.
    그건 조건 필드(HandlePI) 쪽 작업으로 이미 잡혀 있다.
    """
    if not condition:
        return True
    field = asset.get(condition["field"])
    if not isinstance(field, dict):
        return False
    return field.get("value") == condition["equals"]


def _tag_task(key: str, meta: dict, fields: list[str], assets: list[dict],
              total: int) -> dict | None:
    condition = meta.get("condition")
    affected: list[str] = []
    applicable = 0
    for asset in assets:
        if not _applies(asset, condition):
            continue
        applicable += 1
        for field in fields:
            value = asset.get(field, {})
            if isinstance(value, dict) and value.get("reason") == R.TAG_ABSENT:
                affected.append(asset["asset_id"])
                break
    if not affected:
        return None
    base = applicable if condition else total
    ratio = f"{round(len(affected) / base * 100)}%" if base else "0%"
    return {
        "key": key,
        "action": meta["action"],
        "item_name": meta["item_name"],
        "affected_assets": len(affected),
        "affected_ratio": ratio,
        "auto_after_fix": meta.get("auto_after_fix", False),
        "evidence": meta.get("evidence"),
        "sample_asset_ids": affected[:3],
    }


def _manual_task(key: str, meta: dict, asset_types: dict) -> dict | None:
    """수기 등재 항목.

    currently_registered는 **이 항목으로 등재된 수기 행의 수**다. 아직 수기 시트를
    읽어들이지 않으므로 항상 0이다.

    자산유형의 AWS 수집 건수를 여기 적으면 안 된다. 보안시스템에 GuardDuty·KMS가
    5건 있다고 "내부정보 유출통제 시스템 5건 등재"로 보이면, 결함사례 1을
    잡으라고 만든 항목이 오히려 결함을 가려버린다.
    """
    return {
        "key": key,
        "action": meta["action"],
        "item_name": meta["item_name"],
        "affected_assets": 0,
        "currently_registered": 0,
        "auto_after_fix": meta.get("auto_after_fix", False),
        "evidence": meta.get("evidence"),
        "examples": meta.get("examples"),
    }


def _blocked_fields(assets: list[dict]) -> list[tuple[str, str, int, list[str], str | None]]:
    """권한 부족·조회 실패로 못 읽은 필드. 자산 부재로 오인하면 대장 전체가 틀린다."""
    tally: dict[tuple[str, str], list[str]] = {}
    hints: dict[tuple[str, str], str | None] = {}

    def note(key: tuple[str, str], asset_id: str, field: dict) -> None:
        tally.setdefault(key, []).append(asset_id)
        hints.setdefault(key, field.get("hint"))

    for asset in assets:
        for name, field in asset.items():
            if not isinstance(field, dict):
                continue
            if name == "infra_facts":
                for fact_name, fact in field.items():
                    if fact.get("reason") in (R.PERMISSION_DENIED, R.COLLECT_ERROR):
                        note((f"infra_facts.{fact_name}", fact["reason"]), asset["asset_id"], fact)
                continue
            if field.get("reason") in (R.PERMISSION_DENIED, R.COLLECT_ERROR):
                note((name, field["reason"]), asset["asset_id"], field)

    return [(name, reason, len(ids), ids[:3], hints[(name, reason)])
            for (name, reason), ids in sorted(tally.items(), key=lambda kv: -len(kv[1]))]


# --------------------------------------------------------------------------
# 조립
# --------------------------------------------------------------------------

def annotate(payload: dict, config_dir: Path | None = None) -> dict:
    """assets.json에 manual_required와 manual_todo를 더한다."""
    manual_items = load_manual_items(config_dir)
    required = build_manual_required(payload["asset_types"], manual_items)
    for type_name, rows in required.items():
        payload["asset_types"][type_name]["manual_required"] = rows
    payload["manual_todo"] = build_manual_todo(payload["asset_types"], manual_items)
    return payload


def print_manual_summary(payload: dict) -> None:
    """터미널에 담당자 작업 요약.

    마지막 항목(권한 부족·조회 실패)을 반드시 분리해서 보여준다.
    권한 문제를 자산 문제로 오인하면 대장 전체가 틀린다.
    """
    todo = payload["manual_todo"]
    rows = [r for owner_rows in todo["by_owner"].values() for r in owner_rows]

    auto = sorted([r for r in rows if r["auto_after_fix"]],
                  key=lambda r: -r["affected_assets"])
    permanent = [r for r in rows if not r["auto_after_fix"]]

    if auto:
        print("  [태그만 달면 자동화됨]")
        for row in auto:
            owner = _owner_of(todo, row)
            print(f"    · {row['item_name']:28s} {row['affected_assets']:5d}건 "
                  f"({row['affected_ratio']:>4s})  → {owner}")
        print()

    if permanent:
        print("  [수기 등재 필요 — 영구]")
        for row in permanent:
            owner = _owner_of(todo, row)
            registered = row.get("currently_registered", 0)
            print(f"    · {row['item_name']:28s} 현재 {registered:3d}건 등재  → {owner}")
        print()

    if todo["blocked"]:
        print("  [권한 부족·조회 실패 — 자산 부재 아님]")
        for row in todo["blocked"]:
            print(f"    · {row['field']:28s} {row['affected_assets']:5d}건  "
                  f"← {row['reason']}")
            if row.get("detail"):
                print(f"      {row['detail']}")
        print()

    summary = todo["summary"]
    print(f"  작업 {summary['total']}건 "
          f"(태그로 해결 {summary['auto_after_fix']} / 영구 수기 {summary['permanent']})")
    print()


def _owner_of(todo: dict, row: dict) -> str:
    for owner, rows in todo["by_owner"].items():
        if row in rows:
            return owner
    return "미지정"
