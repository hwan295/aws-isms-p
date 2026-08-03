"""수기 입력 단계.

AWS로는 얻을 수 없는 칸을 사람에게 묻고, 답을 파일에 쌓아 다음 실행에서 다시 쓴다.
수집기가 "무엇을 사람이 채워야 하는가"까지 알려주므로(manual_todo) 목록은
그대로 받아 쓰고, 이쪽은 답을 받아 보관하는 일만 한다.

    수집기 manual_todo 중 auto_after_fix=false   대장 공통 항목 (영원히 수기)
    sheet_map 의 from: manual 컬럼                자산별 칸

값을 자산 레코드에 넣지 않는다. 계약은 수집기와 판정기 사이의 약속이고 수기 값은
판정기 안에서만 도는 것이라 계약에 넣을 이유가 없다. 확정 등급을 별도 파일에
두는 것과 같은 이유다.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "state/manual_entries.json"
COMMON = "common"


def load(path=STORE):
    if not Path(path).exists():
        return {"schema_version": "1.0", "entries": {COMMON: {}}}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(store, path=STORE):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(store, ensure_ascii=False, indent=2, sort_keys=True),
                          encoding="utf-8")


def value_of(store, scope, label):
    entry = store["entries"].get(scope, {}).get(label)
    return entry["value"] if entry else None


def manual_columns(sheet_map):
    """양식에서 사람이 채워야 하는 칸. (시트명, 컬럼명). 중복 제거."""
    seen, out = set(), []
    for sheet in sheet_map["sheets"]:
        for column in sheet["columns"]:
            if column["from"] == "manual":
                key = (sheet["name"], column["label"])
                if key not in seen:
                    seen.add(key)
                    out.append(key)
    return out


def common_labels(gaps):
    return [a["item_name"] for a in gaps["type1_manual"]["permanent"]]


def pending(gaps, sheet_map, store, buckets):
    """아직 안 채운 항목. (scope, label, 무엇에 대한 것인지)"""
    todo = [(COMMON, label, "대장 공통") for label in common_labels(gaps)
            if value_of(store, COMMON, label) is None]

    for sheet_name, label in manual_columns(sheet_map):
        for asset in buckets.get(sheet_name, []):
            scope = asset["asset_id"]
            if value_of(store, scope, label) is None:
                name = asset.get("asset_name")
                about = (name.get("value") if isinstance(name, dict) else name) \
                    or scope.rsplit("/", 1)[-1]
                todo.append((scope, label, about))
    return todo


def ask(todo, store, by):
    """빈 항목만 한 줄씩 묻는다. 그냥 엔터를 치면 다음에 다시 묻는다."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"\n수기 입력 {len(todo)}건 (엔터로 건너뜀)")
    for scope, label, about in todo:
        answer = input(f"  [{about}] {label} > ").strip()
        if not answer:
            continue
        store["entries"].setdefault(scope, {})[label] = {
            "value": answer, "by": by, "at": now,
        }
    return store


def collect(gaps, sheet_map, buckets, interactive=False, by="unknown"):
    store = load()
    todo = pending(gaps, sheet_map, store, buckets)
    if interactive and todo:
        store = ask(todo, store, by)
        save(store)
        todo = pending(gaps, sheet_map, store, buckets)
    return store, todo
