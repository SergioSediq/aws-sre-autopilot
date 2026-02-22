# AI SRE: Self-Healing Infrastructure — Architecture Guide

A complete technical deep-dive into how the AI-powered SRE platform works.

---

## 1. Why This Project?

| Challenge | Traditional SRE | AI SRE (This Project) |
|-----------|-----------------|----------------------|
| Detection | Human watches dashboards | CloudWatch alarms auto-trigger |
| Diagnosis | SSH into servers manually | Lambda runs diagnostics via SSM |
| Fix Planning | Engineer decides what to do | Gemini AI suggests remediation |
| Execution | Manual SSH commands | Auto-execute or human approval via dashboard |
| Reporting | Manual write-up | Auto-generated incident reports |

**Bottom line**: MTTR drops from minutes to seconds, with full audit trails.

---

## 2. High-Level Architecture

```mermaid
graph TD
    EC2[EC2 Instance] -->|metrics| CWA[CloudWatch Agent]
    CWA -->|disk, memory| ALARM[CloudWatch Alarms]
    ALARM -->|ALARM state| SNS[SNS Topic]
    SNS -->|invokes| LAMBDA[Lambda - SRE Brain]
    LAMBDA -->|diagnose via| SSM[AWS SSM]
    SSM -->|runs commands on| EC2
    LAMBDA -->|asks AI| GEMINI[Google Gemini API]
    LAMBDA -->|stores incident| DYNAMO[DynamoDB]
    LAMBDA -->|archives logs| S3[S3 Bucket]
    DASH[SRE Dashboard] -->|reads| DYNAMO
    DASH -->|approve/reject| SSM
    ALB[Load Balancer] -->|routes traffic| EC2
```

---

## 3. AWS Components

| Component | Resource Name | Purpose |
|-----------|--------------|---------|
| Compute | `sre-demo-asg` (ASG) | Auto-scales 1-2 `t3.micro` EC2 instances |
| Load Balancer | `sre-demo-alb` | Distributes HTTP traffic to EC2 |
| Monitoring | 3 CloudWatch Alarms | Disk >85%, Memory >90%, Nginx down |
| Notification | `sre-incident-alerts` (SNS) | Bridges alarms to Lambda |
| AI Engine | `sre-brain-handler` (Lambda) | Diagnoses and plans remediation |
| AI Model | Google Gemini API | Generates remediation commands |
| Database | `sre-incidents` (DynamoDB) | Tracks all incidents + timeline |
| Storage | `sre-incident-logs-archive-*` (S3) | Archives rotated logs |
| Execution | AWS SSM | Runs shell commands on EC2 remotely |

---

## 4. EC2 Instance Stack

Each EC2 instance runs the following:

```mermaid
graph LR
    NGINX[Nginx - Port 80] -->|proxy_pass| APP[FastAPI - Port 8000]
    CW[CloudWatch Agent] -->|every 60s| METRICS[Disk + Memory Metrics]
    CHAOS[chaos_master.py] -->|simulates failures| NGINX
```

- **Nginx**: Reverse proxy serving traffic on port 80
- **FastAPI**: Simple health-check app on port 8000
- **CloudWatch Agent**: Reports `disk_used_percent` and `mem_used_percent`
- **chaos_master.py**: Triggers chaos scenarios for testing

---

## 5. Incident Lifecycle

### Step-by-Step Flow

```mermaid
sequenceDiagram
    participant EC2
    participant CW as CloudWatch
    participant SNS
    participant Lambda as SRE Brain
    participant AI as Gemini AI
    participant SSM
    participant DB as DynamoDB
    participant Dash as Dashboard
    participant Op as Operator

    EC2->>CW: Metric exceeds threshold
    CW->>SNS: Alarm fires
    SNS->>Lambda: Invoke

    Lambda->>SSM: Run diagnostic commands
    SSM->>EC2: Execute (df -h, free -m, etc.)
    EC2-->>Lambda: Return diagnostic output

    Lambda->>AI: Analyze diagnostics
    AI-->>Lambda: Suggest fix command

    Lambda->>DB: Save incident (pending_approval)

    Dash->>DB: Poll for incidents
    Dash->>Op: Show AI suggestion
    Op->>Dash: Approve or Reject
    Dash->>SSM: Execute approved command
    SSM->>EC2: Run fix
    EC2-->>Dash: Return result
    Dash->>DB: Update status (completed)
```

### Incident Status Flow

```mermaid
stateDiagram-v2
    [*] --> pending_approval
    pending_approval --> executing : Approved
    pending_approval --> rejected : Rejected
    executing --> completed : Success
    executing --> failed : Error
    executing --> timeout : Timed out
```

---

## 6. Three Monitored Scenarios

### Alarm Details

| Alarm | Trigger | Diagnostics | AI Fallback Fix |
|-------|---------|-------------|-----------------|
| `Disk-Critical-ASG` | `disk_used_percent > 85%` | `df -h`, `ls /var/log` | Archive garbage.log to S3, truncate |
| `Memory-Exhaustion-ASG` | `mem_used_percent > 90%` | `free -m`, `ps aux` | `pkill -f stress-ng` |
| `Nginx-Down-ALB` | `UnHealthyHostCount > 0` | `systemctl status nginx` | `systemctl restart nginx` |

### Lambda Decision Flow

```mermaid
flowchart TD
    A[Alarm Received] --> B{What type?}
    B -->|Disk| C[Run: df -h]
    B -->|Memory| D[Run: free -m]
    B -->|Nginx| E[Run: systemctl status nginx]
    C --> F[Send to Gemini AI]
    D --> F
    E --> F
    F --> G{Approval Mode?}
    G -->|ON| H[Save to DynamoDB for review]
    G -->|OFF| I[Auto-execute fix via SSM]
```

---

## 7. Chaos Engineering

Chaos can be triggered from the dashboard UI or manually via SSM:

| Mode | What It Does | Expected Alarm |
|------|-------------|----------------|
| `disk-fill` | Writes zeros to `/var/log/garbage.log` until >85% full | `Disk-Critical-ASG` |
| `oom` | Runs `stress-ng` at 95% memory for 600s | `Memory-Exhaustion-ASG` |
| `nginx-crash` | Stops Nginx service | `Nginx-Down-ALB` |

---

## 8. DynamoDB Incident Schema

```json
{
  "incident_id": "1708300000_Disk-Critical-ASG_i-0abc123",
  "alarm_name": "Disk-Critical-ASG",
  "alarm_description": "Disk Usage > 85%",
  "instance_id": "i-0abc123def456",
  "status": "pending_approval",
  "diagnostics": "Filesystem  Size  Used Avail Use% ...",
  "ai_suggestion": "aws s3 cp /var/log/garbage.log s3://...",
  "ai_reasoning": "Disk usage critical. Archiving to S3.",
  "remediation_output": "",
  "timeline": [
    {"event": "created", "timestamp": "..."},
    {"event": "approved", "timestamp": "..."},
    {"event": "completed", "timestamp": "..."}
  ]
}
```

---

## 9. Directory Structure

```
Ai-Incident-SRE/
├── .env                    # Secrets (git-ignored)
├── .env.example
├── .gitignore
├── README.md               # Quick-start guide
├── ARCHITECTURE.md         # This file
├── CHANGELOG.md
├── LICENSE
│
├── infra/                  # Terraform IaC
│   ├── main.tf             # All AWS resources
│   ├── variables.tf        # Variable definitions
│   └── terraform.tfvars    # Secret values (git-ignored)
│
├── sre-brain/              # AI Lambda
│   └── handler.py          # Lambda handler + Gemini AI
│
├── dashboard/              # SRE Command Center
│   ├── app.py              # FastAPI backend
│   ├── requirements.txt
│   └── static/             # Frontend (HTML/CSS/JS)
│
├── vm-image/               # EC2 setup
│   ├── app.py              # Health-check app
│   └── user_data.sh        # Bootstrap script
│
├── chaos-scripts/          # Chaos engineering
│   └── chaos_master.py
├── docs/
│   └── TROUBLESHOOTING.md
└── tests/
    └── test_chaos_master.py
```
