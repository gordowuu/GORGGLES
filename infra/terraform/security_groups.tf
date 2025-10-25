# Security Groups for Gorggle Infrastructure
# Manages VPC security groups for Lambda and EC2 communication

# Data source for default VPC
data "aws_vpc" "default" {
  default = true
}

# Data source for VPC CIDR
data "aws_subnet" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
  
  availability_zone = "${var.region}a"
}

# Security Group for Lambda functions
# Allows outbound traffic to EC2 AV-HuBERT server
resource "aws_security_group" "lambda" {
  name        = "${local.name}-lambda-sg"
  description = "Security group for Gorggle Lambda functions"
  vpc_id      = data.aws_vpc.default.id

  # Allow all outbound traffic
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  tags = merge(local.tags, {
    Name = "${local.name}-lambda-sg"
  })
}

# Security Group for EC2 AV-HuBERT server
# Allows inbound traffic from Lambda on port 8000
resource "aws_security_group" "ec2_avhubert" {
  name        = "${local.name}-ec2-avhubert-sg"
  description = "Security group for Gorggle AV-HuBERT EC2 instance"
  vpc_id      = data.aws_vpc.default.id

  # Allow SSH from your IP (you'll need to update this)
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.admin_ip_cidr]
    description = "SSH access from admin IP"
  }

  # Allow port 8000 from Lambda security group
  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
    description     = "Allow AV-HuBERT API access from Lambda"
  }

  # Allow port 8000 from within VPC (for testing)
  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.default.cidr_block]
    description = "Allow AV-HuBERT API access from VPC"
  }

  # Allow all outbound traffic
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  tags = merge(local.tags, {
    Name = "${local.name}-ec2-avhubert-sg"
  })
}

# Output security group IDs for use in deploy_ec2.sh
output "lambda_security_group_id" {
  description = "Security group ID for Lambda functions"
  value       = aws_security_group.lambda.id
}

output "ec2_security_group_id" {
  description = "Security group ID for EC2 AV-HuBERT server"
  value       = aws_security_group.ec2_avhubert.id
}

output "ec2_security_group_name" {
  description = "Security group name for EC2 AV-HuBERT server (for deploy_ec2.sh)"
  value       = aws_security_group.ec2_avhubert.name
}
