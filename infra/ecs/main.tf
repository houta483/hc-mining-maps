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

# Data sources are in data.tf

# Use existing ECS security group (shared with HC Mining)
# The existing SG already allows traffic from ALB and to RDS

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "app" {
  name              = var.log_group_name
  retention_in_days = 7

  tags = {
    Project = "borehole-analysis"
  }
}

# IAM role for ECS tasks
resource "aws_iam_role" "task_execution" {
  name_prefix = "borehole-task-exec-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Project = "borehole-analysis"
  }
}

# Attach managed policy for ECS task execution
resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Custom policy for Secrets Manager access
resource "aws_iam_role_policy" "secrets" {
  name_prefix = "borehole-secrets-"
  role        = aws_iam_role.task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          var.db_secret_arn,
          var.jwt_secret_arn,
          var.mapbox_secret_arn,
          var.box_secret_arn
        ]
      }
    ]
  })
}

# IAM role for ECS tasks (different from execution role)
resource "aws_iam_role" "task" {
  name_prefix = "borehole-task-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Project = "borehole-analysis"
  }
}

# Task definition for frontend
resource "aws_ecs_task_definition" "frontend" {
  family                   = "borehole-frontend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name  = "frontend"
      image = "553165044639.dkr.ecr.${var.region}.amazonaws.com/borehole-frontend:${var.image_tag}"

      portMappings = [
        {
          containerPort = 80
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "MAPBOX_TOKEN"
          value = "from-secret"
        }
      ]

      secrets = [
        {
          name      = "MAPBOX_TOKEN"
          valueFrom = "${var.mapbox_secret_arn}:token::"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "frontend"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:80 || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = {
    Project = "borehole-analysis"
  }
}

# Task definition for backend
resource "aws_ecs_task_definition" "backend" {
  family                   = "borehole-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name  = "backend"
      image = "553165044639.dkr.ecr.${var.region}.amazonaws.com/borehole-backend:${var.image_tag}"

      portMappings = [
        {
          containerPort = 5000
          protocol      = "tcp"
        }
      ]

      environment = [
        {
          name  = "API_PORT"
          value = "5000"
        },
        {
          name  = "API_HOST"
          value = "0.0.0.0"
        },
        {
          name  = "CORS_ORIGINS"
          value = "https://${data.aws_lb.alb.dns_name}"
        }
      ]

      secrets = [
        {
          name      = "MYSQL_HOST"
          valueFrom = "${var.db_secret_arn}:host::"
        },
        {
          name      = "MYSQL_PORT"
          valueFrom = "${var.db_secret_arn}:port::"
        },
        {
          name      = "MYSQL_DATABASE"
          valueFrom = "${var.db_secret_arn}:database::"
        },
        {
          name      = "MYSQL_USER"
          valueFrom = "${var.db_secret_arn}:username::"
        },
        {
          name      = "MYSQL_PASSWORD"
          valueFrom = "${var.db_secret_arn}:password::"
        },
        {
          name      = "JWT_SECRET_KEY"
          valueFrom = "${var.jwt_secret_arn}:secret_key::"
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "backend"
        }
      }

      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:5000/api/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])

  tags = {
    Project = "borehole-analysis"
  }
}

# Task definition for pipeline
resource "aws_ecs_task_definition" "pipeline" {
  family                   = "borehole-pipeline"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([
    {
      name  = "pipeline"
      image = "553165044639.dkr.ecr.${var.region}.amazonaws.com/borehole-pipeline:${var.image_tag}"

      environment = [
        {
          name  = "AWS_REGION"
          value = var.region
        },
        {
          name  = "CONFIG_FILE"
          value = "/app/config/config.yaml"
        },
        {
          name  = "USE_LOCAL_DATA"
          value = "false"
        },
        {
          name  = "DEBUG_MODE"
          value = "false"
        },
        {
          name  = "PYTHONPATH"
          value = "/app"
        }
      ]

      # Box config will be written from secret at startup via entrypoint
      environment = [
        {
          name  = "BOX_CONFIG"
          value = "/tmp/box_config.json"
        }
      ]

      # Entrypoint script writes Box config from secret, then runs pipeline
      entryPoint = ["/bin/sh", "-c"]
      command = [
        "echo \"$BOX_CONFIG_JSON\" > /tmp/box_config.json && chmod 600 /tmp/box_config.json && python3 -m src.main"
      ]

      secrets = [
        {
          name      = "BOX_CONFIG_JSON"
          valueFrom = var.box_secret_arn
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.app.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "pipeline"
        }
      }
    }
  ])

  tags = {
    Project = "borehole-analysis"
  }
}

