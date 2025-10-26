"""
Build model.tar.gz artifact for LipCoordNet deployment to SageMaker.

This creates a proper SageMaker model artifact with:
- code/inference.py (our custom handler)
- code/requirements.txt (dependencies including editdistance)

The model itself will be loaded from HuggingFace Hub at runtime.
"""
import os
import tarfile
import shutil
import tempfile
import boto3
import argparse

def create_lipcoordnet_artifact(output_path, s3_bucket=None, s3_key=None):
    """
    Create model.tar.gz with custom inference code and requirements.
    
    Args:
        output_path: Local path to save model.tar.gz
        s3_bucket: Optional S3 bucket to upload to
        s3_key: Optional S3 key for upload
    """
    print("Creating LipCoordNet model artifact...")
    
    # Create temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        code_dir = os.path.join(tmpdir, 'code')
        os.makedirs(code_dir)
        
        # Copy inference script
        src_inference = 'sagemaker/inference_lipcoordnet.py'
        dst_inference = os.path.join(code_dir, 'inference.py')
        shutil.copy(src_inference, dst_inference)
        print(f"✓ Copied {src_inference} -> code/inference.py")
        
        # Copy requirements
        src_requirements = 'sagemaker/requirements_lipcoordnet.txt'
        dst_requirements = os.path.join(code_dir, 'requirements.txt')
        shutil.copy(src_requirements, dst_requirements)
        print(f"✓ Copied {src_requirements} -> code/requirements.txt")
        
        # Create tar.gz
        print(f"\nCreating tarball: {output_path}")
        with tarfile.open(output_path, 'w:gz') as tar:
            tar.add(code_dir, arcname='code')
        
        # Get file size
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"✓ Created {output_path} ({size_mb:.2f} MB)")
        
        # Verify contents
        print("\nVerifying tarball contents:")
        with tarfile.open(output_path, 'r:gz') as tar:
            for member in tar.getmembers():
                print(f"  {member.name}")
        
        # Upload to S3 if specified
        if s3_bucket and s3_key:
            print(f"\nUploading to s3://{s3_bucket}/{s3_key}...")
            s3 = boto3.client('s3')
            s3.upload_file(output_path, s3_bucket, s3_key)
            print(f"✓ Uploaded to S3")
            print(f"\nS3 URI: s3://{s3_bucket}/{s3_key}")
        
        print("\n✅ Model artifact created successfully!")
        return output_path


def main():
    parser = argparse.ArgumentParser(description='Build LipCoordNet model artifact')
    parser.add_argument('--output', default='model-lipcoordnet.tar.gz',
                        help='Output path for model.tar.gz (default: model-lipcoordnet.tar.gz)')
    parser.add_argument('--bucket', help='S3 bucket to upload to (optional)')
    parser.add_argument('--key', default='sagemaker-models/model-lipcoordnet.tar.gz',
                        help='S3 key (default: sagemaker-models/model-lipcoordnet.tar.gz)')
    
    args = parser.parse_args()
    
    create_lipcoordnet_artifact(
        output_path=args.output,
        s3_bucket=args.bucket,
        s3_key=args.key
    )


if __name__ == '__main__':
    main()
