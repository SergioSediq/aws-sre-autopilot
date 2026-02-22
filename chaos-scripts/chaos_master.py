import argparse
import subprocess
import os
import sys

GARBAGE_LOG_PATH = "/var/log/garbage.log"


def run_command(command):
    """Utility to run shell commands."""
    try:
        subprocess.run(command, shell=True, check=True)
        print(f"Executed: {command}")
    except subprocess.CalledProcessError as e:
        print(f"Error executing {command}: {e}")


def trigger_oom():
    """Trigger Out of Memory using stress-ng."""
    print("WARNING: Triggering OOM... This might make the system unresponsive.")
    # Assuming stress-ng is installed.
    # --vm-bytes 90% --vm-keep --vm-hang 0
    cmd = "stress-ng --vm 1 --vm-bytes 95% --vm-populate --timeout 600s &"
    run_command(cmd)
    print("OOM initiated. Monitor resources with 'top' or 'htop'.")


def trigger_disk_fill():
    """Fill the disk using dd."""
    print(f"WARNING: Filling disk at {GARBAGE_LOG_PATH}...")
    # Create a 10GB file (or enough to fill > 85%)
    # Using /dev/zero is faster
    cmd = f"dd if=/dev/zero of={GARBAGE_LOG_PATH} bs=1M count=10000"
    run_command(cmd)
    print("Disk fill initiated.")


def kill_nginx():
    """Stop the Nginx service."""
    print("WARNING: Stopping Nginx...")
    run_command("systemctl stop nginx")
    print("Nginx stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chaos Master Script for AI SRE Demo")
    parser.add_argument(
        "--mode",
        choices=["oom", "disk-fill", "kill-nginx"],
        required=True,
        help="Chaos mode to trigger",
    )

    args = parser.parse_args()

    if os.geteuid() != 0:
        print("This script must be run as root!")
        sys.exit(1)

    if args.mode == "oom":
        trigger_oom()
    elif args.mode == "disk-fill":
        trigger_disk_fill()
    elif args.mode == "kill-nginx":
        kill_nginx()
