"""
Build proper model.tar.gz artifact for SageMaker PyTorch endpoint.

According to AWS SageMaker PyTorch documentation:
- For PyTorch 1.2+, model.tar.gz structure must be:
  model.tar.gz/
  |- model.pth (or any model files at top level)
  |- code/
     |- inference.py (your entry point script)
     |- requirements.txt (optional)

This script creates that structure and uploads to S3.
"""

import argparse
import os
import tarfile
import tempfile
import shutil
import boto3

def create_model_tarball(source_dir, entry_point, output_path, model_file_path=None, vendor_av_hubert=False):
    """
    Create model.tar.gz with correct structure.
    
    Args:
        source_dir: Directory containing inference script (sagemaker/)
        entry_point: Name of inference script (e.g., 'inference_minimal.py')
        output_path: Where to save model.tar.gz
        model_file_path: Optional path to model checkpoint to include
        vendor_av_hubert: If True, copy av_hubert package from vendor/ into code/
    """
    print(f"Creating model.tar.gz at {output_path}")
    
    # Create temporary directory for staging
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create code/ subdirectory
        code_dir = os.path.join(tmpdir, 'code')
        os.makedirs(code_dir, exist_ok=True)
        
        # Copy inference script as inference.py (SageMaker expects this name by default)
        src_script = os.path.join(source_dir, entry_point)
        dst_script = os.path.join(code_dir, 'inference.py')
        print(f"Copying {src_script} -> {dst_script}")
        shutil.copy2(src_script, dst_script)
        
        # Copy requirements.txt if it exists
        req_src = os.path.join(source_dir, 'requirements.txt')
        req_dst = os.path.join(code_dir, 'requirements.txt')
        if os.path.exists(req_src):
            print(f"Copying {req_src} -> {req_dst}")
            shutil.copy2(req_src, req_dst)
        else:
            print("No requirements.txt found; creating empty one")
            with open(req_dst, 'w') as f:
                f.write("# No additional requirements for minimal test\n")
        
        # Copy av_hubert package if requested
        if vendor_av_hubert:
            vendor_av_hubert_src = os.path.join(source_dir, 'vendor', 'av_hubert')
            if os.path.exists(vendor_av_hubert_src):
                av_hubert_dst = os.path.join(code_dir, 'av_hubert')
                print(f"Vendoring av_hubert package: {vendor_av_hubert_src} -> {av_hubert_dst}")
                shutil.copytree(vendor_av_hubert_src, av_hubert_dst, 
                               ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc', '.gitignore'))
            else:
                print(f"Warning: vendor_av_hubert=True but {vendor_av_hubert_src} not found; skipping")
        
        # Place model artifact at top level
        # If an explicit model file is provided, include it as avhubert.pt
        # Otherwise, create a small dummy file to satisfy container expectations
        if model_file_path and os.path.exists(model_file_path):
            dst_model = os.path.join(tmpdir, 'avhubert.pt')
            print(f"Including model weights: {model_file_path} -> {dst_model}")
            shutil.copy2(model_file_path, dst_model)
            model_root_file = dst_model
        else:
            model_root_file = os.path.join(tmpdir, 'model.pth')
            print(f"Creating dummy model file: {model_root_file}")
            with open(model_root_file, 'wb') as f:
                # Write minimal PyTorch-like file (just a placeholder)
                import pickle
                pickle.dump({'note': 'placeholder model for SageMaker deployment'}, f)
        
        # Create tarball
        print(f"Creating tarball: {output_path}")
        with tarfile.open(output_path, 'w:gz') as tar:
            # Add model file at root (avhubert.pt or dummy model.pth)
            arcname = os.path.basename(model_root_file)
            tar.add(model_root_file, arcname=arcname)
            # Add code/ directory
            tar.add(code_dir, arcname='code')
        
        print(f"Created {output_path} successfully")
        
        # Show contents
        print("\nTarball contents:")
        with tarfile.open(output_path, 'r:gz') as tar:
            for member in tar.getmembers():
                print(f"  {member.name}")


def upload_to_s3(local_path, bucket, key):
    """
    Upload model.tar.gz to S3.
    
    Args:
        local_path: Local path to model.tar.gz
        bucket: S3 bucket name
        key: S3 key (path)
    """
    s3_uri = f"s3://{bucket}/{key}"
    print(f"\nUploading {local_path} to {s3_uri}")
    
    s3 = boto3.client('s3')
    s3.upload_file(local_path, bucket, key)
    
    print(f"Upload complete: {s3_uri}")
    return s3_uri


def main():
    parser = argparse.ArgumentParser(description='Build and upload SageMaker model.tar.gz')
    parser.add_argument('--source-dir', default='sagemaker',
                        help='Directory containing inference script')
    parser.add_argument('--entry-point', default='inference.py',
                        help='Inference script filename')
    parser.add_argument('--output', default='model.tar.gz',
                        help='Output path for model.tar.gz')
    parser.add_argument('--bucket', required=True,
                        help='S3 bucket for upload')
    parser.add_argument('--key', default='sagemaker-models/model.tar.gz',
                        help='S3 key for upload')
    parser.add_argument('--model-file', default=None,
                        help='Optional path to local model checkpoint to include as avhubert.pt')
    parser.add_argument('--vendor-av-hubert', action='store_true',
                        help='Include av_hubert package from vendor/ in code/ directory')
    
    args = parser.parse_args()
    
    # Resolve paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    source_dir = os.path.join(project_root, args.source_dir)
    output_path = os.path.join(project_root, args.output)
    
    print(f"Source directory: {source_dir}")
    print(f"Entry point: {args.entry_point}")
    print(f"Output path: {output_path}")
    
    # Build tarball
    create_model_tarball(source_dir, args.entry_point, output_path, 
                        model_file_path=args.model_file, 
                        vendor_av_hubert=args.vendor_av_hubert)
    
    # Upload to S3
    s3_uri = upload_to_s3(output_path, args.bucket, args.key)
    
    print(f"\n✓ Model artifact ready at: {s3_uri}")
    print(f"\nUse this S3 URI when deploying with PyTorchModel:")
    print(f"  model_data='{s3_uri}'")


if __name__ == '__main__':
    main()
