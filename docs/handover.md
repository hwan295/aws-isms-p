# 수집기 구조와 산출물 명세

**독자** — 판정·리포트를 맡는 담당 B, 그리고 이 저장소를 이어받을 사람.
**목적** — demo가 어떻게 도는지, 산출물 JSON이 각각 무슨 역할인지,
그 안의 필드가 어디서 왔고 무슨 뜻인지.

필드마다 **출처**를 표시했다. 이게 이 문서의 핵심이다.

| 표시 | 뜻 |
|---|---|
| `안내서` | ISMS-P 인증기준 안내서 1.2.1이 요구하는 항목 |
| `명세서` | `docs/field-mapping.md`가 정의한 항목 |
| `AWS` | AWS API 응답을 그대로 옮긴 것 |
| **`신설`** | **이 프로젝트가 임의로 만든 것.** 근거가 문서에 없으니 필요하면 바꿔도 된다 |

---

## 목차

- [1. 30초 요약](#1-30초-요약)
- [2. demo.py는 무엇을 하는가](#2-demopy는-무엇을-하는가)
- [3. 왜 collect와 extract를 나눴는가](#3-왜-collect와-extract를-나눴는가)
- [4. 산출물 4종](#4-산출물-4종)
- [A. 원본 덤프 JSON](#a-원본-덤프-json)
- [B. assets.json — B에게 넘기는 인계물](#b-assetsjson--b에게-넘기는-인계물)
- [C. config yaml 선언 문법](#c-config-yaml-선언-문법)
- [D. 데모 전용 산출물](#d-데모-전용-산출물)
- [E. B가 하면 안 되는 해석](#e-b가-하면-안-되는-해석)
- [F. 미해결 과제](#f-미해결-과제)
- [G. 데이터 계약 v0.1 대조](#g-데이터-계약-v01-대조)
- [H. 설계서 구조와 달라진 지점](#h-설계서-구조와-달라진-지점)

---

## 1. 30초 요약

AWS 계정을 훑어 **자산 목록 JSON**을 만든다. 두 단계로 나뉜다.

```
[collect]  AWS 응답을 손대지 않고 통째로 저장   → snapshots/raw/
              ↓ (AWS 접속 없음. 로컬 파일만 읽는다)
[extract]  yaml 선언대로 필드만 뽑아 정리       → snapshots/normalized/assets.json
              ↓
           담당 B (등급 제안 → 엑셀·리포트)
```

이 도구가 파는 지점은 **"값이 없다"를 그냥 넘기지 않는 것**이다.
모든 필드가 `{value, reason}` 쌍이고, 값이 없으면 왜 없는지가 같이 실린다.

```json
"owner_dept": { "value": null, "reason": "TAG_ABSENT",
                "hint": "OwnerDept 태그를 달면 다음 실행부터 자동 수집됩니다" }
```

**"모른다"와 "없다"를 구분하는 것이 전부다.** 권한이 없어 암호화를 못 읽은 걸
"미암호화"로 적으면 기밀성 등급이 통째로 틀린다.

---

## 2. demo.py는 무엇을 하는가

```bash
python demo.py
```

AWS 계정 없이 전체 흐름을 3초에 돌린다. `moto`라는 라이브러리가 boto3 호출을
가로채 가짜 AWS처럼 응답하기 때문에, 실제 계정에 접속하지 않는다.

### 단계

```
[1/4] 가짜 환경 생성   demo_env.py
      moto 안에 "지저분한" AWS 계정을 만든다.
      깨끗한 환경으로는 갭이 안 잡히므로 일부러 흠을 심는다.
        · 서버 6대 — 태그 완비 2 / 태그 전무 3 / 중지 1
        · 볼륨 4개 — 연결 2 / 미연결 2  ← 아무도 모르는 자산
        · 버킷 3개 — 암호화 1 / 미암호화 1 / 퍼블릭 1
        · DB 2대   — 백업 7일 1 / 백업 없음·퍼블릭 1
        · 보안시스템 — 일부러 아무것도 안 만듦 (결함사례 1 재현)
        · 다른 리전에 자산 1세트  ← 아무도 안 보는 리전 (결함사례 4)
                ↓
[2/4] collect          collector/collect.py
      계정 확인(sts) → 리전 목록(ec2) → 리전 × 서비스 순회
      각 서비스 모듈이 자기 API를 전부 호출하고 응답을 그대로 반환
                ↓
      snapshots/raw/{run_id}/{계정}/{리전}/{서비스}.json  (9개 파일)
                ↓
[3/4] extract          collector/extract.py    ← AWS 접속 없음
      1패스: 리소스별로 자산 레코드를 만들고 색인
      2패스: 색인으로 조인 (볼륨→인스턴스, 보안그룹 규칙, 백업 보호 여부)
      그 뒤 manual.py가 "담당자가 채워야 할 것"을 계산해 덧붙임
                ↓
      snapshots/normalized/{run_id}/assets.json
                ↓
[4/4] 산출물
      수기입력_템플릿.xlsx  +  iam_policy.json
```

### 왜 2패스인가

스냅샷이 어느 볼륨의 사본인지, 그 볼륨이 어느 인스턴스에 붙었는지는
**한 리소스만 봐서는 알 수 없다.** 1패스에서 전부 모아 `InstanceId → 자산` 색인을
만들고, 2패스에서 그 색인으로 `parent_id`를 채운다.
순서를 어기면 "사본은 원본 등급을 상속"(결함사례 5 대응)이 동작하지 않는다.

같은 이유로 보안그룹도 2패스다. EC2 인스턴스 응답에는 `SecurityGroups` **ID만**
있고 규칙은 없다. `describe_security_groups` 결과와 맞춰야 "0.0.0.0/0 → 22/tcp"가 나온다.

### 데모에만 있는 안전장치

| 장치 | 왜 |
|---|---|
| 자격증명 강제 덮어쓰기 | 발표 중 실수로 실제 고객 계정을 긁는 사고 방지 |
| 수집 계정이 `123456789012`가 아니면 중단 | 위 장치가 뚫렸을 때의 2차 방어 |
| `run_id` 충돌 시 `-2` 접미사 | `run_id`가 분 단위라 1분 내 재실행하면 직전 결과가 날아감 |
| moto 산출물 필터 | [D장](#d-데모-전용-산출물) 참조 |

---

## 3. 왜 collect와 extract를 나눴는가

**수집 시점에 필드를 골라 버리면 되돌릴 수 없기 때문이다.**

B가 나중에 "`deletion_protection`도 필요하다"고 하면, 필드를 골라 저장했을 경우
AWS를 다시 호출해야 한다. 자격증명이 필요하고, 전 리전 순회는 수 분이 걸리며,
그 사이 리소스가 바뀌어 **비교 기준선이 흔들린다.**

원본을 통째로 두면 재추출이 초 단위로 끝나고 자격증명도 필요 없다.

그리고 **원본 덤프 자체가 증적이다.** "이 시점에 AWS가 이렇게 응답했다"는 기록이
있어야 대장의 각 칸이 어디서 왔는지 추적된다.

### B의 필드 추가 요청 처리 절차

1. `config/extract_map.yaml`의 해당 리소스 `fields:`에 한 줄 추가
2. `python -m collector extract --run <run_id>` 재실행

**코드는 고치지 않는다. AWS도 다시 부르지 않는다.**
이게 지켜지는지는 `tests/test_extract.py::test_yaml에_필드를_추가하면_코드_수정_없이_반영된다`가 검증한다.

요청 양식:

```
extract_map.yaml 추가 요청
자산유형: 데이터(DBMS)
필요 필드: deletion_protection
원본 경로: rds/describe_db_instances → DBInstances[].DeletionProtection
용도: 가용성 룰 (운영 자산에 삭제 방지 미설정 시 가중)
```

---

## 4. 산출물 4종

| 파일 | 역할 | 누가 쓰나 |
|---|---|---|
| `snapshots/raw/{run_id}/**/*.json` | AWS 응답 원본. **증적이자 재추출 원천** | 재추출·감사 |
| `snapshots/normalized/{run_id}/assets.json` | **B에게 넘기는 인계물** | 담당 B |
| `output/수기입력_템플릿_{run_id}.xlsx` | 담당자가 손으로 채울 양식 | 기업 담당자 |
| `output/iam_policy.json` | 수집에 필요한 최소권한 정책 | 고객사 계정 담당자 |

> `snapshots/`는 `.gitignore`에 있다. 필드를 안 버렸으므로 **태그 값에 담당자
> 이메일·전화번호가 그대로 들어 있을 수 있다.** 개인정보 관리 도구가 스스로
> 개인정보 파일을 만드는 상황을 피한다.

---

## A. 원본 덤프 JSON

`snapshots/raw/{run_id}/{계정}/{리전}/{서비스}.json`

```json
{
  "meta": {
    "run_id": "run-20260801-1332",
    "account_id": "123456789012",
    "region": "ap-northeast-2",
    "service": "ec2",
    "collected_at": "2026-08-01T13:32:10.123456+00:00",
    "source_api": ["ec2:DescribeInstances", "ec2:DescribeVolumes", "..."],
    "is_global": false
  },
  "data": {
    "describe_instances": { "Reservations": [...], "__pages__": 1 },
    "describe_volumes":   { "Volumes": [...], "__pages__": 1 }
  }
}
```

### meta

| 필드 | 출처 | 의미 |
|---|---|---|
| `run_id` | 명세서 | 실행 단위 식별자 `run-YYYYMMDD-HHMM`. 전 리전 순회는 수 분이 걸려 `collected_at`이 레코드마다 달라지므로, **비교 기준선은 이것으로 잡는다** |
| `account_id` | AWS | `sts.get_caller_identity()`의 `Account` |
| `region` | AWS | 이 덤프를 뜬 리전. 전역 서비스는 `us-east-1` 고정 |
| `service` | **신설** | 수집기 이름. 파일명과 같다. `extract_map.yaml`의 `service:`가 이 값과 맞춰진다 |
| `collected_at` | 명세서 | 이 파일을 쓴 시각 (ISO8601, UTC) |
| `source_api` | 명세서 | 이 수집기가 선언한 IAM 액션 목록. **최소권한 정책의 재료** |
| `is_global` | **신설** | 전역 서비스 여부. S3·IAM은 리전 루프 밖에서 1회만 돈다 |

### data 안의 특수 키

여기 둘이 **이 프로젝트가 응답에 끼워 넣은 유일한 값**이다. 나머지는 AWS 응답 그대로다.

#### `__status__` — 값 대신 들어가는 상태 표지 `신설`

API가 값을 못 준 자리에 값 대신 들어간다.

```json
"get_bucket_encryption": {
  "__status__": "NOT_CONFIGURED",
  "error_code": "ServerSideEncryptionConfigurationNotFoundError"
}
```

| `__status__` | 언제 |
|---|---|
| `NOT_CONFIGURED` | AWS 설정이 없음. S3 암호화 미설정 등 |
| `PERMISSION_DENIED` | 권한 부족으로 조회 실패 |
| `COLLECT_ERROR` | 그 밖의 조회 실패 (서비스 없는 리전, 스로틀링, 일시 오류) |

같이 실리는 키: `error_code`(AWS 에러 코드), `detail`(에러 메시지).

**왜 필요한가** — S3의 `get_bucket_*` 계열은 설정이 없을 때 값이 아니라 **예외를 던진다.**
try/except가 에러 처리가 아니라 값 판정 로직이 되는 드문 경우다.
예외를 잡아 버리면 "설정이 없다"는 사실 자체가 사라지므로, 값으로 정규화해 남긴다.

> 미설정 신호는 두 형태로 온다. 예외를 던지는 것(`get_bucket_encryption`)과
> **키 없는 정상 응답**을 주는 것(`get_bucket_versioning`). 둘 다 `NOT_CONFIGURED`로
> 정규화하고, 후자는 `error_code: "EMPTY_RESPONSE"`로 구분한다. 실측 표는 `docs/aws-facts.md` §3.

#### `__pages__` — 페이지네이션 증거 `신설`

```json
"describe_instances": { "Reservations": [...], "__pages__": 3 }
```

페이지네이터가 몇 페이지를 돌았는지. AWS는 자산이 많으면 **조용히 일부만** 반환하는데,
자산 목록 도구에서 가장 치명적이고 가장 늦게 발견되는 버그다.
이 값이 있으면 "정말 다 받았나"를 사후에 확인할 수 있다.

### manifest.json

`snapshots/raw/{run_id}/manifest.json` — 실행 1회의 요약. extract가 무엇을 읽을지 여기서 안다.

| 필드 | 출처 | 의미 |
|---|---|---|
| `run_id` / `account_id` / `account_alias` / `regions` | 명세서 | 실행 범위 |
| `started_at` / `finished_at` | **신설** | 순회 시작·종료 시각. 소요 시간이 길면 그 사이 변경 가능성을 감안해야 한다 |
| `files` | **신설** | 쓴 덤프 파일 경로 목록 |
| `stats` | **신설** | `services` / `regions` / `files` 개수와 **상태 표지 3종의 발생 건수** |

---

## B. assets.json — B에게 넘기는 인계물

> **담당 B에게는 [`contract.md`](contract.md)를 주십시오.** 코드를 짜는 데 필요한 것만
> 추린 짧은 버전입니다. 이 장은 필드별 출처(`안내서`/`명세서`/`신설`)까지 담은 상세판으로,
> 저장소를 이어받는 사람을 위한 것입니다.


```
snapshots/normalized/{run_id}/assets.json
```

```json
{
  "meta": { ... },
  "asset_types": {
    "서버": { "isms_required_items": [...], "assets": [...], "manual_required": [...] },
    "데이터(DBMS)": { ... },
    "보안시스템": { "asset_count": 0, "assets": [] },
    ... (11종 전부)
  },
  "manual_todo": { "summary": {...}, "by_owner": {...}, "blocked": [...] }
}
```

### B-1. meta

| 필드 | 출처 | 의미 |
|---|---|---|
| `contract_version` | **신설** | 이 JSON 구조의 버전. 현재 `"1.0"`. **구조가 바뀌면 올린다** |
| `run_id` | 명세서 | 어느 수집 실행에서 나왔나 |
| `account_id` / `account_alias` | 명세서 | 계정 식별자. 없으면 증적 불성립 |
| `collected_at` | 명세서 | 수집 시작 시각 |
| `regions` | 명세서 | 순회한 리전 목록 |
| `reason_codes` | **신설** | 이 파일에 나올 수 있는 사유 코드 전체. B가 하드코딩하지 않아도 되게 |
| `reason_codes_not_absence` | **신설** | **자산 부재로 해석하면 안 되는 사유.** `["PERMISSION_DENIED", "COLLECT_ERROR", "OUT_OF_SCOPE"]` |
| `infra_fact_keys` | **신설** | `infra_facts`에 반드시 있는 17키. 룰이 조용히 실패하지 않게 계약으로 고정 |
| `source_api_by_resource` | 명세서 | **자산이 어느 API에서 나왔는지 되짚는 표.** 계약 v0.1의 `source_api` 대응 ([G장](#g-데이터-계약-v01-대조)) |
| `graded_by` | **신설** | `grade_proposed`·`grade_confirmed`는 이 파일에 없고 담당 B가 채운다는 명시 |
| `total_assets` | **신설** | 자산 총 건수 |
| `collection_issues` | **신설** | **원천 API 자체가 실패한 기록.** 아래 참조 |

#### `collection_issues` — 0건의 뜻을 가르는 장치 `신설`

```json
"collection_issues": [
  { "region": "eu-west-1", "service": "ec2", "resource_type": "ec2_instance",
    "status": "PERMISSION_DENIED", "error_code": "UnauthorizedOperation" }
]
```

`describe_instances`가 권한 부족으로 실패한 리전을 **"서버 0대"로 적으면 자산 목록
전체가 거짓이 된다.** 그 리전·리소스를 여기 기록하고, 자산 배열에서는 뺀다.
**B는 이 배열이 비어 있지 않으면 "0건"을 신뢰하면 안 된다.**

### B-2. asset_types — 자산유형 11종

키는 안내서 10종 + 클라우드 조항에서 파생한 `가상자원` = **11종 고정**이다.

```
서버 / 데이터(DBMS) / 정보시스템(응용프로그램) / 소프트웨어 / 네트워크장비 /
보안시스템 / PC / 정보 / 설비 / 시설 / 가상자원
```

**AWS로 한 건도 안 잡히는 유형(설비·시설 등)도 키를 만들어 빈 배열로 둔다.**
키가 없으면 "수집기가 빠뜨린 것"과 "실제로 0건인 것"을 구분할 수 없고,
0건이라는 사실 자체가 결함사례 1·4의 리포트 대상이다. `안내서`

| 필드 | 출처 | 의미 |
|---|---|---|
| `isms_required_items` | 안내서 | 이 유형이 요구하는 항목 목록. `config/isms_asset_types.yaml`에서 옴 |
| `aws_collectable` | **신설** | 이 유형을 채우는 수집 리소스 타입 목록 |
| `collector_exists` | **신설** | 수집기가 있는가. **0건의 뜻을 가른다** (아래) |
| `asset_count` | **신설** | 자산 건수 |
| `assets` | — | 자산 레코드 배열 |
| `manual_required` | **신설** | 담당자가 채워야 할 요구항목 ([B-7](#b-7-manual_required--유형별-미충족-요구항목)) |

#### 세 종류의 "0건" — 이 설계의 요점

| 상태 | 판정식 | 심사에서의 뜻 |
|---|---|---|
| **수집했으나 0건** | `collector_exists == true` 이고 `asset_count == 0` | **확인했더니 정말 없다.** 통제 부재이므로 결함 소지 |
| **수집기가 없어 0건** | `collector_exists == false` | **확인하지 않았다.** 아무 말도 할 수 없다 |
| **조회 실패** | `collection_issues`에 기록 | **못 읽었다.** 자산 부재가 아니다 |

셋을 같은 `0`으로 적으면 대장이 거짓이 된다.
데모에서 보안시스템을 일부러 비워두는 이유가 첫 번째를 보여주기 위해서다. `안내서 결함사례 1`

### B-3. 자산 레코드 — 식별 필드 (스칼라)

이 7개만 `{value, reason}`이 아니라 **평범한 값**이다. 항상 채워져 있기 때문이다.

| 필드 | 출처 | 의미 |
|---|---|---|
| `asset_id` | 명세서 | ARN 우선. 없으면 리소스 ID로 구성. **자산의 유일 키이자 diff 기준** |
| `asset_type` | 안내서 | 11종 중 하나 |
| `resource_type` | **신설** | `ec2_instance` / `s3_bucket` 같은 **수집 단위 이름.** 같은 `asset_type`이라도 EC2와 Lambda는 성격이 다르므로, B가 룰을 세분화할 때 쓴다 |
| `account_id` / `region` | 명세서 | 클라우드 자산 특정의 최소 식별자 |
| `run_id` / `collected_at` | 명세서 | 언제 수집됐나 |

### B-4. 자산 레코드 — 계약 필드 39종

**전부 `{value, reason}` 형태이고, 사유가 있으면 `hint`가 붙는다.**

```json
"owner_dept": { "value": null, "reason": "TAG_ABSENT",
                "hint": "OwnerDept 태그를 달면 다음 실행부터 자동 수집됩니다" }
```

| 키 | 타입 | 의미 |
|---|---|---|
| `value` | any | 값. 없으면 `null` |
| `reason` | str \| null | 없는 이유. 정상 수집이면 `null` |
| `hint` | str (선택) | **담당자가 어떻게 하면 채워지는지.** 있을 때만 붙는다 |

> **모든 자산이 39개 키를 전부 갖는다.** 그 리소스가 선언하지 않은 필드는
> `NOT_APPLICABLE`로 채워진다. B는 키 존재 여부를 확인할 필요가 없다.

#### 안내서·명세서가 요구하는 필드

| 필드 | 출처 | 값 예시 | 비고 |
|---|---|---|---|
| `asset_name` | `안내서` | `"prd-web-01"` | 호스트 명칭 / 자산명. 대개 `Name` 태그 |
| `usage` | `안내서` | `"WebServer"` | 용도(목적 및 기능). `InventoryCategory` 태그 |
| `owner_dept` | `안내서` | `"인프라운영팀"` | 관리 부서명 |
| `owner_manager` | `안내서` | `"김실무"` | 관리 실무자 |
| `owner_responsible` | `안내서` | `"박책임"` | 관리 책임자 |
| `has_personal_info` | `안내서` | `true` | 개인정보 보유 여부. `HandlePI` 태그 → bool |
| `personal_info_items` | `안내서` | `["name","phone"]` | 개인정보 항목명. `PIItems` 태그 → 배열 |
| `data_source` | 명세서 | `"ThirdParty"` | 수집 출처. `결함사례 2` 대응 |
| `in_scope` | `안내서` | `true` | 인증범위 포함 여부. `InScope` 태그 → bool |
| `scope_reason` | 명세서 | `null` | 범위 제외 사유. `결함사례 4` 대응 |
| `environment` | 명세서 | `"Prod"` | `Environment` 태그. 등급 룰 A-04/A-05 입력 |
| `service_name` | 명세서 | `"포털"` | 소속 시스템 |
| `az` | 명세서 | `"ap-northeast-2a"` | 가용영역 |
| `lifecycle_state` | 명세서 | `"running"` | 생명주기 상태. diff의 폐기 판정 근거 |
| `created_at` | 명세서 | ISO8601 | 도입일 |
| `endpoint` | 명세서 | `"prd.xxx.rds.amazonaws.com"` | 접속 지점 |
| `ip_private` / `ip_public` | `안내서` | `"10.0.1.25"` | IP주소 |
| `os` | `안내서` | `null` | OS(배포판·버전). **현재 항상 `OUT_OF_SCOPE`** — SSM 미수집. Linux/Windows 구분은 `platform`을 쓸 것 |

#### 이 프로젝트가 추가한 필드 `신설`

안내서·명세서에 없지만 자산 식별·조인·룰에 필요해서 만들었다. **빼도 계약이 깨지지 않는다.**

| 필드 | 값 예시 | 왜 만들었나 |
|---|---|---|
| `serial_no` | `"i-0abc123"` | 안내서의 "자산 일련번호"에 대응하는 AWS 식별자. 사내 자산코드는 아니므로 매핑 규칙이 별도로 필요하다 |
| `model` | `"t3.large"` | 안내서 "모델명". 인스턴스 타입·볼륨 타입 |
| `engine` / `version` | `"mysql"` / `"8.0.35"` | DBMS 종류·버전 |
| `port` | `3306` | 엔드포인트 포트 |
| `size_gb` | `20` | 볼륨·스냅샷 크기. 미연결 볼륨의 규모를 보여줄 때 쓴다 |
| `vpc_id` / `subnet_id` | `"vpc-0abc"` | 네트워크 위치. 구성도·세그먼트 판단 재료 |
| `cidr` | `"10.0.0.0/16"` | VPC·서브넷 대역 |
| `is_default` | `false` | 기본 VPC 여부. 기본 VPC 방치는 흔한 지적 사항 |
| `image_id` | `"ami-0abc"` | 이 인스턴스가 어느 이미지에서 왔나. 가상자원 시트와 조인 |
| `tenancy` / `virtualization` | `"default"` / `"hvm"` | 안내서의 "VM/Hardware" 구분 재료 |
| `attached_to` | `"i-0abc123"` | 볼륨·EIP가 붙은 대상. `parent_id`의 원본 값 |
| `expires_at` | `"2027-03-01"` | 인증서 만료일. 등급 룰 A-06 입력 |
| `owner_account` | `"591542846629"` | 스냅샷·이미지 소유 계정. **실계정에서는 항상 수집 계정과 같다.** moto가 `OwnerIds=['self']` 필터를 무시해서 데모가 남의 계정 산출물을 걸러낼 근거로 넣었다 |
| `platform` `신설` | `"Linux/UNIX"` | OS 계열. `describe_instances`에 이미 있어 추가 호출이 없다. `os`(배포판·버전, SSM 필요)와 다르다. **시트 배정은 이 값을 쓸 것** |
| `data_classification` `신설` | `"confidential"` | 정보 민감도(`DataClass` 태그). 별지 제3호 기밀성 접근 범위 3단계의 근거. `has_personal_info`와 **다른 축**이라 합치면 안 된다 |

### B-5. 관계 필드

| 필드 | 출처 | 의미 |
|---|---|---|
| `parent_id` | 명세서 | 상위 자산의 `asset_id`. 볼륨→인스턴스, 스냅샷→볼륨 |
| `relation_type` | 명세서 | `attached_to` / `snapshot_of` / `image_of` |
| `tags_raw` | 명세서 | 정규화된 태그 전체 `{키: 값}`. **반출 시 마스킹 대상** |

`tags_raw`는 서비스마다 다른 태그 형식을 하나로 통일한 결과다.
EC2는 `Tags`(대문자 리스트), RDS는 `TagList`, S3는 `get_bucket_tagging()` 별도 호출.
**B는 이 차이를 몰라도 된다.**

`parent_id`가 `NOT_CONFIGURED`면 "붙어 있지 않다"(미연결 볼륨),
`COLLECT_ERROR`면 "참조 대상을 수집 결과에서 못 찾았다"는 뜻이다. 둘은 다르다.

### B-6. 사유 코드 8종 — 이 계약의 핵심

`안내서 결함사례 5` 대응의 근간이다. 값이 없는 이유를 모르면 등급을 매길 수 없다.

| reason | 의미 | 담당자가 고칠 수 있나 | 갭 리포트 |
|---|---|---|---|
| `null` | 정상 수집됨 | — | — |
| `TAG_ABSENT` | 태그 미입력 | **가능.** 태그 달면 다음 실행부터 자동 | 출력 |
| `NOT_CONFIGURED` | AWS 설정이 없음 | 사실 자체가 정보. 등급 근거가 됨 | 출력 |
| `API_NULL` | API가 값을 안 줌 | 불가 | 출력 |
| `NOT_APPLICABLE` | **이 자산유형에 개념 자체가 없음** | — | **출력 안 함** |
| `PERMISSION_DENIED` | 권한 부족으로 조회 실패 | 권한 부여로 해결 | **별도 출력** |
| `COLLECT_ERROR` | 조회 자체가 실패 | 재실행·수집기 수정 | **별도 출력** |
| `OUT_OF_SCOPE` | **개념은 있는데 이 도구가 아직 그 API를 안 부름** | 수집기 확장으로 해결 | **별도 출력** |

`TAG_ABSENT` / `NOT_CONFIGURED` / `API_NULL`은 원래 프로젝트 규칙에 있었고,
나머지 넷은 구현하면서 필요해서 만들었다. `신설`

#### 왜 넷을 더 만들었는가

**`NOT_APPLICABLE`** — 이게 없으면 갭 리포트가 *"S3 버킷의 IP주소 미확인"* 같은 행으로
채워져 리포트 전체의 신뢰가 무너진다. 명세서 §7이 지적한 문제다.

**`PERMISSION_DENIED`** — 권한이 없어 암호화 설정을 못 읽은 것을 "미암호화"로 기록하면
**기밀성 등급이 통째로 틀린다.**

**`COLLECT_ERROR`** — 전 리전 순회 중 서비스가 없는 리전·스로틀링을 만나면 조회가 실패한다.
이걸 `NOT_CONFIGURED`로 뭉개면 "설정이 없다"가 되고, 예외를 던지면 순회가 통째로 죽는다.

**`OUT_OF_SCOPE`** — EC2에 공인 IP가 없다고 `exposure_path`를 `"None"`으로 단정하면
**ALB 뒤에 있는 자산을 "외부 미노출"로 규정**하게 된다. 룰 C-03이 무너진다.
안 불러본 것을 "없음"이라고 쓰지 않기 위한 코드다.

> 요약하면 **`PERMISSION_DENIED` · `COLLECT_ERROR` · `OUT_OF_SCOPE`는 전부 "모른다"이고
> "없다"가 아니다.** `meta.reason_codes_not_absence`에 이 셋이 들어 있다.

### B-7. infra_facts — 등급 룰의 입력값

`docs/field-mapping.md` §5가 정의한 17키. **자산마다 반드시 17개가 다 있다.**
값 형태는 계약 필드와 같은 `{value, reason}`이다.

```json
"infra_facts": {
  "open_sg_rule":   { "value": true, "reason": null },
  "open_sg_detail": { "value": ["sg-0abc:22/tcp"], "reason": null },
  "backup_exists":  { "value": null, "reason": "COLLECT_ERROR", "hint": "..." },
  "exposure_path":  { "value": null, "reason": "OUT_OF_SCOPE", "hint": "..." }
}
```

| 키 | 타입 | 어디서 나오나 |
|---|---|---|
| `backup_exists` | bool | **2패스 조인.** `backup.list_protected_resources()`에 이 ARN이 있는가 |
| `backup_source` | str | 위 API의 보관소·최종 백업 시각 문자열 |
| `snapshot_count` | int | **2패스 조인.** 이 볼륨을 원본으로 하는 스냅샷 수 |
| `pitr_enabled` | bool | RDS `BackupRetentionPeriod > 0` |
| `multi_az` | bool | RDS `MultiAZ` |
| `in_asg` | bool | `aws:autoscaling:groupName` 태그 존재 여부 |
| `public_exposed` | bool | EC2 공인 IP / RDS `PubliclyAccessible` / S3 `IsPublic` |
| `exposure_path` | enum | **2패스 조인.** `Direct`/`ALB`/`CloudFront`/`APIGateway`. 찾았을 때만 값이 붙는다 |
| `encryption_at_rest` | enum | `None` / `SSE-S3` / `SSE-ECR` / `SSE-KMS` (아래 주의) |
| `encryption_in_transit` | bool | ALB 리스너 프로토콜 / CloudFront ViewerProtocolPolicy |
| `open_sg_rule` | bool | **2패스 조인.** 0.0.0.0/0 인바운드 존재 여부 |
| `open_sg_detail` | list | `["sg-0abc:22/tcp"]` — 포트까지. 근거 문구를 구체적으로 쓰기 위해 |
| `versioning_enabled` | bool | S3 버전관리 |
| `object_lock` | bool | S3 객체 잠금. 증적 불변성 |
| `logging_enabled` | bool | S3 접근 로깅 / CloudTrail 다중 리전 |
| `deletion_protection` | bool | RDS 삭제 방지 |
| `state` | str | 자산 상태 |

> **사실 수집일 뿐 판정이 아니다.** `encryption_at_rest: "None"`은 사실,
> "기밀성 2점"은 판정이다. 판정은 B의 몫이다.

#### `exposure_path` — 2패스가 채우는 노출 경로 `신설`

공인 IP가 없어도 ALB 뒤에 있으면 외부에 노출된다. 앞단을 안 보면 "미노출"로
단정하게 되고 기밀성 룰이 통째로 틀어진다. 2패스가 ALB 타깃그룹과 CloudFront
오리진을 훑어 뒤에 있는 자산에 경로를 붙인다.

```
prd-was-02          public_exposed=False  →  exposure_path=ALB
corp-public-assets  public_exposed=None   →  exposure_path=CloudFront
```

**찾았을 때만 값이 붙는다.** 못 찾으면 `OUT_OF_SCOPE`로 두고 아직 안 보는 경로를
hint에 적는다(Route 53 별칭·Global Accelerator·VPC 엔드포인트). `None`으로 단정하면
"안 불러본 것을 없음이라 쓰지 않는다"는 이 프로젝트의 대원칙을 어긴다.

무엇이 노출될 수 있는가는 **yaml 선언이 정한다.** 2패스는 선언이
`NOT_APPLICABLE`이라고 말한 자산은 건드리지 않는다 — 서브넷의 `MapPublicIpOnLaunch`는
네트워크 설정이지 엔드포인트가 아니다.

#### `SSE-ECR` — ECR 리포지토리 전용 값 `신설`

ECR의 `AES256`은 ECR이 관리하는 키다. S3가 아니므로 `SSE-S3`로 적으면 거짓이다.
서비스 관리 키라는 점은 같지만 출처가 달라 갈라 적는다. 등급 룰은 "암호화 없음"만
보므로 룰에는 영향이 없다.

#### ⚠ `encryption_at_rest`에 `SSE-KMS-CMK`는 나오지 않는다

명세서 부록B의 허용값은 `None` / `SSE-S3` / `SSE-KMS-AWS` / `SSE-KMS-CMK` 네 가지다.
그런데 **고객관리형 키(CMK)인지 AWS 관리형인지는 `kms.describe_key`의 `KeyManager`를
봐야 알 수 있고, 아직 그 API를 부르지 않는다.**

`describe_volumes`는 `Encrypted: true`와 `KmsKeyId`까지만 준다.
여기서 `SSE-KMS-CMK`로 적으면 **룰 C-06이 근거 없이 발동한다.**

→ **`SSE-KMS`까지만 적는다.** 허용값이 하나 늘어난 셈이다. `신설`

| 값 | 뜻 |
|---|---|
| `None` | 미암호화 (확정) |
| `SSE-S3` | S3 관리 키 (확정) |
| `SSE-KMS` | **KMS 암호화는 확실하나 키 소유자 미확정** |

**룰 C-06은 KMS 수집기가 생기기 전까지 쓸 수 없다.**

### B-8. manual_required — 유형별 미충족 요구항목

`asset_types[유형].manual_required` — **AWS로 채워지지 않는 요구항목**을 자동 계산한 것. `신설`

```json
{
  "item_name": "개인정보유출방지시스템",
  "collected_count": 0,
  "asset_count": 0,
  "reason": "온프레미스 엔드포인트 솔루션이라 AWS API 대상이 아니다",
  "evidence": "ISMS-P 안내서 1.2.1 결함사례 1 — ...",
  "owner": "정보보안팀",
  "action": "보유 솔루션을 수기 등재. 미보유 시 미보유 사실을 문서화",
  "examples": ["출력물 보안", "문서암호화(DRM)", "USB 매체제어"],
  "auto_after_fix": false,
  "manual_ref": "security_system_dlp",
  "sample_asset_ids": [],
  "note": "AWS 수집 결과 0건"
}
```

| 필드 | 의미 |
|---|---|
| `item_name` | 안내서가 요구하는 항목명 |
| `collected_count` / `asset_count` | 채워진 건수 / 대상 건수 |
| `reason` | **왜** AWS로 못 채우는가 |
| `evidence` | 안내서 어느 조항·결함사례가 근거인가 |
| `owner` | **누가** 해야 하나 |
| `action` | **어떻게** 채우나 |
| `examples` | 해당 항목의 구체 예시 |
| `auto_after_fix` | **`true`면 태그만 달면 다음 실행부터 자동.** `false`면 영원히 수기 |
| `manual_ref` | `config/manual_items.yaml`의 키 |
| `sample_asset_ids` | 결측 자산 샘플 3건 |
| `note` | `"AWS 수집 결과 0건"` 또는 `"N건 전부 미입력"` |

**`auto_after_fix`가 이 구조에서 가장 중요하다.** 담당자 입장에서
"태그 한 번 달면 끝"과 "매번 손으로 관리"는 완전히 다른 일이다. 섞어 보여주면
우선순위를 정할 수 없다.

### B-9. manual_todo — 담당자별 작업 지시

`assets.json` 최상단. **누가 무엇을 몇 건 해야 하는지.** `신설`
(프롬프트에 골격이 있었고, `blocked`와 세부 필드는 구현하며 추가)

```json
"manual_todo": {
  "summary": { "total": 22, "auto_after_fix": 5, "permanent": 17, "total_assets": 2380 },
  "by_owner": {
    "각 자산 운영 부서": [
      { "key": "asset_owner", "item_name": "관리부서·관리실무자·관리책임자",
        "action": "OwnerDept / OwnerManager / OwnerResponsible 태그 입력",
        "affected_assets": 38, "affected_ratio": "90%",
        "auto_after_fix": true,
        "evidence": "ISMS-P 안내서 1.2.1 ...",
        "sample_asset_ids": ["arn:aws:ec2:...", "..."] }
    ]
  },
  "blocked": [ ... ]
}
```

#### summary

| 필드 | 의미 |
|---|---|
| `total` | 작업 건수 |
| `auto_after_fix` | 그중 태그로 해결되는 것 |
| `permanent` | 영구 수기 |
| `total_assets` | 모수 |

#### by_owner — 태그로 해결되는 행

| 필드 | 의미 |
|---|---|
| `key` | `manual_items.yaml`의 항목 키 |
| `affected_assets` / `affected_ratio` | **영향 자산 수와 비율.** 이게 있어야 우선순위를 정한다 |
| `sample_asset_ids` | 확인용 샘플 3건 |

> "태그 하나로 38건 해결"과 "1건짜리 수기 등재"는 **노력 대비 효과가 완전히 다르다.**
> 숫자가 없으면 담당자는 무엇부터 할지 못 정한다.

#### by_owner — 영구 수기 행

| 필드 | 의미 |
|---|---|
| `currently_registered` | **이 항목으로 등재된 수기 행의 수.** 아직 수기 시트를 읽어들이지 않으므로 항상 `0` |
| `examples` | 구체 예시 |

> ⚠ `currently_registered`에 **자산유형의 AWS 수집 건수를 넣으면 안 된다.**
> 보안시스템에 GuardDuty·KMS가 5건 있다고 "내부정보 유출통제 시스템 5건 등재"로
> 보이면, `결함사례 1`을 잡으려고 만든 항목이 오히려 결함을 가려버린다.
> (구현 중 실제로 이렇게 나왔던 것을 고쳤다.)

#### blocked — 권한 부족·조회 실패 `신설`

```json
{ "field": "infra_facts.backup_exists", "reason": "COLLECT_ERROR",
  "affected_assets": 24, "detail": "조회에 실패했습니다(404). 자산이 없다는 뜻이 아닙니다",
  "sample_asset_ids": [...],
  "note": "자산이 없다는 뜻이 아니다. 권한 부여 또는 재수집으로 해결한다" }
```

**작업 목록과 절대 섞지 않는다.** 권한 문제를 자산 문제로 오인하면 대장 전체가 틀린다.

---

## C. config yaml 선언 문법

**전부 이 프로젝트가 설계한 것이다.** `신설`
"추출 규칙은 코드가 아니라 선언"이라는 원칙을 구현한 결과이고,
**여기를 고치면 코드 수정 없이 동작이 바뀐다.**

### C-1. `config/extract_map.yaml` — 원본 경로 → 계약 필드

```yaml
resources:
  ec2_instance:
    service: ec2                                    # 어느 덤프 파일에서 읽나
    iterate: "describe_instances.Reservations[].Instances[]"
    asset_type: "서버"
    asset_id: "arn:aws:ec2:{region}:{account}:instance/{InstanceId}"
    index_key: "InstanceId"                         # 2패스 조인용 색인 키
    tags: "Tags"                                    # 태그가 있는 경로
    security_groups: "SecurityGroups[].GroupId"     # 보안그룹 조인용
    backupable: true                                # AWS Backup 대상인가
    fields:
      asset_name: { tag: "Name" }
      model:      { path: "InstanceType" }
```

#### 리소스 선언 키

| 키 | 의미 |
|---|---|
| `service` | 읽어올 덤프 파일 이름 (`meta.service`와 매칭) |
| `iterate` | 자산 하나하나를 꺼낼 JMESPath. 또는 `{map: "buckets", key_as: "Name"}` (dict를 도는 형태) |
| `merge` | 다른 응답과 합치기. `{from: "list_buckets.Buckets", match_key: "Name"}` |
| `where` | **자산으로 등재할 것만 남기는 필터.** KMS는 `KeyManager == 'CUSTOMER'`만 자산 |
| `asset_type` | 11종 중 하나 |
| `asset_id` | ARN 템플릿. `{region}` `{account}`와 응답 필드를 치환 |
| `index_key` | 2패스 조인 색인 키 |
| `region_from` | 리전을 응답에서 읽어야 할 때 (S3 버킷) |
| `tags` | 태그 경로. 서비스마다 다른 형식을 여기서 흡수 |
| `tags_unavailable` | **태그 조회 API를 안 부르는 리소스.** 지정하면 모든 태그 필드가 `TAG_ABSENT`가 아니라 `OUT_OF_SCOPE`가 된다 |
| `security_groups` | 보안그룹 ID 경로. 있으면 `open_sg_rule` 조인 대상 |
| `backupable` | AWS Backup 대상 여부. `false`면 `backup_exists`가 `NOT_APPLICABLE` |
| `parent` | 상위 자산 연결. `{via: "...", target: "...", relation: "..."}` |
| `fields` | 계약 필드 선언 |
| `infra_facts` | 이 리소스가 채울 수 있는 fact |
| `infra_facts_out_of_scope` | **개념은 있는데 안 부르는 API.** `{키: "필요한 수집기"}` |

> `tags_unavailable`과 `infra_facts_out_of_scope`가 **`OUT_OF_SCOPE`를 만들어내는 자리**다.
> 이 둘이 없으면 "안 불러본 것"이 `TAG_ABSENT`나 `NOT_APPLICABLE`로 잘못 나간다.

#### 필드 선언 형태

| 형태 | 값이 없을 때 사유 | 쓰임 |
|---|---|---|
| `{ path: "InstanceId" }` | `API_NULL` | AWS 응답에서 |
| `{ tag: "OwnerDept" }` | `TAG_ABSENT` | 태그에서 |
| `{ tag_present: "aws:autoscaling:groupName" }` | (없음) | **태그의 존재 여부가 답인 경우.** 없는 것도 값(`false`)이므로 `TAG_ABSENT`가 아니다 |
| `{ const: "침입탐지시스템" }` | (없음) | 고정값 |
| `{ out_of_scope: "ssm.describe_... 필요" }` | `OUT_OF_SCOPE` | 안 부르는 API |

> `tag_present`가 왜 필요한가 — `aws:autoscaling:groupName`은 AWS가 붙이는 태그다.
> 없다고 "태그를 다세요"라고 안내하면 **틀린 처방**이 된다.

`transform`으로 값 변환: `present` `bool` `csv` `enabled` `positive` `enc_bool` `sse_algorithm` `str`

#### 경로 도중 상태 표지를 만나면

`get_bucket_encryption`이 `__status__: NOT_CONFIGURED`면, 그 경로를 쓰는 필드는
자동으로 `reason: "NOT_CONFIGURED"`가 된다. **특수 코드가 아니라 이 규칙 하나의 결과다.**

### C-2. `config/isms_asset_types.yaml` — 유형별 요구 항목

```yaml
서버:
  required_items:
    - { name: "호스트 명칭", field: asset_name }
    - { name: "보안등급",   field: null, manual_ref: security_grade }
  not_applicable: [endpoint, personal_info_items]
  aws_collectable: [ec2_instance]
```

#### `required_items`의 세 형태

| 형태 | 충족 조건 | 쓰임 |
|---|---|---|
| `field: <이름>` | 그 계약 필드가 채워지면 충족 | 대부분의 항목 |
| `field: null` + `manual_ref` | AWS로 못 채움. 무조건 수기 | 보안등급, 테이블명 등 |
| `presence: [resource_type]` | **그 리소스 자산이 1건 이상 있으면 충족** | 보안시스템 |

> `presence`가 왜 필요한가 — 보안시스템의 요구항목은 "자산의 어느 필드"가 아니라
> **"그 통제가 존재하는가"**다. "보안시스템 5건 있음"과 "침입차단시스템 있음"은 다르다.
> 뭉개면 `결함사례 1`을 잡으라고 만든 기능이 결함을 가린다.

| 그 밖의 키 | 의미 |
|---|---|
| `not_applicable` | 그 유형에서 `NOT_APPLICABLE` 사유를 붙일 필드 목록 |
| `aws_collectable` | 이 유형을 채우는 리소스 타입. **비어 있으면 `collector_exists: false`** |
| `manual_only` | AWS API 대상이 아닌 유형 (설비·시설) |

### C-3. `config/manual_items.yaml` — 수집 불가 항목

```yaml
personal_info_items:
  isms_asset_type: "데이터(DBMS)"
  item_name: "(개인)정보 항목명"
  reason: "컬럼명·데이터 내용은 관리 API 밖의 영역이다"
  evidence: "ISMS-P 안내서 1.2.1 데이터 유형 항목(예) — 이름, 성별, ..."
  owner: "개인정보보호 담당 / DBA"
  action: "개인정보 흐름표와 대조해 PIItems 태그 입력"
  fields: [personal_info_items]
  condition: { field: has_personal_info, equals: true }
  auto_after_fix: true
```

| 키 | 의미 |
|---|---|
| `item_name` / `examples` | 항목명과 구체 예시 |
| `reason` / `evidence` | 왜 수기인가 / 안내서 근거 |
| `owner` / `action` | 누가 / 어떻게 |
| `fields` | 이 항목이 담당하는 계약 필드. **`required_items`에 `manual_ref`를 안 적어도 이걸로 자동 연결된다** |
| `condition` | **조건부 필수 규칙** (아래) |
| `auto_after_fix` | 태그로 해결되는가 |
| `note` | 부가 설명 |

#### `condition` — 조건부 필수

```yaml
condition: { field: has_personal_info, equals: true }
```

`HandlePI=Y`일 때만 `PIItems`가 필수이고, `InScope=N`일 때만 `ScopeReason`이 필수다.
**조건을 안 보면 개인정보를 안 다루는 자산까지 "개인정보 항목 미입력"으로 세어
숫자가 부풀고 우선순위가 뒤집힌다.** (실제로 24건 → 4건으로 바로잡혔다.)

---

## D. 데모 전용 산출물

### `assets.demo-view.json`

**데모 화면용 사본이다. B에게 넘기는 것은 `assets.json`이다.**

moto는 `describe_snapshots(OwnerIds=['self'])` 필터를 구현하지 않아
**Amazon·Canonical 소유 스냅샷 2337건**을 돌려준다. 실계정에서는 나오지 않는다.
그대로 두면 전체 자산의 98%가 노이즈라 "관리주체 미식별 100%" 같은 숫자가
전부 남의 계정 스냅샷에 지배된다.

`demo.py`가 이를 걸러 별도 파일로 쓴다. 걸러낸 뒤 `manual_todo`를 다시 계산한다.

```json
"meta": {
  "demo_filter": {
    "removed": {
      "타 계정 소유 스냅샷·이미지 — moto가 OwnerIds=['self'] 필터를 무시함":
        { "count": 2337, "details": ["013907871322", "099720109477", "..."] }
    },
    "note": "moto가 심어둔 산출물. 실제 AWS 계정에서는 애초에 수집되지 않는다"
  }
}
```

**조용히 빼지 않는다.** 몇 건을 왜 뺐는지 화면과 JSON에 남기고,
원본 `assets.json`은 손대지 않는다. 그러지 않으면 JSON을 열어본 사람이
숫자 불일치를 발견하는 순간 도구 전체의 신뢰가 무너진다.

### `output/iam_policy.json`

각 수집기가 선언한 `required_actions`를 모은 최소권한 정책.
**쓰기 액션이 하나라도 섞이면 생성이 실패한다.**
`ReadOnlyAccess`를 요구하지 않는다는 것 자체가 산출물이 된다.

### `output/수기입력_템플릿_{run_id}.xlsx`

3시트. **담당자가 백지에서 시작하지 않게 하는 것이 목적이다.**

| 시트 | 내용 |
|---|---|
| 수기 등재 | AWS 밖 자산. `자산유형 / 항목명 / 예시 / 왜 수기인가 / 근거 / 담당 / 해야 할 일 / 작성란` |
| 태그로 해결 | 태그만 달면 자동. **영향 자산 수 내림차순** 정렬 |
| 읽는 법 | 두 시트가 왜 나뉘는지, 설비·시설이 왜 미리 채워져 있는지 |

설비·시설의 작성란에는 제외 사유가 미리 채워져 있다.
사유 없이 비워두면 그 자체가 결함이기 때문이다.

---

## E. B가 하면 안 되는 해석

1. **`PERMISSION_DENIED` · `COLLECT_ERROR` · `OUT_OF_SCOPE`를 자산 부재로 읽지 말 것.**
   `meta.reason_codes_not_absence`에 명시돼 있다.
2. **`NOT_APPLICABLE`을 갭으로 세지 말 것.** 개념이 없는 것이지 미확인이 아니다.
3. **`collection_issues`가 비어 있지 않으면 "0건"을 신뢰하지 말 것.**
4. **`encryption_at_rest == "SSE-KMS-CMK"`를 기대하지 말 것.** 나오지 않는다.
   **룰 C-06은 KMS 수집기가 생기기 전까지 사용 불가.**
5. **`exposure_path`가 `OUT_OF_SCOPE`인 것을 "외부 미노출"로 읽지 말 것.** `갱신`
   값이 있으면(`Direct`/`ALB`/`CloudFront`/`APIGateway`) 그 경로로 노출된 것이 확정이다.
   없으면 **우리가 보는 경로에서 안 나왔다**는 뜻이지 미노출이라는 뜻이 아니다.
6. **`asset_count == 0`을 볼 때 `collector_exists`를 함께 볼 것.**
   "확인했더니 없다"와 "확인하지 않았다"는 다르다.
7. **`parent_id`가 비어 있다고 고아 자산으로 읽지 말 것.** `신설`
   `NOT_CONFIGURED`는 원본이 실제로 없는 것(미연결 볼륨·삭제된 원본),
   `OUT_OF_SCOPE`는 남의 계정 소유라 수집 범위 밖인 것, `COLLECT_ERROR`는 조회 실패다.
   등급 상속(결함사례 5)은 값이 있는 자산에만 적용할 수 있다.
8. **`os`로 시트를 배정하지 말 것.** `신설` SSM 미도입이라 항상 `OUT_OF_SCOPE`다.
   Linux/Windows 구분은 `platform`을 쓴다.

---

## F. 미해결 과제

| 과제 | 영향 |
|---|---|
| **태그 미입력 14,000여 건** | **가장 큰 병목.** 도구가 아니라 조직이 푸는 문제다. 규약은 `docs/tag-standard.md`에 있고, 태그를 달면 다음 실행부터 자동으로 채워진다 |
| 수기 시트 역방향 병합 | 담당자가 채운 내용이 `assets.json`에 합쳐지지 않는다. 자산관리대장이 완성되려면 필요 |
| SSM 수집기 | `os`·`version`이 항상 `OUT_OF_SCOPE`. 안내서가 요구하는 항목이고 **소프트웨어 유형 0건의 원인**이다. moto가 SSM Inventory를 구현하지 않아 실계정에서만 검증 가능 |
| KMS 수집기 | `SSE-KMS-CMK` 판별 불가 → 룰 C-06 사용 불가 |
| 노출 경로 나머지 | Route 53 별칭·Global Accelerator·VPC 엔드포인트는 아직 안 본다. `exposure_path`가 `OUT_OF_SCOPE`인 자산이 여기 해당한다 |
| 설비·시설 | CSP 책임영역이라 **수기가 정답**이다. 수집기를 만들 대상이 아니다 |
| `created_at` (네트워크장비) | VPC·서브넷·보안그룹·EIP는 describe 응답에 생성 시각이 없다. Config·CloudTrail 수집 필요 |
| `backup_exists` | moto가 `list_protected_resources`를 구현하지 않아 데모에서 항상 `COLLECT_ERROR`. 코드 문제가 아니며 실계정에서만 검증된다 |
| 멀티계정 | 코드는 계정 루프로 열어뒀으나 AssumeRole 미구현 |
| CloudTrail 생성자 추론 | 관리주체 후보 제시(`created_by`) 미구현 |
| `tags_raw` 마스킹 | 반출 시 마스킹 옵션이 없다 |

### 해결된 과제 `갱신`

| 과제 | 어떻게 해결됐나 |
|---|---|
| ELB·CloudFront 수집기 | `collector/services/frontend.py` 신설. `exposure_path`가 2패스 조인으로 확정된다 |
| 정보시스템·PC 수집기 | 정보시스템은 frontend, PC는 WorkSpaces(`inventory.py`)가 담당. **0건 유형 5종 → 3종** |

---

## G. 데이터 계약 v0.1 대조

착수 전 제안서의 **데이터 계약 v0.1** 표(자산 1건 = JSON 1객체)와 실제 `assets.json`을
필드 단위로 대조한 결과다. **18개 중 13개 일치, 5개가 다르다.**

### ① 이름·모양만 다름 — 실질은 동등

| 계약 v0.1 | 실제 | 판단 |
|---|---|---|
| `service` (EC2 / RDS / S3 / ECR / AMI) | `resource_type` (`ec2_instance` / `s3_bucket`) | **상위호환.** 같은 EC2라도 인스턴스·볼륨·스냅샷은 자산유형이 다르므로 서비스 수준으로는 부족했다 |
| `location` obj (region, az, vpc_id, subnet_id) | 네 개를 **평면 필드**로 | "레코드 모양 = 평면" 확정과 일관. 네 값 모두 있다 |

### ② 담당 B 영역이라 만들지 않음

`grade_proposed` / `grade_confirmed`가 자산 레코드에 **없다.**
`docs/design.md` §5.5의 3단 분리에서 둘은 **GradedAsset(B의 산출물)** 필드다.

```
RawAsset  →  NormalizedAsset (A)        →  GradedAsset (B)
                공통필드 + asset_type         + grade_proposed
                + infra_facts + 사유          + grade_confirmed(항상 null)
```

**A 산출물에 판정 필드가 없는 것이 역할 경계다.** 오해를 막기 위해
`meta.graded_by`에 이 사실을 문자열로 명시했다.

```json
"graded_by": "담당 B — grade_proposed / grade_confirmed는 이 파일에 없다"
```

### ③ 누락이었던 것 — `source_api` (해결됨)

계약 v0.1은 자산마다 `source_api`를 **"증적 추적용"**으로 요구했는데,
초기 구현은 원본 덤프의 `meta.source_api`에만 두어 **`assets.json`만 받은 B가
"이 자산이 어느 API 응답에서 나왔는가"를 되짚을 수 없었다.**

자산 2천여 건에 같은 배열을 반복하면 파일이 불어나므로,
**`meta.source_api_by_resource` 매핑표를 한 번만 싣는 방식**으로 채웠다.

```json
"source_api_by_resource": {
  "ec2_instance": {
    "service": "ec2",
    "raw_path": "describe_instances.Reservations[].Instances[]",
    "apis": ["describe_instances"],
    "iam_actions": ["ec2:DescribeInstances", "..."]
  },
  "s3_bucket": {
    "service": "s3",
    "raw_path": "buckets (map)",
    "apis": ["list_buckets", "get_bucket_encryption", "get_bucket_versioning", "..."],
    "iam_actions": ["s3:ListAllMyBuckets", "..."]
  }
}
```

| 키 | 의미 |
|---|---|
| `service` | 열어볼 원본 덤프 파일 이름 (`raw/{run_id}/{계정}/{리전}/{service}.json`) |
| `raw_path` | 그 파일의 `data` 안에서 자산을 꺼낸 위치 |
| `apis` | 이 자산을 만드는 데 쓰인 원본 API 이름들 |
| `iam_actions` | 필요한 IAM 액션. **수집기(서비스) 단위이며 리소스 단위로 좁혀져 있지 않다** |

> `iterate`가 map 형태인 리소스(`detectors`·`keys`)는 그 키가 수집기가 만든 이름이라
> yaml에서 역산되지 않는다. `extract_map.yaml`의 `source_apis:`로 직접 선언한다.
> 모든 리소스가 `apis`를 밝히는지는
> `tests/test_extract.py::test_모든_리소스가_출처_API를_밝힌다`가 검증한다.

### 계약 v0.1에 없던 확장

| 추가 | 왜 |
|---|---|
| 모든 필드의 `{value, reason, hint}` 형태 | v0.1은 `str/null`이었다. **null의 이유를 모르면 등급을 못 매긴다** |
| 사유 8종 | 위와 같은 이유 |
| `parent_id` / `relation_type` | 사본→원본 등급 상속(`결함사례 5`) |
| `manual_required` / `manual_todo` | "담당자 부담 경감" — 도구의 두 번째 목적 |
| `meta` 블록 전체 | 계약 버전·사유 코드·수집 실패 기록 |
| 계약 필드 39종 | v0.1의 13개에서 확장 ([B-4](#b-4-자산-레코드--계약-필드-39종)) |

---

## H. 설계서 구조와 달라진 지점

`docs/design.md` §5.2가 착수 전 폴더 구조를 그려뒀지만, **구현 결과는 네 군데가 다르다.**
설계서 원문은 당초 의도를 남기기 위해 그대로 두고, 여기에 무엇이 왜 바뀌었는지 적는다.

### 실제 구조

```
AWS-ISMS-P/
├── config/                    ← 사람이 고치는 설정 (코드 아님)
│   ├── extract_map.yaml          원본 경로 → 계약 필드. 리소스 25종
│   ├── isms_asset_types.yaml     자산유형 11종 + 유형별 요구 항목
│   └── manual_items.yaml         수집 불가 항목 + 담당자 작업 지시
│
├── collector/                 ← 수집 + 추출 (담당 A 전체)
│   ├── __main__.py               CLI: collect / extract / manual-sheet / iam-policy
│   ├── session.py                계정·리전 순회, 페이지네이션, 재시도
│   ├── safe_call.py              예외·빈 응답을 상태 표지로 바꾸는 래퍼
│   ├── registry.py               services/ 자동 등록 + 최소권한 액션 수집
│   ├── base.py                   ServiceCollector 추상 클래스
│   ├── collect.py                수집 오케스트레이션
│   ├── dump.py                   원본 덤프 저장 + manifest
│   ├── reasons.py                사유 8종 정의
│   ├── extract.py                원본 → 자산유형별 JSON (2패스)
│   ├── manual.py                 미충족 요구항목 + 담당자 작업 지시
│   └── services/                 ← 여기에 파일 추가 = 기능 확장
│       ├── ec2.py                   서버·볼륨·스냅샷·네트워크·SG
│       ├── rds.py                   데이터(DBMS)
│       ├── s3.py                    정보(전자적)
│       ├── backup.py                백업 보호 여부
│       ├── security.py              WAF·GuardDuty·KMS·CloudTrail 등
│       ├── frontend.py              ALB·API Gateway + CloudFront(전역)
│       └── inventory.py             ECR 리포지토리 · WorkSpaces
│
├── reporter/
│   └── manual_sheet.py           수기 입력 템플릿 xlsx
│
├── snapshots/                 ← .gitignore
│   ├── raw/{run_id}/{계정}/{리전}/{서비스}.json
│   └── normalized/{run_id}/assets.json
│
├── output/                    ← .gitignore
├── docs/tag-standard.md          조직이 지켜야 할 태그 규약 (담당자용)
├── demo.py  demo_env.py          전체 흐름 시연
└── tests/                        86개
```

### 변경 ① `advisor/`를 만들지 않음 — 합의된 변경

`CLAUDE.md` 금지 사항이 *"`advisor/`·`reporter/`의 판정 로직을 만들지 않는다. 담당 B 영역이다"* 이다.
설계서는 정규화·분류·관계 해소를 `advisor/`에 뒀지만, **그건 판정이 아니라 사실 가공**이므로
A가 맡는 것으로 착수 전에 확정했다.

| 설계 | 현재 | 판단 |
|---|---|---|
| `advisor/normalize.py` | `collector/extract.py` | A가 정규화까지 하고 B는 정규화된 것부터 시작 |
| `advisor/classify.py` | `config/extract_map.yaml`의 `asset_type:` | 분류는 코드가 아니라 선언으로 |
| `advisor/relation.py` | `collector/extract.py` 2패스 | **조인은 사실이지 판정이 아니다** |
| `advisor/grade.py` `gap.py` `diff.py` | 만들지 않음 | 담당 B 영역 |

### 변경 ② `config/` 5개 → 3개 — 구현 중 판단

없어진 게 아니라 다른 파일에 흡수됐다.

| 설계서 | 현재 위치 |
|---|---|
| `asset_types.yaml` | `isms_asset_types.yaml` (이름만 변경) |
| `service_map.yaml` | `extract_map.yaml`의 리소스별 `asset_type:` |
| `field_profile.yaml` | `isms_asset_types.yaml`의 `required_items` + `not_applicable` |
| `tag_standard.yaml` | `extract_map.yaml`의 `{tag: "OwnerDept"}` 선언 + `docs/field-mapping.md` §2.1 |
| `grade_rules.yaml` | **만들지 않음** — 등급 룰은 담당 B 영역 |
| — | **`extract_map.yaml` (신규)** — 설계서에 없던 파일 |
| — | **`manual_items.yaml` (신규)** — 설계서에 없던 파일 |

**이유** — "B가 필드 추가를 요청하면 yaml 한 줄 + 재추출로 끝난다"가 이 구조의 핵심 이점인데,
자산유형·필드·태그가 세 파일에 흩어져 있으면 한 줄로 안 끝난다.
`extract_map.yaml`의 리소스 블록 하나에 *어느 자산유형인가 / 어느 필드를 뽑나 / 어느 태그를 보나*
가 모여 있어야 한 곳만 고치면 된다.

> ⚠ **이건 합의한 게 아니라 구현하며 정한 것이다.** 파일을 다시 쪼갤 거면
> "한 곳만 고치면 되는가"라는 원칙부터 다시 정해야 한다.

### 변경 ③ `snapshots/` 경로 — 합의된 변경

```
설계:  snapshots/{run_id}/{계정}/{리전}.json
현재:  snapshots/raw/{run_id}/{계정}/{리전}/{서비스}.json
       snapshots/normalized/{run_id}/assets.json
```

`raw`/`normalized`를 나누고 서비스별로 파일을 쪼갰다.
한 리전 파일에 전 서비스를 담으면 EC2 하나 때문에 파일 전체를 다시 읽어야 한다.

### 변경 ④ `main.py` 없음 — 구현 중 판단

```
설계:  main.py                    ← 진입점
현재:  collector/__main__.py      python -m collector {collect|extract|manual-sheet|iam-policy}
       demo.py                    전체 흐름 한 번에 (S4에서 추가)
```

작업명세서가 CLI를 `python -m collector collect`로 지정했으므로 그쪽을 따랐다.
`reporter/iam_policy.py`도 만들지 않았다 — `registry.all_required_actions()`와 CLI 한 줄이라
파일을 따로 둘 만큼이 아니었다.

### 변경 ⑤ `services/` 12개 → 9개 — 범위 축소 `갱신`

```
설계:  ec2 rds dynamodb s3 efs backup elbv2 cloudfront ssm ecr security workspaces
현재:  ec2 rds s3 backup security frontend(elbv2+apigateway) cloudfront ecr workspaces
```

파일은 7개다 — `frontend.py`가 elbv2·API Gateway를 묶고 CloudFront 수집기를 함께 담으며
(전역 서비스라 클래스는 분리), `inventory.py`가 ECR·WorkSpaces를 담는다.
설계에 없던 `apigateway`가 추가됐다.

**미구현 3개가 산출물에 그대로 드러난다.** 숨기지 않는다.

| 빠진 수집기 | 산출물에 나타나는 형태 |
|---|---|
| `ssm` | `os`·`version` → `OUT_OF_SCOPE`, **소프트웨어 유형 `collector_exists: false`** |
| `dynamodb` `efs` | 데이터·정보 유형 커버리지 축소 |
| (KMS 상세) | `encryption_at_rest`가 `SSE-KMS`까지만 → **룰 C-06 사용 불가** |

### 설계서에 없던 파일

| 파일 | 왜 생겼나 |
|---|---|
| `collector/reasons.py` | 사유 8종을 한 곳에 정의. 설계서는 4종만 상정했다 |
| `collector/manual.py` | "담당자 부담 경감"이 도구의 두 번째 목적인데 설계서에 담당 모듈이 없었다 |
| `collector/collect.py` `dump.py` | `session.py`가 순회·저장까지 다 하면 너무 커진다 |
| `demo.py` `demo_env.py` | S4에서 추가 |
| `docs/aws-facts.md` | **설계서와 실물이 다른 지점을 실측해 기록.** moto와 실계정 차이 포함 |
| `docs/handover.md` | 이 문서 |

### 요약

| # | 지점 | 성격 |
|---|---|---|
| ① | `advisor/` 미생성, 정규화·조인을 `collector/`로 | 착수 전 합의 |
| ③ | `snapshots/raw` · `normalized` 분리 | 착수 전 합의 |
| ② | `config/` 5개 → 3개 | **구현 중 판단 — 재논의 가능** |
| ④ | `main.py` → `python -m collector` | 구현 중 판단 (작업명세서 근거) |
| ⑤ | `services/` 12개 → 9개 | 프로토타입 범위 축소 (elbv2·cloudfront·ecr·workspaces·apigateway 추가) |

---

## 참조

| 문서 | 내용 |
|---|---|
| `README.md` | 실행 방법, 프로토타입 한계 |
| `CLAUDE.md` | 작업 규칙, 문서 간 충돌 확정 사항 |
| `docs/design.md` | 자산유형 정의, 호출할 boto3 함수 목록 |
| `docs/field-mapping.md` | 대장 필드 ↔ 응답 경로, **등급 룰 카탈로그(B용)** |
| `docs/aws-facts.md` | **실측 기록.** moto와 실계정이 다른 지점 |
