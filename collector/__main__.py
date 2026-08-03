"""python -m collector collect"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from reporter import manual_sheet

from .collect import print_summary, run_collect
from .extract import print_extract_summary, run_extract
from .registry import all_required_actions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m collector",
        description="ISMS-P 1.2.1 대응 AWS 자산 수집기 (읽기 전용)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="디버그 로그")
    sub = parser.add_subparsers(dest="command", required=True)

    collect = sub.add_parser("collect", help="AWS 응답을 통째로 덤프한다")
    collect.add_argument(
        "--regions", nargs="+", default=None,
        help="순회할 리전 (기본: 전 리전. 미사용 리전 방치가 자산 누락 1순위다)",
    )
    collect.add_argument("--run-id", default=None, help="run_id 직접 지정")

    extract = sub.add_parser(
        "extract", help="원본 덤프에서 ISMS-P 자산유형별 JSON을 만든다 (AWS 접속 없음)"
    )
    extract.add_argument("--run", default=None, help="run_id (기본: 가장 최근 실행)")

    sheet = sub.add_parser(
        "manual-sheet", help="담당자가 채울 수기 입력 템플릿 xlsx를 만든다"
    )
    sheet.add_argument("--run", default=None, help="run_id (기본: 가장 최근 실행)")

    sub.add_parser("iam-policy", help="수집에 필요한 최소권한 정책 JSON")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "collect":
        result = run_collect(
            regions=tuple(args.regions) if args.regions else None,
            run_id=args.run_id,
        )
        print_summary(result)
        return 0

    if args.command == "extract":
        result = run_extract(run_id=args.run)
        print_extract_summary(result)
        return 0

    if args.command == "manual-sheet":
        from pathlib import Path

        from .extract import NORMALIZED_ROOT, latest_run_id

        run_id = args.run or latest_run_id()
        assets_path = NORMALIZED_ROOT / run_id / "assets.json"
        payload = json.loads(assets_path.read_text(encoding="utf-8")) if assets_path.exists() else None
        if payload is None:
            print(f"경고: {assets_path}가 없다. 영향 자산 수 없이 템플릿만 만든다.")
        out = manual_sheet.build(payload=payload, out_path=Path("output") / f"수기입력_템플릿_{run_id}.xlsx")
        print(f"  수기 입력 템플릿  →  {out}")
        return 0

    if args.command == "iam-policy":
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "ISMSPAssetInventoryReadOnly",
                    "Effect": "Allow",
                    "Action": all_required_actions(),
                    "Resource": "*",
                }
            ],
        }
        print(json.dumps(policy, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
