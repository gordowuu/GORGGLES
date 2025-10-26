"""
Deploy SageMaker PyTorch endpoint with proper model.tar.gz artifact.

This script follows AWS SageMaker PyTorch documentation best practices:
1. Uses model_data pointing to S3 model.tar.gz artifact
2. Artifact contains model files at top level and code/ directory
3. Container uses script mode with inference handlers

Prerequisites:
- model.tar.gz uploaded to S3 (use build_model_artifact.py)
- IAM role with SageMaker permissions
- AWS credentials configured

Usage:
  python scripts/deploy_sagemaker_minimal.py \\
    --endpoint-name gorggle-test-minimal \\
    --model-data s3://bucket/path/model.tar.gz \\
    --role-arn arn:aws:iam::ACCOUNT:role/SageMakerExecutionRole
"""

import argparse
import os
import sys
from datetime import datetime

import boto3
from sagemaker import Session
from sagemaker.pytorch import PyTorchModel


def parse_args():
    parser = argparse.ArgumentParser(description='Deploy SageMaker PyTorch endpoint')
    parser.add_argument('--endpoint-name', required=True,
                        help='Name for the SageMaker endpoint')
    parser.add_argument('--model-data', required=True,
                        help='S3 URI to model.tar.gz (e.g., s3://bucket/path/model.tar.gz)')
    parser.add_argument('--role-arn', required=True,
                        help='IAM role ARN with SageMaker permissions')
    parser.add_argument('--region', default='us-east-1',
                        help='AWS region (default: us-east-1)')
    parser.add_argument('--instance-type', default='ml.m5.xlarge',
                        help='Instance type (default: ml.m5.xlarge)')
    parser.add_argument('--instance-count', type=int, default=1,
                        help='Number of instances (default: 1)')
    parser.add_argument('--framework-version', default='2.1',
                        help='PyTorch version (default: 2.1)')
    parser.add_argument('--py-version', default='py310',
                        help='Python version (default: py310)')
    parser.add_argument('--update', action='store_true',
                        help='Update existing endpoint in-place (UpdateEndpoint)')
    
    return parser.parse_args()


def main():
    args = parse_args()
    
    print(f"Deploying SageMaker endpoint: {args.endpoint_name}")
    print(f"  Model data: {args.model_data}")
    print(f"  Role: {args.role_arn}")
    print(f"  Instance: {args.instance_type} x {args.instance_count}")
    print(f"  Framework: PyTorch {args.framework_version} / {args.py_version}")
    print(f"  Region: {args.region}")
    
    # Setup SageMaker session
    boto3.setup_default_session(region_name=args.region)
    sagemaker_session = Session()
    
    # Create PyTorchModel
    # Note: entry_point is not needed here because it's in model.tar.gz as code/inference.py
    # SageMaker will automatically find and use it
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    model_name = f"{args.endpoint_name}-model-{timestamp}"
    
    print(f"\nCreating PyTorchModel: {model_name}")
    
    model = PyTorchModel(
        name=model_name,
        model_data=args.model_data,  # S3 URI to model.tar.gz
        role=args.role_arn,
        framework_version=args.framework_version,
        py_version=args.py_version,
        sagemaker_session=sagemaker_session,
    )
    
    # Deploy to endpoint
    print(f"\nDeploying endpoint: {args.endpoint_name}")
    if args.update:
        print("Update mode: will call UpdateEndpoint to reuse the existing endpoint name")
    print("This will take several minutes...")
    
    try:
        predictor = model.deploy(
            endpoint_name=args.endpoint_name,
            instance_type=args.instance_type,
            initial_instance_count=args.instance_count,
            wait=True,  # Block until deployment completes
            update_endpoint=args.update,
        )
        
        print(f"\n✓ Successfully deployed endpoint: {args.endpoint_name}")
        print(f"\nEndpoint details:")
        print(f"  Name: {predictor.endpoint_name}")
        print(f"  Region: {args.region}")
        print(f"\nTest invocation:")
        print(f'  aws sagemaker-runtime invoke-endpoint \\')
        print(f'    --endpoint-name {args.endpoint_name} \\')
        print(f'    --body \'{{"test": "input"}}\' \\')
        print(f'    --content-type application/json \\')
        print(f'    --profile gorggle-admin \\')
        print(f'    --region {args.region} \\')
        print(f'    output.json')
        
        return 0
        
    except Exception as e:
        print(f"\n✗ Deployment failed: {e}", file=sys.stderr)
        print("\nCheck CloudWatch logs:")
        print(f"  https://console.aws.amazon.com/cloudwatch/home?region={args.region}#logStream:group=/aws/sagemaker/Endpoints/{args.endpoint_name}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
