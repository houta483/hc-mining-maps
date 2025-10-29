# Data sources for shared infrastructure
# Using hardcoded values from HC Mining shared resources

# Get existing ECS cluster
data "aws_ecs_cluster" "cluster" {
  cluster_name = "hc-mining"
}

# Get existing VPC
data "aws_vpc" "vpc" {
  id = "vpc-0c4831a5c6652ff71"
}

# Get existing subnets
data "aws_subnet" "private" {
  count = 2
  id    = ["subnet-06b64cf77582c2ce6", "subnet-0a9a2151c0467e3d3"][count.index]
}

# Get existing ALB
data "aws_lb" "alb" {
  arn = "arn:aws:elasticloadbalancing:us-east-2:553165044639:loadbalancer/app/hc-mining-alb-v2/f398a4a42564276e"
}

# Get ALB HTTPS listener (port 443)
data "aws_lb_listener" "https" {
  load_balancer_arn = data.aws_lb.alb.arn
  port              = 443
}

# Get security groups (using IDs from shared resources)
# Reference the existing ECS security group by ID
data "aws_security_group" "ecs" {
  id = "sg-04f49875c63de498c"
}
