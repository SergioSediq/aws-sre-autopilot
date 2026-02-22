provider "aws" {
  region = "ap-south-1"
}

# --- Data Sources ---
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_vpc" "default" {
  default = true
}
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# --- S3 Bucket for Logs ---
resource "aws_s3_bucket" "log_archive" {
  bucket_prefix = "sre-incident-logs-archive-"
  force_destroy = true
}

# --- IAM Roles ---
# EC2 Role
resource "aws_iam_role" "ec2_role" {
  name = "sre_demo_ec2_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "cw_agent" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

resource "aws_iam_role_policy" "s3_access" {
  name = "s3_access"
  role = aws_iam_role.ec2_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["s3:PutObject", "s3:GetObject", "s3:ListBucket", "s3:ListAllMyBuckets"]
      Resource = ["*"]
    }]
  })
}

resource "aws_iam_role_policy" "dashboard_permissions" {
  name = "dashboard_permissions"
  role = aws_iam_role.ec2_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "autoscaling:DescribeAutoScalingGroups",
          "autoscaling:DescribeAutoScalingInstances"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "elasticloadbalancing:DescribeTargetGroups",
          "elasticloadbalancing:DescribeTargetHealth",
          "elasticloadbalancing:DescribeLoadBalancers"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Scan",
          "dynamodb:Query"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams",
          "logs:GetLogEvents",
          "logs:FilterLogEvents"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:DescribeInstanceStatus"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ssm:SendCommand",
          "ssm:GetCommandInvocation",
          "ssm:ListCommands"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:DescribeAlarms",
          "cloudwatch:GetMetricData"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "sre_demo_ec2_profile"
  role = aws_iam_role.ec2_role.name
}

# Lambda Role
resource "aws_iam_role" "lambda_role" {
  name = "sre_demo_lambda_role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_ssm" {
  name = "lambda_ssm"
  role = aws_iam_role.lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:SendCommand", 
          "ssm:GetCommandInvocation", 
          "ssm:ListCommands",
          "autoscaling:DescribeAutoScalingGroups",
          "s3:ListAllMyBuckets"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Scan",
          "dynamodb:Query"
        ]
        Resource = "*"
      }
    ]
  })
}

# --- Networking & Compute ---
resource "aws_security_group" "web_sg" {
  name        = "sre_demo_web_sg"
  description = "Allow HTTP and SSH"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "aws_launch_template" "app_lt" {
  name_prefix   = "sre-demo-lt-"
  image_id      = data.aws_ami.ubuntu.id
  instance_type = "t3.micro"
  
  iam_instance_profile {
    name = aws_iam_instance_profile.ec2_profile.name
  }

  vpc_security_group_ids = [aws_security_group.web_sg.id]

  user_data = base64encode(file("${path.module}/../vm-image/user_data.sh"))
  
  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "SRE-Demo-Instance"
    }
  }
}

resource "aws_autoscaling_group" "app_asg" {
  name                = "sre-demo-asg"
  desired_capacity    = 1
  max_size            = 2
  min_size            = 1
  vpc_zone_identifier = data.aws_subnets.default.ids
  launch_template {
    id      = aws_launch_template.app_lt.id
    version = "$Latest"
  }
}

# --- Load Balancer (ALB) ---
resource "aws_lb" "app_alb" {
  name               = "sre-demo-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.web_sg.id]
  subnets            = data.aws_subnets.default.ids
}

resource "aws_lb_target_group" "app_tg" {
  name     = "sre-demo-tg"
  port     = 80
  protocol = "HTTP"
  vpc_id   = data.aws_vpc.default.id
  health_check {
    path = "/health" # Check FastAPI health
    matcher = "200"
  }
}

resource "aws_lb_listener" "front_end" {
  load_balancer_arn = aws_lb.app_alb.arn
  port              = "80"
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app_tg.arn
  }
}

resource "aws_autoscaling_attachment" "asg_attachment" {
  autoscaling_group_name = aws_autoscaling_group.app_asg.id
  lb_target_group_arn    = aws_lb_target_group.app_tg.arn
}

# --- AI SRE Brain (Lambda & SNS) ---
resource "aws_sns_topic" "alerts" {
  name = "sre-incident-alerts"
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../sre-brain/handler.py"
  output_path = "${path.module}/../sre-brain/lambda_function.zip"
}

resource "aws_lambda_function" "sre_brain" {
  filename      = data.archive_file.lambda_zip.output_path
  function_name = "sre-brain-handler"
  role          = aws_iam_role.lambda_role.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.11"
  timeout       = 180 # 3 minutes (Gemini API can take time)

  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      GEMINI_API_KEY  = var.gemini_api_key
      GEMINI_MODEL    = var.gemini_model
      DYNAMODB_TABLE  = aws_dynamodb_table.sre_incidents.name
      APPROVAL_MODE   = "true"
    }
  }
}

resource "aws_lambda_permission" "with_sns" {
  statement_id  = "AllowExecutionFromSNS"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sre_brain.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.alerts.arn
}

resource "aws_sns_topic_subscription" "lambda_sub" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.sre_brain.arn
}

# --- CloudWatch Alarms ---

# 1. Disk Critical (> 85%) on CWAgent logic (ASG Aggregated)
resource "aws_cloudwatch_metric_alarm" "disk_alarm" {
  alarm_name          = "Disk-Critical-ASG"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "disk_used_percent"
  namespace           = "CWAgent"
  period              = "60"
  statistic           = "Average"
  threshold           = "85"
  alarm_description   = "Disk Usage > 85%"
  dimensions = {
    AutoScalingGroupName = aws_autoscaling_group.app_asg.name
    # Removed path to match CWAgent aggregation behavior
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
}

# 2. Memory Exhaustion (> 90%)
resource "aws_cloudwatch_metric_alarm" "memory_alarm" {
  alarm_name          = "Memory-Exhaustion-ASG"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "mem_used_percent"
  namespace           = "CWAgent"
  period              = "60"
  statistic           = "Average"
  threshold           = "90"
  alarm_description   = "Memory Usage > 90%"
  dimensions = {
    AutoScalingGroupName = aws_autoscaling_group.app_asg.name
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
}

# 3. Nginx Down (Unhealthy Host Count > 0)
resource "aws_cloudwatch_metric_alarm" "nginx_down" {
  alarm_name          = "Nginx-Down-ALB"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "UnHealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  period              = "60"
  statistic           = "Maximum"
  threshold           = "0"
  alarm_description   = "Nginx Down (Unhealthy Hosts)"
  dimensions = {
    TargetGroup  = aws_lb_target_group.app_tg.arn_suffix
    LoadBalancer = aws_lb.app_alb.arn_suffix
  }
  alarm_actions = [aws_sns_topic.alerts.arn]
}

# --- DynamoDB for Incident Tracking ---
resource "aws_dynamodb_table" "sre_incidents" {
  name         = "sre-incidents"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "incident_id"

  attribute {
    name = "incident_id"
    type = "S"
  }

  tags = {
    Name = "sre-incidents"
  }
}

# --- Outputs ---
output "alb_dns_name" {
  value = aws_lb.app_alb.dns_name
}

output "bucket_name" {
  value = aws_s3_bucket.log_archive.id
}

output "dynamodb_table" {
  value = aws_dynamodb_table.sre_incidents.name
}
