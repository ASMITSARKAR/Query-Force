provider "aws" {
  region = var.aws_region
}

# 7.2 VPC
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.0.0"

  name = "queryforce-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["${var.aws_region}a", "${var.aws_region}b"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]

  enable_nat_gateway = true
}

# 7.3 ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "queryforce-cluster"
}

# ECS Fargate Service (Backend)
resource "aws_ecs_task_definition" "backend" {
  family                   = "queryforce-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 1024
  memory                   = 2048
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([{
    name      = "queryforce-api"
    image     = "${var.ecr_repository_url}:latest"
    essential = true
    portMappings = [{
      containerPort = 8000
      hostPort      = 8000
    }]
    environment = [
      { name = "AWS_REGION", value = var.aws_region },
      { name = "DYNAMODB_SESSION_TABLE", value = aws_dynamodb_table.sessions.name },
      { name = "S3_DOCUMENTS_BUCKET", value = aws_s3_bucket.documents.bucket }
    ]
    secrets = [
      { name = "GROQ_API_KEY", valueFrom = aws_secretsmanager_secret.groq_api_key.arn },
      { name = "TELEMETRY_DSN", valueFrom = aws_secretsmanager_secret.db_password.arn }
    ]
  }])
}

# 7.4 RDS PostgreSQL (Telemetry)
resource "aws_db_instance" "telemetry" {
  identifier           = "queryforce-telemetry"
  engine               = "postgres"
  engine_version       = "16"
  instance_class       = "db.t3.micro"
  allocated_storage    = 20
  db_name              = "queryforce_telemetry"
  username             = "postgres"
  password             = var.db_password
  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name = module.vpc.database_subnet_group
  skip_final_snapshot  = true
}

# 7.5 DynamoDB (Sessions)
resource "aws_dynamodb_table" "sessions" {
  name           = "queryforce_sessions"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "session_id"

  attribute {
    name = "session_id"
    type = "S"
  }
  
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}

# 7.6 S3 Documents Bucket
resource "aws_s3_bucket" "documents" {
  bucket = "queryforce-documents-${var.environment}"
}

# 7.7 Secrets Manager
resource "aws_secretsmanager_secret" "groq_api_key" {
  name = "queryforce/groq_api_key"
}

resource "aws_secretsmanager_secret" "db_password" {
  name = "queryforce/db_password"
}

# IAM Roles (Skeleton)
resource "aws_iam_role" "ecs_task_execution_role" {
  name = "ecsTaskExecutionRole"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" } }]
  })
}

resource "aws_iam_role" "ecs_task_role" {
  name = "ecsTaskRole"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "ecs-tasks.amazonaws.com" } }]
  })
}

# Basic Security Group
resource "aws_security_group" "rds" {
  name   = "rds-sg"
  vpc_id = module.vpc.vpc_id
}
