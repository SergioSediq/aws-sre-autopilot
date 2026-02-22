# Operational Runbook

## Deployment

1. **Configure secrets**
   - Copy `infra/terraform.tfvars.example` to `infra/terraform.tfvars`
   - Add `gemini_api_key` (from [Google AI Studio](https://aistudio.google.com/apikey))

2. **Apply infrastructure**
   ```bash
   cd infra
   terraform init
   terraform plan
   terraform apply -auto-approve
   ```

3. **Verify**
   - Note `alb_dns_name` output
   - Visit `http://<alb_dns_name>` for the app
   - Dashboard: `http://<alb_dns_name>:3000` (or via ALB listener)

## Rollback

- **Terraform:** `terraform apply` with previous state, or `terraform destroy` and redeploy
- **Lambda:** Redeploy previous zip via Terraform or AWS Console
- **Dashboard:** Roll back container/image to previous tag

## Chaos Testing

1. Get an instance ID: `aws ec2 describe-instances --filters "Name=tag:Name,Values=sre-demo*" --query "Reservations[].Instances[].InstanceId" --output text`
2. SSM into instance: `aws ssm start-session --target <INSTANCE_ID>`
3. Run chaos: `sudo python3 /home/ubuntu/chaos_master.py --mode disk-fill`
4. Monitor CloudWatch alarms and dashboard for incident creation

## Monitoring

- **CloudWatch Logs:** `/aws/lambda/sre-brain-handler`
- **DynamoDB:** Table `sre-incidents` (or `DYNAMODB_TABLE` env)
- **Dashboard:** Incident list, metrics, Lambda logs viewer

## Common Commands

| Task | Command |
|------|---------|
| Run tests | `pytest tests/ -v` or `make test` |
| Build Lambda zip | `make build-lambda` |
| Lint | `ruff check dashboard/ sre-brain/ chaos-scripts/` |
| Format | `ruff format dashboard/ sre-brain/ chaos-scripts/` |
| Dashboard (local) | `cd dashboard && python app.py` |
| Dashboard (Docker) | `docker compose up --build` |
