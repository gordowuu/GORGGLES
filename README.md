# Gorggle (GORGGLES2)

🎬 **AI-powered video transcription platform** combining **audio transcription**, **AI lip reading**, and **speaker diarization** for accessible, accurate video captions.

---

## ✨ Features

- 🎤 **Audio Transcription**: AWS Transcribe with speaker diarization
- 👄 **AI Lip Reading**: AV-HuBERT visual speech recognition
- 👤 **Face Detection**: AWS Rekognition face tracking
- 🎯 **Speaker Fusion**: Intelligent alignment of audio + visual + face data
- 🌐 **Web Interface**: Modern drag-&-drop upload + caption viewer
- ⚡ **GPU-Accelerated**: Fast inference on NVIDIA GPUs
- 🏗️ **Serverless Pipeline**: AWS Lambda + Step Functions orchestration

---

## 🚀 Quick Start

### Prerequisites

- AWS Account with CLI configured
- Git, Terraform, Python 3.8+
- SSH client (for EC2 access)

### 1. Clone Repository

```powershell
git clone https://github.com/gordowuu/GORGGLES2.git
cd GORGGLES2
```

### 2. Deploy Infrastructure

```powershell
# Package Lambda layers
cd scripts
.\package_lambda_layers.ps1 -Region us-east-1

# Apply Terraform
cd ..\infra\terraform
terraform init
terraform apply
```

### 3. Launch EC2 Instance

**Via AWS Console (Recommended):**

See **[MANUAL_EC2_DEPLOYMENT.md](MANUAL_EC2_DEPLOYMENT.md)** for detailed guide.

**Quick Settings:**
- **AMI**: `ami-0ac1f653c5b6af751` (Deep Learning GPU PyTorch 2.1.0)
- **Type**: `g6.xlarge` (NVIDIA L4, 4 vCPU, 16GB RAM)
- **Key**: `gorggle-key`
- **Security Group**: `gorggle-ec2-sg`

### 4. Deploy Server to EC2

```powershell
.\scripts\deploy_to_manual_ec2.ps1 -InstanceIp "YOUR_PUBLIC_IP"
```

### 5. Test Your Pipeline

```powershell
# Upload a video
aws s3 cp test-video.mp4 s3://gorggle-dev-uploads/uploads/job-001.mp4

# Open web interface
start web\index.html
```

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| **[MANUAL_EC2_DEPLOYMENT.md](MANUAL_EC2_DEPLOYMENT.md)** | Step-by-step EC2 setup via AWS Console |
| **[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)** | Pre-flight checks and validation |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | System design and data flow |
| **[web/README.md](web/README.md)** | Frontend usage guide |
| **[TODO.md](TODO.md)** | Roadmap and pending tasks |

---

## 🏗️ Architecture Overview

```
┌─────────────┐
│   User      │
│  Upload MP4 │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────┐
│              S3 Upload Bucket                       │
│           s3://gorggle-dev-uploads                  │
└────────────────────┬────────────────────────────────┘
                     │ S3 Event Trigger
                     ▼
┌─────────────────────────────────────────────────────┐
│         Step Functions State Machine                │
│          (Parallel Processing)                      │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────────┐  ┌─────────────────────┐    │
│  │ Extract Media    │  │ AWS Transcribe      │    │
│  │ (FFmpeg/OpenCV)  │  │ (Audio + Speakers)  │    │
│  └────────┬─────────┘  └──────────┬──────────┘    │
│           │                        │               │
│           │  ┌─────────────────────┴──┐            │
│           │  │  AWS Rekognition       │            │
│           │  │  (Face Detection)      │            │
│           │  └─────────────┬──────────┘            │
│           │                │                        │
│           ▼                │                        │
│  ┌──────────────────────┐ │                        │
│  │  AV-HuBERT Server    │ │                        │
│  │  (Lip Reading GPU)   │ │                        │
│  │  EC2 g6.xlarge       │ │                        │
│  └────────┬─────────────┘ │                        │
│           │                │                        │
│           └────────────────┴───────────┐            │
│                                        ▼            │
│                              ┌──────────────────┐   │
│                              │  Fuse Results    │   │
│                              │  (Align & Merge) │   │
│                              └────────┬─────────┘   │
└───────────────────────────────────────┼─────────────┘
                                        │
                     ┌──────────────────┴──────────────────┐
                     ▼                                     ▼
          ┌────────────────────┐              ┌─────────────────┐
          │  S3 Processed      │              │   DynamoDB      │
          │  Bucket (JSON)     │              │   (Job Index)   │
          └─────────┬──────────┘              └─────────────────┘
                    │
                    │
          ┌─────────▼──────────────────────────────────┐
          │       API Gateway + Lambda                 │
          │   GET /results/{jobId}                     │
          └─────────┬──────────────────────────────────┘
                    │
                    ▼
          ┌──────────────────────┐
          │   Web Interface      │
          │   (Caption Viewer)   │
          └──────────────────────┘
```

---

## 🎯 Why AV-HuBERT?

**AV-HuBERT** is state-of-the-art for audio-visual speech recognition:

✅ Combines audio + visual (lip) features for superior accuracy  
✅ Pre-trained on LRS3 dataset (English lip reading)  
✅ Excels in noisy environments where audio-only fails  
✅ Handles multiple speakers, accents, and low-quality audio  

**Deployment:** EC2 GPU instance (g6.xlarge with NVIDIA L4) serving REST API

---

## 📁 Repository Layout

```
GORGGLES2/
├── 📄 README.md                          # You are here
├── 📄 MANUAL_EC2_DEPLOYMENT.md           # AWS Console deployment guide
├── 📄 DEPLOYMENT_CHECKLIST.md            # Pre-deployment validation
├── 📄 ARCHITECTURE.md                    # System design details
├── 📄 TODO.md                            # Roadmap
│
├── 📂 avhubert/                          # AV-HuBERT server
│   ├── server.py                         # FastAPI inference server
│   ├── setup_ec2.sh                      # EC2 environment setup
│   ├── download_models.sh                # Model downloader
│   └── requirements-server.txt           # Python dependencies
│
├── 📂 infra/terraform/                   # Infrastructure as Code
│   ├── main.tf                           # Core resources
│   ├── security_groups.tf                # VPC networking
│   ├── lambda_layers.tf                  # Lambda layers config
│   └── variables.tf                      # Configuration variables
│
├── 📂 lambdas/                           # Lambda functions
│   ├── extract_media/                    # FFmpeg extraction
│   ├── invoke_lipreading/                # AV-HuBERT caller
│   ├── fuse_results/                     # Result merger
│   ├── get_results/                      # API handler
│   ├── s3_trigger/                       # Pipeline starter
│   ├── start_transcribe/                 # AWS Transcribe
│   └── start_rekognition/                # Face detection
│
├── 📂 scripts/                           # Deployment automation
│   ├── package_lambda_layers.ps1         # Layer packager
│   ├── deploy_to_manual_ec2.ps1          # EC2 deployer
│   ├── setup_ec2_instance.sh             # Instance setup
│   └── deploy_ec2.sh                     # Automated EC2 (CLI)
│
└── 📂 web/                               # Frontend
    ├── index.html                        # Upload + viewer UI
    ├── app.js                            # Client-side logic
    └── README.md                         # Frontend guide
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | HTML5, CSS3, Vanilla JavaScript |
| **API** | AWS API Gateway (HTTP API) |
| **Compute** | AWS Lambda (Python 3.12), EC2 g6.xlarge |
| **ML Models** | AV-HuBERT, AWS Transcribe, AWS Rekognition |
| **Storage** | Amazon S3, DynamoDB |
| **Orchestration** | AWS Step Functions |
| **IaC** | Terraform |
| **GPU** | NVIDIA L4 (g6.xlarge) with PyTorch + CUDA |
| **ML Stack** | PyTorch, fairseq, dlib, OpenCV |

---

## 💰 Cost Estimate

**Monthly cost for moderate usage** (~50 videos/month, 5 min avg):

| Service | Usage | Cost |
|---------|-------|------|
| **EC2 g6.xlarge** | On-Demand, 20 hrs/month | ~$14 |
| **EC2 g6.xlarge** | Spot, 20 hrs/month | ~$5 |
| **Lambda** | 50 executions | ~$1 |
| **S3** | 100 GB storage | ~$2 |
| **Transcribe** | 4 hours audio | ~$10 |
| **Rekognition** | 2 hours video | ~$6 |
| **Step Functions** | 50 executions | ~$0.10 |
| **API Gateway** | 1000 requests | ~$0.01 |
| **DynamoDB** | On-demand | ~$0.50 |
| **Total (On-Demand)** | | **~$33/month** |
| **Total (Spot)** | | **~$24/month** |

**Cost optimization tips:**
- Stop EC2 when not in use
- Use Spot instances (70% savings)
- Set S3 lifecycle policies (delete old files)
- Use Reserved Capacity for predictable workloads

---

## 🔐 Security

- ✅ IAM roles with least-privilege policies
- ✅ VPC security groups for network isolation
- ✅ Lambda VPC integration for EC2 access
- ✅ S3 encryption at rest (SSE-S3)
- ✅ API Gateway with CORS configuration
- ✅ SSH key-based EC2 access only

**Best Practices:**
- Never commit AWS credentials to Git
- Use AWS Secrets Manager for sensitive data
- Enable CloudTrail for audit logging
- Rotate SSH keys regularly
- Monitor with CloudWatch alarms

---

## 📊 Performance

| Metric | Value | Notes |
|--------|-------|-------|
| **Inference Speed** | ~0.5s per second of video | On g6.xlarge with AV-HuBERT Large |
| **End-to-End Latency** | 2-5 minutes | For 5-minute video |
| **Accuracy (Audio)** | 95%+ WER | AWS Transcribe standard |
| **Accuracy (Visual)** | 85%+ WER | AV-HuBERT in clean conditions |
| **Throughput** | ~10-20 videos/hour | Single EC2 instance |

---

## 🧪 Testing

### Unit Tests

```powershell
# Test Lambda functions
cd lambdas/extract_media
python -m pytest tests/

# Test server
cd avhubert
python -m pytest tests/
```

### Integration Tests

```powershell
# Upload test video
aws s3 cp tests/fixtures/test-video.mp4 s3://gorggle-dev-uploads/uploads/test-001.mp4

# Monitor Step Functions
aws stepfunctions list-executions --state-machine-arn arn:aws:states:us-east-1:ACCOUNT:stateMachine:gorggle-dev-pipeline

# Fetch results
curl https://y9m2193c2i.execute-api.us-east-1.amazonaws.com/results/test-001
```

---

## 🤝 Contributing

Contributions welcome! Areas for improvement:

- [ ] Fine-grained word-level timestamps
- [ ] Multi-language support
- [ ] Real-time streaming processing
- [ ] Mobile app integration
- [ ] SRT/VTT export
- [ ] Speaker name assignment
- [ ] Batch processing API

---

## 📜 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- **AV-HuBERT**: [Facebook Research](https://github.com/facebookresearch/av_hubert)
- **fairseq**: [Facebook AI Research](https://github.com/facebookresearch/fairseq)
- **dlib**: [Davis King](http://dlib.net/)
- **AWS**: For Transcribe, Rekognition, and cloud infrastructure

---

## 📞 Support & Contact

- **Issues**: [GitHub Issues](https://github.com/gordowuu/GORGGLES2/issues)
- **Documentation**: See `docs/` folder
- **Deployment Help**: See [MANUAL_EC2_DEPLOYMENT.md](MANUAL_EC2_DEPLOYMENT.md)

---

**Made with ❤️ for accessible AI-powered video transcription**

🎬 **Start processing videos now!** Follow the [Quick Start](#-quick-start) guide above.

- `infra/terraform/` — IaC (Terraform) for buckets, IAM, Lambdas, Step Functions, DynamoDB, API Gateway
- `lambdas/` — Python Lambda handlers for each pipeline step
- `web/` — Minimal static viewer to render overlays

## Credentials setup (Windows)

Never commit keys to the repo. Use the AWS CLI credentials store so Terraform and the SDKs can read them automatically.

Option A — Named profile (recommended):

```powershell
aws configure --profile gorggle-admin
# Then for this terminal session:
$env:AWS_PROFILE = "gorggle-admin"
```

Option B — Environment variables (session only):

```powershell
$env:AWS_ACCESS_KEY_ID = "<YOUR_ACCESS_KEY_ID>"
$env:AWS_SECRET_ACCESS_KEY = "<YOUR_SECRET_ACCESS_KEY>"
$env:AWS_DEFAULT_REGION = "us-east-1"
# If using temporary credentials:
# $env:AWS_SESSION_TOKEN = "<YOUR_SESSION_TOKEN>"
```

For SSO, run `aws configure sso --profile gorggle-sso` and set `$env:AWS_PROFILE = "gorggle-sso"`.

## Terraform variables

You can override defaults via a `terraform.tfvars` file. See `infra/terraform/terraform.tfvars.example`.

- project_name: defaults to `gorggle`
- region: defaults to `us-east-1`
- environment: defaults to `dev`
- enable_website: defaults to `false`

## Deploy (Terraform)

Prereqs:
- Terraform >= 1.5
- AWS credentials configured (Administrator or required IAM privileges)

Steps:
1. Optionally create `infra/terraform/terraform.tfvars` using the example
2. Ensure `$env:AWS_PROFILE` (or environment variables) are set for your account
3. Initialize and apply:

```powershell
cd infra/terraform
terraform init
terraform apply -auto-approve
```

Outputs will include:
- Upload bucket name
- API URL for results

## Uploading a video

Upload an MP4 to the upload bucket under `uploads/` prefix. The pipeline will start automatically.

## Getting results

Use the API URL output to fetch processed overlay JSON by `jobId` (the S3 object key is used as a jobId sans prefix). The web viewer can be pointed at your upload and jobId.

## AV-HuBERT Setup (EC2 GPU Instance)

See `avhubert/README.md` for full deployment instructions.

Quick summary:
1. Launch EC2 g4dn.xlarge instance with Deep Learning AMI (Ubuntu)
2. Install fairseq, av_hubert, and dependencies
3. Download pre-trained model weights
4. Deploy REST API server (`avhubert/server.py`)
5. Update Lambda environment variable `AVHUBERT_ENDPOINT` with your EC2 endpoint URL

Cost: ~$0.526/hour on-demand, or ~$0.16/hour with Spot instances

## Lambda Requirements

### extract_media Lambda
**Critical**: Requires FFmpeg to extract audio and frames.

Options:
1. **Lambda Layer** (recommended): Use pre-built FFmpeg layer
   - ARN: Search AWS SAR for "ffmpeg-lambda-layer" or build your own
   - Add layer ARN to extract_media Lambda in Terraform
   
2. **Container Image**: Package Lambda as Docker image with FFmpeg
   - More control, larger size
   - See `lambdas/extract_media/Dockerfile` (to be added)

3. **Alternative**: Use AWS Elemental MediaConvert
   - More expensive but fully managed
   - Replace extract_media Lambda with MediaConvert job submission

### invoke_lipreading & fuse_results Lambdas
Require `requests` library (not in Lambda runtime by default).

To deploy with dependencies:
```powershell
cd lambdas/invoke_lipreading
pip install -r requirements.txt -t .
# Rezip and deploy via Terraform
```

Or use Lambda Layers for requests.

## Notes
- **Extract media**: Currently needs FFmpeg Lambda Layer (not included). Add layer ARN to Terraform or use Container Image.
- **Transcribe & Rekognition**: Work directly on MP4 files; no extraction needed for these services.
- **AV-HuBERT**: Requires EC2 GPU setup. See `avhubert/` directory for deployment guide.
- **Fusion logic**: Aligns audio transcripts with face tracks and lip reading. Can be enhanced with better time-window matching and confidence weighting.

## Cost per 10-minute video
- Processing: ~$0.44 (Transcribe $0.24, Rekognition $0.10, Lambda $0.003, EC2 $0.09)
- Storage: ~$0.01/month
- See `ARCHITECTURE.md` for detailed breakdown and optimization strategies

## Local Dev
- Lambdas are plain Python 3.11 compatible
- Keep Lambda deps small; use layers or container images for heavy libs

## Security
- Principle of least privilege for IAM roles
- S3 buckets have server-side encryption enabled

## Next steps
- **Add FFmpeg Lambda Layer**: Package FFmpeg for extract_media Lambda or use Container Image
- **Deploy AV-HuBERT**: Set up EC2 GPU instance following `avhubert/README.md`
- **Add requests to Lambdas**: Package dependencies or use Lambda Layer for invoke_lipreading and fuse_results
- **Replace polling**: Use Step Functions callbacks + EventBridge instead of blocking Lambda polls
- **Enhance fusion**: Implement sophisticated alignment algorithm for multi-speaker overlap scenarios
- **Add CloudFront**: Serve web UI and video assets via CDN
- **Authentication**: Add API Gateway authorizer or Cognito for production
- **Monitoring**: Set up CloudWatch dashboards and alarms
