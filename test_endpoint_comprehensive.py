"""
Comprehensive test script for the AV-HuBERT SageMaker endpoint.
Tests all critical aspects after deployment.
"""
import json
import boto3
import os
import sys
from datetime import datetime

# Configuration
os.environ['AWS_PROFILE'] = 'gorggle-admin'
REGION = 'us-east-1'
ENDPOINT_NAME = 'gorggle-avhubert-dev-cpu'
LOG_GROUP = f'/aws/sagemaker/Endpoints/{ENDPOINT_NAME}'

# Initialize clients
sagemaker_runtime = boto3.client('sagemaker-runtime', region_name=REGION)
sagemaker = boto3.client('sagemaker', region_name=REGION)
logs = boto3.client('logs', region_name=REGION)

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def check_endpoint_status():
    """Check if endpoint is InService"""
    print_section("1. Checking Endpoint Status")
    try:
        response = sagemaker.describe_endpoint(EndpointName=ENDPOINT_NAME)
        status = response['EndpointStatus']
        print(f"Endpoint: {ENDPOINT_NAME}")
        print(f"Status: {status}")
        
        # Get instance type from production variants
        variants = response.get('ProductionVariants', [])
        if variants:
            instance_type = variants[0].get('CurrentInstanceCount', 'N/A')
            print(f"Instance Count: {instance_type}")
        
        print(f"Last Modified: {response['LastModifiedTime']}")
        
        if status != 'InService':
            print(f"\n⚠️  Endpoint is not ready yet. Current status: {status}")
            print("Please wait for it to reach 'InService' status and try again.")
            return False
        print("✅ Endpoint is InService and ready!")
        return True
    except Exception as e:
        print(f"❌ Error checking endpoint: {e}")
        return False

def get_latest_log_stream():
    """Get the most recent log stream"""
    try:
        response = logs.describe_log_streams(
            logGroupName=LOG_GROUP,
            orderBy='LastEventTime',
            descending=True,
            limit=1
        )
        if response['logStreams']:
            return response['logStreams'][0]['logStreamName']
        return None
    except Exception as e:
        print(f"⚠️  Could not get log stream: {e}")
        return None

def check_model_loading_logs():
    """Check CloudWatch logs for model loading success/failure"""
    print_section("2. Checking Model Loading Logs")
    
    stream_name = get_latest_log_stream()
    if not stream_name:
        print("❌ No log stream found")
        return False
    
    print(f"Checking log stream: {stream_name}\n")
    
    try:
        response = logs.get_log_events(
            logGroupName=LOG_GROUP,
            logStreamName=stream_name,
            startFromHead=True,
            limit=500
        )
        
        events = response.get('events', [])
        messages = [event['message'] for event in events]
        full_log = '\n'.join(messages)
        
        # Check for success indicators
        success_indicators = {
            'sys.path added': 'Added vendored av_hubert root to sys.path' in full_log,
            'avhubert imported': 'avhubert module imported successfully' in full_log,
            'model loading started': 'Loading AV-HuBERT from /opt/ml/model/avhubert.pt' in full_log,
            'model loaded': 'AV-HuBERT model loaded successfully' in full_log,
        }
        
        # Check for failure indicators
        failure_indicators = {
            'task inference error': 'Could not infer task type' in full_log,
            'import failed': 'Failed to import avhubert module' in full_log,
            'package not found': 'Vendored avhubert package not found' in full_log,
            'model load failed': 'Failed to load AV-HuBERT model, falling back to placeholder' in full_log,
        }
        
        print("Success Indicators:")
        all_success = True
        for check, passed in success_indicators.items():
            status = "✅" if passed else "❌"
            print(f"  {status} {check}: {passed}")
            if not passed:
                all_success = False
        
        print("\nFailure Indicators:")
        any_failure = False
        for check, failed in failure_indicators.items():
            status = "❌" if failed else "✅"
            print(f"  {status} {check}: {failed}")
            if failed:
                any_failure = True
        
        # Print relevant log excerpts
        if any_failure or not all_success:
            print("\n📋 Relevant Log Excerpts:")
            for msg in messages:
                if any(keyword in msg.lower() for keyword in ['avhubert', 'sys.path', 'failed', 'error', 'loading']):
                    print(f"  {msg[:200]}")
        
        return all_success and not any_failure
        
    except Exception as e:
        print(f"❌ Error checking logs: {e}")
        return False

def test_endpoint_invocation():
    """Test endpoint with a minimal payload"""
    print_section("3. Testing Endpoint Invocation")
    
    # Test with non-existent video to see graceful error handling
    payload = {
        "s3_bucket": "gorggle-dev-uploads",
        "s3_video_key": "test-nonexistent.mp4",
        "fps": 25
    }
    
    print(f"Test Payload:")
    print(json.dumps(payload, indent=2))
    print()
    
    try:
        response = sagemaker_runtime.invoke_endpoint(
            EndpointName=ENDPOINT_NAME,
            ContentType='application/json',
            Body=json.dumps(payload)
        )
        
        result = json.loads(response['Body'].read().decode('utf-8'))
        
        print("Response:")
        print(json.dumps(result, indent=2))
        print()
        
        # Analyze response
        text = result.get('text', '')
        note = result.get('note', '')
        error = result.get('error', '')
        
        if 'placeholder' in text.lower():
            print("⚠️  Got placeholder response - model may not be loaded correctly")
            return False
        elif 'not loaded' in text.lower():
            print("⚠️  Model not loaded - check logs")
            return False
        elif error:
            print(f"✅ Endpoint responding with error handling: {error}")
            print("   (This is expected for non-existent video)")
            return True
        else:
            print("✅ Endpoint is responding properly!")
            return True
            
    except Exception as e:
        print(f"❌ Error invoking endpoint: {e}")
        return False

def main():
    print(f"\n🔍 AV-HuBERT Endpoint Comprehensive Test")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Step 1: Check status
    if not check_endpoint_status():
        sys.exit(1)
    
    # Step 2: Check logs
    logs_ok = check_model_loading_logs()
    
    # Step 3: Test invocation
    invoke_ok = test_endpoint_invocation()
    
    # Summary
    print_section("Summary")
    
    if logs_ok and invoke_ok:
        print("✅ All checks passed!")
        print("\n✨ The AV-HuBERT endpoint is working correctly!")
        print("\nNext steps:")
        print("1. Test with a real video file")
        print("2. Integrate with Lambda function")
        print("3. Test end-to-end pipeline")
        sys.exit(0)
    else:
        print("⚠️  Some checks failed.")
        if not logs_ok:
            print("\n❌ Model loading issues detected in logs")
            print("   → Check CloudWatch logs for detailed error messages")
            print("   → Verify av_hubert package is properly vendored")
            print("   → Check sys.path manipulation in inference.py")
        if not invoke_ok:
            print("\n❌ Endpoint invocation issues")
            print("   → Endpoint may be returning placeholders")
            print("   → Check that model loaded successfully")
        sys.exit(1)

if __name__ == '__main__':
    main()
