"""원본 덤프 → ISMS-P 자산유형별 JSON.

**이 단계는 AWS에 접속하지 않는다.** snapshots/raw/ 만 읽는다.
그게 원본 보관 구조의 핵심 이점이다. B가 필드 추가를 요청하면
extract_map.yaml 한 줄 추가 + 재추출로 끝나야 한다.

2패스로 돈다.
  1패스 — 리소스별로 자산 레코드를 만들고 index_key로 색인한다
  2패스 — 색인을 써서 조인을 푼다 (parent_id, open_sg_rule, backup_exists)

순서를 어기면 "사본은 원본 등급을 상속"이 동작하지 않는다(결함사례 5).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import jmespath
import yaml

from . import reasons as R
from .dump import RAW_ROOT, AwsJsonEncoder
from .manual import annotate, print_manual_summary

log = logging.getLogger(__name__)

CONFIG_DIR = Path("config")
NORMALIZED_ROOT = Path("snapshots/normalized")

#: 등급 룰(docs/field-mapping.md §6)의 입력값. 17키를 못 박는다.
#: 여기 없는 키를 B가 쓰면 룰이 조용히 실패하므로 계약으로 고정한다.
INFRA_FACT_KEYS = (
    "backup_exists", "backup_source", "snapshot_count", "pitr_enabled",
    "multi_az", "in_asg", "public_exposed", "exposure_path",
    "encryption_at_rest", "encryption_in_transit", "open_sg_rule",
    "open_sg_detail", "versioning_enabled", "object_lock", "logging_enabled",
    "deletion_protection", "state",
)

CONTRACT_VERSION = "1.0"


# --------------------------------------------------------------------------
# 값 변환
# --------------------------------------------------------------------------

def _t_present(v: Any) -> bool:
    return v is not None and v != "" and v != []


def _t_bool(v: Any) -> Any:
    if isinstance(v, bool):
        return v
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("y", "yes", "true", "1"):
        return True
    if s in ("n", "no", "false", "0"):
        return False
    return None


def _t_csv(v: Any) -> Any:
    if v is None:
        return None
    return [part.strip() for part in str(v).split(",") if part.strip()]


def _t_enabled(v: Any) -> Any:
    if v is None:
        return None
    return str(v).strip().lower() == "enabled"


def _t_positive(v: Any) -> Any:
    if v is None:
        return None
    try:
        return float(v) > 0
    except (TypeError, ValueError):
        return None


def _t_enc_bool(v: Any) -> Any:
    """암호화 여부 bool → encryption_at_rest 값.

    True는 "KMS로 암호화됨"까지만 말할 수 있다. 고객관리형 키(CMK)인지
    AWS 관리형인지는 kms.describe_key를 불러야 알 수 있고 아직 안 부른다.
    그래서 SSE-KMS-CMK로 단정하지 않는다. 단정하면 B의 C-06이 잘못 발동한다.
    """
    if v is None:
        return None
    return "SSE-KMS" if v else "None"


def _t_sse_algorithm(v: Any) -> Any:
    if v is None:
        return None
    return {"AES256": "SSE-S3", "aws:kms": "SSE-KMS"}.get(v, v)


TRANSFORMS = {
    "present": _t_present,
    "bool": _t_bool,
    "csv": _t_csv,
    "enabled": _t_enabled,
    "positive": _t_positive,
    "enc_bool": _t_enc_bool,
    "sse_algorithm": _t_sse_algorithm,
    "str": lambda v: None if v is None else str(v),
}


# --------------------------------------------------------------------------
# 상태 표지 전파 — S3 미암호화가 NOT_CONFIGURED로 붙는 원리
# --------------------------------------------------------------------------

def status_on_path(item: Any, path: str) -> dict[str, Any] | None:
    """경로를 따라가다 __status__ 표지를 만나면 그걸 돌려준다.

    수집 단계가 "값 대신 상태"를 넣어둔 자리를 추출 단계가 알아채는 지점이다.
    이게 없으면 미암호화 버킷의 encryption이 그냥 API_NULL로 나가서
    "설정이 없다"는 사실이 사라진다.
    """
    node = item
    for part in path.split("."):
        key = part.split("[", 1)[0]
        if not isinstance(node, dict):
            return None
        if isinstance(node.get(key), dict) and "__status__" in node[key]:
            return node[key]
        node = node.get(key)
        if node is None:
            return None
    return None


def _reason_from_status(status: dict[str, Any]) -> dict[str, Any]:
    kind = status["__status__"]
    code = status.get("error_code")
    if kind == R.NOT_CONFIGURED:
        return R.missing(R.NOT_CONFIGURED)
    if kind == R.PERMISSION_DENIED:
        return R.missing(R.PERMISSION_DENIED, detail=code)
    if kind == R.OUT_OF_SCOPE:
        return R.missing(R.OUT_OF_SCOPE, detail=status.get("detail"))
    return R.missing(R.COLLECT_ERROR, detail=code or "unknown")


# --------------------------------------------------------------------------
# 태그 정규화 — 서비스마다 필드명이 다르다
# --------------------------------------------------------------------------

def normalize_tags(item: dict[str, Any], tags_path: str | None) -> tuple[dict[str, str], dict | None]:
    """Tags / TagList / TagSet 을 한 모양의 dict로.

    돌려주는 두 번째 값은 태그를 못 읽은 사유다(권한 부족 등).
    태그 '설정이 없음'(NoSuchTagSet)은 사유가 아니라 그냥 빈 태그다 —
    담당자 입장에서는 TAG_ABSENT, 즉 태그를 달면 해결되는 일이기 때문이다.
    """
    if not tags_path:
        return {}, None

    status = status_on_path(item, tags_path)
    if status is not None:
        if status["__status__"] == R.NOT_CONFIGURED:
            return {}, None
        return {}, status

    raw = jmespath.search(tags_path, item)
    if not raw:
        return {}, None
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}, None
    return {t["Key"]: t.get("Value", "") for t in raw if isinstance(t, dict) and "Key" in t}, None


# --------------------------------------------------------------------------
# 필드 하나 뽑기
# --------------------------------------------------------------------------

def resolve_field(
    spec: dict[str, Any],
    item: dict[str, Any],
    tags: dict[str, str],
    tag_status: dict | None,
) -> dict[str, Any]:
    if "const" in spec:
        return R.value(spec["const"])

    if "out_of_scope" in spec:
        return R.missing(R.OUT_OF_SCOPE, detail=spec["out_of_scope"])

    transform = TRANSFORMS.get(spec.get("transform", ""), lambda v: v)

    if "tag_present" in spec:
        # 태그의 '존재 여부' 자체가 답인 경우. 없는 것도 값이므로 TAG_ABSENT가 아니다.
        # aws:autoscaling:groupName 같은 AWS 관리 태그에 "태그를 다세요"라고 하면 틀린 안내다.
        if tag_status is not None:
            return _reason_from_status(tag_status)
        return R.value(bool(tags.get(spec["tag_present"])))

    if "tag" in spec:
        key = spec["tag"]
        if tag_status is not None:
            return _reason_from_status(tag_status)
        if key not in tags or tags[key] == "":
            return R.missing(R.TAG_ABSENT, detail=key)
        converted = transform(tags[key])
        if converted is None:
            return R.missing(R.API_NULL, hint=f"{key} 태그 값 '{tags[key]}'을 해석하지 못했습니다")
        return R.value(converted)

    path = spec["path"]
    status = status_on_path(item, path)
    if status is not None:
        return _reason_from_status(status)

    raw = jmespath.search(path, item)
    converted = transform(raw)
    if converted is None:
        return R.missing(R.API_NULL)
    return R.value(converted)


# --------------------------------------------------------------------------
# 원본 읽기
# --------------------------------------------------------------------------

def load_config(config_dir: Path | None = None) -> tuple[dict, dict]:
    config_dir = config_dir or CONFIG_DIR
    extract_map = yaml.safe_load((config_dir / "extract_map.yaml").read_text(encoding="utf-8"))
    asset_types = yaml.safe_load((config_dir / "isms_asset_types.yaml").read_text(encoding="utf-8"))
    return extract_map, asset_types


def load_raw(run_dir: Path) -> tuple[dict, list[dict]]:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json이 없다: {run_dir}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    dumps = []
    for path in sorted(run_dir.rglob("*.json")):
        if path.name == "manifest.json":
            continue
        dumps.append(json.loads(path.read_text(encoding="utf-8")))
    return manifest, dumps


def latest_run_id(root: Path | None = None) -> str:
    root = root or RAW_ROOT
    runs = sorted(p.name for p in root.glob("run-*") if (p / "manifest.json").exists())
    if not runs:
        raise FileNotFoundError(f"{root} 아래에 실행 결과가 없다. 먼저 collect를 돌려라")
    return runs[-1]


# --------------------------------------------------------------------------
# 1패스 — 자산 레코드 만들기
# --------------------------------------------------------------------------

def _iterate_items(spec: dict, data: dict) -> list[dict[str, Any]]:
    iterate = spec["iterate"]
    if isinstance(iterate, str):
        found = jmespath.search(iterate, data)
        items = [i for i in (found or []) if isinstance(i, dict)]
    else:
        node = jmespath.search(iterate["map"], data)
        if not isinstance(node, dict):
            return []
        key_as = iterate["key_as"]
        items = [{**v, key_as: k} for k, v in node.items() if isinstance(v, dict)]

    where = spec.get("where")
    if where:
        # 자산으로 등재할 것만 남긴다. KMS는 고객관리형 키(CUSTOMER)만 자산이다.
        items = [i for i in items if jmespath.search(where, i)]
    return items


def _merge_items(spec: dict, data: dict, items: list[dict]) -> list[dict]:
    merge = spec.get("merge")
    if not merge:
        return items
    source = jmespath.search(merge["from"], data) or []
    key = merge["match_key"]
    lookup = {row[key]: row for row in source if isinstance(row, dict) and key in row}
    return [{**lookup.get(item.get(key), {}), **item} for item in items]


def _format_asset_id(template: str, item: dict, region: str, account: str) -> str | None:
    out = template.replace("{region}", region).replace("{account}", account)
    while "{" in out:
        start = out.index("{")
        end = out.index("}", start)
        field = out[start + 1:end]
        found = jmespath.search(field, item)
        if found is None:
            return None
        out = out[:start] + str(found) + out[end + 1:]
    return out


def _source_failure(spec: dict, data: dict) -> dict | None:
    """이 리소스의 원천 API 자체가 실패했는가.

    0건이 "자산이 없다"인지 "못 읽었다"인지 구분하려면 반드시 봐야 한다.
    권한이 없어 describe_instances가 실패한 리전을 "서버 0대"로 적으면
    자산 목록 전체가 거짓이 된다.
    """
    iterate = spec["iterate"]
    path = iterate if isinstance(iterate, str) else iterate["map"]
    root = path.split(".", 1)[0].split("[", 1)[0]
    node = data.get(root)
    if isinstance(node, dict) and "__status__" in node:
        return node
    return None


def build_assets(extract_map: dict, dumps: list[dict]) -> tuple[list[dict], list[dict]]:
    """1패스. 자산 레코드와 수집 실패 기록을 만든다."""
    resources = extract_map["resources"]
    contract_fields = sorted({f for r in resources.values() for f in r.get("fields", {})})

    assets: list[dict] = []
    issues: list[dict] = []

    for dump in dumps:
        meta, data = dump["meta"], dump["data"]
        for res_name, spec in resources.items():
            if spec["service"] != meta["service"]:
                continue

            failure = _source_failure(spec, data)
            if failure is not None:
                issues.append({
                    "region": meta["region"],
                    "service": meta["service"],
                    "resource_type": res_name,
                    "status": failure["__status__"],
                    "error_code": failure.get("error_code"),
                })
                continue

            items = _merge_items(spec, data, _iterate_items(spec, data))
            for item in items:
                asset = _build_one(res_name, spec, item, meta, contract_fields)
                if asset is not None:
                    assets.append(asset)

    return assets, issues


def _build_one(res_name: str, spec: dict, item: dict, meta: dict,
               contract_fields: list[str]) -> dict | None:
    region = meta["region"]
    if spec.get("region_from"):
        found = jmespath.search(spec["region_from"], item)
        region = found or ("us-east-1" if "LocationConstraint" in spec["region_from"] else region)

    asset_id = _format_asset_id(spec["asset_id"], item, region, meta["account_id"])
    if asset_id is None:
        log.warning("%s: asset_id를 만들지 못해 건너뛴다", res_name)
        return None

    tags, tag_status = normalize_tags(item, spec.get("tags"))
    if spec.get("tags_unavailable"):
        # 태그 조회 API를 아직 안 부르는 리소스. "태그를 다세요"는 틀린 안내다.
        tag_status = {"__status__": R.OUT_OF_SCOPE, "detail": spec["tags_unavailable"]}
    declared = spec.get("fields", {})

    asset: dict[str, Any] = {
        "asset_id": asset_id,
        "asset_type": spec["asset_type"],
        "resource_type": res_name,
        "account_id": meta["account_id"],
        "region": region,
        "run_id": meta["run_id"],
        "collected_at": meta["collected_at"],
    }

    for name in contract_fields:
        if name in declared:
            asset[name] = resolve_field(declared[name], item, tags, tag_status)
        else:
            # 이 리소스가 선언하지 않은 필드 = 이 자산유형에 개념이 없다
            asset[name] = R.missing(R.NOT_APPLICABLE)

    asset["parent_id"] = R.missing(R.NOT_APPLICABLE)
    asset["relation_type"] = R.missing(R.NOT_APPLICABLE)
    asset["infra_facts"] = _build_infra_facts(spec, item, tags, tag_status)
    asset["tags_raw"] = tags
    # 2패스에서만 쓰는 임시 키. resolve_relations 끝에서 지운다.
    asset["_index_key"] = jmespath.search(spec["index_key"], item)
    asset["_security_groups"] = jmespath.search(spec["security_groups"], item) if spec.get("security_groups") else None
    asset["_parent_ref"] = jmespath.search(spec["parent"]["via"], item) if spec.get("parent") else None
    asset["_backupable"] = bool(spec.get("backupable"))
    return asset


def _build_infra_facts(spec: dict, item: dict, tags: dict, tag_status: dict | None) -> dict:
    declared = spec.get("infra_facts") or {}
    out_of_scope = spec.get("infra_facts_out_of_scope") or {}
    facts: dict[str, Any] = {}
    for key in INFRA_FACT_KEYS:
        if key in declared:
            facts[key] = resolve_field(declared[key], item, tags, tag_status)
        elif key in out_of_scope:
            facts[key] = R.missing(R.OUT_OF_SCOPE, detail=out_of_scope[key])
        else:
            facts[key] = R.missing(R.NOT_APPLICABLE)
    return facts


# --------------------------------------------------------------------------
# 2패스 — 조인
# --------------------------------------------------------------------------

def resolve_relations(extract_map: dict, assets: list[dict], dumps: list[dict],
                      issues: list[dict] | None = None) -> None:
    """색인을 만들고 parent_id·open_sg_rule·backup_exists를 채운다.

    조인은 사실이지 판정이 아니다. 등급을 매기는 건 여전히 B다.

    issues는 1패스가 기록한 수집 실패 목록이다. 조인이 실패했을 때
    "못 읽었다"와 "원본이 없다"를 가르는 데 쓴다.
    """
    resources = extract_map["resources"]

    index: dict[tuple[str, str, Any], dict] = {}
    for asset in assets:
        index[(asset["resource_type"], asset["region"], asset["_index_key"])] = asset

    # 목록 조회에 실패한 (리소스, 리전). 이 조합은 색인이 불완전하다.
    failed = {(i["resource_type"], i["region"]) for i in (issues or [])}

    _resolve_parents(resources, assets, index, failed)
    _resolve_security_groups(assets, dumps)
    _resolve_backup(assets, dumps)
    _resolve_snapshot_counts(assets)

    for asset in assets:
        for key in ("_index_key", "_security_groups", "_parent_ref", "_backupable"):
            asset.pop(key, None)


def _resolve_parents(resources: dict, assets: list[dict], index: dict,
                     failed: set[tuple[str, str]]) -> None:
    for asset in assets:
        spec = resources[asset["resource_type"]]
        parent = spec.get("parent")
        if not parent:
            continue
        ref = asset.get("_parent_ref")
        if ref is None:
            # 붙어 있지 않은 자산. 미연결 볼륨이 바로 이 경우다.
            asset["parent_id"] = R.missing(R.NOT_CONFIGURED, hint="연결된 상위 자산이 없습니다")
            asset["relation_type"] = R.missing(R.NOT_CONFIGURED)
            continue
        found = index.get((parent["target"], asset["region"], ref))
        if found is None:
            # 색인에 없다. 사정이 셋으로 갈리고 조치가 전부 다르다.
            # 색인은 "우리가 수집한 것"이므로, 없다는 사실만으로 부재를 단정할 수 없다.
            owner = asset.get("owner_account", {}).get("value")
            if (parent["target"], asset["region"]) in failed:
                # 목록 조회가 실패했다. 정말 모른다 → 권한을 열고 재수집
                asset["parent_id"] = R.missing(
                    R.COLLECT_ERROR,
                    hint=f"{parent['target']} 목록 조회에 실패해 원본 {ref}를 확인하지 못했습니다",
                )
            elif owner and owner != asset["account_id"]:
                # 남의 계정 자원이다. 그 계정의 볼륨은 애초에 수집 대상이 아니라
                # 색인에 있을 수 없다. "삭제됐다"고 쓰면 없는 사실을 지어내는 것이다.
                asset["parent_id"] = R.missing(
                    R.OUT_OF_SCOPE,
                    detail=f"다른 계정({owner}) 소유 자산이라 원본 {parent['target']}을 "
                           f"수집 범위에서 확인할 수 없습니다",
                )
            else:
                # 우리 계정이고 목록도 다 읽었는데 없다 → 원본이 삭제된 것.
                # 스냅샷이 원본 볼륨보다 오래 사는 건 정상이라 이 경우가 있다.
                # COLLECT_ERROR로 적으면 재수집해도 안 나올 것에 "재수집하라"는
                # 틀린 지시가 나가고, 부재 아님 사유라 미확인 건수까지 부풀린다.
                asset["parent_id"] = R.missing(
                    R.NOT_CONFIGURED,
                    hint=f"원본 {parent['target']} {ref}가 이미 삭제되었습니다",
                )
            asset["relation_type"] = R.value(parent["relation"])
            continue
        asset["parent_id"] = R.value(found["asset_id"])
        asset["relation_type"] = R.value(parent["relation"])


def _resolve_security_groups(assets: list[dict], dumps: list[dict]) -> None:
    """전체 개방 인바운드 규칙을 자산 단위로 채운다.

    "SG sg-0abc에 0.0.0.0/0 → 22/tcp 인바운드 허용" 처럼 포트까지 적어야
    B의 근거 문구가 구체적으로 나온다(docs/field-mapping.md §4.7).
    """
    by_region: dict[str, dict[str, list[str]]] = {}
    for dump in dumps:
        if dump["meta"]["service"] != "ec2":
            continue
        groups = dump["data"].get("describe_security_groups")
        if not isinstance(groups, dict) or "SecurityGroups" not in groups:
            continue
        region_map = by_region.setdefault(dump["meta"]["region"], {})
        for group in groups["SecurityGroups"]:
            region_map[group["GroupId"]] = _open_rules(group)

    for asset in assets:
        if asset["resource_type"] == "ec2_security_group":
            # 보안그룹 자산은 자기 자신의 규칙을 보고한다
            group_ids = [asset["serial_no"]["value"]]
        elif asset.get("_security_groups") is not None:
            group_ids = asset["_security_groups"]
        else:
            continue  # 보안그룹 개념이 없는 자산유형. NOT_APPLICABLE로 둔다

        if not group_ids:
            # 개념은 있는데 API가 목록을 안 줬다. "개방 규칙 없음"으로 단정하지 않는다.
            asset["infra_facts"]["open_sg_rule"] = R.missing(R.API_NULL)
            asset["infra_facts"]["open_sg_detail"] = R.missing(R.API_NULL)
            continue

        region_map = by_region.get(asset["region"], {})
        detail: list[str] = []
        unknown = [gid for gid in group_ids if gid not in region_map]
        for gid in group_ids:
            detail.extend(region_map.get(gid, []))

        if unknown:
            # 규칙을 못 읽은 보안그룹이 있다. False로 적으면 개방 규칙을 놓친다.
            asset["infra_facts"]["open_sg_rule"] = R.missing(
                R.COLLECT_ERROR, hint=f"보안그룹 {', '.join(unknown)}의 규칙을 수집 결과에서 찾지 못했습니다")
            asset["infra_facts"]["open_sg_detail"] = R.value(detail)
            continue

        asset["infra_facts"]["open_sg_rule"] = R.value(bool(detail))
        asset["infra_facts"]["open_sg_detail"] = R.value(detail)


def _open_rules(group: dict) -> list[str]:
    found = []
    for perm in group.get("IpPermissions", []):
        wide = any(r.get("CidrIp") == "0.0.0.0/0" for r in perm.get("IpRanges", []))
        wide = wide or any(r.get("CidrIpv6") == "::/0" for r in perm.get("Ipv6Ranges", []))
        if not wide:
            continue
        proto = perm.get("IpProtocol", "-1")
        if proto == "-1":
            ports = "all"
        else:
            lo, hi = perm.get("FromPort"), perm.get("ToPort")
            ports = f"{lo}" if lo == hi else f"{lo}-{hi}"
        found.append(f"{group['GroupId']}:{ports}/{proto}")
    return found


def _resolve_backup(assets: list[dict], dumps: list[dict]) -> None:
    """backup_exists는 스냅샷 개수가 아니라 list_protected_resources로 판정한다.

    "스냅샷 3건 존재"는 심사에서 반박당하지만
    "백업 계획에 포함되어 최종 보호 시각 ○○"는 통과한다.
    """
    protected: dict[str, dict] = {}
    failure: dict | None = None
    for dump in dumps:
        if dump["meta"]["service"] != "backup":
            continue
        node = dump["data"].get("list_protected_resources")
        if isinstance(node, dict) and "__status__" in node:
            failure = failure or node
            continue
        for row in (node or {}).get("Results", []):
            protected[row["ResourceArn"]] = row

    for asset in assets:
        if not asset.get("_backupable"):
            continue  # AWS Backup 대상이 아닌 자산유형. NOT_APPLICABLE로 둔다
        if failure is not None and asset["asset_id"] not in protected:
            # 조회 자체가 실패했다. "백업 없음"이라고 쓰면 무결성 등급이 틀린다.
            asset["infra_facts"]["backup_exists"] = R.missing(
                R.COLLECT_ERROR, detail=failure.get("error_code"))
            asset["infra_facts"]["backup_source"] = R.missing(
                R.COLLECT_ERROR, detail=failure.get("error_code"))
            continue
        row = protected.get(asset["asset_id"])
        if row is None:
            asset["infra_facts"]["backup_exists"] = R.value(False)
            asset["infra_facts"]["backup_source"] = R.missing(R.NOT_CONFIGURED)
        else:
            asset["infra_facts"]["backup_exists"] = R.value(True)
            asset["infra_facts"]["backup_source"] = R.value(
                f"AWS Backup: vault={row.get('LastBackupVaultArn', '?')} "
                f"last={row.get('LastBackupTime', '?')}"
            )


def _resolve_snapshot_counts(assets: list[dict]) -> None:
    counts: dict[str, int] = {}
    for asset in assets:
        if asset["resource_type"] != "ec2_snapshot":
            continue
        parent = asset["parent_id"].get("value")
        if parent:
            counts[parent] = counts.get(parent, 0) + 1

    for asset in assets:
        if asset["resource_type"] != "ec2_volume":
            continue
        asset["infra_facts"]["snapshot_count"] = R.value(counts.get(asset["asset_id"], 0))


# --------------------------------------------------------------------------
# 조립
# --------------------------------------------------------------------------

_API_PREFIXES = ("describe_", "list_", "get_", "batch_")


def _declared_apis(spec: dict) -> list[str]:
    """이 리소스가 실제로 읽는 원본 API 이름들.

    yaml 선언에서 역산한다. S3처럼 버킷마다 get_bucket_* 을 여러 번 부르는 경우
    그 목록이 필드 경로에 그대로 드러나 있다.

    iterate가 map 형태이면 그 키(detectors·keys)는 수집기가 만든 이름이지 API가 아니라
    역산이 안 된다. 그런 리소스는 source_apis로 직접 선언한다.
    """
    if spec.get("source_apis"):
        return sorted(spec["source_apis"])

    apis: set[str] = set()

    def add(path: str | None) -> None:
        if not path or "." not in path:
            return
        root = path.split(".", 1)[0].split("[", 1)[0]
        if root.startswith(_API_PREFIXES):
            apis.add(root)

    iterate = spec["iterate"]
    if isinstance(iterate, str):
        add(iterate)
    if spec.get("merge"):
        add(spec["merge"]["from"])
    add(spec.get("tags"))
    add(spec.get("region_from"))
    declared = list((spec.get("fields") or {}).values())
    declared += list((spec.get("infra_facts") or {}).values())
    for decl in declared:
        add(decl.get("path"))
    return sorted(apis)


def build_source_api_map(extract_map: dict, dumps: list[dict]) -> dict:
    """자산이 어느 API 응답에서 나왔는지 되짚는 표. 증적 추적용.

    자산 레코드마다 넣으면 같은 배열이 수천 번 반복되므로 meta에 한 번만 싣는다.
    B는 자산의 resource_type으로 이 표를 조회한다.

    iam_actions는 그 수집기가 선언한 액션 전체(서비스 단위)다.
    apis처럼 리소스 단위로 좁혀져 있지 않다.
    """
    actions_by_service: dict[str, set[str]] = {}
    for dump in dumps:
        actions_by_service.setdefault(dump["meta"]["service"], set()).update(
            dump["meta"].get("source_api") or [])

    out: dict[str, dict] = {}
    for name, spec in extract_map["resources"].items():
        service = spec["service"]
        iterate = spec["iterate"]
        out[name] = {
            "service": service,
            "raw_path": iterate if isinstance(iterate, str) else f"{iterate['map']} (map)",
            "apis": _declared_apis(spec),
            "iam_actions": sorted(actions_by_service.get(service, [])),
        }
    return out


def group_by_asset_type(asset_types_cfg: dict, assets: list[dict]) -> dict:
    """자산유형 11종 키를 전부 만든다. 0건이면 빈 배열이다.

    키가 없으면 "수집기가 빠뜨린 것"과 "실제로 0건인 것"을 구분할 수 없다.
    """
    grouped: dict[str, Any] = {}
    for type_name, cfg in asset_types_cfg["asset_types"].items():
        members = [a for a in assets if a["asset_type"] == type_name]
        collectable = cfg.get("aws_collectable") or []
        grouped[type_name] = {
            "isms_required_items": cfg.get("required_items", []),
            "aws_collectable": collectable,
            "collector_exists": bool(collectable),
            "asset_count": len(members),
            "assets": members,
        }
        if not collectable:
            grouped[type_name]["note"] = (
                "이 유형의 AWS 수집기가 아직 없다. 0건은 '자산이 없다'가 아니라 '확인하지 않았다'는 뜻이다."
                if not cfg.get("manual_only")
                else "AWS API 대상이 아닌 유형이다. 수기 등재와 제외 사유 문서화가 필요하다."
            )
    return grouped


def run_extract(
    *,
    run_id: str | None = None,
    raw_root: Path | None = None,
    out_root: Path | None = None,
    config_dir: Path | None = None,
) -> dict:
    raw_root = raw_root or RAW_ROOT
    out_root = out_root or NORMALIZED_ROOT
    run_id = run_id or latest_run_id(raw_root)

    extract_map, asset_types_cfg = load_config(config_dir)
    manifest, dumps = load_raw(raw_root / run_id)

    assets, issues = build_assets(extract_map, dumps)
    resolve_relations(extract_map, assets, dumps, issues)

    payload = {
        "meta": {
            "contract_version": CONTRACT_VERSION,
            "run_id": run_id,
            "account_id": manifest["account_id"],
            "account_alias": manifest.get("account_alias"),
            "collected_at": manifest["started_at"],
            "regions": manifest["regions"],
            "reason_codes": list(R.ALL_REASONS),
            "reason_codes_not_absence": list(R.NOT_ABSENCE_REASONS),
            "infra_fact_keys": list(INFRA_FACT_KEYS),
            # 자산이 어느 API에서 나왔는지 되짚는 표(증적 추적용).
            # 자산마다 싣지 않고 resource_type으로 조회하게 한다.
            "source_api_by_resource": build_source_api_map(extract_map, dumps),
            # grade_proposed·grade_confirmed는 담당 B의 산출물이다(docs/design.md §5.5).
            # A는 자리를 만들지 않는다. 판정 필드가 A 산출물에 없는 것이 역할 경계다.
            "graded_by": "담당 B — grade_proposed / grade_confirmed는 이 파일에 없다",
            "total_assets": len(assets),
            "collection_issues": issues,
        },
        "asset_types": group_by_asset_type(asset_types_cfg, assets),
    }

    # 못 채운 칸을 빈 칸으로 두지 않는다. 누가·왜·어떻게까지 실어 보낸다.
    annotate(payload, config_dir)

    out_dir = out_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "assets.json"
    out_path.write_text(
        json.dumps(payload, cls=AwsJsonEncoder, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    payload["_path"] = str(out_path)
    return payload


def print_extract_summary(payload: dict) -> None:
    """담당자가 볼 요약. 자동 수집분과 '확인하지 않은 것'을 반드시 갈라 보여준다."""
    meta = payload["meta"]
    print()
    print(f"  run_id      {meta['run_id']}")
    print(f"  계정         {meta['account_id']}")
    print(f"  자산 합계    {meta['total_assets']}건  →  {payload.get('_path')}")
    print()
    print("  [자동 수집]")
    for name, block in payload["asset_types"].items():
        if block["asset_count"]:
            print(f"    {name:24s} {block['asset_count']:5d}건")
    print()

    # 수집기가 있는데 0건 — "확인했더니 정말 없다".
    # 이걸 안 보여주면 결함사례 1(보안시스템 누락)이 화면에서 통째로 사라진다.
    # "확인했더니 없다"와 "확인하지 않았다"는 심사에서 완전히 다른 말이다.
    confirmed_empty = [
        (name, block) for name, block in payload["asset_types"].items()
        if block["collector_exists"] and not block["asset_count"]
    ]
    if confirmed_empty:
        print("  [0건 — 수집했으나 자산이 없음. 통제 부재 자체가 결함 소지]")
        for name, block in confirmed_empty:
            missing = [r["item_name"] for r in block.get("manual_required", [])
                       if r.get("note") == "AWS 수집 결과 0건"]
            detail = f"  ← {', '.join(missing)} 미확인" if missing else ""
            print(f"    {name:24s}     0건{detail}")
        print()

    no_collector = [
        (name, block) for name, block in payload["asset_types"].items()
        if not block["collector_exists"]
    ]
    if no_collector:
        print("  [0건 — 수집기가 없어 '확인하지 않음'. 자산이 없다는 뜻이 아니다]")
        for name, block in no_collector:
            manual = "수기 등재 대상" if "AWS API 대상이 아닌" in block.get("note", "") else "수집기 필요"
            print(f"    {name:24s}     0건   ({manual})")
        print()

    # 수집기는 있는데 그 안의 특정 통제만 0건인 경우 (보안시스템에 GuardDuty는 있고 WAF는 없음)
    partial = []
    for name, block in payload["asset_types"].items():
        if not (block["collector_exists"] and block["asset_count"]):
            continue
        missing = [r["item_name"] for r in block.get("manual_required", [])
                   if r.get("note") == "AWS 수집 결과 0건"]
        if missing:
            partial.append((name, missing))
    if partial:
        print("  [일부 통제 미확인 — 유형에 자산은 있으나 해당 통제가 0건]")
        for name, missing in partial:
            print(f"    {name:24s} {', '.join(missing)}")
        print()

    issues = meta["collection_issues"]
    if issues:
        print("  [원천 API 조회 실패 — 자산 부재로 오인 금지]")
        seen: dict[tuple[str, str], int] = {}
        for issue in issues:
            key = (issue["resource_type"], issue["status"])
            seen[key] = seen.get(key, 0) + 1
        for (resource, status), count in sorted(seen.items()):
            print(f"    {resource:24s} {status:18s} {count:3d}개 리전")
        print()

    if "manual_todo" in payload:
        print_manual_summary(payload)
