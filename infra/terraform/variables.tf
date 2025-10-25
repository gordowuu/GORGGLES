variable "project_name" {
  type    = string
  default = "gorggle"
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "enable_website" {
  type    = bool
  default = false
}

# Admin IP for EC2 SSH access
variable "admin_ip_cidr" {
  type        = string
  description = "CIDR block for admin SSH access to EC2 (e.g., '1.2.3.4/32')"
  default     = "0.0.0.0/0"  # WARNING: Change this to your IP for production
}

# AV-HuBERT EC2 endpoint (set after deployment)
variable "avhubert_endpoint" {
  type        = string
  description = "Private endpoint for AV-HuBERT EC2 server (e.g., 'http://10.0.1.100:8000')"
  default     = ""  # Will be set by deploy_ec2.sh
}

