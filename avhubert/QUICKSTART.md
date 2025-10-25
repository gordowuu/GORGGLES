# AV-HuBERT Quick Start Guide

## Summary

This guide will get AV-HuBERT running on EC2 in ~30 minutes.

## ⚠️ Before You Start

**LICENSE**: AV-HuBERT is for NON-COMMERCIAL RESEARCH ONLY. If Gorggle is commercial, you need Meta's permission or an alternative model.

## Prerequisites Checklist

- [ ] EC2 GPU instance launched (g4dn.xlarge or g6.xlarge)
- [ ] SSH access to instance
- [ ] Security group allows inbound port 8000
- [ ] At least 50GB disk space

## Installation (10 minutes)

### Step 1: SSH into EC2

```bash
ssh -i your-key.pem ubuntu@<ec2-public-ip>
```

### Step 2: Clone Repository

```bash
git clone https://github.com/gordowuu/GORGGLES2.git
cd GORGGLES2/avhubert
```

### Step 3: Run Setup Script

```bash
sudo bash setup_ec2.sh
```

This installs:
- Miniconda
- PyTorch with CUDA
- fairseq
- All Python dependencies

**Time**: ~8-10 minutes

### Step 4: Activate Environment

```bash
source /opt/avhubert/miniconda/bin/activate avhubert
```

## Download Models (15 minutes)

### Step 5: Download Preprocessing Files

```bash
bash download_models.sh
```

This downloads:
- Face detector (10MB)
- Landmark predictor (100MB)
- Mean face template (1MB)

**Time**: ~2-3 minutes

### Step 6: Download AV-HuBERT Model

**MANUAL STEP REQUIRED**:

1. Visit: http://facebookresearch.github.io/av_hubert
2. Find "Large-scale English model" section
3. Download **large_vox_iter5.pt** (~400MB) - RECOMMENDED
4. Transfer to EC2:

```bash
# On your local machine (where you downloaded the file)
scp -i your-key.pem large_vox_iter5.pt ubuntu@<ec2-ip>:/tmp/

# On EC2
sudo mv /tmp/large_vox_iter5.pt /opt/avhubert/model.pt
```

**Time**: ~5-10 minutes (depends on your internet speed)

### Step 7: Verify Files

```bash
ls -lh /opt/avhubert/
```

Should show:
```
-rw-r--r-- 1 ubuntu ubuntu  10M mmod_human_face_detector.dat
-rw-r--r-- 1 ubuntu ubuntu  99M shape_predictor_68_face_landmarks.dat
-rw-r--r-- 1 ubuntu ubuntu 1.1K mean_face.npy
-rw-r--r-- 1 ubuntu ubuntu 398M model.pt
```

## Deploy Server (5 minutes)

### Step 8: Setup Systemd Service

```bash
sudo nano /etc/systemd/system/avhubert.service
```

Paste:

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
ExecStart=/opt/avhubert/miniconda/envs/avhubert/bin/python /home/ubuntu/GORGGLES2/avhubert/server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Save (Ctrl+O, Enter, Ctrl+X)

### Step 9: Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable avhubert
sudo systemctl start avhubert
```

### Step 10: Check Status

```bash
sudo systemctl status avhubert
```

Should show: `Active: active (running)`

View logs:
```bash
sudo journalctl -u avhubert -f
```

Look for:
```
INFO:     AV-HuBERT model loaded successfully on cuda
INFO:     Face detection models loaded successfully
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## Test Server (2 minutes)

### Step 11: Health Check

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "model_loaded": true,
  "device": "cuda",
  "gpu_name": "Tesla T4"
}
```

## Connect to Lambda

### Step 12: Update Lambda Environment

1. Go to AWS Lambda Console
2. Find `gorggle-dev-invoke_lipreading` function
3. Configuration → Environment variables
4. Edit `AVHUBERT_ENDPOINT`:
   ```
   http://<ec2-PRIVATE-ip>:8000
   ```
   (Use private IP if Lambda is in same VPC)

5. Save

### Step 13: Test End-to-End

Upload a test video to S3:
```bash
aws s3 cp test_video.mp4 s3://gorggle-dev-uploads/test_video.mp4
```

Watch Step Functions execution in AWS console.

## Troubleshooting

### Server Won't Start

```bash
# Check if port 8000 is in use
sudo netstat -tlnp | grep 8000

# Test manually
conda activate avhubert
cd /home/ubuntu/GORGGLES2/avhubert
python server.py
```

### CUDA Errors

```bash
# Check GPU
nvidia-smi

# Verify CUDA in PyTorch
python -c "import torch; print(torch.cuda.is_available())"
```

### Model Not Found

```bash
# Verify model path
ls -lh /opt/avhubert/model.pt

# Check permissions
sudo chmod 644 /opt/avhubert/model.pt
```

### Face Detection Fails

```bash
# Verify dlib files
ls -lh /opt/avhubert/*.dat

# Test dlib
python -c "import dlib; d = dlib.cnn_face_detection_model_v1('/opt/avhubert/mmod_human_face_detector.dat'); print('OK')"
```

## Next Steps

1. **Monitor Performance**:
   ```bash
   watch -n 1 nvidia-smi
   ```

2. **View Logs**:
   ```bash
   sudo journalctl -u avhubert -f
   ```

3. **Update Code**:
   ```bash
   cd ~/GORGGLES2
   git pull
   sudo systemctl restart avhubert
   ```

4. **Scale Up** (if needed):
   - Switch to g4dn.2xlarge for faster inference
   - Use Spot Instances to save 70% on costs

## Quick Reference

**Service Commands**:
```bash
sudo systemctl start avhubert      # Start
sudo systemctl stop avhubert       # Stop
sudo systemctl restart avhubert    # Restart
sudo systemctl status avhubert     # Status
sudo journalctl -u avhubert -f     # Logs
```

**File Locations**:
- Model: `/opt/avhubert/model.pt`
- Server: `/home/ubuntu/GORGGLES2/avhubert/server.py`
- Service: `/etc/systemd/system/avhubert.service`
- Logs: `sudo journalctl -u avhubert`

**API Endpoints**:
- Health: `http://<ec2-ip>:8000/health`
- Predict: `http://<ec2-ip>:8000/predict`
- Docs: `http://<ec2-ip>:8000/docs`

## Support

- Full README: `avhubert/README.md`
- Architecture: `ARCHITECTURE.md`
- Issues: https://github.com/gordowuu/GORGGLES2/issues
