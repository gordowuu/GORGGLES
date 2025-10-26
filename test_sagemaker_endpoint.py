"""Quick test script to invoke the SageMaker endpoint and see response/errors."""
import json
import boto3
import os

os.environ['AWS_PROFILE'] = 'gorggle-admin'

client = boto3.client('sagemaker-runtime', region_name='us-east-1')

# Minimal test payload - use a bucket/key that doesn't exist to see graceful handling
payload = {
    "s3_bucket": "gorggle-dev-uploads",
    "s3_video_key": "test-nonexistent.mp4",
    "fps": 25
}

try:
    response = client.invoke_endpoint(
        EndpointName='gorggle-avhubert-dev-cpu',
        ContentType='application/json',
        Body=json.dumps(payload)
    )
    
    result = json.loads(response['Body'].read().decode('utf-8'))
    print("Success! Endpoint returned:")
    print(json.dumps(result, indent=2))
    
except Exception as e:
    print(f"Error invoking endpoint: {type(e).__name__}")
    print(f"Details: {e}")
