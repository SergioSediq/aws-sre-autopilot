"""Tests for sre-brain Lambda handler with mocked AWS."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Mock boto3 BEFORE handler is imported (avoids NoRegionError, no real AWS calls)
mock_boto3 = MagicMock()
mock_boto3.client.return_value = MagicMock()
mock_boto3.resource.return_value = MagicMock()
sys.modules["boto3"] = mock_boto3
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sre-brain"))

import handler as handler_mod


def test_get_target_instances_from_instance_id():
    """get_target_instances returns instance when InstanceId dimension present."""
    with patch.object(handler_mod, "asg_client", MagicMock()), patch.object(
        handler_mod, "elbv2_client", MagicMock()
    ):
        alarm = {"Trigger": {"Dimensions": [{"name": "InstanceId", "value": "i-abc123"}]}}
        result = handler_mod.get_target_instances(alarm)
        assert result == ["i-abc123"]


def test_get_target_instances_from_asg():
    """get_target_instances returns ASG instances when AutoScalingGroupName present."""
    mock_asg = MagicMock()
    mock_asg.describe_auto_scaling_groups.return_value = {
        "AutoScalingGroups": [{
            "Instances": [
                {"InstanceId": "i-1", "LifecycleState": "InService"},
                {"InstanceId": "i-2", "LifecycleState": "InService"},
            ]
        }]
    }
    with patch.object(handler_mod, "asg_client", mock_asg), patch.object(
        handler_mod, "elbv2_client", MagicMock()
    ):
        alarm = {"Trigger": {"Dimensions": [{"name": "AutoScalingGroupName", "value": "sre-demo-asg"}]}}
        result = handler_mod.get_target_instances(alarm)
        assert result == ["i-1", "i-2"]


def test_get_target_instances_empty_dimensions():
    """get_target_instances returns empty list when no valid dimension."""
    with patch.object(handler_mod, "asg_client", MagicMock()), patch.object(
        handler_mod, "elbv2_client", MagicMock()
    ):
        alarm = {"Trigger": {"Dimensions": [{"name": "UnknownDimension", "value": "x"}]}}
        result = handler_mod.get_target_instances(alarm)
        assert result == []


def test_get_target_instances_from_target_group():
    """get_target_instances returns unhealthy instances when TargetGroup dimension present."""
    mock_elbv2 = MagicMock()
    mock_elbv2.describe_target_health.return_value = {
        "TargetHealthDescriptions": [
            {"Target": {"Id": "i-unhealthy1"}, "TargetHealth": {"State": "unhealthy"}},
            {"Target": {"Id": "i-unhealthy2"}, "TargetHealth": {"State": "draining"}},
            {"Target": {"Id": "i-healthy"}, "TargetHealth": {"State": "healthy"}},
        ]
    }
    with patch.object(handler_mod, "asg_client", MagicMock()), patch.object(
        handler_mod, "elbv2_client", mock_elbv2
    ):
        alarm = {
            "Trigger": {"Dimensions": [{"name": "TargetGroup", "value": "targetgroup/sre-demo-tg/abc123"}]},
            "Region": "ap-south-1",
            "AWSAccountId": "123456789012",
        }
        result = handler_mod.get_target_instances(alarm)
        assert set(result) == {"i-unhealthy1", "i-unhealthy2"}
        assert "i-healthy" not in result


def test_get_log_bucket_fallback():
    """get_log_bucket returns fallback when list_buckets fails."""
    mock_s3 = MagicMock()
    mock_s3.list_buckets.side_effect = Exception("AccessDenied")
    with patch.object(handler_mod, "s3_client", mock_s3):
        result = handler_mod.get_log_bucket()
        assert result == "sre-incident-logs-archive"


def test_get_log_bucket_finds_archive():
    """get_log_bucket returns first matching bucket name."""
    mock_s3 = MagicMock()
    mock_s3.list_buckets.return_value = {
        "Buckets": [{"Name": "other"}, {"Name": "sre-incident-logs-archive-123"}]
    }
    with patch.object(handler_mod, "s3_client", mock_s3):
        result = handler_mod.get_log_bucket()
        assert result == "sre-incident-logs-archive-123"


def test_send_ssm_command_returns_command_id():
    """send_ssm_command returns CommandId on success."""
    mock_ssm = MagicMock()
    mock_ssm.send_command.return_value = {"Command": {"CommandId": "cmd-123"}}
    with patch.object(handler_mod, "ssm", mock_ssm):
        result = handler_mod.send_ssm_command("i-abc", ["echo hi"])
        assert result == "cmd-123"


def test_send_ssm_command_returns_none_on_failure():
    """send_ssm_command returns None on failure."""
    mock_ssm = MagicMock()
    mock_ssm.send_command.side_effect = Exception("Failed")
    with patch.object(handler_mod, "ssm", mock_ssm):
        result = handler_mod.send_ssm_command("i-abc", ["echo hi"])
        assert result is None


def test_fallback_remediation_disk():
    """fallback_remediation returns S3 archive command for Disk issues."""
    mock_s3 = MagicMock()
    mock_s3.list_buckets.return_value = {"Buckets": [{"Name": "sre-incident-logs-archive-test"}]}
    with patch.object(handler_mod, "s3_client", mock_s3):
        result = handler_mod.fallback_remediation("Disk Critical")
        assert "reasoning" in result
        assert "command" in result
        assert "s3://sre-incident-logs-archive-test" in result["command"]


def test_fallback_remediation_nginx():
    """fallback_remediation returns nginx restart for Nginx issues."""
    result = handler_mod.fallback_remediation("Nginx Down")
    assert result["command"] == "systemctl restart nginx"


def test_fallback_remediation_memory():
    """fallback_remediation returns pkill for Memory issues."""
    result = handler_mod.fallback_remediation("Memory Exhaustion")
    assert "pkill" in result["command"]


def test_fallback_remediation_unknown():
    """fallback_remediation returns no-op for unknown issue type."""
    result = handler_mod.fallback_remediation("Unknown")
    assert result["command"] == "echo 'No remediation found'"


def test_lambda_handler_ignores_non_alarm():
    """lambda_handler returns 200 and ignores OK/INSUFFICIENT_DATA transitions."""
    event = {
        "Records": [{
            "Sns": {"Message": '{"NewStateValue": "OK", "AlarmName": "Test", "Trigger": {"Dimensions": []}}'}
        }]
    }
    result = handler_mod.lambda_handler(event, None)
    assert result["statusCode"] == 200
    assert "Ignored" in result["body"]


def test_ask_genai_uses_fallback_when_no_api_key():
    """ask_genai returns fallback when GEMINI_API_KEY is missing or dummy."""
    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}, clear=False):
        result = handler_mod.ask_genai("df shows 95% full", "Disk Critical")
    assert "reasoning" in result
    assert "command" in result
    assert "s3://" in result["command"] or "archive" in result["command"].lower()


def test_ask_genai_uses_fallback_on_http_error():
    """ask_genai returns fallback when Gemini API returns HTTP error."""
    import urllib.error

    with patch.dict("os.environ", {"GEMINI_API_KEY": "AIza-test123"}, clear=False):
        with patch.object(handler_mod, "get_log_bucket", return_value="test-bucket"):
            with patch(
                "urllib.request.urlopen",
                side_effect=urllib.error.HTTPError("url", 500, "Server Error", {}, None),
            ):
                result = handler_mod.ask_genai("context", "Memory Exhaustion")
    assert "reasoning" in result
    assert "pkill" in result["command"]


def test_lambda_handler_no_targets_returns_400():
    """lambda_handler returns 400 when no target instances found."""
    event = {
        "Records": [{
            "Sns": {
                "Message": json.dumps({
                    "NewStateValue": "ALARM",
                    "AlarmName": "Disk-Critical",
                    "AlarmDescription": "",
                    "Trigger": {"Dimensions": [{"name": "UnknownDim", "value": "x"}]},
                })
            }
        }]
    }
    with patch.object(handler_mod, "asg_client", MagicMock()), patch.object(
        handler_mod, "elbv2_client", MagicMock()
    ):
        result = handler_mod.lambda_handler(event, None)
        assert result["statusCode"] == 400
