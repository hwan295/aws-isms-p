# ISMS-P 1.2.1 정보자산목록 — boto3 수집값 → 대장 필드 매핑 명세서

**버전** v1.0
**대상** AWS 단일/멀티 계정 환경
**용도** 수집기(Collector) 구현 명세 + 출력기(Reporter) 컬럼 정의 + 심사 대응 근거
**작성 기준일** 2026-07-27

---

## 0. 리서치 근거와 한계

### 0.1 먼저 밝혀둘 것 — 기업의 실제 증적 제출본은 공개되지 않는다

ISMS-P 인증심사에 제출되는 정보자산목록은 **자산의 호스트명·IP·담당자 실명·개인정보 항목**이 그대로 담긴 대외비 문서다. 인증서 발급 현황은 공개되지만 제출 증적 원본은 공개된 사례가 없다. "A사 자산목록.xlsx 원본"을 찾아 그대로 베끼는 접근은 성립하지 않는다.

따라서 이 문서는 다음 세 층위를 교차 검증해 **"공개 자료로 재구성 가능한 최대치"**로 작성했다.

| 층위 | 자료 | 이 문서에서 쓴 부분 |
|---|---|---|
| ① 규제기관 공식 | KISA ISMS-P 인증기준 안내서 1.2.1 | 자산 유형표, 유형별 필수 항목, 결함사례 5종 |
| ① 규제기관 공식 | KISA CSAP `03_정보자산목록.hwp` 실물 예시 양식 | **시트 구조·컬럼명 원본** (본 프로젝트가 확보) |
| ① 규제기관 공식 | KISA 지역정보보호센터 ICT중소기업 컨설팅 자산관리대장 양식·가이드 | 중소기업 실무 컬럼 세트 |
| ② 법령·훈령 | 국가법령정보센터 「정보자산관리지침」 (국가정보자원관리원 훈령 / 항공교통본부 부록2) | CIA 1~3점 합산 산정, "실시간 백업 미실시" 무결성 조건 |
| ② 준표준 | TTA(한국정보통신기술협회) 정보자산 분류·중요도 평가 기준 | 필수기입 5항목, 보안등급 = C+I+A |
| ③ 기업 실무 | **AWS Korea** 기술블로그 (2023.06, 한태경 SA) | **ISMS/CSAP 대응 권장 태그 5종** — 이 문서의 태그 표준 원본 |
| ③ 기업 실무 | **스마일샤크** (ISMS-P 인증 취득 AWS Premier Partner, 2026.06) | IaaS/PaaS/SaaS 책임범위별 증적 대상, 증적 4원칙 |
| ③ 기업 실무 | **SK쉴더스 EQST** AWS 환경 ISMS 구현 전략 | Config·Inspector 기반 자산 위험평가 자동화 |
| ③ 기업 실무 | **베스핀글로벌** AWS Control Tower ISMS-P 대응 | 멀티 계정 Config 룰 기반 통제 |
| ③ 기업 실무 | **LG CNS** 정보자산 식별 가이드 | 자산 조사 → 분류 → 목록 작성 → 가치평가 절차 |
| ③ 기업 실무 | **메가존클라우드** ISMS 인증 컨설팅 프로세스 | Discover → 기술환경진단 → 내부감사 단계 구성 |
| ④ 벤더 표준 | AWS Organizations 태그 정책 / 리소스 태그 지정 모범 사례 백서 | 태그 강제·준수 검증 방식 |

### 0.2 교차 검증에서 반복 확인된 5가지 합의점

여러 출처가 독립적으로 같은 말을 하는 지점만 추렸다. 이 5개가 이 명세서의 설계 근거다.

1. **필수기입 항목은 최소 5개** — 자산 유형, 자산코드, 자산명, 자산관리자, 보안등급(C·I·A). (TTA / LG CNS)
2. **보안등급 = 기밀성 + 무결성 + 가용성 합산**, 각 1~3점, 합계 분포로 등급 결정. (TTA / 정보자산관리지침 제7~8조)
3. **클라우드 자산 분류는 태그로 한다** — AWS Korea가 ISMS/CSAP 대응용으로 제시한 태그가 `Environment` / `InventoryCategory` / `SeverityLevel` / `HandlePI` / `IsPublic` 5종. 우리 데이터 계약의 태그 필드는 여기에 정렬시킨다.
4. **인증범위는 책임공유모델로 결정된다** — IaaS는 Guest OS·미들웨어·응용·DB까지, PaaS는 응용과 할당받은 계정·권한, SaaS는 계정·권한 등 관리 가능 영역. (KISA 안내서, 스마일샤크 정리)
5. **증적은 시점 스냅샷이 아니라 축적된 기록이어야 한다** — 연속성·자동화·문서와 실제의 일치·변경불가능성. (스마일샤크) → 이것이 우리 도구의 diff 기능이 정당화되는 근거다.

### 0.3 이 문서를 쓰는 법

- 수집기 담당(A): §3~§5의 **boto3 호출 / 응답 경로** 열만 보면 구현이 끝난다.
- 규칙·출력 담당(B): §6 룰 카탈로그, §7 필드 프로파일, §8 갭 정의를 그대로 코드화한다.
- 보고서 작성 시: §11 체크리스트와 §부록C 출처 목록을 인용한다.

---

## 1. 대장 시트 구조 (KISA CSAP 실물 양식 원본)

확보한 `03_정보자산목록.hwp`를 파싱한 결과, 원본 양식은 **7개 시트**이며 모든 시트가 `구분 / 자산상세내역 / 관리형태` 3단 헤더를 공유한다.

| # | 시트명 (원본) | 원본 컬럼 |
|---|---|---|
| 1 | 서버 시스템 목록 | 번호, 호스트명, VM/Hardware, OS, OS버전, IP, 추가IP, 용도(목적 및 기능), 설치서버, 관리부서, 운용자, 위치(상세위치) |
| 2 | WEB Application 목록 | 번호, 자산명(관리명칭), VM/Hardware, OS, SW version, IP, 용도, 관리부서, 운용자, 위치 |
| 3 | WAS 목록 | 번호, 호스트명, VM/Hardware, OS, SW version, IP, 용도, 관리부서, 운용자, 위치 |
| 4 | DBMS 목록 | 번호, DBMS명(종류), 설치서버 호스트명, IP, 용도, 관리부서, 운용자, 위치 |
| 5 | PC 목록 | 번호, 모델명, OS, PC IP / VDI IP, 용도, 소속팀, 사용자(소속/명) |
| 6 | 오픈 소프트웨어 목록 | 번호, 모델명, 버전, 수량, 용도, 소속팀, 운용자 |
| 7 | 기타 자산 목록 | 번호, 구분, 자산명, OS, 버전, IP, 용도, 관리부서, 운용자, 위치, 비고 |

### 1.1 원본 양식의 결손 — 반드시 컬럼을 추가해야 하는 이유

원본 7개 시트 **어디에도 보안등급 컬럼이 없다.** 그런데 1.2.1 인증기준 원문은 "…중요도를 산정한 후 그 목록을 최신으로 관리하여야 한다"이고, 세부점검항목 ②는 "법적 요구사항 및 업무에 미치는 영향 등을 고려하여 중요도를 결정하고 보안등급을 부여하고 있는가"다.

→ **원본 양식을 그대로 출력하면 세부점검항목 ②를 증적으로 충족하지 못한다.** 아래 컬럼 추가는 선택이 아니라 필수다.

| 추가 컬럼 | 근거 |
|---|---|
| 자산코드 | TTA 필수기입 5항목 |
| 관리책임자 | 안내서 "관리 부서명, 관리 실무자, 관리 책임자" 3주체 요구 |
| 기밀성(C) / 무결성(I) / 가용성(A) | 정보자산관리지침 제7조, TTA |
| 보안등급 | 정보자산관리지침 제8조 (C+I+A 합산 분포) |
| 개인정보 포함 여부 / 개인정보 항목 | 안내서 데이터 자산 항목 예시, 결함사례 2·5 |
| 수집 출처 (자체수집/제3자제공/위탁) | 결함사례 2 |
| 계정ID / 리전 / AZ | 클라우드 자산 특정을 위한 최소 식별자 |
| 인증범위 포함 여부 + 제외 사유 | "관리체계 **범위 내** 모든 자산" 요구, 결함사례 4 |
| 원본-사본 관계 | 결함사례 5 (백업 등급 저평가) |
| 생명주기 상태 | 세부점검항목 ③ (신규·변경·폐기) |
| 최종 확인일 / 확인자 | 정기 실사 증적 |

### 1.2 도구가 출력할 최종 시트 구성 (원본 7 → 11)

기타 자산 시트 하나에 네트워크·보안·스토리지·위탁을 전부 넣으면 심사원이 누락 여부를 검증할 수 없다. 4개로 분리한다.

| 시트 | asset_type | 주 수집원 |
|---|---|---|
| S1 서버 시스템 | `서버` | EC2, ECS, EKS, Lambda, Lightsail |
| S2 WEB Application | `응용프로그램` | ALB/NLB, CloudFront, API Gateway, S3 정적호스팅 |
| S3 WAS | `응용프로그램` | Elastic Beanstalk, App Runner, ECS Service |
| S4 DBMS | `저장장치(DBMS)` | RDS, Aurora, DynamoDB, Redshift, ElastiCache, DocumentDB |
| S5 저장장치·데이터 | `저장장치` | S3, EBS, EFS, FSx, AWS Backup |
| S6 가상자원 | `가상자원` | AMI, ECR 이미지, EBS 스냅샷 |
| S7 네트워크 | `네트워크장비` | VPC, Subnet, RTB, IGW, NAT, TGW, VPN, DX, SG, NACL |
| S8 보안시스템 | `보안시스템` | WAF, Shield, GuardDuty, Inspector, Security Hub, Network Firewall, KMS, ACM, Secrets Manager, IAM, CloudTrail, Config, Macie |
| S9 PC | `PC` | WorkSpaces (+ 온프레 단말 수기) |
| S10 오픈 소프트웨어 | `소프트웨어` | SSM Inventory, ECR 이미지 패키지, License Manager |
| S11 기타·위탁 | `기타` | 외부 SaaS, MSP, PG (수기) + AWS Artifact 보고서 |

---

## 2. 태그 표준 — 수집 이전의 전제조건

수집기는 태그를 **읽을 뿐** 만들지 못한다. 태그가 없으면 대장의 절반이 빈다. 따라서 태그 표준 문서가 도구보다 먼저 나와야 한다.

### 2.1 태그 키 정의 (AWS Korea 권장 5종 + ISMS-P 요구 확장)

| 태그 키 | 출처 | 허용값 | 매핑되는 대장 컬럼 | 필수 |
|---|---|---|---|---|
| `Name` | AWS 관례 | 네이밍 규칙 준수 문자열 | 호스트명 / 자산명 | ● |
| `Environment` | **AWS Korea 권장** | `Prod` `Stg` `Dev` `Test` `DR` | (등급 룰 입력) | ● |
| `InventoryCategory` | **AWS Korea 권장** | `WebServer` `WAS` `DB` `Batch` `Bastion` `CICD` `Monitoring` `Log` `Backup` `Auth` `File` `Gateway` | 용도(목적 및 기능) | ● |
| `SeverityLevel` | **AWS Korea 권장** | `1`~`5` | (참고값, 확정 등급 아님) | ○ |
| `HandlePI` | **AWS Korea 권장** | `Y` `N` | 개인정보 포함 여부 | ● |
| `IsPublic` | **AWS Korea 권장** | `Y` `N` | (등급 룰 입력, API 실측과 교차검증) | ○ |
| `OwnerDept` | ISMS-P 확장 | 부서명 | 관리부서 | ● |
| `OwnerManager` | ISMS-P 확장 | 실명/사번 | 관리 실무자(운용자) | ● |
| `OwnerResponsible` | ISMS-P 확장 | 실명/사번 | 관리 책임자 | ● |
| `PIItems` | ISMS-P 확장 | `name,phone,email,rrn,card` | 개인정보 항목 | 조건부 |
| `DataSource` | ISMS-P 확장 | `Self` `ThirdParty` `Entrusted` | 수집 출처 | 조건부 |
| `InScope` | ISMS-P 확장 | `Y` `N` | 인증범위 포함 여부 | ● |
| `ScopeReason` | ISMS-P 확장 | 자유 문자열 | 제외 사유 | 조건부 |
| `ServiceName` | 운영 | 서비스/시스템 명 | 소속 시스템 | ● |

`HandlePI=Y`이면 `PIItems`·`DataSource` 필수, `InScope=N`이면 `ScopeReason` 필수 — 이 조건부 규칙까지 문서에 넣어야 결함사례 2·4를 막는다.

### 2.2 태그 강제 방법 (프로젝트 산출물 "규칙 문서"의 핵심)

| 방식 | 도구 | 성격 |
|---|---|---|
| 사전 예방 | Organizations **태그 정책**, CloudFormation/Terraform 기본 태그, IAM 리소스 수준 조건 | 생성 시점 차단 |
| 사후 탐지 | AWS Config `required-tags` 룰, Resource Groups 준수 보고서, **우리 도구의 갭 리포트** | 미준수 발견 |

**주의 — 태그 정책의 한계를 문서에 명시할 것.** AWS 문서상 태그 정책은 *정의되지 않은 태그나 태그가 아예 없는 리소스는 준수 평가 대상으로 보지 않는다.* 즉 **태그가 하나도 없는 리소스는 태그 정책만으로는 잡히지 않는다.** 그 공백을 메우는 것이 우리 도구의 존재 이유이므로, 발표에서 이 문장을 쓰면 차별점이 선명해진다.

### 2.3 수집 시 함정 — `GetResources`만 쓰면 안 되는 이유

`resourcegroupstaggingapi.get_resources()`는 한 번에 전 서비스 태그 리소스를 긁을 수 있어 편하지만, **태그가 전혀 없는 리소스는 응답에 포함되지 않는다.** 그런데 그게 우리의 주 타깃이다.

```
전수 목록  = 서비스별 describe_* 결과의 합집합   ← 진실
태그 목록  = get_resources() 결과                ← 보조
갭 대상    = 전수 목록 − 태그 목록               ← 갭 리포트의 1행
```

---

## 3. 공통 필드 매핑 (전 시트 공통, 자산 1건마다 채움)

| 대장/계약 필드 | boto3 호출 | 응답 경로 | 값 예시 | 비고 |
|---|---|---|---|---|
| `account_id` | `sts.get_caller_identity()` | `Account` | `123456789012` | **전 레코드 필수.** 없으면 증적 불성립 |
| `account_alias` | `iam.list_account_aliases()` | `AccountAliases[0]` | `corp-prod` | 없으면 null 허용 |
| `region` | `ec2.describe_regions()` 루프 | `Regions[].RegionName` | `ap-northeast-2` | **전 리전 순회 필수** |
| `az` | 서비스별 | `Placement.AvailabilityZone` 등 | `ap-northeast-2a` | 리전 서비스는 null |
| `asset_id` | 서비스별 | ARN 또는 리소스 ID | `arn:aws:ec2:...:instance/i-0abc` | ARN 우선 |
| `asset_name` | 태그 | `Tags[Key=Name].Value` | `prd-web-01` | 없으면 null → 갭 |
| `usage` | 태그 | `Tags[Key=InventoryCategory].Value` | `WebServer` | 없으면 null → 갭 |
| `environment` | 태그 | `Tags[Key=Environment].Value` | `Prod` | 등급 룰 입력값 |
| `owner_dept` / `owner_manager` / `owner_responsible` | 태그 | `OwnerDept` / `OwnerManager` / `OwnerResponsible` | `인프라운영팀` / `김○○` / `박○○` | 3개 모두 갭 대상 |
| `has_personal_info` | 태그 | `HandlePI` → bool | `true` | null이면 미확인 갭 |
| `personal_info_items` | 태그 | `PIItems` 쉼표 분리 | `["name","phone"]` | 안내서 요구 항목 |
| `data_source` | 태그 | `DataSource` | `ThirdParty` | 결함사례 2 |
| `in_scope` / `scope_reason` | 태그 | `InScope` / `ScopeReason` | `Y` / null | 결함사례 4 |
| `lifecycle_state` | 서비스별 | `State.Name`, `DBInstanceStatus` 등 | `running` | diff 폐기 판정 근거 |
| `created_at` | 서비스별 | `LaunchTime`, `InstanceCreateTime`, `CreateTime` | ISO8601 | 세부점검항목 ③ |
| `created_by` | `cloudtrail.lookup_events(LookupAttributes=[{'AttributeKey':'ResourceName','AttributeValue':<id>}])` | `Events[].Username` 또는 `CloudTrailEvent` JSON의 `userIdentity.arn` | `dev-kim` | **관리주체 후보 추론** — 90일 이내만 조회 가능 |
| `tags_raw` | 서비스별 | `Tags` / `TagList` / `tags` 전체 | `{...}` | 감사용. **반출 시 마스킹** |
| `collected_at` / `run_id` | 수집기 | — | ISO8601 / `run-20260727-0930` | diff 기준선 |
| `source_api` | 수집기 | — | `["ec2:DescribeInstances","ec2:DescribeVolumes"]` | **배열** |

> **API 명칭 주의** — 필드명이 서비스마다 다르다. EC2·EBS는 `Tags`(대문자 리스트), RDS는 `TagList`, Lambda·ECR은 `tags`(소문자 dict), S3는 `get_bucket_tagging()` 별도 호출. 파서를 서비스별로 분기해야 한다.

---

## 4. 시트별 boto3 → 필드 매핑

### 4.1 S1 서버 시스템

#### EC2 인스턴스

| 대장 컬럼 | boto3 호출 | 응답 경로 | 값 예시 | 결측 시 |
|---|---|---|---|---|
| 호스트명 | `ec2.describe_instances()` | `Reservations[].Instances[].Tags[Name]` | `prd-web-01` | InstanceId로 대체 + 갭 |
| 자산 일련번호 | 〃 | `.InstanceId` | `i-0a1b2c3d4e5f` | 항상 존재 |
| VM/Hardware | 〃 | `.InstanceType` 접미 `.metal` 여부 + `.Placement.Tenancy` | `VM(t3.large)` / `Bare Metal` / `Dedicated` | 규칙 판정 |
| 모델명 | 〃 | `.InstanceType` | `t3.large` | — |
| OS | `ssm.describe_instance_information()` | `InstanceInformationList[].PlatformName` | `Amazon Linux` | SSM 미설치 시 `ec2 .PlatformDetails` |
| OS버전 | 〃 | `.PlatformVersion` | `2023` | 〃 (`Linux/UNIX`로만 나옴 → 갭) |
| AMI | `ec2.describe_instances()` | `.ImageId` | `ami-0abc123` | 가상자원 시트와 조인 |
| IP | 〃 | `.PrivateIpAddress` | `10.10.1.25` | — |
| 추가IP | `ec2.describe_addresses()` / `describe_instances` | `Addresses[].PublicIp` / `.NetworkInterfaces[].PrivateIpAddresses[]` | `3.35.x.x` | 없으면 `해당없음` |
| 용도 | 태그 `InventoryCategory` | — | `WebServer` | 갭 |
| 설치서버 | 〃 | `account_id` + `Placement.AvailabilityZone` + `Tags[aws:autoscaling:groupName]` | `123456789012 / apne2-a / asg-web` | 온프레의 "하이퍼바이저"를 대체 |
| 위치(상세위치) | 〃 | `region` + `az` | `AWS ap-northeast-2a` | — |
| 상태 | 〃 | `.State.Name` | `running` / `stopped` | **stopped도 목록 유지** |
| 생성일 | 〃 | `.LaunchTime` | ISO8601 | — |

> **서버 수 산정 규칙** — ISMS-P 인증신청서의 유형별 요약표는 가상화 환경에서 **OS 단위**로 세는 것이 원칙이다. 하이퍼바이저 1대에 VM 10대면 10으로 센다. AWS에서는 `describe_instances`의 인스턴스 수가 곧 OS 수이므로 그대로 쓰되, **ECS Fargate 태스크와 Lambda는 OS를 갖지 않으므로 서버 수에 합산하지 말고 별도 행으로 표기**한다. 이 판단을 대장 각주에 남겨야 심사원 질문에 답할 수 있다.

#### ECS / EKS / Lambda

| 대장 컬럼 | boto3 호출 | 응답 경로 |
|---|---|---|
| 클러스터명 | `ecs.list_clusters()` → `ecs.describe_clusters()` | `clusters[].clusterName` |
| 서비스명 | `ecs.list_services()` → `describe_services()` | `services[].serviceName`, `.launchType` (`EC2`/`FARGATE`) |
| 실행 이미지 | `ecs.describe_task_definition()` | `taskDefinition.containerDefinitions[].image` |
| EKS 클러스터 | `eks.list_clusters()` → `describe_cluster()` | `cluster.version`, `.endpoint`, `.resourcesVpcConfig.endpointPublicAccess`, `.logging` |
| Lambda 함수 | `lambda.list_functions()` | `Functions[].FunctionName`, `.Runtime`, `.LastModified`, `.VpcConfig`, `.KMSKeyArn` |
| Lambda 태그 | `lambda.list_tags(Resource=<arn>)` | `Tags` |

`OS` 컬럼은 Fargate·Lambda에서 **`해당없음(Serverless)`**로 채운다. null이 아니다 — §7 참조.

---

### 4.2 S2 WEB Application

| 대장 컬럼 | boto3 호출 | 응답 경로 | 값 예시 |
|---|---|---|---|
| 자산명 | `elbv2.describe_load_balancers()` | `LoadBalancers[].LoadBalancerName` | `prd-portal-alb` |
| VM/Hardware | 〃 | 고정값 | `Managed(ALB)` |
| IP/엔드포인트 | 〃 | `.DNSName` | `prd-portal-alb-...elb.amazonaws.com` |
| 대외 공개 | 〃 | `.Scheme` = `internet-facing` \| `internal` | `internet-facing` |
| 위치 | 〃 | `.AvailabilityZones[].ZoneName`, `.VpcId` | — |
| SW version | `elbv2.describe_listeners()` | `Listeners[].Protocol`, `.Port`, `.SslPolicy` | `HTTPS/443 TLS1.2` |
| 인증서 | 〃 → `acm.describe_certificate()` | `Certificate.NotAfter` | `2027-03-01` |
| WAF 연동 | `wafv2.get_web_acl_for_resource(ResourceArn=)` | `WebACL.Name` | `prd-waf` / 없으면 `미적용` |
| CDN | `cloudfront.list_distributions()` | `DistributionList.Items[].DomainName`, `.Aliases`, `.WebACLId` | — |
| API | `apigateway.get_rest_apis()` / `apigatewayv2.get_apis()` | `items[].name`, `.id` | — |
| 도메인 | `route53.list_hosted_zones()` → `list_resource_record_sets()` | `ResourceRecordSets[].Name` | `www.example.co.kr` |

> **`public_exposed` 오판 방지** — S3 버킷 정책이 비공개여도 CloudFront OAI/OAC로 전 세계 서빙 중일 수 있다. `exposure_path` 필드를 두고 `Direct` / `ALB` / `CloudFront` / `APIGateway` / `None`으로 구분해 기록한다. 이 구분 없이 기밀성 등급을 매기면 제안 전체의 신뢰가 무너진다.

---

### 4.3 S3 WAS

| 대장 컬럼 | boto3 호출 | 응답 경로 |
|---|---|---|
| 호스트명 | `elasticbeanstalk.describe_environments()` | `Environments[].EnvironmentName` |
| SW version | 〃 | `.SolutionStackName` (예: `64bit AL2 v3.x running Tomcat 9`) |
| 상태 | 〃 | `.Health`, `.Status` |
| App Runner | `apprunner.list_services()` → `describe_service()` | `Service.ServiceName`, `.SourceConfiguration` |
| 컨테이너 WAS | `ecs.describe_task_definition()` | `containerDefinitions[].image` (태그로 버전 추출) |
| OS 내 설치 WAS | `ssm.list_inventory_entries(TypeName='AWS:Application')` | `Entries[].Name` / `.Version` (Tomcat 등) |

상용 WAS(WebLogic·JEUS 등)는 **S3 시트와 S10 소프트웨어 시트에 이중 등재**한다. 라이선스 관리 통제와 연결하기 위함이다.

---

### 4.4 S4 DBMS

| 대장 컬럼 | boto3 호출 | 응답 경로 | 값 예시 |
|---|---|---|---|
| DBMS명(종류) | `rds.describe_db_instances()` | `DBInstances[].Engine` + `.EngineVersion` | `aurora-mysql 8.0` |
| 설치서버 호스트명 | 〃 | `.DBInstanceIdentifier` / `.DBClusterIdentifier` | `prd-aurora-01` |
| IP(엔드포인트) | 〃 | `.Endpoint.Address` : `.Endpoint.Port` | `prd.cluster-x.rds.../3306` |
| 다중화 | 〃 | `.MultiAZ` | `true` |
| 암호화 | 〃 | `.StorageEncrypted`, `.KmsKeyId` | `SSE-KMS(CMK)` |
| 백업 | 〃 | `.BackupRetentionPeriod` | `7일` |
| 퍼블릭 노출 | 〃 | `.PubliclyAccessible` | `false` |
| 삭제보호 | 〃 | `.DeletionProtection` | `true` |
| 위치 | 〃 | `.AvailabilityZone`, `.DBSubnetGroup.VpcId` | — |
| 상태/생성일 | 〃 | `.DBInstanceStatus`, `.InstanceCreateTime` | `available` |
| 클러스터 | `rds.describe_db_clusters()` | `DBClusters[].Engine`, `.MultiAZ`, `.BackupRetentionPeriod` | — |
| DynamoDB | `dynamodb.list_tables()` → `describe_table()` | `Table.TableName`, `.SSEDescription.SSEType`, `.CreationDateTime` | — |
| DynamoDB PITR | `dynamodb.describe_continuous_backups()` | `...PointInTimeRecoveryStatus` | `ENABLED` |
| Redshift | `redshift.describe_clusters()` | `Clusters[].Encrypted`, `.PubliclyAccessible` | — |
| ElastiCache | `elasticache.describe_replication_groups()` | `.AtRestEncryptionEnabled`, `.AutomaticFailover` | — |
| OpenSearch | `opensearch.list_domain_names()` → `describe_domain()` | `DomainStatus.EncryptionAtRestOptions` | — |

**개인정보 항목 컬럼은 태그 외 방법이 없다.** 프로젝트 결정 로그 07.20에 따라 스키마 스캔은 범위 밖이므로, `PIItems` 태그를 읽고 없으면 갭으로 처리한다. 보고서에는 "Macie 도입 시 자동 검증 가능"을 조치방안으로 적는다.

---

### 4.5 S5 저장장치·데이터

#### S3

| 대장 컬럼 | boto3 호출 | 응답 경로 |
|---|---|---|
| 자산명 | `s3.list_buckets()` | `Buckets[].Name` |
| 생성일 | 〃 | `Buckets[].CreationDate` |
| 위치 | `s3.get_bucket_location(Bucket=)` | `LocationConstraint` (null이면 `us-east-1`) |
| 암호화 | `s3.get_bucket_encryption(Bucket=)` | `...ApplyServerSideEncryptionByDefault.SSEAlgorithm` (`AES256`/`aws:kms`) |
| 공개 차단 | `s3.get_public_access_block(Bucket=)` | `PublicAccessBlockConfiguration.*` 4개 |
| 공개 여부 | `s3.get_bucket_policy_status(Bucket=)` | `PolicyStatus.IsPublic` |
| 버전관리 | `s3.get_bucket_versioning(Bucket=)` | `Status` = `Enabled` |
| 객체 잠금 | `s3.get_object_lock_configuration(Bucket=)` | `ObjectLockConfiguration.ObjectLockEnabled` |
| 수명주기 | `s3.get_bucket_lifecycle_configuration(Bucket=)` | `Rules[]` |
| 로깅 | `s3.get_bucket_logging(Bucket=)` | `LoggingEnabled` |
| 태그 | `s3.get_bucket_tagging(Bucket=)` | `TagSet[]` |

> **구현 주의 3가지**
> 1. 위 `get_bucket_*` 호출은 설정이 없으면 예외를 던진다 (`ServerSideEncryptionConfigurationNotFoundError`, `NoSuchTagSet`, `NoSuchLifecycleConfiguration` 등). **예외 = 미설정**으로 정규화해야 한다. try/except를 값 판정 로직으로 쓰는 드문 경우다.
> 2. `list_buckets`는 전역이지만 각 버킷은 리전이 다르다. 버킷별 리전으로 클라이언트를 다시 만들어야 일부 호출이 성공한다.
> 3. 계정 수준 차단도 함께 봐야 한다: `s3control.get_public_access_block(AccountId=)`.

#### EBS 볼륨·스냅샷 — 우선순위 최상위

| 대장 컬럼 | boto3 호출 | 응답 경로 | 갭 관점 |
|---|---|---|---|
| 자산명 | `ec2.describe_volumes()` | `Volumes[].VolumeId` | — |
| 연결 상태 | 〃 | `.State` (`in-use` / **`available`**) | **`available` = 미연결 고아 볼륨** |
| 연결 대상 | 〃 | `.Attachments[].InstanceId` | `parent_id`로 사용 |
| 크기/암호화 | 〃 | `.Size`, `.Encrypted`, `.KmsKeyId` | 기밀성 룰 입력 |
| 생성일 | 〃 | `.CreateTime` | — |
| 스냅샷 | `ec2.describe_snapshots(OwnerIds=['self'])` | `Snapshots[].SnapshotId`, `.VolumeId`, `.StartTime`, `.Encrypted` | 원본 등급 상속 대상 |

`OwnerIds=['self']`를 빼면 공개 스냅샷 수만 건이 딸려온다. 반드시 지정한다.

미연결 볼륨과 수년 묵은 스냅샷이 **결함사례 5(백업 등급 저평가)**의 직접 대상이고, 데모에서 가장 잘 먹히는 장면이다 — "관리자가 존재조차 모르는 볼륨 N개".

#### EFS / Backup

| 항목 | 호출 | 경로 |
|---|---|---|
| EFS | `efs.describe_file_systems()` | `FileSystems[].FileSystemId`, `.Encrypted`, `.KmsKeyId`, `.LifeCycleState` |
| 백업 플랜 | `backup.list_backup_plans()` → `get_backup_plan()` | `BackupPlan.Rules[].ScheduleExpression`, `.Lifecycle` |
| **보호 대상** | `backup.list_protected_resources()` | `Results[].ResourceArn` | ← **`backup_exists` 판정의 정답 소스** |
| 복구 지점 | `backup.list_recovery_points_by_resource(ResourceArn=)` | `RecoveryPoints[].CreationDate` |

> **`backup_exists`를 스냅샷 존재 여부로 판정하면 안 된다.** "스냅샷 3개 있음"은 심사에서 반박당하지만 "AWS Backup 플랜 `daily-prd`에 포함되어 일 1회 보호 중"은 통과한다. `backup_source` 필드에 근거 문자열을 함께 저장한다.

---

### 4.6 S6 가상자원 (CSAP 부적합 "골든 이미지 미식별" 대응)

| 대장 컬럼 | boto3 호출 | 응답 경로 |
|---|---|---|
| AMI | `ec2.describe_images(Owners=['self'])` | `Images[].ImageId`, `.Name`, `.CreationDate`, `.State` |
| AMI 암호화 | 〃 | `.BlockDeviceMappings[].Ebs.Encrypted` |
| ECR 리포지토리 | `ecr.describe_repositories()` | `repositories[].repositoryName`, `.repositoryUri`, `.imageTagMutability` |
| ECR 스캔 설정 | 〃 | `.imageScanningConfiguration.scanOnPush` |
| ECR 암호화 | 〃 | `.encryptionConfiguration.encryptionType` |
| 이미지 | `ecr.describe_images(repositoryName=)` | `imageDetails[].imageTags`, `.imagePushedAt`, `.imageSizeInBytes` |
| **실행 주체** | `ecs.describe_task_definition()` / `ec2.describe_instances()` | 이미지 URI ↔ 컨테이너 정의, AMI ID ↔ 인스턴스 | ← 조인 필수 |

**이미지만 수집하고 실행 주체를 안 보면 대응 논리가 절반만 완성된다.** 이미지↔실행주체 매핑이 있어야 "운영 중 이미지"와 "방치된 미사용 이미지"를 구분할 수 있고, 그래야 등급이 달라진다. `parent_id` / `relation_type='runs_on'`으로 연결한다.

---

### 4.7 S7 네트워크

| 대상 | boto3 호출 | 주요 필드 |
|---|---|---|
| VPC | `ec2.describe_vpcs()` | `VpcId`, `CidrBlock`, `IsDefault` |
| Subnet | `ec2.describe_subnets()` | `SubnetId`, `CidrBlock`, `AvailabilityZone`, `MapPublicIpOnLaunch` |
| Route Table | `ec2.describe_route_tables()` | `RouteTableId`, `Routes[].GatewayId` |
| IGW / NAT | `ec2.describe_internet_gateways()` / `describe_nat_gateways()` | `InternetGatewayId` / `NatGatewayId`, `.State` |
| TGW / VPN | `ec2.describe_transit_gateways()` / `describe_vpn_connections()` | `TransitGatewayId` / `VpnConnectionId`, `.State` |
| Direct Connect | `directconnect.describe_connections()` | `connections[].connectionId`, `.bandwidth` |
| **보안그룹** | `ec2.describe_security_groups()` | `GroupId`, `IpPermissions[].IpRanges[].CidrIp` |
| NACL | `ec2.describe_network_acls()` | `NetworkAclId`, `Entries[]` |
| VPC Flow Logs | `ec2.describe_flow_logs()` | `FlowLogId`, `.ResourceId`, `.LogDestination` |

**`open_sg_rule` 판정 로직** — `IpPermissions[]`를 순회하며 `IpRanges[].CidrIp == '0.0.0.0/0'` 또는 `Ipv6Ranges[].CidrIpv6 == '::/0'`인 규칙을 찾는다. 포트도 함께 기록(`FromPort`~`ToPort`)해야 근거 문구가 구체적으로 나온다: *"SG sg-0abc에 0.0.0.0/0 → 22/tcp 인바운드 허용"*.

---

### 4.8 S8 보안시스템 (결함사례 1 대응)

안내서 자산 유형표는 "보안시스템: 침입차단시스템, 침입탐지시스템, 침입방지시스템, 개인정보유출방지시스템 등"을 명시적으로 요구한다. 현재 수집 범위에 이 유형이 통째로 빠져 있으면 **결함사례 1에 그대로 걸린다.**

| 자산 | boto3 호출 | 활성 판정 |
|---|---|---|
| WAF | `wafv2.list_web_acls(Scope='REGIONAL')` + `Scope='CLOUDFRONT'` | ACL 존재 + `list_resources_for_web_acl` 연결 대상 |
| Shield Advanced | `shield.describe_subscription()` | 구독 여부 |
| GuardDuty | `guardduty.list_detectors()` → `get_detector()` | `Status == 'ENABLED'` |
| Inspector | `inspector2.batch_get_account_status()` | `accounts[].state.status` |
| Security Hub | `securityhub.describe_hub()` + `get_enabled_standards()` | 예외 발생 시 미활성 |
| Network Firewall | `network-firewall.list_firewalls()` | 존재 여부 |
| Macie | `macie2.get_macie_session()` | `status == 'ENABLED'` |
| KMS | `kms.list_keys()` → `describe_key()` | `KeyManager == 'CUSTOMER'`만 자산 등재 |
| ACM | `acm.list_certificates()` → `describe_certificate()` | `NotAfter` (가용성 근거) |
| Secrets Manager | `secretsmanager.list_secrets()` | `RotationEnabled`, `LastRotatedDate` |
| Parameter Store | `ssm.describe_parameters()` | `Type == 'SecureString'` |
| CloudTrail | `cloudtrail.describe_trails()` + `get_trail_status()` | `IsMultiRegionTrail`, `LogFileValidationEnabled`, `KmsKeyId` |
| Config | `config.describe_configuration_recorders()` + `describe_configuration_recorder_status()` | `recording == true` |
| IAM | `iam.list_users()` / `list_roles()` / `get_account_password_policy()` | 계정 자산 |

> **AWS로 덮이지 않는 것을 명시할 것** — 출력물 보안, 문서암호화, USB 매체제어는 여전히 온프레 엔드포인트 영역이다. S11 시트에 수기로 등재하고, 없으면 갭으로 리포트한다. 결함사례 1은 클라우드 API로 해결되지 않는다.

---

### 4.9 S9 PC / 4.10 S10 오픈 소프트웨어

| 대상 | 호출 | 필드 |
|---|---|---|
| WorkSpaces | `workspaces.describe_workspaces()` | `Workspaces[].WorkspaceId`, `.UserName`, `.ComputerName`, `.IpAddress`, `.State`, `.WorkspaceProperties` |
| SSM 관리 인스턴스 | `ssm.describe_instance_information()` | `PlatformType`, `PlatformName`, `PlatformVersion`, `IpAddress`, `ComputerName`, `AgentVersion`, `LastPingDateTime` |
| **설치 소프트웨어** | `ssm.list_inventory_entries(InstanceId=, TypeName='AWS:Application')` | `Entries[].Name`, `.Version`, `.Publisher`, `.InstalledTime` |
| 패치 상태 | `ssm.describe_instance_patch_states()` | `InstancePatchStates[].MissingCount`, `.CriticalNonCompliantCount` |
| 라이선스 | `license-manager.list_license_configurations()` | `LicenseConfigurations[].Name`, `.LicenseCount` |

`ssm.get_inventory()`로 전 인스턴스 요약을, `list_inventory_entries()`로 인스턴스별 상세를 얻는다. 오픈SW 시트의 `수량` 컬럼은 동일 `Name`+`Version` 그룹의 인스턴스 수로 자동 집계한다.

**라이선스 컬럼 추가 권고** — 원본 양식에는 없지만 GPL/AGPL 계열이 상용 서비스에 포함되면 법적 리스크다. SSM Inventory는 라이선스를 주지 않으므로 수기 보완 항목으로 둔다.

---

### 4.11 S11 기타·위탁 (결함사례 4 대응)

API로 수집 불가. **수기 입력 시트로 두되 도구가 템플릿을 생성**한다.

| `구분` | 예시 | 필수 기재 |
|---|---|---|
| 위탁 IT 서비스 | 웹호스팅, 서버호스팅, MSP 운영대행, PG | 수탁사명, 계약기간, 위탁 업무 범위, 개인정보 위탁 여부 |
| 외부 SaaS | Slack, Notion, Jira, GitHub, Datadog, Sentry | 저장 데이터 성격, 계정 수, 데이터 리전 |
| 문서적 정보 | 계약서, 서면동의서, 출력물 | 보관 위치, 보관 기간 |
| 설비·시설 | 전산실, UPS, 출입통제, CCTV | **AWS 책임영역 → Artifact 보고서로 대체, 제외 사유 필수 기재** |
| 온프레 유출통제 | 출력물 보안, 문서암호화, USB 통제, DLP | 결함사례 1 대응 |

설비·시설을 사유 없이 비워두면 그 자체가 결함이다. `in_scope=N` + `scope_reason="책임공유모델상 CSP 책임영역, AWS Artifact ISO 27001·SOC 2 보고서 첨부"`로 채운다.

---

## 5. `infra_facts` 수집 명세 (등급 룰의 입력값)

데이터 계약에서 이 객체의 키를 못 박지 않으면 B가 룰을 짤 수 없다. 1주차에 확정할 것.

| 키 | 타입 | 수집원 | 판정 규칙 |
|---|---|---|---|
| `backup_exists` | bool | `backup.list_protected_resources()` | ARN이 목록에 있으면 true |
| `backup_source` | str/null | 〃 + `get_backup_plan()` | `"AWS Backup plan: daily-prd"` |
| `snapshot_count` | int | `describe_snapshots` / `describe_db_snapshots` | 개수 |
| `pitr_enabled` | bool/null | RDS `BackupRetentionPeriod>0`, DynamoDB `PointInTimeRecoveryStatus` | — |
| `multi_az` | bool/null | RDS `.MultiAZ`, ELB `.AvailabilityZones` 길이≥2 | 해당 없으면 null |
| `in_asg` | bool | `Tags[aws:autoscaling:groupName]` 존재 | — |
| `public_exposed` | bool | EC2 `PublicIpAddress`, RDS `PubliclyAccessible`, S3 `IsPublic`, ELB `Scheme` | — |
| `exposure_path` | enum/null | `Direct`/`ALB`/`CloudFront`/`APIGateway`/`None` | 오판 방지 |
| `encryption_at_rest` | enum | `None`/`SSE-S3`/`SSE-KMS-AWS`/`SSE-KMS-CMK` | KMS `KeyManager`로 CMK 구분 |
| `encryption_in_transit` | bool/null | 리스너 `Protocol` in (HTTPS,TLS), RDS 파라미터그룹 | — |
| `open_sg_rule` | bool | `describe_security_groups` 0.0.0.0/0 존재 | 포트도 별도 저장 |
| `open_sg_detail` | list | 〃 | `["sg-0abc:22/tcp"]` |
| `versioning_enabled` | bool/null | S3 `get_bucket_versioning` | — |
| `object_lock` | bool/null | S3 `get_object_lock_configuration` | 증적 불변성 |
| `logging_enabled` | bool | CloudTrail/S3 access log/VPC Flow Log | — |
| `deletion_protection` | bool/null | RDS `.DeletionProtection` | — |
| `state` | str | 서비스별 상태 필드 | — |

---

## 6. 보안등급 룰 카탈로그

### 6.1 채점 체계 (법령·TTA 공통)

정보자산관리지침 제7~8조와 TTA 기준이 동일하게 규정한다.

- 기밀성·무결성·가용성 각각 **1(하) / 2(중) / 3(상)**
- **보안등급 = C + I + A** (3~9점)
- 합계 분포로 등급 결정

| 합계 | 중요도 | 대장 표기 |
|---|---|---|
| 8~9 | H (상) | 1등급 |
| 5~7 | M (중) | 2등급 |
| 3~4 | L (하) | 3등급 |

각 축의 정성 정의(그대로 대장 각주에 인용 가능):
- **기밀성 3** — 조직 내부에서도 특별히 허가받은 사람만 열람 가능하며, 외부 공개 시 프라이버시나 사업에 치명적 피해
- **무결성 3** — 고의·우연히 변경될 경우 프라이버시나 사업에 치명적 피해
- **가용성 3** — 서비스 중단 시 조직 운영·사업에 치명적 피해

### 6.2 룰 테이블 — `rule_id` 체계

근거 문자열을 자유 텍스트로 두면 재현성과 감사 가능성이 없다. 모든 제안은 `rule_id`를 달고, 보고서 부록에 이 표를 그대로 붙인다.

#### 기밀성 (C)

| rule_id | 조건 | 제안 | 근거 문구 템플릿 |
|---|---|---|---|
| `C-01` | `has_personal_info == true` | 3 | 개인정보 보유 자산(법적 요구사항: 개인정보보호법). 항목: {personal_info_items} |
| `C-02` | `personal_info_items`에 `rrn`/`card` 포함 | 3 (고정) | 고유식별정보·신용정보 보유. 하향 조정 불가 |
| `C-03` | `public_exposed == true` AND `encryption_at_rest == None` | 3 | 외부 노출({exposure_path}) 상태에서 저장 데이터 미암호화 |
| `C-04` | `encryption_at_rest == None` (비공개) | 2 | 저장 데이터 미암호화 |
| `C-05` | `open_sg_rule == true` | +1 (최대 3) | 전체 개방 인바운드 규칙 존재: {open_sg_detail} |
| `C-06` | `encryption_at_rest == SSE-KMS-CMK` AND `has_personal_info == false` AND `public_exposed == false` | 1 | 내부 전용 + 고객관리형 키 암호화 |
| `C-07` | `usage` in (`StaticContent`,`PublicWeb`) AND `has_personal_info == false` | 1 | 공개가 의도된 자산 |
| `C-99` | `has_personal_info == null` | **제안 보류** | 개인정보 보유 여부 미확인 — 담당자 확인 필요 |

#### 무결성 (I)

| rule_id | 조건 | 제안 | 근거 문구 템플릿 |
|---|---|---|---|
| `I-01` | `backup_exists == false` AND `snapshot_count == 0` | 3 | **실시간 백업이 이루어지고 있지 않아 원본 정보 복구가 곤란** (정보자산관리지침 무결성 상 조건) |
| `I-02` | `backup_exists == false` AND `snapshot_count > 0` | 2 | 수동 스냅샷만 존재, 백업 정책 미포함 |
| `I-03` | `backup_exists == true` | 1 | {backup_source}에 포함되어 정기 보호 중 |
| `I-04` | S3 AND `versioning_enabled == false` | +1 | 버전관리 미사용으로 덮어쓰기 복구 불가 |
| `I-05` | 로그 자산 AND `object_lock == false` | +1 | 증적 로그에 객체 잠금 미적용 |
| `I-06` | CloudTrail AND `LogFileValidationEnabled == false` | 3 | 로그파일 무결성 검증 미사용 |

`I-01`의 근거 문구는 법령 부록 지침의 무결성 "상" 판정 조건을 그대로 옮긴 것이다. **인프라 상태로 기계 판정이 가능한 몇 안 되는 법령 조건**이고, 이 프로젝트의 등급 자동화가 정당화되는 핵심 근거다.

#### 가용성 (A)

| rule_id | 조건 | 제안 | 근거 문구 템플릿 |
|---|---|---|---|
| `A-01` | `multi_az == false` AND `in_asg == false` | 3 | 다중화·자동확장 미구성으로 **대체 자산 부재** |
| `A-02` | `multi_az` XOR `in_asg` | 2 | 부분 다중화 구성 |
| `A-03` | `multi_az == true` AND `in_asg == true` | 1 | Multi-AZ + Auto Scaling 이중화 |
| `A-04` | `environment == Prod` | +1 (최대 3) | 운영 환경 |
| `A-05` | `environment` in (`Dev`,`Test`) | -1 (최소 1) | 비운영 환경 |
| `A-06` | ACM 인증서 만료 30일 이내 | 3 | 인증서 만료 임박({NotAfter}) |
| `A-07` | `deletion_protection == false` AND `environment == Prod` | +1 | 운영 자산에 삭제 방지 미설정 |

`A-04`/`A-05`가 등급 정확도를 가장 크게 올린다. 개발 서버와 운영 서버의 가용성 등급이 같을 수 없다.

#### 상속 룰 (결함사례 5 대응)

| rule_id | 조건 | 동작 |
|---|---|---|
| `X-01` | `relation_type == 'backup_of'` 또는 `'snapshot_of'` | 원본의 **C 등급을 그대로 상속**. 하향 불가 |
| `X-02` | `relation_type == 'image_of'` (AMI/ECR) | 원본 서버의 C 등급 상속 |
| `X-03` | 원본이 미식별 상태 | 상속 불가 → 갭 처리 |

> "고유식별정보를 저장하는 백업서버의 기밀성 등급을 (하)로 산정" — 결함사례 5의 문구 그대로다. `X-01`이 이걸 막는 장치이며, **지침 문서에 "사본은 원본 등급을 상속한다"를 명문화**해야 룰과 지침이 일치한다(결함사례 3 예방).

### 6.3 출력 스키마

```json
"grade_proposed": {
  "c": {"level": 3, "rule_ids": ["C-01", "C-05"],
        "evidence": "개인정보 보유 자산(항목: name, phone). SG sg-0abc에 0.0.0.0/0 → 3306/tcp 인바운드 허용"},
  "i": {"level": 2, "rule_ids": ["I-02"],
        "evidence": "수동 스냅샷 3건만 존재, AWS Backup 플랜 미포함"},
  "a": {"level": 3, "rule_ids": ["A-01", "A-04"],
        "evidence": "Multi-AZ 미구성, ASG 미소속으로 대체 자산 부재. 운영(Prod) 환경"},
  "total": 8, "grade": "1등급",
  "ruleset_version": "v1.0", "proposed_at": "2026-07-27T09:30:00+09:00"
},
"grade_confirmed": null
```

`ruleset_version` 없이 과거 스냅샷과 등급을 비교하면 사과와 오렌지를 비교하게 된다.

---

## 7. `asset_type`별 필수 필드 프로파일 — null의 두 종류

**v0.1 데이터 계약의 가장 큰 결함**: "태그가 없으면 null, null은 갭 리포트의 한 행"이라는 원칙은 그대로는 작동하지 않는다. null에는 두 종류가 있다.

| 종류 | 의미 | 예시 | 갭 리포트 |
|---|---|---|---|
| `MISSING` | 있어야 하는데 없음 | EC2에 `OwnerDept` 태그 없음 | **행으로 출력** |
| `N/A` | 이 자산 유형에 개념이 없음 | S3 버킷의 `ip_private` | 출력하지 않음 |

이 구분이 없으면 갭 리포트가 "S3 버킷 IP 미확인" 같은 행으로 채워지고, 리포트 전체의 신뢰가 무너진다.

| asset_type | 필수(MISSING 판정) | N/A (갭 제외) |
|---|---|---|
| 서버 | asset_name, usage, owner_dept, owner_manager, owner_responsible, ip_private, os, in_scope | endpoint, personal_info_items(단 has_personal_info=false일 때) |
| 응용프로그램 | asset_name, usage, owner_*, endpoint, public_exposed | ip_private, os(관리형인 경우) |
| 저장장치(DBMS) | asset_name, endpoint, usage, owner_*, has_personal_info, encryption_at_rest | ip_private, os |
| 저장장치(오브젝트) | asset_name, usage, owner_*, has_personal_info, encryption_at_rest, public_exposed | ip_*, os, multi_az |
| 가상자원 | asset_name, owner_dept, parent_id(실행주체) | ip_*, endpoint, multi_az |
| 네트워크장비 | asset_id, owner_dept, in_scope | os, has_personal_info, backup_exists |
| 보안시스템 | asset_name, owner_dept, owner_responsible, state | ip_*, has_personal_info |
| PC | asset_name, os, ip, 사용자 | endpoint, multi_az |
| 소프트웨어 | asset_name, version, 수량, owner_dept | ip_*, encryption_at_rest |

계약 JSON에는 다음처럼 명시적으로 표기한다.

```json
"network": { "ip_private": {"value": null, "reason": "N/A"} },
"owner_dept": { "value": null, "reason": "MISSING" }
```

또한 `ip_private`/`ip_public`을 최상위에 두지 말고 `network` 객체로 내린다. S3·ECR·AMI·KMS에는 IP 개념이 없기 때문이다.

---

## 8. 갭 리포트 정의 (세부점검항목 3문항 축)

| 축 | 갭 항목 | 판정식 | 출력 문구 예시 |
|---|---|---|---|
| ① 식별·목록 | 태그 전무 자산 | 전수목록 − `get_resources()` 결과 | 태그가 전혀 없는 자산 12건 |
| ① | 자산명 미지정 | `Name` 태그 없음 | 자산명 미지정 8건 |
| ① | 인증범위 미판정 | `in_scope == null` | 범위 판정 미완료 34건 |
| ① | 미연결 고아 자산 | EBS `State=available`, EIP 미연결 | 미연결 볼륨 7건(총 340GB) |
| ① | 보안시스템 유형 부재 | S8 시트 행 수 == 0 | **유출통제 시스템 미식별 → 결함사례 1** |
| ② | 관리주체 미식별 | `owner_dept` 또는 `owner_responsible` MISSING | **관리주체 미식별 자산 40%** |
| ② | 개인정보 여부 미확인 | `has_personal_info == null` | 개인정보 보유 여부 미확인 21건 |
| ② | 등급 제안 보류 | `C-99` 발동 | 등급 산정 불가 21건 |
| ② | 등급 미확정 | `grade_confirmed == null` | 사람 확정 대기 156건 |
| ③ | 최신성 | 마지막 실사일 초과 | 최종 확인 후 200일 경과 |
| ③ | 신규 미등록 | diff 신규 AND 태그 없음 | 신규 도입 후 미등록 5건 |

### 8.1 차별화 기능 — 담당자 후보 제시

갭 리포트가 "미식별 40%"라는 진단에서 멈추면 진단서일 뿐이다. `created_by`를 붙이면 처방전이 된다.

```
관리주체 미식별: 40% (62/156)
  ├ 생성자 추적 가능: 32% (50건) → CloudTrail 기준 담당자 후보 제시
  └ 추적 불가(90일 초과): 8% (12건) → 수기 조사 필요
```

`cloudtrail.lookup_events()`는 **90일** 이내만 조회 가능하다. 이 제약을 리포트에 명시해야 신뢰를 얻는다.

---

## 9. diff 정의 (세부점검항목 ③)

`asset_id` 기준 집합 연산. 반나절 작업이므로 **2주차로 앞당길 것.**

| 판정 | 정의 | 대장 반영 |
|---|---|---|
| 신규 도입 | `asset_id ∈ B − A` | 행 추가, `lifecycle_state=신규` |
| 폐기 | `asset_id ∈ A − B` | **행 삭제 금지.** `lifecycle_state=폐기`로 표기 + 폐기일 |
| 변경 | 교집합 중 감시 필드 차이 | 변경 전/후 값 병기 |
| 무변동 | 나머지 | — |

**변경 감시 필드**(전체 diff는 노이즈가 많다): `instance_type`, `os_version`, `ip_*`, `public_exposed`, `encryption_at_rest`, `backup_exists`, `multi_az`, `owner_*`, `has_personal_info`, `in_scope`, `open_sg_rule`, `state`

> **중지된 인스턴스를 대장에서 지우면 "목록과 실제 현황 불일치" 결함이 된다.** 폐기는 삭제가 아니라 상태 전이로 표현한다.

전 리전 순회는 수집에 수 분이 걸려 `collected_at`이 레코드마다 달라진다. diff 기준선은 `run_id`로 잡는다.

---

## 10. 최소권한 IAM 정책

보안 도구가 고객 계정에 붙는다. `ReadOnlyAccess` 대신 필요한 액션만 담은 정책을 **산출물로 제공**하면 그 자체가 역량 증거가 된다.

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "ISMSPAssetInventoryReadOnly",
    "Effect": "Allow",
    "Action": [
      "sts:GetCallerIdentity", "iam:ListAccountAliases",
      "ec2:Describe*",
      "rds:Describe*", "rds:ListTagsForResource",
      "s3:ListAllMyBuckets", "s3:GetBucketLocation", "s3:GetBucketTagging",
      "s3:GetEncryptionConfiguration", "s3:GetBucketPublicAccessBlock",
      "s3:GetBucketPolicyStatus", "s3:GetBucketVersioning",
      "s3:GetBucketLogging", "s3:GetLifecycleConfiguration",
      "s3:GetBucketObjectLockConfiguration",
      "ecr:DescribeRepositories", "ecr:DescribeImages", "ecr:ListTagsForResource",
      "ecs:List*", "ecs:Describe*", "eks:List*", "eks:Describe*",
      "lambda:ListFunctions", "lambda:ListTags",
      "elasticloadbalancing:Describe*",
      "cloudfront:List*", "apigateway:GET", "route53:List*",
      "dynamodb:ListTables", "dynamodb:DescribeTable",
      "dynamodb:DescribeContinuousBackups", "dynamodb:ListTagsOfResource",
      "elasticfilesystem:Describe*", "backup:List*", "backup:Get*",
      "kms:ListKeys", "kms:DescribeKey", "kms:ListAliases",
      "acm:ListCertificates", "acm:DescribeCertificate",
      "secretsmanager:ListSecrets", "ssm:Describe*", "ssm:GetInventory",
      "ssm:ListInventoryEntries",
      "wafv2:List*", "wafv2:Get*", "guardduty:List*", "guardduty:Get*",
      "inspector2:BatchGetAccountStatus", "securityhub:Describe*",
      "securityhub:GetEnabledStandards", "macie2:GetMacieSession",
      "network-firewall:ListFirewalls",
      "cloudtrail:DescribeTrails", "cloudtrail:GetTrailStatus",
      "cloudtrail:LookupEvents",
      "config:Describe*", "config:SelectResourceConfig",
      "tag:GetResources", "tag:GetTagKeys",
      "resource-explorer-2:Search", "resource-explorer-2:ListViews",
      "directconnect:Describe*", "workspaces:Describe*",
      "elasticbeanstalk:Describe*", "apprunner:List*", "apprunner:Describe*",
      "redshift:Describe*", "elasticache:Describe*", "es:Describe*",
      "es:ListDomainNames", "autoscaling:Describe*",
      "license-manager:List*", "shield:DescribeSubscription",
      "organizations:ListAccounts", "organizations:DescribeOrganization"
    ],
    "Resource": "*"
  }]
}
```

`SecurityAudit` + `ViewOnlyAccess` 관리형 정책 조합에서 출발해 실제 호출 액션으로 좁힌 결과다. `cloudtrail:LookupEvents`는 조회량이 많으므로 별도 Sid로 분리해 옵션화하는 것도 방법이다.

---

## 11. 심사 대응 체크리스트

스마일샤크가 정리한 증적 4원칙에 우리 도구를 대응시킨 것이다.

| 원칙 | 요구 | 도구의 대응 | 확인 |
|---|---|---|---|
| **연속성** | 시점 스냅샷이 아닌 축적된 기록 | 주 1회 이상 자동 실행, 스냅샷 JSON 보관 | ☐ 3개월 이상 이력 |
| **자동화** | 수작업 수집은 누락·오류 불가피 | 수집 → 갭 탐지 → 알림 파이프라인 | ☐ "탐지→조치" 기록 |
| **문서-실제 일치** | 지침의 분류기준 = 대장의 분류기준 | 태그 표준 문서 ↔ 룰 카탈로그 1:1 | ☐ **결함사례 3 예방** |
| **변경 불가능성** | 증적 위·변조 방지 | 스냅샷을 Object Lock 버킷에 보관 | ☐ 권장사항 |

### 추가 확인

- ☐ 전 리전 순회 여부 (미사용 리전 방치가 누락 1순위)
- ☐ 계정ID·리전·캡처일시가 화면 증적에 함께 보이는가
- ☐ 설비·시설 제외 사유가 기재되어 있는가 (AWS Artifact 보고서 첨부)
- ☐ 온프레 유출통제 시스템(출력물·문서암호화·USB)이 목록에 있는가
- ☐ 백업·스냅샷이 원본 등급을 상속하는가
- ☐ **스냅샷 JSON을 깃허브에 올리지 않는가** — 태그 값에 담당자 이메일·전화번호가 들어 있는 경우가 흔하다. 개인정보 관리 도구가 스스로 개인정보 파일을 만드는 사고를 피할 것. `.gitignore` 등록 + 반출 시 마스킹 옵션

---

## 부록 A. AWS 서비스 → KISA 자산분류 전체 매핑

| KISA 자산유형 (안내서) | AWS 서비스 | 시트 |
|---|---|---|
| 서버 | EC2, ECS, EKS, Lambda, Lightsail, ASG | S1 |
| 데이터(DBMS) | RDS, Aurora, DynamoDB, Redshift, ElastiCache, DocumentDB, OpenSearch | S4 |
| 정보시스템(응용프로그램) | ALB/NLB, CloudFront, API Gateway, Beanstalk, App Runner | S2, S3 |
| 소프트웨어 | SSM Inventory 수집 패키지, ECR 이미지 레이어, Marketplace 구독 | S10 |
| 네트워크장비 | VPC, Subnet, RTB, IGW, NAT, TGW, VPN, DX, SG, NACL | S7 |
| 보안시스템 | WAF, Shield, GuardDuty, Inspector, Security Hub, Network Firewall, Macie, KMS, ACM, Secrets Manager, IAM, CloudTrail, Config | S8 |
| PC | WorkSpaces + 온프레 단말 | S9 |
| 정보(전자적) | S3, EBS, EFS, FSx, Backup Vault, 스냅샷 | S5 |
| 정보(문서적) | (오프라인) 계약서, 서면동의서, 출력물 | S11 |
| 가상자원 (CSAP 추가) | AMI, ECR 이미지, EBS 스냅샷 | S6 |
| 설비·시설 | **CSP 책임영역 → 제외 + Artifact 보고서** | S11 |

## 부록 B. 코드값 도메인

| 항목 | 허용값 |
|---|---|
| `asset_type` | 서버 / 저장장치(DBMS) / 저장장치 / 응용프로그램 / 소프트웨어 / 네트워크장비 / 보안시스템 / PC / 가상자원 / 기타 |
| `environment` | Prod / Stg / Dev / Test / DR |
| `lifecycle_state` | 도입예정 / 운영중 / 변경중 / 사용중지 / 폐기완료 |
| `관리형태` | 자체보유·운영 / 임차 / 위탁운영(MSP) / 클라우드 종량제 / 구독(SaaS) / 무상(오픈소스) |
| `data_source` | Self / ThirdParty / Entrusted |
| `relation_type` | backup_of / snapshot_of / image_of / runs_on / attached_to |
| `encryption_at_rest` | None / SSE-S3 / SSE-KMS-AWS / SSE-KMS-CMK |
| `exposure_path` | Direct / ALB / CloudFront / APIGateway / None |
| `보안등급` | 1등급(H, 8~9) / 2등급(M, 5~7) / 3등급(L, 3~4) |

## 부록 C. 출처 목록 (보고서 인용용)

**규제기관**
1. 한국인터넷진흥원, 「정보보호 및 개인정보보호 관리체계(ISMS-P) 인증기준 안내서」 — 1.2.1 정보자산 식별
2. 한국인터넷진흥원, 「ISMS-P 인증기준 세부점검항목」 — 1.2.1 점검 3문항
3. 한국인터넷진흥원, CSAP 정보자산목록 예시 양식 `03_정보자산목록.hwp`
4. 한국인터넷진흥원 지역정보보호센터, ICT중소기업 정보보호 컨설팅 자산관리대장 작성 양식·가이드
5. 한국인터넷진흥원, 클라우드서비스 보안인증 제도 안내 (인증범위: 자산·조직·지원서비스 포함)

**법령·준표준**

6. 국가법령정보센터, 「정보자산관리지침」 (정보자산 중요도 평가 제7조 / 보안등급 제8조 — CIA 각 1~3점 합산)
7. 한국정보통신기술협회(TTA), 정보자산 분류 기준 및 중요도 평가 기준

**기업 실무 (5개사 이상)**

8. **AWS Korea** 기술블로그, 「AWS Systems Manager와 Amazon Inspector로 Amazon EC2 자산 관리 자동화 하기」(2023.06) — ISMS·CSAP 대응 태그 5종
9. **스마일샤크**(ISMS-P 인증 취득, AWS Premier Tier Partner), 「ISMS-P 클라우드 증적자료 AWS 환경 실무 가이드」(2026.06)
10. **SK쉴더스 EQST**, 「AWS 클라우드 환경 내 ISMS 주요 인증항목 구현 전략」
11. **베스핀글로벌**, 「AWS Control Tower ISMS-P 인증 대응(적용 사례, Config 정책)」
12. **LG CNS**, 「정보보안의 첫 스텝, 정보자산 식별하기」
13. **메가존클라우드**, ISMS 인증 컨설팅 프로세스

**벤더 문서**

14. AWS Organizations 태그 정책 / 태그 정책 모범 사례
15. AWS 백서, 「AWS 리소스 태그 지정 모범 사례」(2023.03)
16. AWS 백서, 「AWS 보안 모범 사례」 — ISMS 자산 정의와 책임공유모델

---

*본 명세서는 공개 자료 기반으로 작성되었으며, 실제 인증심사 적용 전 KISA 최신 안내서와 심사기관 협의를 거쳐야 한다. 인증기준·양식·법령은 개정될 수 있다.*
