from __future__ import annotations

import json
from typing import Any

import boto3
import time
import os
import logging

# import google.generativeai as genai # Uncomment if using Gemini SDK
import urllib.request

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

ssm = boto3.client("ssm")
asg_client = boto3.client("autoscaling")
s3_client = boto3.client("s3")

elbv2_client = boto3.client("elbv2")
dynamodb = boto3.resource("dynamodb")

# ── Approval Mode ────────────────────────────────────────────
# When True, Lambda writes incidents to DynamoDB for dashboard approval.
# When False, Lambda auto-executes remediation (original behavior).
APPROVAL_MODE = os.environ.get("APPROVAL_MODE", "true").lower() == "true"
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "sre-incidents")


def get_unhealthy_targets(tg_suffix: str, region: str, account_id: str) -> list[str]:
    """
    Find unhealthy instances in the given Target Group.
    tg_suffix looks like: targetgroup/sre-demo-tg/42f85d5ede20f6d3
    """
    try:
        tg_arn = f"arn:aws:elasticloadbalancing:{region}:{account_id}:{tg_suffix}"
        logger.info(f"Checking health for Target Group: {tg_arn}")

        response = elbv2_client.describe_target_health(TargetGroupArn=tg_arn)
        unhealthy_targets = []
        for description in response.get("TargetHealthDescriptions", []):
            if description["TargetHealth"]["State"] != "healthy":
                target_id = description["Target"]["Id"]
                if target_id.startswith("i-"):
                    unhealthy_targets.append(target_id)

        logger.info(f"Found unhealthy targets: {unhealthy_targets}")
        return unhealthy_targets
    except Exception as e:
        logger.error(f"Error fetching target health: {e}")
        return []


def get_target_instances(alarm_data: dict[str, Any]) -> list[str]:
    """
    Extract target InstanceIds from CloudWatch Alarm data.
    Handles InstanceId, AutoScalingGroupName, and TargetGroup dimensions.
    """
    trigger = alarm_data.get("Trigger", {})
    # Convert list of dicts to a single dict for easy lookup
    dimensions = {d["name"]: d["value"] for d in trigger.get("Dimensions", [])}

    logger.info(f"Resolving targets for dimensions: {dimensions}")

    # CASE 1: Alarm from Auto Scaling Group
    asg_name = dimensions.get("AutoScalingGroupName")
    if asg_name:
        logger.info(f"Alarm triggered for ASG: {asg_name}")
        try:
            response = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
            if not response["AutoScalingGroups"]:
                return []
            instances = response["AutoScalingGroups"][0]["Instances"]
            return [i["InstanceId"] for i in instances if i["LifecycleState"] == "InService"]
        except Exception as e:
            logger.error(f"Error fetching ASG instances: {e}")
            return []

    # CASE 2: Alarm from Load Balancer (Target Group)
    tg_suffix = dimensions.get("TargetGroup")
    if tg_suffix:
        logger.info(f"Alarm triggered for Target Group: {tg_suffix}")
        region = alarm_data.get("Region", os.environ.get("AWS_REGION", "ap-south-1"))

        # Try to find Account ID
        account_id = alarm_data.get("AWSAccountId")
        if not account_id and "AlarmArn" in alarm_data:
            try:
                account_id = alarm_data["AlarmArn"].split(":")[4]
            except IndexError:
                pass

        if not account_id:
            logger.error("Could not determine AWS Account ID for Target Group lookup.")
            return []

        # Use the function defined earlier
        return get_unhealthy_targets(tg_suffix, region, account_id)

    # CASE 3: Alarm from specific Instance
    instance_id = dimensions.get("InstanceId")
    if instance_id:
        return [instance_id]

    logger.warning("No valid dimension found for target resolution.")
    return []


def get_log_bucket() -> str:
    """Find the log archive bucket dynamically."""
    try:
        response = s3_client.list_buckets()
        for bucket in response["Buckets"]:
            if bucket["Name"].startswith("sre-incident-logs-archive"):
                return bucket["Name"]
    except Exception as e:
        logger.error(f"Error listing buckets: {e}")
    return "sre-incident-logs-archive"  # Fallback


def send_ssm_command(instance_id: str, commands: list[str]) -> str | None:
    """Send a shell command to an EC2 instance via SSM."""
    logger.info(f"Sending SSM command to {instance_id}: {commands}")
    try:
        response = ssm.send_command(
            InstanceIds=[instance_id],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": commands},
        )
        return response["Command"]["CommandId"]
    except Exception as e:
        logger.error(f"Failed to send command to {instance_id}: {e}")
        return None


def wait_for_command(command_id, instance_id):
    """Poll for SSM command completion."""
    if not command_id:
        return None

    retries = 60  # 2 minutes polling
    while retries > 0:
        try:
            response = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
            status = response["Status"]
            if status in ["Success", "Failed", "Cancelled", "TimedOut"]:
                return response
        except Exception as e:
            if "InvocationDoesNotExist" in str(e):
                pass
            else:
                logger.error(f"Error polling command {command_id}: {e}")

        time.sleep(2)
        retries -= 1
    return None


def ask_genai(context, issue_type):
    """
    Call Google Gemini via REST API (Standard Library).
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key.startswith("dummy"):
        logger.info("No valid API Key found (or dummy). Using fallback.")
        return fallback_remediation(issue_type)

    bucket_name = get_log_bucket()
    system_instruction = f"You are a Linux Sysadmin. The S3 bucket for log archival is '{bucket_name}'. Return ONLY a JSON object with keys 'reasoning' (brief explanation of why this command fixes the issue) and 'command' (the bash command itself). No markdown, no explanations outside JSON."
    prompt = f"{system_instruction}\n\nContext:\n{context}\n\nIssue: {issue_type}\n\nProvide the specific remediation JSON."

    model_name = os.environ.get("GEMINI_MODEL", "gemini-1.5-pro")
    base_url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    )
    headers = {"Content-Type": "application/json"}

    if api_key.startswith("AIza"):
        url = f"{base_url}?key={api_key}"
    else:
        url = base_url
        headers["Authorization"] = f"Bearer {api_key}"

    data = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        req = urllib.request.Request(
            url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST"
        )

        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            generated_text = result["candidates"][0]["content"]["parts"][0]["text"]
            cleaned_text = generated_text.strip().replace("```json", "").replace("```", "").strip()
            return json.loads(cleaned_text)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else "No body"
        logger.error(f"Gemini API HTTP Error {e.code}: {error_body}")
        if e.code == 401:
            logger.error("Auth failed. Verify your GEMINI_API_KEY.")
    except Exception as e:
        logger.error(f"Gemini API Call Failed: {e}")

    return fallback_remediation(issue_type)


def fallback_remediation(issue_type: str) -> dict[str, str]:
    """Deterministic fallback if AI fails."""
    logger.info(f"Using fallback logic for {issue_type}")
    if "Disk" in issue_type:
        bucket = get_log_bucket()
        cmd = f"export PATH=$PATH:/usr/local/bin; aws s3 cp /var/log/garbage.log s3://{bucket}/garbage.log-$(date +%s) && > /var/log/garbage.log"
        return {
            "reasoning": "Disk usage critical. Archiving garbage.log to S3 and clearing file to free space.",
            "command": cmd,
        }
    elif "Nginx" in issue_type:
        return {
            "reasoning": "Nginx service is down. Restarting service to restore availability.",
            "command": "systemctl restart nginx",
        }
    elif "Memory" in issue_type:
        return {
            "reasoning": "Memory exhaustion detected. Terminating stress-ng process.",
            "command": "pkill -f 'stress-ng' || pkill -f 'python3'",
        }
    return {
        "reasoning": "Unknown issue type. No specific remediation.",
        "command": "echo 'No remediation found'",
    }


# ══════════════════════════════════════════════════════════════
# DynamoDB Incident Tracking
# ══════════════════════════════════════════════════════════════


def write_incident(
    incident_id,
    alarm_name,
    alarm_desc,
    instance_id,
    diagnostics,
    ai_suggestion,
    ai_reasoning,
    status,
):
    """Write an incident record to DynamoDB."""
    try:
        from datetime import datetime, timezone

        table = dynamodb.Table(DYNAMODB_TABLE)
        now = datetime.now(timezone.utc).isoformat()

        timeline = [
            {
                "event": "created",
                "timestamp": now,
                "detail": f"Incident created from alarm: {alarm_name}",
            },
            {
                "event": "diagnostics",
                "timestamp": now,
                "detail": "Diagnostics executed successfully",
            },
            {"event": "ai_analysis", "timestamp": now, "detail": "AI generated remediation plan"},
        ]

        item = {
            "incident_id": incident_id,
            "alarm_name": alarm_name,
            "alarm_description": alarm_desc,
            "instance_id": instance_id,
            "diagnostics": diagnostics or "",
            "ai_suggestion": ai_suggestion or "",
            "ai_reasoning": ai_reasoning or "",
            "status": status,
            "created_at": now,
            "updated_at": now,
            "remediation_output": "",
            "timeline": timeline,
        }
        table.put_item(Item=item)
        logger.info(f"Incident {incident_id} written to DynamoDB with status '{status}'")
    except Exception as e:
        logger.error(f"Failed to write incident to DynamoDB: {e}")


def update_incident_status(incident_id, status, output=""):
    """Update an incident's status in DynamoDB."""
    try:
        from datetime import datetime, timezone

        table = dynamodb.Table(DYNAMODB_TABLE)
        table.update_item(
            Key={"incident_id": incident_id},
            UpdateExpression="SET #s = :s, remediation_output = :o, updated_at = :u",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": status,
                ":o": output,
                ":u": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.info(f"Incident {incident_id} updated to '{status}'")
    except Exception as e:
        logger.error(f"Failed to update incident in DynamoDB: {e}")


# ══════════════════════════════════════════════════════════════
# Main Lambda Handler
# ══════════════════════════════════════════════════════════════


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    logger.info("Received event: " + json.dumps(event))

    try:
        sns_message = event["Records"][0]["Sns"]["Message"]
        alarm_data = json.loads(sns_message)
        alarm_name = alarm_data.get("AlarmName", "Unknown")
        alarm_desc = alarm_data.get("AlarmDescription", "")

        # Only process ALARM state (not OK transitions)
        new_state = alarm_data.get("NewStateValue", "ALARM")
        if new_state != "ALARM":
            logger.info(f"Ignoring non-ALARM state: {new_state}")
            return {"statusCode": 200, "body": "Ignored: not in ALARM state"}

        target_instances = get_target_instances(alarm_data)

        if not target_instances:
            logger.error("No target instances found for this alarm.")
            return {"statusCode": 400, "body": json.dumps("No targets found")}

        logger.info(f"Handling incident '{alarm_name}' for targets: {target_instances}")

        results = []

        for instance_id in target_instances:
            logger.info(f"Starting workflow for {instance_id}")

            # Generate unique incident ID
            incident_id = f"{int(time.time())}_{alarm_name}_{instance_id}"

            # ── Classify Alarm ───────────────────────────────
            diag_commands = []
            issue_type = ""

            if "Disk" in alarm_name:
                diag_commands = ["df -h /", "ls -lRh /var/log/ | head -n 20"]
                issue_type = "Disk Critical"
            elif "Nginx" in alarm_name or "Service" in alarm_name:
                diag_commands = ["systemctl status nginx", "journalctl -u nginx -n 20"]
                issue_type = "Nginx Down"
            elif "Memory" in alarm_name:
                diag_commands = ["free -m", "ps aux --sort=-%mem | head -n 10"]
                issue_type = "Memory Exhaustion"
            else:
                logger.info(f"Unknown alarm type: {alarm_name}")
                continue

            # ── Diagnostic Phase ─────────────────────────────
            cmd_id = send_ssm_command(instance_id, diag_commands)
            if not cmd_id:
                continue

            time.sleep(1)
            cmd_result = wait_for_command(cmd_id, instance_id)

            diagnostics = (
                cmd_result.get("StandardOutputContent", "No Output")
                if cmd_result
                else "Diagnostic Timeout"
            )
            logger.info(f"Diagnostic Output for {instance_id}: {diagnostics}")

            # ── AI Analysis Phase ────────────────────────────
            ai_result = ask_genai(diagnostics, issue_type)
            remediation_cmd = ai_result.get("command", "echo 'Error'")
            ai_reasoning = ai_result.get("reasoning", "No reasoning provided.")

            logger.info(f"AI Suggested Remediation: {remediation_cmd}")

            # ── Decide: Approval or Auto-Execute ─────────────
            if APPROVAL_MODE:
                # Write to DynamoDB for dashboard approval
                logger.info("APPROVAL MODE: Writing incident to DynamoDB for operator review")
                write_incident(
                    incident_id=incident_id,
                    alarm_name=alarm_name,
                    alarm_desc=alarm_desc,
                    instance_id=instance_id,
                    diagnostics=diagnostics,
                    ai_suggestion=remediation_cmd,
                    ai_reasoning=ai_reasoning,
                    status="pending_approval",
                )
                results.append(
                    {
                        "instance": instance_id,
                        "status": "pending_approval",
                        "incident_id": incident_id,
                    }
                )
            else:
                # Auto-execute (original behavior)
                logger.info("AUTO MODE: Executing remediation immediately")
                write_incident(
                    incident_id=incident_id,
                    alarm_name=alarm_name,
                    alarm_desc=alarm_desc,
                    instance_id=instance_id,
                    diagnostics=diagnostics,
                    ai_suggestion=remediation_cmd,
                    ai_reasoning=ai_reasoning,
                    status="executing",
                )

                fix_id = send_ssm_command(instance_id, [remediation_cmd])
                fix_result = wait_for_command(fix_id, instance_id)

                if fix_result:
                    status = fix_result.get("Status", "Unknown")
                    fix_stdout = fix_result.get("StandardOutputContent", "")
                    fix_stderr = fix_result.get("StandardErrorContent", "")
                    final_status = "completed" if status == "Success" else "failed"
                    output = fix_stdout or fix_stderr or "No output"

                    logger.info(f"Remediation for {instance_id}: {status}")
                    update_incident_status(incident_id, final_status, output)
                else:
                    logger.error(f"Remediation timed out for {instance_id}")
                    update_incident_status(incident_id, "timeout", "Command timed out")

                results.append(
                    {"instance": instance_id, "status": final_status if fix_result else "timeout"}
                )

        return {"statusCode": 200, "body": json.dumps(results)}

    except Exception as e:
        logger.error(f"Error processing event: {str(e)}")
        raise e
