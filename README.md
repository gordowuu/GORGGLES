# Gorggle (GORGGLES2)

AI-powered accessibility app that provides real-time transcription for deaf/hard-of-hearing users by combining audio transcription and AI-powered lip reading with multi-speaker identification and focus mode.

## Architecture Overview

- Upload: User uploads MP4 with audio to an S3 bucket
- Orchestration: S3 event triggers a Step Functions state machine
- Processing steps:
  1. Extract audio and frames (MediaConvert or placeholder) 
  2. Transcribe audio with AWS Transcribe (speaker diarization enabled)
  3. Detect/track faces with AWS Rekognition (video face detection)
  4. Lip reading via AV-HuBERT (served on SageMaker endpoint; placeholder here)
  5. Fusion logic combines audio + lip reading for best accuracy
  6. Speaker labeling maps transcripts to detected faces and bounding boxes
- Storage: Results JSON saved to S3 and indexes stored in DynamoDB
- API: API Gateway + Lambda to fetch results
- Display: Static web UI (S3/CloudFront-ready) overlays color-coded speaker captions on the video

## Repo Layout

- `infra/terraform/` — IaC (Terraform) for buckets, IAM, Lambdas, Step Functions, DynamoDB, API Gateway
- `lambdas/` — Python Lambda handlers for each pipeline step
- `web/` — Minimal static viewer to render overlays

## Deploy (Terraform)

Prereqs:
- Terraform >= 1.5
- AWS credentials configured (Administrator or required IAM privileges)

Steps:
1. Update variables in `infra/terraform/variables.tf` or via `terraform.tfvars`
2. Initialize and apply:

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

## AV-HuBERT placeholder

This repo scaffolds a SageMaker inference endpoint integration for lip reading but does not include the heavy model. Replace the placeholder with your model image/endpoint and update `invoke_lipreading` Lambda to call it.

## Notes
- Media extraction can be done via AWS Elemental MediaConvert. The `extract_media` Lambda is a placeholder to be replaced with MediaConvert submission or FFmpeg in a container/Lambda with EFS.
- Rekognition video APIs operate directly on the uploaded MP4; frame extraction remains for lip reading.
- Speaker diarization is enabled in Transcribe and then aligned to face tracks for spatial overlays.

## Local Dev
- Lambdas are plain Python 3.11 compatible
- Keep Lambda deps small; use layers or container images for heavy libs

## Security
- Principle of least privilege for IAM roles
- S3 buckets have server-side encryption enabled

## Next steps
- Swap lip reading placeholder to a real AV-HuBERT SageMaker endpoint
- Replace extract placeholder with MediaConvert job + EventBridge callback
- Add CloudFront for the static web app
