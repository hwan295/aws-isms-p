"""진입점. 여기만 보면 흐름 전체가 보이도록.

    수집기 assets.json → 등급 제안 → 갭 판정 → 수기 입력 → 대장·리포트

    python main.py snapshots/normalized/run-.../assets.json
    python main.py <파일> --ask --by 송재우      # 빈 수기 칸을 물어봄
"""
import argparse
import json
import sys
from pathlib import Path

from advisor import classify, gap, grade, manual, resolve
from reporter import html, xlsx

ROOT = Path(__file__).resolve().parent
CONTRACT_VERSION = "1.0"


def main():
    parser = argparse.ArgumentParser(description="ISMS-P 1.2.1 자산 판정·출력기")
    parser.add_argument("snapshot", help="수집기가 만든 assets.json")
    parser.add_argument("-o", "--out", default=str(ROOT / "output"), help="출력 폴더")
    parser.add_argument("--ask", action="store_true",
                        help="AWS로 못 얻는 칸을 한 줄씩 물어본다 (답은 저장돼 다음 실행에 쓰임)")
    parser.add_argument("--by", default="unknown", help="수기 입력 작성자")
    args = parser.parse_args()

    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    # 계약 버전이 다르면 필드 의미가 달라졌을 수 있다. 조용히 틀린 결과를 내느니 멈춘다
    version = snapshot["meta"].get("contract_version")
    if version != CONTRACT_VERSION:
        sys.exit(f"계약 버전 불일치: {version} (이 도구는 {CONTRACT_VERSION})")

    sheet_map = classify.load_sheet_map()

    graded = grade.grade_snapshot(snapshot)
    gaps = gap.detect(graded)
    buckets = classify.assign(resolve.assets_of(graded), sheet_map)
    store, pending = manual.collect(gaps, sheet_map, buckets,
                                    interactive=args.ask, by=args.by)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "graded_assets.json").write_text(
        json.dumps(graded, ensure_ascii=False, indent=2), encoding="utf-8")
    xlsx.write(graded, gaps, out / "자산관리대장.xlsx", sheet_map=sheet_map,
               buckets=buckets, manual=store, common_labels=manual.common_labels(gaps))
    html.write(graded, gaps, out / "갭리포트.html")

    tag_gap = sum(r["count"] for r in gaps["type2_missing_tag"])
    unverified = sum(r["count"] for r in gaps["unverified"])
    uncovered = gaps["type1_manual"]["uncovered_types"]
    print(f"자산 {gaps['total_assets']}건 판정 완료 (룰팩 {grade.load_rules()['ruleset_version']})")
    print(f"  ② 태그 미입력 {tag_gap}건 · 관리책임자 미식별 {gaps['owner_missing_ratio']}%")
    print(f"  ③ 확정 대기 {len(gaps['type3_pending_confirm'])}건 · 미확인 {unverified}건")
    print(f"  ① 영구 수기 {len(gaps['type1_manual']['permanent'])}항목 · "
          f"수집기 없는 자산유형 {len(uncovered)}종")
    print(f"  ① 수기 미입력 {len(pending)}건" + ("" if args.ask else " (--ask 로 채울 수 있음)"))
    print(f"→ {out}/자산관리대장.xlsx, 갭리포트.html, graded_assets.json")


if __name__ == "__main__":
    main()
