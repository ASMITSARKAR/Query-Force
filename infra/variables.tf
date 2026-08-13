variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment (dev/prod)"
  type        = string
  default     = "prod"
}

variable "db_password" {
  description = "RDS PostgreSQL password"
  type        = string
  sensitive   = true
}

variable "ecr_repository_url" {
  description = "URL of the ECR repository containing the QueryForce API image"
  type        = string
}
