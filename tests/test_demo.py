"""S4 검증 — 데모가 시연 중 사고 없이 돌아가는가."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import demo
from collector.registry import all_required_actions


@pytest.fixture(autouse=True)
def in_tmp_cwd(tmp_path, monkeypatch):
    """데모는 snapshots/·output/에 쓴다. 저장소를 더럽히지 않게 격리한다."""
    repo = Path(__file__).resolve().parent.parent
    monkeypatch.chdir(tmp_path)
    for name in ("config",):
        (tmp_path / name).symlink_to(repo / name)
    return tmp_path


def test_데모가_끝까지_돈다(in_tmp_cwd, capsys):
    assert demo.main([]) == 0
    out = capsys.readouterr().out

    assert "collect" in out and "extract" in out
    assert (in_tmp_cwd / "output" / "iam_policy.json").exists()
    assert list((in_tmp_cwd / "snapshots" / "normalized").glob("*/assets.json"))
    assert list((in_tmp_cwd / "output").glob("*.xlsx"))


def test_실계정_자격증명을_덮어쓴다(monkeypatch):
    """발표 중 실수로 고객 계정을 긁는 사고를 막는다."""
    monkeypatch.setenv("AWS_PROFILE", "production")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAREALKEY")

    demo.guard_real_credentials()

    import os
    assert "AWS_PROFILE" not in os.environ
    assert os.environ["AWS_ACCESS_KEY_ID"] == "testing"


def test_run_id가_겹치면_이전_실행을_보존한다(tmp_path):
    """1분 안에 재실행해도 직전 결과가 날아가지 않아야 한다."""
    from collector.session import new_run_id

    base = new_run_id()
    (tmp_path / base).mkdir(parents=True)
    assert demo.resolve_run_id(tmp_path) == f"{base}-2"

    (tmp_path / f"{base}-2").mkdir()
    assert demo.resolve_run_id(tmp_path) == f"{base}-3"


def test_moto_산출물만_걸러내고_실자산은_남긴다(in_tmp_cwd):
    demo.main([])
    raw = json.loads(
        next((in_tmp_cwd / "snapshots" / "normalized").glob("*/assets.json"))
        .read_text(encoding="utf-8"))
    view = json.loads(
        next((in_tmp_cwd / "snapshots" / "normalized").glob("*/assets.demo-view.json"))
        .read_text(encoding="utf-8"))

    # 원본은 손대지 않는다
    assert raw["meta"]["total_assets"] > view["meta"]["total_assets"]
    assert "demo_filter" not in raw["meta"]

    # 걸러진 것은 전부 타 계정 소유이거나 moto 기본 키다
    account = raw["meta"]["account_id"]
    kept_snapshots = [
        a for a in view["asset_types"]["가상자원"]["assets"]
        if a["resource_type"] == "ec2_snapshot"
    ]
    assert kept_snapshots, "우리가 만든 스냅샷 2건은 남아야 한다"
    for asset in kept_snapshots:
        assert asset["owner_account"]["value"] == account

    # 서버·DB 같은 실자산은 하나도 안 빠진다
    for type_name in ("서버", "데이터(DBMS)", "정보"):
        assert (view["asset_types"][type_name]["asset_count"]
                == raw["asset_types"][type_name]["asset_count"])


def test_필터가_무엇을_왜_뺐는지_밝힌다(in_tmp_cwd, capsys):
    """조용히 빼면 assets.json을 열어본 사람이 숫자 불일치를 발견한다."""
    demo.main([])
    out = capsys.readouterr().out

    assert "데모 표시 필터" in out
    assert "OwnerIds" in out
    assert "원본 assets.json에는 그대로 남아 있다" in out


def test_raw_옵션은_거르지_않는다(in_tmp_cwd, capsys):
    demo.main(["--raw"])
    out = capsys.readouterr().out
    assert "데모 표시 필터" not in out
    assert not list((in_tmp_cwd / "snapshots" / "normalized").glob("*/assets.demo-view.json"))


def test_보안시스템_0건이_화면에서_사라지지_않는다(in_tmp_cwd, capsys):
    """데모 환경은 보안시스템을 일부러 안 만든다. 결함사례 1 재현이 목적이다.

    수집기가 있는데 0건인 유형이 화면에서 빠지면 시연 자체가 성립하지 않는다.
    """
    demo.main([])
    out = capsys.readouterr().out

    assert "수집했으나 자산이 없음" in out
    assert "보안시스템" in out
    assert "침입차단시스템" in out


def test_세_종류의_0건이_구분된다(in_tmp_cwd, capsys):
    demo.main([])
    out = capsys.readouterr().out

    assert "수집했으나 자산이 없음" in out      # 확인했더니 없다
    assert "수집기가 없어" in out                # 확인하지 않았다
    assert "자산 부재 아님" in out               # 못 읽었다


def test_리전별_분포를_보여준다(in_tmp_cwd, capsys):
    """미사용 리전 방치가 자산 누락 1순위라는 주장이 화면에 드러나야 한다."""
    demo.main([])
    out = capsys.readouterr().out
    assert "리전별 분포" in out
    assert "us-east-1" in out


def test_IAM_정책에_쓰기_액션이_있으면_데모가_실패한다(in_tmp_cwd, monkeypatch):
    """산출물이 '읽기 전용'을 주장하므로 자동으로 검증돼야 한다."""
    from collector import registry

    class Fake:
        client_name = "ec2"
        service_name = ""
        is_global = False
        required_actions = ("ec2:DeleteSnapshot",)

        @property
        def dump_name(self):
            return "ec2"

        @classmethod
        def write_actions(cls):
            return list(cls.required_actions)

    monkeypatch.setattr(registry, "discover", lambda: [Fake()])
    with pytest.raises(AssertionError, match="읽기 전용"):
        registry.all_required_actions()


def test_최소권한_정책이_산출물로_떨어진다(in_tmp_cwd):
    demo.main([])
    policy = json.loads((in_tmp_cwd / "output" / "iam_policy.json").read_text(encoding="utf-8"))
    actions = policy["Statement"][0]["Action"]
    assert actions == all_required_actions()
    assert policy["Statement"][0]["Effect"] == "Allow"
