"""Tests for chaos_master logic and constants."""
import sys
from pathlib import Path

# Add chaos-scripts to path for import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "chaos-scripts"))


def test_chaos_master_constants():
    """Verify chaos_master constants."""
    import chaos_master as cm
    assert cm.GARBAGE_LOG_PATH == "/var/log/garbage.log"


def test_chaos_master_has_trigger_functions():
    """Verify chaos_master exposes trigger functions."""
    import chaos_master as cm
    assert callable(cm.trigger_oom)
    assert callable(cm.trigger_disk_fill)
    assert callable(cm.kill_nginx)


def test_chaos_master_argparse_modes():
    """Test valid chaos modes."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["oom", "disk-fill", "kill-nginx"], required=True)
    for mode in ["oom", "disk-fill", "kill-nginx"]:
        args = parser.parse_args(["--mode", mode])
        assert args.mode == mode
