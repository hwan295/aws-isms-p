"""전체 흐름 한 번에: 환경 생성 → collect → extract → 결과 출력.

    python demo.py                # 2개 리전 (빠름)
    python demo.py --all-regions  # 전 리전 순회
    python demo.py --raw          # moto 산출물을 거르지 않고 그대로

시연에서 생길 수 있는 사고를 막는 장치가 몇 개 들어 있다. 각각 왜 있는지는
해당 함수 주석에 적었다.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

#: moto가 쓰는 목 계정. 수집 결과가 이 계정이 아니면 실계정에 붙은 것이다.
MOTO_ACCOUNT_ID = "123456789012"

#: moto가 계정에 심어두는 산출물. 실계정에는 없다(docs/aws-facts.md §6·§9).
MOTO_ARTIFACT_KEY_DESC = "Default master key that protects my EBS"


def guard_real_credentials() -> None:
    """실계정 자격증명이 새어 들어가지 않게 한다.

    이 도구의 금지사항 1번이 "AWS 실계정에 접속하지 않는다"이다.
    moto가 가로채므로 실제로는 안 나가지만, 발표 중 실수로 mock 없이 도는
    경로가 생기면 고객 계정을 긁게 된다. 가짜 값을 강제로 덮어써 둔다.
    """
    for key in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
        if os.environ.pop(key, None):
            print(f"  [안전장치] {key} 환경변수를 데모 실행에서 제거했다")
    os.environ.update(
        AWS_ACCESS_KEY_ID="testing",
        AWS_SECRET_ACCESS_KEY="testing",
        AWS_SECURITY_TOKEN="testing",
        AWS_SESSION_TOKEN="testing",
        AWS_DEFAULT_REGION="ap-northeast-2",
    )


def resolve_run_id(root: Path) -> str:
    """겹치지 않는 run_id를 고른다.

    run_id는 분 단위(run-YYYYMMDD-HHMM)라 1분 안에 두 번 돌리면 이전 실행을 덮어쓴다.
    발표 중 재실행은 흔하고, 그때 직전 결과가 날아가면 비교 시연을 못 한다.
    """
    from collector.session import new_run_id

    base = new_run_id()
    if not (root / base).exists():
        return base
    for suffix in range(2, 100):
        candidate = f"{base}-{suffix}"
        if not (root / candidate).exists():
            print(f"  [안전장치] {base}가 이미 있다 → {candidate}로 실행한다 "
                  f"(이전 실행 보존)")
            return candidate
    raise RuntimeError("run_id를 정하지 못했다")


def print_region_spread(payload: dict) -> None:
    """리전별 자산 분포.

    "미사용 리전 방치가 자산 누락 1순위"는 이 도구의 핵심 주장인데,
    리전별 숫자를 안 보여주면 그 주장이 화면에 드러나지 않는다(결함사례 4).
    """
    counts: dict[str, int] = {}
    for block in payload["asset_types"].values():
        for asset in block["assets"]:
            counts[asset["region"]] = counts.get(asset["region"], 0) + 1
    if len(counts) < 2:
        return
    print("  [리전별 분포 — 미사용 리전 방치가 자산 누락 1순위]")
    for region, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"    {region:20s} {count:5d}건")
    print()


# --------------------------------------------------------------------------
# moto 산출물 걸러내기 — 숨기는 게 아니라 드러내면서 뺀다
# --------------------------------------------------------------------------

def _is_moto_artifact(asset: dict, account_id: str) -> tuple[str, str] | None:
    """이 자산이 moto가 심어둔 것인가. 맞으면 (분류, 세부) 를 준다."""
    if asset["resource_type"] in ("ec2_snapshot", "ec2_image"):
        owner = asset.get("owner_account", {}).get("value")
        if owner and owner != account_id:
            # 실계정에서는 OwnerIds=['self'] 때문에 애초에 안 온다.
            # moto가 그 필터를 무시해서 Amazon·Canonical 소유 스냅샷이 섞인다.
            return ("타 계정 소유 스냅샷·이미지 — moto가 OwnerIds=['self'] 필터를 무시함", owner)
    if asset["resource_type"] == "kms_key":
        name = asset.get("asset_name", {}).get("value") or ""
        if MOTO_ARTIFACT_KEY_DESC in name:
            # 실계정에서 aws/ebs 기본 키는 KeyManager=AWS라 where 필터에 걸린다.
            return ("moto가 만든 EBS 기본 마스터키 — 실계정에서는 KeyManager=AWS", "kms")
    return None


def strip_moto_artifacts(payload: dict, config_dir: Path | None = None) -> tuple[dict, dict]:
    """데모 화면용 사본을 만든다. 원본 assets.json은 건드리지 않는다.

    화면에서만 지우면 manual_todo의 "관리주체 미식별 100%" 같은 숫자가
    여전히 남의 계정 스냅샷에 지배된다. 그래서 거른 뒤 지시 요약을 다시 계산한다.

    **뺀 것을 반드시 화면에 알린다.** 조용히 빼면 assets.json을 열어본 사람이
    숫자가 안 맞는 걸 발견하고, 그 순간 도구 전체의 신뢰가 무너진다.
    """
    from collector.manual import annotate

    view = copy.deepcopy(payload)
    account_id = view["meta"]["account_id"]
    removed: dict[str, dict] = {}

    total = 0
    for block in view["asset_types"].values():
        kept = []
        for asset in block["assets"]:
            found = _is_moto_artifact(asset, account_id)
            if found:
                kind, detail = found
                entry = removed.setdefault(kind, {"count": 0, "details": set()})
                entry["count"] += 1
                entry["details"].add(detail)
                continue
            kept.append(asset)
        block["assets"] = kept
        block["asset_count"] = len(kept)
        total += len(kept)

    view["meta"]["total_assets"] = total
    view["meta"]["demo_filter"] = {
        "removed": {k: {"count": v["count"], "details": sorted(v["details"])}
                    for k, v in removed.items()},
        "note": "moto가 심어둔 산출물. 실제 AWS 계정에서는 애초에 수집되지 않는다",
    }
    annotate(view, config_dir)
    return view, removed


def print_filter_report(removed: dict, original_total: int, kept_total: int) -> None:
    if not removed:
        return
    print("  [데모 표시 필터 — moto 산출물 제외]")
    for kind, entry in sorted(removed.items(), key=lambda kv: -kv[1]["count"]):
        print(f"    -{entry['count']:5d}건  {kind}")
        if len(entry["details"]) > 1:
            print(f"             소유 계정 {len(entry['details'])}개 "
                  f"({', '.join(sorted(entry['details'])[:3])} 등)")
    print(f"    합계 {original_total}건 → {kept_total}건")
    print("    원본 assets.json에는 그대로 남아 있다. 실계정에서는 이 항목들이 나오지 않는다.")
    print()


# --------------------------------------------------------------------------
# 실행
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ISMS-P 자산 수집기 데모 (moto 전용)")
    parser.add_argument("--all-regions", action="store_true",
                        help="전 리전 순회 (기본은 2개 리전)")
    parser.add_argument("--raw", action="store_true",
                        help="moto 산출물을 거르지 않고 그대로 보여준다")
    parser.add_argument("--keep", action="store_true",
                        help="기존 snapshots/·output/을 지우지 않는다")
    args = parser.parse_args(argv)

    print()
    print("=" * 72)
    print("  ISMS-P 1.2.1 정보자산 식별 — AWS 자산 수집기 데모")
    print("=" * 72)
    guard_real_credentials()

    from moto import mock_aws

    import demo_env
    from collector.collect import print_summary, run_collect
    from collector.extract import NORMALIZED_ROOT, print_extract_summary, run_extract
    from collector.dump import RAW_ROOT
    from collector.registry import all_required_actions
    from reporter import manual_sheet

    if not args.keep:
        for path in (Path("snapshots"), Path("output")):
            shutil.rmtree(path, ignore_errors=True)

    print()
    print("  [1/4] moto 안에 가짜 환경을 만든다 — 실제 AWS 계정은 쓰지 않는다")
    for line in demo_env.describe():
        print(f"    · {line}")

    run_id = resolve_run_id(RAW_ROOT)

    @mock_aws
    def _run():
        demo_env.build()
        demo_env.build_secondary()

        regions = None if args.all_regions else (demo_env.REGION, demo_env.ALT_REGION)
        print()
        print("  [2/4] collect — AWS 응답을 손대지 않고 통째로 덤프")
        if not args.all_regions:
            print("        (데모는 2개 리전. 기본값은 전 리전 순회 — --all-regions)")
        collected = run_collect(regions=regions, run_id=run_id)
        print_summary(collected)
        return collected

    collected = _run()

    # 목 계정이 아니면 실계정에 붙은 것이다. 즉시 멈춘다.
    if collected["account_id"] != MOTO_ACCOUNT_ID:
        print(f"  [중단] 수집된 계정이 {collected['account_id']}다. moto 목 계정이 아니다.")
        print("        실제 AWS 계정에 접속했을 수 있다. 자격증명 설정을 확인하라.")
        return 2

    print("  [3/4] extract — AWS 접속 없이 원본만 읽어 자산유형별 JSON 생성")
    payload = run_extract(run_id=collected["run_id"])

    if args.raw:
        view = payload
    else:
        original = payload["meta"]["total_assets"]
        view, removed = strip_moto_artifacts(payload)
        print_filter_report(removed, original, view["meta"]["total_assets"])
        demo_path = NORMALIZED_ROOT / collected["run_id"] / "assets.demo-view.json"
        demo_path.write_text(
            json.dumps(view, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        view["_path"] = str(demo_path)

    print_extract_summary(view)
    print_region_spread(view)

    print("  [4/4] 산출물")
    sheet = manual_sheet.build(
        payload=view, out_path=Path("output") / f"수기입력_템플릿_{collected['run_id']}.xlsx")
    policy_path = Path("output") / "iam_policy.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    actions = all_required_actions()   # 쓰기 액션이 하나라도 있으면 여기서 실패한다
    policy_path.write_text(json.dumps({
        "Version": "2012-10-17",
        "Statement": [{"Sid": "ISMSPAssetInventoryReadOnly", "Effect": "Allow",
                       "Action": actions, "Resource": "*"}],
    }, indent=2), encoding="utf-8")

    print(f"    자산 JSON (B 인계물)   {payload['_path']}")
    if not args.raw:
        print(f"    데모 표시용 사본       {view['_path']}")
    print(f"    수기 입력 템플릿       {sheet}")
    print(f"    최소권한 IAM 정책      {policy_path}  ({len(actions)}개 액션, 전부 읽기)")
    print()
    print(f"  완료 {datetime.now(timezone.utc).astimezone():%Y-%m-%d %H:%M:%S}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
