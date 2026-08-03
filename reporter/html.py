"""갭 리포트 HTML. 서버 없이 파일 하나로 여는 발표용 화면.

리포트 첫머리에 도구의 한계를 먼저 쓴다. 커버하지 못한 범위를 밝히지 않으면
그 자체가 자산 식별 누락이 되기 때문이다.
"""
import html as _html

from advisor import resolve

CSS = """
body{font:14px/1.7 -apple-system,'Apple SD Gothic Neo',sans-serif;margin:0;padding:40px;
     background:#f6f7f9;color:#1c1f23}
main{max-width:1120px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:16px;margin:36px 0 12px;padding-bottom:8px;border-bottom:1px solid #dfe3e8}
.sub{color:#6b727c;margin:0 0 28px}
.notice{background:#fff8e6;border-left:3px solid #e0a800;padding:14px 18px;margin:0 0 28px;
        border-radius:0 4px 4px 0}
.notice p{margin:4px 0}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px}
.card{flex:1;min-width:150px;background:#fff;border:1px solid #e2e5e9;border-radius:6px;padding:16px 18px}
.card .n{font-size:26px;font-weight:600}
.card .l{color:#6b727c;font-size:12px;margin-top:2px}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e2e5e9;border-radius:6px}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid #eef0f3;vertical-align:top}
th{background:#f0f2f5;font-weight:600;font-size:12px;color:#4a5058}
tr:last-child td{border-bottom:none}
code{background:#f0f2f5;padding:1px 5px;border-radius:3px;font-size:12px}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.tag{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:600;
     white-space:nowrap}
.t1{background:#e8eaf6;color:#3949ab}
.t2{background:#fdecea;color:#c62828}
.t3{background:#e8f5e9;color:#2e7d32}
.tx{background:#eceff1;color:#546e7a}
.lead{color:#5a616b;margin:-4px 0 12px;font-size:13px}
.empty{color:#8a9099;padding:14px 12px;background:#fff;border:1px solid #e2e5e9;border-radius:6px}
.basis{color:#5a616b;font-size:12px}
"""


def _e(value):
    return _html.escape(str(value if value is not None else ""))


def _table(headers, rows, empty="해당 없음"):
    if not rows:
        return f'<div class="empty">{empty}</div>'
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def _field_rows(rows, tag_class, tag_text, action):
    return [[f'<span class="tag {tag_class}">{tag_text}</span>',
             _e(r["asset_type"]),
             f'{_e(r["item_name"])} <code>{_e(r["field"])}</code>',
             f'<span class="num">{r["count"]}</span>',
             _e(", ".join(r["samples"])),
             action] for r in rows]


def _grade_rows(snapshot, limit=40):
    rows = []
    for asset in resolve.assets_of(snapshot):
        proposed = asset.get("grade_proposed")
        if not proposed or not proposed["overall"]:
            continue
        basis = []
        for axis in ("confidentiality", "integrity", "availability"):
            for item in proposed[axis]["basis"]:
                basis.append(f"<code>{_e(item['rule_id'])}</code> {_e(item['statement'])}")
        rows.append([
            _e(resolve.value_of(asset, "asset_name") or asset["asset_id"].rsplit("/", 1)[-1]),
            _e(resolve.value_of(asset, "asset_type")),
            _e(proposed["confidentiality"]["level"] or "미정"),
            _e(proposed["integrity"]["level"] or "미정"),
            _e(proposed["availability"]["level"] or "미정"),
            f"<b>{_e(proposed['overall'])}</b>",
            '<span class="basis">' + "<br>".join(basis or ["근거 없음"]) + "</span>",
        ])
        if len(rows) >= limit:
            break
    return rows


def write(snapshot, gaps, path):
    meta = snapshot["meta"]
    graded = sum(1 for a in resolve.assets_of(snapshot)
                 if (a.get("grade_proposed") or {}).get("overall"))
    tag_gap = sum(r["count"] for r in gaps["type2_missing_tag"])
    unverified_count = sum(r["count"] for r in gaps["unverified"])

    cards = [
        (gaps["total_assets"], "식별 자산"),
        (tag_gap, "② 태그 미입력 (필드 기준)"),
        (f"{gaps['owner_missing_ratio']}%", "관리책임자 미식별"),
        (len(gaps["type3_pending_confirm"]), "③ 확정 대기"),
        (unverified_count, "권한 부족·조회 실패"),
    ]
    card_html = "".join(
        f'<div class="card"><div class="n">{_e(n)}</div><div class="l">{_e(l)}</div></div>'
        for n, l in cards
    )

    type2 = _field_rows(gaps["type2_missing_tag"], "t2", "②", "태그 부착 후 재수집")
    type2 += [[f'<span class="tag t2">② 작업</span>', _e(a.get("owner")),
               _e(a["item_name"]), f'<span class="num">{a.get("affected_assets", "")}</span>',
               "", _e(a.get("action", ""))]
              for a in gaps["type2_actions"]]

    type1 = [[f'<span class="tag t1">①</span>', _e(a.get("owner")), _e(a["item_name"]),
              f'<span class="num">{a.get("affected_assets", "")}</span>',
              _e(a.get("evidence", "")), _e(a.get("action", ""))]
             for a in gaps["type1_manual"]["permanent"]]
    type1 += [[f'<span class="tag t1">① 수집기 없음</span>', _e(t), "이 유형은 훑지 않았음",
               "", "", "0건이 아니라 미확인. 별도 식별 필요"]
              for t in gaps["type1_manual"]["uncovered_types"]]

    type3 = [[f'<span class="tag t3">③</span>', _e(r["asset_type"]), _e(r["asset_name"]),
              _e(r["overall"] or "판정불가"), "검토 후 확정등급 기입"]
             for r in gaps["type3_pending_confirm"][:30]]

    unknown = _field_rows(gaps["unverified"], "tx", "미확인",
                          "권한 부여 후 재수집 (자산 부재 아님)")
    unknown += _field_rows(gaps["out_of_scope"], "tx", "범위 밖",
                           "수집기가 해당 API를 부르지 않음")
    unknown += [[f'<span class="tag tx">차단</span>', "-", f'<code>{_e(b["field"])}</code>',
                 f'<span class="num">{b.get("affected_assets", "")}</span>', "",
                 f'{_e(b["reason"])} — 작업 목록과 섞지 말 것']
                for b in gaps["blocked"]]

    by_type = [[_e(t), f'<span class="num">{v["count"]}</span>',
                "예" if v["collector_exists"] else "아니오",
                "확인했더니 없음" if v["collector_exists"] or v["count"]
                else "확인하지 않음 — 0건으로 읽으면 안 됨"]
               for t, v in gaps["by_type"].items()]

    body = f"""<main>
<h1>정보자산 갭 리포트</h1>
<p class="sub">ISMS-P 1.2.1 정보자산 식별 · 스캔 {_e(meta['run_id'])} ·
계정 {_e(meta['account_id'])} · 계약 v{_e(meta.get('contract_version'))}</p>

<div class="notice">
<p>이 리포트가 말하지 않는 것</p>
<p>· 개인정보 보유 여부는 PII 태그가 유일한 근거다. 태그가 없는 자산에
개인정보가 있어도 도구는 알 수 없다.</p>
<p>· 보안등급은 제안이며 확정이 아니다. 확정은 관리책임자의 검토를 거친다.</p>
<p>· 권한 부족·조회 실패·수집 범위 밖은 갭이 아니라 미확인이다. 자산이 없다는
뜻으로 읽으면 안 된다.</p>
<p>· 정보자산관리지침 별지 제3호의 등급 조건 중 확인되는 것은 개인정보 보유 여부,
백업 부재, 대체 자산 부재뿐이다. 정보 민감도를 수집하지 않아 기밀성의 접근 범위
3단계는 쓰지 못하고 있다.</p>
<p>· 별지 제3호 원문에서 무결성 '상'과 '중'의 조건 문장이 동일하다. 중 조건을 그대로
룰로 옮기면 모든 자산이 상이면서 중이 되므로 상만 사용했다. 지침 개정이 필요한 지점.</p>
</div>

<div class="cards">{card_html}</div>

<h2>자산유형별 현황</h2>
<p class="lead">0건일 때는 수집기 유무를 함께 봐야 한다. 수집기가 없으면 없는 게 아니라 안 본 것이다.</p>
{_table(["자산유형", "건수", "수집기", "0건의 뜻"], by_type)}

<h2>① 수기 등재가 필요한 항목</h2>
<p class="lead">AWS로는 얻을 수 없다. 도구가 줄이지 못하고 목록으로 드러내기만 한다.</p>
{_table(["유형", "담당", "항목", "대상", "근거", "조치"], type1)}

<h2>② 태그만 달면 채워지는 항목</h2>
<p class="lead">도구가 줄일 수 있는 유일한 갭이다. 태그를 붙이면 다음 수집부터 자동으로 들어간다.</p>
{_table(["유형", "자산유형·담당", "항목", "건수", "표본", "조치"], type2, "태그 갭 없음")}

<h2>③ 등급 확정 대기</h2>
<p class="lead">도구가 {graded}건에 등급을 제안했고 아직 확정된 것은 없다.</p>
{_table(["유형", "자산유형", "자산", "제안 등급", "조치"], type3)}

<h2>미확인과 수집 범위 밖</h2>
<p class="lead">갭이 아니다. 권한이 없어 못 읽었거나 수집기가 아직 그 API를 부르지 않는 것이므로
자산 부재나 통제 미비로 세면 안 된다.</p>
{_table(["구분", "자산유형", "항목", "건수", "표본", "조치"], unknown, "미확인 항목 없음")}

<h2>등급 제안 근거</h2>
{_table(["자산", "유형", "기밀성", "무결성", "가용성", "종합", "근거"], _grade_rows(snapshot))}
</main>"""

    doc = (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
           f"<title>정보자산 갭 리포트 · {_e(meta['run_id'])}</title>"
           f"<style>{CSS}</style></head><body>{body}</body></html>")

    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return path
