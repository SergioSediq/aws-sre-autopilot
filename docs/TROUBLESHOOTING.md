# Troubleshooting

Common issues and fixes for the AI SRE platform.

## Infra Artifacts

If `infra/response*.json` files were committed and you want to stop tracking them: run `scripts/clean-infra-artifacts.sh` (or `git rm --cached infra/response*.json`) then commit.

---

## Terraform

### "Error acquiring the state lock"

- **Cause:** Previous `terraform apply` or `plan` was interrupted.
- **Fix:** Run `terraform force-unlock <LOCK_ID>` (find the lock ID in the error message), or wait for the lock to expire.

### "Backend configuration changed"

- **Cause:** Terraform state backend was modified.
- **Fix:** Run `terraform init -reconfigure` to reinitialize with the new backend.

### "Invalid API Key" or Gemini errors in Lambda

- **Cause:** `gemini_api_key` in terraform.tfvars is wrong or expired.
- **Fix:** Get a new key from [Google AI Studio](https://aistudio.google.com/apikey) and update terraform.tfvars, then `terraform apply`.

---

## Dashboard

### "Could not connect to backend" / CORS errors

- **Cause:** Dashboard cannot reach the FastAPI server.
- **Fix:** Ensure the dashboard is running (`cd dashboard && python app.py`). Check that port 3000 is free.

### "Access Denied" or AWS credential errors

- **Cause:** AWS credentials not configured for the dashboard.
- **Fix:** Run `aws configure` or set `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`. Ensure the IAM user/role has permissions for DynamoDB, CloudWatch, SSM, ASG, ELB, S3.

### DynamoDB table not found

- **Cause:** Infrastructure not deployed or wrong region.
- **Fix:** Run `terraform apply` in `infra/`. Set `AWS_REGION` or `DYNAMODB_TABLE` env var if using a different region/table.

---

## Lambda (SRE Brain)

### Lambda timeout or no incident created

- **Cause:** SSM Run Command taking too long, or Gemini API slow.
- **Fix:** Increase Lambda timeout in Terraform. Check CloudWatch Logs for `/aws/lambda/sre-brain-handler` for errors.

### SSM "Target not connected"

- **Cause:** EC2 instance does not have SSM agent running or IAM role attached.
- **Fix:** Verify EC2 IAM role has `AmazonSSMManagedInstanceCore`. Ensure instance is in a subnet with NAT/VPC endpoint for SSM. Run `sudo systemctl status amazon-ssm-agent` on the instance.

---

## Chaos / EC2

### Chaos script "Permission denied"

- **Cause:** Chaos scripts require root.
- **Fix:** Run with `sudo python3 chaos_master.py --mode disk-fill`.

### Alarm never fires

- **Cause:** CloudWatch Agent not sending metrics, or threshold not met.
- **Fix:** Check CloudWatch Metrics for `CWAgent` namespace. Verify alarm threshold (e.g. disk > 85%). On EC2, ensure CloudWatch Agent is running: `sudo systemctl status amazon-cloudwatch-agent`.

### ALB reports unhealthy but Nginx is running

- **Cause:** Health check path or port misconfigured.
- **Fix:** Verify ALB target group health check path (e.g. `/health`) and port match the FastAPI app. Check security groups allow traffic from ALB to EC2.

---

## General

### "Model not found" or Gemini API error

- **Cause:** Model name may have changed. Google updates model names over time.
- **Fix:** Use `gemini-1.5-pro` or `gemini-1.5-flash` in terraform.tfvars. Check [Google AI documentation](https://ai.google.dev/gemini-api/docs/models) for current names.
