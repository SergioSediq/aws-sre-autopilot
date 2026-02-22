# Service Level Objectives (SLOs)

Target metrics for the AI SRE platform.

## Incident Response

| Metric | Target | Notes |
|--------|--------|-------|
| **MTTR** (Mean Time To Repair) | < 5 minutes | From alarm firing to remediation complete |
| **Detection latency** | < 2 minutes | CloudWatch metric interval + alarm evaluation |
| **Approval latency** | < 3 minutes | Operator review (when APPROVAL_MODE=true) |

## Reliability

| Metric | Target | Notes |
|--------|--------|-------|
| **Remediation success rate** | > 90% | Completed vs failed incidents |
| **Lambda success rate** | > 99% | Successful handler invocations |
| **Dashboard availability** | > 99% | When used for approval workflow |

## AI Quality

| Metric | Target | Notes |
|--------|--------|-------|
| **Fallback usage** | < 20% | When Gemini fails, fallback logic is used |
| **Custom command override** | Optional | Operators may override AI suggestion |

---

*These are aspirational targets. Tune based on your environment and risk tolerance.*
