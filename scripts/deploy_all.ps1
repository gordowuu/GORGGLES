# One command to package layers, apply Terraform, deploy EC2, and wire everything
# Requires: AWS CLI, Terraform, OpenSSH, Python (pip), PowerShell 5+

param(
    [string]$Region = "us-east-1",
    [string]$AdminIpCidr = "0.0.0.0/0",
    [string]$ModelFile = "models/large_noise_pt_noise_ft_433h.pt",
    [switch]$UseSpot
)

$ErrorActionPreference = "Stop"

function Assert-Command($name) {
  if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
    throw "Required command not found: $name"
  }
}

# Preconditions
Assert-Command aws
Assert-Command terraform
Assert-Command ssh
Assert-Command scp
Assert-Command python

$RepoRoot = Split-Path -Parent $PSCommandPath

Write-Host "[1/4] Packaging and publishing Lambda layers..." -ForegroundColor Yellow
& "$RepoRoot\package_lambda_layers.ps1" -Region $Region

Write-Host "[2/4] Applying Terraform (S3, DynamoDB, Lambdas, Step Functions)..." -ForegroundColor Yellow
Push-Location "$RepoRoot\..\infra\terraform"
$tfVarFile = "admin.auto.tfvars"
@" 
admin_ip_cidr = "$AdminIpCidr"
"@ | Set-Content -Path $tfVarFile -Encoding ASCII
terraform init
terraform apply -auto-approve
Pop-Location

Write-Host "[3/4] Deploying EC2 AV-HuBERT server..." -ForegroundColor Yellow
# Try to use bash (Git Bash) if available
$bash = Get-Command bash -ErrorAction SilentlyContinue
if ($bash) {
  $spotFlag = $UseSpot.IsPresent ? 'y' : 'n'
  $env:EC2_REGION = $Region
  $env:MODEL_FILE = (Resolve-Path (Join-Path (Split-Path -Parent $RepoRoot) $ModelFile)).Path

  function Convert-ToMsysPath($winPath) {
    $full = (Resolve-Path $winPath).Path
    $drive = $full.Substring(0,1).ToLower()
    $rest = $full.Substring(2).Replace("\\","/")
    return "/$drive$rest"
  }

  $repoWinPath = (Split-Path -Parent $RepoRoot)
  $repoMsys = Convert-ToMsysPath $repoWinPath
  & bash -lc "cd '$repoMsys' && bash ./scripts/deploy_ec2.sh" 
} else {
  Write-Warning "bash not found. Please run scripts/deploy_ec2.sh in WSL or Git Bash."
}

Write-Host "[4/4] All set. You can now upload a test video to the uploads bucket to trigger the pipeline." -ForegroundColor Green
