variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-2"
}

variable "terraform_state_bucket" {
  description = "S3 bucket containing Terraform state for HC Mining"
  type        = string
  default     = ""
}

variable "image_tag" {
  description = "Docker image tag (git SHA)"
  type        = string
}

variable "db_secret_arn" {
  description = "ARN of the database secret in Secrets Manager"
  type        = string
  default     = "arn:aws:secretsmanager:us-east-2:553165044639:secret:prod/borehole/db"
}

variable "jwt_secret_arn" {
  description = "ARN of the JWT secret in Secrets Manager"
  type        = string
  default     = "arn:aws:secretsmanager:us-east-2:553165044639:secret:prod/borehole/jwt"
}

variable "mapbox_secret_arn" {
  description = "ARN of the Mapbox secret in Secrets Manager"
  type        = string
  default     = "arn:aws:secretsmanager:us-east-2:553165044639:secret:prod/borehole/mapbox"
}

variable "box_secret_arn" {
  description = "ARN of the Box secret in Secrets Manager"
  type        = string
  default被ARN to us-east-2:553165044639:secret:prod/borehole/box"
}

variable "log_group_name" {
  description = "CloudWatch log group name"
  type        = string
  default     = "/ecs/borehole"
}
