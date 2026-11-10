"""AWS Cloud Advisor - an MCP server exposing read-only AWS auditing tools.

Run standalone with the MCP Inspector:
    npx @modelcontextprotocol/inspector python3 aws_advisor_mcp_server.py
"""
import os
from datetime import date, timedelta

import boto3
from botocore.exceptions import ClientError
from mcp.server.fastmcp import FastMCP

REGION = os.getenv("AWS_REGION", "us-east-1")

mcp = FastMCP("aws-cloud-advisor")
ec2 = boto3.client("ec2", region_name=REGION)
rds = boto3.client("rds", region_name=REGION)
iam = boto3.client("iam")  # global service
s3 = boto3.client("s3")  # bucket listing is global
ce = boto3.client("ce", region_name="us-east-1")  # Cost Explorer endpoint lives in us-east-1


@mcp.tool()
def get_cost_summary(days: int = 7) -> dict:
    """Get AWS cost broken down by service for the last N days."""
    end = date.today()
    start = end - timedelta(days=days)
    resp = ce.get_cost_and_usage(
        TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )
    totals: dict[str, float] = {}
    for day in resp["ResultsByTime"]:
        for group in day["Groups"]:
            service = group["Keys"][0]
            cost = float(group["Metrics"]["UnblendedCost"]["Amount"])
            totals[service] = totals.get(service, 0) + cost
    return {service: round(cost, 4) for service, cost in totals.items() if cost > 0}


@mcp.tool()
def find_idle_resources() -> dict:
    """Find unattached Elastic IPs and unattached EBS volumes that are wasting money."""
    idle_eips = [
        addr["PublicIp"]
        for addr in ec2.describe_addresses()["Addresses"]
        if "InstanceId" not in addr and "NetworkInterfaceId" not in addr
    ]
    idle_volumes = [
        {"id": v["VolumeId"], "size_gb": v["Size"]}
        for v in ec2.describe_volumes(
            Filters=[{"Name": "status", "Values": ["available"]}]
        )["Volumes"]
    ]
    return {"unattached_elastic_ips": idle_eips, "unattached_ebs_volumes": idle_volumes}


@mcp.tool()
def check_well_architected_basics() -> dict:
    """Run a handful of basic Well-Architected security and reliability checks."""
    findings: list[str] = []

    # Security: root account MFA
    summary = iam.get_account_summary()["SummaryMap"]
    if summary.get("AccountMFAEnabled", 0) == 0:
        findings.append("SECURITY: Root account does NOT have MFA enabled.")

    # Security: S3 Block Public Access
    for bucket in s3.list_buckets()["Buckets"]:
        name = bucket["Name"]
        try:
            cfg = s3.get_public_access_block(Bucket=name)["PublicAccessBlockConfiguration"]
            if not all(cfg.values()):
                findings.append(
                    f"SECURITY: Bucket '{name}' does not have all Block Public Access settings enabled."
                )
        except ClientError as err:
            code = err.response["Error"]["Code"]
            if code == "NoSuchPublicAccessBlockConfiguration":
                findings.append(
                    f"SECURITY: Bucket '{name}' has NO Block Public Access configuration at all."
                )
            else:
                findings.append(f"CHECK FAILED: Could not inspect bucket '{name}' ({code}).")

    # Reliability: RDS Multi-AZ
    for db in rds.describe_db_instances()["DBInstances"]:
        if not db.get("MultiAZ", False):
            findings.append(
                f"RELIABILITY: DB instance '{db['DBInstanceIdentifier']}' is not Multi-AZ."
            )

    return {"findings": findings, "clean": len(findings) == 0}


if __name__ == "__main__":
    mcp.run()
