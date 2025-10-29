# Target group for Frontend
resource "aws_lb_target_group" "frontend" {
  name        = "borehole-frontend-tg"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.vpc.id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 2
    timeout             = 5
    interval            = 30
    path                = "/"
    matcher             = "200"
  }

  deregistration_delay = 30

  tags = {
    Project = "borehole-analysis"
  }
}

# Target group for Backend
resource "aws_lb_target_group" "backend" {
  name        = "borehole-backend-tg"
  port        = 5000
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.vpc.id
  target_type = "ip"

  health_check {
    enabled             = true
    healthy_threshold   = 2
    unhealthy_threshold = 2
    timeout             = 5
    interval            = 30
    path                = "/api/health"
    matcher             = "200"
  }

  deregistration_delay = 30

  tags = {
    Project = "borehole-analysis"
  }
}

# ALB Listener Rule for Frontend
resource "aws_lb_listener_rule" "frontend" {
  listener_arn = data.aws_lb_listener.https.arn
  priority     = 100

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }

  condition {
    path_pattern {
      values = ["/boreholes*"]
    }
  }
}

# ALB Listener Rule for Backend API
resource "aws_lb_listener_rule" "backend" {
  listener_arn = data.aws_lb_listener.https.arn
  priority     = 101

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/boreholes/api*"]
    }
  }
}

