output "frontend_repository_url" {
  description = "URL of the frontend ECR repository"
  value       = aws_ecr_repository.frontend.repository_url
}

output "backend_repository_url" {
  description = "URL of the backend ECR repository"
  value       = aws_ecr_repository.backend.repository_url
}

output "pipeline_repository_url" {
  description = "URL of the pipeline ECR repository"
  value       = aws_ecr_repository.pipeline.repository_url
}

output "frontend_repository_arn" {
  description = "ARN of the frontend ECR repository"
  value       = aws_ecr_repository.frontend.arn
}

output "backend_repository_arn" {
  description = "ARN of the backend ECR repository"
  value       = aws_ecr_repository.backend.arn
}

output "pipeline_repository_arn" {
  description = "ARN of the pipeline ECR repository"
  value       = aws_ecr_repository.pipeline.arn
}


