# 데이터 계약 v1.0 — 수집기(A) → 판정(B)

수집기가 넘기는 JSON의 명세. **이 문서 하나로 코드를 짤 수 있게** 필요한 것만 적었다.
설계 배경·필드별 출처는 [`handover.md`](handover.md).

---

## 1. 받는 것

| 파일 | 내용 |
|---|---|
| `snapshots/normalized/{run_id}/assets.json` | **자산 목록.** 이 문서가 설명하는 것 |
| `config/isms_asset_types.yaml` | 자산유형별 ISMS-P 요구 항목 |
| `config/manual_items.yaml` | 수집 불가 항목 정의 |

---

## 2. 전체 구조

```json
{
  "meta": { "contract_version": "1.0", "run_id": "...", "account_id": "...", ... },
  "asset_types": {
    "서버":        { "asset_count": 7, "assets": [ ... ], "manual_required": [ ... ] },
    "데이터(DBMS)": { ... },
    "보안시스템":   { "asset_count": 0, "assets": [] },
    ...  // 자산유형 11종. 0건이어도 키는 항상 있다
  },
  "manual_todo": { "summary": {...}, "by_owner": {...}, "blocked": [...] }
}
```

**자산유형 11종** — 서버 / 데이터(DBMS) / 정보시스템(응용프로그램) / 소프트웨어 /
네트워크장비 / 보안시스템 / PC / 정보 / 설비 / 시설 / 가상자원

`meta`에서 챙길 것 — `reason_codes_not_absence`(자산 부재로 읽으면 안 되는 사유),
`collection_issues`(조회 실패한 리전·리소스), `source_api_by_resource`(자산→원본 API 추적),
`graded_by`(등급 필드는 여기 없다는 명시), `contract_version`.

---

## 3. 자산 레코드

```json
{
  "asset_id": "arn:aws:ec2:ap-northeast-2:123456789012:instance/i-0abc",
  "asset_type": "서버",
  "resource_type": "ec2_instance",
  "account_id": "123456789012",
  "region": "ap-northeast-2",
  "run_id": "run-20260803-0615",
  "collected_at": "2026-08-03T06:15:10+00:00",

  "asset_name":  { "value": "prd-web-01", "reason": null },
  "owner_dept":  { "value": null, "reason": "TAG_ABSENT",
                   "hint": "OwnerDept 태그를 달면 다음 실행부터 자동 수집됩니다" },

  "infra_facts": { "open_sg_rule": { "value": true, "reason": null }, ... },
  "tags_raw":    { "Name": "prd-web-01", "OwnerDept": "인프라운영팀" }
}
```

- 위 **7개와 `tags_raw`는 평범한 값**(항상 채워짐). `infra_facts`는 6절의 중첩 객체다.
  그 셋을 뺀 나머지는 전부 `{value, reason}` 쌍이다.
- `reason`이 `null`이면 정상 수집. 아니면 `value`는 `null`이고 왜 없는지가 `reason`에 들어간다.
- `hint`는 **담당자가 어떻게 하면 채워지는지.** 있을 때만 붙는다.
- **모든 자산이 같은 키를 갖는다.** 그 자산유형에 없는 개념은 `NOT_APPLICABLE`로 채워진다.
  키 존재 여부를 확인할 필요가 없다.

### 계약 필드 39종

| 분류 | 필드 |
|---|---|
| 식별 | `asset_name` `serial_no` `model` `version` `engine` |
| 관리주체 | `owner_dept` `owner_manager` `owner_responsible` `service_name` |
| 분류·범위 | `usage` `environment` `in_scope` `scope_reason` |
| 개인정보 | `has_personal_info` `personal_info_items` `data_source` `data_classification` |
| 위치 | `region`* `az` `vpc_id` `subnet_id` `cidr` |
| 접속 | `ip_private` `ip_public` `endpoint` `port` |
| 상태 | `lifecycle_state` `created_at` `expires_at` `os` `platform` |
| 관계 | `parent_id` `relation_type` `attached_to` `image_id` |
| 기타 | `size_gb` `tenancy` `virtualization` `is_default` `owner_account` |

\* `region`은 평범한 값이다. 위 표에서 이것만 빼면 `{value, reason}` 필드가 39종이다.

### `data_classification` — 신규 필드 (기밀성 룰 복구용)

`DataClass` 태그(`public` / `internal` / `confidential`). **정보를 담는 8개 리소스에만 선언**했고
네트워크장비·보안시스템은 `NOT_APPLICABLE`이다.

`has_personal_info`와 **다른 축**이다. 합치면 "내부용이면서 개인정보를 포함하는 자산"을
표현할 수 없고 그런 자산이 개인정보 목록에서 빠진다.

이 값이 들어오면 별지 제3호의 **기밀성 접근 범위 3단계 룰을 되살릴 수 있다**
(`grade_rules.yaml` 머리말에 요청해 둔 필드). 태그 규약은 [`tag-standard.md`](tag-standard.md).

### `platform` — 신규 필드 (B 조치 필요)

`os`와 다르다. `platform`은 **OS 계열**(`Linux/UNIX` / `Windows`)이고
`describe_instances` 응답에 이미 있어 추가 호출 없이 뽑는다.
`os`는 정확한 배포판·버전이라 SSM이 필요해 **현재 항상 `OUT_OF_SCOPE`**다.

```
원본 경로: ec2/describe_instances → PlatformDetails || Platform
용도:      OS (Linux) / OS (Windows) 시트 배정
```

**시트 배정에는 `os`가 아니라 `platform`을 쓸 것.** 현재 `os_family()`가 `os`만 보는데
`os`는 값이 나오는 일이 없어서 서버가 전부 "OS 미확인" 시트로 간다.

단, moto는 `PlatformDetails`를 주지 않아 **데모에서는 `API_NULL`**이다.
실계정에서만 값이 오므로, 고쳐도 데모 화면은 그대로다.

---

## 4. 사유 코드 8종 — **가장 중요**

| reason | 뜻 | 갭 리포트 |
|---|---|---|
| `null` | 정상 수집됨 | — |
| `TAG_ABSENT` | 태그 미입력. **담당자가 태그 달면 해결** | 출력 |
| `NOT_CONFIGURED` | AWS 설정이 없음. **사실 자체가 등급 근거** | 출력 |
| `API_NULL` | API가 값을 안 줌 | 출력 |
| `NOT_APPLICABLE` | 이 자산유형에 **개념 자체가 없음** (S3 버킷의 IP) | **출력 안 함** |
| `PERMISSION_DENIED` | 권한 부족으로 조회 실패 | **별도 출력** |
| `COLLECT_ERROR` | 조회 자체가 실패 | **별도 출력** |
| `OUT_OF_SCOPE` | 개념은 있는데 **이 도구가 아직 그 API를 안 부름** | **별도 출력** |

### 핵심 원칙 — **"모른다"와 "없다"는 다르다**

마지막 셋(`PERMISSION_DENIED` `COLLECT_ERROR` `OUT_OF_SCOPE`)은 **전부 "모른다"이지
"없다"가 아니다.** `meta.reason_codes_not_absence`에 이 셋이 들어 있다.

권한이 없어 암호화를 못 읽은 걸 "미암호화"로 처리하면 기밀성 등급이 통째로 틀린다.

---

## 5. 절대 하면 안 되는 해석

1. `PERMISSION_DENIED` · `COLLECT_ERROR` · `OUT_OF_SCOPE`를 **자산 부재로 읽지 말 것**
2. `NOT_APPLICABLE`을 **갭으로 세지 말 것** — 개념이 없는 것이지 미확인이 아니다
3. `meta.collection_issues`가 비어 있지 않으면 **"0건"을 신뢰하지 말 것**
   (그 리전·리소스는 조회 자체가 실패했다)
4. `asset_count == 0`을 볼 때 **`collector_exists`를 함께 볼 것**
   `true`면 "확인했더니 없다"(결함 소지), `false`면 "확인하지 않았다"
5. `encryption_at_rest`가 `SSE-KMS`인 것을 **AWS 관리형 키로 읽지 말 것.**
   `SSE-KMS-CMK`/`SSE-KMS-AWS`로 갈린 것은 `KeyManager`를 확인한 결과이고,
   `SSE-KMS`로 남은 것은 **키를 못 가른 것**이다(키가 수집 범위 밖이거나 참조가 ARN이 아님).
   → **룰 C-06은 `SSE-KMS-CMK`인 자산에만 적용할 것.**
6. `exposure_path`가 `OUT_OF_SCOPE`인 것을 **"외부 미노출"로 읽지 말 것.**
   값이 있으면(`Direct`/`ALB`/`CloudFront`/`APIGateway`) 그 경로로 노출된 것이 확정이다.
   없으면 **우리가 보는 경로에서 안 나왔다는 뜻**이고 미노출이라는 뜻이 아니다
   (Route 53 별칭·Global Accelerator·VPC 엔드포인트는 아직 수집하지 않는다).
7. `parent_id`가 비어 있다고 **고아 자산으로 읽지 말 것.** 사유마다 뜻이 다르다

   | reason | 뜻 |
   |---|---|
   | `NOT_CONFIGURED` | 원본이 실제로 없다. 미연결 볼륨이거나 원본이 삭제된 스냅샷 |
   | `OUT_OF_SCOPE` | 남의 계정 소유라 원본이 수집 범위 밖. **부재가 아니라 미확인** |
   | `COLLECT_ERROR` | 원본 목록 조회가 실패했다. 재수집 대상 |

   스냅샷이 원본 볼륨보다 오래 사는 것은 정상이므로 `NOT_CONFIGURED`는 결함이 아니다.
   등급 상속(결함사례 5)은 `parent_id`에 값이 있는 자산에만 적용할 수 있다.

---

## 6. infra_facts — 등급 룰의 입력값

자산마다 **17키가 반드시 다 있다.** 형태는 계약 필드와 같은 `{value, reason}`.

| 키 | 타입 | 비고 |
|---|---|---|
| `backup_exists` `backup_source` | bool / str | `list_protected_resources` 기준. 스냅샷 개수가 아니다 |
| `snapshot_count` | int | |
| `pitr_enabled` `multi_az` `deletion_protection` | bool | RDS |
| `in_asg` | bool | |
| `public_exposed` | bool | |
| `exposure_path` | enum | `Direct`/`ALB`/`CloudFront`/`APIGateway`. **찾았을 때만 값이 붙는다** |
| `encryption_at_rest` | enum | `None` / `SSE-S3` / `SSE-ECR` / `SSE-KMS` / **`SSE-KMS-CMK`** / `SSE-KMS-AWS` |
| `encryption_in_transit` | bool | **현재 항상 `OUT_OF_SCOPE`** |
| `open_sg_rule` `open_sg_detail` | bool / list | `["sg-0abc:22/tcp"]` — 포트까지 |
| `versioning_enabled` `object_lock` `logging_enabled` | bool | S3 |
| `state` | str | |

> **`SSE-KMS-CMK`는 2패스가 `kms.describe_key`의 `KeyManager`를 조인해 붙인다.**
> 자원의 키 참조(EBS·RDS·스냅샷의 `KmsKeyId`, S3의 `KMSMasterKeyID`, ECR의 `kmsKey`)를
> 수집한 KMS 키 목록과 맞춰 `CUSTOMER`면 `SSE-KMS-CMK`, `AWS`면 `SSE-KMS-AWS`로 간다.
> **못 맞추면 `SSE-KMS` 그대로 둔다** — "KMS로 암호화됐다"는 여전히 참이고,
> 확인 못 한 것을 AWS 관리형으로 단정하면 C-06이 잘못 발동한다.
>
> **`SSE-ECR`은 ECR 리포지토리 전용이다.** ECR의 `AES256`은 ECR이 관리하는 키이고
> S3가 아니다. 서비스 관리 키라는 점은 `SSE-S3`와 같지만 출처가 다르므로 갈라 적는다.
> 등급 룰은 "암호화 없음"만 보므로 룰에는 영향이 없다.

**사실 수집일 뿐 판정이 아니다.** `encryption_at_rest: "None"`은 사실,
"기밀성 2점"은 판정이다. 판정은 B의 몫이다.

`grade_proposed` · `grade_confirmed`는 **이 파일에 없다.** B가 추가한다.

---

## 7. manual_todo — 담당자 작업 지시

AWS로 못 채우는 항목이 **담당·조치와 함께** 들어 있다. 리포트에 그대로 옮겨 쓸 수 있다.
`asset_types[유형].manual_required`(유형별)와 최상위 `manual_todo`(전체 요약) 두 곳.

```json
"by_owner": { "각 자산 운영 부서": [
  { "item_name": "관리부서·관리실무자·관리책임자",
    "action": "OwnerDept / OwnerManager / OwnerResponsible 태그 입력",
    "affected_assets": 38, "affected_ratio": "90%", "auto_after_fix": true }
]},
"blocked": [ { "field": "infra_facts.backup_exists", "reason": "COLLECT_ERROR",
               "affected_assets": 24 } ]
```

| 구분 | 뜻 |
|---|---|
| `auto_after_fix: true` | **태그만 달면 다음 실행부터 자동.** 한 번 투자하면 끝 |
| `auto_after_fix: false` | AWS 밖 자산이라 **영원히 수기** |
| `blocked` | 권한 부족·조회 실패. **작업 목록과 절대 섞지 말 것** |

---

## 8. 필드가 더 필요하면

**AWS 재호출 없이 처리된다.** 이 양식으로 요청하면 `extract_map.yaml` 한 줄 추가 +
재추출로 끝난다.

```
자산유형: 데이터(DBMS)
필요 필드: deletion_protection
원본 경로: rds/describe_db_instances → DBInstances[].DeletionProtection
용도: 가용성 룰 (운영 자산에 삭제 방지 미설정 시 가중)
```

자산이 어느 API에서 나왔는지는 `meta.source_api_by_resource`에서
`resource_type`으로 조회한다.
