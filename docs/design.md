# ISMS-P 1.2.1 정보자산 식별 — AWS 자산 수집 설계서

**버전** v2.0
**범위** ① 필요 자산 목록 확정 → ② AWS 서비스 매핑 → ③ boto3 추출 방법
**원칙** 공적 레퍼런스(규제기관 고시·안내서, 법령, AWS 공식 문서)만 인용. 개인 블로그·기업 기술블로그·GitHub 저장소 미인용.

---

## 목차

- [0. 참고 자료](#0-참고-자료)
- [1단계. ISMS-P 문서 기준 자산 목록 확정](#1단계-isms-p-문서-기준-자산-목록-확정)
- [2·3단계. AWS 서비스별 매핑 + boto3 추출](#23단계-aws-서비스별-매핑--boto3-추출)
  - [A. 계정·범위 식별](#a-계정범위-식별)
  - [B. 서버](#b-서버)
  - [C. 데이터(DBMS)](#c-데이터dbms)
  - [D. 정보(전자적)·저장장치](#d-정보전자적저장장치)
  - [E. 정보시스템(응용프로그램)](#e-정보시스템응용프로그램)
  - [F. 소프트웨어](#f-소프트웨어)
  - [G. 네트워크장비](#g-네트워크장비)
  - [H. 보안시스템](#h-보안시스템)
  - [I. PC](#i-pc)
  - [J. 가상자원](#j-가상자원)
  - [K. 횡단 기능](#k-횡단-기능)
- [4. 수집 불가·검증 필요 항목 총괄](#4-수집-불가검증-필요-항목-총괄)
- [5. 전체 구조 설계](#5-전체-구조-설계)

---

## 0. 참고 자료

### 0.1 인용 자료 (전부 하이퍼링크)

| 구분 | 자료 | 링크 |
|---|---|---|
| 규제기관 | ISMS-P 인증제도 공식 홈페이지 | <https://isms-p.or.kr/> |
| 규제기관 | ISMS-P 자료실 (인증기준 안내서·세부점검항목·신청 양식 배포처) | <https://isms-p.or.kr/ntcn/rcsrm/selectGnrlRcsrmList.do> |
| 규제기관 | KISA ISMS-P 인증제도 안내서 (PDF) | <https://isms.kisa.or.kr/board/file/bbs_0000000000000014/14/FILE_000000000000750/202107141700113011901763919.pdf> |
| 규제기관 | KISA ISMS-P 신청절차·제출서류 안내 | <https://isms.kisa.or.kr/main/ispims/request/> |
| 규제기관 | KISA 클라우드 보안인증제(CSAP) 제도소개 — 인증범위에 자산·조직·지원서비스 포함 규정 | <https://isms.kisa.or.kr/main/csap/intro/> |
| 규제기관 | KISA 클라우드서비스(SaaS) 보안인증기준 해설서 (PDF) | <https://isms.kisa.or.kr/board/file/bbs_0000000000000004/64/FILE_000000000000915/2023031715564523949363878> |
| 규제기관 | KISA 클라우드 취약점 점검 가이드 (CCE 점검 항목) | <https://isms.kisa.or.kr/main/csap/notice/?boardId=bbs_0000000000000004&mode=view&cntId=45> |
| 규제기관 | KISA 지역정보보호센터 — 자산관리대장 작성 양식·가이드 | <https://risc.kisa.or.kr/inform/dataBbsDetail.do?bbsId=BBS_0000000000000014&pageIndex=1> |
| 법령 | 국가법령정보센터 「정보자산 관리지침」(국가정보자원관리원 훈령) — 중요도 평가·보안등급 산정 | <https://www.law.go.kr/LSW/admRulLsInfoP.do?admRulSeq=2100000197210> |
| 법령 | 국가법령정보센터 「클라우드컴퓨팅서비스 보안인증에 관한 고시」 | <https://law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000218804> |
| AWS 공식 | AWS SDK for Python (Boto3) API Reference — 서비스 목록 | <https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/> |
| AWS 공식 | Boto3 `ec2.describe_instances` | <https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/client/describe_instances.html> |
| AWS 공식 | Boto3 `backup.list_protected_resources` | <https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/backup/client/list_protected_resources.html> |
| AWS 공식 | Boto3 `resourcegroupstaggingapi.get_resources` — **무태그 리소스 미반환 명시** | <https://docs.aws.amazon.com/boto3/latest/reference/services/resourcegroupstaggingapi/client/get_resources.html> |
| AWS 공식 | AWS CLI `resourcegroupstaggingapi get-resources` (동일 제약 기술) | <https://docs.aws.amazon.com/cli/latest/reference/resourcegroupstaggingapi/get-resources.html> |
| AWS 공식 | Boto3 `resource-explorer-2.search` | <https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/resource-explorer-2/client/search.html> |
| AWS 공식 | AWS Organizations — 태그 정책 | <https://docs.aws.amazon.com/ko_kr/organizations/latest/userguide/orgs_manage_policies_tag-policies.html> |
| AWS 공식 | AWS Organizations — 태그 정책 모범 사례 | <https://docs.aws.amazon.com/ko_kr/organizations/latest/userguide/orgs_manage_policies_tag-policies-best-practices.html> |
| AWS 공식 | AWS 백서 — 리소스 태그 지정 모범 사례 | <https://docs.aws.amazon.com/ko_kr/whitepapers/latest/tagging-best-practices/tagging-best-practices.html> |
| AWS 공식 | AWS 백서 — 태그 지정 구현 및 적용 | <https://docs.aws.amazon.com/ko_kr/whitepapers/latest/tagging-best-practices/implementing-and-enforcing-tagging.html> |
| AWS 공식 | Tag Editor 사용 설명서 | <https://docs.aws.amazon.com/ko_kr/tag-editor/latest/userguide/best-practices-and-strats.html> |
| AWS 공식 | Amazon Inspector — EC2 인스턴스 스캔(SSM Agent 요구사항) | <https://docs.aws.amazon.com/ko_kr/inspector/latest/user/scanning-ec2.html> |
| AWS 공식 | AWS 백서 — AWS 보안 모범 사례 (책임공유모델·ISMS 자산 정의) | <https://d1.awsstatic.com/whitepapers/Security/KO_Whitepapers/AWS_Security_Best_Practices_KO.pdf> |
| AWS 공식 | AWS 규정 준수 — K-ISMS | <https://aws.amazon.com/ko/compliance/k-isms/> |

### 0.2 boto3 문서 URL 규칙

개별 함수 문서는 아래 패턴으로 생성됩니다. 표에 나오는 모든 함수를 이 규칙으로 직접 확인할 수 있습니다.

```
https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/{서비스}/client/{함수명}.html

예) rds.describe_db_instances
    → .../services/rds/client/describe_db_instances.html
    s3.get_bucket_encryption
    → .../services/s3/client/get_bucket_encryption.html
```

### 0.3 제외한 자료와 그 이유

이전 검토에서 인용했던 클라우드 MSP·보안기업 기술블로그(AWS 파트너사 인증 취득 후기, 보안 컨설팅사 구현 전략, SI 기업 자산 식별 가이드), AWS 직원 개인 기고 형태의 기술블로그 포스트는 **공적 레퍼런스 요건에 부합하지 않아 이 문서에서 전부 제외**했습니다. 실무 참고 가치는 있으나 규제기관 고시·법령·벤더 공식 문서와 동일한 근거력을 갖지 않으며, 심사 대응 문서에 인용할 경우 근거 다툼의 여지가 생깁니다.

그 결과 **태그 키 표준은 특정 사에서 제시한 키 이름이 아니라, AWS Organizations 태그 정책 문서와 태그 지정 모범 사례 백서가 규정하는 "조직이 스스로 표준을 정의하고 정책으로 강제한다"는 원칙에 근거해 이 프로젝트가 정의**하는 것으로 위치를 바꿨습니다(§K, §5.4).

---

## 1단계. ISMS-P 문서 기준 자산 목록 확정

### 1.1 안내서가 규정하는 자산 유형

「ISMS-P 인증기준 안내서」 1.2.1 세부설명의 '정보자산 분류(예시)'가 규정하는 자산 유형입니다. 이 목록이 수집 범위의 출발점이자 누락 판정 기준입니다.

| # | 자산 유형 | 안내서가 명시한 유형별 항목(예) | AWS API 수집 |
|---|---|---|---|
| 1 | **서버** | 호스트 명칭, 자산 일련번호, 모델명, 용도, IP주소, 관리 부서명, 관리 실무자, 관리 책임자, 보안등급 | ● |
| 2 | **데이터(DBMS)** | 데이터베이스명, 테이블명, (개인)정보 항목명, 관리 부서명, 관리 실무자, 관리 책임자, 저장 시스템(호스트 명칭), 저장 위치(IP주소), 보안등급 | ◐ |
| 3 | **정보시스템(응용프로그램)** | 서버·PC 등 단말기, 보조저장매체, 네트워크 장비, 응용프로그램 등 정보의 수집·가공·저장·검색·송수신에 필요한 하드웨어 및 소프트웨어 | ● |
| 4 | **소프트웨어** | (분류만 규정) | ◐ |
| 5 | **네트워크장비** | (분류만 규정) | ● |
| 6 | **보안시스템** | 정보의 훼손·변조·유출 방지 목적 시스템. 침입차단시스템, 침입탐지시스템, 침입방지시스템, 개인정보유출방지시스템 등 포함 | ◐ |
| 7 | **PC** | (분류만 규정) | ◐ |
| 8 | **정보** | 문서적 정보와 전자적 정보 모두 포함(중요정보, 개인정보 등) | ◐ |
| 9 | **설비** | (분류만 규정) | ✕ |
| 10 | **시설** | (분류만 규정) | ✕ |
| 11 | **가상자원** *(파생)* | 안내서 클라우드 조항에서 파생 — 아래 1.2 참조 | ● |

범례: ● 대부분 수집 가능 / ◐ 부분 수집 (§4 참조) / ✕ 수집 불가

### 1.2 11번 유형(가상자원)의 근거

안내서 1.2.1 세부설명 마지막 항목이 클라우드 환경에 대해 별도로 요구합니다.

> 클라우드 서비스를 이용하는 경우, 클라우드 서비스의 특성을 반영한 분류기준(예를 들어, 가상서버, 오브젝트 스토리지 등)을 마련하고 이에 따라 클라우드 자산을 식별·관리

즉 **온프레미스 분류표를 그대로 쓰지 말라는 것이 명시적 요구사항**입니다. AMI·컨테이너 이미지·EBS 스냅샷은 온프레 분류표의 어느 유형에도 정확히 들어맞지 않으므로, 이 조항을 근거로 별도 유형을 신설합니다.

### 1.3 인증기준 원문과 세부점검항목 (기능 설계의 축)

**인증기준**: 조직의 업무특성에 따라 정보자산 분류기준을 수립하여 관리체계 범위 내 모든 정보자산을 식별·분류하고, 중요도를 산정한 후 그 목록을 최신으로 관리하여야 한다.

| 세부점검항목 | 도구 기능 | 관련 절 |
|---|---|---|
| ① 분류기준을 수립하고 범위 내 모든 자산을 식별하여 목록으로 관리하는가 | 수집기 + 분류 매핑 + 대장 생성 | §2·3단계 전체 |
| ② 법적 요구사항·업무 영향을 고려해 중요도를 결정하고 보안등급을 부여하는가 | 등급 제안 엔진 | §5.5 |
| ③ 정기적으로 현황을 조사하여 목록을 최신으로 유지하는가 | 스냅샷 diff | §5.6 |

### 1.4 CSAP 예시 양식 대비 결손 항목

KISA CSAP 정보자산목록 예시 양식(7개 시트: 서버 시스템 / WEB Application / WAS / DBMS / PC / 오픈 소프트웨어 / 기타 자산)에는 **보안등급·관리 책임자·(개인)정보 항목명 컬럼이 없습니다.** 안내서는 세 항목 모두를 요구하므로, 양식을 그대로 출력하면 세부점검항목 ②를 충족하지 못합니다. 도구는 반드시 컬럼을 추가해야 합니다.

---

## 2·3단계. AWS 서비스별 매핑 + boto3 추출

표기 규칙: `클라이언트.함수()` → `응답 경로`

각 블록 끝의 **"수집 불가 · 담당자 검증 필요"** 표가 이 문서의 핵심입니다. 도구가 채울 수 없는 칸을 미리 확정해야 갭 리포트가 정직해집니다.

---

### A. 계정·범위 식별

| AWS 서비스 | 채우는 항목 | boto3 함수 | 응답 경로 |
|---|---|---|---|
| STS | 계정 식별자 | `sts.get_caller_identity()` | `Account`, `Arn` |
| IAM | 계정 별칭 | `iam.list_account_aliases()` | `AccountAliases[0]` |
| EC2 | 수집 리전 범위 | `ec2.describe_regions()` | `Regions[].RegionName`, `.OptInStatus` |
| Organizations | 멀티계정 범위 | `organizations.list_accounts()` | `Accounts[].Id`, `.Name`, `.Status` |
| Organizations | OU 구조 | `organizations.list_organizational_units_for_parent()` | `OrganizationalUnits[].Name` |

#### 수집 불가 · 담당자 검증 필요

| 항목 | 왜 불가능한가 | 근거 | 담당자가 해야 할 일 |
|---|---|---|---|
| **인증범위 포함 여부** (`in_scope`) | 관리체계 범위는 조직이 정책으로 정의하는 것이지 API가 알려주는 값이 아님 | 인증기준 원문 "**관리체계 범위 내** 모든 정보자산" | 범위 정의서와 대조해 자산별 포함/제외 판정 |
| **범위 제외 사유** (`scope_reason`) | 위와 동일 | 안내서 결함사례 4 (인증범위 내 위탁 자산 누락) | 제외 자산마다 사유 문서화. 사유 없는 제외는 그 자체가 결함 |
| **인증 신청 범위 서비스 특정** | 계정에 있는 리소스 ≠ 인증 대상 서비스 | 신청서의 서비스 범위 기재란 | 인증 대상 서비스에 속한 자산만 필터링 |
| **AWS 계정 소유 주체** | 계열사·수탁사 명의 계정 여부는 API로 판별 불가 | CSAP 인증범위 규정 (자산·조직·지원서비스 포함) | 계정 소유·비용 부담 주체 확인 |

---

### B. 서버

| AWS 서비스 | 채우는 항목 | boto3 함수 | 응답 경로 |
|---|---|---|---|
| EC2 | 호스트 명칭 | `ec2.describe_instances()` | `Reservations[].Instances[].Tags[Key=Name].Value` |
| EC2 | 자산 일련번호 | 〃 | `.InstanceId` |
| EC2 | 모델명 | 〃 | `.InstanceType` |
| EC2 | IP주소 | 〃 | `.PrivateIpAddress`, `.PublicIpAddress` |
| EC2 | 위치 | 〃 | `.Placement.AvailabilityZone`, `.VpcId`, `.SubnetId` |
| EC2 | 상태·도입일 | 〃 | `.State.Name`, `.LaunchTime` |
| EC2 | 가상화 구분 | 〃 | `.Placement.Tenancy`, `.VirtualizationType` |
| EC2 | 이미지 출처 | 〃 | `.ImageId` |
| EC2 | 관리주체·용도 | 〃 | `.Tags[]` |
| EC2 | 공인 IP(추가IP) | `ec2.describe_addresses()` | `Addresses[].PublicIp`, `.InstanceId` |
| SSM | OS·OS버전 | `ssm.describe_instance_information()` | `InstanceInformationList[].PlatformName`, `.PlatformVersion` |
| SSM | 패치 준수 | `ssm.describe_instance_patch_states()` | `InstancePatchStates[].MissingCount`, `.CriticalNonCompliantCount` |
| Auto Scaling | 대체자산 유무 | `autoscaling.describe_auto_scaling_instances()` | `AutoScalingInstances[].AutoScalingGroupName` |
| ECS | 컨테이너 클러스터 | `ecs.list_clusters()` → `ecs.describe_clusters()` | `clusters[].clusterName`, `.status` |
| ECS | 실행 서비스·이미지 | `ecs.list_services()` → `ecs.describe_services()` → `ecs.describe_task_definition()` | `services[].launchType`, `taskDefinition.containerDefinitions[].image` |
| EKS | 클러스터 | `eks.list_clusters()` → `eks.describe_cluster()` | `cluster.version`, `.endpoint`, `.resourcesVpcConfig.endpointPublicAccess` |
| Lambda | 서버리스 실행주체 | `lambda.list_functions()` | `Functions[].FunctionName`, `.Runtime`, `.LastModified`, `.VpcConfig` |
| Lambda | 태그 | `lambda.list_tags(Resource=arn)` | `Tags` |

#### 수집 불가 · 담당자 검증 필요

| 항목 | 왜 불가능한가 | 근거 | 담당자가 해야 할 일 |
|---|---|---|---|
| **관리 부서명 / 관리 실무자 / 관리 책임자** | AWS에 '소유자' 개념 자체가 없음. 태그로 넣지 않으면 어디에도 존재하지 않는 정보 | 안내서 서버 유형 항목(예)에 3주체 모두 명시 | 태그 입력. CloudTrail 생성자는 **후보 제시일 뿐 책임자 지정이 아님** |
| **용도(목적 및 기능)** | 업무적 의미는 조직만 앎 | 안내서 서버 항목 "용도" | `InventoryCategory` 태그 입력 |
| **OS·OS버전** (SSM Agent 미설치 시) | EC2 API의 `PlatformDetails`는 Linux 계열을 `Linux/UNIX`로만 반환. 배포판·버전 구분 불가 | [Inspector EC2 스캔 문서](https://docs.aws.amazon.com/ko_kr/inspector/latest/user/scanning-ec2.html) — SSM Agent 및 `AmazonSSMManagedInstanceCore` 권한 필요 | SSM Agent 설치·인스턴스 프로파일 부여. 미설치 서버는 갭으로 리포트 |
| **자산 일련번호(사내 자산코드)** | InstanceId는 AWS 식별자이지 사내 자산관리 코드가 아님 | 안내서 "자산 일련번호" | 사내 자산관리시스템 코드와 매핑 규칙 수립 |
| **폐기 확인** | 종료된 인스턴스는 API 응답에서 약 1시간 내 사라짐 | [`describe_instances` 문서](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/ec2/client/describe_instances.html) — 최근 종료 인스턴스만 일시적으로 노출 | 폐기 판정은 API 조회가 아니라 **스냅샷 diff**로 수행. 폐기 승인 기록은 별도 |
| **서버 수 산정 기준** | Fargate 태스크·Lambda를 서버 수에 합산할지는 규칙 결정의 문제 | 인증신청서 유형별 요약표(가상화는 OS 기준) | 산정 규칙을 지침에 명문화하고 대장 각주로 표기 |
| **온프레미스 서버** | AWS 계정 밖 | 안내서 서버 유형 | 하이브리드 환경이면 수기 시트 병합 |

---

### C. 데이터(DBMS)

| AWS 서비스 | 채우는 항목 | boto3 함수 | 응답 경로 |
|---|---|---|---|
| RDS | 데이터베이스명 | `rds.describe_db_instances()` | `DBInstances[].DBInstanceIdentifier`, `.DBName` |
| RDS | DBMS 종류·버전 | 〃 | `.Engine`, `.EngineVersion` |
| RDS | 저장 위치 | 〃 | `.Endpoint.Address`, `.Endpoint.Port` |
| RDS | 저장 시스템 | 〃 | `.AvailabilityZone`, `.DBSubnetGroup.VpcId` |
| RDS | 암호화 (기밀성 근거) | 〃 | `.StorageEncrypted`, `.KmsKeyId` |
| RDS | 백업 (무결성 근거) | 〃 | `.BackupRetentionPeriod` |
| RDS | 다중화 (가용성 근거) | 〃 | `.MultiAZ` |
| RDS | 외부 노출 | 〃 | `.PubliclyAccessible` |
| RDS | 삭제 보호 | 〃 | `.DeletionProtection` |
| RDS | 관리주체 | 〃 | `.TagList[]` |
| RDS | 클러스터 | `rds.describe_db_clusters()` | `DBClusters[].Engine`, `.MultiAZ`, `.BackupRetentionPeriod` |
| DynamoDB | 테이블명 | `dynamodb.list_tables()` → `dynamodb.describe_table()` | `Table.TableName`, `.TableArn`, `.CreationDateTime` |
| DynamoDB | 암호화 | 〃 | `Table.SSEDescription.SSEType`, `.KMSMasterKeyArn` |
| DynamoDB | 백업 | `dynamodb.describe_continuous_backups()` | `...PointInTimeRecoveryDescription.PointInTimeRecoveryStatus` |
| DynamoDB | 태그 | `dynamodb.list_tags_of_resource(ResourceArn=)` | `Tags[]` |
| Redshift | 클러스터 | `redshift.describe_clusters()` | `Clusters[].ClusterIdentifier`, `.Encrypted`, `.PubliclyAccessible` |
| ElastiCache | 캐시 | `elasticache.describe_replication_groups()` | `.AtRestEncryptionEnabled`, `.AutomaticFailover` |
| OpenSearch | 도메인 | `opensearch.list_domain_names()` → `opensearch.describe_domain()` | `DomainStatus.EncryptionAtRestOptions.Enabled` |

#### 수집 불가 · 담당자 검증 필요

| 항목 | 왜 불가능한가 | 근거 | 담당자가 해야 할 일 |
|---|---|---|---|
| **테이블명** (RDS 계열) | 관리 API는 인스턴스 메타데이터만 반환. 테이블 목록은 DB 엔진에 접속해 스키마를 조회해야 함 | 안내서 데이터 유형 항목(예) "테이블명" | DBA가 테이블 목록 제출. 프로젝트 스코프상 태그로 갈음 |
| **(개인)정보 항목명** | 컬럼명·데이터 내용은 관리 API 밖의 영역 | 안내서 항목(예): 이름, 성별, 생년월일, 휴대폰번호, 이메일 등 | 개인정보 흐름표와 대조해 태그(`PIItems`) 입력. 자동 탐지는 Amazon Macie 등 별도 도입 사안 |
| **개인정보 보유 여부** | 위와 동일 | 결함사례 5 (개인정보 저장 자산의 기밀성 등급 저평가) | 태그 입력 필수. 미입력 시 등급 산정 자체를 보류해야 함 |
| **제3자 제공 여부** | 데이터의 출처는 계약 문서의 정보 | 결함사례 2 (제3자로부터 제공받은 개인정보 미식별) | 제공 계약서·수탁 계약서 확인 후 태그 입력 |
| **암호화 알고리즘 적정성** | KMS 사용 여부는 나오지만 컬럼 단위 암호화·해시 적용은 애플리케이션 영역 | 안전성 확보조치 기준 | 응용프로그램 암호화 구현 확인 |
| **EC2 자체 설치 DB** | `describe_db_instances`는 RDS만 반환. EC2에 직접 설치한 MySQL·PostgreSQL은 안 나옴 | 안내서 데이터 유형 | SSM Inventory 소프트웨어 목록으로 탐지하거나 수기 등재 |

---

### D. 정보(전자적)·저장장치

| AWS 서비스 | 채우는 항목 | boto3 함수 | 응답 경로 |
|---|---|---|---|
| S3 | 자산명·생성일 | `s3.list_buckets()` | `Buckets[].Name`, `.CreationDate` |
| S3 | 저장 위치 | `s3.get_bucket_location(Bucket=)` | `LocationConstraint` (null → `us-east-1`) |
| S3 | 암호화 | `s3.get_bucket_encryption(Bucket=)` | `...ApplyServerSideEncryptionByDefault.SSEAlgorithm` |
| S3 | 공개 여부 | `s3.get_bucket_policy_status(Bucket=)` | `PolicyStatus.IsPublic` |
| S3 | 공개 차단 설정 | `s3.get_public_access_block(Bucket=)` | `PublicAccessBlockConfiguration.*` |
| S3 | 버전관리 | `s3.get_bucket_versioning(Bucket=)` | `Status` |
| S3 | 객체 잠금 | `s3.get_object_lock_configuration(Bucket=)` | `ObjectLockConfiguration.ObjectLockEnabled` |
| S3 | 접근 로깅 | `s3.get_bucket_logging(Bucket=)` | `LoggingEnabled.TargetBucket` |
| S3 | 관리주체 | `s3.get_bucket_tagging(Bucket=)` | `TagSet[]` |
| S3 (계정) | 계정 수준 차단 | `s3control.get_public_access_block(AccountId=)` | `PublicAccessBlockConfiguration.*` |
| EBS | 볼륨 | `ec2.describe_volumes()` | `Volumes[].VolumeId`, `.State`, `.Size`, `.Encrypted`, `.KmsKeyId` |
| EBS | 연결 대상 | 〃 | `.Attachments[].InstanceId`, `.Device` |
| EBS | 스냅샷 | `ec2.describe_snapshots(OwnerIds=['self'])` | `Snapshots[].SnapshotId`, `.VolumeId`, `.StartTime`, `.Encrypted` |
| EFS | 파일시스템 | `efs.describe_file_systems()` | `FileSystems[].FileSystemId`, `.Encrypted`, `.KmsKeyId`, `.LifeCycleState` |
| Backup | **보호 여부** | `backup.list_protected_resources()` | `Results[].ResourceArn`, `.ResourceType`, `.LastBackupTime`, `.LastBackupVaultArn` |
| Backup | 백업 계획 | `backup.list_backup_plans()` → `backup.get_backup_plan()` | `BackupPlan.Rules[].ScheduleExpression`, `.Lifecycle` |

> **구현 주의** — `s3.get_bucket_*` 계열은 설정이 없을 때 값이 아니라 예외를 던집니다(`ServerSideEncryptionConfigurationNotFoundError`, `NoSuchTagSet`, `NoSuchLifecycleConfiguration` 등). 예외를 "미설정"이라는 값으로 정규화하는 래퍼가 필요합니다(§5.3).
>
> **무결성 등급 근거는 스냅샷 개수가 아니라 `list_protected_resources()`** 로 판정해야 합니다. 이 API는 [Backup으로 실제 백업된 리소스를 ARN·타입·최종 백업 시각과 함께 반환](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/backup/client/list_protected_resources.html)하므로, "스냅샷 3건 존재"보다 "백업 계획에 포함되어 최종 보호 시각 ○○"가 심사에서 훨씬 강한 근거가 됩니다.

#### 수집 불가 · 담당자 검증 필요

| 항목 | 왜 불가능한가 | 근거 | 담당자가 해야 할 일 |
|---|---|---|---|
| **문서적 정보** (종이 문서) | 물리 자산. API 대상 아님 | 안내서 정보 유형 "**문서적 정보와 전자적 정보 모두를 포함**" | 계약서·서면동의서·출력물 대장을 수기 시트로 관리 |
| **버킷·볼륨 안의 데이터 성격** | 객체 내용 스캔은 관리 API 범위 밖 | 안내서 정보 유형(중요정보·개인정보) | 태그 입력. 자동 판별은 Macie 등 별도 도입 사안 |
| **미연결 볼륨의 잔존 데이터** | `State=available`은 알 수 있으나 안에 무엇이 남았는지는 알 수 없음 | 결함사례 5 | 담당자가 내용 확인 후 폐기 또는 등급 부여 판단 |
| **오프라인 백업 매체** | 테이프·외장 디스크 등 | 안내서 보조저장매체 | 수기 등재 |
| **보조저장매체 반출입** | AWS 밖 | 안내서 정보시스템 유형 | 매체 관리대장 별도 운영 |
| **개인정보 보유 기간·파기 이행** | 수명주기 규칙 존재 여부는 조회되나 실제 파기 이행 여부는 별개 | 개인정보 파기 요구사항 | 파기 이행 기록 확인 |

---

### E. 정보시스템(응용프로그램)

| AWS 서비스 | 채우는 항목 | boto3 함수 | 응답 경로 |
|---|---|---|---|
| ELBv2 | 자산명·엔드포인트 | `elbv2.describe_load_balancers()` | `LoadBalancers[].LoadBalancerName`, `.DNSName`, `.Type` |
| ELBv2 | 대외 공개 | 〃 | `.Scheme` (`internet-facing` / `internal`) |
| ELBv2 | 프로토콜·인증서 | `elbv2.describe_listeners(LoadBalancerArn=)` | `Listeners[].Protocol`, `.Port`, `.SslPolicy`, `.Certificates[]` |
| ELBv2 | 관리주체 | `elbv2.describe_tags(ResourceArns=[])` | `TagDescriptions[].Tags[]` |
| CloudFront | CDN 배포 | `cloudfront.list_distributions()` | `DistributionList.Items[].Id`, `.DomainName`, `.Aliases.Items[]`, `.WebACLId` |
| API Gateway | REST API | `apigateway.get_rest_apis()` | `items[].id`, `.name`, `.createdDate` |
| API Gateway | HTTP/WS API | `apigatewayv2.get_apis()` | `Items[].ApiId`, `.Name`, `.ProtocolType`, `.ApiEndpoint` |
| Route 53 | 도메인 | `route53.list_hosted_zones()` → `route53.list_resource_record_sets(HostedZoneId=)` | `ResourceRecordSets[].Name`, `.Type` |
| Elastic Beanstalk | WAS 환경 | `elasticbeanstalk.describe_environments()` | `Environments[].EnvironmentName`, `.SolutionStackName`, `.CNAME`, `.Health` |
| App Runner | 관리형 앱 | `apprunner.list_services()` → `apprunner.describe_service()` | `Service.ServiceName`, `.ServiceUrl`, `.Status` |

#### 수집 불가 · 담당자 검증 필요

| 항목 | 왜 불가능한가 | 근거 | 담당자가 해야 할 일 |
|---|---|---|---|
| **응용프로그램의 업무 기능** | 엔드포인트는 나오지만 "무슨 업무를 처리하는지"는 조직 지식 | 안내서 정보시스템 유형 "용도" | 서비스별 기능 정의서와 대조 |
| **응용프로그램이 처리하는 개인정보** | 트래픽·페이로드 분석 영역 | 개인정보 흐름표 요구사항 | 개인정보 흐름 분석 결과와 매핑 |
| **소스코드 형상관리 자산** | 외부 SCM(사내 Git 서버, 외부 호스팅 등)은 AWS 계정 밖 | 안내서 소프트웨어 유형 | 형상관리 시스템 목록 수기 등재 |
| **내부망 전용 웹 애플리케이션** | ALB 없이 EC2에 직접 구동되는 앱은 별도 식별 안 됨 | 안내서 정보시스템 유형 | SSM Inventory 프로세스·포트 점검으로 보완 |
| **공개 노출의 업무적 타당성** | `Scheme=internet-facing`은 사실일 뿐, 그래도 되는지는 판단 | 세부점검항목 ② | 대외 서비스 승인 여부 확인 |

---

### F. 소프트웨어

| AWS 서비스 | 채우는 항목 | boto3 함수 | 응답 경로 |
|---|---|---|---|
| SSM Inventory | 설치 SW·버전 | `ssm.list_inventory_entries(InstanceId=, TypeName='AWS:Application')` | `Entries[].Name`, `.Version`, `.Publisher`, `.InstalledTime` |
| SSM Inventory | 전체 집계 | `ssm.get_inventory()` | `Entities[].Data` |
| ECR | 컨테이너 이미지 SW | `ecr.describe_repositories()` → `ecr.describe_images(repositoryName=)` | `repositories[].repositoryName`, `imageDetails[].imageTags`, `.imagePushedAt` |
| License Manager | 라이선스 구성 | `license-manager.list_license_configurations()` | `LicenseConfigurations[].Name`, `.LicenseCount`, `.LicenseCountingType` |

#### 수집 불가 · 담당자 검증 필요

| 항목 | 왜 불가능한가 | 근거 | 담당자가 해야 할 일 |
|---|---|---|---|
| **오픈소스 라이선스 종류** (GPL·AGPL·MIT 등) | SSM Inventory는 패키지명·버전·게시자만 반환. 라이선스 필드 없음 | 안내서 소프트웨어 유형 | 라이선스 조사 후 수기 입력. AGPL 계열 상용 서비스 포함 여부는 법적 리스크 |
| **상용 SW 계약 수량·계약기간** | 계약 문서의 정보 | CSAP 자산목록 '수량' 컬럼 | 구매·계약 대장과 대조 |
| **SSM Agent 미설치 서버의 설치 SW** | 에이전트 없이는 인스턴스 내부 조회 불가 | [Inspector EC2 스캔 문서](https://docs.aws.amazon.com/ko_kr/inspector/latest/user/scanning-ec2.html) | 에이전트 설치 또는 수기 조사 |
| **PC·노트북 설치 SW** | 온프레 단말은 AWS 밖 | 안내서 PC 유형 | 사내 자산관리 에이전트 결과 병합 |
| **SaaS 구독 소프트웨어** | AWS 계정 밖 | 결함사례 4 | 구독 목록 수기 등재 |

---

### G. 네트워크장비

| AWS 서비스 | 채우는 항목 | boto3 함수 | 응답 경로 |
|---|---|---|---|
| VPC | 논리 네트워크 | `ec2.describe_vpcs()` | `Vpcs[].VpcId`, `.CidrBlock`, `.IsDefault` |
| Subnet | 세그먼트 | `ec2.describe_subnets()` | `Subnets[].SubnetId`, `.CidrBlock`, `.AvailabilityZone`, `.MapPublicIpOnLaunch` |
| Route Table | 라우팅 | `ec2.describe_route_tables()` | `RouteTables[].RouteTableId`, `.Routes[].GatewayId` |
| IGW / NAT | 게이트웨이 | `ec2.describe_internet_gateways()` / `ec2.describe_nat_gateways()` | `.InternetGatewayId` / `.NatGatewayId`, `.State` |
| Transit GW / VPN | 연동 구간 | `ec2.describe_transit_gateways()` / `ec2.describe_vpn_connections()` | `.TransitGatewayId` / `.VpnConnectionId`, `.State` |
| Direct Connect | 전용선 | `directconnect.describe_connections()` | `connections[].connectionId`, `.bandwidth`, `.connectionState` |
| Security Group | 접근통제 규칙 | `ec2.describe_security_groups()` | `SecurityGroups[].GroupId`, `.IpPermissions[].IpRanges[].CidrIp`, `.FromPort`, `.ToPort` |
| Network ACL | 서브넷 ACL | `ec2.describe_network_acls()` | `NetworkAcls[].Entries[]` |
| Flow Logs | 트래픽 로그 | `ec2.describe_flow_logs()` | `FlowLogs[].FlowLogId`, `.ResourceId`, `.LogDestination` |

#### 수집 불가 · 담당자 검증 필요

| 항목 | 왜 불가능한가 | 근거 | 담당자가 해야 할 일 |
|---|---|---|---|
| **온프레미스 네트워크 장비** | 라우터·L2/L3 스위치·물리 방화벽은 AWS 밖 | 안내서 네트워크장비 유형 | 네트워크 구성도·장비 대장 수기 등재 |
| **보안그룹 규칙의 업무적 타당성** | `0.0.0.0/0` 존재는 탐지되지만 그것이 허용될 사유인지는 판단 영역 | 세부점검항목 ② (업무 영향 고려) | 규칙별 신청·승인 이력 확인 |
| **네트워크 구성도** | 토폴로지 도출은 가능하나 보안구역 구분·DMZ 정의는 설계 판단 | 신청서 구성도 작성 요령 | 구성도 작성·검증. 이번 프로젝트 범위 밖 |
| **하이브리드 연결 상대편** | Direct Connect·VPN의 반대편 장비 정보는 조회 불가 | 안내서 네트워크장비 유형 | 상대편 장비·회선 계약 정보 확인 |
| **네트워크 장비 관리 책임자** | 태그 미입력 시 부재 | 안내서 3주체 요구 | 태그 입력 |

---

### H. 보안시스템

| AWS 서비스 | 안내서 대응 유형 | boto3 함수 | 활성 판정 경로 |
|---|---|---|---|
| WAF v2 | 침입차단(웹) | `wafv2.list_web_acls(Scope='REGIONAL')` / `Scope='CLOUDFRONT'` | `WebACLs[].Name`, `.Id` |
| WAF v2 | 적용 대상 | `wafv2.list_resources_for_web_acl(WebACLArn=)` | `ResourceArns[]` |
| Shield | DDoS 방어 | `shield.describe_subscription()` | `Subscription.StartTime` (미구독 시 예외) |
| GuardDuty | 침입탐지 | `guardduty.list_detectors()` → `guardduty.get_detector(DetectorId=)` | `Status == 'ENABLED'` |
| Inspector | 취약점 점검 | `inspector2.batch_get_account_status(accountIds=[])` | `accounts[].state.status` |
| Security Hub | 통합 관제 | `securityhub.describe_hub()` + `securityhub.get_enabled_standards()` | `HubArn`, `StandardsSubscriptions[]` |
| Macie | 개인정보 탐지 | `macie2.get_macie_session()` | `status == 'ENABLED'` |
| Network Firewall | 침입방지 | `network-firewall.list_firewalls()` | `Firewalls[].FirewallName` |
| KMS | 암호키 자산 | `kms.list_keys()` → `kms.describe_key(KeyId=)` | `KeyMetadata.KeyManager == 'CUSTOMER'`, `.KeyState` |
| ACM | 인증서 자산 | `acm.list_certificates()` → `acm.describe_certificate()` | `Certificate.DomainName`, `.NotAfter`, `.Status` |
| Secrets Manager | 비밀정보 | `secretsmanager.list_secrets()` | `SecretList[].Name`, `.KmsKeyId`, `.RotationEnabled` |
| CloudTrail | 감사로그 | `cloudtrail.describe_trails()` + `cloudtrail.get_trail_status(Name=)` | `trailList[].IsMultiRegionTrail`, `.LogFileValidationEnabled`, `.KmsKeyId` |
| Config | 구성 이력 | `config.describe_configuration_recorders()` + `..._status()` | `ConfigurationRecordersStatus[].recording` |
| IAM | 계정·권한 | `iam.list_users()`, `iam.list_roles()`, `iam.get_account_password_policy()` | — |

#### 수집 불가 · 담당자 검증 필요

**이 블록이 가장 중요합니다.** 안내서 결함사례 1이 정확히 이 지점을 지적합니다.

| 항목 | 왜 불가능한가 | 근거 | 담당자가 해야 할 일 |
|---|---|---|---|
| **출력물 보안 시스템** | 온프레 엔드포인트 솔루션 | 안내서 **결함사례 1** — 중요정보·개인정보 취급자 PC를 통제하는 출력물 보안, 문서암호화, USB매체제어 등 내부정보 유출통제 시스템이 목록에서 누락된 경우 | 수기 등재 필수. 미보유 시 미보유 사실을 문서화 |
| **문서암호화(DRM)** | 위와 동일 | 안내서 결함사례 1 | 수기 등재 |
| **USB 매체제어** | 위와 동일 | 안내서 결함사례 1 | 수기 등재 |
| **DLP / 개인정보유출방지시스템** | Macie는 S3 한정. 엔드포인트·메일·웹 DLP는 별도 솔루션 | 안내서 보안시스템 유형에 "개인정보유출방지시스템" 명시 | 수기 등재 |
| **NAC / 백신 / 서버접근제어** | 온프레 또는 서드파티 솔루션 | 안내서 보안시스템 유형 | 수기 등재 (EC2 내부 설치분은 SSM Inventory로 부분 탐지) |
| **보안시스템 룰셋 적정성** | 룰 존재는 조회되나 적정 여부는 판단 | 세부점검항목 ② | 정기 룰셋 검토 기록 |
| **보안시스템 운영 담당자** | 태그 미입력 시 부재 | 안내서 3주체 요구 | 태그 입력 |
| **AWS Artifact 규정 준수 보고서** | 설비·시설 통제의 위임 근거 문서. 콘솔에서 수령·보관하는 문서 자산 | 책임공유모델([AWS 보안 모범 사례 백서](https://d1.awsstatic.com/whitepapers/Security/KO_Whitepapers/AWS_Security_Best_Practices_KO.pdf)) | 보고서 다운로드·보관, 자산목록 제외 사유에 첨부 |

> **설계 판단** — 도구는 이 항목들을 "찾지 못했다"가 아니라 **"수기 등재 대상인데 행이 0건이다"** 로 리포트해야 합니다. 클라우드 API로 해결되지 않는 결함을 발견해 주는 것도 갭 리포트의 역할입니다.

---

### I. PC

| AWS 서비스 | 채우는 항목 | boto3 함수 | 응답 경로 |
|---|---|---|---|
| WorkSpaces | VDI 단말 | `workspaces.describe_workspaces()` | `Workspaces[].WorkspaceId`, `.UserName`, `.ComputerName`, `.IpAddress`, `.State` |
| WorkSpaces | 번들(모델명) | `workspaces.describe_workspace_bundles()` | `Bundles[].Name`, `.ComputeType` |
| WorkSpaces | 디렉터리 | `workspaces.describe_workspace_directories()` | `Directories[].DirectoryName`, `.DirectoryType` |

#### 수집 불가 · 담당자 검증 필요

| 항목 | 왜 불가능한가 | 근거 | 담당자가 해야 할 일 |
|---|---|---|---|
| **온프레 PC·노트북 전체** | AWS 밖. WorkSpaces 미사용 조직이면 이 블록은 통째로 비어 있음 | 안내서 PC 유형 | 사내 자산관리시스템 결과 병합 |
| **개인정보취급자 PC 구분** | 취급자 지정은 조직의 인사·권한 결정 | 안내서 **결함사례 1** (취급자 PC 통제 시스템 누락) | 개인정보취급자 목록과 대조해 PC 구분 표기 |
| **사용자 실명·소속** | WorkSpaces `UserName`은 디렉터리 계정 ID이지 실명이 아님 | CSAP 양식 '사용자(소속/명)' 컬럼 | 인사 정보와 매핑 |
| **PC 반출입·폐기 이력** | 물리 자산 이력 | 세부점검항목 ③ | 자산 이력 대장 운영 |

---

### J. 가상자원

| AWS 서비스 | 채우는 항목 | boto3 함수 | 응답 경로 |
|---|---|---|---|
| AMI | 골든 이미지 | `ec2.describe_images(Owners=['self'])` | `Images[].ImageId`, `.Name`, `.CreationDate`, `.State` |
| AMI | 암호화 | 〃 | `.BlockDeviceMappings[].Ebs.Encrypted` |
| ECR | 컨테이너 이미지 저장소 | `ecr.describe_repositories()` | `repositories[].repositoryUri`, `.imageScanningConfiguration.scanOnPush`, `.encryptionConfiguration` |
| ECR | 이미지 | `ecr.describe_images(repositoryName=)` | `imageDetails[].imageDigest`, `.imageTags`, `.imagePushedAt` |
| EBS 스냅샷 | 사본 자산 | `ec2.describe_snapshots(OwnerIds=['self'])` | `Snapshots[].SnapshotId`, `.VolumeId`, `.StartTime` |

> `Owners=['self']` / `OwnerIds=['self']`를 생략하면 공개 이미지 수만 건이 함께 반환됩니다. 반드시 지정하세요.

#### 수집 불가 · 담당자 검증 필요

| 항목 | 왜 불가능한가 | 근거 | 담당자가 해야 할 일 |
|---|---|---|---|
| **이미지의 승인 여부** | 검증된 골든 이미지인지, 임시 생성물인지 API가 구분하지 못함 | 안내서 클라우드 분류 조항 | 승인 이미지 목록과 대조 |
| **미사용 이미지 폐기 판단** | 실행 주체가 없다는 사실은 조인으로 알 수 있으나 폐기 여부는 결정 사항 | 세부점검항목 ③ | 폐기 승인 절차 수행 |
| **이미지 내부 구성** | 이미지 안의 OS·패키지는 인스턴스화하거나 스캔해야 확인 가능 | 안내서 소프트웨어 유형 | Inspector 컨테이너 이미지 스캔 결과 활용 |
| **사본의 원본 등급 상속** | 관계는 `parent_id`로 도출 가능하나 등급 확정은 사람 몫 | 결함사례 5 | 지침에 "사본은 원본 등급 상속" 명문화 후 확정 |

---

### K. 횡단 기능

| AWS 서비스 | 용도 | boto3 함수 | 비고 |
|---|---|---|---|
| Resource Groups Tagging API | 태그 보유 자산 조회 | `resourcegroupstaggingapi.get_resources()` | **무태그 리소스 미반환** ([공식 문서](https://docs.aws.amazon.com/boto3/latest/reference/services/resourcegroupstaggingapi/client/get_resources.html)) |
| Resource Groups Tagging API | 태그 정책 준수 요약 | `resourcegroupstaggingapi.get_compliance_summary()` | Organizations 관리계정 + `us-east-1`에서만 호출 |
| Resource Explorer | **무태그 자산 탐색** | `resource-explorer-2.search(QueryString='tag:none')` | 쿼리는 view를 사용하며, 미지정 시 리전 기본 view 적용 ([공식 문서](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/resource-explorer-2/client/search.html)) |
| CloudTrail | 신규 도입 시점·생성 주체 | `cloudtrail.lookup_events(LookupAttributes=[{'AttributeKey':'ResourceName','AttributeValue':<id>}])` | 조회 가능 기간 90일 |
| Config | 구성 변경 이력 | `config.select_resource_config(Expression=)` | Config 활성 계정 한정 |

#### 이 블록의 설계 함의

AWS 공식 문서는 `GetResources`가 **태그가 없는 리소스를 반환하지 않으며**, 무태그 자산을 찾으려면 Resource Explorer에서 `tag:none` 쿼리를 쓰라고 명시합니다. 태그 없는 자산이야말로 "정보자산 식별 누락"의 실체이므로, 갭 산출식은 다음과 같아야 합니다.

```
전수 목록 = 서비스별 describe_* 결과의 합집합        ← 진실
태그 목록 = get_resources()                          ← 보조
갭       = 전수 − 태그  ≡  search('tag:none')        ← 두 경로 교차 검증
```

두 경로가 같은 수를 내지 않으면 수집기 자체에 누락이 있다는 뜻입니다. **도구가 자기 자신을 검증하는 장치**로 쓸 수 있습니다.

#### 수집 불가 · 담당자 검증 필요

| 항목 | 왜 불가능한가 | 근거 | 담당자가 해야 할 일 |
|---|---|---|---|
| **보안등급 확정** | 등급 산정은 조직의 판단. 도구는 근거와 함께 제안만 | 「정보자산 관리지침」 중요도 평가 조항 — 평가 주체는 조직 | 제안 검토 후 확정란 기입 |
| **위탁 IT 서비스 / 외부 SaaS** | AWS 계정 밖 | 안내서 **결함사례 4** — 온프레미스 자산은 식별했으나 외부에 위탁한 IT 서비스(웹호스팅, 서버호스팅, 클라우드 등)에 대한 자산 식별이 누락된 경우 | 위탁 계약 목록 수기 등재 |
| **설비·시설** | CSP 책임 영역 | 책임공유모델 | 제외 사유 문서화 + Artifact 보고서 첨부 |
| **90일 이전 생성 주체** | CloudTrail 조회 한계 | CloudTrail 이벤트 보관 정책 | 수기 조사 |
| **Config 활성화 이전 이력** | 기록 시작 이전 데이터는 존재하지 않음 | Config 동작 원리 | 자체 스냅샷 축적으로 대체 |
| **정기 실사 수행 사실** | 데이터가 최신인 것과 사람이 실사한 것은 다름 | 세부점검항목 ③ | 실사 결과 확인서에 서명·날짜 기재 |

---

## 4. 수집 불가·검증 필요 항목 총괄

블록별 표를 원인별로 재분류하면 세 가지뿐입니다. 이 분류가 갭 리포트의 카테고리가 됩니다.

| 유형 | 정의 | 해결 경로 | 대표 항목 |
|---|---|---|---|
| **① API 부재** | 자산이 AWS 계정 밖에 존재 | 수기 시트 병합 외에 방법 없음 | 온프레 PC·네트워크 장비, 출력물 보안·DRM·USB 통제, 외부 SaaS, 위탁 서비스, 문서적 정보, 설비·시설 |
| **② 태그 의존** | AWS 안에 있지만 조직이 입력해야만 존재하는 정보 | 태그 표준 수립 + 정책 강제 → 자동 수집 전환 가능 | 관리부서·실무자·책임자, 용도, 개인정보 보유 여부, 개인정보 항목, 제3자 제공 여부, 인증범위 포함 여부 |
| **③ 판단 영역** | 사실은 수집되지만 해석·결정은 사람 몫 | 도구는 근거만 제시, 확정란 분리 | 보안등급 확정, SG 규칙 타당성, 폐기 결정, 이미지 승인 여부, 서버 수 산정 규칙 |

### 4.1 리포트 문구 설계

세 유형을 한 줄로 뭉뚱그리면 리포트가 무의미해집니다. 이렇게 나눠야 합니다.

```
[① 수기 등재 필요]  내부정보 유출통제 시스템 0건 등재됨
                    → 안내서 결함사례 1 해당 가능. 담당자 확인 요망

[② 태그 미입력]     관리주체 미식별 62건 (40%)
                    ├ 생성자 추적 가능 50건 → 담당자 후보 제시
                    └ 추적 불가 12건 (90일 초과) → 수기 조사

[③ 확정 대기]       등급 제안 완료 156건 / 사람 확정 0건
                    → 검토 후 확정란 기입 필요
```

②만 도구가 줄일 수 있고, ①과 ③은 도구가 **드러내는** 것이 역할입니다. 이 구분을 보고서에 명시하면 도구의 한계를 스스로 정의한 것이 되어 오히려 신뢰를 얻습니다.

---

## 5. 전체 구조 설계

### 5.1 한 문장 요약

**AWS에서 자산을 긁어와(수집) → 하나의 공통 모양으로 다듬고(정규화) → 등급과 갭을 판단해서(판정) → 엑셀과 리포트로 뱉는다(출력).** 네 단계가 한 방향으로만 흐르고, 단계 사이는 정해진 데이터 형식으로만 대화합니다.

### 5.2 폴더 구조

> **⚠ 이 절은 착수 전 계획이며 현재 구현과 다릅니다.**
> `advisor/`는 만들지 않았고(담당 B 영역), 정규화·관계 해소는 `collector/extract.py`로 옮겼습니다.
> `config/`는 5개에서 3개로 합쳐졌고, 진입점은 `main.py`가 아니라 `python -m collector` + `demo.py`입니다.
> **현재 구조와 변경 사유는 [`docs/handover.md`](handover.md)의 "설계서 구조와 달라진 지점"을 보십시오.**
> 이 절은 당초 설계 의도를 남기기 위해 원문 그대로 둡니다.

```
isms-asset-collector/
│
├── config/                      ← 사람이 고치는 설정 (코드 아님)
│   ├── asset_types.yaml            ISMS-P 자산유형 11종 정의
│   ├── service_map.yaml            자산유형 ↔ AWS 서비스 매핑
│   ├── tag_standard.yaml           태그 키·허용값·조건부 필수 규칙
│   ├── field_profile.yaml          자산유형별 필수 필드 (갭 판정 기준)
│   └── grade_rules.yaml            보안등급 룰 (rule_id, 조건, 근거 문구)
│
├── collector/                   ← ① 수집: AWS API 호출 담당
│   ├── session.py                  계정·리전 순회, 페이지네이션, 재시도
│   ├── safe_call.py                예외를 값으로 바꾸는 래퍼
│   ├── registry.py                 서비스 모듈 자동 등록
│   ├── base.py                     ServiceCollector 추상 클래스
│   └── services/                   ← 여기에 파일 추가 = 기능 확장
│       ├── ec2.py                     서버·볼륨·스냅샷·네트워크·SG
│       ├── rds.py  dynamodb.py        데이터
│       ├── s3.py   efs.py  backup.py  저장장치
│       ├── elbv2.py  cloudfront.py    응용프로그램
│       ├── ssm.py                     OS·설치 소프트웨어
│       ├── ecr.py                     가상자원
│       ├── security.py                WAF·GuardDuty·KMS·CloudTrail 등
│       └── workspaces.py              PC
│
├── advisor/                     ← ②③ 정규화 + 판정
│   ├── normalize.py                원본 응답 → 공통 스키마
│   ├── classify.py                 AWS 리소스타입 → ISMS-P 자산유형
│   ├── relation.py                 부모-자식 연결 (스냅샷→볼륨→인스턴스)
│   ├── grade.py                    등급 룰 엔진
│   ├── gap.py                      갭 판정 (①②③ 유형 분류)
│   └── diff.py                     이전 실행과 비교
│
├── reporter/                    ← ④ 출력
│   ├── xlsx.py                     자산관리대장 (KISA 양식)
│   ├── html.py                     갭 리포트 (발표 시연용)
│   ├── manual_sheet.py             수기 입력 템플릿 (①유형 대응)
│   └── iam_policy.py               최소권한 정책 자동 생성
│
├── snapshots/                   ← 실행마다 쌓이는 원본 JSON
│   └── run-20260731-0930/
│       └── 123456789012/
│           ├── ap-northeast-2.json
│           └── us-east-1.json
│
├── output/                      ← 최종 산출물
└── main.py                      ← 진입점
```

### 5.3 데이터가 흐르는 순서 (초심자용 상세 설명)

**[그림 삽입 위치 — 아키텍처 다이어그램]**

<!-- 여기에 별도 제공된 architecture 이미지를 삽입하세요 -->
<!-- 예: ![아키텍처](./docs/architecture.svg) -->

텍스트 버전:

```
main.py 실행
   │
   ▼
① collector/session.py
   ├ sts.get_caller_identity() 로 "지금 어느 계정인가" 확인
   ├ ec2.describe_regions() 로 "어느 리전을 돌아야 하나" 확인
   └ for 계정 → for 리전 → for 서비스모듈:  collect() 호출
                                    │
                                    ▼
                          collector/services/*.py
                          (각 파일이 자기 담당 API만 호출)
                                    │
                                    ▼
                             RawAsset (원본 응답 + 호출 이력)
                                    │
                                    ├──→ snapshots/ 에 JSON 저장 (diff 재료)
                                    ▼
② advisor/normalize.py + classify.py
   ├ 서비스마다 다른 태그 필드명 통일 (Tags / TagList / tags)
   ├ 예외로 던져진 "설정 없음"을 값으로 변환
   └ AWS 리소스타입 → ISMS-P 자산유형 부여
                                    │
                                    ▼
                          NormalizedAsset (공통 스키마)
                                    │
                                    ▼
③ advisor/relation.py → grade.py → gap.py
   ├ 1패스: 전체를 asset_id로 색인
   ├ 2패스: parent_id 연결 (스냅샷은 어느 볼륨의 사본인가)
   ├ 3패스: 등급 제안 + 사본은 원본 등급 상속
   └ 4패스: 갭 판정 (①API부재 / ②태그미입력 / ③확정대기)
                                    │
                                    ▼
                          GradedAsset (등급 제안 + 갭 플래그)
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
④ reporter/xlsx.py      reporter/html.py      reporter/manual_sheet.py
   자산관리대장.xlsx        갭리포트.html          수기입력템플릿.xlsx

   (별도) advisor/diff.py ← 이전 snapshots/ 와 비교 → 변경이력.xlsx
```

### 5.4 각 파일이 하는 일 (한 줄씩)

| 파일 | 하는 일 | 왜 분리했나 |
|---|---|---|
| `main.py` | 전체 순서를 지휘 | 여기만 보면 흐름 전체가 보이도록 |
| `collector/session.py` | 계정·리전 루프, 페이지네이터, 스로틀링 재시도 | 모든 서비스가 똑같이 필요한 일이라 한 곳에 |
| `collector/safe_call.py` | API 예외를 "미설정" 값으로 바꿈. 권한 부족은 별도 예외로 승격 | S3 계열이 설정 없을 때 예외를 던지므로 |
| `collector/registry.py` | `services/` 폴더의 모듈을 자동 등록 | 서비스 추가 시 파일만 넣으면 되게 |
| `collector/base.py` | 모든 수집기가 지켜야 할 형식 정의 | 담당 A가 새 파일 만들 때 복사 기준 |
| `collector/services/*.py` | 각자 자기 AWS 서비스만 담당 | 한 파일이 망가져도 나머지는 동작 |
| `advisor/normalize.py` | 제각각인 응답을 한 모양으로 | 담당 B가 서비스별 차이를 몰라도 되게 |
| `advisor/classify.py` | 리소스타입 → 자산유형 | 분류 규칙이 바뀌면 여기만 수정 |
| `advisor/relation.py` | 자산 간 부모-자식 연결 | 등급 상속의 전제 |
| `advisor/grade.py` | 등급 룰 실행, 근거 문구 생성 | 룰은 yaml에, 실행은 여기에 |
| `advisor/gap.py` | 빠진 값 찾기 + 3유형 분류 | 갭 정의가 바뀌면 여기만 |
| `advisor/diff.py` | 이번 실행 vs 지난 실행 | 세부점검항목 ③ 대응 |
| `reporter/*.py` | 파일로 출력 | 출력 형식이 바뀌어도 판정 로직 무관 |

### 5.5 데이터 계약 — 3단 분리

수집기(담당 A)와 판정·출력(담당 B)이 **`NormalizedAsset` 하나만** 공유합니다. 이러면 A가 새 서비스를 추가해도 B는 코드를 안 고쳐도 됩니다.

```
RawAsset          API 응답 그대로 + source_api[] + collected_at + run_id
   ↓ normalize
NormalizedAsset   공통 필드 + asset_type + infra_facts + null 사유 구분
   ↓ grade / gap
GradedAsset       + grade_proposed(rule_id 포함) + grade_confirmed(항상 null) + gap_flags[]
```

**null은 두 종류입니다.** 이 구분이 없으면 갭 리포트에 "S3 버킷의 IP주소 미확인" 같은 쓸모없는 행이 채워집니다.

```json
"network": { "ip_private": { "value": null, "reason": "N/A" } },
"owner_dept": { "value": null, "reason": "MISSING" },
"dlp_system": { "value": null, "reason": "OUT_OF_API_SCOPE" }
```

| reason | 의미 | 갭 리포트 |
|---|---|---|
| `N/A` | 이 자산유형에 개념이 없음 | 출력 안 함 |
| `MISSING` | 태그로 있어야 하는데 없음 | **②유형으로 출력** |
| `OUT_OF_API_SCOPE` | AWS API로 얻을 수 없는 항목 | **①유형으로 출력** |
| `PERMISSION_DENIED` | 권한 부족으로 조회 실패 | **별도 출력** — 자산 부재로 오인 금지 |

마지막 항목이 특히 중요합니다. 권한이 없어서 조회에 실패한 것을 "암호화 미적용"으로 기록하면 등급 제안 전체가 틀립니다.

### 5.6 반드시 지켜야 할 구현 규칙 5가지

**① 페이지네이션은 예외 없이**

AWS EC2 API 참조 문서는 페이지네이션된 요청만 사용할 것을 강력히 권장하며, 페이지네이션 없는 요청은 스로틀링과 타임아웃에 취약하다고 명시합니다. 자산 수백 건 환경에서 그냥 호출하면 **조용히 일부만 받습니다.** 자산 목록 도구에서 가장 치명적이고 가장 발견하기 어려운 버그입니다.

```python
paginator = client.get_paginator('describe_instances')
for page in paginator.paginate():
    ...
```

**② 전역 서비스는 리전 루프 밖에서**

S3·IAM·CloudFront·Route 53을 리전 루프 안에 넣으면 같은 자산이 리전 수만큼 중복됩니다. `is_global` 플래그로 분리합니다.

**③ 예외는 한 곳에서만 처리**

```python
def safe(fn, *, absent_errors, absent_value=None):
    try:
        return fn()
    except ClientError as e:
        code = e.response['Error']['Code']
        if code in absent_errors:
            return absent_value                    # 설정 없음 = 값
        if code in ('AccessDenied', 'UnauthorizedOperation'):
            raise PermissionGap(code)              # 권한 없음 = 갭
        raise
```

**④ 관계 해소는 전체 수집 후 2패스로**

스냅샷→볼륨→인스턴스 연결은 한 서비스만 봐서는 못 풉니다. 1패스에서 전부 모아 색인을 만들고, 2패스에서 `parent_id`를 채운 뒤, 3패스에서 등급 상속을 적용합니다. 순서를 어기면 "사본은 원본 등급 상속"이 동작하지 않습니다.

**⑤ 실행 단위는 `run_id`**

전 리전 순회는 수 분이 걸려 `collected_at`이 레코드마다 다릅니다. diff의 기준선은 `run_id`(예: `run-20260731-0930`)로 잡습니다.

### 5.7 권한 정책 자동 생성

각 수집기 클래스가 자기가 쓰는 IAM 액션을 선언하게 하면, 최소권한 정책 JSON을 코드에서 자동으로 뽑을 수 있습니다.

```python
class ServiceCollector(ABC):
    client_name: str              # 'ec2'
    asset_types: list[str]        # ['서버', '네트워크장비', '가상자원']
    is_global: bool = False
    required_actions: list[str]   # ['ec2:DescribeInstances', ...]

    @abstractmethod
    def collect(self, session, region) -> list[RawAsset]: ...
```

산출물 하나가 공짜로 생기고, 권한을 추가할 때 정책 문서와 코드가 어긋나지 않습니다. 보안 도구가 고객 계정에 붙는 상황에서 `ReadOnlyAccess`를 요구하지 않는다는 점 자체가 설계 역량의 증거가 됩니다.

### 5.8 개인정보 취급 주의

`tags_raw`를 통째로 보관하면 태그 값에 담당자 이메일·전화번호가 들어 있는 경우가 흔합니다. **개인정보 관리 자동화 도구가 스스로 개인정보 파일을 생성**하게 됩니다.

- `snapshots/`, `output/`을 `.gitignore`에 등록
- 반출 시 마스킹 옵션 제공
- 이 판단을 보고서에 한 문단으로 기록 (한계 인식의 증거가 됨)

### 5.9 구현 순서

| 시점 | 블록 | 확인 지점 |
|---|---|---|
| 1주 | A·B·C·D + 페이지네이터·예외 래퍼 골격 + xlsx 출력 | 계정 넣으면 대장이 나온다 |
| 2주 | G·H·J·K + 갭 3유형 분류 + **diff 앞당김** + 등급 룰 | 두 번 돌리면 변경이 보인다 |
| 3주 | E·F·I + 수기 시트 템플릿 + CloudTrail 생성자 추론 + HTML 리포트 | 갭이 처방까지 준다 |
| 4주 | 보고서·발표 | — |

블록 단위로 자르면 매주 "이번 주에 늘어난 자산 유형"을 그대로 시연할 수 있습니다.

---

*본 문서는 공개된 공적 자료만을 근거로 작성되었습니다. 실제 인증심사 적용 전 KISA 최신 안내서 및 심사기관 협의가 필요하며, 인증기준·양식·법령은 개정될 수 있습니다. AWS API 사양은 변경될 수 있으므로 구현 시 §0.2 규칙으로 최신 문서를 확인하십시오.*
