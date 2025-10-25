# Pre-Deployment Checklist for Groggle

## ✅ What You Have Completed

- [x] Downloaded AV-HuBERT model: `large_noise_pt_noise_ft_433h.pt` (~1GB)
- [x] Terraform infrastructure defined (25 AWS resources)
- [x] All Lambda function handlers implemented
- [x] AV-HuBERT server implementation with mouth ROI extraction
- [x] Face detection with dlib integration
- [x] Git repository initialized and pushed to GitHub
- [x] Comprehensive documentation (README, ARCHITECTURE, MODEL_SELECTION)

---

## 🚨 CRITICAL - Must Do Before Testing

### 1. Package Lambda Dependencies

**Problem:** Several Lambdas have missing Python dependencies

#### A. `extract_media` Lambda - FFmpeg Required ❌

**Current State:** Code uses `subprocess` to call FFmpeg, but FFmpeg is not included in Lambda runtime.

**Options:**

**Option 1: Lambda Layer (Recommended)**
```bash
# Download pre-built FFmpeg layer
wget https://github.com/serverlesspub/ffmpeg-aws-lambda-layer/releases/download/5.1.2/ffmpeg-layer.zip

# Or build your own
# See: https://github.com/serverlesspub/ffmpeg-aws-lambda-layer
```

**Option 2: Container Image**
```dockerfile
FROM public.ecr.aws/lambda/python:3.11
RUN yum install -y ffmpeg
COPY handler.py .
CMD ["handler.handler"]
```

**Action Required:**
```bash
# Add to Terraform
resource "aws_lambda_layer_version" "ffmpeg" {
  filename   = "ffmpeg-layer.zip"
  layer_name = "ffmpeg"
  compatible_runtimes = ["python3.11"]
}

# Attach to extract_media Lambda
layers = [aws_lambda_layer_version.ffmpeg.arn]
```

#### B. `invoke_lipreading` Lambda - requests library ❌

**Missing:** `import requests` (not in Lambda runtime by default)

**Action Required:**
```bash
# Create layer
mkdir -p python/lib/python3.11/site-packages
pip install requests -t python/lib/python3.11/site-packages
zip -r requests-layer.zip python
```

#### C. `fuse_results` Lambda - requests library ❌

**Missing:** `import requests` (same as above)

**Action Required:** Use same requests layer as `invoke_lipreading`

---

### 2. Deploy EC2 GPU Instance with AV-HuBERT

**Current State:** Server implementation complete, but instance not launched

**Steps:**

#### A. Launch EC2 Instance
```bash
# AWS Console or CLI
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \  # Ubuntu 22.04
  --instance-type g4dn.xlarge \
  --key-name your-keypair \
  --security-group-ids sg-xxxxx \
  --subnet-id subnet-xxxxx \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=gorggle-avhubert}]'
```

#### B. Upload Model to EC2
```bash
# On your local machine
scp -i your-key.pem large_noise_pt_noise_ft_433h.pt ubuntu@<ec2-ip>:/tmp/

# On EC2
sudo mkdir -p /opt/avhubert
sudo mv /tmp/large_noise_pt_noise_ft_433h.pt /opt/avhubert/model.pt
sudo chown ubuntu:ubuntu /opt/avhubert/model.pt
```

#### C. Run Setup Scripts
```bash
# SSH into EC2
ssh -i your-key.pem ubuntu@<ec2-ip>

# Clone repo and run setup
git clone https://github.com/gordowuu/GORGGLES2.git
cd GORGGLES2/avhubert
sudo bash setup_ec2.sh

# Download preprocessing files
bash download_models.sh
# (Downloads dlib models, mean_face.npy)

# Verify files
ls -lh /opt/avhubert/
# Should show: model.pt, *.dat, mean_face.npy
```

#### D. Deploy Server
```bash
# Copy systemd service
sudo cp /home/ubuntu/GORGGLES2/avhubert/avhubert.service /etc/systemd/system/

# Start service
sudo systemctl daemon-reload
sudo systemctl enable avhubert
sudo systemctl start avhubert

# Check status
sudo systemctl status avhubert
sudo journalctl -u avhubert -f
```

#### E. Update Lambda Environment Variable
```bash
# Get EC2 private IP
EC2_IP=$(aws ec2 describe-instances \
  --instance-ids i-xxxxx \
  --query 'Reservations[0].Instances[0].PrivateIpAddress' \
  --output text)

# Update Lambda
aws lambda update-function-configuration \
  --function-name gorggle-dev-invoke_lipreading \
  --environment "Variables={AVHUBERT_ENDPOINT=http://${EC2_IP}:8000}"
```

---

### 3. Configure Security Groups

**Problem:** Lambda cannot reach EC2 if security groups not configured

#### A. Create Lambda Security Group
```bash
aws ec2 create-security-group \
  --group-name gorggle-lambda-sg \
  --description "Security group for Gorggle Lambda functions" \
  --vpc-id vpc-xxxxx
```

#### B. Update EC2 Security Group
```bash
# Allow port 8000 from Lambda security group
aws ec2 authorize-security-group-ingress \
  --group-id sg-ec2-xxxxx \
  --protocol tcp \
  --port 8000 \
  --source-group sg-lambda-xxxxx
```

#### C. Update Terraform (if using VPC)
```hcl
resource "aws_security_group" "lambda" {
  name        = "${local.name}-lambda-sg"
  description = "Security group for Lambda functions"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ec2" {
  name        = "${local.name}-ec2-sg"
  description = "Security group for AV-HuBERT EC2"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
```

---

### 4. Update Lambda Configurations

#### A. Increase Memory and Timeout

**Current:** Defaults likely too low for video processing

**Action Required - Update Terraform:**
```hcl
resource "aws_lambda_function" "extract_media" {
  # ...
  memory_size = 1024  # Increase for FFmpeg
  timeout     = 300   # 5 minutes for video extraction
}

resource "aws_lambda_function" "invoke_lipreading" {
  # ...
  memory_size = 512
  timeout     = 600   # 10 minutes for lip reading (can be slow)
}

resource "aws_lambda_function" "fuse_results" {
  # ...
  memory_size = 512
  timeout     = 180   # 3 minutes for fusion
}
```

#### B. Add Environment Variables

**Missing from current Terraform:**
```hcl
resource "aws_lambda_function" "invoke_lipreading" {
  # ...
  environment {
    variables = {
      AVHUBERT_ENDPOINT = "http://<ec2-private-ip>:8000"  # Set after EC2 launch
      TIMEOUT          = "600"
    }
  }
}
```

---

## ⚠️ IMPORTANT - Should Do Before Production

### 5. Add IAM Permissions

**Verify Terraform includes these permissions:**

#### A. Lambda Execution Role
```hcl
# Already have S3 access, but verify:
- s3:GetObject (for reading videos)
- s3:PutObject (for writing results)
- transcribe:StartTranscriptionJob
- transcribe:GetTranscriptionJob
- rekognition:StartFaceDetection
- rekognition:GetFaceDetection
- dynamodb:PutItem
- dynamodb:GetItem
- dynamodb:UpdateItem
```

#### B. EC2 Instance Role
```hcl
# Create IAM role for EC2 to access S3
resource "aws_iam_role" "ec2_avhubert" {
  name = "${local.name}-ec2-avhubert"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ec2_s3" {
  role       = aws_iam_role.ec2_avhubert.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess"
}

resource "aws_iam_instance_profile" "ec2_avhubert" {
  name = "${local.name}-ec2-avhubert"
  role = aws_iam_role.ec2_avhubert.name
}
```

---

### 6. Add Error Handling

#### A. Step Functions - Add Retry Logic

**Current:** No retry configuration

**Add to Terraform:**
```hcl
resource "aws_sfn_state_machine" "pipeline" {
  # ... existing config
  
  definition = jsonencode({
    # ... existing states
    "InvokeLipReading": {
      "Type": "Task",
      "Resource": aws_lambda_function.invoke_lipreading.arn,
      "Retry": [
        {
          "ErrorEquals": ["States.Timeout", "Lambda.ServiceException"],
          "IntervalSeconds": 2,
          "MaxAttempts": 3,
          "BackoffRate": 2.0
        }
      ],
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.error",
          "Next": "FuseResults"  # Continue even if lip reading fails
        }
      ],
      "Next": "FuseResults"
    }
  })
}
```

#### B. Lambda - Add Try/Catch

**Update handlers with better error handling:**
```python
# Example for invoke_lipreading
try:
    response = requests.post(...)
    response.raise_for_status()
    result = response.json()
    return {**event, "lipreading": result}
except requests.exceptions.Timeout:
    return {**event, "lipreading": {"text": "", "error": "timeout"}}
except Exception as e:
    return {**event, "lipreading": {"text": "", "error": str(e)}}
```

---

### 7. Testing Prerequisites

#### A. Prepare Test Video
```bash
# Use a short video (10-30 seconds) for initial testing
# Requirements:
# - MP4 format
# - Clear speaker facing camera
# - Good lighting
# - Minimal background noise

# Upload to S3
aws s3 cp test_video.mp4 s3://gorggle-dev-uploads/test_video.mp4
```

#### B. Verify AWS Services
```bash
# Check Transcribe quota
aws service-quotas get-service-quota \
  --service-code transcribe \
  --quota-code L-6F8C4F6E

# Check Rekognition quota
aws service-quotas get-service-quota \
  --service-code rekognition \
  --quota-code L-F3B0B1FD
```

#### C. Enable CloudWatch Logs
```bash
# Verify Lambda log groups exist
aws logs describe-log-groups \
  --log-group-name-prefix /aws/lambda/gorggle-dev
```

---

## 📋 Deployment Sequence

Execute in this order:

### Phase 1: Infrastructure (30 min)
1. ✅ Package Lambda dependencies (FFmpeg layer, requests layer)
2. ✅ Update Terraform with layers, timeouts, memory
3. ✅ Run `terraform apply` with updated config
4. ✅ Verify all Lambda functions deployed

### Phase 2: EC2 Setup (60 min)
1. ✅ Launch g4dn.xlarge EC2 instance
2. ✅ Upload `large_noise_pt_noise_ft_433h.pt` to EC2
3. ✅ Run `setup_ec2.sh` (installs conda, PyTorch, fairseq, dlib)
4. ✅ Run `download_models.sh` (downloads dlib files, mean_face)
5. ✅ Verify all files present in `/opt/avhubert/`
6. ✅ Deploy systemd service
7. ✅ Test health endpoint: `curl http://localhost:8000/health`

### Phase 3: Integration (15 min)
1. ✅ Get EC2 private IP
2. ✅ Update Lambda env var: `AVHUBERT_ENDPOINT`
3. ✅ Configure security groups (Lambda → EC2 port 8000)
4. ✅ Test EC2 connectivity from Lambda VPC

### Phase 4: Testing (30 min)
1. ✅ Upload test video to S3
2. ✅ Monitor Step Functions execution
3. ✅ Check CloudWatch Logs for errors
4. ✅ Retrieve results via API Gateway
5. ✅ View results in web/index.html

---

## 🔧 Quick Fixes Needed

### Fix 1: Update `extract_media` handler

**Issue:** FFmpeg not available in Lambda

**Quick Fix (if no layer):** Use boto3 to copy MP4 to /tmp and let other services handle it
```python
# Simplified version without FFmpeg
def handler(event, context):
    job_id = event.get("jobId")
    input_obj = event.get("input", {})
    
    # For now, just pass through
    # AV-HuBERT can extract frames from video directly
    return {
        **event,
        "media": {
            "video_uri": f"s3://{input_obj['bucket']}/{input_obj['key']}",
            "fps": 25,
            "note": "Frame extraction will be done by AV-HuBERT server"
        }
    }
```

### Fix 2: Update `server.py` to handle S3 video directly

**Current:** Expects frames already extracted  
**Better:** Download video from S3, extract frames locally

```python
# Add to server.py
def download_video_from_s3(bucket: str, key: str) -> Path:
    """Download video file from S3"""
    video_path = Path(tempfile.mkdtemp()) / "video.mp4"
    s3_client.download_file(bucket, key, str(video_path))
    return video_path

def extract_frames_from_video(video_path: Path) -> List[Path]:
    """Extract frames using opencv"""
    frames = []
    cap = cv2.VideoCapture(str(video_path))
    frame_count = 0
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        if frame_count % 1 == 0:  # Every frame at 25fps
            frames.append(frame)
        frame_count += 1
    
    cap.release()
    return frames
```

---

## 📊 Verification Checklist

Before declaring "deployment complete," verify:

- [ ] All Lambda functions show "Active" state
- [ ] Step Functions state machine shows "Active"
- [ ] API Gateway endpoint returns 200 on health check
- [ ] EC2 instance running and accessible
- [ ] AV-HuBERT server responding on port 8000
- [ ] Security groups allow Lambda → EC2 communication
- [ ] S3 buckets created and accessible
- [ ] DynamoDB table created
- [ ] CloudWatch log groups exist for all Lambdas
- [ ] IAM roles have correct permissions

---

## 🐛 Known Issues to Address

### Issue 1: `server.py` has TODO
```python
# Line 261 in server.py
'segments': []  # TODO: Add time-aligned segments
```

**Fix:** Implement segment extraction from AV-HuBERT predictions
```python
def get_segments_from_predictions(predictions, fps=25):
    """Convert frame-level predictions to time segments"""
    segments = []
    current_segment = None
    
    for frame_idx, pred in enumerate(predictions):
        timestamp = frame_idx / fps
        if pred != current_segment:
            if current_segment:
                segments.append({
                    'start': start_time,
                    'end': timestamp,
                    'text': current_segment
                })
            current_segment = pred
            start_time = timestamp
    
    return segments
```

### Issue 2: No monitoring/alerting

**Add:** CloudWatch alarms for:
- Lambda errors
- Step Functions failures
- EC2 CPU/GPU utilization
- API Gateway 5xx errors

### Issue 3: No cost controls

**Add:**
- Budget alerts
- EC2 auto-stop after hours
- S3 lifecycle policies for processed files

---

## 💰 Cost Estimate for Testing

**10-minute test video:**
- Lambda: $0.02
- Transcribe: $0.024
- Rekognition: $0.10
- Step Functions: $0.001
- S3: $0.001
- EC2 g4dn.xlarge: $0.17 (20 min processing)
- **Total: ~$0.32 per test**

**Daily development (10 tests):** ~$3.20  
**Monthly estimate:** ~$96

---

## 🚀 Ready to Deploy?

You are **90% ready**. The remaining 10%:

1. **Package FFmpeg** for Lambda (1 hour)
2. **Deploy EC2 + model** (1 hour)
3. **Configure networking** (30 min)
4. **Test end-to-end** (30 min)

**Total time to full deployment: ~3 hours**

Would you like me to:
1. Create the Lambda layer packaging scripts?
2. Generate the complete EC2 setup script?
3. Update Terraform with missing configurations?
4. Create a testing script to automate validation?

Let me know which you'd like to tackle first!
