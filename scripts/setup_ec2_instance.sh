#!/bin/bash
# Quick setup script to run on your manually launched EC2 instance
# Usage: 
#   1. Launch EC2 instance through AWS Console with the specs provided
#   2. SSH into instance: ssh -i ~/.ssh/gorggle-key.pem ubuntu@<PUBLIC_IP>
#   3. Run: bash <(curl -s https://raw.githubusercontent.com/gordowuu/GORGGLES2/main/scripts/setup_ec2_instance.sh)
#   Or upload this script and model manually

set -e

echo "=========================================="
echo "🚀 Gorggle AV-HuBERT Quick Setup"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${YELLOW}→ $1${NC}"; }
success() { echo -e "${GREEN}✓ $1${NC}"; }
error() { echo -e "${RED}ERROR: $1${NC}" >&2; exit 1; }

# Check if running on EC2
if ! curl -s --max-time 1 http://169.254.169.254/latest/meta-data/instance-id &> /dev/null; then
    error "This script must be run on an EC2 instance"
fi

INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
PRIVATE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)

info "Instance ID: $INSTANCE_ID"
info "Private IP: $PRIVATE_IP"
info "Public IP: $PUBLIC_IP"
echo ""

# Create working directory
INSTALL_DIR="/opt/avhubert"
info "Creating installation directory: $INSTALL_DIR"
sudo mkdir -p $INSTALL_DIR
sudo chown ubuntu:ubuntu $INSTALL_DIR
cd $INSTALL_DIR

# Update system
info "Updating system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq build-essential git wget curl unzip \
    python3-pip libsm6 libxext6 libxrender-dev libglib2.0-0 libgomp1

# Check for GPU
if command -v nvidia-smi &> /dev/null; then
    success "NVIDIA GPU detected:"
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
    USE_GPU=true
else
    echo -e "${YELLOW}⚠ No GPU detected. Will install CPU-only PyTorch${NC}"
    USE_GPU=false
fi

# Install Miniconda if not present
if ! command -v conda &> /dev/null; then
    info "Installing Miniconda..."
    wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh
    bash /tmp/miniconda.sh -b -p $HOME/miniconda3
    rm /tmp/miniconda.sh
    eval "$($HOME/miniconda3/bin/conda shell.bash hook)"
    conda init bash
    success "Miniconda installed"
else
    success "Conda already installed"
    eval "$(conda shell.bash hook)"
fi

# Create conda environment
info "Creating avhubert conda environment (Python 3.8)..."
conda create -n avhubert python=3.8 -y -q
conda activate avhubert

# Install PyTorch
info "Installing PyTorch..."
if [ "$USE_GPU" = true ]; then
    conda install pytorch torchvision torchaudio pytorch-cuda=11.8 -c pytorch -c nvidia -y -q
else
    conda install pytorch torchvision torchaudio cpuonly -c pytorch -y -q
fi

# Install Python dependencies
info "Installing Python dependencies..."
pip install -q fastapi uvicorn[standard] boto3 requests pydantic
pip install -q opencv-python numpy scipy scikit-video sentencepiece
pip install -q cmake dlib

# Install fairseq
info "Installing fairseq..."
cd $INSTALL_DIR
if [ ! -d "fairseq" ]; then
    git clone -q https://github.com/facebookresearch/fairseq.git
fi
cd fairseq
pip install -q --editable ./

# Clone AV-HuBERT
info "Cloning AV-HuBERT repository..."
cd $INSTALL_DIR
if [ ! -d "av_hubert" ]; then
    git clone -q https://github.com/facebookresearch/av_hubert.git
fi
cd av_hubert
pip install -q -r requirements.txt

# Download shape predictor (for dlib face detection)
info "Downloading dlib shape predictor..."
cd $INSTALL_DIR
if [ ! -f "shape_predictor_68_face_landmarks.dat" ]; then
    wget -q http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2
    bunzip2 shape_predictor_68_face_landmarks.dat.bz2
fi

# Create models directory
mkdir -p $INSTALL_DIR/models

echo ""
echo "=========================================="
echo "📦 Core Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1️⃣  Upload your model file from your local machine:"
echo "    scp -i ~/.ssh/gorggle-key.pem models/large_noise_pt_noise_ft_433h.pt ubuntu@$PUBLIC_IP:/tmp/"
echo "    ssh -i ~/.ssh/gorggle-key.pem ubuntu@$PUBLIC_IP"
echo "    mv /tmp/large_noise_pt_noise_ft_433h.pt /opt/avhubert/models/"
echo ""
echo "2️⃣  Upload server.py:"
echo "    scp -i ~/.ssh/gorggle-key.pem avhubert/server.py ubuntu@$PUBLIC_IP:/opt/avhubert/"
echo ""
echo "3️⃣  Start the server:"
echo "    conda activate avhubert"
echo "    cd /opt/avhubert"
echo "    python server.py"
echo ""
echo "4️⃣  Update Lambda with endpoint:"
echo "    aws lambda update-function-configuration --region us-east-1 \\"
echo "      --function-name gorggle-dev-invoke-lipreading \\"
echo "      --environment \"Variables={AVHUBERT_ENDPOINT=http://$PRIVATE_IP:8000}\""
echo ""
echo "📍 Your endpoints:"
echo "   Private (for Lambda): http://$PRIVATE_IP:8000"
echo "   Public (for testing):  http://$PUBLIC_IP:8000"
echo ""
