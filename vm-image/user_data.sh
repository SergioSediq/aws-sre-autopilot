#!/bin/bash
set -e

# Update and install dependencies
apt-get update
apt-get install -y nginx python3-pip stress-ng unzip curl jq

# Install CloudWatch Agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
dpkg -i -E ./amazon-cloudwatch-agent.deb

# Install Python packages
pip3 install fastapi uvicorn boto3 requests awscli

# --- Create App File ---
cat << 'EOF' > /home/ubuntu/app.py
from fastapi import FastAPI
import uvicorn
import socket

app = FastAPI()

@app.get("/")
def read_root():
    hostname = socket.gethostname()
    return {"message": "Hello from AI SRE Demo App", "host": hostname}

@app.get("/health")
def read_health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
EOF

# --- Create Chaos Script ---
cat << 'EOF' > /home/ubuntu/chaos_master.py
import argparse
import subprocess
import time
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
    cmd = "stress-ng --vm 1 --vm-bytes 95% --vm-populate --timeout 600s &"
    run_command(cmd)
    print("OOM initiated.")

def trigger_disk_fill():
    """Fill the disk using dd."""
    print(f"WARNING: Filling disk at {GARBAGE_LOG_PATH}...")
    import shutil
    total, used, free = shutil.disk_usage("/")
    # Leave 500MB for system services (SSM Agent logs)
    safe_margin = 500 * 1024 * 1024 
    bytes_to_fill = free - safe_margin
    
    if bytes_to_fill > 0:
        blocks = int(bytes_to_fill / (1024 * 1024))
        print(f"Filling {blocks} MB to reach critical state...")
        cmd = f"dd if=/dev/zero of={GARBAGE_LOG_PATH} bs=1M count={blocks}"
    else:
        print("Disk already critical (<500MB free). Skipping fill.")
        cmd = "echo 'Disk already full'"
    run_command(cmd)
    print("Disk fill initiated.")

def kill_nginx():
    """Stop the Nginx service."""
    print("WARNING: Stopping Nginx...")
    run_command("systemctl stop nginx")
    print("Nginx stopped.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chaos Master Script for AI SRE Demo")
    parser.add_argument("--mode", choices=["oom", "disk-fill", "kill-nginx"], required=True, help="Chaos mode to trigger")
    
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
EOF

# --- Configure Nginx ---
cat << 'EOF' > /etc/nginx/sites-available/default
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

# --- CloudWatch Agent Config ---
cat << 'EOF' > /opt/aws/amazon-cloudwatch-agent/bin/config.json
{
	"agent": {
		"metrics_collection_interval": 60,
		"run_as_user": "root"
	},
	"metrics": {
		"aggregation_dimensions": [
			[
				"AutoScalingGroupName"
			]
		],
		"append_dimensions": {
			"AutoScalingGroupName": "${aws:AutoScalingGroupName}",
			"ImageId": "${aws:ImageId}",
			"InstanceId": "${aws:InstanceId}",
			"InstanceType": "${aws:InstanceType}"
		},
		"metrics_collected": {
			"disk": {
				"measurement": [
					"used_percent"
				],
				"metrics_collection_interval": 60,
				"resources": [
					"/"
				]
			},
			"mem": {
				"measurement": [
					"mem_used_percent"
				],
				"metrics_collection_interval": 60
			}
		}
	}
}
EOF

# --- Start Services ---
systemctl restart nginx

# Setup FastAPI Service
cat << 'EOF' > /etc/systemd/system/fastapi_app.service
[Unit]
Description=FastAPI App
After=network.target

[Service]
User=root
WorkingDirectory=/home/ubuntu
ExecStart=/usr/bin/python3 /home/ubuntu/app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl enable fastapi_app
systemctl start fastapi_app

# Start CloudWatch Agent
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -s -c file:/opt/aws/amazon-cloudwatch-agent/bin/config.json

echo "User Data Script Completed!"
