"""Tests for dashboard FastAPI endpoints with mocked AWS."""
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dashboard"))

from app import app

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_dynamodb_table():
    """Mock DynamoDB table."""
    table = MagicMock()
    table.scan.return_value = {
        "Items": [
            {
                "incident_id": "inc-1",
                "status": "pending_approval",
                "created_at": "2024-01-15T10:00:00Z",
                "alarm_name": "Disk-Critical-ASG",
            }
        ]
    }
    table.get_item.return_value = {
        "Item": {
            "incident_id": "inc-1",
            "status": "pending_approval",
            "instance_id": "i-123",
            "ai_suggestion": "echo test",
            "created_at": "2024-01-15T10:00:00Z",
        }
    }
    table.update_item.return_value = {}
    return table


@pytest.fixture
def mock_dynamodb_resource(mock_dynamodb_table):
    """Patch app.dynamodb so Table() returns our mock table."""
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_dynamodb_table
    with patch("app.dynamodb", mock_resource):
        yield mock_dynamodb_table


@pytest.fixture
async def client(mock_dynamodb_resource):
    """Async test client."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


async def test_root_returns_html(client):
    """Root serves index.html."""
    resp = await client.get("/")
    assert resp.status_code == 200
    assert "html" in resp.headers.get("content-type", "")


async def test_health_liveness(client):
    """Simple /health returns 200 OK for load balancer probes."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"
    assert data.get("service") == "sre-dashboard"


async def test_api_incidents_list(client, mock_dynamodb_resource):
    """GET /api/incidents returns incidents from DynamoDB."""
    resp = await client.get("/api/incidents")
    assert resp.status_code == 200
    data = resp.json()
    assert "incidents" in data
    mock_dynamodb_resource.scan.assert_called_once()


async def test_api_incidents_filtered(client, mock_dynamodb_resource):
    """GET /api/incidents?status=pending_approval filters by status."""
    resp = await client.get("/api/incidents?status=pending_approval")
    assert resp.status_code == 200
    mock_dynamodb_resource.scan.assert_called_once()


async def test_api_incident_get(client, mock_dynamodb_resource):
    """GET /api/incidents/{id} returns single incident."""
    resp = await client.get("/api/incidents/inc-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["incident_id"] == "inc-1"
    assert data["status"] == "pending_approval"


async def test_api_incident_get_404(client, mock_dynamodb_resource):
    """GET /api/incidents/{id} returns 404 when not found."""
    mock_dynamodb_resource.get_item.return_value = {}
    resp = await client.get("/api/incidents/nonexistent")
    assert resp.status_code == 404


@pytest.fixture
def mock_autoscaling_ssm():
    """Patch autoscaling and ssm for chaos endpoint."""
    mock_asg = MagicMock()
    mock_asg.describe_auto_scaling_groups.return_value = {
        "AutoScalingGroups": [{
            "Instances": [{"InstanceId": "i-chaos1", "LifecycleState": "InService"}]
        }]
    }
    mock_ssm = MagicMock()
    mock_ssm.send_command.return_value = {"Command": {"CommandId": "cmd-chaos-1"}}
    with patch("app.autoscaling", mock_asg), patch("app.ssm", mock_ssm):
        yield {"autoscaling": mock_asg, "ssm": mock_ssm}


async def test_api_approve_returns_executing(
    client, mock_dynamodb_resource, mock_autoscaling_ssm
):
    """POST /api/approve/{id} returns 200 and executing status."""
    mock_dynamodb_resource.get_item.return_value = {
        "Item": {
            "incident_id": "inc-1",
            "status": "pending_approval",
            "instance_id": "i-123",
            "ai_suggestion": "echo fixed",
        }
    }
    resp = await client.post("/api/approve/inc-1", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "executing"


async def test_api_approve_404(client, mock_dynamodb_resource):
    """POST /api/approve/{id} returns 404 when incident not found."""
    mock_dynamodb_resource.get_item.return_value = {}
    resp = await client.post("/api/approve/nonexistent", json={})
    assert resp.status_code == 404


async def test_api_reject(client, mock_dynamodb_resource):
    """POST /api/reject/{id} returns 200 and rejected status."""
    resp = await client.post("/api/reject/inc-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "rejected"
    mock_dynamodb_resource.update_item.assert_called()


async def test_api_chaos_triggered(client, mock_dynamodb_resource, mock_autoscaling_ssm):
    """POST /api/chaos/{mode} returns 200 with command_id when valid mode."""
    resp = await client.post("/api/chaos/disk-fill")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "triggered"
    assert data.get("mode") == "disk-fill"
    assert "command_id" in data


async def test_api_chaos_invalid_mode(client, mock_dynamodb_resource):
    """POST /api/chaos/{mode} returns 400 for invalid mode."""
    resp = await client.post("/api/chaos/invalid-mode")
    assert resp.status_code == 400


@pytest.fixture
def mock_autoscaling_cloudwatch():
    """Patch autoscaling and cloudwatch for /api/health."""
    mock_asg = MagicMock()
    mock_asg.describe_auto_scaling_groups.return_value = {
        "AutoScalingGroups": [{
            "AutoScalingGroupName": "sre-demo-asg",
            "DesiredCapacity": 1,
            "MinSize": 0,
            "MaxSize": 3,
            "Instances": [
                {
                    "InstanceId": "i-health1",
                    "LifecycleState": "InService",
                    "HealthStatus": "Healthy",
                    "AvailabilityZone": "ap-south-1a",
                }
            ],
        }]
    }
    mock_cw = MagicMock()
    mock_cw.describe_alarms.return_value = {
        "MetricAlarms": [
            {
                "AlarmName": "Disk-Critical",
                "StateValue": "OK",
                "AlarmDescription": "Disk usage",
                "MetricName": "disk_used_percent",
                "Threshold": 85,
                "StateUpdatedTimestamp": datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            }
        ]
    }
    with patch("app.autoscaling", mock_asg), patch("app.cloudwatch", mock_cw):
        yield


async def test_api_health_aggregate(client, mock_autoscaling_cloudwatch):
    """GET /api/health returns instances, alarms, asg."""
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "instances" in data
    assert "alarms" in data
    assert "asg" in data
    assert data["asg"]["name"] == "sre-demo-asg"
    assert len(data["instances"]) >= 1
    assert len(data["alarms"]) >= 1


@pytest.fixture
def mock_logs_client():
    """Patch CloudWatch Logs for /api/logs."""
    mock_logs = MagicMock()
    mock_logs.filter_log_events.return_value = {
        "events": [
            {"message": "START RequestId abc", "timestamp": 1705312800000},
            {"message": "END RequestId abc", "timestamp": 1705312801000},
        ]
    }
    with patch("app.logs_client", mock_logs):
        yield mock_logs


async def test_api_logs(client, mock_logs_client):
    """GET /api/logs returns CloudWatch log events."""
    resp = await client.get("/api/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert "logs" in data
    assert len(data["logs"]) >= 1
    assert "timestamp" in data["logs"][0]
    assert "message" in data["logs"][0]


@pytest.fixture
def mock_s3_client():
    """Patch S3 for /api/archives."""
    mock_s3 = MagicMock()
    mock_s3.list_buckets.return_value = {
        "Buckets": [{"Name": "sre-incident-logs-archive-test"}]
    }
    mock_s3.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "garbage.log-123", "Size": 1024 * 1024, "LastModified": datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)}
        ]
    }
    with patch("app.s3", mock_s3):
        yield mock_s3


async def test_api_archives(client, mock_s3_client):
    """GET /api/archives returns S3 archive list."""
    resp = await client.get("/api/archives")
    assert resp.status_code == 200
    data = resp.json()
    assert "archives" in data
    assert "bucket" in data
    assert data["bucket"] == "sre-incident-logs-archive-test"
    assert len(data["archives"]) >= 1
    assert data["archives"][0]["key"] == "garbage.log-123"


async def test_api_incidents_stats(client, mock_dynamodb_resource):
    """GET /api/incidents/stats returns aggregates."""
    mock_dynamodb_resource.scan.return_value = {
        "Items": [
            {"incident_id": "i1", "status": "completed", "created_at": "2024-01-15T10:00:00Z", "updated_at": "2024-01-15T10:05:00Z"},
            {"incident_id": "i2", "status": "failed", "created_at": "2024-01-15T11:00:00Z", "updated_at": "2024-01-15T11:10:00Z"},
        ]
    }
    resp = await client.get("/api/incidents/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "status_counts" in data
    assert "avg_mttr_seconds" in data
    assert "success_rate" in data
