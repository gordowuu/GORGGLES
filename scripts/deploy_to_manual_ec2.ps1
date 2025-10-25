# Deploy Gorggle to manually launched EC2 instance
# Run this AFTER you've launched the instance through AWS Console
# Usage: .\deploy_to_manual_ec2.ps1 -InstanceIp "3.x.x.x"

param(
    [Parameter(Mandatory=$true)]
    [string]$InstanceIp,
    
    [string]$KeyPath = "$HOME\.ssh\gorggle-key.pem",
    [string]$ModelFile = "..\models\large_noise_pt_noise_ft_433h.pt",
    [string]$Region = "us-east-1"
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "🚀 Deploying Gorggle to EC2 Instance" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

# Validate files
if (-not (Test-Path $KeyPath)) {
    Write-Error "SSH key not found: $KeyPath"
}

$modelPath = Join-Path $repoRoot $ModelFile
if (-not (Test-Path $modelPath)) {
    Write-Error "Model file not found: $modelPath"
}

$serverPath = Join-Path $repoRoot "avhubert\server.py"
if (-not (Test-Path $serverPath)) {
    Write-Error "Server file not found: $serverPath"
}

Write-Host "✓ Instance IP: $InstanceIp" -ForegroundColor Green
Write-Host "✓ SSH Key: $KeyPath" -ForegroundColor Green
Write-Host "✓ Model: $modelPath" -ForegroundColor Green
Write-Host "✓ Server: $serverPath" -ForegroundColor Green
Write-Host ""

# Test SSH connection
Write-Host "→ Testing SSH connection..." -ForegroundColor Yellow
$testCmd = "echo 'SSH OK'"
& ssh -i $KeyPath -o StrictHostKeyChecking=no ubuntu@$InstanceIp $testCmd
if ($LASTEXITCODE -ne 0) {
    Write-Error "Cannot connect to instance. Check security group allows SSH from your IP."
}
Write-Host "✓ SSH connection successful" -ForegroundColor Green
Write-Host ""

# Upload setup script
Write-Host "→ Uploading setup script..." -ForegroundColor Yellow
$setupScript = Join-Path $scriptDir "setup_ec2_instance.sh"
& scp -i $KeyPath $setupScript ubuntu@${InstanceIp}:/tmp/
Write-Host "✓ Setup script uploaded" -ForegroundColor Green
Write-Host ""

# Run setup script
Write-Host "→ Running setup script (this will take 5-10 minutes)..." -ForegroundColor Yellow
Write-Host ""
& ssh -i $KeyPath ubuntu@$InstanceIp "bash /tmp/setup_ec2_instance.sh"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Setup script failed"
}
Write-Host ""
Write-Host "✓ Setup complete" -ForegroundColor Green
Write-Host ""

# Upload model file
Write-Host "→ Uploading model file (~1.3GB, may take 3-5 minutes)..." -ForegroundColor Yellow
& scp -i $KeyPath $modelPath ubuntu@${InstanceIp}:/tmp/large_noise_pt_noise_ft_433h.pt
if ($LASTEXITCODE -ne 0) {
    Write-Error "Model upload failed"
}

& ssh -i $KeyPath ubuntu@$InstanceIp "sudo mv /tmp/large_noise_pt_noise_ft_433h.pt /opt/avhubert/models/"
Write-Host "✓ Model uploaded" -ForegroundColor Green
Write-Host ""

# Upload server
Write-Host "→ Uploading server code..." -ForegroundColor Yellow
& scp -i $KeyPath $serverPath ubuntu@${InstanceIp}:/tmp/server.py
& ssh -i $KeyPath ubuntu@$InstanceIp "sudo mv /tmp/server.py /opt/avhubert/"
Write-Host "✓ Server uploaded" -ForegroundColor Green
Write-Host ""

# Create systemd service
Write-Host "→ Configuring systemd service..." -ForegroundColor Yellow
$serviceContent = @"
[Unit]
Description=AV-HuBERT Lip Reading Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/avhubert
Environment="PATH=/home/ubuntu/miniconda3/envs/avhubert/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/ubuntu/miniconda3/envs/avhubert/bin/python server.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"@

$serviceContent | & ssh -i $KeyPath ubuntu@$InstanceIp "sudo tee /etc/systemd/system/avhubert.service > /dev/null"

& ssh -i $KeyPath ubuntu@$InstanceIp @"
sudo systemctl daemon-reload
sudo systemctl enable avhubert.service
sudo systemctl start avhubert.service
"@

Write-Host "✓ Service configured and started" -ForegroundColor Green
Write-Host ""

# Wait for service to start
Write-Host "→ Waiting for service to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Check service status
$serviceStatus = & ssh -i $KeyPath ubuntu@$InstanceIp "systemctl is-active avhubert.service"
if ($serviceStatus -eq "active") {
    Write-Host "✓ Service is running!" -ForegroundColor Green
} else {
    Write-Warning "Service may not be running. Check logs with:"
    Write-Host "  ssh -i $KeyPath ubuntu@$InstanceIp sudo journalctl -u avhubert.service -f" -ForegroundColor Yellow
}
Write-Host ""

# Get private IP
$privateIp = & ssh -i $KeyPath ubuntu@$InstanceIp "curl -s http://169.254.169.254/latest/meta-data/local-ipv4"

# Update Lambda
Write-Host "→ Updating Lambda environment variable..." -ForegroundColor Yellow
try {
    $lambdaName = (aws lambda list-functions --region $Region --query "Functions[?contains(FunctionName, 'invoke_lipreading')].FunctionName" --output text) -split "`t" | Select-Object -First 1
    
    if ($lambdaName) {
        aws lambda update-function-configuration `
            --region $Region `
            --function-name $lambdaName `
            --environment "Variables={AVHUBERT_ENDPOINT=http://${privateIp}:8000}" `
            --output json | Out-Null
        
        Write-Host "✓ Lambda updated with endpoint: http://${privateIp}:8000" -ForegroundColor Green
    } else {
        Write-Warning "Could not find invoke_lipreading Lambda. Update manually."
    }
} catch {
    Write-Warning "Failed to update Lambda: $_"
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "🎉 Deployment Complete!" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "📊 Instance Details:" -ForegroundColor White
Write-Host "  Public IP:  $InstanceIp" -ForegroundColor White
Write-Host "  Private IP: $privateIp" -ForegroundColor White
Write-Host ""
Write-Host "🔗 Service Endpoints:" -ForegroundColor White
Write-Host "  Internal: http://${privateIp}:8000" -ForegroundColor White
Write-Host "  Health:   http://${privateIp}:8000/health" -ForegroundColor White
Write-Host ""
Write-Host "📝 Useful Commands:" -ForegroundColor White
Write-Host "  SSH:" -ForegroundColor Gray
Write-Host "    ssh -i $KeyPath ubuntu@$InstanceIp" -ForegroundColor Gray
Write-Host ""
Write-Host "  View logs:" -ForegroundColor Gray
Write-Host "    ssh -i $KeyPath ubuntu@$InstanceIp sudo journalctl -u avhubert.service -f" -ForegroundColor Gray
Write-Host ""
Write-Host "  Restart service:" -ForegroundColor Gray
Write-Host "    ssh -i $KeyPath ubuntu@$InstanceIp sudo systemctl restart avhubert.service" -ForegroundColor Gray
Write-Host ""
Write-Host "🚀 Next: Test your deployment!" -ForegroundColor Yellow
Write-Host "  1. Open web/index.html in a browser" -ForegroundColor White
Write-Host "  2. Or upload via CLI:" -ForegroundColor White
Write-Host "     aws s3 cp test.mp4 s3://gorggle-dev-uploads/uploads/test-job.mp4" -ForegroundColor Gray
Write-Host ""
