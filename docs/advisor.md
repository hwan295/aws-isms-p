# 판정·출력 (담당 B)

수집기의 `assets.json` 을 받아 보안등급을 제안하고, 실물 양식의 자산관리대장과
갭 리포트를 만든다. AWS에 접속하지 않는다. 로컬 JSON만 읽는다.

```bash
python demo.py                                              # 수집기 (A) — assets.json 생성
python main.py snapshots/normalized/<run_id>/assets.json     # 판정·출력 (B)
python main.py <assets.json> --ask --by 홍길동                # 수기 칸을 한 줄씩 물어봄
```

```
자산 2380건 판정 완료 (룰팩 1.0.0)
  ② 태그 미입력 4853건 · 관리책임자 미식별 99.8%
  ③ 확정 대기 2380건 · 미확인 2337건
  ① 영구 수기 17항목 · 수집기 없는 자산유형 5종
→ output/자산관리대장.xlsx, 갭리포트.html, graded_assets.json
```

---

## 1. 흐름

```
assets.json (계약 v1.0)
   │
   ├─ advisor/grade.py     config/grade_rules.yaml 실행 → grade_proposed 부착
   ├─ advisor/gap.py       사유 코드별로 묶어 갭 ①②③ 집계
   ├─ advisor/classify.py  config/sheet_map.yaml 로 양식 시트 배정
   ├─ advisor/manual.py    수기 칸을 묻고 state/ 에 저장 (다음 실행에 재사용)
   │
   ├─ reporter/xlsx.py     표지·대장 8시트·요약표·갭·수기입력
   └─ reporter/html.py     갭 리포트 1장 (서버 없이 열림)
```

| 파일 | 하는 일 |
|---|---|
| `advisor/resolve.py` | 사유 코드 판독. 다른 모듈은 전부 여기에 물어본다 |
| `advisor/grade.py` | 룰 실행, 검토 사유 생성 |
| `advisor/classify.py` | 자산유형 → 양식 시트 배정 |
| `advisor/gap.py` | 갭 집계 |
| `advisor/manual.py` | 수기 입력 보관 |
| `config/grade_rules.yaml` | 등급 룰. 조건 → 축·등급·근거 문구·지침 조항 |
| `config/sheet_map.yaml` | 계약 필드 → 양식 컬럼 |

룰과 매핑을 yaml에 둔 이유는 지침이나 양식이 개정될 때 코드를 안 고치기 위해서다.
`ruleset_version` 을 레코드에 남기므로 "같은 자산인데 지난달과 등급이 다르다"가 추적된다.

---

## 2. 사유 코드를 어떻게 쓰는가

계약 §4의 8종을 조치 단위로 옮긴다. 이 표가 `advisor/resolve.py` 한 곳에만 있고
등급 사유·갭 집계·대장 표기가 전부 여기를 거친다. 판정이 흩어지면 세 곳의 숫자가
어긋나는데 그게 제일 잡기 어려운 버그다.

| 계약 reason | 대장 표기 | 갭 리포트 | 조치 |
|---|---|---|---|
| `null` | 값 | — | 없음 |
| `TAG_ABSENT` | `미식별` | ② | 태그를 단다 |
| `NOT_CONFIGURED` | `미설정` | 별도 | 설정이 없다는 사실. 등급 근거로 쓴다 |
| `API_NULL` | `API 미제공` | 별도 | AWS가 값을 안 준다 |
| `NOT_APPLICABLE` | `-` | 출력 안 함 | 없음 |
| `PERMISSION_DENIED` | `미확인` | 별도 | 권한 부여 후 재수집 |
| `COLLECT_ERROR` | `미확인` | 별도 | 재수집 |
| `OUT_OF_SCOPE` | `범위 밖` | 별도 | 수집기가 그 API를 부르지 않음 |

계약 §5가 금지한 해석을 코드로 막은 지점이 두 군데다.

- 뒤의 셋을 갭이나 통제 미비로 세지 않는다. `PERMISSION_DENIED` 를 "미암호화"로
  기록하면 기밀성 등급이 통째로 틀린다.
- `asset_count == 0` 은 `collector_exists` 와 함께 본다. `false` 면 "없다"가 아니라
  "확인하지 않았다"이므로 갭 리포트와 대장 표지에 그렇게 적는다.

무엇이 필수 항목인지는 우리가 정하지 않는다. 수집기가 자산유형마다 실어 보내는
`isms_required_items` 를 그대로 쓴다.

---

## 3. 등급 룰

원본은 정보자산관리지침 [별지 제3호] 정보자산 중요도 평가 기준이다. `statement` 는
별지 원문을 그대로 옮기고 어떤 값으로 확인했는지만 괄호로 덧붙인다. 심사에서
"왜 상인가"에 조항으로 답이 되어야 하므로 문구를 임의로 바꾸지 않는다.

```yaml
- id: I-BACKUP-01
  axis: integrity
  level: 상
  basis_type: control_state
  when: { infra_facts.backup_exists: false }
  statement: 해당 자산정보에 대한 실시간 백업이 이루어지고 있지 않아 원래의 정보를 복구하기 힘든 경우
  source: 정보자산관리지침 별지 제3호 무결성 상
  evidence_field: infra_facts.backup_exists
```

지키는 원칙 둘.

- 등급을 확정하려면 자산 속성 근거(`asset_attribute`)가 최소 1건 있어야 한다.
  통제 상태만 보고 중요도를 정하지 않는다.
- 통제 상태(`control_state`)는 별지가 '상' 조건에 명시한 경우만, 등급을 올리는
  쪽으로만 쓴다. 백업을 켜면 등급이 내려가면 "등급을 낮추려고 백업을 끈다"가 성립한다.

`grade_confirmed` 는 도구가 어떤 경우에도 쓰지 않는다. 항상 `null` 로 두고 사람이
검토한 뒤 채운다.

### 퍼블릭 노출을 등급에 반영하지 않는 이유

별지는 "조직 외부인이 접근 및 열람이 가능한 정보를 담고 있는 자산"을 기밀성 **하**로
본다. 정적 웹 자산 버킷이 퍼블릭인 건 설계이고 회원 DB가 퍼블릭이면 사고인데,
설정만 봐서는 둘을 구분할 수 없다. 등급 대신 `exposure_intent_unknown` 사유로 남긴다.

### 별지 제3호 원문의 결함

무결성 '상'과 '중'의 조건 문장이 동일하다. 중 조건을 그대로 옮기면 모든 자산이
상이면서 중이 되므로 상만 썼다. 지침 개정 권고 항목으로 보고서에 넣을 예정.

---

## 4. 대장 출력

서식을 우리가 고를 수 없다. 정보자산관리지침 제6조②가
`03. 정보자산관리지침 별첨 클라우드 보안인증(SaaS) 정보자산목록.xlsx` 를 지정한다.
그런데 이 서식은 물리 서버를 전제로 만들어져 있어서 그대로 못 채우는 칸이 있다.

| 양식 칸 | 처리 |
|---|---|
| VM / Hardware | 클라우드 인스턴스는 전부 `VM` |
| DBMS명 (종류) | `engine` + `version` 조립 |
| 설치 서버 호스트명 | 관리형이라 없음 → `관리형 서비스 (설치 서버 없음)` |
| IP (DB 시트) | IP가 없음 → `endpoint:port` |
| 위치 (상세위치) | 물리 위치 대신 `AWS {region} / {az}` |
| 설치서버 (서버 시트) | AWS로 안 보임 → `수기` 로 찍고 수기 입력 시트로 |

양식 원본에 관리책임자 칸도 보안등급 칸도 없다. 그대로 채우면 1.2.1 ②(중요도
결정·보안등급 부여)와 CSAP 3.1.2(책임자 지정)를 증적하지 못한다. 그래서 뒤에
`인증기준 추가 요구` 묶음을 붙이고 원본 칸과 색을 갈랐다.

---

## 5. 수기 입력

수집기의 `manual_todo` 중 `auto_after_fix: false` 인 항목과, 양식에서 API로 못 얻는
칸을 사람에게 묻고 `state/manual_entries.json` 에 쌓는다. 다음 실행에는 저장된 값이
자동으로 대장에 들어가고 갭에서 빠진다.

값을 자산 레코드에 넣지 않는다. 계약은 수집기와 판정기 사이의 약속이고 수기 값은
판정기 안에서만 도는 것이라 계약에 넣을 이유가 없다.

---

## 6. 담당 A에게 — 필드 요청 2건

계약 §8 양식으로 적었다.

**① 정보 민감도**

```
자산유형: 전체
필요 필드: data_classification  (public | internal | confidential)
원본 경로: 태그 DataClass
용도: 별지 제3호 기밀성 등급. 접근 범위 3단계(담당자만 / 조직 내부 / 외부인)가
      이 값과 정확히 대응한다. 지금은 has_personal_info 로 상·하만 낼 수 있고
      중을 낼 근거가 없다
```

`has_personal_info` 와 별도 축이어야 한다. 하나로 합치면 "내부용이면서 개인정보를
포함하는 자산"을 표현할 수 없고, 그런 자산이 개인정보 보유 목록에서 조용히 빠진다.

**② OS 계열**

```
자산유형: 서버
필요 필드: platform  (Linux | Windows)
원본 경로: ec2/describe_instances → Reservations[].Instances[].PlatformDetails
용도: 양식이 OS (Linux) / OS (Windows) 로 시트가 갈린다. 현재 os 가 항상
      OUT_OF_SCOPE 라 배정을 못 해서 '서버 (OS 미확인)' 시트에 모아두고 있다
```

`describe_instances` 응답에 이미 들어 있어 추가 호출이 없다. SSM 도입 없이도
시트 배정은 된다.

---

## 7. 아직 안 한 것

- `advisor/diff.py` — 스냅샷 비교. 세부점검항목 ③에 대응하고 인증신청서
  자산 변경 현황 표를 채운다
- 요약표의 구분 매핑. 신청서 구분에 저장소 항목이 없어 정보·가상자원을
  어플리케이션으로 넣어뒀다. `config/sheet_map.yaml` 의 `category_map` 에서 바꾼다
- 가상자원 2339건이 전부 EBS 스냅샷이라 대장 `기타` 시트가 2380행이 된다.
  moto 데모 환경 특성인지 실계정에서도 그런지 확인 필요
