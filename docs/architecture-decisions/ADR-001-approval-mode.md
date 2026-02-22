# ADR-001: Human-in-the-Loop Approval Mode

## Status

Accepted

## Context

The SRE Brain Lambda can execute remediation commands directly on EC2 instances via SSM. Unchecked auto-execution risks unintended changes from AI-suggested commands.

## Decision

Introduce `APPROVAL_MODE` (default: true). When enabled:

- Lambda writes incidents to DynamoDB with status `pending_approval`
- Operators review and approve/reject via the dashboard
- Remediation runs only after explicit approval

When disabled, the original auto-execute behavior is used.

## Consequences

- **Pro:** Reduces risk of harmful auto-remediation
- **Pro:** Operators can override AI suggestions with custom commands
- **Con:** Increases MTTR by requiring human review
- **Con:** Dashboard must be operational for approval workflow
