# ISMS-P 1.2.1 대응 AWS 자산 수집기 (프로토타입)

AWS 계정의 정보자산을 boto3로 수집해, **ISMS-P 인증기준 1.2.1(정보자산 식별)** 대응
자산관리대장의 재료가 될 JSON을 만든다.

화이트햇 스쿨 4기 팀 프로젝트. 2인 분업이며 **이 저장소는 수집 파트(A)** 다.
판정·등급·리포트 파트(B)는 별도로 만들어진다.

```bash
python demo.py        # 환경 생성 → collect → extract → 결과 출력
```

---

## 1. 어느 항목에 대응하는가

**인증기준 1.2.1** — 조직의 업무특성에 따라 정보자산 분류기준을 수립하여 관리체계 범위 내
모든 정보자산을 식별·분류하고, 중요도를 산정한 후 그 목록을 최신으로 관리하여야 한다.

| 세부점검항목 | 대응 |
|---|---|
| ① 분류기준을 수립하고 범위 내 모든 자산을 식별하여 목록으로 관리하는가 | **이 저장소 (수집기)** |
| ② 중요도를 결정하고 보안등급을 부여하는가 | 등급 엔진 (담당 B) |
| ③ 정기적으로 조사하여 목록을 최신으로 유지하는가 | diff (담당 B) |

안내서는 클라우드에 대해 별도로 요구한다 — *"클라우드 서비스의 특성을 반영한 분류기준
(예를 들어, 가상서버, 오브젝트 스토리지 등)을 마련하고 이에 따라 클라우드 자산을 식별·관리"*.
온프레미스 분류표를 그대로 쓰지 말라는 명시적 요구다. 그래서 안내서 10종에
**가상자원**(AMI·컨테이너 이미지·스냅샷)을 더해 11종으로 다룬다.

---

## 2. 이 도구의 두 가지 목적

**① 자동화** — API로 얻을 수 있는 건 전부 자동 수집한다.

**② 담당자 부담 경감** — 자동화할 수 없는 부분을 "빈 칸"으로 남기지 않는다.
**누가 / 왜 / 어떻게** 채워야 하는지까지 알려준다.

②를 빼면 이 도구는 그냥 리소스 덤프 도구가 된다. 결함사례 1(출력물 보안·DRM·USB 통제 누락)과
결함사례 4(위탁 IT 서비스 누락)는 **AWS API로 절대 해결되지 않는다.**
그 영역이야말로 안내가 필요한 곳이다.

---

## 3. 왜 collect와 extract를 나눴는가

```
① collect   AWS 응답을 손대지 않고 그대로 덤프
            snapshots/raw/{run_id}/{account}/{region}/{service}.json
               ↓ (AWS 접속 없음)
② extract   config/extract_map.yaml에 선언된 필드만 뽑아
            ISMS-P 자산유형별 JSON 생성
            snapshots/normalized/{run_id}/assets.json
               ↓
            담당 B에게 인계
```

수집 시점에 필드를 골라 버리면, 나중에 B가 "이 필드도 필요하다"고 할 때
**AWS를 다시 호출해야 한다.** 자격증명이 필요하고, 전 리전 순회는 수 분이 걸리며,
그 사이 리소스가 바뀌어 비교 기준선이 흔들린다.

원본이 있으면 재추출이 초 단위로 끝나고 자격증명도 필요 없다.
**그리고 원본 덤프 자체가 증적이다** — "이 시점에 AWS가 이렇게 응답했다"는 기록이 있어야
대장의 각 칸이 어디서 왔는지 추적된다.

필드를 추가할 때 코드는 고치지 않는다. `config/extract_map.yaml`에 한 줄 더하고 재추출하면 된다.
(`tests/test_extract.py::test_yaml에_필드를_추가하면_코드_수정_없이_반영된다`)

---

## 4. 값이 없을 때의 사유 8종 — 이 프로젝트의 핵심

값이 없다는 사실만 넘기면 B가 판단할 수 없다. **왜 없는지를 함께 실어야 한다.**

| reason | 의미 | 갭 리포트 |
|---|---|---|
| `null` | 정상 수집됨 | — |
| `TAG_ABSENT` | 태그 미입력. 담당자가 태그 달면 해결 | 출력 |
| `NOT_CONFIGURED` | AWS 설정이 없음. 사실 자체가 정보이고 등급 근거가 된다 | 출력 |
| `API_NULL` | API가 값을 안 줌 | 출력 |
| `NOT_APPLICABLE` | 이 자산유형에 개념 자체가 없음 (S3 버킷의 IP주소) | **출력 안 함** |
| `PERMISSION_DENIED` | 권한 부족으로 조회 실패 | **별도 출력** |
| `COLLECT_ERROR` | 조회 자체가 실패 (서비스 없는 리전·스로틀링) | **별도 출력** |
| `OUT_OF_SCOPE` | 개념은 있는데 이 도구가 아직 그 API를 안 부른다 | **별도 출력** |

```json
"owner_dept":    { "value": null, "reason": "TAG_ABSENT",
                   "hint": "OwnerDept 태그를 달면 다음 실행부터 자동 수집됩니다" }
"encryption":    { "value": null, "reason": "NOT_CONFIGURED" }
"ip_private":    { "value": null, "reason": "NOT_APPLICABLE" }
"exposure_path": { "value": null, "reason": "OUT_OF_SCOPE",
                   "hint": "ELB·CloudFront 수집기가 있어야 확정됩니다" }
```

### 마지막 세 개를 왜 따로 두는가 — **"모른다"와 "없다"는 다르다**

- 권한이 없어서 암호화 설정을 못 읽은 것을 "미암호화"로 기록하면 **기밀성 등급이 통째로 틀린다.**
- EC2에 공인 IP가 없다고 `exposure_path`를 `"None"`으로 단정하면 **ALB 뒤에 있는 자산을
  "외부 미노출"로 규정**하게 되고, 등급 룰 C-03이 무너진다.
- 조회에 실패한 것을 "자산 없음"으로 세면 자산 목록 전체가 거짓이 된다.

`NOT_APPLICABLE`은 반대 방향이다. 이게 없으면 갭 리포트가
"S3 버킷의 IP주소 미확인" 같은 행으로 채워져 리포트 전체의 신뢰가 무너진다.

---

## 5. 담당 B에게 넘기는 것

| 파일 | 내용 |
|---|---|
| `snapshots/normalized/{run_id}/assets.json` | **인수인계물** |
| `config/isms_asset_types.yaml` | 자산유형별 요구 항목 |
| `config/manual_items.yaml` | 수집 불가 항목 정의 |

### assets.json 구조

```json
{
  "meta": {
    "contract_version": "1.0",
    "run_id": "run-20260801-1325",
    "account_id": "123456789012",
    "regions": ["ap-northeast-2", "us-east-1"],
    "reason_codes": [...],
    "reason_codes_not_absence": ["PERMISSION_DENIED", "COLLECT_ERROR", "OUT_OF_SCOPE"],
    "infra_fact_keys": [...],
    "total_assets": 42,
    "collection_issues": []
  },
  "asset_types": {
    "서버": {
      "isms_required_items": [...],
      "aws_collectable": ["ec2_instance"],
      "collector_exists": true,
      "asset_count": 7,
      "assets": [ ... ],
      "manual_required": [ ... ]
    },
    "보안시스템": { "asset_count": 0, "assets": [], ... },
    "설비": { "asset_count": 0, "assets": [], ... }
  },
  "manual_todo": {
    "summary": { "total": 22, "auto_after_fix": 5, "permanent": 17 },
    "by_owner": { "각 자산 운영 부서": [ ... ] },
    "blocked": [ ... ]
  }
}
```

**자산유형 11종 키는 0건이어도 항상 있다.** 키가 없으면 "수집기가 빠뜨린 것"과
"실제로 0건인 것"을 구분할 수 없고, 0건이라는 사실 자체가 결함사례 1·4의 리포트 대상이다.

### 자산 레코드

```json
{
  "asset_id": "arn:aws:ec2:ap-northeast-2:123456789012:instance/i-0abc",
  "asset_type": "서버",
  "resource_type": "ec2_instance",
  "region": "ap-northeast-2",
  "asset_name":  { "value": "prd-web-01", "reason": null },
  "owner_dept":  { "value": null, "reason": "TAG_ABSENT", "hint": "..." },
  "parent_id":   { "value": null, "reason": "NOT_APPLICABLE" },
  "infra_facts": {
    "open_sg_rule":   { "value": true, "reason": null },
    "open_sg_detail": { "value": ["sg-0abc:22/tcp"], "reason": null },
    "backup_exists":  { "value": null, "reason": "COLLECT_ERROR", "hint": "..." }
  },
  "tags_raw": { "Name": "prd-web-01", "OwnerDept": "인프라운영팀" }
}
```

`infra_facts` 17키는 등급 룰(`docs/field-mapping.md` §6)의 입력값이다.
**사실 수집일 뿐 판정이 아니다.** 등급을 매기는 건 B다.

### B가 필드를 더 원할 때

AWS 재호출 없이 처리된다. 이 형식으로 요청하면 된다.

```
extract_map.yaml 추가 요청
자산유형: 데이터(DBMS)
필요 필드: deletion_protection
원본 경로: rds/describe_db_instances → DBInstances[].DeletionProtection
용도: 가용성 룰 (운영 자산에 삭제 방지 미설정 시 가중)
```

### B가 반드시 알아야 할 것

1. **`PERMISSION_DENIED` / `COLLECT_ERROR` / `OUT_OF_SCOPE`를 자산 부재로 해석하지 말 것.**
   `meta.reason_codes_not_absence`에 명시돼 있다.
2. **`NOT_APPLICABLE`은 갭 리포트에서 제외할 것.**
3. **`encryption_at_rest`에 `SSE-KMS-CMK`는 나오지 않는다.** 고객관리형 키인지
   AWS 관리형인지는 `kms:DescribeKey`의 `KeyManager`를 봐야 알 수 있고 아직 안 부른다.
   `SSE-KMS`까지만 적는다. **룰 C-06은 KMS 수집기가 생기기 전까지 쓸 수 없다.**

---

## 6. 실행

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
python demo.py
```

| 명령 | 하는 일 | AWS 접속 |
|---|---|---|
| `python demo.py` | moto 환경 생성 → collect → extract → 산출물 | **없음** |
| `python -m collector collect` | AWS 응답 덤프 | **있음** |
| `python -m collector extract --run <run_id>` | 원본에서 재추출 | 없음 |
| `python -m collector manual-sheet` | 수기 입력 템플릿 xlsx | 없음 |
| `python -m collector iam-policy` | 최소권한 정책 JSON | 없음 |

```bash
pytest        # 84개
```

### demo.py 옵션

| 옵션 | 의미 |
|---|---|
| `--all-regions` | 전 리전 순회 (기본은 2개 리전) |
| `--raw` | moto 산출물을 거르지 않고 그대로 |
| `--keep` | 이전 `snapshots/`·`output/`을 지우지 않는다 |

> **`collect`만 실제 AWS에 접속한다.** 프로토타입 단계에서는 moto로만 검증하며,
> 실계정을 쓸 때도 장기 액세스 키가 아니라 `aws sso login` 단기 자격증명을 쓴다.
> `demo.py`는 자격증명을 가짜로 덮어쓰고, 수집된 계정이 moto 목 계정이 아니면 중단한다.

---

## 7. 데모에서 보이는 것

```
[0건 — 수집했으나 자산이 없음. 통제 부재 자체가 결함 소지]
  보안시스템        0건  ← 침입차단시스템, 침입탐지시스템, 침입방지시스템 미확인

[0건 — 수집기가 없어 '확인하지 않음'. 자산이 없다는 뜻이 아니다]
  PC               0건   (수집기 필요)
  설비             0건   (수기 등재 대상)

[태그만 달면 자동화됨]
  · 관리부서·관리실무자·관리책임자    38건 (90%)  → 각 자산 운영 부서
  · 자산명 · 호스트 명칭          29건 (69%)  → 각 자산 운영 부서

[수기 등재 필요 — 영구]
  · 내부정보 유출통제 시스템        현재 0건 등재  → 정보보안팀

[권한 부족·조회 실패 — 자산 부재 아님]
  · infra_facts.backup_exists   24건  ← COLLECT_ERROR

[리전별 분포 — 미사용 리전 방치가 자산 누락 1순위]
  ap-northeast-2   31건
  us-east-1        11건
```

**세 종류의 "0건"이 다르다는 것이 이 화면의 요점이다.**

| 표시 | 뜻 | 심사에서 |
|---|---|---|
| 수집했으나 0건 | 확인했더니 정말 없다 | 통제 부재. 결함 소지 |
| 수집기가 없어 0건 | 확인하지 않았다 | 아무 말도 못 한다 |
| 조회 실패 | 못 읽었다 | 자산 부재가 아니다 |

"확인했더니 없다"와 "확인하지 않았다"를 같은 0으로 적으면 대장이 거짓이 된다.

---

## 8. 프로토타입의 한계

| 한계 | 영향 |
|---|---|
| 수집 서비스가 EC2·RDS·S3·Backup·보안시스템 5개 | 정보시스템·소프트웨어·PC 유형은 수집기가 없어 0건 |
| 단일 계정만 수집 | Organizations 멀티계정은 코드 구조만 열어둠 |
| `SSE-KMS-CMK` 판별 불가 | 등급 룰 C-06 사용 불가 |
| `exposure_path` 확정 불가 | ELB·CloudFront 수집기 필요 |
| moto로만 검증 | 실계정 응답과 다른 지점은 `docs/aws-facts.md`에 전부 기록 |
| 수기 시트를 다시 읽어들이지 않음 | 담당자가 채운 내용이 assets.json에 합쳐지지 않는다 |

**moto와 실계정의 차이는 추측하지 않고 실측해서 기록했다.** `docs/aws-facts.md` 참조.
특히 moto는 `describe_snapshots(OwnerIds=['self'])` 필터를 무시해 타 계정 스냅샷 2337건을
돌려준다. `demo.py`가 이를 걸러 보여주되 **몇 건을 왜 뺐는지 화면에 표시하고,
원본 `assets.json`에는 그대로 남긴다.**

---

## 9. 하지 않는 것

- **쓰기 API를 호출하지 않는다.** `create_*` / `delete_*` / `modify_*` / `put_*` 등은 존재하지 않는다.
  각 수집기가 선언한 IAM 액션에 쓰기가 섞이면 `python -m collector iam-policy`가 실패한다.
- **개인정보를 자동 탐지하지 않는다.** DB 접속·스키마 스캔·객체 내용 분석은 범위 밖이고,
  태그(`HandlePI`, `PIItems`)로 갈음한다.
- **적합·부적합을 판정하지 않는다.** "미확인 / 미입력" 사실만 제시한다. 등급 확정도 사람 몫이다.

### 개인정보 취급 주의

`snapshots/`의 원본 덤프는 정규화 결과보다 민감하다. 필드를 안 버렸으므로
**태그 값의 담당자 이메일·전화번호가 그대로 들어 있다.**
`.gitignore`에 `snapshots/`·`output/`을 등록했다.
개인정보 관리 도구가 스스로 개인정보 파일을 만드는 상황을 피한다.

---

## 10. 문서

| 파일 | 내용 |
|---|---|
| `CLAUDE.md` | 작업 규칙, 배경 지식, 확정 사항 |
| `docs/contract.md` | **담당 B용 데이터 계약.** assets.json 필드 명세 |
| `docs/demo-guide.md` | 데모 진행 가이드 |
| `docs/design.md` | 자산유형 정의, AWS 서비스 매핑, 호출할 boto3 함수 목록 |
| `docs/field-mapping.md` | 대장 필드 ↔ 응답 경로, 태그 표준, `infra_facts` 17키, 등급 룰 카탈로그 |
| `docs/aws-facts.md` | **실측 확인 기록.** 설계서와 실물이 다른 지점 |
| `docs/prompt-A.md` | 세션별 작업 명세서 |

---

*공개된 공적 자료(KISA 안내서·법령·AWS 공식 문서)만을 근거로 작성했다.
실제 인증심사 적용 전 KISA 최신 안내서 및 심사기관 협의가 필요하다.*
