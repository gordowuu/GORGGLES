# AV-HuBERT Lip Reading Server

Serves AV-HuBERT model for audio-visual speech recognition on EC2 GPU instance.

## EC2 Setup

### Instance Requirements
- Type: `g4dn.xlarge` (1 x NVIDIA T4 GPU, 16GB GPU memory)
- AMI: Deep Learning AMI (Ubuntu 20.04) - has CUDA/PyTorch pre-installed
- Storage: 100GB EBS (model weights are ~1GB, video frames can be large)
- Security Group: Allow inbound on port 8000 from Lambda security group

### Launch Instance

```bash
# Use AWS Console or CLI to launch g4dn.xlarge with Deep Learning AMI
# Note the instance IP or DNS name
```

## Installation

SSH into your EC2 instance:

```bash
ssh -i your-key.pem ubuntu@<instance-ip>

# Clone fairseq and AV-HuBERT
cd ~
git clone https://github.com/facebookresearch/fairseq.git
cd fairseq
pip install --editable ./

cd ~
git clone https://github.com/facebookresearch/av_hubert.git
cd av_hubert
pip install -r requirements.txt

# Download pre-trained model (Large model trained on LRS3)
mkdir -p models
cd models
wget https://dl.fbaipublicfiles.com/avhubert/model/lrs3_vox/vsr/large_vox_iter5.pt
cd ..

# Install server dependencies
pip install fastapi uvicorn boto3 opencv-python-headless pillow
```

## Deploy Server

Copy the server code to EC2:

```bash
# From your local machine
scp -i your-key.pem server.py ubuntu@<instance-ip>:~/av_hubert/
scp -i your-key.pem requirements-server.txt ubuntu@<instance-ip>:~/av_hubert/
```

Start the server:

```bash
# On EC2
cd ~/av_hubert
python server.py
```

Or use systemd for production (see `avhubert.service`)

## Testing

```bash
curl -X POST http://<instance-ip>:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "s3_bucket": "gorggle-dev-uploads",
    "frames_prefix": "frames/test-video/",
    "fps": 25
  }'
```

## Costs

- g4dn.xlarge: ~$0.526/hour in us-east-1 (on-demand)
- Consider Spot instances for 70% savings
- Or use AWS Inference or EC2 Auto Scaling to start/stop based on demand
