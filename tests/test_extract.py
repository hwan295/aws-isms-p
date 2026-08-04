"""S2 검증.

extract는 AWS에 접속하지 않는다. 그게 원본 보관 구조의 핵심 이점이므로
"접속하지 않는다"를 말이 아니라 테스트로 증명한다.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
import yaml
from moto import mock_aws

from collector import reasons as R
from collector.collect import run_collect
from collector.extract import (
    INFRA_FACT_KEYS,
    latest_run_id,
    run_extract,
    status_on_path,
)
from tests.aws_fixture import ALT_REGION, REGION, build_environment

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


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


@pytest.fixture
def raw_run(tmp_path):
    """moto로 원본 덤프를 한 번 만들어 둔다. 이후 테스트는 이 파일만 읽는다."""
    raw_root = tmp_path / "raw"

    @mock_aws
    def _build():
        build_environment(REGION)
        build_environment(ALT_REGION, suffix="-use1")
        return run_collect(regions=(REGION, ALT_REGION), root=raw_root)

    result = _build()
    return {"raw_root": raw_root, "run_id": result["run_id"], "tmp": tmp_path}


def do_extract(raw_run, config_dir: Path | None = None):
    return run_extract(
        run_id=raw_run["run_id"],
        raw_root=raw_run["raw_root"],
        out_root=raw_run["tmp"] / "norm",
        config_dir=config_dir or CONFIG_DIR,
    )


def find(payload, asset_type, predicate):
    for asset in payload["asset_types"][asset_type]["assets"]:
        if predicate(asset):
            return asset
    raise AssertionError(f"{asset_type}에서 조건에 맞는 자산을 못 찾았다")


# --------------------------------------------------------------------------
# AWS 접속 없이 단독 실행 — 이 구조의 존재 이유
# --------------------------------------------------------------------------

def test_extract는_네트워크를_한_번도_열지_않는다(raw_run, monkeypatch):
    """소켓을 막아놓고 돌린다. 한 번이라도 접속하면 실패한다."""

    def blocked(*args, **kwargs):
        raise AssertionError("extract가 네트워크에 접속했다. AWS 재호출 없이 동작해야 한다")

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)

    payload = do_extract(raw_run)
    assert payload["meta"]["total_assets"] > 0


def test_자격증명이_없어도_동작한다(raw_run, monkeypatch):
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                "AWS_SECURITY_TOKEN", "AWS_SESSION_TOKEN", "AWS_DEFAULT_REGION"):
        monkeypatch.delenv(key, raising=False)
    payload = do_extract(raw_run)
    assert payload["meta"]["total_assets"] > 0


def test_최근_run을_자동으로_찾는다(raw_run):
    assert latest_run_id(raw_run["raw_root"]) == raw_run["run_id"]


# --------------------------------------------------------------------------
# yaml 한 줄로 필드가 늘어나는가 — 이 구조의 검증 포인트
# --------------------------------------------------------------------------

def test_yaml에_필드를_추가하면_코드_수정_없이_반영된다(raw_run, tmp_path):
    """B가 '이 필드도 필요하다'고 하면 yaml 한 줄 + 재추출로 끝나야 한다."""
    before = do_extract(raw_run)
    server = find(before, "서버", lambda a: a["resource_type"] == "ec2_instance")
    assert "root_device_type" not in server

    # config를 복사해 한 줄만 더한다
    patched = tmp_path / "config_patched"
    patched.mkdir()
    for name in ("isms_asset_types.yaml", "manual_items.yaml"):
        (patched / name).write_text(
            (CONFIG_DIR / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    doc = yaml.safe_load((CONFIG_DIR / "extract_map.yaml").read_text(encoding="utf-8"))
    doc["resources"]["ec2_instance"]["fields"]["root_device_type"] = {"path": "RootDeviceType"}
    (patched / "extract_map.yaml").write_text(
        yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8"
    )

    after = do_extract(raw_run, config_dir=patched)
    server = find(after, "서버", lambda a: a["resource_type"] == "ec2_instance")
    assert server["root_device_type"]["value"] == "ebs"
    assert server["root_device_type"]["reason"] is None


def test_AWS_재호출_없이_재추출한다(raw_run, monkeypatch):
    """재추출은 원본만 읽는다. 자격증명도 리전 순회도 필요 없다."""
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("네트워크 접속"))
    first = do_extract(raw_run)
    second = do_extract(raw_run)
    assert first["meta"]["total_assets"] == second["meta"]["total_assets"]


# --------------------------------------------------------------------------
# 사유가 올바르게 붙는가
# --------------------------------------------------------------------------

def test_태그_없는_EC2는_TAG_ABSENT(raw_run):
    payload = do_extract(raw_run)
    untagged = find(payload, "서버",
                    lambda a: a["asset_name"]["reason"] == R.TAG_ABSENT)
    assert untagged["owner_dept"]["reason"] == R.TAG_ABSENT
    assert untagged["usage"]["reason"] == R.TAG_ABSENT
    assert "OwnerDept" in untagged["owner_dept"]["hint"]


def test_태그_있는_EC2는_사유가_null(raw_run):
    payload = do_extract(raw_run)
    tagged = find(payload, "서버", lambda a: a["asset_name"]["value"] == "prd-web-01")
    assert tagged["owner_dept"]["value"] == "인프라운영팀"
    assert tagged["owner_dept"]["reason"] is None
    assert tagged["usage"]["value"] == "WebServer"  # Purpose가 아니라 InventoryCategory


def test_암호화_없는_S3는_NOT_CONFIGURED(raw_run):
    """수집 단계의 __status__ 표지가 추출 단계 필드 사유로 이어지는지."""
    payload = do_extract(raw_run)
    plain = find(payload, "정보", lambda a: a["asset_id"] == "arn:aws:s3:::isms-demo-plain")
    encrypted = find(payload, "정보", lambda a: a["asset_id"] == "arn:aws:s3:::isms-demo-encrypted")

    assert plain["infra_facts"]["encryption_at_rest"]["reason"] == R.NOT_CONFIGURED
    assert plain["infra_facts"]["encryption_at_rest"]["value"] is None
    assert encrypted["infra_facts"]["encryption_at_rest"]["value"] == "SSE-S3"


def test_S3버킷의_IP주소는_NOT_APPLICABLE(raw_run):
    """이게 없으면 갭 리포트가 'S3 버킷 IP 미확인' 같은 행으로 채워진다."""
    payload = do_extract(raw_run)
    bucket = find(payload, "정보", lambda a: a["resource_type"] == "s3_bucket")
    assert bucket["ip_private"]["reason"] == R.NOT_APPLICABLE
    assert not R.counts_as_gap(bucket["ip_private"])
    # 반면 태그 미입력은 갭으로 센다
    assert R.counts_as_gap(bucket["owner_dept"])


def test_안_불러본_API는_OUT_OF_SCOPE이지_NOT_APPLICABLE이_아니다(raw_run):
    """EC2에 공인 IP가 없다고 exposure_path를 None으로 단정하면 C-03이 틀어진다."""
    payload = do_extract(raw_run)
    server = find(payload, "서버", lambda a: a["resource_type"] == "ec2_instance")

    assert server["os"]["reason"] == R.OUT_OF_SCOPE
    assert "ssm" in server["os"]["hint"]

    # 노출 경로는 찾았을 때만 값이 붙는다. 못 찾은 것을 "미노출"로 적지 않는다.
    for block in payload["asset_types"].values():
        for asset in block["assets"]:
            exposure = asset["infra_facts"]["exposure_path"]
            if exposure["value"] is None:
                assert exposure["reason"] in (R.OUT_OF_SCOPE, R.NOT_APPLICABLE), asset["asset_id"]
            else:
                assert exposure["value"] in (
                    "Direct", "ALB", "CloudFront", "APIGateway"), asset["asset_id"]


def test_공인IP가_없어도_ALB_뒤에_있으면_노출로_잡힌다(raw_run):
    """이 조인이 없으면 ALB 뒤 자산이 '미노출'로 새어 나가 기밀성 등급이 통째로 틀린다."""
    payload = do_extract(raw_run)
    backend = find(payload, "서버", lambda a: a["asset_name"]["value"] == "prd-was-02")

    assert backend["infra_facts"]["public_exposed"]["value"] is False
    assert backend["infra_facts"]["exposure_path"]["value"] == "ALB"


def test_노출_경로_판정이_선언된_NOT_APPLICABLE을_덮지_않는다(raw_run):
    """서브넷의 MapPublicIpOnLaunch는 네트워크 설정이지 엔드포인트가 아니다.

    무엇이 노출될 수 있는가는 yaml 선언이 정하고, 2패스는 안 본 것만 채운다.
    """
    payload = do_extract(raw_run)
    subnet = find(payload, "네트워크장비", lambda a: a["resource_type"] == "ec2_subnet")
    assert subnet["infra_facts"]["exposure_path"]["reason"] == R.NOT_APPLICABLE


def test_조회_실패는_설정부재로_뭉개지지_않는다(raw_run):
    """moto가 list_protected_resources를 구현하지 않아 backup_exists를 모른다.

    이걸 false로 적으면 '백업 없음'이 되어 무결성 등급이 통째로 틀린다.
    """
    payload = do_extract(raw_run)
    server = find(payload, "서버", lambda a: a["resource_type"] == "ec2_instance")
    backup = server["infra_facts"]["backup_exists"]

    assert backup["reason"] == R.COLLECT_ERROR
    assert backup["value"] is not False
    assert backup["reason"] in R.NOT_ABSENCE_REASONS


def test_AWS관리_태그는_없어도_TAG_ABSENT가_아니다(raw_run):
    """aws:autoscaling:groupName에 '태그를 다세요'라고 안내하면 틀린 처방이다."""
    payload = do_extract(raw_run)
    server = find(payload, "서버", lambda a: a["resource_type"] == "ec2_instance")
    in_asg = server["infra_facts"]["in_asg"]
    assert in_asg["value"] is False
    assert in_asg["reason"] is None


def test_상태표지_전파(raw_run):
    assert status_on_path({"a": {"__status__": "NOT_CONFIGURED"}}, "a.b.c")["__status__"] == "NOT_CONFIGURED"
    assert status_on_path({"a": {"b": 1}}, "a.b") is None


# --------------------------------------------------------------------------
# 조인 — 사실이지 판정이 아니다
# --------------------------------------------------------------------------

def test_볼륨이_인스턴스에_연결된다(raw_run):
    payload = do_extract(raw_run)
    attached = find(payload, "정보",
                    lambda a: a["resource_type"] == "ec2_volume"
                    and a["lifecycle_state"]["value"] == "in-use")
    assert attached["parent_id"]["value"].endswith(attached["attached_to"]["value"])
    assert attached["relation_type"]["value"] == "attached_to"


def test_미연결_볼륨은_상위가_없다는_사실이_기록된다(raw_run):
    """관리자가 존재조차 모르는 볼륨. 결함사례 5의 직접 대상이다."""
    payload = do_extract(raw_run)
    orphan = find(payload, "정보",
                  lambda a: a["resource_type"] == "ec2_volume"
                  and a["lifecycle_state"]["value"] == "available")
    assert orphan["parent_id"]["value"] is None
    assert orphan["parent_id"]["reason"] == R.NOT_CONFIGURED


def test_전체개방_보안그룹이_자산_단위로_붙는다(raw_run):
    """SG sg-0abc에 0.0.0.0/0 → 22/tcp — 포트까지 있어야 근거 문구가 구체적이다."""
    payload = do_extract(raw_run)
    exposed = find(payload, "서버", lambda a: a["asset_name"]["value"] == "prd-web-01")
    assert exposed["infra_facts"]["open_sg_rule"]["value"] is True
    assert exposed["infra_facts"]["open_sg_detail"]["value"][0].endswith(":22/tcp")

    internal = find(payload, "서버", lambda a: a["asset_name"]["reason"] == R.TAG_ABSENT)
    assert internal["infra_facts"]["open_sg_rule"]["value"] is False


def test_보안그룹_목록을_못_받으면_개방없음으로_단정하지_않는다(raw_run):
    payload = do_extract(raw_run)
    stopped = find(payload, "서버", lambda a: a["asset_name"]["value"] == "batch-01")
    assert stopped["infra_facts"]["open_sg_rule"]["value"] is None
    assert stopped["infra_facts"]["open_sg_rule"]["reason"] == R.API_NULL


# --------------------------------------------------------------------------
# 계약 형태
# --------------------------------------------------------------------------

def test_자산유형_11종_키가_전부_있고_0건도_키가_있다(raw_run):
    payload = do_extract(raw_run)
    types = payload["asset_types"]
    expected = {"서버", "데이터(DBMS)", "정보시스템(응용프로그램)", "소프트웨어",
                "네트워크장비", "보안시스템", "PC", "정보", "설비", "시설", "가상자원"}
    assert set(types) == expected

    # 0건이라는 사실 자체가 결함사례 1·4의 리포트 대상이다.
    # 수집기가 생긴 유형은 여기서 빠진다 — 정보시스템은 frontend 수집기가 담당한다.
    for name in ("소프트웨어", "PC"):
        assert types[name]["assets"] == []
        assert types[name]["asset_count"] == 0
        assert types[name]["collector_exists"] is False
        assert "확인하지 않았다" in types[name]["note"]
    assert "수기" in types["설비"]["note"]

    # 수집기가 있는 유형은 0건이어도 "확인했다"로 나가야 한다.
    assert types["정보시스템(응용프로그램)"]["collector_exists"] is True


def test_모든_자산이_infra_facts_17키를_갖는다(raw_run):
    payload = do_extract(raw_run)
    for block in payload["asset_types"].values():
        for asset in block["assets"]:
            assert tuple(asset["infra_facts"]) == INFRA_FACT_KEYS, asset["asset_id"]


def test_모든_필드가_value와_reason을_갖는다(raw_run):
    payload = do_extract(raw_run)
    skip = {"asset_id", "asset_type", "resource_type", "account_id",
            "region", "run_id", "collected_at", "infra_facts", "tags_raw"}
    for block in payload["asset_types"].values():
        for asset in block["assets"]:
            for name, field in asset.items():
                if name in skip:
                    continue
                assert isinstance(field, dict), f"{asset['asset_id']}.{name}"
                assert "value" in field and "reason" in field
                assert field["reason"] is None or field["reason"] in R.ALL_REASONS


def test_임시_조인_키가_결과에_남지_않는다(raw_run):
    payload = do_extract(raw_run)
    for block in payload["asset_types"].values():
        for asset in block["assets"]:
            assert not [k for k in asset if k.startswith("_")]


def test_RDS는_TagList에서_태그를_읽는다(raw_run):
    """서비스마다 태그 필드명이 다른 걸 추출 단계에서 흡수한다."""
    payload = do_extract(raw_run)
    prd = find(payload, "데이터(DBMS)", lambda a: a["asset_name"]["value"] == "prd-db-01")
    assert prd["has_personal_info"]["value"] is True
    assert prd["infra_facts"]["multi_az"]["value"] is True
    assert prd["infra_facts"]["pitr_enabled"]["value"] is True

    dev = find(payload, "데이터(DBMS)", lambda a: a["asset_name"]["value"] == "dev-db-01")
    assert dev["infra_facts"]["pitr_enabled"]["value"] is False


def test_S3버킷은_자기_리전으로_기록된다(raw_run):
    """list_buckets는 전역이지만 버킷마다 리전이 다르다."""
    payload = do_extract(raw_run)
    seoul = find(payload, "정보", lambda a: a["asset_id"] == "arn:aws:s3:::isms-demo-plain")
    virginia = find(payload, "정보", lambda a: a["asset_id"] == "arn:aws:s3:::isms-demo-plain-use1")
    assert seoul["region"] == REGION
    assert virginia["region"] == ALT_REGION


def test_meta에_계약_정보가_실린다(raw_run):
    payload = do_extract(raw_run)
    meta = payload["meta"]
    assert meta["contract_version"]
    assert set(meta["reason_codes"]) == set(R.ALL_REASONS)
    assert set(meta["reason_codes_not_absence"]) == set(R.NOT_ABSENCE_REASONS)
    assert meta["infra_fact_keys"] == list(INFRA_FACT_KEYS)


def test_assets_json이_파일로_떨어진다(raw_run):
    payload = do_extract(raw_run)
    path = Path(payload["_path"])
    assert path.exists()
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["meta"]["total_assets"] == payload["meta"]["total_assets"]


def test_자산의_출처_API를_되짚을_수_있다(raw_run):
    """계약 v0.1의 source_api(증적 추적용) 대응.

    자산마다 같은 배열을 반복하지 않고 meta에 매핑표를 한 번 싣는다.
    """
    payload = do_extract(raw_run)
    table = payload["meta"]["source_api_by_resource"]

    server = find(payload, "서버", lambda a: a["resource_type"] == "ec2_instance")
    entry = table[server["resource_type"]]

    assert entry["service"] == "ec2"
    assert "describe_instances" in entry["apis"]
    assert "ec2:DescribeInstances" in entry["iam_actions"]
    # raw_path로 원본 덤프의 어느 자리인지 바로 찾아갈 수 있다
    assert entry["raw_path"].startswith("describe_instances")


def test_모든_리소스가_출처_API를_밝힌다(raw_run):
    """map 형태 리소스도 역산이 안 되면 source_apis로 직접 선언해야 한다."""
    table = do_extract(raw_run)["meta"]["source_api_by_resource"]
    empty = [name for name, entry in table.items() if not entry["apis"]]
    assert empty == [], f"출처 API를 밝히지 못한 리소스: {empty}"


def test_등급_필드는_A가_만들지_않는다(raw_run):
    """grade_proposed·grade_confirmed는 담당 B의 산출물이다(design.md §5.5)."""
    payload = do_extract(raw_run)
    assert "담당 B" in payload["meta"]["graded_by"]
    for block in payload["asset_types"].values():
        for asset in block["assets"]:
            assert "grade_proposed" not in asset
            assert "grade_confirmed" not in asset
