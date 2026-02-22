"""Tests for vm-image health check app."""
import importlib.util
from pathlib import Path

import pytest

# Load vm-image app explicitly to avoid conflict with dashboard/app
_vm_app_path = Path(__file__).resolve().parent.parent / "vm-image" / "app.py"
_spec = importlib.util.spec_from_file_location("vm_image_app", _vm_app_path)
_vm_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vm_module)
app = _vm_module.app


def test_read_root():
    """GET / returns message and host."""
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data
    assert "host" in data
    assert "AI SRE" in data["message"]


def test_read_health():
    """GET /health returns status ok."""
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
