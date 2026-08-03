"""S1 검증. 실제 AWS 계정은 쓰지 않는다."""

from __future__ import annotations

import json

import boto3
import pytest
from botocore.stub import Stubber
from moto import mock_aws

from collector.base import ServiceCollector
from collector.collect import run_collect
from collector.registry import all_required_actions, discover
from collector.safe_call import (
    COLLECT_ERROR,
    NOT_CONFIGURED,
    PERMISSION_DENIED,
    is_status,
    safe_call,
)
from collector.services.backup import BackupCollector
from collector.session import CollectorSession, paginate
from tests.aws_fixture import ALT_REGION, REGION, build_environment, build_many_instances


@pytest.fixture(autouse=True)
def fake_credentials(monkeypatch):
    for key, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SECURITY_TOKEN": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": REGION,
    }.items():
        monkeypatch.setenv(key, value)


def _load(tmp_path, run_id, account, region, service):
    path = tmp_path / run_id / account / region / f"{service}.json"
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# 읽기 전용 보증
# --------------------------------------------------------------------------

def test_수집기는_쓰기_액션을_선언하지_않는다():
    for collector in discover():
        assert type(collector).write_actions() == [], type(collector).__name__


def test_최소권한_정책에_쓰기_액션이_없다():
    actions = all_required_actions()
    assert actions
    # Batch는 inspector2:BatchGetAccountStatus 같은 조회 API의 접두사다.
    for action in actions:
        verb = action.split(":", 1)[1]
        assert verb.startswith(("Describe", "List", "Get", "Batch")), action


def test_모든_수집기가_계약을_지킨다():
    for collector in discover():
        cls = type(collector)
        assert issubclass(cls, ServiceCollector)
        # client_name이 None인 수집기(여러 서비스를 묶는 경우)도 덤프 이름은 있어야 한다
        assert collector.dump_name
        assert cls.required_actions, f"{cls.__name__}에 required_actions가 없다"


# --------------------------------------------------------------------------
# safe_call — 이 프로젝트에서 제일 중요한 구분
# --------------------------------------------------------------------------

def test_권한부족을_설정부재로_처리하지_않는다():
    """권한이 없어서 암호화를 못 읽은 걸 '미암호화'로 기록하면 기밀성 등급이 통째로 틀린다."""
    from botocore.exceptions import ClientError

    def denied():
        raise ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "no"}}, "GetBucketVersioning"
        )

    result = safe_call(denied, absent_errors=("NoSuchTagSet",))
    assert is_status(result, PERMISSION_DENIED)
    assert not is_status(result, NOT_CONFIGURED)


def test_서비스별로_다른_권한거부_코드를_모두_잡는다():
    from botocore.exceptions import ClientError

    for code in ("AccessDenied", "AccessDeniedException", "UnauthorizedOperation",
                 "AuthFailure", "NotAuthorizedException"):
        def denied(c=code):
            raise ClientError({"Error": {"Code": c, "Message": ""}}, "Op")

        assert is_status(safe_call(denied), PERMISSION_DENIED), code


def test_알수없는_에러는_COLLECT_ERROR이지_설정부재가_아니다():
    """전 리전 순회 중 서비스 없는 리전을 만나도 순회가 죽으면 안 된다."""
    from botocore.exceptions import ClientError

    def broken():
        raise ClientError({"Error": {"Code": "404", "Message": "Not yet implemented"}}, "Op")

    result = safe_call(broken)
    assert is_status(result, COLLECT_ERROR)
    assert result["error_code"] == "404"


def test_빈_응답도_설정부재로_정규화한다():
    """get_bucket_versioning은 예외가 아니라 Status 키 없는 정상 응답을 준다."""
    result = safe_call(lambda: {}, absent_when=lambda r: "Status" not in r)
    assert is_status(result, NOT_CONFIGURED)
    assert result["error_code"] == "EMPTY_RESPONSE"


# --------------------------------------------------------------------------
# 페이지네이션 — 가장 늦게 발견되는 치명적 버그
# --------------------------------------------------------------------------

@mock_aws
def test_인스턴스_120건이_한_건도_빠지지_않는다():
    made = build_many_instances(120)
    ec2 = boto3.client("ec2", region_name=REGION)

    result = paginate(ec2, "describe_instances", "Reservations")
    got = sum(len(r["Instances"]) for r in result["Reservations"])
    assert got == made == 120


def test_여러_페이지로_쪼개져도_전부_합친다():
    """NextToken이 실제로 도는지 검증한다.

    moto는 describe_instances의 MaxResults를 무시하고 항상 한 페이지로 준다
    (docs/aws-facts.md §8). moto로는 다중 페이지가 재현되지 않으므로
    Stubber로 NextToken 왕복을 직접 만든다.
    """
    ec2 = boto3.client("ec2", region_name=REGION,
                       aws_access_key_id="x", aws_secret_access_key="x")
    stubber = Stubber(ec2)

    def reservation(prefix, n):
        return {"Instances": [{"InstanceId": f"i-{prefix}{i:04d}"} for i in range(n)]}

    stubber.add_response(
        "describe_instances",
        {"Reservations": [reservation("a", 50)], "NextToken": "page2"},
        {},
    )
    stubber.add_response(
        "describe_instances",
        {"Reservations": [reservation("b", 50)], "NextToken": "page3"},
        {"NextToken": "page2"},
    )
    stubber.add_response(
        "describe_instances",
        {"Reservations": [reservation("c", 20)]},
        {"NextToken": "page3"},
    )

    with stubber:
        result = paginate(ec2, "describe_instances", "Reservations")

    got = [i["InstanceId"] for r in result["Reservations"] for i in r["Instances"]]
    assert result["__pages__"] == 3, "페이지가 하나면 이 테스트는 아무것도 증명하지 않는다"
    assert len(got) == 120
    assert len(set(got)) == 120, "페이지 병합에서 중복이 생겼다"
    stubber.assert_no_pending_responses()


def test_페이지네이션을_안_쓰면_조용히_일부만_받는다():
    """왜 페이지네이터가 필수인지를 코드로 남긴다.

    첫 페이지만 받고 NextToken을 무시하면 자산이 조용히 사라진다.
    자산 목록 도구에서 가장 치명적이고 가장 늦게 발견되는 버그다.
    """
    ec2 = boto3.client("ec2", region_name=REGION,
                       aws_access_key_id="x", aws_secret_access_key="x")
    stubber = Stubber(ec2)
    stubber.add_response(
        "describe_instances",
        {"Reservations": [{"Instances": [{"InstanceId": f"i-{i:04d}"} for i in range(50)]}],
         "NextToken": "page2"},
        {},
    )
    with stubber:
        naive = ec2.describe_instances()

    truncated = sum(len(r["Instances"]) for r in naive["Reservations"])
    assert truncated == 50
    assert "NextToken" in naive, "NextToken이 있는데 무시하면 나머지 70건이 사라진다"


@mock_aws
def test_페이지네이터_없는_API도_처리한다():
    """describe_addresses에는 페이지네이터가 없다(docs/aws-facts.md §1)."""
    ec2 = boto3.client("ec2", region_name=REGION)
    assert ec2.can_paginate("describe_addresses") is False
    result = paginate(ec2, "describe_addresses", "Addresses")
    assert "Addresses" in result


# --------------------------------------------------------------------------
# 리전 순회
# --------------------------------------------------------------------------

@mock_aws
def test_옵트인_안된_리전은_순회하지_않는다():
    session = CollectorSession()
    regions = session.regions()
    raw = boto3.client("ec2", region_name=REGION).describe_regions()["Regions"]
    not_opted = {r["RegionName"] for r in raw if r["OptInStatus"] == "not-opted-in"}

    assert regions
    assert not (set(regions) & not_opted)


@mock_aws
def test_전역_서비스는_리전_수만큼_중복되지_않는다(tmp_path):
    build_environment(REGION)
    result = run_collect(regions=(REGION, ALT_REGION), root=tmp_path)

    s3_files = [f for f in result["files"] if f.endswith("s3.json")]
    assert len(s3_files) == 1, "S3는 전역이라 리전 수와 무관하게 1회만 수집돼야 한다"


# --------------------------------------------------------------------------
# 원본 덤프
# --------------------------------------------------------------------------

@mock_aws
def test_덤프가_원본을_고르지_않고_그대로_담는다(tmp_path):
    env = build_environment(REGION)
    result = run_collect(regions=(REGION,), root=tmp_path)
    account = result["account_id"]

    dump = _load(tmp_path, result["run_id"], account, REGION, "ec2")
    assert dump["meta"]["run_id"] == result["run_id"]
    assert dump["meta"]["region"] == REGION
    assert dump["meta"]["source_api"]

    instances = [
        i for r in dump["data"]["describe_instances"]["Reservations"] for i in r["Instances"]
    ]
    ids = {i["InstanceId"] for i in instances}
    assert set(env["instances"].values()) <= ids

    # 필드를 고르지 않았다는 증거 — 쓸 계획이 없는 필드까지 남아 있어야 한다
    sample = instances[0]
    for field in ("BlockDeviceMappings", "MetadataOptions", "RootDeviceType",
                  "Hypervisor", "NetworkInterfaces"):
        assert field in sample, f"{field}가 버려졌다. 원본을 가공하고 있다"


@mock_aws
def test_중지된_인스턴스도_수집한다(tmp_path):
    """중지된 인스턴스를 대장에서 지우면 '목록과 실제 현황 불일치' 결함이 된다."""
    env = build_environment(REGION)
    result = run_collect(regions=(REGION,), root=tmp_path)

    dump = _load(tmp_path, result["run_id"], result["account_id"], REGION, "ec2")
    states = {
        i["InstanceId"]: i["State"]["Name"]
        for r in dump["data"]["describe_instances"]["Reservations"]
        for i in r["Instances"]
    }
    assert states[env["instances"]["stopped"]] == "stopped"


@mock_aws
def test_미연결_볼륨이_available로_잡힌다(tmp_path):
    env = build_environment(REGION)
    result = run_collect(regions=(REGION,), root=tmp_path)

    dump = _load(tmp_path, result["run_id"], result["account_id"], REGION, "ec2")
    volumes = {v["VolumeId"]: v["State"] for v in dump["data"]["describe_volumes"]["Volumes"]}
    assert volumes[env["volumes"]["orphan"]] == "available"
    assert volumes[env["volumes"]["attached"]] == "in-use"


@mock_aws
def test_암호화_없는_S3버킷은_NOT_CONFIGURED로_기록된다(tmp_path):
    build_environment(REGION)
    result = run_collect(regions=(REGION,), root=tmp_path)

    dump = _load(tmp_path, result["run_id"], result["account_id"], "us-east-1", "s3")
    buckets = dump["data"]["buckets"]

    plain = buckets["isms-demo-plain"]["get_bucket_encryption"]
    assert plain["__status__"] == NOT_CONFIGURED
    assert plain["error_code"] == "ServerSideEncryptionConfigurationNotFoundError"

    encrypted = buckets["isms-demo-encrypted"]["get_bucket_encryption"]
    assert "__status__" not in encrypted
    assert (encrypted["ServerSideEncryptionConfiguration"]["Rules"][0]
            ["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256")


@mock_aws
def test_태그_없는_버킷과_있는_버킷이_구분된다(tmp_path):
    build_environment(REGION)
    result = run_collect(regions=(REGION,), root=tmp_path)

    buckets = _load(tmp_path, result["run_id"], result["account_id"], "us-east-1", "s3")["data"]["buckets"]
    assert buckets["isms-demo-plain"]["get_bucket_tagging"]["__status__"] == NOT_CONFIGURED
    assert buckets["isms-demo-encrypted"]["get_bucket_tagging"]["TagSet"]


@mock_aws
def test_버전관리_미설정은_빈응답_경로로_잡힌다(tmp_path):
    build_environment(REGION)
    result = run_collect(regions=(REGION,), root=tmp_path)

    buckets = _load(tmp_path, result["run_id"], result["account_id"], "us-east-1", "s3")["data"]["buckets"]
    versioning = buckets["isms-demo-plain"]["get_bucket_versioning"]
    assert versioning["__status__"] == NOT_CONFIGURED
    assert versioning["error_code"] == "EMPTY_RESPONSE"


@mock_aws
def test_RDS는_TagList로_태그를_준다(tmp_path):
    build_environment(REGION)
    result = run_collect(regions=(REGION,), root=tmp_path)

    dump = _load(tmp_path, result["run_id"], result["account_id"], REGION, "rds")
    dbs = {d["DBInstanceIdentifier"]: d for d in dump["data"]["describe_db_instances"]["DBInstances"]}
    assert "TagList" in dbs["prd-db-01"]
    assert dbs["prd-db-01"]["BackupRetentionPeriod"] == 7
    assert dbs["dev-db-01"]["BackupRetentionPeriod"] == 0


@mock_aws
def test_datetime이_ISO8601로_직렬화된다(tmp_path):
    build_environment(REGION)
    result = run_collect(regions=(REGION,), root=tmp_path)

    dump = _load(tmp_path, result["run_id"], result["account_id"], REGION, "ec2")
    launch = dump["data"]["describe_instances"]["Reservations"][0]["Instances"][0]["LaunchTime"]
    assert isinstance(launch, str) and "T" in launch


@mock_aws
def test_manifest가_실행_전체를_요약한다(tmp_path):
    build_environment(REGION)
    result = run_collect(regions=(REGION, ALT_REGION), root=tmp_path)

    manifest = json.loads((tmp_path / result["run_id"] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["regions"] == sorted([REGION, ALT_REGION])
    assert manifest["stats"]["files"] == len(result["files"])
    assert manifest["stats"][NOT_CONFIGURED] > 0


# --------------------------------------------------------------------------
# moto가 지원하지 않는 API — Stubber로 응답 구조를 고정한다
# --------------------------------------------------------------------------

def test_backup_보호리소스_응답구조(monkeypatch):
    """list_protected_resources는 moto 미구현이라 Stubber로 검증한다.

    backup_exists 판정의 정답 소스이므로 포기할 수 없다(docs/field-mapping.md §5).
    """
    client = boto3.client("backup", region_name=REGION,
                          aws_access_key_id="x", aws_secret_access_key="x")
    stubber = Stubber(client)
    stubber.add_response(
        "list_protected_resources",
        {
            "Results": [
                {
                    "ResourceArn": "arn:aws:rds:ap-northeast-2:123456789012:db:prd-db-01",
                    "ResourceType": "RDS",
                    "LastBackupTime": "2026-07-31T09:00:00+09:00",
                }
            ]
        },
        {},
    )
    stubber.add_response("list_backup_plans", {"BackupPlansList": []}, {})

    with stubber:
        data = BackupCollector().collect(client, region=REGION, session=None)

    results = data["list_protected_resources"]["Results"]
    assert results[0]["ResourceArn"].endswith("prd-db-01")
    assert results[0]["ResourceType"] == "RDS"


@mock_aws
def test_moto_미구현_API가_순회를_죽이지_않는다(tmp_path):
    """list_protected_resources는 moto에서 404를 던진다. 그래도 수집은 끝나야 한다."""
    build_environment(REGION)
    result = run_collect(regions=(REGION,), root=tmp_path)

    dump = _load(tmp_path, result["run_id"], result["account_id"], REGION, "backup")
    protected = dump["data"]["list_protected_resources"]
    assert protected["__status__"] == COLLECT_ERROR
    assert protected["__status__"] != NOT_CONFIGURED  # 자산 부재로 오인 금지
    assert result["stats"][COLLECT_ERROR] > 0
