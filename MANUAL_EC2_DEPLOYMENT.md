# 🚀 Manual EC2 Deployment Guide

Since your AWS account has GPU quota limits, follow this guide to manually launch your EC2 instance through the AWS Console and deploy the Gorggle AV-HuBERT server.

## Prerequisites

✅ **Completed:**
- Lambda layers published (requests)
- Terraform infrastructure deployed
- Security groups created
- API Gateway deployed
- SSH key pair created (`gorggle-key`)

## 📋 Step 1: Launch EC2 Instance via AWS Console

### Navigate to EC2
1. Go to: https://console.aws.amazon.com/ec2/v2/home?region=us-east-1
2. Click **"Launch Instance"**

### Instance Configuration

| Setting | Value | Notes |
|---------|-------|-------|
| **Name** | `gorggle-avhubert-server` | For easy identification |
| **AMI** | `ami-0ac1f653c5b6af751` | Deep Learning AMI GPU PyTorch 2.1.0 (Ubuntu 20.04) |
| **Instance Type** | `g6.xlarge` | NVIDIA L4 GPU, 4 vCPU, 16GB RAM |
| **Key Pair** | `gorggle-key` | Already created |
| **VPC** | Default VPC | Leave as default |
| **Subnet** | No preference | Auto-assign |
| **Auto-assign Public IP** | **Enable** | ✅ Required |
| **Security Group** | Select existing: `gorggle-ec2-sg` | `sg-0571933d52537d6c4` |
| **Storage** | `100 GiB` gp3 | For models + temp files |
| **IAM Role** | None | Not needed |

### Finding the Right AMI

**Option A - Search by ID:**
1. Click "Browse more AMIs"
2. Select "Community AMIs"
3. Search: `ami-0ac1f653c5b6af751`

**Option B - Search by Name:**
1. Click "Browse more AMIs"
2. Select "AWS Marketplace AMIs"
3. Search: "Deep Learning AMI GPU PyTorch 2.1"
4. Select the Ubuntu 20.04 version

### Security Group Settings

The `gorggle-ec2-sg` security group should have:

| Type | Protocol | Port | Source | Description |
|------|----------|------|--------|-------------|
| SSH | TCP | 22 | `129.210.115.224/32` | Your IP (admin access) |
| Custom TCP | TCP | 8000 | `172.31.0.0/16` | VPC CIDR (Lambda access) |
| Custom TCP | TCP | 8000 | `sg-0c1a7177f027bd8c8` | Lambda security group |

### Cost Estimate

| Type | Price | Use Case |
|------|-------|----------|
| **Spot** | ~$0.24/hr | 70% cheaper, may be interrupted |
| **On-Demand** | ~$0.69/hr | Guaranteed availability |

**Recommendation:** Start with **On-Demand** for stability, then switch to Spot once tested.

### Launch

1. Review all settings
2. Click **"Launch Instance"**
3. Wait ~2 minutes for instance to start
4. Note the **Public IPv4 address** (e.g., `3.84.123.45`)
5. Note the **Private IPv4 address** (e.g., `172.31.12.34`)

---

## 📦 Step 2: Deploy Gorggle to Your Instance

Once your instance is running, use the automated deployment script:

### PowerShell (Recommended)

```powershell
cd C:\Users\gdwu0\GORGGLE2\scripts

.\deploy_to_manual_ec2.ps1 -InstanceIp "YOUR_PUBLIC_IP"
```

**Example:**
```powershell
.\deploy_to_manual_ec2.ps1 -InstanceIp "3.84.123.45"
```

### What This Script Does:

1. ✅ Validates SSH access
2. ✅ Uploads setup script to EC2
3. ✅ Installs dependencies (Conda, PyTorch, fairseq, AV-HuBERT, dlib, OpenCV)
4. ✅ Uploads your model file (~1.3GB)
5. ✅ Uploads server.py
6. ✅ Configures systemd service
7. ✅ Starts the service
8. ✅ Updates Lambda environment variable with private IP

**Time:** ~15-20 minutes (mostly model upload and dependency installation)

---

## ⚙️ Step 3: Verify Deployment

### Check Service Status

```powershell
ssh -i ~/.ssh/gorggle-key.pem ubuntu@YOUR_PUBLIC_IP

# On EC2 instance:
sudo systemctl status avhubert.service

# View logs:
sudo journalctl -u avhubert.service -f
```

### Test Health Endpoint

```powershell
# From your local machine:
curl http://YOUR_PRIVATE_IP:8000/health

# Should return: {"status":"healthy","model_loaded":true}
```

### Verify Lambda Connection

The deployment script automatically updates the Lambda function with your EC2 private IP. To verify:

```powershell
aws lambda get-function-configuration `
  --region us-east-1 `
  --function-name gorggle-dev-invoke-lipreading `
  --query 'Environment.Variables.AVHUBERT_ENDPOINT' `
  --output text

# Should show: http://YOUR_PRIVATE_IP:8000
```

---

## 🎬 Step 4: Test End-to-End

### Upload a Test Video

```powershell
# Create a test job
aws s3 cp path\to\your\video.mp4 s3://gorggle-dev-uploads/uploads/test-job-001.mp4
```

### Monitor Processing

1. **Step Functions Console:**
   - Go to: https://console.aws.amazon.com/states/home?region=us-east-1#/statemachines
   - Click: `gorggle-dev-pipeline`
   - Watch execution in real-time

2. **CloudWatch Logs:**
   ```powershell
   # View Lambda logs:
   aws logs tail /aws/lambda/gorggle-dev-invoke-lipreading --follow

   # View EC2 server logs:
   ssh -i ~/.ssh/gorggle-key.pem ubuntu@YOUR_PUBLIC_IP
   sudo journalctl -u avhubert.service -f
   ```

### Retrieve Results

After processing completes (~2-5 minutes):

```powershell
# Via API:
curl https://y9m2193c2i.execute-api.us-east-1.amazonaws.com/results/test-job-001

# Or open web interface:
start web\index.html
```

---

## 🌐 Step 5: Use Web Interface

### Open Frontend

```powershell
cd C:\Users\gdwu0\GORGGLE2\web
start index.html
```

### Upload Tab

1. Click "📤 Upload Video"
2. Drag & drop your video
3. Copy the AWS CLI command
4. Run it to upload:
   ```powershell
   aws s3 cp "video.mp4" s3://gorggle-dev-uploads/uploads/job-123456.mp4
   ```
5. Note your Job ID

### Viewer Tab

1. Click "🎥 View Results"
2. Enter your Job ID
3. Enter video S3 URL (from processed bucket)
4. Click "Load Results"
5. Watch with AI captions!

---

## 📊 Management Commands

### View Server Logs

```powershell
ssh -i ~/.ssh/gorggle-key.pem ubuntu@YOUR_PUBLIC_IP
sudo journalctl -u avhubert.service -f
```

### Restart Service

```powershell
ssh -i ~/.ssh/gorggle-key.pem ubuntu@YOUR_PUBLIC_IP
sudo systemctl restart avhubert.service
```

### Update Server Code

```powershell
scp -i ~/.ssh/gorggle-key.pem avhubert/server.py ubuntu@YOUR_PUBLIC_IP:/tmp/
ssh -i ~/.ssh/gorggle-key.pem ubuntu@YOUR_PUBLIC_IP "sudo mv /tmp/server.py /opt/avhubert/ && sudo systemctl restart avhubert.service"
```

### Stop Instance (Save Money)

```powershell
# Get instance ID from EC2 console, then:
aws ec2 stop-instances --region us-east-1 --instance-ids i-YOUR_INSTANCE_ID
```

### Start Instance Again

```powershell
aws ec2 start-instances --region us-east-1 --instance-ids i-YOUR_INSTANCE_ID

# Wait for new IP, then update Lambda:
$newIp = (aws ec2 describe-instances --region us-east-1 --instance-ids i-YOUR_INSTANCE_ID --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text)

aws lambda update-function-configuration `
  --region us-east-1 `
  --function-name gorggle-dev-invoke-lipreading `
  --environment "Variables={AVHUBERT_ENDPOINT=http://${newIp}:8000}"
```

### Terminate Instance (Delete Everything)

```powershell
aws ec2 terminate-instances --region us-east-1 --instance-ids i-YOUR_INSTANCE_ID
```

---

## 🔧 Troubleshooting

### SSH Connection Refused

**Problem:** Can't SSH into instance

**Solution:**
1. Check security group allows your IP:
   ```powershell
   curl https://api.ipify.org  # Get your current IP
   ```
2. Update security group in AWS Console if IP changed
3. Verify key permissions:
   ```powershell
   icacls $HOME\.ssh\gorggle-key.pem
   ```

### Service Won't Start

**Problem:** `avhubert.service` is failed

**Solution:**
```powershell
ssh -i ~/.ssh/gorggle-key.pem ubuntu@YOUR_PUBLIC_IP

# Check detailed logs:
sudo journalctl -u avhubert.service -n 100 --no-pager

# Common issues:
# 1. Model not found: Check /opt/avhubert/models/
# 2. Conda env not activated: Check /home/ubuntu/miniconda3/envs/avhubert
# 3. Missing dependencies: Re-run setup script
```

### Lambda Timeouts

**Problem:** `invoke_lipreading` Lambda times out

**Solution:**
1. Check EC2 is running:
   ```powershell
   aws ec2 describe-instances --region us-east-1 --instance-ids i-YOUR_INSTANCE_ID
   ```
2. Verify security group allows Lambda SG:
   - Lambda SG: `sg-0c1a7177f027bd8c8`
   - EC2 SG should allow port 8000 from Lambda SG
3. Test endpoint from Lambda subnet:
   ```powershell
   ssh -i ~/.ssh/gorggle-key.pem ubuntu@YOUR_PUBLIC_IP
   curl http://localhost:8000/health
   ```

### Processing Takes Too Long

**Problem:** Videos take >5 minutes

**Possible Causes:**
- Video is very long (>10 min)
- CPU-only mode (no GPU detected)
- Network latency downloading from S3

**Solutions:**
1. Check GPU is available:
   ```powershell
   ssh -i ~/.ssh/gorggle-key.pem ubuntu@YOUR_PUBLIC_IP
   nvidia-smi  # Should show NVIDIA L4
   ```
2. Increase Lambda timeout (already set to 5 min)
3. Use smaller test videos first

---

## 💰 Cost Optimization

### Stop When Not in Use

```powershell
# Stop instance:
aws ec2 stop-instances --region us-east-1 --instance-ids i-YOUR_INSTANCE_ID

# Storage cost only: ~$8/month for 100GB
```

### Use Spot Instances

After initial testing, switch to Spot:

1. Create AMI from your instance
2. Launch new Spot instance with same AMI
3. 70% cost savings!

### Auto-Scaling (Future)

For production, consider:
- AWS Auto Scaling Groups
- Spot Fleet for cost savings
- Application Load Balancer
- Multiple availability zones

---

## 📚 Next Steps

✅ **You're Ready!** Your complete pipeline is deployed:

1. **Upload:** via CLI or web interface
2. **Process:** Lambda → S3 → Step Functions → EC2
3. **View:** API or web viewer with captions

### Optional Enhancements

- [ ] Request GPU quota increase for future scalability
- [ ] Configure CloudWatch alarms for EC2 health
- [ ] Set up auto-stop/start schedules
- [ ] Add CloudFront CDN for video delivery
- [ ] Implement direct browser S3 uploads (Cognito)
- [ ] Fine-tune time-aligned segments
- [ ] Add WebSocket for real-time progress

---

## 📞 Support

If you encounter issues:

1. **Check logs** (CloudWatch + journalctl)
2. **Verify security groups** (SSH + port 8000)
3. **Test health endpoint** (curl)
4. **Review Step Functions** execution details

Your infrastructure is production-ready once the EC2 instance is deployed! 🎉

---

Built with ❤️ for Gorggle AI Video Transcription
