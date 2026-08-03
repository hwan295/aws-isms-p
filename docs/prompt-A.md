# 담당 A 프로토타입 프롬프트 — 수집기

목표: boto3로 가져올 수 있는 건 전부 가져오고, 못 가져오는 건 **왜 못 가져오는지와 누가 어떻게 채워야 하는지**까지 담아서 판정 담당에게 JSON으로 넘긴다.

세션 순서: **S1 → S2 → S3 → S4**. 한 세션에 하나씩. S1이 끝나야 S2가 의미 있습니다.

---

## 착수 전 확정 사항 (2026-08-01)

문서 간 충돌을 해소하고 아래로 확정했습니다. 상세는 `CLAUDE.md`의 "확정 사항" 절.

| 쟁점 | 확정 |
|---|---|
| `asset_type` 도메인 | 안내서 **11종** (서버/데이터(DBMS)/정보시스템(응용프로그램)/소프트웨어/네트워크장비/보안시스템/PC/정보/설비/시설/가상자원). AWS로 0건인 유형도 빈 배열로 출력 |
| 결측 사유 | **8종** — `null` / `TAG_ABSENT` / `NOT_CONFIGURED` / `PERMISSION_DENIED` / `API_NULL` / `NOT_APPLICABLE` / `COLLECT_ERROR` / `OUT_OF_SCOPE` |
| `infra_facts` | **A가 만들어 넘긴다.** `docs/field-mapping.md` §5의 17키. S2에서 구현 |
| 자산 간 조인 | **A가 한다.** `parent_id`(스냅샷→볼륨→인스턴스)와 `open_sg_rule`·`exposure_path`를 자산 단위로 채운다. 조인은 사실이지 판정이 아니다 |
| 레코드 모양 | **평면.** `ip_private`를 최상위에 두고 개념 없는 자산은 `NOT_APPLICABLE`로 표시 (명세서 §7의 `network` 중첩 안 씀) |
| 용도 태그 키 | **`InventoryCategory`** (`Purpose` 아님) |
| `required_items` | 항목마다 `field`(대응 계약 필드) 선언. 그래야 미충족 자동 계산이 성립 |
| 계정·리전 | 단일 계정 + 전 리전 순회. 코드는 계정 루프로 써두되 Organizations AssumeRole은 범위 밖 |
| S1 서비스 범위 | ec2 / rds / s3 / backup 4개 유지. **보안시스템 수집기(결함사례 1 대응)는 S3에서** |
| 저장소 | `AWS-ISMS-P/`가 프로젝트 루트. 문서는 `docs/`. **git 미사용 — 로컬만** |
| 환경 | uv + Python 3.13 `.venv`, `requirements.txt` |

---

## S1 — 원본 수집기

```
ISMS-P 인증기준 1.2.1(정보자산 식별) 대응 AWS 자산 수집기의 프로토타입을 만든다.
나는 수집 파트(A) 담당이고, 판정·출력 파트(B)는 다른 사람이 맡는다.
내 산출물은 B에게 넘길 JSON 파일이다.

이번 세션 목표: AWS 응답을 통째로 덤프하는 수집기.
필드 선별은 다음 세션에서 한다. 지금은 고르지 않는다.

핵심 설계 원칙:
수집 시점에 필드를 골라 버리면, 나중에 B가 "이 필드도 필요하다"고 할 때
AWS를 다시 호출해야 한다. 그래서 응답을 손대지 않고 통째로 저장한다.
나중에는 저장된 원본에서 다시 뽑기만 하면 된다.

구현:

1. collector/session.py
   - sts.get_caller_identity() 로 계정 ID
   - ec2.describe_regions() 로 활성 리전 목록 (OptInStatus 확인)
   - 계정 → 리전 → 서비스 순회
     (계정은 현재 자격증명 1개만. 단 코드는 for account 루프로 써서
      나중에 Organizations AssumeRole만 끼워 넣으면 되게 한다)
   - --regions 옵션으로 리전 제한 가능. 기본값은 전 리전
   - 전역 서비스(s3 list_buckets, iam, cloudfront, route53)는
     리전 루프 밖에서 1회만
   - run_id 생성 (run-YYYYMMDD-HHMM)
   - botocore adaptive retry mode

2. collector/safe_call.py
   AWS 호출 결과를 세 가지 상태로 구분해서 기록하는 래퍼.
   이 구분이 이 프로젝트 전체에서 제일 중요하다.

   - 정상 응답      → 응답 그대로
   - 설정이 없음    → {"__status__": "NOT_CONFIGURED", "error_code": "..."}
   - 권한이 없음    → {"__status__": "PERMISSION_DENIED", "error_code": "..."}

   권한 부족을 설정 부재로 처리하면 등급 제안이 통째로 틀린다.
   예: 권한이 없어서 암호화 설정을 못 읽었는데 "미암호화"로 기록하면
   기밀성 등급이 잘못 나온다.

   S3의 get_bucket_encryption 등은 설정이 없을 때 값이 아니라 예외를 던진다.
   예외를 값으로 정규화하는 게 이 파일의 역할이다.

3. collector/services/ 에 서비스별 모듈
   각 모듈은 자기가 담당하는 AWS API를 전부 호출하고 응답을 그대로 반환한다.
   응답을 가공하지 마라. 필드를 고르지 마라.

   이번 세션에서 만들 것:
   - ec2.py    : describe_instances, describe_addresses, describe_volumes,
                 describe_snapshots(OwnerIds=['self']),
                 describe_images(Owners=['self']), describe_security_groups,
                 describe_vpcs, describe_subnets
   - rds.py    : describe_db_instances, describe_db_clusters
   - s3.py     : list_buckets 후 버킷마다 get_bucket_location,
                 get_bucket_encryption, get_bucket_policy_status,
                 get_public_access_block, get_bucket_versioning,
                 get_bucket_logging, get_bucket_tagging
   - backup.py : list_protected_resources, list_backup_plans

   각 모듈에 required_actions 리스트를 선언해라.
   나중에 최소권한 IAM 정책을 자동 생성하는 데 쓴다.

4. collector/dump.py
   snapshots/raw/{run_id}/{account}/{region}/{service}.json 으로 저장.
   각 파일 상단에 메타: run_id, account, region, collected_at,
   호출한 API 목록(source_api).

5. CLI
   python -m collector collect

반드시 지킬 것:
- 페이지네이터를 쓸 수 있는 모든 API는 페이지네이터로 호출해라.
  그냥 호출하면 자산이 많을 때 조용히 일부만 받는다.
  자산 목록 도구에서 제일 늦게 발견되는 치명적 버그다.
- describe_images(Owners=['self']), describe_snapshots(OwnerIds=['self'])
  생략하면 공개 이미지 수만 건이 딸려온다.
- 쓰기 API를 절대 호출하지 마라. 읽기 전용이다.
- S3는 list_buckets만 전역이고 나머지는 버킷별 리전 클라이언트로 호출해야 한다.

테스트:
moto로 가짜 환경을 만들어 검증해라. 실제 AWS 계정은 쓰지 않는다.
- EC2 3대(태그 있음/없음/중지), 미연결 EBS 볼륨 1개
- 암호화 없는 S3 버킷 1개 → NOT_CONFIGURED로 기록되는지 확인
- 인스턴스 100건 이상 생성해서 페이지네이션 검증

응답 경로를 추측하지 마라. 확실하지 않으면 moto나 botocore Stubber로
실제 구조를 확인한 뒤 코드를 써라.
다 만들었으면 실행해서 덤프 파일 내용을 보여줘라.
```

---

## S2 — ISMS-P 항목별 JSON 생성기

```
S1에서 만든 원본 덤프를 읽어, ISMS-P 자산유형별로 정리된 JSON을 만든다.
이게 판정 담당(B)에게 넘길 인수인계물이다.

중요: 이 단계는 AWS에 접속하지 않는다. snapshots/raw/ 만 읽는다.
반드시 단독 실행되는지 확인해라. 이게 원본 보관 구조의 핵심 이점이다.

1. config/extract_map.yaml — 추출 규칙을 코드가 아니라 선언으로
   나중에 B가 "이 필드도 필요하다"고 하면 yaml 한 줄 추가 + 재추출로 끝나야 한다.
   AWS 재호출도 코드 수정도 없어야 한다.

   구조 예시:

   ec2_instance:
     source: "ec2/describe_instances"
     iterate: "Reservations[].Instances[]"
     isms_asset_type: "서버"
     asset_id: "arn:aws:ec2:{region}:{account}:instance/{InstanceId}"
     fields:
       asset_name:      { path: "Tags[?Key=='Name'].Value | [0]", from: "tag" }
       serial_no:       { path: "InstanceId", from: "api" }
       model:           { path: "InstanceType", from: "api" }
       ip_private:      { path: "PrivateIpAddress", from: "api" }
       usage:           { path: "Tags[?Key=='InventoryCategory'].Value | [0]", from: "tag" }
       owner_dept:      { path: "Tags[?Key=='OwnerDept'].Value | [0]", from: "tag" }
       owner_manager:   { path: "Tags[?Key=='OwnerManager'].Value | [0]", from: "tag" }
       owner_responsible: { path: "Tags[?Key=='OwnerResponsible'].Value | [0]", from: "tag" }
       has_personal_info: { path: "Tags[?Key=='HandlePI'].Value | [0]", from: "tag" }
       lifecycle_state: { path: "State.Name", from: "api" }
       created_at:      { path: "LaunchTime", from: "api" }

   경로는 JMESPath로 쓴다 (boto3에 이미 포함되어 있어 의존성이 늘지 않는다).
   from 이 "tag"인 필드는 값이 없을 때 TAG_ABSENT,
   "api"인 필드는 값이 없을 때 API_NULL 로 사유가 갈린다.

   서비스마다 태그 형식이 다르다. transform으로 흡수해라.
   EC2/EBS: Tags (대문자 리스트) / RDS: TagList /
   Lambda·ECR: tags (소문자 dict) / S3: TagSet

2. config/isms_asset_types.yaml
   ISMS-P 안내서 1.2.1의 자산 유형 정의와,
   각 유형이 요구하는 항목(안내서 "자산 유형별 항목(예)")을 선언한다.

   자산유형은 안내서 11종 전부를 키로 만든다.
   AWS로 한 건도 안 잡히는 유형(설비/시설/정보(문서적))도 키를 만든다.
   0건이라는 사실 자체가 결함사례 1·4의 리포트 대상이기 때문이다.

   required_items는 문자열 리스트가 아니라 field를 함께 선언한다.
   한글 항목명만으로는 "이 요구항목이 채워졌는가"를 기계가 계산할 수 없다.

   서버:
     required_items:
       - { name: "호스트 명칭",     field: asset_name }
       - { name: "자산 일련번호",   field: serial_no }
       - { name: "모델명",          field: model }
       - { name: "용도",            field: usage }
       - { name: "IP주소",          field: ip_private }
       - { name: "관리 부서명",     field: owner_dept }
       - { name: "관리 실무자",     field: owner_manager }
       - { name: "관리 책임자",     field: owner_responsible }
       - { name: "보안등급",        field: null, manual_ref: security_grade }
     not_applicable: [endpoint]
     aws_collectable: [ec2_instance, ecs_service, lambda_function]

   데이터(DBMS):
     required_items:
       - { name: "데이터베이스명",     field: asset_name }
       - { name: "테이블명",           field: null, manual_ref: db_table_names }
       - { name: "(개인)정보 항목명",  field: personal_info_items }
       - { name: "관리 부서명",        field: owner_dept }
       ...
     not_applicable: [ip_private, os]
     aws_collectable: [rds_instance, dynamodb_table]

   설비:
     required_items: [...]
     aws_collectable: []          # 비어 있는 게 정답. CSP 책임영역
     manual_only: true

   field: null 은 AWS API로 채울 수 없는 항목이고,
   manual_ref 가 config/manual_items.yaml 의 키를 가리킨다.
   not_applicable 은 그 유형에서 NOT_APPLICABLE 사유를 붙일 필드 목록이다.

   이 파일이 3번(수집 불가 항목 처리)의 근거가 된다.

3. collector/extract.py
   raw JSON을 읽어 자산 레코드를 만든다.
   출력은 ISMS-P 자산유형별로 그룹핑한다.

   각 필드는 값만 넣지 말고 사유를 함께 실어라:

   "owner_dept": { "value": null, "reason": "TAG_ABSENT",
                   "hint": "OwnerDept 태그를 달면 다음 실행부터 자동 수집됩니다" }
   "ip_private": { "value": "10.0.1.25", "reason": null }
   "encryption":  { "value": null, "reason": "NOT_CONFIGURED" }
   "versioning":  { "value": null, "reason": "PERMISSION_DENIED",
                    "hint": "s3:GetBucketVersioning 권한이 필요합니다" }

   사유 종류 (8종):
   - null              : 정상 수집됨
   - TAG_ABSENT        : 태그 미입력 (담당자가 태그 달면 해결)
   - NOT_CONFIGURED    : AWS 설정이 없음 (사실 자체가 정보)
   - PERMISSION_DENIED : 권한 부족 (자산 부재 아님. 절대 혼동 금지)
   - API_NULL          : API가 값을 안 줌
   - NOT_APPLICABLE    : 이 자산유형에 개념 자체가 없음 (S3 버킷의 IP주소)
                         → 갭 리포트에 출력하지 않는다.
                         이게 없으면 "S3 버킷 IP 미확인" 같은 행이 리포트를 덮는다.
                         isms_asset_types.yaml 의 not_applicable 목록으로 판정한다.
   - COLLECT_ERROR     : 조회 자체가 실패 (자산 부재 아님)
   - OUT_OF_SCOPE      : 개념은 있는데 이 도구가 아직 그 API를 안 부른다.
                         안 불러본 것을 "없음"으로 단정하지 않기 위한 코드다.
                         EC2에 공인 IP가 없다고 exposure_path를 "None"으로 적으면
                         ALB 뒤 자산을 외부 미노출로 단정하게 되고 C-03이 틀어진다.

4. infra_facts — 등급 룰(B)의 입력값

   자산 레코드마다 infra_facts 객체를 싣는다.
   docs/field-mapping.md §5의 17키를 그대로 쓴다.

   "infra_facts": {
     "backup_exists":      { "value": true, "reason": null },
     "backup_source":      { "value": "AWS Backup plan: daily-prd", "reason": null },
     "encryption_at_rest": { "value": "SSE-KMS-CMK", "reason": null },
     "public_exposed":     { "value": false, "reason": null },
     "multi_az":           { "value": null, "reason": "NOT_APPLICABLE" },
     ...
   }

   - 사실 수집일 뿐 판정이 아니다. 등급은 여전히 B가 매긴다.
   - S1 수집 범위 밖에서 오는 키는 다른 필드와 똑같이 사유를 달아 null로 둔다.
     조용히 false를 넣으면 B가 "미설정"으로 오독한다.
   - backup_exists는 스냅샷 개수가 아니라
     backup.list_protected_resources() 결과로 판정한다.

5. 출력 형식

   snapshots/normalized/{run_id}/assets.json

   {
     "meta": { "run_id", "account_id", "collected_at", "regions": [...],
               "contract_version", "reason_codes": [...] },
     "asset_types": {
       "서버": {
         "isms_required_items": [...],
         "assets": [ {...}, {...} ]
       },
       "데이터(DBMS)": { ... },
       "보안시스템": { "assets": [] },
       "설비": { "assets": [] },
       "시설": { "assets": [] }
     }
   }

   자산유형 11종 키를 전부 만든다. 0건이면 빈 배열이다.
   키가 없으면 "수집기가 빠뜨린 것"과 "실제로 0건인 것"을 구분할 수 없다.

6. CLI
   python -m collector extract --run <run_id>

   AWS 접속 없이 단독 실행되는지 반드시 확인해라.

테스트:
- extract_map.yaml에 필드를 하나 추가하고 재추출했을 때
  코드 수정 없이 반영되는지 확인해라. 이게 이 구조의 검증 포인트다.
- 각 사유가 올바르게 붙는지 (태그 없는 EC2 → TAG_ABSENT,
  암호화 없는 S3 → NOT_CONFIGURED, S3 버킷의 ip_private → NOT_APPLICABLE)

실행해서 assets.json 내용을 보여줘라.
```

---

## S3 — 수집 불가 항목 처리 + 담당자 작업 지시

```
이 프로젝트는 자동화가 목적이지만, 동시에 증적을 관리하는 기업 담당자의
부담을 줄여주는 것도 목적이다.

따라서 도구가 못 채우는 칸을 "빈 칸"으로 두면 안 된다.
"이 칸은 당신이 채워야 하고, 이유는 이거고, 이렇게 채우면 된다"까지
알려줘야 담당자의 부담이 실제로 줄어든다.

0. collector/services/security.py — 보안시스템 수집기 (선행)

   결함사례 1을 시연하려면 "AWS 보안서비스는 있는데 유출통제 시스템은 0건"을
   보여줘야 한다. 그러려면 AWS 쪽 보안시스템을 먼저 수집해야 한다.

   wafv2.list_web_acls(Scope='REGIONAL'), guardduty.list_detectors(),
   kms.list_keys() → describe_key(KeyManager=='CUSTOMER'만),
   acm.list_certificates(), cloudtrail.describe_trails() + get_trail_status(),
   config.describe_configuration_recorders(), securityhub.describe_hub(),
   secretsmanager.list_secrets()

   moto 지원 범위를 먼저 확인하고, 미지원 API는 botocore Stubber로
   응답 구조를 확인한 뒤 별도 유닛테스트로 검증한다.
   지원 여부를 추측해서 코드를 쓰지 마라.

1. config/manual_items.yaml
   AWS API로 얻을 수 없는 항목을 자산유형별로 선언한다.
   docs/design.md의 "수집 불가·담당자 검증 필요" 표가 원본이다.

   각 항목에 네 가지를 담아라:

   security_system_dlp:
     isms_asset_type: "보안시스템"
     item_name: "내부정보 유출통제 시스템"
     examples: ["출력물 보안", "문서암호화(DRM)", "USB 매체제어", "DLP"]
     reason: "온프레미스 엔드포인트 솔루션으로 AWS API 대상이 아님"
     evidence: "ISMS-P 안내서 1.2.1 결함사례 1 — 취급자 PC를 통제하는
                유출통제 시스템이 자산 목록에서 누락된 경우"
     owner: "정보보안팀"
     action: "보유 솔루션을 수기 등재. 미보유 시 미보유 사실을 문서화"
     recurring: false          # 영구히 수기

   asset_owner_dept:
     isms_asset_type: "전체"
     item_name: "관리부서·실무자·책임자"
     reason: "AWS에 소유자 개념이 없음. 태그로 넣지 않으면 어디에도 없는 정보"
     evidence: "ISMS-P 안내서 1.2.1 자산 유형별 항목(예) — 3주체 모두 요구"
     owner: "각 자산 운영 부서"
     action: "OwnerDept / OwnerManager / OwnerResponsible 태그 입력"
     recurring: true           # 태그 달면 다음부터 자동
     auto_after_fix: true

   recurring / auto_after_fix 구분이 중요하다.
   - 태그만 달면 다음 실행부터 자동으로 채워지는 항목
   - AWS 밖 자산이라 영원히 수기여야 하는 항목
   담당자 입장에서 완전히 다른 일이다. 섞어서 보여주면 안 된다.

   최소한 이 항목들을 담아라:
   - 내부정보 유출통제 시스템 (출력물보안/DRM/USB/DLP)  ← 결함사례 1
   - 제3자 제공 개인정보 여부                          ← 결함사례 2
   - 위탁 IT 서비스·외부 SaaS                          ← 결함사례 4
   - 온프레미스 PC·네트워크 장비
   - 문서적 정보 (계약서, 서면동의서, 출력물)
   - 설비·시설 (책임공유모델상 CSP 영역, 제외 사유 필요)
   - DB 테이블명·개인정보 항목명
   - 인증범위 포함 여부 / 제외 사유
   - 관리부서·실무자·책임자
   - 용도(목적 및 기능)
   - 보안등급 확정

2. collector/manual.py
   assets.json에 두 가지를 추가한다.

   (a) 자산유형별 미수집 항목
       isms_asset_types.yaml의 required_items를 순회하며 자동 계산한다.
       - field: null 인 항목        → 무조건 manual_required (manual_ref 참조)
       - field 가 있는데 그 유형의 자산 전부에서 결측 → manual_required
         (몇 건 중 몇 건이 결측인지 함께 적는다)
       - 일부만 결측 → manual_required 아님. 대신 todo의 affected_assets로 집계

       "보안시스템": {
         "assets": [ ...WAF, GuardDuty 등... ],
         "manual_required": [
           { "item_name": "내부정보 유출통제 시스템",
             "collected_count": 0,
             "reason": "...", "evidence": "...", "owner": "...",
             "action": "...", "recurring": false }
         ]
       }

   (b) 담당자 작업 지시 요약 (todo)
       assets.json 최상단에 넣어라.

       "manual_todo": {
         "summary": { "total": 8, "auto_after_fix": 5, "permanent": 3 },
         "by_owner": {
           "각 자산 운영 부서": [
             { "action": "OwnerDept 태그 입력",
               "affected_assets": 62, "affected_ratio": "40%",
               "auto_after_fix": true,
               "sample_asset_ids": ["i-0abc...", "i-0def..."] }
           ],
           "정보보안팀": [
             { "action": "내부정보 유출통제 시스템 수기 등재",
               "affected_assets": 0, "auto_after_fix": false,
               "evidence": "안내서 결함사례 1" }
           ]
         }
       }

       affected_assets 숫자가 붙어야 담당자가 우선순위를 정할 수 있다.
       "태그 하나 달면 62건이 해결된다"와 "1건짜리 수기 등재"는
       들이는 노력 대비 효과가 완전히 다르다.

3. reporter/manual_sheet.py — 수기 입력 템플릿 xlsx
   담당자가 실제로 채워 넣을 빈 양식을 생성한다.
   컬럼: 자산유형 / 항목명 / 예시 / 왜 수기인가 / 담당 / 작성란
   설비·시설은 제외 사유 예시 문구를 미리 채워둬라
   ("책임공유모델상 CSP 책임영역. AWS Artifact ISO 27001·SOC 2 보고서 첨부")

   담당자가 백지에서 시작하지 않게 하는 것이 목적이다.

4. 콘솔 출력
   extract 실행 후 터미널에 담당자 작업 요약을 보여줘라.

   [자동 수집] 서버 24건 / DBMS 3건 / 저장장치 12건 / 보안시스템 4건

   [태그만 달면 자동화됨]
     · OwnerDept 태그 입력      62건 (40%)  → 각 자산 운영 부서
     · HandlePI 태그 입력       21건 (14%)  → 개인정보보호 담당
   [수기 등재 필요 - 영구]
     · 내부정보 유출통제 시스템  현재 0건 등재  → 정보보안팀
     · 위탁 IT 서비스·SaaS      현재 0건 등재  → IT기획팀
   [권한 부족으로 조회 실패]
     · s3:GetBucketVersioning    3건  ← 자산 부재 아님

   마지막 항목을 반드시 분리해서 보여줘라.
   권한 문제를 자산 문제로 오인하면 대장 전체가 틀린다.

실행해서 assets.json의 manual_todo 부분과 콘솔 출력을 보여줘라.
```

---

## S4 — 데모 마무리

```
프로토타입을 발표·검토 가능한 상태로 마무리한다.

1. moto 기반 데모 환경 스크립트 (demo_env.py)
   갭이 실제로 잡히는 걸 보여주려면 지저분한 환경이 필요하다.
   AWS 계정 없이 moto 안에서 생성한다.

   - 태그 완비 EC2 2대 / 태그 전무 EC2 3대 / 중지 EC2 1대
   - 백업 있는 RDS 1대 / 없는 RDS 1대
   - 암호화 S3 1개 / 미암호화 S3 1개 / 퍼블릭 S3 1개
   - 연결된 EBS 2개 / 미연결 EBS 2개
   - 오래된 스냅샷 2개
   - 보안시스템은 일부러 아무것도 만들지 않는다 (결함사례 1 재현)

   한 번에 실행:
   python demo.py    # 환경 생성 → collect → extract → 결과 출력

2. README
   - 이 도구가 무엇이고 ISMS-P 1.2.1의 어느 항목에 대응하는지
   - collect / extract 분리 이유 (재수집 없이 재추출)
   - 사유 5종(정상/TAG_ABSENT/NOT_CONFIGURED/PERMISSION_DENIED/API_NULL) 설명
   - 판정 담당(B)에게 넘기는 JSON 구조 설명
   - 실행 방법

3. 최소권한 IAM 정책 생성
   각 수집기의 required_actions를 모아 JSON 출력.
   쓰기 액션이 하나라도 있으면 실패시켜라.

4. .gitignore (이미 작성됨 — 유지·검토만)
   snapshots/, output/, .env, .aws/, __pycache__, .venv
   원본 덤프는 태그 값에 담당자 이메일·전화번호가 들어 있을 수 있다.
   절대 커밋하지 않는다.
   현재는 git 저장소가 아니다. git init·커밋을 임의로 실행하지 마라.

python demo.py 를 실행해서 전체 흐름 결과를 보여줘라.
```

---

## 세션마다 붙일 문장

```
응답 경로를 추측하지 마라. 확실하지 않으면 moto나 botocore Stubber로
실제 구조를 확인한 뒤 코드를 써라.

advisor/ 와 reporter/ 의 판정 로직은 담당 B 영역이다. 만들지 마라.
(reporter/manual_sheet.py 는 수집 불가 항목 안내이므로 예외로 내가 만든다)

만든 코드는 실제로 실행해서 출력을 보여줘라. "동작할 겁니다"로 끝내지 마라.

AWS 실계정에 접속하지 마라. moto로만 검증한다.
```

---

## 판정 담당(B)에게 넘길 때 함께 전달할 것

- `snapshots/normalized/{run_id}/assets.json` — 인수인계물
- `config/isms_asset_types.yaml` — 자산유형별 요구 항목
- `config/manual_items.yaml` — 수집 불가 항목 정의
- 사유 6종의 의미 (특히 `PERMISSION_DENIED`를 자산 부재로 해석하지 말 것,
  `NOT_APPLICABLE`은 갭 리포트에서 제외할 것)
- `infra_facts` 17키 — 등급 룰의 입력값. 값이 null이면 사유를 보고 판단할 것

**필드 추가 요청 양식** — B가 이 형식으로 요청하면 AWS 재호출 없이 처리됩니다.

```
extract_map.yaml 추가 요청
자산유형: 데이터(DBMS)
필요 필드: deletion_protection
원본 경로: rds/describe_db_instances → DBInstances[].DeletionProtection
용도: 가용성 룰 (운영 자산에 삭제 방지 미설정 시 가중)
```
