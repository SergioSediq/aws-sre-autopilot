# Dashboard API Reference

API endpoints for the SRE Command Center. Interactive docs: `/docs` (Swagger UI).

## Base URL

- Local: `http://localhost:3000`
- Production: `http://<alb_dns_name>`

## Endpoints

### Health

| Method | Path     | Description                    |
| ------ | -------- | ------------------------------ |
| GET    | `/health` | Liveness probe. Returns `{"status": "ok", "service": "sre-dashboard"}` |

### Incidents

| Method | Path                     | Description                          |
| ------ | ------------------------ | ------------------------------------ |
| GET    | `/api/incidents`         | List all incidents                   |
| GET    | `/api/incidents?status=` | Filter by status (e.g. `pending_approval`) |
| GET    | `/api/incidents/stats`   | Incident statistics (MTTR, success rate) |
| GET    | `/api/incidents/{id}`    | Get single incident by ID            |
| POST   | `/api/approve/{id}`      | Approve remediation (optional `custom_command` in body) |
| POST   | `/api/reject/{id}`       | Reject incident                      |

### Chaos

| Method | Path                | Description                                      |
| ------ | ------------------- | ------------------------------------------------ |
| POST   | `/api/chaos/{mode}` | Trigger chaos: `disk-fill`, `nginx-crash`, `oom` |

## Auth

Dashboard uses AWS credentials (IAM) for DynamoDB, SSM, CloudWatch. No API keys required for local use.

## Rate Limiting

60 requests per minute per IP. Disable with `RATE_LIMIT_DISABLED=1`.
