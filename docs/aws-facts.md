# 실측 확인 기록 — 추측하지 않기 위한 근거

`docs/design.md`·`docs/field-mapping.md`는 공식 문서 기반이라 실물과 미묘하게 다를 수 있다.
**실제 응답이 진실이다.** 이 파일은 코드가 왜 그렇게 쓰였는지의 근거다.

확인 환경: boto3 1.43.62 / botocore 1.43.62 / moto 5.2.2 / Python 3.13.11 (2026-08-01)

---

## 1. 페이지네이터가 **없는** API — 직접 호출해야 한다

`can_paginate()`로 전수 확인한 결과다. 페이지네이터 없는 API에 `get_paginator()`를 부르면 예외가 난다.

| API | 페이지네이터 |
|---|---|
| `ec2.describe_addresses` | **없음** |
| `ec2.describe_regions` | **없음** |
| `s3.get_bucket_*` 전부 | **없음** (단건 조회) |
| 그 외 S1 대상 API 전부 (`describe_instances`, `describe_volumes`, `describe_snapshots`, `describe_images`, `describe_security_groups`, `describe_vpcs`, `describe_subnets`, `rds.describe_db_*`, `s3.list_buckets`, `backup.list_*`) | 있음 |

→ 수집기는 `can_paginate()`로 분기한다. 서비스 모듈이 개별적으로 판단하지 않는다.

## 2. `ec2.describe_regions()` — OptInStatus 필터가 필수

moto는 38개 리전을 반환하며 `OptInStatus`에 `opt-in-not-required`와 **`not-opted-in`이 섞여 있다.**

```python
{'RegionName': 'af-south-1', 'OptInStatus': 'not-opted-in', 'Endpoint': '...'}
```

`not-opted-in` 리전은 호출해도 실패한다. **`opt-in-not-required` / `opted-in`만 순회한다.**
(실계정은 기본적으로 옵트인된 리전만 주지만, 코드가 그 가정에 기대면 안 된다.)

## 3. S3 "미설정"은 **두 가지 형태**로 온다 — safe_call이 둘 다 흡수해야 한다

설계서 §D는 "예외를 던진다"고만 적었지만, 실제로는 예외를 던지는 것과 **빈 응답을 주는 것**이 갈린다.

| 호출 | 미설정 시 | 판정 근거 |
|---|---|---|
| `get_bucket_encryption` | 예외 `ServerSideEncryptionConfigurationNotFoundError` | 에러 코드 |
| `get_public_access_block` | 예외 `NoSuchPublicAccessBlockConfiguration` | 에러 코드 |
| `get_bucket_tagging` | 예외 `NoSuchTagSet` | 에러 코드 |
| `get_object_lock_configuration` | 예외 `ObjectLockConfigurationNotFoundError` | 에러 코드 |
| `get_bucket_versioning` | **정상 응답 `{}`** (`Status` 키 없음) | 키 부재 |
| `get_bucket_logging` | **정상 응답 `{}`** (`LoggingEnabled` 키 없음) | 키 부재 |
| `get_bucket_policy_status` | **정상 응답 `{'PolicyStatus': {}}`** (moto) | 키 부재 |

> `get_bucket_policy_status`는 실계정에서 버킷 정책이 없으면 `NoSuchBucketPolicy` 예외를 던진다.
> moto는 빈 응답을 준다. **양쪽 다 처리한다** — 에러 코드 목록에도 넣고, 빈 응답 판정식도 건다.

→ `safe_call(fn, absent_errors=..., absent_when=...)` 두 인자를 모두 갖는 이유.

## 4. `backup.list_protected_resources`는 moto 미구현

```
ClientError: An error occurred (404) ... ListProtectedResources operation: Not yet implemented
```

`list_backup_plans` / `list_backup_vaults`는 동작한다. **`list_protected_resources`만 미구현이다.**

이 API는 `infra_facts.backup_exists`의 정답 소스(`docs/field-mapping.md` §5)이므로 포기할 수 없다.
→ moto가 아니라 **botocore Stubber로 응답 구조를 고정해 유닛테스트**한다.

## 5. 알 수 없는 에러를 만나면 — 7번째 상태가 필요하다

CLAUDE.md의 `safe()` 초안은 미지의 에러를 `raise`한다. 그러면 위 4번 같은 상황에서
**전 리전 순회가 통째로 죽는다.** 그리고 이건 moto만의 문제가 아니다.

- 서비스가 특정 리전에 없으면 엔드포인트 에러가 난다 (전 리전 순회의 상시 조건)
- 스로틀링·일시적 서비스 오류

→ 원본 덤프 레벨에 `__status__: "COLLECT_ERROR"`를 추가한다.
**`NOT_CONFIGURED`(설정 없음)로 뭉개지 않는다.** 자산 부재로 오인하면 안 되는 건 `PERMISSION_DENIED`와 같다.

> **확정(2026-08-01)** — 사유 코드는 6종이 아니라 `COLLECT_ERROR`를 포함한 **7종**이다.
> extract 단계에서도 이 사유를 그대로 필드에 붙인다. B에게 넘길 때 함께 설명해야 한다.

## 6. moto 동작 특이점 (실계정과 다름 — 테스트 해석 시 주의)

| 항목 | moto | 실계정 |
|---|---|---|
| `describe_snapshots(OwnerIds=['self'])` | 1160건 반환. **OwnerIds 필터가 안 먹는다** | 자기 소유만. 생략 시 공개 스냅샷 수만 건 |
| `describe_images(Owners=['self'])` | 0건 (필터 정상 동작) | 자기 소유 AMI |
| `get_bucket_encryption` (신규 버킷) | 예외 | AWS는 2023-01부터 SSE-S3 기본 적용이라 `AES256`이 나올 수 있다 |

`OwnerIds` 생략과 지정의 결과가 moto에서 같다고 해서 **파라미터를 빼면 안 된다.** 실계정에서 터진다.

## 7. moto는 `describe_instances`의 `MaxResults`를 무시한다

인스턴스 120건 + `MaxResults=25`로 호출해도 **한 페이지에 120건 전부**를 주고 `NextToken`을 안 준다.

```
direct MaxResults=25 -> reservations 3, instances 120, NextToken? False
paginator PageSize=25 -> pages 1
```

→ **moto로는 다중 페이지가 재현되지 않는다.** "moto에서 전부 받아졌다"는 페이지네이션이
동작한다는 증거가 아니다. `NextToken` 왕복은 **botocore Stubber로 3페이지를 만들어** 검증한다.
(`tests/test_collect.py::test_여러_페이지로_쪼개져도_전부_합친다`)

## 8. `encryption_at_rest` — CMK 여부는 단정할 수 없다

`docs/field-mapping.md` 부록B의 허용값은 `None` / `SSE-S3` / `SSE-KMS-AWS` / `SSE-KMS-CMK` 네 가지다.
그런데 **고객관리형 키(CMK)인지 AWS 관리형인지는 `kms.describe_key`의 `KeyManager`를 봐야 알 수 있고,
아직 KMS를 수집하지 않는다.**

`describe_volumes`는 `Encrypted: true`와 `KmsKeyId`까지만 준다. 여기서 `SSE-KMS-CMK`로 적으면
B의 룰 `C-06`(내부 전용 + 고객관리형 키 암호화 → 기밀성 1)이 근거 없이 발동한다.

→ **추출은 `SSE-KMS`까지만 적는다.** 허용값에 한 가지가 늘어난 셈이다.

| 값 | 의미 |
|---|---|
| `None` | 미암호화 (확정) |
| `SSE-S3` | S3 관리 키 (확정) |
| `SSE-KMS` | **KMS 암호화는 확실하나 키 소유자 미확정** — KMS 수집기가 생기면 CMK/AWS로 갈린다 |

`C-06`을 쓰려면 KMS 수집기가 먼저 필요하다. B에게 이 사실을 전달해야 한다.

## 9. 보안시스템 API의 moto 지원 범위 (S3 세션)

| 호출 | 페이지네이터 | moto | 비고 |
|---|---|---|---|
| `wafv2.list_web_acls(Scope=)` | **없음** | 동작 | `Scope`는 필수 인자 |
| `guardduty.list_detectors` | 있음 | 동작 | |
| `kms.list_keys` / `describe_key` | 있음 / 없음 | 동작 | `KeyManager=='CUSTOMER'`만 자산 |
| `acm.list_certificates` | 있음 | 동작 | |
| `cloudtrail.describe_trails` | **없음** | 동작 | |
| `config.describe_configuration_recorders` | **없음** | 동작 | |
| `secretsmanager.list_secrets` | 있음 | 동작 | |
| `network-firewall.list_firewalls` | 있음 | 동작 | |
| `inspector2.batch_get_account_status` | 없음 | 동작 | |
| `macie2.get_macie_session` | 없음 | **동작하나 실물과 다름** | 아래 참조 |
| `securityhub.describe_hub` | 없음 | **미활성 시 예외** | `InvalidAccessException` |
| `shield.describe_subscription` | 없음 | **미구독 시 예외** | `ResourceNotFoundException` |

마지막 두 개가 중요하다. **"서비스가 꺼져 있음"이 값이 아니라 예외로 온다.**
S3의 `get_bucket_encryption`과 같은 경우이므로 `absent_errors`에 넣어 `NOT_CONFIGURED`로 정규화한다.
그리고 이때의 `NOT_CONFIGURED`는 그 자체가 **"침입탐지 체계가 없다"는 증적**이다.

> `macie2.get_macie_session`은 moto가 활성화 안 된 상태에서도 세션을 돌려준다.
> 실계정은 Macie 미활성 시 `AccessDeniedException`을 던진다. 이 값으로 "Macie 있음"을 단정하면 안 된다.

**moto의 KMS 기본 키는 `KeyManager`가 실물과 다르다.** EBS 볼륨을 만들면 moto가
`"Default master key that protects my EBS..."` 키를 자동 생성하는데 `KeyManager=CUSTOMER`로 온다.
실계정에서 `aws/ebs` 기본 키는 `KeyManager=AWS`다.

→ `where: KeyMetadata.KeyManager == 'CUSTOMER'` 필터 자체는 옳다. **moto 결과에서 KMS 키가
한 건 더 잡히는 것은 moto 쪽 차이다.** 테스트에서 "보안시스템 0건"을 기대하면 안 된다.

## 10. 확인된 응답 구조

- `Instance.LaunchTime` → `datetime` 객체. JSON 직렬화 시 ISO8601 변환 필요
- `Instance.State` → `{'Code': 16, 'Name': 'running'}`
- `Instance.Placement` → `{'GroupName','Tenancy','AvailabilityZone'}`
- EC2 태그 → `Tags` (대문자 리스트), RDS 태그 → **`TagList`** (설계서 기술과 일치)
- RDS 신규 인스턴스 기본값: `StorageEncrypted=False`, `BackupRetentionPeriod=1`, `MultiAZ=False`
