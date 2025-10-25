# Gorggle (GORGGLES2)

AI-powered accessibility app that provides real-time transcription for deaf/hard-of-hearing users by combining audio transcription and AI-powered lip reading with multi-speaker identification and focus mode.

## Architecture Overview

- Upload: User uploads MP4 with audio to an S3 bucket
- Orchestration: S3 event triggers a Step Functions state machine
- Processing steps:
  1. **Extract media**: FFmpeg extracts audio (WAV) and video frames (25 fps) to S3
  2. **Transcribe audio**: AWS Transcribe processes the original MP4 with speaker diarization
  3. **Detect faces**: AWS Rekognition tracks faces across the original MP4
  4. **Lip reading**: AV-HuBERT model on EC2 GPU analyzes extracted frames for visual speech recognition
  5. **Fusion**: Align and combine audio transcripts, face tracks, and lip reading for maximum accuracy
  6. **Speaker labeling**: Map transcriptions to detected faces with spatial positioning
- Storage: Results JSON saved to S3 and indexed in DynamoDB
- API: API Gateway + Lambda to fetch results
- Display: Static web UI overlays color-coded speaker captions on video

## Why AV-HuBERT?

AV-HuBERT is state-of-the-art for audio-visual speech recognition:
- Combines audio + visual (lip) features for superior accuracy
- Pre-trained on LRS3 dataset (English lip reading)
- Excels in noisy environments where audio-only fails
- Handles multiple speakers, accents, and low-quality audio

Deployment: EC2 GPU instance (g4dn.xlarge with NVIDIA T4) serving REST API

## Repo Layout

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
