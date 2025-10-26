"""
Test script for LipCoordNet SageMaker endpoint.
Tests the endpoint with a video from S3.
"""
import json
import boto3
import os
import sys
import argparse
from datetime import datetime

def parse_args():
    parser = argparse.ArgumentParser(description='Test LipCoordNet SageMaker endpoint')
    parser.add_argument('--endpoint-name', default='gorggle-lipcoordnet-dev',
                        help='SageMaker endpoint name (default: gorggle-lipcoordnet-dev)')
    parser.add_argument('--video-bucket', default='gorggle-dev-uploads',
                        help='S3 bucket containing video (default: gorggle-dev-uploads)')
    parser.add_argument('--video-key', default='test-video.mov',
                        help='S3 key for video file (default: test-video.mov)')
    parser.add_argument('--fps', type=int, default=25,
                        help='Video FPS (default: 25)')
    parser.add_argument('--region', default='us-east-1',
                        help='AWS region (default: us-east-1)')
    parser.add_argument('--profile', default='gorggle-admin',
                        help='AWS profile (default: gorggle-admin)')
    
    return parser.parse_args()


def print_section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def check_endpoint_status(sagemaker_client, endpoint_name):
    """Check if endpoint is InService"""
    print_section("1. Checking Endpoint Status")
    try:
        response = sagemaker_client.describe_endpoint(EndpointName=endpoint_name)
        status = response['EndpointStatus']
        print(f"Endpoint: {endpoint_name}")
        print(f"Status: {status}")
        
        # Get instance details
        variants = response.get('ProductionVariants', [])
        if variants:
            variant = variants[0]
            print(f"Instance Type: {variant.get('InstanceType', 'N/A')}")
            print(f"Instance Count: {variant.get('CurrentInstanceCount', 'N/A')}")
        
        print(f"Last Modified: {response['LastModifiedTime']}")
        
        if status != 'InService':
            print(f"\n⚠️  Endpoint is not ready. Current status: {status}")
            print("Please wait for it to reach 'InService' status and try again.")
            return False
        
        print("✅ Endpoint is InService and ready!")
        return True
    except Exception as e:
        print(f"❌ Error checking endpoint: {e}")
        print(f"\n💡 Make sure endpoint '{endpoint_name}' is deployed first:")
        print(f"   python scripts/deploy_lipcoordnet.py --endpoint-name {endpoint_name} --role-arn <YOUR_ROLE>")
        return False


def check_video_exists(s3_client, bucket, key):
    """Check if video exists in S3"""
    print_section("2. Checking Video File")
    try:
        response = s3_client.head_object(Bucket=bucket, Key=key)
        size_mb = response['ContentLength'] / (1024 * 1024)
        print(f"Video: s3://{bucket}/{key}")
        print(f"Size: {size_mb:.2f} MB")
        print(f"Last Modified: {response['LastModified']}")
        print("✅ Video file exists!")
        return True
    except Exception as e:
        print(f"❌ Error accessing video: {e}")
        print(f"\n💡 Upload a test video:")
        print(f"   aws s3 cp your-video.mp4 s3://{bucket}/{key}")
        return False


def invoke_endpoint(runtime_client, endpoint_name, bucket, key, fps):
    """Invoke the LipCoordNet endpoint"""
    print_section("3. Invoking LipCoordNet Endpoint")
    
    payload = {
        "s3_bucket": bucket,
        "s3_video_key": key,
        "fps": fps
    }
    
    print(f"Payload:")
    print(json.dumps(payload, indent=2))
    print(f"\nInvoking endpoint...")
    
    try:
        start_time = datetime.now()
        
        response = runtime_client.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType='application/json',
            Body=json.dumps(payload)
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Parse response
        result = json.loads(response['Body'].read().decode())
        
        print(f"✅ Inference completed in {duration:.2f} seconds")
        print(f"\nResponse:")
        print(json.dumps(result, indent=2))
        
        # Extract key information
        if 'transcription' in result:
            print(f"\n{'='*70}")
            print(f"TRANSCRIPTION RESULT:")
            print(f"{'='*70}")
            print(f"\n{result['transcription']}")
            print(f"\n{'='*70}")
        
        if 'confidence' in result:
            print(f"Confidence: {result['confidence']:.4f}")
        
        if 'processing_time_seconds' in result:
            print(f"Server Processing Time: {result['processing_time_seconds']:.2f}s")
        
        return True, result
        
    except Exception as e:
        print(f"❌ Endpoint invocation failed: {e}")
        print(f"\nTroubleshooting:")
        print(f"1. Check CloudWatch logs:")
        print(f"   https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logStream:group=/aws/sagemaker/Endpoints/{endpoint_name}")
        print(f"2. Verify endpoint is InService:")
        print(f"   aws sagemaker describe-endpoint --endpoint-name {endpoint_name}")
        print(f"3. Check video format (should be MP4/MOV with clear face/lips)")
        return False, None


def main():
    args = parse_args()
    
    # Set AWS profile
    os.environ['AWS_PROFILE'] = args.profile
    
    print(f"\n{'#'*70}")
    print(f"  LipCoordNet Endpoint Test")
    print(f"{'#'*70}")
    print(f"\nConfiguration:")
    print(f"  Endpoint: {args.endpoint_name}")
    print(f"  Video: s3://{args.video_bucket}/{args.video_key}")
    print(f"  FPS: {args.fps}")
    print(f"  Region: {args.region}")
    print(f"  Profile: {args.profile}")
    
    # Initialize AWS clients
    sagemaker_client = boto3.client('sagemaker', region_name=args.region)
    runtime_client = boto3.client('sagemaker-runtime', region_name=args.region)
    s3_client = boto3.client('s3', region_name=args.region)
    
    # Run tests
    tests_passed = 0
    total_tests = 3
    
    # Test 1: Check endpoint status
    if check_endpoint_status(sagemaker_client, args.endpoint_name):
        tests_passed += 1
    else:
        print("\n❌ Stopping tests - endpoint not available")
        sys.exit(1)
    
    # Test 2: Check video exists
    if check_video_exists(s3_client, args.video_bucket, args.video_key):
        tests_passed += 1
    else:
        print("\n❌ Stopping tests - video not found")
        sys.exit(1)
    
    # Test 3: Invoke endpoint
    success, result = invoke_endpoint(runtime_client, args.endpoint_name, 
                                     args.video_bucket, args.video_key, args.fps)
    if success:
        tests_passed += 1
    
    # Final summary
    print_section("Test Summary")
    print(f"Tests Passed: {tests_passed}/{total_tests}")
    
    if tests_passed == total_tests:
        print("✅ All tests passed! LipCoordNet endpoint is working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Please check the errors above.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
