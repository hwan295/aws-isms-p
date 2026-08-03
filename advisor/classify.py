"""자산을 실물 양식의 어느 시트로 보낼지 정한다.

수집기가 이미 asset_type(11종)을 붙여 주므로 규제 분류는 다시 하지 않는다.
여기서 하는 건 그 유형을 양식의 시트에 배정하는 일뿐이다.

서버만 한 단계가 더 있다. 양식이 OS (Linux) / OS (Windows) 로 갈려 있는데
계약 v1.0 의 os 는 현재 항상 OUT_OF_SCOPE(SSM 미도입)라 가를 수가 없다.
아무 시트에나 넣지 않고 '서버 (OS 미확인)' 로 모아 갭으로 드러낸다.
"""
import yaml
from pathlib import Path

from . import resolve

ROOT = Path(__file__).resolve().parent.parent
UNKNOWN_SHEET = "분류 보류"


def load_sheet_map(path=ROOT / "config/sheet_map.yaml"):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def os_family(asset):
    name = (resolve.value_of(asset, "os") or "").lower()
    if not name:
        return "unknown"
    return "windows" if "windows" in name else "linux"


def _matches(asset, when):
    for key, expected in when.items():
        actual = os_family(asset) if key == "os_family" else resolve.value_of(asset, key)
        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def assign(assets, sheet_map):
    """시트명 → 자산 목록. 어느 시트에도 못 넣은 자산은 따로 모은다.

    못 넣은 자산을 조용히 버리면 대장 합계가 수집 건수와 어긋나는데,
    그건 자산 식별 누락 그 자체다. 그래서 '분류 보류'로 남긴다.
    """
    buckets = {sheet["name"]: [] for sheet in sheet_map["sheets"]}
    buckets[UNKNOWN_SHEET] = []

    for asset in assets:
        for sheet in sheet_map["sheets"]:
            if _matches(asset, sheet["when"]):
                buckets[sheet["name"]].append(asset)
                break
        else:
            buckets[UNKNOWN_SHEET].append(asset)

    return buckets


def unclassified_reason(asset):
    return f"자산유형 '{resolve.value_of(asset, 'asset_type')}' 에 대응하는 양식 시트 없음"
