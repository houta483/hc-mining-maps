# ECS Service for Frontend
resource "aws_ecs_service" "frontend" {
  name            = "borehole-frontend"
  cluster         = data.aws_ecs_cluster.cluster.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "frontend"
    container_port   = 80
  }

  depends_on = [aws_lb_listener_rule.frontend]

  tags = {
    Project = "borehole-analysis"
  }
}

# ECS Service for Backend
resource "aws_ecs_service" "backend" {
  name            = "borehole-backend"
  cluster         = data.aws_ecs_cluster.cluster.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.app.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 5000
  }

  depends_on = [aws_lb_listener_rule.backend]

  tags = {
    Project = "borehole-analysis"
  }
}

# EventBridge rule for scheduled pipeline runs
resource "aws_cloudwatch_event_rule" "pipeline_schedule" {
  name                = "borehole-pipeline-schedule"
  description         = "Run borehole pipeline every 10 minutes"
  schedule_expression = "rate(10 minutes)"

  tags = {
    Project = "borehole-analysis"
  }
}

# EventBridge target for pipeline task
resource "aws_cloudwatch_event_target" "pipeline" {
  rule      = aws_cloudwatch_event_rule.pipeline_schedule.name
  target_id = "BoreholePipelineTarget"
  arn       = data.aws_ecs_cluster.cluster.arn
  role_arn  = aws_iam_role.eventbridge.arn

  ecs_target {
    launch_type         = "FARGATE"
    platform_version    = "LATEST"
    task_definition_arn = aws_ecs_task_definition.pipeline.arn
    task_count          = 1

    network_configuration {
      subnets          = [for s in data.aws_subnet.private : s.id]
      security_groups  = [data.aws_security_group.ecs.id]
      assign_public_ip = false
    }
  }
}

# IAM role for EventBridge to run ECS tasks
resource "aws_iam_role" "eventbridge" {
  name_prefix = "borehole-eventbridge-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Project = "borehole-analysis"
  }
}

resource "aws_iam_role_policy" "eventbridge" {
  name_prefix = "borehole-eventbridge-"
  role        = aws_iam_role.eventbridge.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecs:RunTask"
        ]
        Resource = aws_ecs_task_definition.pipeline.arn
      },
      {
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = [
          aws_iam_role.task_execution.arn,
          aws_iam_role.task.arn
        ]
      }
    ]
  })
}

