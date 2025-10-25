import os
import boto3
import json

# Placeholder: call a SageMaker endpoint with frames prefix & optional face tracks
# For now, return empty segments.

SM_ENDPOINT = os.environ.get("SM_ENDPOINT", "")
smrt = boto3.client('sagemaker-runtime')


def handler(event, context):
    media = event.get("media", {})
    frames_prefix = media.get("frames_prefix")

    payload = {
        "frames_prefix": frames_prefix,
        "options": {"fps": 25}
    }

    segments = []
    if SM_ENDPOINT:
        resp = smrt.invoke_endpoint(EndpointName=SM_ENDPOINT,
                                    ContentType='application/json',
                                    Body=json.dumps(payload))
        body = resp['Body'].read()
        try:
            data = json.loads(body)
            segments = data.get("segments", [])
        except Exception:
            segments = []

    return {**event, "lipreading": {"segments": segments}}
