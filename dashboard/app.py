"""
SRE Command Center — FastAPI Backend
Provides APIs for incidents, logs, health, approvals, and chaos engineering.
"""

from pathlib import Path

from collections import defaultdict
from time import time

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import boto3
import os
import time
import logging
from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal
import asyncio
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sre-dashboard")

app = FastAPI(title="SRE Command Center")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit: 60 req/min per IP. Disable with RATE_LIMIT_DISABLED=1."""

    def __init__(self, app, limit: int = 60, window: int = 60):
        super().__init__(app)
        self.limit = limit
        self.window = window
        self.store: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request, call_next):
        if os.environ.get("RATE_LIMIT_DISABLED", "").lower() in ("1", "true", "yes"):
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        now = time()
        self.store[ip] = [t for t in self.store[ip] if now - t < self.window]
        if len(self.store[ip]) >= self.limit:
            from starlette.responses import JSONResponse

            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        self.store[ip].append(now)
        return await call_next(request)


app.add_middleware(RateLimitMiddleware, limit=60, window=60)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── AWS Clients ──────────────────────────────────────────────
REGION = os.environ.get("AWS_REGION", "ap-south-1")
dynamodb = boto3.resource("dynamodb", region_name=REGION)
logs_client = boto3.client("logs", region_name=REGION)
cloudwatch = boto3.client("cloudwatch", region_name=REGION)
ec2_client = boto3.client("ec2", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)
elbv2 = boto3.client("elbv2", region_name=REGION)
autoscaling = boto3.client("autoscaling", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)

TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "sre-incidents")
LOG_GROUP = "/aws/lambda/sre-brain-handler"
ASG_NAME = "sre-demo-asg"

# ── Static Files ─────────────────────────────────────────────
_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/")
async def root():
    return FileResponse(str(_STATIC_DIR / "index.html"))


@app.get("/health")
async def health_liveness():
    """Simple liveness probe for load balancers and container orchestration."""
    return {"status": "ok", "service": "sre-dashboard"}


# ── WebSocket for real-time updates ──────────────────────────
active_connections: list[WebSocket] = []


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)


async def broadcast(data: dict):
    for ws in active_connections:
        try:
            await ws.send_json(data)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
# API ENDPOINTS
# ══════════════════════════════════════════════════════════════


# ── Incidents ────────────────────────────────────────────────
@app.get("/api/incidents")
async def get_incidents(status: Optional[str] = None):
    """List all incidents from DynamoDB, optionally filtered by status."""
    try:
        table = dynamodb.Table(TABLE_NAME)
        if status:
            from boto3.dynamodb.conditions import Attr

            response = table.scan(FilterExpression=Attr("status").eq(status))
        else:
            response = table.scan()

        items = response.get("Items", [])
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return {"incidents": items}
    except Exception as e:
        logger.error(f"Error fetching incidents: {e}")
        return {"incidents": [], "error": str(e)}


@app.get("/api/incidents/stats")
async def get_incident_stats():
    """Aggregate incident statistics for the Metrics dashboard."""
    try:
        table = dynamodb.Table(TABLE_NAME)
        response = table.scan()
        items = response.get("Items", [])

        # Status counts
        status_counts = {}
        for item in items:
            s = item.get("status", "unknown")
            status_counts[s] = status_counts.get(s, 0) + 1

        # Daily counts (last 7 days)
        now = datetime.now(timezone.utc)
        daily = {}
        for i in range(7):
            day = (now - __import__("datetime").timedelta(days=i)).strftime("%Y-%m-%d")
            daily[day] = 0
        for item in items:
            created = item.get("created_at", "")
            if created:
                day = created[:10]
                if day in daily:
                    daily[day] += 1

        # MTTR calculation (avg time from created_at to updated_at for completed/failed)
        mttr_values = []
        for item in items:
            if (
                item.get("status") in ("completed", "failed")
                and item.get("created_at")
                and item.get("updated_at")
            ):
                try:
                    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
                    updated = datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))
                    diff = (updated - created).total_seconds()
                    if diff > 0:
                        mttr_values.append(diff)
                except Exception:
                    pass
        avg_mttr = sum(mttr_values) / len(mttr_values) if mttr_values else 0

        # Success rate
        resolved = sum(1 for i in items if i.get("status") in ("completed", "failed", "rejected"))
        completed = sum(1 for i in items if i.get("status") == "completed")
        success_rate = (completed / resolved * 100) if resolved > 0 else 0

        # Convert Decimal to float for JSON serialization
        def to_serializable(val):
            if isinstance(val, Decimal):
                return float(val)
            return val

        return {
            "total": len(items),
            "status_counts": {k: to_serializable(v) for k, v in status_counts.items()},
            "daily_counts": {k: to_serializable(v) for k, v in sorted(daily.items())},
            "avg_mttr_seconds": round(avg_mttr, 1),
            "success_rate": round(success_rate, 1),
            "total_resolved": resolved,
        }
    except Exception as e:
        logger.error(f"Error computing stats: {e}")
        return {"error": str(e)}


@app.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: str):
    """Get a single incident by ID."""
    try:
        table = dynamodb.Table(TABLE_NAME)
        resp = table.get_item(Key={"incident_id": incident_id})
        if "Item" not in resp:
            raise HTTPException(404, "Incident not found")
        return resp["Item"]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Approval Workflow ────────────────────────────────────────
# ── Pydantic Models ──────────────────────────────────────────
class ApproveRequest(BaseModel):
    custom_command: Optional[str] = None


def _append_timeline(table, incident_id: str, event: str, detail: str = ""):
    """Append a timeline entry to an incident's timeline array."""
    now = datetime.now(timezone.utc).isoformat()
    entry = {"event": event, "timestamp": now, "detail": detail}
    try:
        table.update_item(
            Key={"incident_id": incident_id},
            UpdateExpression="SET #tl = list_append(if_not_exists(#tl, :empty), :entry)",
            ExpressionAttributeNames={"#tl": "timeline"},
            ExpressionAttributeValues={":entry": [entry], ":empty": []},
        )
    except Exception as e:
        logger.warning(f"Failed to append timeline for {incident_id}: {e}")


@app.post("/api/approve/{incident_id}")
async def approve_incident(incident_id: str, body: ApproveRequest = ApproveRequest()):
    """Approve a pending remediation and execute the command."""
    table = dynamodb.Table(TABLE_NAME)
    resp = table.get_item(Key={"incident_id": incident_id})

    if "Item" not in resp:
        raise HTTPException(404, "Incident not found")

    incident = resp["Item"]
    if incident["status"] != "pending_approval":
        raise HTTPException(400, f"Cannot approve: status is '{incident['status']}'")

    now = datetime.now(timezone.utc).isoformat()

    # Determine which command to execute
    command = body.custom_command if body.custom_command else incident["ai_suggestion"]
    used_custom = bool(body.custom_command)

    # Mark as executing immediately
    update_expr = "SET #s = :s, updated_at = :u"
    expr_vals = {":s": "executing", ":u": now}
    if used_custom:
        update_expr += ", custom_command = :cc"
        expr_vals[":cc"] = command

    table.update_item(
        Key={"incident_id": incident_id},
        UpdateExpression=update_expr,
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues=expr_vals,
    )

    # Timeline entry
    detail = "Custom command used" if used_custom else "AI-suggested command approved"
    _append_timeline(table, incident_id, "approved", detail)

    instance_id = incident["instance_id"]

    # Run SSM command execution in background (non-blocking)
    asyncio.create_task(_execute_remediation(incident_id, instance_id, command, table))

    return {"status": "executing", "message": "Command dispatched. Watch for updates."}


async def _execute_remediation(incident_id, instance_id, command, table):
    """Background task to execute and poll SSM command."""
    try:
        cmd_resp = ssm.send_command(
            InstanceIds=[instance_id],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": [command]},
        )
        command_id = cmd_resp["Command"]["CommandId"]

        # Poll for completion (up to 2 min)
        for _ in range(60):
            await asyncio.sleep(2)
            try:
                inv = ssm.get_command_invocation(CommandId=command_id, InstanceId=instance_id)
                if inv["Status"] in ("Success", "Failed", "Cancelled", "TimedOut"):
                    final_status = "completed" if inv["Status"] == "Success" else "failed"
                    output = inv.get("StandardOutputContent", "") or inv.get(
                        "StandardErrorContent", "No output"
                    )
                    table.update_item(
                        Key={"incident_id": incident_id},
                        UpdateExpression="SET #s = :s, remediation_output = :o, updated_at = :u",
                        ExpressionAttributeNames={"#s": "status"},
                        ExpressionAttributeValues={
                            ":s": final_status,
                            ":o": output,
                            ":u": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    _append_timeline(table, incident_id, final_status, output[:200])
                    await broadcast(
                        {
                            "type": "incident_update",
                            "incident_id": incident_id,
                            "status": final_status,
                            "output": output[:500],
                        }
                    )
                    return
            except Exception:
                pass

        # Timed out polling
        table.update_item(
            Key={"incident_id": incident_id},
            UpdateExpression="SET #s = :s, updated_at = :u",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": "timeout",
                ":u": datetime.now(timezone.utc).isoformat(),
            },
        )
        _append_timeline(table, incident_id, "timeout", "SSM command timed out after 2 minutes")
        await broadcast(
            {
                "type": "incident_update",
                "incident_id": incident_id,
                "status": "timeout",
            }
        )

    except Exception as e:
        logger.error(f"Remediation error for {incident_id}: {e}")
        table.update_item(
            Key={"incident_id": incident_id},
            UpdateExpression="SET #s = :s, remediation_output = :o, updated_at = :u",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": "failed",
                ":o": str(e),
                ":u": datetime.now(timezone.utc).isoformat(),
            },
        )
        _append_timeline(table, incident_id, "failed", str(e)[:200])
        await broadcast(
            {
                "type": "incident_update",
                "incident_id": incident_id,
                "status": "failed",
                "output": str(e),
            }
        )


@app.post("/api/reject/{incident_id}")
async def reject_incident(incident_id: str):
    """Reject a pending remediation."""
    table = dynamodb.Table(TABLE_NAME)
    table.update_item(
        Key={"incident_id": incident_id},
        UpdateExpression="SET #s = :s, updated_at = :u",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "rejected",
            ":u": datetime.now(timezone.utc).isoformat(),
        },
    )
    _append_timeline(table, incident_id, "rejected", "Operator rejected remediation")
    await broadcast(
        {
            "type": "incident_update",
            "incident_id": incident_id,
            "status": "rejected",
        }
    )
    return {"status": "rejected"}


# ── System Health ────────────────────────────────────────────
@app.get("/api/health")
async def get_health():
    """Aggregate system health: instances, alarms, target groups."""
    health = {"instances": [], "alarms": [], "asg": None}

    # ASG Instances
    try:
        asg_resp = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[ASG_NAME])
        if asg_resp["AutoScalingGroups"]:
            asg = asg_resp["AutoScalingGroups"][0]
            health["asg"] = {
                "name": asg["AutoScalingGroupName"],
                "desired": asg["DesiredCapacity"],
                "min": asg["MinSize"],
                "max": asg["MaxSize"],
                "instances_count": len(asg["Instances"]),
            }
            for inst in asg["Instances"]:
                health["instances"].append(
                    {
                        "id": inst["InstanceId"],
                        "state": inst["LifecycleState"],
                        "health": inst["HealthStatus"],
                        "az": inst["AvailabilityZone"],
                    }
                )
    except Exception as e:
        logger.error(f"ASG error: {e}")

    # CloudWatch Alarms
    try:
        alarm_resp = cloudwatch.describe_alarms()
        for alarm in alarm_resp.get("MetricAlarms", []):
            health["alarms"].append(
                {
                    "name": alarm["AlarmName"],
                    "state": alarm["StateValue"],
                    "description": alarm.get("AlarmDescription", ""),
                    "metric": alarm.get("MetricName", ""),
                    "threshold": str(alarm.get("Threshold", "")),
                    "updated": alarm.get("StateUpdatedTimestamp", datetime.now()).isoformat(),
                }
            )
    except Exception as e:
        logger.error(f"Alarm error: {e}")

    return health


# ── Live Logs ────────────────────────────────────────────────
@app.get("/api/logs")
async def get_logs(minutes: int = 60, limit: int = 200):
    """Fetch Lambda execution logs from CloudWatch."""
    try:
        end_time = int(time.time() * 1000)
        start_time = end_time - (minutes * 60 * 1000)

        response = logs_client.filter_log_events(
            logGroupName=LOG_GROUP,
            startTime=start_time,
            endTime=end_time,
            limit=limit,
            interleaved=True,
        )

        events = []
        for ev in response.get("events", []):
            msg = ev["message"].strip()
            # Classify log level
            level = "info"
            if "[ERROR]" in msg:
                level = "error"
            elif "[WARNING]" in msg or "[WARN]" in msg:
                level = "warning"
            elif "START " in msg or "END " in msg or "REPORT " in msg:
                level = "system"
            elif "INIT_START" in msg:
                level = "system"

            events.append(
                {
                    "timestamp": ev["timestamp"],
                    "message": msg,
                    "level": level,
                    "formatted_time": datetime.fromtimestamp(
                        ev["timestamp"] / 1000, tz=timezone.utc
                    ).strftime("%Y-%m-%d %H:%M:%S UTC"),
                }
            )

        return {"logs": events}
    except Exception as e:
        return {"logs": [], "error": str(e)}


# ── S3 Archives ──────────────────────────────────────────────
@app.get("/api/archives")
async def get_archives():
    """List archived log files in the S3 bucket."""
    try:
        buckets = s3.list_buckets()
        log_bucket = None
        for b in buckets.get("Buckets", []):
            if b["Name"].startswith("sre-incident-logs-archive"):
                log_bucket = b["Name"]
                break

        if not log_bucket:
            return {"archives": [], "bucket": None}

        resp = s3.list_objects_v2(Bucket=log_bucket)
        archives = []
        for obj in resp.get("Contents", []):
            archives.append(
                {
                    "key": obj["Key"],
                    "size_mb": round(obj["Size"] / (1024 * 1024), 2),
                    "last_modified": obj["LastModified"].isoformat(),
                }
            )

        return {"archives": archives, "bucket": log_bucket}
    except Exception as e:
        return {"archives": [], "error": str(e)}


# ── Chaos Engineering ────────────────────────────────────────
@app.post("/api/chaos/{mode}")
async def trigger_chaos(mode: str):
    """Trigger a chaos scenario on an in-service instance."""
    valid_modes = ["disk-fill", "nginx-crash", "oom"]
    if mode not in valid_modes:
        raise HTTPException(400, f"Invalid mode. Choose from: {valid_modes}")

    try:
        asg_resp = autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[ASG_NAME])
        instances = asg_resp["AutoScalingGroups"][0]["Instances"]
        in_service = [i for i in instances if i["LifecycleState"] == "InService"]

        if not in_service:
            raise HTTPException(400, "No in-service instances")

        instance_id = in_service[0]["InstanceId"]
        cmd = f"sudo python3 /home/ubuntu/chaos_master.py --mode {mode}"

        resp = ssm.send_command(
            InstanceIds=[instance_id],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": [cmd]},
        )

        return {
            "status": "triggered",
            "instance_id": instance_id,
            "mode": mode,
            "command_id": resp["Command"]["CommandId"],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Post-Incident Report ─────────────────────────────────────
@app.get("/api/incidents/{incident_id}/report")
async def get_incident_report(incident_id: str):
    """Generate a post-incident report in markdown format."""
    try:
        table = dynamodb.Table(TABLE_NAME)
        resp = table.get_item(Key={"incident_id": incident_id})

        if "Item" not in resp:
            raise HTTPException(404, "Incident not found")

        inc = resp["Item"]
        created = inc.get("created_at", "Unknown")
        updated = inc.get("updated_at", "Unknown")
        status = inc.get("status", "unknown")

        # Calculate duration
        duration_str = "N/A"
        if created != "Unknown" and updated != "Unknown":
            try:
                t1 = datetime.fromisoformat(created.replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                diff = (t2 - t1).total_seconds()
                mins, secs = divmod(int(diff), 60)
                duration_str = f"{mins}m {secs}s"
            except Exception:
                pass

        # Build timeline section
        timeline_md = ""
        timeline = inc.get("timeline", [])
        if timeline:
            timeline_md = "\n## Timeline\n\n| Time | Event | Detail |\n|------|-------|--------|\n"
            for entry in timeline:
                timeline_md += f"| {entry.get('timestamp', 'N/A')} | {entry.get('event', 'N/A')} | {entry.get('detail', '')[:100]} |\n"

        # Build markdown
        md = f"""# Post-Incident Report

## Incident Summary

| Field | Value |
|-------|-------|
| **Incident ID** | `{incident_id}` |
| **Alarm** | {inc.get("alarm_name", "N/A")} |
| **Instance** | `{inc.get("instance_id", "N/A")}` |
| **Status** | {status.replace("_", " ").title()} |
| **Created** | {created} |
| **Resolved** | {updated} |
| **Duration** | {duration_str} |

## Alarm Details

{inc.get("alarm_description", "No description available.")}

## Root Cause Analysis

**AI Analysis:** {inc.get("ai_reasoning", "No AI analysis available.")}

## Remediation

**Suggested Command:**
```bash
{inc.get("ai_suggestion", "N/A")}
```

{f"**Custom Command Used:**{chr(10)}```bash{chr(10)}{inc.get('custom_command')}{chr(10)}```" if inc.get("custom_command") else ""}

**Remediation Output:**
```
{inc.get("remediation_output", "No output recorded.")}
```
{timeline_md}
## Diagnostics

```
{inc.get("diagnostics", "No diagnostics available.")}
```

---
*Report auto-generated by SRE Command Center*
"""
        return {
            "incident_id": incident_id,
            "markdown": md,
            "status": status,
            "created_at": created,
            "updated_at": updated,
            "duration": duration_str,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating report for {incident_id}: {e}")
        raise HTTPException(500, str(e))


# ── Dashboard Config ─────────────────────────────────────────
@app.get("/api/config")
async def get_config():
    """Return dashboard configuration."""
    return {
        "region": REGION,
        "asg_name": ASG_NAME,
        "log_group": LOG_GROUP,
        "table_name": TABLE_NAME,
    }


# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=3000, log_level="info")
