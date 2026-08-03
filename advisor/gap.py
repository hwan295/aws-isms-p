"""갭 판정 — 계약 v1.0.

빠진 값을 한 덩어리로 세면 리포트가 쓸모없어진다. 원인이 다르면 조치도 다르기
때문에 세 유형으로 나눈다.

  ① 수기 등재 필요   AWS 밖 자산이거나 사람만 정할 수 있는 항목. 도구가 줄일 수 없다
  ② 태그 미입력      태그만 달면 다음 실행부터 자동으로 채워진다
  ③ 확정 대기        도구가 등급을 제안했고 사람이 확정하지 않은 상태

여기에 갭이 아닌 것을 따로 뺀다. 계약 §5가 금지하는 해석을 코드로 막는 부분이다.

  미확인      권한 부족·조회 실패. 자산 부재로 세면 안 된다
  수집 범위 밖 개념은 있는데 수집기가 아직 그 API를 안 부른다

무엇이 필수 항목인지는 우리가 정하지 않는다. 수집기가 자산유형마다
isms_required_items 로 실어 보내는 것을 그대로 쓴다.

자산이 수천 건까지 가므로 전부 나열하지 않고 (자산유형, 필드) 단위로 묶어
건수와 표본만 남긴다. 표본은 담당자가 콘솔에서 바로 찾아볼 수 있게 하는 용도다.
"""
from . import resolve

SAMPLE = 3


def _bucket_key(asset_type, item_name, field):
    return (asset_type, item_name, field)


def _tally(store, key, asset):
    row = store.setdefault(key, {"count": 0, "samples": []})
    row["count"] += 1
    if len(row["samples"]) < SAMPLE:
        row["samples"].append(resolve.value_of(asset, "asset_name")
                              or asset["asset_id"].rsplit("/", 1)[-1])


def _rows(store):
    return [{"asset_type": t, "item_name": n, "field": f, **v}
            for (t, n, f), v in sorted(store.items(), key=lambda kv: -kv[1]["count"])]


def detect(snapshot):
    missing, not_set, api_null, unverified, out_of_scope = {}, {}, {}, {}, {}
    pending, by_type = [], {}
    total = 0
    owner_missing = 0

    for type_name, block in snapshot["asset_types"].items():
        by_type[type_name] = {
            "count": block["asset_count"],
            # 0건일 때 이 값이 갈린다. true 면 "확인했더니 없다"(결함 소지),
            # false 면 "확인하지 않았다". 계약 §5.4
            "collector_exists": block.get("collector_exists"),
        }
        required = block.get("isms_required_items", [])

        for asset in block["assets"]:
            total += 1
            if resolve.status(asset, "owner_responsible") != resolve.PRESENT:
                owner_missing += 1

            for item in required:
                field = item.get("field")
                if not field:
                    continue  # 보안등급처럼 수집 대상이 아닌 항목은 manual_required 가 다룬다
                key = _bucket_key(type_name, item["name"], field)
                state = resolve.status(asset, field)
                if state == resolve.MISSING:
                    _tally(missing, key, asset)
                elif state == resolve.NOT_SET:
                    _tally(not_set, key, asset)
                elif state == resolve.API_NULL:
                    _tally(api_null, key, asset)
                elif state == resolve.UNVERIFIED:
                    _tally(unverified, key, asset)
                elif state == resolve.OUT_OF_SCOPE:
                    _tally(out_of_scope, key, asset)

            if asset.get("grade_proposed") and asset.get("grade_confirmed") is None:
                pending.append({
                    "asset_type": type_name,
                    "asset_name": resolve.value_of(asset, "asset_name") or asset["asset_id"],
                    "overall": asset["grade_proposed"]["overall"],
                })

    todo = snapshot.get("manual_todo") or {"summary": {}, "by_owner": {}, "blocked": []}
    actions = [{**a, "owner": owner}
               for owner, items in todo["by_owner"].items() for a in items]

    return {
        "total_assets": total,
        "by_type": by_type,
        "type1_manual": {
            # 태그로도 해결되지 않는 항목. 도구가 줄일 수 없고 드러내기만 한다
            "permanent": [a for a in actions if not a.get("auto_after_fix")],
            # 수집기가 아예 없는 자산유형. 0건을 "없다"로 읽으면 안 된다
            "uncovered_types": [t for t, v in by_type.items()
                                if not v["collector_exists"]],
        },
        "type2_missing_tag": _rows(missing),
        "type2_actions": [a for a in actions if a.get("auto_after_fix")],
        "type3_pending_confirm": pending,
        "not_configured": _rows(not_set),
        "api_null": _rows(api_null),
        "unverified": _rows(unverified),
        "out_of_scope": _rows(out_of_scope),
        "blocked": todo.get("blocked", []),
        "collection_issues": snapshot["meta"].get("collection_issues", []),
        "owner_missing_ratio": round(owner_missing / total * 100, 1) if total else 0.0,
        "manual_summary": todo.get("summary", {}),
    }
