# 🚀 YOUR NEXT STEP: Launch EC2 Instance

Everything is ready! Follow these exact steps to complete your deployment.

---

## Step 1: Launch EC2 via AWS Console

### 1. Navigate to EC2
Open in your browser: **https://console.aws.amazon.com/ec2/v2/home?region=us-east-1**

### 2. Click "Launch Instance"

### 3. Configure Instance

| Field | Value to Enter | Notes |
|-------|---------------|-------|
| **Name** | `gorggle-avhubert-server` | Name tag |
| **AMI** | Click "Browse more AMIs" → Community AMIs → Search `ami-0ac1f653c5b6af751` | Deep Learning GPU PyTorch 2.1.0 |
| **Instance type** | Search and select: **`g6.xlarge`** | NVIDIA L4 GPU, 4 vCPU, 16GB RAM |
| **Key pair** | Select: **`gorggle-key`** | Already created |
| **Network** | Click "Edit" → Select existing security group | |
| **Security group** | Search and select: **`gorggle-ec2-sg`** | ID: `sg-0571933d52537d6c4` |
| **Storage** | Change to: **`100 GiB`** gp3 | For model + temp files |

### 4. Review and Launch
- Verify all settings match above
- Click **"Launch Instance"**
- Wait ~2 minutes

### 5. Get IP Addresses
- Click on your new instance
- Copy **Public IPv4 address** (e.g., `3.84.123.45`)
- Copy **Private IPv4 address** (e.g., `172.31.12.34`)

---

## Step 2: Deploy Server to EC2

Once instance is running, open PowerShell and run:

```powershell
cd C:\Users\gdwu0\GORGGLE2\scripts

.\deploy_to_manual_ec2.ps1 -InstanceIp "YOUR_PUBLIC_IP_HERE"
```

**Replace `YOUR_PUBLIC_IP_HERE` with the IP from Step 1.**

### Example:
```powershell
.\deploy_to_manual_ec2.ps1 -InstanceIp "3.84.123.45"
```

This script will:
- ✅ Test SSH connection
- ✅ Install all dependencies (Conda, PyTorch, fairseq, AV-HuBERT, dlib)
- ✅ Upload your model file (~1.3GB)
- ✅ Upload and configure server
- ✅ Start systemd service
- ✅ Update Lambda with EC2 endpoint

**Time:** 15-20 minutes

---

## Step 3: Test Your Pipeline

### Upload a video:

```powershell
# Create job ID
$jobId = "test-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

# Upload
aws s3 cp "path\to\your\video.mp4" "s3://gorggle-dev-uploads/uploads/${jobId}.mp4"

# Wait 2-5 minutes for processing
```

### Monitor:

**Step Functions Console:**
https://console.aws.amazon.com/states/home?region=us-east-1#/statemachines/view/arn:aws:states:us-east-1:613304588110:stateMachine:gorggle-dev-pipeline

**CloudWatch Logs:**
```powershell
aws logs tail /aws/lambda/gorggle-dev-invoke-lipreading --follow
```

### Get Results:

```powershell
curl "https://y9m2193c2i.execute-api.us-east-1.amazonaws.com/results/${jobId}"
```

Or open the web interface:
```powershell
start C:\Users\gdwu0\GORGGLE2\web\index.html
```

---

## 🎯 Quick Reference

### Your Infrastructure Details

| Component | Value |
|-----------|-------|
| **Region** | us-east-1 |
| **Upload Bucket** | gorggle-dev-uploads |
| **API URL** | https://y9m2193c2i.execute-api.us-east-1.amazonaws.com |
| **Your IP** | 129.210.115.224 |
| **SSH Key** | C:\Users\gdwu0\.ssh\gorggle-key.pem |
| **Model File** | C:\Users\gdwu0\GORGGLE2\models\large_noise_pt_noise_ft_433h.pt |

### Useful Commands

**SSH to EC2:**
```powershell
ssh -i ~/.ssh/gorggle-key.pem ubuntu@YOUR_PUBLIC_IP
```

**View Server Logs:**
```powershell
ssh -i ~/.ssh/gorggle-key.pem ubuntu@YOUR_PUBLIC_IP
sudo journalctl -u avhubert.service -f
```

**Restart Server:**
```powershell
ssh -i ~/.ssh/gorggle-key.pem ubuntu@YOUR_PUBLIC_IP
sudo systemctl restart avhubert.service
```

**Stop Instance (Save Money):**
```powershell
aws ec2 stop-instances --instance-ids i-YOUR_INSTANCE_ID --region us-east-1
```

---

## 📚 Documentation

- **[MANUAL_EC2_DEPLOYMENT.md](MANUAL_EC2_DEPLOYMENT.md)** - Detailed step-by-step guide
- **[DEPLOYMENT_SUMMARY.md](DEPLOYMENT_SUMMARY.md)** - What's deployed + quick links
- **[web/README.md](web/README.md)** - Frontend usage guide
- **[README.md](README.md)** - Full project overview

---

## 💰 Cost

**g6.xlarge pricing:**
- **On-Demand:** ~$0.69/hour ($14/month for 20 hours)
- **Spot:** ~$0.24/hour ($5/month for 20 hours) - 65% cheaper!

**Tip:** Stop the instance when not in use to save money.

---

## 🆘 Need Help?

**Common Issues:**

1. **Can't find AMI?**
   - Go to "Browse more AMIs" → "Community AMIs"
   - Search: `ami-0ac1f653c5b6af751`

2. **Can't select g6.xlarge?**
   - Type "g6.xlarge" in the instance type search box
   - If not showing, try region us-east-1

3. **SSH connection refused?**
   - Check security group is `gorggle-ec2-sg`
   - Verify your IP is whitelisted (129.210.115.224)

4. **Script fails?**
   - Check EC2 is in "running" state
   - Verify you can ping the public IP
   - Ensure SSH key has correct permissions

---

## ✅ Checklist

- [ ] Launch EC2 instance via AWS Console
- [ ] Note public and private IPs
- [ ] Run `.\deploy_to_manual_ec2.ps1 -InstanceIp "YOUR_IP"`
- [ ] Wait for deployment to complete
- [ ] Upload test video to S3
- [ ] Monitor Step Functions execution
- [ ] View results in web interface or via API
- [ ] Open `web\index.html` in browser

---

**You're almost there!** 🎉

Just launch the EC2 instance and run the deployment script. Your complete AI video transcription pipeline will be live in ~20 minutes!

🚀 **Go to:** https://console.aws.amazon.com/ec2/v2/home?region=us-east-1

Click **"Launch Instance"** and follow the values in Step 1 above.
