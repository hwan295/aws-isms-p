"""moto 안에 지저분한 가짜 환경을 만든다. 실제 AWS 계정은 쓰지 않는다.

갭이 실제로 잡히는 걸 보여주려면 깨끗한 환경으로는 안 된다.
태그가 빠지고, 암호화가 없고, 아무도 안 쓰는 볼륨이 굴러다니는 환경이 필요하다.
"""

from __future__ import annotations

import boto3

REGION = "ap-northeast-2"
ALT_REGION = "us-east-1"

#: 태그 표준 (docs/field-mapping.md §2.1). 용도는 InventoryCategory다.
FULL_TAGS = [
    {"Key": "Name", "Value": "prd-web-01"},
    {"Key": "Environment", "Value": "Prod"},
    {"Key": "InventoryCategory", "Value": "WebServer"},
    {"Key": "OwnerDept", "Value": "인프라운영팀"},
    {"Key": "OwnerManager", "Value": "김실무"},
    {"Key": "OwnerResponsible", "Value": "박책임"},
    {"Key": "HandlePI", "Value": "N"},
    {"Key": "InScope", "Value": "Y"},
]

AMI_ID = "ami-12345678"


def build_environment(region: str = REGION, suffix: str = "") -> dict:
    """수집기가 마주칠 상황을 골고루 만든다.

    S3 버킷 이름은 전역에서 유일해야 한다. 여러 리전에 환경을 만들 때는 suffix를 준다.
    """
    ec2 = boto3.client("ec2", region_name=region)
    created: dict = {"region": region}

    vpc_id = ec2.describe_vpcs()["Vpcs"][0]["VpcId"]

    # 전체 개방 인바운드가 있는 보안그룹 — "0.0.0.0/0 → 22/tcp"
    open_sg = ec2.create_security_group(
        GroupName=f"open-ssh{suffix}", Description="demo: 전체 개방", VpcId=vpc_id,
    )["GroupId"]
    ec2.authorize_security_group_ingress(
        GroupId=open_sg,
        IpPermissions=[{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}],
    )
    closed_sg = ec2.create_security_group(
        GroupName=f"internal-only{suffix}", Description="demo: 내부 전용", VpcId=vpc_id,
    )["GroupId"]
    ec2.authorize_security_group_ingress(
        GroupId=closed_sg,
        IpPermissions=[{"IpProtocol": "tcp", "FromPort": 3306, "ToPort": 3306,
                        "IpRanges": [{"CidrIp": "10.0.0.0/8"}]}],
    )
    created["security_groups"] = {"open": open_sg, "closed": closed_sg}

    # 서버 3대 — 태그 완비 / 태그 전무 / 중지
    tagged = ec2.run_instances(
        ImageId=AMI_ID, MinCount=1, MaxCount=1, InstanceType="t3.large",
        SecurityGroupIds=[open_sg],
        TagSpecifications=[{"ResourceType": "instance", "Tags": FULL_TAGS}],
    )["Instances"][0]

    untagged = ec2.run_instances(
        ImageId=AMI_ID, MinCount=1, MaxCount=1, InstanceType="t3.micro",
        SecurityGroupIds=[closed_sg],
    )["Instances"][0]

    stopped = ec2.run_instances(
        ImageId=AMI_ID, MinCount=1, MaxCount=1, InstanceType="t3.small",
        TagSpecifications=[{"ResourceType": "instance",
                            "Tags": [{"Key": "Name", "Value": "batch-01"}]}],
    )["Instances"][0]
    ec2.stop_instances(InstanceIds=[stopped["InstanceId"]])

    created["instances"] = {
        "tagged": tagged["InstanceId"],
        "untagged": untagged["InstanceId"],
        "stopped": stopped["InstanceId"],
    }

    # 미연결 EBS 볼륨 — "관리자가 존재조차 모르는 볼륨"
    az = f"{region}a"
    orphan = ec2.create_volume(AvailabilityZone=az, Size=8, Encrypted=False)
    attached = ec2.create_volume(AvailabilityZone=az, Size=20, Encrypted=True)
    ec2.attach_volume(
        VolumeId=attached["VolumeId"],
        InstanceId=tagged["InstanceId"],
        Device="/dev/sdf",
    )
    created["volumes"] = {"orphan": orphan["VolumeId"], "attached": attached["VolumeId"]}

    # S3 — 암호화 있는 것 하나, 없는 것 하나
    s3 = boto3.client("s3", region_name=region)
    kwargs = {} if region == "us-east-1" else {
        "CreateBucketConfiguration": {"LocationConstraint": region}
    }
    plain = f"isms-demo-plain{suffix}"
    encrypted = f"isms-demo-encrypted{suffix}"
    s3.create_bucket(Bucket=plain, **kwargs)
    s3.create_bucket(Bucket=encrypted, **kwargs)
    s3.put_bucket_encryption(
        Bucket=encrypted,
        ServerSideEncryptionConfiguration={
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
        },
    )
    s3.put_bucket_tagging(
        Bucket=encrypted,
        Tagging={"TagSet": [{"Key": "OwnerDept", "Value": "데이터팀"},
                            {"Key": "HandlePI", "Value": "Y"}]},
    )
    created["buckets"] = {"plain": plain, "encrypted": encrypted}

    # RDS — 백업 있는 것 / 없는 것
    rds = boto3.client("rds", region_name=region)
    prd_db = f"prd-db-01{suffix}"
    dev_db = f"dev-db-01{suffix}"
    rds.create_db_instance(
        DBInstanceIdentifier=prd_db, DBInstanceClass="db.t3.micro",
        Engine="mysql", AllocatedStorage=20, BackupRetentionPeriod=7,
        StorageEncrypted=True, MultiAZ=True,
        Tags=[{"Key": "Name", "Value": prd_db},
              {"Key": "HandlePI", "Value": "Y"}],
    )
    rds.create_db_instance(
        DBInstanceIdentifier=dev_db, DBInstanceClass="db.t3.micro",
        Engine="mysql", AllocatedStorage=20, BackupRetentionPeriod=0,
    )
    created["db_instances"] = {"prd": prd_db, "dev": dev_db}

    # 외부 ALB와 그 뒤의 공인 IP 없는 서버.
    # 공인 IP만 보면 미노출로 보이는 자산이 있어야 exposure_path 조인을 검증할 수 있다.
    subnets = [
        ec2.create_subnet(VpcId=vpc_id, CidrBlock=f"172.31.{n}.0/24",
                          AvailabilityZone=f"{region}{z}")["Subnet"]["SubnetId"]
        for n, z in ((210, "a"), (211, "b"))
    ]
    elb = boto3.client("elbv2", region_name=region)
    alb = elb.create_load_balancer(
        Name=f"prd-alb{suffix}"[:32], Subnets=subnets, SecurityGroups=[open_sg],
        Scheme="internet-facing", Type="application",
        Tags=[{"Key": "Name", "Value": "prd-alb"}],
    )["LoadBalancers"][0]
    tg = elb.create_target_group(
        Name=f"prd-tg{suffix}"[:32], Protocol="HTTP", Port=80, VpcId=vpc_id,
    )["TargetGroups"][0]
    elb.create_listener(
        LoadBalancerArn=alb["LoadBalancerArn"], Protocol="HTTPS", Port=443,
        DefaultActions=[{"Type": "forward", "TargetGroupArn": tg["TargetGroupArn"]}])
    backend = ec2.run_instances(
        ImageId=AMI_ID, MinCount=1, MaxCount=1, InstanceType="t3.large",
        SubnetId=subnets[0], SecurityGroupIds=[closed_sg],
        TagSpecifications=[{"ResourceType": "instance",
                            "Tags": [{"Key": "Name", "Value": "prd-was-02"}]}],
    )["Instances"][0]["InstanceId"]
    elb.register_targets(TargetGroupArn=tg["TargetGroupArn"], Targets=[{"Id": backend}])
    created["load_balancer"] = alb["LoadBalancerArn"]
    created["instances"]["alb_backend"] = backend

    # 컨테이너 리포지토리 — 태그 완비 / 태그 전무
    ecr = boto3.client("ecr", region_name=region)
    ecr.create_repository(
        repositoryName=f"portal/api{suffix}",
        encryptionConfiguration={"encryptionType": "KMS"},
        tags=[{"Key": "Name", "Value": "portal-api"},
              {"Key": "OwnerDept", "Value": "개발팀"}])
    ecr.create_repository(repositoryName=f"legacy/batch{suffix}")
    created["repositories"] = [f"portal/api{suffix}", f"legacy/batch{suffix}"]

    return created


def build_many_instances(count: int, region: str = REGION) -> int:
    """페이지네이션 검증용. 그냥 호출하면 조용히 일부만 받는지 확인한다."""
    ec2 = boto3.client("ec2", region_name=region)
    made = 0
    while made < count:
        batch = min(50, count - made)
        ec2.run_instances(ImageId=AMI_ID, MinCount=batch, MaxCount=batch,
                          InstanceType="t3.nano")
        made += batch
    return made
