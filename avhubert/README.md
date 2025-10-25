# AV-HuBERT Inference Server

This directory contains the FastAPI server for running AV-HuBERT (Audio-Visual Hidden Unit BERT) inference on an EC2 GPU instance. AV-HuBERT performs state-of-the-art audio-visual speech recognition by combining lip reading with audio transcription.

## ⚠️ License Notice

**IMPORTANT**: AV-HuBERT is licensed under Meta Platforms' custom license for **NON-COMMERCIAL RESEARCH USE ONLY**. This implementation is intended for research and educational purposes. For commercial use, you must:
- Contact Meta Platforms for commercial licensing
- Or use an alternative model with appropriate licensing

See: https://github.com/facebookresearch/av_hubert/blob/main/LICENSE

## Overview

The AV-HuBERT server:
1. Receives video frame locations from Lambda via HTTP POST
2. Downloads frames from S3
3. Detects faces and extracts mouth ROI (96x96 pixels)
4. Runs GPU inference using pre-trained AV-HuBERT model
5. Returns lip reading predictions with confidence scores

## Architecture

```
Lambda (invoke_lipreading) 
    ↓ HTTP POST
EC2 GPU Instance (g4dn.xlarge)
    ↓ Download frames
S3 (processed bucket)
    ↓ Face detection + Mouth ROI extraction (dlib)
    ↓ 96x96 mouth crops
AV-HuBERT Model (PyTorch + fairseq)
    ↓ GPU Inference
Return JSON: {text, confidence}
```

## Prerequisites

- EC2 GPU instance (g4dn.xlarge or g6.xlarge with NVIDIA GPU)
- Ubuntu 20.04 or 22.04
- CUDA 11.7+ and cuDNN
- At least 16GB GPU memory
- 50GB+ disk space for models and dependencies

## Installation

### Option 1: Automated Setup (Recommended)

```bash
# SSH into your EC2 instance
ssh -i your-key.pem ubuntu@<ec2-ip>

# Download setup scripts from your repository
git clone https://github.com/gordowuu/GORGGLES2.git
cd GORGGLES2/avhubert

# Run automated setup (requires sudo)
sudo bash setup_ec2.sh

# Download model files
bash download_models.sh

# Manually download AV-HuBERT model checkpoint
# Visit: http://facebookresearch.github.io/av_hubert
# Download: large_vox_iter5.pt (or your preferred checkpoint)
# Save to: /opt/avhubert/model.pt
```

### Option 2: Manual Setup

#### 1. Install System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake git wget curl \
    python3-pip python3-dev libsm6 libxext6 libxrender-dev \
    libglib2.0-0 libgomp1
```

#### 2. Install CUDA (if not present)

```bash
# Check CUDA version
nvcc --version

# If CUDA not installed, download from:
# https://developer.nvidia.com/cuda-downloads
```

#### 3. Install Miniconda

```bash
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh -b -p /opt/avhubert/miniconda
export PATH="/opt/avhubert/miniconda/bin:$PATH"
conda init bash
source ~/.bashrc
```

#### 4. Create Conda Environment

```bash
conda create -n avhubert python=3.8 -y
conda activate avhubert
```

#### 5. Install PyTorch with CUDA

```bash
conda install pytorch torchvision torchaudio pytorch-cuda=11.7 -c pytorch -c nvidia -y
```

#### 6. Install Python Dependencies

```bash
pip install fastapi uvicorn[standard] boto3 requests pydantic
pip install opencv-python numpy scipy scikit-video
pip install sentencepiece dlib
```

#### 7. Install fairseq

```bash
cd /opt/avhubert
git clone https://github.com/facebookresearch/fairseq.git
cd fairseq
pip install --editable ./
```

#### 8. Download AV-HuBERT Repository

```bash
cd /opt/avhubert
git clone https://github.com/facebookresearch/av_hubert.git
cd av_hubert
pip install -r requirements.txt
```

## Download Required Model Files

### 1. Face Detection Models (dlib)

```bash
cd /opt/avhubert

# Face detector (~10MB)
wget http://dlib.net/files/mmod_human_face_detector.dat.bz2
bunzip2 mmod_human_face_detector.dat.bz2

# Facial landmark predictor (~100MB)
wget http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2
bunzip2 shape_predictor_68_face_landmarks.dat.bz2
```

### 2. Mean Face for Mouth ROI Alignment

```bash
wget https://raw.githubusercontent.com/facebookresearch/av_hubert/main/avhubert/preparation/mean_face.npy
```

### 3. AV-HuBERT Pre-trained Model

Visit the official model repository:
**http://facebookresearch.github.io/av_hubert**

Download one of:
- **AV-HuBERT Base** (large_vox_iter5.pt) - ~400MB - RECOMMENDED
- **AV-HuBERT Large** - ~1GB - Better accuracy, slower inference
- **V-HuBERT** (visual-only) - ~400MB - For noisy/silent environments

Save the downloaded checkpoint as:
```bash
/opt/avhubert/model.pt
```

### 4. Verify All Files

```bash
ls -lh /opt/avhubert/
# Should show:
# - mmod_human_face_detector.dat
# - shape_predictor_68_face_landmarks.dat
# - mean_face.npy
# - model.pt
```

## Configuration

Set environment variables (or edit systemd service file):

```bash
export AVHUBERT_MODEL_PATH="/opt/avhubert/model.pt"
export FACE_DETECTOR_PATH="/opt/avhubert/mmod_human_face_detector.dat"
export LANDMARK_PREDICTOR_PATH="/opt/avhubert/shape_predictor_68_face_landmarks.dat"
export MEAN_FACE_PATH="/opt/avhubert/mean_face.npy"
export AWS_REGION="us-east-1"
```

## Deploy Server

### 1. Copy server.py to EC2

```bash
# On your local machine
scp -i your-key.pem server.py ubuntu@<ec2-ip>:/opt/avhubert/
```

### 2. Test Server Manually

```bash
conda activate avhubert
cd /opt/avhubert
python server.py
```

The server will start on `http://0.0.0.0:8000`

### 3. Setup Systemd Service (Production)

Create `/etc/systemd/system/avhubert.service`:

```ini
[Unit]
Description=AV-HuBERT Inference Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/avhubert
Environment="PATH=/opt/avhubert/miniconda/envs/avhubert/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="AVHUBERT_MODEL_PATH=/opt/avhubert/model.pt"
Environment="FACE_DETECTOR_PATH=/opt/avhubert/mmod_human_face_detector.dat"
Environment="LANDMARK_PREDICTOR_PATH=/opt/avhubert/shape_predictor_68_face_landmarks.dat"
Environment="MEAN_FACE_PATH=/opt/avhubert/mean_face.npy"
Environment="AWS_REGION=us-east-1"
ExecStart=/opt/avhubert/miniconda/envs/avhubert/bin/python /opt/avhubert/server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable avhubert
sudo systemctl start avhubert
sudo systemctl status avhubert
```

### 4. Configure Security Group

In AWS EC2 console, add inbound rule:
- Type: Custom TCP
- Port: 8000
- Source: Lambda security group or VPC CIDR

### 5. Update Lambda Environment Variable

Update `invoke_lipreading` Lambda:
```bash
AVHUBERT_ENDPOINT=http://<ec2-private-ip>:8000
```

## API Endpoints

### POST /predict

Request:
```json
{
  "s3_bucket": "gorggle-dev-processed",
  "s3_prefix": "frames/job123/"
}
```

Response:
```json
{
  "text": "hello world",
  "confidence": 0.92,
  "num_frames": 75
}
```

### GET /health

Returns:
```json
{
  "status": "healthy",
  "model_loaded": true,
  "device": "cuda",
  "gpu_name": "Tesla T4"
}
```

## Mouth ROI Preprocessing

The server performs these steps for each frame:
1. **Face Detection**: Uses dlib CNN face detector
2. **Landmark Detection**: Identifies 68 facial landmarks
3. **Face Alignment**: Warps face to align with mean face template
4. **Mouth ROI Extraction**: Crops 96x96 region around mouth (landmarks 48-68)
5. **Normalization**: Converts to float32, normalizes to [0,1]

This preprocessing ensures the model receives properly aligned mouth regions, critical for accurate lip reading.

## Troubleshooting

### Model Loading Errors

```bash
# Check model file exists and is readable
ls -lh /opt/avhubert/model.pt

# Test loading in Python
python -c "import torch; torch.load('/opt/avhubert/model.pt')"
```

### CUDA/GPU Issues

```bash
# Check GPU availability
nvidia-smi

# Test PyTorch CUDA
python -c "import torch; print(torch.cuda.is_available())"
```

### dlib Face Detection Issues

```bash
# Verify dlib models
ls -lh /opt/avhubert/*.dat /opt/avhubert/*.npy

# Test face detection
python -c "import dlib; detector = dlib.cnn_face_detection_model_v1('/opt/avhubert/mmod_human_face_detector.dat'); print('OK')"
```

### Memory Issues

```bash
# Monitor GPU memory
watch -n 1 nvidia-smi

# If OOM errors, consider:
# - Using smaller batch sizes
# - Using AV-HuBERT Base instead of Large
# - Upgrading to g4dn.2xlarge or g6.2xlarge
```

### Server Won't Start

```bash
# Check logs
sudo journalctl -u avhubert -f

# Test manually
conda activate avhubert
cd /opt/avhubert
python server.py
```

## Performance

**Expected throughput (g4dn.xlarge with Tesla T4):**
- AV-HuBERT Base: ~10-15 FPS (66-100ms per frame)
- AV-HuBERT Large: ~5-8 FPS (125-200ms per frame)
- 10-minute video (~15,000 frames): 16-25 minutes processing

**Optimization tips:**
- Use batched inference for multiple frames
- Cache face detection results across similar frames
- Use V-HuBERT (visual-only) if audio isn't needed

## Cost Estimation

**g4dn.xlarge (Tesla T4, 4 vCPU, 16GB RAM):**
- On-Demand: ~$0.526/hour
- Spot Instance: ~$0.16-0.21/hour (70% savings)

**For 10-min video processing (~20 min runtime):**
- On-Demand: ~$0.18
- Spot: ~$0.05-0.07

Consider using Spot Instances with interruption handling for cost savings.

## Development

### Local Testing (without GPU)

```bash
# Use CPU mode (slow but works)
export DEVICE="cpu"
python server.py
```

### Adding Custom Preprocessing

Edit `detect_face_and_extract_mouth()` function in `server.py` to modify:
- Face detection parameters
- Mouth ROI size
- Landmark alignment strategy

## References

- AV-HuBERT Paper: https://arxiv.org/abs/2201.02184
- Official Repository: https://github.com/facebookresearch/av_hubert
- Model Checkpoints: http://facebookresearch.github.io/av_hubert
- dlib Face Detection: http://dlib.net/
- fairseq Framework: https://github.com/facebookresearch/fairseq

## Support

For issues specific to:
- **AV-HuBERT model**: See official repo issues
- **Gorggle integration**: Open issue at https://github.com/gordowuu/GORGGLES2
- **AWS/Infrastructure**: Check CloudWatch logs and Terraform state
