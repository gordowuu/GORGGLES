#!/bin/bash
# AV-HuBERT EC2 Setup Script for Gorggle
# This script sets up the complete AV-HuBERT environment on EC2 GPU instance
# Run as: sudo bash setup_ec2.sh

set -e  # Exit on error

echo "======================================"
echo "AV-HuBERT EC2 Setup for Gorggle"
echo "======================================"

# Configuration
INSTALL_DIR="/opt/avhubert"
PYTHON_VERSION="3.8"
CUDA_VERSION="11.7"

# Create installation directory
echo "[1/9] Creating installation directory..."
mkdir -p $INSTALL_DIR
cd $INSTALL_DIR

# Update system packages
echo "[2/9] Updating system packages..."
apt-get update
apt-get install -y build-essential cmake git wget curl unzip \
    python3-pip python3-dev libsm6 libxext6 libxrender-dev \
    libglib2.0-0 libgomp1

# Install CUDA and cuDNN (if not already installed)
echo "[3/9] Checking CUDA installation..."
if ! command -v nvcc &> /dev/null; then
    echo "CUDA not found. Please install CUDA $CUDA_VERSION manually."
    echo "Visit: https://developer.nvidia.com/cuda-downloads"
    exit 1
else
    echo "CUDA found: $(nvcc --version | grep release)"
fi

# Install Miniconda
echo "[4/9] Installing Miniconda..."
if ! command -v conda &> /dev/null; then
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh
    bash miniconda.sh -b -p $INSTALL_DIR/miniconda
    rm miniconda.sh
    export PATH="$INSTALL_DIR/miniconda/bin:$PATH"
    conda init bash
else
    echo "Conda already installed"
fi

# Create conda environment
echo "[5/9] Creating conda environment..."
conda create -n avhubert python=$PYTHON_VERSION -y
source $INSTALL_DIR/miniconda/bin/activate avhubert

# Install PyTorch with CUDA support
echo "[6/9] Installing PyTorch with CUDA $CUDA_VERSION..."
conda install pytorch torchvision torchaudio pytorch-cuda=11.7 -c pytorch -c nvidia -y

# Install Python dependencies
echo "[7/9] Installing Python dependencies..."
pip install fastapi uvicorn[standard] boto3 requests pydantic
pip install opencv-python numpy scipy scikit-video
pip install sentencepiece

# Install dlib (for face detection)
pip install cmake
pip install dlib

# Clone and install fairseq
echo "[8/9] Installing fairseq..."
cd $INSTALL_DIR
git clone https://github.com/facebookresearch/fairseq.git
cd fairseq
pip install --editable ./

# Download AV-HuBERT repository
echo "[9/9] Downloading AV-HuBERT repository..."
cd $INSTALL_DIR
git clone https://github.com/facebookresearch/av_hubert.git
cd av_hubert
pip install -r requirements.txt

echo ""
echo "======================================"
echo "Core Installation Complete!"
echo "======================================"
echo ""
echo "Next Steps:"
echo "1. Download required preprocessing files (run download_models.sh)"
echo "2. Download pre-trained model checkpoint"
echo "3. Deploy server.py from your Gorggle repository"
echo "4. Start the FastAPI server"
echo ""
echo "Conda environment: avhubert"
echo "Activate with: conda activate avhubert"
echo ""
