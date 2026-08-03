"""데모용 가짜 AWS 환경. moto 안에서만 만든다. 실제 계정은 쓰지 않는다.

갭이 실제로 잡히는 걸 보여주려면 깨끗한 환경으로는 안 된다.
태그가 빠지고, 암호화가 없고, 아무도 안 쓰는 볼륨이 굴러다니는 환경이 필요하다.

**보안시스템은 일부러 아무것도 만들지 않는다.** 결함사례 1 재현이 목적이다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import boto3

REGION = "ap-northeast-2"
ALT_REGION = "us-east-1"
AMI_ID = "ami-12345678"


def _tags(**kwargs: str) -> list[dict]:
    return [{"Key": k, "Value": v} for k, v in kwargs.items()]


#: 태그 표준 전체를 갖춘 자산 (docs/field-mapping.md §2.1)
COMPLETE = dict(
    Environment="Prod",
    InventoryCategory="WebServer",
    OwnerDept="인프라운영팀",
    OwnerManager="김실무",
    OwnerResponsible="박책임",
    HandlePI="N",
    InScope="Y",
    ServiceName="포털",
)


def build(region: str = REGION) -> dict:
    ec2 = boto3.client("ec2", region_name=region)
    made: dict = {"region": region}

    vpc_id = ec2.describe_vpcs()["Vpcs"][0]["VpcId"]
    open_sg = ec2.create_security_group(
        GroupName="prd-web-sg", Description="운영 웹 서버", VpcId=vpc_id)["GroupId"]
    ec2.authorize_security_group_ingress(
        GroupId=open_sg,
        IpPermissions=[
            {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
             "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
            {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443,
             "IpRanges": [{"CidrIp": "0.0.0.0/0"}]},
        ],
    )
    internal_sg = ec2.create_security_group(
        GroupName="prd-db-sg", Description="운영 DB", VpcId=vpc_id)["GroupId"]
    ec2.authorize_security_group_ingress(
        GroupId=internal_sg,
        IpPermissions=[{"IpProtocol": "tcp", "FromPort": 3306, "ToPort": 3306,
                        "IpRanges": [{"CidrIp": "10.0.0.0/8"}]}],
    )

    # 서버 — 태그 완비 2대 / 태그 전무 3대 / 중지 1대
    complete = []
    for name, category in (("prd-web-01", "WebServer"), ("prd-was-01", "WAS")):
        inst = ec2.run_instances(
            ImageId=AMI_ID, MinCount=1, MaxCount=1, InstanceType="t3.large",
            SecurityGroupIds=[open_sg],
            TagSpecifications=[{"ResourceType": "instance",
                                "Tags": _tags(Name=name, **{**COMPLETE, "InventoryCategory": category})}],
        )["Instances"][0]
        complete.append(inst["InstanceId"])

    untagged = []
    for _ in range(3):
        inst = ec2.run_instances(
            ImageId=AMI_ID, MinCount=1, MaxCount=1, InstanceType="t3.micro",
            SecurityGroupIds=[internal_sg],
        )["Instances"][0]
        untagged.append(inst["InstanceId"])

    stopped = ec2.run_instances(
        ImageId=AMI_ID, MinCount=1, MaxCount=1, InstanceType="t3.small",
        SecurityGroupIds=[internal_sg],
        TagSpecifications=[{"ResourceType": "instance", "Tags": _tags(Name="batch-01")}],
    )["Instances"][0]["InstanceId"]
    ec2.stop_instances(InstanceIds=[stopped])
    made["instances"] = {"complete": complete, "untagged": untagged, "stopped": stopped}

    # 볼륨 — 연결 2 / 미연결 2. 미연결이 "관리자가 존재조차 모르는 자산"이다.
    az = f"{region}a"
    attached, orphans = [], []
    for index, instance_id in enumerate(complete):
        vol = ec2.create_volume(AvailabilityZone=az, Size=20 + index, Encrypted=True)
        ec2.attach_volume(VolumeId=vol["VolumeId"], InstanceId=instance_id, Device="/dev/sdf")
        attached.append(vol["VolumeId"])
    for size in (8, 100):
        vol = ec2.create_volume(AvailabilityZone=az, Size=size, Encrypted=False)
        orphans.append(vol["VolumeId"])
    made["volumes"] = {"attached": attached, "orphan": orphans}

    # 오래된 스냅샷 2개 — 원본 볼륨은 이미 사라졌다고 가정하지 않고 연결을 남긴다
    snapshots = []
    for vol_id in orphans:
        snap = ec2.create_snapshot(VolumeId=vol_id, Description="수동 백업(방치)")
        snapshots.append(snap["SnapshotId"])
    made["snapshots"] = snapshots

    # S3 — 암호화 1 / 미암호화 1 / 퍼블릭 1
    s3 = boto3.client("s3", region_name=region)
    kwargs = {} if region == "us-east-1" else {
        "CreateBucketConfiguration": {"LocationConstraint": region}}

    s3.create_bucket(Bucket="corp-prd-secure", **kwargs)
    s3.put_bucket_encryption(
        Bucket="corp-prd-secure",
        ServerSideEncryptionConfiguration={
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]},
    )
    s3.put_bucket_versioning(Bucket="corp-prd-secure",
                             VersioningConfiguration={"Status": "Enabled"})
    s3.put_bucket_tagging(Bucket="corp-prd-secure", Tagging={"TagSet": _tags(
        Name="corp-prd-secure", OwnerDept="데이터팀", OwnerManager="이실무",
        OwnerResponsible="박책임", HandlePI="Y", PIItems="name,phone,email",
        DataSource="Self", InScope="Y", InventoryCategory="File")})

    s3.create_bucket(Bucket="corp-legacy-dump", **kwargs)  # 미암호화·태그 없음

    s3.create_bucket(Bucket="corp-public-assets", **kwargs)
    s3.put_bucket_policy(Bucket="corp-public-assets", Policy=(
        '{"Version":"2012-10-17","Statement":[{"Sid":"PublicRead","Effect":"Allow",'
        '"Principal":"*","Action":"s3:GetObject",'
        '"Resource":"arn:aws:s3:::corp-public-assets/*"}]}'))
    made["buckets"] = ["corp-prd-secure", "corp-legacy-dump", "corp-public-assets"]

    # RDS — 백업 있는 것 / 없는 것
    rds = boto3.client("rds", region_name=region)
    rds.create_db_instance(
        DBInstanceIdentifier="prd-portal-db", DBInstanceClass="db.r6g.large",
        Engine="mysql", EngineVersion="8.0.35", AllocatedStorage=100,
        BackupRetentionPeriod=7, StorageEncrypted=True, MultiAZ=True,
        DeletionProtection=True, PubliclyAccessible=False,
        VpcSecurityGroupIds=[internal_sg],
        Tags=_tags(Name="prd-portal-db", OwnerDept="데이터팀", OwnerManager="이실무",
                   OwnerResponsible="박책임", HandlePI="Y", PIItems="name,phone,rrn",
                   DataSource="ThirdParty", InScope="Y", Environment="Prod",
                   InventoryCategory="DB"),
    )
    rds.create_db_instance(
        DBInstanceIdentifier="dev-sandbox-db", DBInstanceClass="db.t3.micro",
        Engine="mysql", AllocatedStorage=20, BackupRetentionPeriod=0,
        StorageEncrypted=False, PubliclyAccessible=True,
        VpcSecurityGroupIds=[open_sg],
    )
    made["db_instances"] = ["prd-portal-db", "dev-sandbox-db"]

    # 보안시스템은 만들지 않는다. 결함사례 1 재현이 목적이다.
    return made


def build_secondary(region: str = ALT_REGION) -> dict:
    """다른 리전에 자산을 하나 심는다.

    "미사용 리전 방치가 자산 누락 1순위"라는 주장을 시연하려면
    아무도 안 보는 리전에 자산이 있어야 한다(결함사례 4).
    """
    ec2 = boto3.client("ec2", region_name=region)
    inst = ec2.run_instances(
        ImageId=AMI_ID, MinCount=1, MaxCount=1, InstanceType="t3.micro",
    )["Instances"][0]

    s3 = boto3.client("s3", region_name=region)
    s3.create_bucket(Bucket="corp-forgotten-logs")
    return {"region": region, "instance": inst["InstanceId"],
            "bucket": "corp-forgotten-logs"}


def describe() -> list[str]:
    """무엇을 왜 심었는지. 발표에서 그대로 읽을 수 있게."""
    return [
        "서버 6대       — 태그 완비 2 / 태그 전무 3 / 중지 1",
        "볼륨 4개       — 연결 2 / 미연결 2  (미연결 = 관리자가 존재조차 모르는 자산)",
        "스냅샷 2개     — 미연결 볼륨의 수동 백업. 원본 등급 상속 대상",
        "버킷 3개       — 암호화·태그 완비 1 / 미암호화·태그 전무 1 / 퍼블릭 1",
        "DB 2대         — 백업 7일·MultiAZ·개인정보 보유 1 / 백업 없음·퍼블릭 1",
        "보안그룹 2개   — 0.0.0.0/0 개방 1 / 내부 전용 1",
        "다른 리전      — 아무도 안 보는 리전에 EC2 1대·버킷 1개 (결함사례 4)",
        "보안시스템     — 일부러 아무것도 만들지 않음 (결함사례 1 재현)",
    ]
