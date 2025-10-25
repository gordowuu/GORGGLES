#!/bin/bash
# Automated EC2 Deployment for Gorggle AV-HuBERT Server
# This script launches EC2, uploads models, installs dependencies, and starts the service
# Prerequisites: AWS CLI configured, SSH key pair created, model file downloaded

set -e  # Exit on error

# ============================================================================
# Configuration
# ============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# EC2 Settings (modify these to match your AWS setup)
EC2_KEY_NAME="${EC2_KEY_NAME:-gorggle-key}"           # Your SSH key pair name
EC2_KEY_PATH="${EC2_KEY_PATH:-~/.ssh/${EC2_KEY_NAME}.pem}"
EC2_INSTANCE_TYPE="${EC2_INSTANCE_TYPE:-g4dn.xlarge}"
EC2_AMI="${EC2_AMI:-ami-0c55b159cbfafe1f0}"           # Ubuntu 20.04 Deep Learning AMI
EC2_REGION="${EC2_REGION:-us-east-1}"
EC2_SECURITY_GROUP="${EC2_SECURITY_GROUP:-gorggle-ec2-sg}"
EC2_SUBNET="${EC2_SUBNET:-}"                          # Leave empty for default VPC

# Model file (must be downloaded manually from official website)
MODEL_FILE="${MODEL_FILE:-$PROJECT_ROOT/models/large_noise_pt_noise_ft_433h.pt}"

# ============================================================================
# Color output
# ============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

error() { echo -e "${RED}ERROR: $1${NC}" >&2; exit 1; }
success() { echo -e "${GREEN}✓ $1${NC}"; }
info() { echo -e "${YELLOW}→ $1${NC}"; }

# ============================================================================
# Pre-flight Checks
# ============================================================================
echo "=== Gorggle EC2 Deployment Script ==="
echo ""

info "Running pre-flight checks..."

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    error "AWS CLI not found. Install with: pip install awscli"
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    error "AWS CLI not configured. Run 'aws configure' first."
fi

# Check SSH key
if [ ! -f "$EC2_KEY_PATH" ]; then
    error "SSH key not found at $EC2_KEY_PATH. Set EC2_KEY_PATH environment variable."
fi
chmod 400 "$EC2_KEY_PATH"

# Check model file
if [ ! -f "$MODEL_FILE" ]; then
    error "Model file not found at $MODEL_FILE. Download from: https://github.com/facebookresearch/av_hubert/tree/main/avhubert"
fi

success "Pre-flight checks passed"

# ============================================================================
# 1. Launch EC2 Instance (Spot or On-Demand)
# ============================================================================
echo ""
info "Launching EC2 instance..."

# Non-interactive override via env var USE_SPOT (true/false). If not set, prompt.
if [ -n "$USE_SPOT" ]; then
    case "${USE_SPOT,,}" in
        true|yes|y|1) USE_SPOT=true ;;
        *) USE_SPOT=false ;;
    esac
else
    read -p "Use Spot instance? (70% cheaper, may be interrupted) [y/N]: " -n 1 -r
    echo
    USE_SPOT=false
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        USE_SPOT=true
    fi
fi

# Create security group if it doesn't exist
SG_ID=$(aws ec2 describe-security-groups \
    --region "$EC2_REGION" \
    --filters "Name=group-name,Values=$EC2_SECURITY_GROUP" \
    --query 'SecurityGroups[0].GroupId' \
    --output text 2>/dev/null || echo "None")

if [ "$SG_ID" = "None" ]; then
    info "Creating security group: $EC2_SECURITY_GROUP"
    SG_ID=$(aws ec2 create-security-group \
        --region "$EC2_REGION" \
        --group-name "$EC2_SECURITY_GROUP" \
        --description "Security group for Gorggle AV-HuBERT EC2 instance" \
        --query 'GroupId' \
        --output text)
    
    # Allow SSH from your IP
    MY_IP=$(curl -s https://checkip.amazonaws.com)
    aws ec2 authorize-security-group-ingress \
        --region "$EC2_REGION" \
        --group-id "$SG_ID" \
        --protocol tcp \
        --port 22 \
        --cidr "$MY_IP/32"
    
    # Allow port 8000 from within VPC (Lambda access)
    VPC_CIDR=$(aws ec2 describe-vpcs \
        --region "$EC2_REGION" \
        --filters "Name=isDefault,Values=true" \
        --query 'Vpcs[0].CidrBlock' \
        --output text)
    
    aws ec2 authorize-security-group-ingress \
        --region "$EC2_REGION" \
        --group-id "$SG_ID" \
        --protocol tcp \
        --port 8000 \
        --cidr "$VPC_CIDR"
    
    success "Security group created: $SG_ID"
else
    success "Using existing security group: $SG_ID"
fi

# Launch instance
if [ "$USE_SPOT" = true ]; then
    info "Requesting spot instance..."
    SPOT_REQUEST=$(aws ec2 request-spot-instances \
        --region "$EC2_REGION" \
        --instance-count 1 \
        --type "one-time" \
        --launch-specification "{
            \"ImageId\": \"$EC2_AMI\",
            \"InstanceType\": \"$EC2_INSTANCE_TYPE\",
            \"KeyName\": \"$EC2_KEY_NAME\",
            \"SecurityGroupIds\": [\"$SG_ID\"]
        }" \
        --query 'SpotInstanceRequests[0].SpotInstanceRequestId' \
        --output text)
    
    info "Waiting for spot request to be fulfilled..."
    aws ec2 wait spot-instance-request-fulfilled \
        --region "$EC2_REGION" \
        --spot-instance-request-ids "$SPOT_REQUEST"
    
    INSTANCE_ID=$(aws ec2 describe-spot-instance-requests \
        --region "$EC2_REGION" \
        --spot-instance-request-ids "$SPOT_REQUEST" \
        --query 'SpotInstanceRequests[0].InstanceId' \
        --output text)
else
    info "Launching on-demand instance..."
    INSTANCE_ID=$(aws ec2 run-instances \
        --region "$EC2_REGION" \
        --image-id "$EC2_AMI" \
        --instance-type "$EC2_INSTANCE_TYPE" \
        --key-name "$EC2_KEY_NAME" \
        --security-group-ids "$SG_ID" \
        --query 'Instances[0].InstanceId' \
        --output text)
fi

# Tag instance
aws ec2 create-tags \
    --region "$EC2_REGION" \
    --resources "$INSTANCE_ID" \
    --tags Key=Name,Value=gorggle-avhubert-server Key=Project,Value=Gorggle

success "Instance launched: $INSTANCE_ID"

# Wait for instance to be running
info "Waiting for instance to start..."
aws ec2 wait instance-running \
    --region "$EC2_REGION" \
    --instance-ids "$INSTANCE_ID"

# Get instance IP
INSTANCE_IP=$(aws ec2 describe-instances \
    --region "$EC2_REGION" \
    --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

INSTANCE_PRIVATE_IP=$(aws ec2 describe-instances \
    --region "$EC2_REGION" \
    --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].PrivateIpAddress' \
    --output text)

success "Instance running at: $INSTANCE_IP (private: $INSTANCE_PRIVATE_IP)"

# Wait for SSH to be available
info "Waiting for SSH to be ready (this may take 2-3 minutes)..."
for i in {1..30}; do
    if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -i "$EC2_KEY_PATH" ubuntu@"$INSTANCE_IP" "echo 'SSH ready'" &> /dev/null; then
        success "SSH connection established"
        break
    fi
    sleep 10
    if [ $i -eq 30 ]; then
        error "SSH connection timeout. Check security group allows SSH from your IP."
    fi
done

# ============================================================================
# 2. Upload Files to EC2
# ============================================================================
echo ""
info "Uploading files to EC2..."

# Create remote directories
ssh -i "$EC2_KEY_PATH" ubuntu@"$INSTANCE_IP" "mkdir -p /tmp/gorggle"

# Upload setup scripts
info "Uploading setup scripts..."
scp -i "$EC2_KEY_PATH" "$PROJECT_ROOT/avhubert/setup_ec2.sh" ubuntu@"$INSTANCE_IP":/tmp/gorggle/
scp -i "$EC2_KEY_PATH" "$PROJECT_ROOT/avhubert/download_models.sh" ubuntu@"$INSTANCE_IP":/tmp/gorggle/

# Upload server code
info "Uploading AV-HuBERT server..."
scp -i "$EC2_KEY_PATH" "$PROJECT_ROOT/avhubert/server.py" ubuntu@"$INSTANCE_IP":/tmp/gorggle/

# Upload model file (this will take a few minutes)
info "Uploading model file (~1GB, may take 3-5 minutes)..."
scp -i "$EC2_KEY_PATH" "$MODEL_FILE" ubuntu@"$INSTANCE_IP":/tmp/gorggle/large_noise_pt_noise_ft_433h.pt

success "Files uploaded"

# ============================================================================
# 3. Run Setup on EC2
# ============================================================================
echo ""
info "Running setup on EC2 (this will take ~10 minutes)..."

ssh -i "$EC2_KEY_PATH" ubuntu@"$INSTANCE_IP" bash <<'ENDSSH'
set -e

cd /tmp/gorggle
chmod +x setup_ec2.sh download_models.sh

echo ">>> Running setup_ec2.sh..."
sudo bash setup_ec2.sh

echo ">>> Running download_models.sh..."
bash download_models.sh <<EOF
1
EOF

echo ">>> Moving model file..."
sudo mv /tmp/gorggle/large_noise_pt_noise_ft_433h.pt /opt/avhubert/models/

echo ">>> Moving server.py..."
sudo mv /tmp/gorggle/server.py /opt/avhubert/

echo ">>> Setup complete!"
ENDSSH

success "EC2 setup complete"

# ============================================================================
# 4. Configure systemd Service
# ============================================================================
echo ""
info "Configuring systemd service..."

ssh -i "$EC2_KEY_PATH" ubuntu@"$INSTANCE_IP" sudo bash <<'ENDSSH'
set -e

# Create systemd service file
cat > /etc/systemd/system/avhubert.service <<'EOF'
[Unit]
Description=AV-HuBERT Lip Reading Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/avhubert
Environment="PATH=/home/ubuntu/miniconda3/envs/avhubert/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/ubuntu/miniconda3/envs/avhubert/bin/python server.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and start service
systemctl daemon-reload
systemctl enable avhubert.service
systemctl start avhubert.service

echo "Service started!"
ENDSSH

success "Service configured and started"

# ============================================================================
# 5. Verify Service
# ============================================================================
echo ""
info "Verifying service..."

sleep 5  # Give service time to start

SERVICE_STATUS=$(ssh -i "$EC2_KEY_PATH" ubuntu@"$INSTANCE_IP" "systemctl is-active avhubert.service" || echo "inactive")

if [ "$SERVICE_STATUS" = "active" ]; then
    success "AV-HuBERT service is running!"
    
    # Test health endpoint
    info "Testing health endpoint..."
    HEALTH_CHECK=$(ssh -i "$EC2_KEY_PATH" ubuntu@"$INSTANCE_IP" "curl -s http://localhost:8000/health" || echo "failed")
    
    if [[ "$HEALTH_CHECK" == *"healthy"* ]]; then
        success "Health check passed: $HEALTH_CHECK"
    else
        echo -e "${YELLOW}Warning: Health check returned unexpected response${NC}"
    fi
else
    echo -e "${YELLOW}Warning: Service not active. Check logs with:${NC}"
    echo "  ssh -i $EC2_KEY_PATH ubuntu@$INSTANCE_IP sudo journalctl -u avhubert.service -f"
fi

# ============================================================================
# 6. Save Instance Info
# ============================================================================
echo ""
info "Saving instance information..."

mkdir -p "$PROJECT_ROOT/.deployment"

cat > "$PROJECT_ROOT/.deployment/ec2_info.sh" <<EOF
# EC2 Instance Information
# Source this file to set environment variables: source .deployment/ec2_info.sh

export EC2_INSTANCE_ID="$INSTANCE_ID"
export EC2_PUBLIC_IP="$INSTANCE_IP"
export EC2_PRIVATE_IP="$INSTANCE_PRIVATE_IP"
export EC2_REGION="$EC2_REGION"
export EC2_KEY_PATH="$EC2_KEY_PATH"
export AVHUBERT_ENDPOINT="http://$INSTANCE_PRIVATE_IP:8000"

# Quick SSH command
alias ssh-gorggle="ssh -i $EC2_KEY_PATH ubuntu@$INSTANCE_IP"
EOF

success "Instance info saved to: .deployment/ec2_info.sh"

# ============================================================================
# 7. Update Lambda Environment Variable
# ============================================================================
echo ""
info "Updating Lambda environment variable..."

# Find invoke_lipreading Lambda function name
LAMBDA_NAME=$(aws lambda list-functions \
    --region "$EC2_REGION" \
    --query "Functions[?contains(FunctionName, 'invoke_lipreading')].FunctionName" \
    --output text | head -n 1)

if [ -n "$LAMBDA_NAME" ]; then
    aws lambda update-function-configuration \
        --region "$EC2_REGION" \
        --function-name "$LAMBDA_NAME" \
        --environment "Variables={AVHUBERT_ENDPOINT=http://$INSTANCE_PRIVATE_IP:8000}" \
        > /dev/null
    
    success "Lambda updated with endpoint: http://$INSTANCE_PRIVATE_IP:8000"
else
    echo -e "${YELLOW}Warning: invoke_lipreading Lambda not found. Update manually later.${NC}"
fi

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "=========================================="
echo "🎉 Deployment Complete!"
echo "=========================================="
echo ""
echo "📊 Instance Details:"
echo "  Instance ID:   $INSTANCE_ID"
echo "  Public IP:     $INSTANCE_IP"
echo "  Private IP:    $INSTANCE_PRIVATE_IP"
echo "  Type:          $EC2_INSTANCE_TYPE"
echo "  Pricing:       $([ "$USE_SPOT" = true ] && echo 'Spot (~$0.16/hr)' || echo 'On-Demand (~$0.526/hr)')"
echo ""
echo "🔗 Service Endpoint:"
echo "  Internal: http://$INSTANCE_PRIVATE_IP:8000"
echo "  Health:   http://$INSTANCE_PRIVATE_IP:8000/health"
echo ""
echo "📝 Useful Commands:"
echo "  SSH into instance:"
echo "    ssh -i $EC2_KEY_PATH ubuntu@$INSTANCE_IP"
echo ""
echo "  View logs:"
echo "    ssh -i $EC2_KEY_PATH ubuntu@$INSTANCE_IP sudo journalctl -u avhubert.service -f"
echo ""
echo "  Restart service:"
echo "    ssh -i $EC2_KEY_PATH ubuntu@$INSTANCE_IP sudo systemctl restart avhubert.service"
echo ""
echo "  Stop instance (to save costs):"
echo "    aws ec2 stop-instances --region $EC2_REGION --instance-ids $INSTANCE_ID"
echo ""
echo "  Terminate instance:"
echo "    aws ec2 terminate-instances --region $EC2_REGION --instance-ids $INSTANCE_ID"
echo ""
echo "🚀 Next Steps:"
echo "  1. Run Terraform to update Lambda configurations:"
echo "     cd $PROJECT_ROOT/infra/terraform && terraform apply"
echo ""
echo "  2. Test the deployment:"
echo "     aws s3 cp test_video.mp4 s3://gorggle-dev-uploads/test_video.mp4"
echo ""
echo "  3. Monitor Step Functions execution in AWS Console"
echo ""
