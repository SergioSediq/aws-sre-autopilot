"""Pytest configuration."""
import os
import sys
from pathlib import Path

# Must run before handler (which uses boto3) is imported
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("RATE_LIMIT_DISABLED", "1")  # Disable rate limit in tests
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))


def pytest_configure(config):
    """Ensure AWS env is set before any tests run."""
    os.environ.setdefault("AWS_REGION", "us-east-1")
