# SageMaker AV-HuBERT Endpoint (Script Mode)

This folder contains a minimal entry script (`inference.py`) and a `requirements.txt` to deploy a real-time SageMaker endpoint using the AWS PyTorch inference container.

What you get now:
- A placeholder predict pipeline that extracts frames from an input S3 video using OpenCV and returns a single coarse segment. Replace the TODO areas to run AV-HuBERT and produce real transcripts.
- Optional dlib-based mouth ROI; falls back gracefully if dlib isn't present.

What you need to do next:
1) Deploy the endpoint using the provided helper script.
2) Set the endpoint name into Terraform (`sagemaker_endpoint_name`) and apply so the Lambda invokes SageMaker.

## Deploy the endpoint

Prereqs:
- Python >= 3.9 on your local machine, with `pip install sagemaker boto3`.
- An IAM role with SageMaker permissions (CreateModel, CreateEndpoint, etc.).
- Model artifact (model.tar.gz) uploaded to S3 (use `scripts/build_model_artifact.py`).

Steps (PowerShell):
```powershell
# 1. Build and upload model artifact
python scripts/build_model_artifact.py `
  --source-dir sagemaker `
  --entry-point inference.py `
  --output model-avhubert-vendored.tar.gz `
  --bucket gorggle-dev-uploads `
  --key sagemaker-models/model-avhubert-vendored.tar.gz `
  --model-file models/large_noise_pt_noise_ft_433h.pt `
  --vendor-av-hubert

# 2. Deploy or update endpoint
$env:AWS_PROFILE='gorggle-admin'
python scripts/deploy_sagemaker_minimal.py `
  --endpoint-name gorggle-avhubert-dev-cpu `
  --model-data s3://gorggle-dev-uploads/sagemaker-models/model-avhubert-vendored.tar.gz `
  --role-arn arn:aws:iam::<account_id>:role/service-role/SageMakerExecutionRole `
  --instance-type ml.m5.xlarge `
  --update  # Include --update to update existing endpoint
```

Notes:
- For GPU, use `--instance-type ml.g4dn.xlarge` and ensure your IAM/service limits allow it.
- The PyTorch DLC provides torch; we install OpenCV via `requirements.txt`.

## Input/Output contract

Input JSON (via SageMaker InvokeEndpoint):
- s3_bucket: S3 bucket containing the input video
- s3_video_key: S3 key for the input video
- fps (optional): target FPS for frame sampling (default 25)

Output JSON:
- text: transcript string
- segments: [{ start: number, end: number, text: string }]
- note: optional note about placeholder logic

## Wiring to Lambda

After deploying the endpoint, set the output endpoint name into Terraform variable `sagemaker_endpoint_name` and apply. The `invoke_lipreading` Lambda will call SageMaker if that variable is non-empty.

