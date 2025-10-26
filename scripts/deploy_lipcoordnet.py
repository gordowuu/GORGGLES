"""
Deploy LipCoordNet from HuggingFace Hub to SageMaker.
Uses HuggingFaceModel for easy deployment.
"""
import argparse
from sagemaker.huggingface import HuggingFaceModel
import sagemaker
import boto3

def parse_args():
    parser = argparse.ArgumentParser(description='Deploy LipCoordNet to SageMaker')
    parser.add_argument('--endpoint-name', required=True,
                        help='Name for the SageMaker endpoint')
    parser.add_argument('--role-arn', required=True,
                        help='IAM role ARN with SageMaker permissions')
    parser.add_argument('--region', default='us-east-1',
                        help='AWS region (default: us-east-1)')
    parser.add_argument('--instance-type', default='ml.g5.xlarge',
                        help='Instance type (default: ml.g5.xlarge)')
    parser.add_argument('--instance-count', type=int, default=1,
                        help='Number of instances (default: 1)')
    parser.add_argument('--update', action='store_true',
                        help='Update existing endpoint in-place')
    
    return parser.parse_args()


def main():
    args = parse_args()
    
    print(f"Deploying LipCoordNet endpoint: {args.endpoint_name}")
    print(f"  Model: SilentSpeak/LipCoordNet from HuggingFace Hub")
    print(f"  Role: {args.role_arn}")
    print(f"  Instance: {args.instance_type} x {args.instance_count}")
    print(f"  Region: {args.region}")
    
    # Setup SageMaker session
    boto3.setup_default_session(region_name=args.region)
    sagemaker_session = sagemaker.Session()
    
    # Configuration for HuggingFace model from Hub
    hub_config = {
        'HF_MODEL_ID': 'SilentSpeak/LipCoordNet',  # Model ID from HuggingFace Hub
        'HF_TASK': 'custom',  # Custom task (not a standard transformers pipeline)
    }
    
    # Create HuggingFace Model
    print(f"\nCreating HuggingFaceModel...")
    
    huggingface_model = HuggingFaceModel(
        env=hub_config,
        role=args.role_arn,
        transformers_version='4.49.0',  # Use latest supported version
        pytorch_version='2.6.0',  # Match required PyTorch version
        py_version='py312',  # Use Python 3.12
        sagemaker_session=sagemaker_session
    )
    
    # Deploy the model
    print(f"\nDeploying endpoint: {args.endpoint_name}")
    if args.update:
        print("Update mode: will update existing endpoint")
    
    try:
        predictor = huggingface_model.deploy(
            initial_instance_count=args.instance_count,
            instance_type=args.instance_type,
            endpoint_name=args.endpoint_name,
            update_endpoint=args.update
        )
        
        print(f"\n✓ Successfully deployed endpoint: {args.endpoint_name}")
        print(f"\nEndpoint details:")
        print(f"  Name: {args.endpoint_name}")
        print(f"  Region: {args.region}")
        print(f"\nTest invocation:")
        print(f'  aws sagemaker-runtime invoke-endpoint \\')
        print(f'    --endpoint-name {args.endpoint_name} \\')
        print(f'    --body \'{{"s3_bucket": "your-bucket", "s3_video_key": "video.mp4"}}\' \\')
        print(f'    --content-type application/json \\')
        print(f'    --region {args.region} \\')
        print(f'    output.json')
        
    except Exception as e:
        print(f"\n✗ Deployment failed: {e}")
        print(f"\nCheck CloudWatch logs:")
        print(f"  https://console.aws.amazon.com/cloudwatch/home?region={args.region}#logStream:group=/aws/sagemaker/Endpoints/{args.endpoint_name}")
        raise


if __name__ == '__main__':
    main()
