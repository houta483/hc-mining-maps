terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

resource "aws_ecr_repository" "frontend" {
  name                 = "borehole-frontend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }


  tags = {
    Project = "borehole-analysis"
    Service = "frontend"
  }
}

resource "aws_ecr_repository" "backend" {
  name                 = "borehole-backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }


  tags = {
    Project = "borehole-analysis"
    Service = "backend"
  }
}

resource "aws_ecr_repository" "pipeline" {
  name                 = "borehole-pipeline"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }


  tags = {
    Project = "borehole-analysis"
    Service = "pipeline"
  }
}

